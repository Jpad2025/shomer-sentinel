"""Perfiles de monitoreo Infra — capa 'vivo' vs telemetría (Fase 3).

Cada equipo tiene un monitor_profile que define cómo decidir online/offline.
La telemetría (tóner, puertos SNMP) sigue en el ciclo SNMP aparte.

Perfiles (inferidos al crear equipo si no se especifica):
  ap_guardian   — AP: sin ping Infra, estado desde Guardian/infra_nodes
  network_gear  — Switch/router con SNMP: SNMP fresco manda sobre ping
  printer       — Impresora/POS: ping laxo (2 paquetes), SNMP si hay
  endpoint_tcp  — Servidor/POS con tcp_port: puerto TCP manda
  generic       — Ping estándar (3 paquetes)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

VALID_PROFILES = frozenset({
    "ap_guardian",
    "network_gear",
    "printer",
    "endpoint_tcp",
    "generic",
})

PROFILE_LABELS = {
    "ap_guardian": "AP (solo Guardian)",
    "network_gear": "Switch/Router (SNMP primario)",
    "printer": "Impresora/POS (SNMP o ping laxo)",
    "endpoint_tcp": "Servicio TCP primario",
    "generic": "Ping estándar",
}

SNMP_LIVENESS_MAX_AGE_SEC = int(os.environ.get("INFRA_SNMP_LIVENESS_MAX_AGE_SEC", "360"))


def resolve_monitor_profile(
    device_type: str,
    tcp_port: Optional[int],
    snmp_community: Optional[str],
    explicit: Optional[str] = None,
) -> str:
    """Perfil efectivo: explícito en BD o inferido por tipo/puertos/SNMP."""
    if explicit and explicit.strip() in VALID_PROFILES:
        return explicit.strip()
    dt = (device_type or "generic").strip().lower()
    snmp = (snmp_community or "").strip()
    if dt == "ap":
        return "ap_guardian"
    if dt in ("switch", "router", "nas", "controller") and snmp:
        return "network_gear"
    if dt in ("printer", "pos"):
        return "printer"
    if tcp_port and dt in ("server", "pos"):
        return "endpoint_tcp"
    return "generic"


def enrich_device_row(row: dict) -> dict:
    """Añade monitor_profile resuelto al dict de fila del poller."""
    row = dict(row)
    row["monitor_profile"] = resolve_monitor_profile(
        row.get("device_type") or "generic",
        row.get("tcp_port"),
        row.get("snmp_community"),
        row.get("monitor_profile"),
    )
    return row


def _parse_snmp_prev(existing_row: Optional[dict]) -> Optional[dict]:
    if not existing_row or not existing_row.get("snmp_data"):
        return None
    try:
        return json.loads(existing_row["snmp_data"])
    except Exception:
        return None


def _snmp_liveness_fresh(snmp_prev: dict) -> bool:
    polled_at = snmp_prev.get("polled_at")
    if not polled_at or not snmp_prev.get("ok"):
        return False
    try:
        age = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(polled_at.replace("Z", "+00:00"))
        ).total_seconds()
        return age <= SNMP_LIVENESS_MAX_AGE_SEC
    except Exception:
        return False


def derive_liveness(
    profile: str,
    ping_r: Any,
    tcp_ok: Optional[int],
    existing_row: Optional[dict],
) -> Tuple[str, Optional[float], float]:
    """
    Decide status/latency/loss para persistir en infra_status.
    ping_r: (status, latency, loss) o Exception.
    """
    if profile == "ap_guardian":
        return "unknown", None, 0.0

    if isinstance(ping_r, Exception):
        ping_status, latency, loss = "offline", None, 100.0
    else:
        ping_status, latency, loss = ping_r

    snmp_prev = _parse_snmp_prev(existing_row)

    if profile == "endpoint_tcp" and tcp_ok is not None:
        if tcp_ok == 1:
            return "online", latency, float(loss or 0.0)
        return "offline", None, 100.0

    if profile == "network_gear" and snmp_prev and _snmp_liveness_fresh(snmp_prev):
        if ping_status == "offline":
            return "online", latency, 0.0
        return ping_status, latency, float(loss or 0.0)

    if profile == "printer":
        if snmp_prev and snmp_prev.get("ok"):
            if ping_status == "offline":
                return "online", latency, float(loss or 0.0)
        if ping_status == "degraded":
            return "online", latency, float(loss or 0.0)
        return ping_status, latency, float(loss or 0.0)

    return ping_status, latency, float(loss or 0.0)


def ping_count_for_profile(profile: str, default_count: int) -> int:
    """Impresoras: menos paquetes, menos falsos offline en WiFi."""
    if profile == "printer":
        return int(os.environ.get("INFRA_PING_COUNT_PRINTER", "2"))
    return default_count
