"""Shomer Pulse — correlación de oleadas Infra (producto multi-cliente).

Publica contexto de poll en Redis para que el agente Telegram correlacione alertas
sin lógica por sitio. Complementa host_network_blip en el poller.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REDIS_KEY_POLL_CONTEXT = "infra:poll:context"
REDIS_KEY_BLIP_LAST = "infra:poll:blip_last"

PULSE_WAVE_MIN_DEVICES = int(os.environ.get("PULSE_WAVE_MIN_DEVICES", "3"))
PULSE_BLIP_CONTEXT_TTL_SEC = int(os.environ.get("PULSE_BLIP_CONTEXT_TTL_SEC", "300"))
PULSE_POLL_CONTEXT_TTL_SEC = int(os.environ.get("PULSE_POLL_CONTEXT_TTL_SEC", "120"))


def _ttl() -> int:
    return max(60, PULSE_POLL_CONTEXT_TTL_SEC)


def write_poll_context(
    redis_client,
    *,
    batch_id: str,
    host_network_blip: bool,
    offline_count: int,
    total_devices: int,
    gateway_ip: str = "",
    gateway_status: str = "",
    blip_skip_count: int = 0,
    pulse_events: Optional[list] = None,
) -> None:
    """Estado del último ciclo fast poll — leído por /infra/devices y el agente."""
    if not redis_client:
        return
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "batch_id": batch_id,
        "host_network_blip": bool(host_network_blip),
        "offline_count": offline_count,
        "total_devices": total_devices,
        "gateway_ip": gateway_ip,
        "gateway_status": gateway_status,
        "blip_skip_count": blip_skip_count,
        "wave_threshold": PULSE_WAVE_MIN_DEVICES,
        "ts": now,
        "pulse_events": pulse_events or [],
    }
    try:
        redis_client.setex(REDIS_KEY_POLL_CONTEXT, _ttl(), json.dumps(payload))
        if host_network_blip:
            blip_payload = {**payload, "kind": "host_network_blip"}
            redis_client.setex(
                REDIS_KEY_BLIP_LAST,
                max(60, PULSE_BLIP_CONTEXT_TTL_SEC),
                json.dumps(blip_payload),
            )
    except Exception as e:
        logger.debug("pulse correlate redis write: %s", e)


def read_poll_context(redis_client) -> Dict[str, Any]:
    if not redis_client:
        return {}
    try:
        raw = redis_client.get(REDIS_KEY_POLL_CONTEXT)
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return json.loads(raw)
    except Exception as e:
        logger.debug("pulse correlate redis read: %s", e)
        return {}


def read_last_blip(redis_client) -> Dict[str, Any]:
    if not redis_client:
        return {}
    try:
        raw = redis_client.get(REDIS_KEY_BLIP_LAST)
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return json.loads(raw)
    except Exception:
        return {}
