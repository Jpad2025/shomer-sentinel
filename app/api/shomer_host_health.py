"""Salud del host Shomer — blips confirmados y contadores NIC (delta RX dropped).

Producto multi-cliente: persiste eventos `host_network_blip` y muestras periódicas
de `/sys/class/net/<iface>/statistics/*` para correlacionar visibilidad transitoria
con descartes en la NIC de gestión (típ. `eno1`).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.api.shomer_common import get_db

logger = logging.getLogger(__name__)

HOST_HEALTH_NIC = os.environ.get("HOST_HEALTH_NIC", "eno1")
NIC_SAMPLE_INTERVAL_SEC = int(os.environ.get("HOST_NIC_SAMPLE_INTERVAL_SEC", "3600"))
NIC_COUNTERS = ("rx_dropped", "rx_errors", "rx_missed_errors")

_last_nic_sample_ts: float = 0.0


def ensure_host_health_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS infra_blip_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            gateway_ip TEXT,
            gateway_status TEXT,
            gateway_loss REAL,
            gateway_rtt_ms REAL,
            offline_count INTEGER,
            total_devices INTEGER,
            batch_id TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_blip_events_ts ON infra_blip_events (ts)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS host_nic_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iface TEXT NOT NULL,
            rx_dropped INTEGER,
            rx_errors INTEGER,
            rx_missed_errors INTEGER,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_nic_samples_iface_ts "
        "ON host_nic_samples (iface, recorded_at)"
    )


def record_blip_event(
    *,
    gateway_ip: str,
    gateway_status: str,
    gateway_loss: float,
    gateway_rtt_ms: Optional[float],
    offline_count: int,
    total_devices: int,
    batch_id: str = "",
) -> None:
    """Persiste un `host_network_blip` confirmado (post-recheck 300 ms)."""
    try:
        with get_db() as conn:
            ensure_host_health_tables(conn)
            conn.execute(
                """
                INSERT INTO infra_blip_events
                (gateway_ip, gateway_status, gateway_loss, gateway_rtt_ms,
                 offline_count, total_devices, batch_id, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gateway_ip,
                    gateway_status,
                    gateway_loss,
                    gateway_rtt_ms,
                    offline_count,
                    total_devices,
                    batch_id or "",
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.warning("record_blip_event: %s", e)


def _read_sysfs_counter(iface: str, counter: str) -> Optional[int]:
    path = f"/sys/class/net/{iface}/statistics/{counter}"
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def read_nic_counters(iface: str = HOST_HEALTH_NIC) -> Dict[str, Optional[int]]:
    """Lee contadores kernel acumulados (no son delta por sí solos)."""
    return {c: _read_sysfs_counter(iface, c) for c in NIC_COUNTERS}


def persist_nic_sample(iface: str = HOST_HEALTH_NIC) -> None:
    """Guarda una muestra de contadores NIC en SQLite."""
    counters = read_nic_counters(iface)
    if all(v is None for v in counters.values()):
        return
    try:
        with get_db() as conn:
            ensure_host_health_tables(conn)
            conn.execute(
                """
                INSERT INTO host_nic_samples
                (iface, rx_dropped, rx_errors, rx_missed_errors, recorded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    iface,
                    counters.get("rx_dropped"),
                    counters.get("rx_errors"),
                    counters.get("rx_missed_errors"),
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.debug("persist_nic_sample: %s", e)


def maybe_sample_nic_counters(force: bool = False) -> bool:
    """Muestrea NIC como máximo cada NIC_SAMPLE_INTERVAL_SEC (salvo force=True)."""
    global _last_nic_sample_ts
    import time

    now = time.time()
    if not force and (now - _last_nic_sample_ts) < max(60, NIC_SAMPLE_INTERVAL_SEC):
        return False
    _last_nic_sample_ts = now
    persist_nic_sample(HOST_HEALTH_NIC)
    return True


def _nic_delta_in_window(
    conn,
    iface: str,
    hours: float = 24.0,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Delta de contadores entre muestra más antigua y más reciente en la ventana."""
    rows = conn.execute(
        """
        SELECT rx_dropped, rx_errors, rx_missed_errors, recorded_at
        FROM host_nic_samples
        WHERE iface = ? AND recorded_at > datetime('now', ?)
        ORDER BY recorded_at ASC
        """,
        (iface, f"-{hours} hours"),
    ).fetchall()
    if len(rows) < 2:
        return None, None, None
    first, last = rows[0], rows[-1]
    deltas = []
    for col in ("rx_dropped", "rx_errors", "rx_missed_errors"):
        a, b = first[col], last[col]
        if a is None or b is None:
            deltas.append(None)
        else:
            deltas.append(max(0, int(b) - int(a)))
    return deltas[0], deltas[1], deltas[2]


def blip_stats_24h(conn) -> Dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt,
               MAX(ts) AS last_ts,
               AVG(offline_count) AS avg_offline
        FROM infra_blip_events
        WHERE ts > datetime('now', '-24 hours')
        """
    ).fetchone()
    cnt = int(row["cnt"] or 0) if row else 0
    last_ts = row["last_ts"] if row else None
    avg_off = round(float(row["avg_offline"] or 0), 1) if row and row["avg_offline"] else 0
    recent = conn.execute(
        """
        SELECT gateway_ip, gateway_status, gateway_loss, gateway_rtt_ms,
               offline_count, total_devices, ts
        FROM infra_blip_events
        WHERE ts > datetime('now', '-24 hours')
        ORDER BY ts DESC LIMIT 5
        """
    ).fetchall()
    return {
        "count_24h": cnt,
        "last_at": last_ts,
        "avg_offline": avg_off,
        "recent": [dict(r) for r in recent],
    }


def format_blip_daily_section(stats: Dict[str, Any]) -> str:
    """Texto plano para resumen diario / Telegram."""
    cnt = stats.get("count_24h", 0)
    if cnt == 0:
        return (
            "📡 Visibilidad Shomer (24h): sin blips confirmados — "
            "el hotel no tuvo cortes transitorios de visibilidad desde este servidor."
        )
    avg = stats.get("avg_offline", 0)
    last = stats.get("last_at") or "—"
    lines = [
        f"📡 Visibilidad Shomer (24h): {cnt} blip(s) confirmado(s)",
        f"   Último: {last} · ~{avg:.0f} equipos afectados por ciclo (transitorio, no caída real)",
        "   El poller omitió transiciones offline — Guardian no debió alertar oleada.",
    ]
    return "\n".join(lines)


def _format_int(n: Optional[int]) -> str:
    if n is None:
        return "—"
    return f"{n:,}".replace(",", ".")


def nic_health_summary(
    conn,
    iface: str = HOST_HEALTH_NIC,
    hours: float = 24.0,
) -> Dict[str, Any]:
    live = read_nic_counters(iface)
    delta_dropped, delta_errors, delta_missed = _nic_delta_in_window(conn, iface, hours)
    sample_count = conn.execute(
        """
        SELECT COUNT(*) FROM host_nic_samples
        WHERE iface = ? AND recorded_at > datetime('now', ?)
        """,
        (iface, f"-{hours} hours"),
    ).fetchone()[0]
    return {
        "iface": iface,
        "live_rx_dropped": live.get("rx_dropped"),
        "live_rx_errors": live.get("rx_errors"),
        "delta_rx_dropped_24h": delta_dropped,
        "delta_rx_errors_24h": delta_errors,
        "delta_rx_missed_24h": delta_missed,
        "samples_24h": int(sample_count or 0),
    }


def format_nic_daily_section(nic: Dict[str, Any]) -> str:
    iface = nic.get("iface", HOST_HEALTH_NIC)
    delta = nic.get("delta_rx_dropped_24h")
    total = nic.get("live_rx_dropped")
    samples = nic.get("samples_24h", 0)

    if delta is None and samples < 2:
        return (
            f"🔌 NIC {iface}: acumulado RX dropped {_format_int(total)} "
            f"(faltan muestras para delta 24h — se registran cada "
            f"{NIC_SAMPLE_INTERVAL_SEC // 3600}h)"
        )

    delta_s = _format_int(delta)
    total_s = _format_int(total)
    hint = ""
    if delta is not None:
        if delta == 0:
            hint = " — sin nuevos descartes en 24h"
        elif delta < 10_000:
            hint = " — bajo; normal bajo ráfaga ICMP"
        elif delta < 100_000:
            hint = " — moderado; revisar si coincide con blips"
        else:
            hint = " — alto; priorizar cable/puerto switch del servidor"

    return (
        f"🔌 NIC {iface} RX dropped: +{delta_s} en 24h "
        f"(acumulado {total_s}){hint}"
    )


def get_daily_health_summary(hours: float = 24.0) -> Dict[str, Any]:
    """Resumen blips + NIC para API y agente Telegram."""
    try:
        with get_db() as conn:
            ensure_host_health_tables(conn)
            blips = blip_stats_24h(conn)
            nic = nic_health_summary(conn, HOST_HEALTH_NIC, hours)
    except Exception as e:
        logger.warning("get_daily_health_summary: %s", e)
        return {"success": False, "error": str(e)}

    blip_text = format_blip_daily_section(blips)
    nic_text = format_nic_daily_section(nic)
    hotel_ok = blips.get("count_24h", 0) == 0

    return {
        "success": True,
        "blips": blips,
        "nic": nic,
        "hotel_visibility_ok": hotel_ok,
        "text_blips": blip_text,
        "text_nic": nic_text,
        "text_combined": f"{blip_text}\n{nic_text}",
    }
