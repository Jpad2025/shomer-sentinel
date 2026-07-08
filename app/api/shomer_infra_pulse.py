"""Shomer Pulse EWMA — latencia/pérdida suavizada (producto multi-cliente).

No altera infra_status.status; enriquece métricas predictivas y transiciones Pulse.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.api.shomer_common import get_config

logger = logging.getLogger(__name__)

PULSE_STATES = ("stable", "degrading", "recovered")

_BASELINE_ALPHA = 0.05


def _env_bool(key: str, default: str = "0") -> bool:
    return os.environ.get(key, default).strip().lower() in ("1", "true", "yes", "on")


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def pulse_config() -> Dict[str, Any]:
    enabled_cfg = get_config("infra.pulse.enabled")
    if enabled_cfg is not None:
        enabled = bool(enabled_cfg) if not isinstance(enabled_cfg, str) else enabled_cfg.strip().lower() in (
            "1", "true", "yes", "on",
        )
    else:
        enabled = _env_bool("INFRA_PULSE_ENABLED", "0")
    return {
        "enabled": enabled,
        "alpha": _env_float("INFRA_PULSE_ALPHA", 0.25),
        "latency_factor": _env_float("INFRA_PULSE_LATENCY_FACTOR", 1.5),
        "latency_floor_ms": _env_float("INFRA_PULSE_LATENCY_FLOOR_MS", 15.0),
        "loss_ewma_pct": _env_float("INFRA_PULSE_LOSS_EWMA_PCT", 25.0),
        "persist_ticks": _env_int("INFRA_PULSE_PERSIST_TICKS", 5),
        "timeout_ms": _env_float("INFRA_PULSE_TIMEOUT_MS", 9000.0),
        "alert_cooldown_sec": _env_int("INFRA_PULSE_ALERT_COOLDOWN_SEC", 1800),
    }


def pulse_enabled() -> bool:
    return bool(pulse_config()["enabled"])


def ewma(prev: Optional[float], sample: float, alpha: float) -> float:
    if prev is None:
        return sample
    return alpha * sample + (1.0 - alpha) * prev


def ensure_pulse_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS infra_pulse (
            ip                  TEXT PRIMARY KEY,
            ewma_latency_ms     REAL,
            ewma_loss_pct       REAL,
            baseline_latency_ms REAL,
            degrade_ticks       INTEGER DEFAULT 0,
            pulse_state         TEXT DEFAULT 'stable',
            last_alert_at       TEXT,
            updated_at          TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_infra_pulse_state ON infra_pulse (pulse_state)"
    )


def _sample_latency(
    latency_ms: Optional[float],
    loss_pct: float,
    status: str,
    timeout_ms: float,
) -> float:
    if latency_ms is not None and status != "offline":
        return float(latency_ms)
    if status == "offline" or loss_pct >= 100.0:
        return timeout_ms
    return float(latency_ms) if latency_ms is not None else timeout_ms


def _degrade_trigger(
    ewma_lat: float,
    ewma_loss: float,
    baseline: Optional[float],
    status: str,
    cfg: Dict[str, Any],
) -> Tuple[bool, str]:
    if status == "offline":
        return False, ""
    reasons = []
    floor = cfg["latency_floor_ms"]
    factor = cfg["latency_factor"]
    ref = baseline if baseline and baseline > 0 else floor
    threshold = max(ref * factor, floor * 2.0)
    if ewma_lat >= threshold:
        reasons.append(f"latencia EWMA {ewma_lat:.0f}ms > umbral {threshold:.0f}ms")
    if ewma_loss >= cfg["loss_ewma_pct"]:
        reasons.append(f"pérdida EWMA {ewma_loss:.0f}%")
    if not reasons:
        return False, ""
    return True, " · ".join(reasons)


def update_pulse(
    conn,
    *,
    ip: str,
    name: str,
    latency_ms: Optional[float],
    loss_pct: float,
    status: str,
    host_network_blip: bool = False,
    now_iso: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Actualiza EWMA y devuelve snapshot + transición opcional."""
    cfg = cfg or pulse_config()
    empty = {
        "enabled": False,
        "ip": ip,
        "pulse_state": "stable",
        "transition": None,
        "reason": "",
    }
    if not cfg["enabled"]:
        return empty
    if host_network_blip:
        return {**empty, "enabled": True, "skipped": "host_network_blip"}

    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    alpha = cfg["alpha"]
    sample_lat = _sample_latency(latency_ms, loss_pct, status, cfg["timeout_ms"])
    sample_loss = float(loss_pct or 0.0)

    row = conn.execute(
        "SELECT ewma_latency_ms, ewma_loss_pct, baseline_latency_ms, "
        "degrade_ticks, pulse_state, last_alert_at FROM infra_pulse WHERE ip=?",
        (ip,),
    ).fetchone()

    prev_lat = row["ewma_latency_ms"] if row else None
    prev_loss = row["ewma_loss_pct"] if row else None
    baseline = row["baseline_latency_ms"] if row else None
    degrade_ticks = int(row["degrade_ticks"] or 0) if row else 0
    prev_state = (row["pulse_state"] or "stable") if row else "stable"
    last_alert_at = row["last_alert_at"] if row else None

    ewma_lat = ewma(prev_lat, sample_lat, alpha)
    ewma_loss = ewma(prev_loss, sample_loss, alpha)

    if prev_state in ("stable", "recovered") and status in ("online", "degraded"):
        baseline = ewma(baseline, sample_lat, _BASELINE_ALPHA)

    firing, reason = _degrade_trigger(ewma_lat, ewma_loss, baseline, status, cfg)
    if firing:
        degrade_ticks += 1
    else:
        degrade_ticks = max(0, degrade_ticks - 1)

    persist = cfg["persist_ticks"]
    pulse_state = prev_state
    transition = None

    if degrade_ticks >= persist and status in ("online", "degraded"):
        if prev_state != "degrading":
            pulse_state = "degrading"
            transition = "enter_degrading"
    elif prev_state == "degrading" and degrade_ticks == 0:
        pulse_state = "recovered"
        transition = "exit_degrading"
    elif prev_state == "recovered" and degrade_ticks == 0:
        pulse_state = "stable"

    if status == "offline":
        degrade_ticks = 0
        if prev_state == "degrading":
            pulse_state = "recovered"
            transition = "exit_degrading"
        elif prev_state != "stable":
            pulse_state = "stable"

    conn.execute(
        """
        INSERT INTO infra_pulse
            (ip, ewma_latency_ms, ewma_loss_pct, baseline_latency_ms,
             degrade_ticks, pulse_state, last_alert_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ip) DO UPDATE SET
            ewma_latency_ms=excluded.ewma_latency_ms,
            ewma_loss_pct=excluded.ewma_loss_pct,
            baseline_latency_ms=excluded.baseline_latency_ms,
            degrade_ticks=excluded.degrade_ticks,
            pulse_state=excluded.pulse_state,
            last_alert_at=excluded.last_alert_at,
            updated_at=excluded.updated_at
        """,
        (
            ip, ewma_lat, ewma_loss, baseline, degrade_ticks, pulse_state,
            last_alert_at, now_iso,
        ),
    )

    return {
        "enabled": True,
        "ip": ip,
        "name": name,
        "pulse_state": pulse_state,
        "ewma_latency_ms": round(ewma_lat, 1),
        "ewma_loss_pct": round(ewma_loss, 1),
        "baseline_latency_ms": round(baseline, 1) if baseline is not None else None,
        "degrade_ticks": degrade_ticks,
        "transition": transition,
        "reason": reason,
        "status": status,
        "last_alert_at": last_alert_at,
    }


def mark_pulse_alerted(conn, ip: str, now_iso: Optional[str] = None) -> None:
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE infra_pulse SET last_alert_at=? WHERE ip=?",
        (now_iso, ip),
    )


def pulse_alert_due(pulse_row: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> bool:
    if pulse_row.get("transition") != "enter_degrading":
        return False
    cfg = cfg or pulse_config()
    last = pulse_row.get("last_alert_at")
    if not last:
        return True
    try:
        t0 = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - t0).total_seconds()
        return age >= cfg["alert_cooldown_sec"]
    except Exception:
        return True
