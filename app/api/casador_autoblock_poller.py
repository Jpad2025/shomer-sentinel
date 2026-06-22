"""Autobloqueo Hunter 24/7 — lee alertas Suricata y bloquea sin panel abierto."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Deque, Dict, Set

from app.api.casador_blocking import _auto_block_policy, _ip_in_exceptions, execute_hunter_block
from app.api.casador_support import _is_external_ip
from app.api.casador_support_state import _is_blocked
from app.api.casador_support_suricata import _read_suricata_recent_alerts

logger = logging.getLogger("shomer.casador.autoblock")

POLL_INTERVAL_SEC = 30
_SEEN: Set[str] = set()
_SEEN_ORDER: Deque[str] = deque()
_MAX_SEEN = 8000
_poller_running = False


def _alert_key(a: Dict[str, Any]) -> str:
    return "|".join(
        str(a.get(k) or "")
        for k in ("timestamp", "src_ip", "sid", "dest_ip", "dest_port")
    )


def _remember(key: str) -> None:
    if key in _SEEN:
        return
    _SEEN.add(key)
    _SEEN_ORDER.append(key)
    while len(_SEEN_ORDER) > _MAX_SEEN:
        old = _SEEN_ORDER.popleft()
        _SEEN.discard(old)


def _should_auto_block(alert: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    if not policy.get("enabled"):
        return False
    ip = (alert.get("src_ip") or "").strip()
    if not ip:
        return False
    sev_i = int(alert.get("severity") or 3)
    if sev_i > int(policy.get("min_severity") or 2):
        return False
    if policy.get("only_external") and not _is_external_ip(ip) and sev_i != 1:
        return False
    if _ip_in_exceptions(ip, policy.get("exceptions") or []):
        return False
    return True


async def _poller_tick() -> None:
    try:
        from app.api.shomer import is_module_enabled

        if not is_module_enabled("hunter"):
            return
    except ImportError:
        pass

    policy = _auto_block_policy()
    if not policy.get("enabled"):
        return

    alerts, _src = _read_suricata_recent_alerts(limit=150)
    if not alerts:
        return

    for alert in alerts:
        key = _alert_key(alert)
        if key in _SEEN:
            continue
        _remember(key)

        ip = (alert.get("src_ip") or "").strip()
        if not ip or alert.get("is_blocked") or _is_blocked(ip):
            continue
        if not _should_auto_block(alert, policy):
            continue

        try:
            result = await execute_hunter_block(
                ip,
                blocked_by="auto",
                alert_sid=alert.get("sid"),
                alert_signature=str(alert.get("signature") or ""),
                severity=int(alert.get("severity") or 3),
            )
            if result.get("success") and not result.get("already_blocked"):
                logger.warning(
                    "AUTO-BLOCK %s sid=%s sig=%s",
                    ip,
                    alert.get("sid"),
                    (alert.get("signature") or "")[:80],
                )
            elif result.get("skipped"):
                logger.debug("AUTO-BLOCK skip %s: %s", ip, result.get("detail"))
        except Exception as e:
            logger.error("AUTO-BLOCK error %s: %s", ip, e)


async def _poller_loop() -> None:
    global _poller_running
    logger.info("Hunter autoblock poller iniciado (intervalo %ss)", POLL_INTERVAL_SEC)
    while _poller_running:
        try:
            await _poller_tick()
        except Exception as e:
            logger.error("Hunter autoblock poller: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SEC)


def start_hunter_autoblock_poller() -> None:
    global _poller_running
    if _poller_running:
        return
    _poller_running = True
    asyncio.create_task(_poller_loop())
