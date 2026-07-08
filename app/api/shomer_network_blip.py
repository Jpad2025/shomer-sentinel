"""Detección de host_network_blip — corte transitorio de red del propio Shomer.

Compartido entre Inframonitor y Guardian. No cambia estados ni alertas cuando
el gateway está mal y muchos equipos caen a la vez en el mismo ciclo.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)

BLIP_MIN_DEVICES = int(os.environ.get("INFRA_BLIP_MIN_DEVICES", "8"))
BLIP_MIN_DEVICES_HIGH = int(os.environ.get("INFRA_BLIP_MIN_DEVICES_HIGH", "20"))
BLIP_PCT_INVENTORY = float(os.environ.get("INFRA_BLIP_PCT_INVENTORY", "0.5"))
BLIP_GATEWAY_LOSS_PCT = float(os.environ.get("INFRA_BLIP_GATEWAY_LOSS_PCT", "50"))
BLIP_GATEWAY_RTT_MS = float(os.environ.get("INFRA_BLIP_GATEWAY_RTT_MS", "300"))
BLIP_RECHECK_SEC = float(os.environ.get("INFRA_BLIP_RECHECK_SEC", "0.3"))


def ping_triplet_to_status(
    status: str,
    loss_pct: float,
    rtt_ms: Optional[float],
) -> str:
    """Normaliza salida de _ping (infra) a online/degraded/offline."""
    return status


def metrics_to_status(
    lan_ok: bool,
    loss_pct: float,
    rtt_ms: Optional[float],
    *,
    loss_degraded_pct: float = 60.0,
) -> str:
    """Convierte (_ping_metrics) Guardian a online/degraded/offline."""
    if not lan_ok or loss_pct >= 100.0:
        return "offline"
    if loss_pct >= loss_degraded_pct:
        return "degraded"
    return "online"


def gateway_unhealthy(
    status: str,
    loss_pct: float,
    rtt_ms: Optional[float],
) -> bool:
    """Gateway caído o degradado con pérdida/RTT altos — cuenta como blip posible."""
    if status == "offline":
        return True
    if status == "degraded":
        if loss_pct > BLIP_GATEWAY_LOSS_PCT:
            return True
        if rtt_ms is not None and rtt_ms > BLIP_GATEWAY_RTT_MS:
            return True
    return False


def mass_outage_threshold_met(offline_count: int, total_devices: int) -> bool:
    """Umbral dinámico: ≥8, ≥20, ≥50% del inventario o todos offline."""
    if total_devices <= 0 or offline_count <= 0:
        return False
    if offline_count >= total_devices:
        return True
    if offline_count >= int(total_devices * BLIP_PCT_INVENTORY + 0.5):
        return True
    if offline_count >= BLIP_MIN_DEVICES_HIGH:
        return True
    if offline_count >= BLIP_MIN_DEVICES:
        return True
    return False


def compute_blip_skip_ips(
    cycle_status: Dict[str, str],
    existing_status: Dict[str, str],
) -> Set[str]:
    """IPs cuyo paso a offline en este ciclo se debe omitir durante un blip."""
    return {
        ip
        for ip, st in cycle_status.items()
        if st == "offline" and existing_status.get(ip) not in ("offline",)
    }


def evaluate_host_network_blip(
    gateway_ip: str,
    gateway_status: str,
    gateway_loss: float,
    gateway_rtt: Optional[float],
    cycle_status: Dict[str, str],
    existing_status: Dict[str, str],
    total_devices: int,
) -> Tuple[bool, Set[str]]:
    """Evalúa blip sincrónico (sin recheck). Devuelve (is_blip, skip_ips)."""
    if not gateway_ip:
        return False, set()
    if not gateway_unhealthy(gateway_status, gateway_loss, gateway_rtt):
        return False, set()

    offline_count = sum(1 for s in cycle_status.values() if s == "offline")
    if not mass_outage_threshold_met(offline_count, total_devices):
        return False, set()

    skip_ips = compute_blip_skip_ips(cycle_status, existing_status)
    return True, skip_ips


async def evaluate_host_network_blip_async(
    gateway_ip: str,
    gateway_ping_coro_factory: Callable[[], Any],
    cycle_status: Dict[str, str],
    existing_status: Dict[str, str],
    total_devices: int,
    *,
    log_prefix: str = "poll",
    batch_id: str = "",
) -> Tuple[bool, Set[str]]:
    """Evalúa blip con segundo ping al gateway 300 ms después si aplica."""
    if not gateway_ip:
        return False, set()

    gw = await gateway_ping_coro_factory()
    if isinstance(gw, Exception):
        gw_status, gw_loss, gw_rtt = "offline", 100.0, None
    else:
        gw_status, gw_loss, gw_rtt = gw

    is_blip, skip_ips = evaluate_host_network_blip(
        gateway_ip,
        gw_status,
        gw_loss,
        gw_rtt,
        cycle_status,
        existing_status,
        total_devices,
    )
    if not is_blip:
        return False, set()

    await asyncio.sleep(BLIP_RECHECK_SEC)
    gw2 = await gateway_ping_coro_factory()
    if isinstance(gw2, Exception):
        gw2_status, gw2_loss, gw2_rtt = "offline", 100.0, None
    else:
        gw2_status, gw2_loss, gw2_rtt = gw2

    if not gateway_unhealthy(gw2_status, gw2_loss, gw2_rtt):
        logger.info(
            "%s: host_network_blip descartado tras recheck %.0fms — gateway %s recuperado",
            log_prefix, BLIP_RECHECK_SEC * 1000, gateway_ip,
        )
        return False, set()

    offline_count = sum(1 for s in cycle_status.values() if s == "offline")
    loss_display = (
        f"{gw2_loss:.0f}%"
        if gw2_loss is not None
        else "—"
    )
    logger.warning(
        "%s: host_network_blip confirmado — gateway %s (%s, loss=%s, rtt=%s) y "
        "%d/%d equipos offline en el mismo ciclo. Se omiten %d transiciones offline.",
        log_prefix,
        gateway_ip,
        gw2_status,
        loss_display,
        f"{gw2_rtt:.0f}ms" if gw2_rtt is not None else "—",
        offline_count,
        total_devices,
        len(skip_ips),
    )
    try:
        from app.api.shomer_host_health import record_blip_event

        record_blip_event(
            gateway_ip=gateway_ip,
            gateway_status=gw2_status,
            gateway_loss=float(gw2_loss or 0),
            gateway_rtt_ms=gw2_rtt,
            offline_count=offline_count,
            total_devices=total_devices,
            batch_id=batch_id or log_prefix,
        )
    except Exception as e:
        logger.debug("blip persist: %s", e)
    return True, skip_ips
