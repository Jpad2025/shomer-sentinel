"""
Historial unificado de transiciones online/offline — Guardian + Inframonitor.

Tabla status_events + oleadas (incidentes) + retención configurable + causa confirmada.
No altera alertas Telegram ni lógica de ping/reboot.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_config, get_db, get_redis, set_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["network-status"])

_PRUNE_LAST_RUN: Optional[float] = None
_PRUNE_INTERVAL_SEC = 3600

DOWN_STATUSES = frozenset({"offline", "no-internet"})
CLUSTER_GAP_SEC = 3

DEFAULT_STATUS_RETENTION_DAYS = 90
DEFAULT_INFRA_EVENTS_RETENTION_DAYS = 90
DEFAULT_EVENT_LOG_RETENTION_DAYS = 30
DEFAULT_AGGRESSIVE_DISK_PCT = 85
MIN_RETENTION_DAYS = 7
MAX_RETENTION_DAYS = 365

# Informe Telegram post-oleada (adicional — no reemplaza alertas por AP del bot)
DEFAULT_OUTAGE_REPORT_ENABLED = True
DEFAULT_OUTAGE_REPORT_MIN_APS = 5
DEFAULT_OUTAGE_REPORT_MIN_DEVICES = 10
DEFAULT_OUTAGE_REPORT_REPEAT_HOURS = 24
DEFAULT_OUTAGE_REPORT_REPEAT_MIN = 2
DEFAULT_OUTAGE_REPORT_SETTLE_SEC = 90
OUTAGE_REPORT_LOOP_SEC = 60

FIELD_CHECKLIST: Dict[str, List[str]] = {
    "microcorte_red_admin": [
        "Switch core admin / uplink UniFi",
        "PoE en switches de piso afectados",
        "Cable fibra o patch entre switches",
    ],
    "wan_ok_interno": [
        "Switch admin — muchos equipos caen con internet OK",
        "PoE / alimentación de APs",
        "Controlador UniFi o VLAN admin",
    ],
    "wan_isp": [
        "Router WAN / MikroTik — enlace ISP",
        "Contactar proveedor de internet",
        "Verificar doble WAN si aplica",
    ],
    "sector_parcial": [
        "Switch o PoE del sector afectado",
        "VLAN o uplink del piso",
        "Revisar solo los APs que cayeron juntos",
    ],
    "fallo_electrico": [
        "UPS / breaker del rack o cuarto técnico",
        "PoE agotado tras corte eléctrico",
    ],
    "desconocido": [
        "Revisar logs en panel → Estado del sistema → Historial",
        "Confirmar causa en campo y registrar en el panel",
    ],
}

# Catálogo de causas (probable automática + confirmación manual)
CAUSE_CATALOG: Dict[str, str] = {
    "microcorte_red_admin": "Microcorte red admin — muchos equipos a la vez",
    "wan_ok_interno": "Red interna — WAN del Shomer OK",
    "wan_isp": "Caída internet (ISP / WAN)",
    "sector_parcial": "Caída parcial — switch, PoE o VLAN",
    "equipo_aislado": "Equipo aislado",
    "mantenimiento": "Mantenimiento programado",
    "fallo_electrico": "Fallo eléctrico (confirmado en campo)",
    "desconocido": "Sin clasificar",
    "otro": "Otro",
}


def _clamp_days(days: int) -> int:
    return max(MIN_RETENTION_DAYS, min(MAX_RETENTION_DAYS, int(days)))


def get_retention_config() -> Dict[str, Any]:
    status_d = _clamp_days(int(get_config("monitor.status_retention_days") or DEFAULT_STATUS_RETENTION_DAYS))
    infra_d = _clamp_days(int(get_config("monitor.infra_events_retention_days") or DEFAULT_INFRA_EVENTS_RETENTION_DAYS))
    log_d = _clamp_days(int(get_config("monitor.event_log_retention_days") or DEFAULT_EVENT_LOG_RETENTION_DAYS))
    disk_pct = int(get_config("monitor.aggressive_prune_disk_pct") or DEFAULT_AGGRESSIVE_DISK_PCT)
    return {
        "status_retention_days": status_d,
        "infra_events_retention_days": infra_d,
        "event_log_retention_days": log_d,
        "aggressive_prune_disk_pct": max(70, min(98, disk_pct)),
        **get_outage_report_config(),
    }


def get_outage_report_config() -> Dict[str, Any]:
    raw_enabled = get_config("monitor.outage_report_enabled")
    if raw_enabled is None:
        enabled = DEFAULT_OUTAGE_REPORT_ENABLED
    else:
        enabled = bool(raw_enabled) if not isinstance(raw_enabled, str) else raw_enabled.lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    return {
        "outage_report_enabled": enabled,
        "outage_report_min_aps": max(1, int(get_config("monitor.outage_report_min_aps") or DEFAULT_OUTAGE_REPORT_MIN_APS)),
        "outage_report_min_devices": max(
            1, int(get_config("monitor.outage_report_min_devices") or DEFAULT_OUTAGE_REPORT_MIN_DEVICES)
        ),
        "outage_report_repeat_hours": max(
            1, int(get_config("monitor.outage_report_repeat_hours") or DEFAULT_OUTAGE_REPORT_REPEAT_HOURS)
        ),
        "outage_report_repeat_min": max(
            2, int(get_config("monitor.outage_report_repeat_min") or DEFAULT_OUTAGE_REPORT_REPEAT_MIN)
        ),
        "outage_report_settle_sec": max(
            30, int(get_config("monitor.outage_report_settle_sec") or DEFAULT_OUTAGE_REPORT_SETTLE_SEC)
        ),
    }


def _disk_usage_pct() -> Optional[float]:
    try:
        import psutil
        return float(psutil.disk_usage("/").percent)
    except Exception:
        return None


def _effective_retention_days(configured: int) -> int:
    """Si disco root supera umbral, reduce retención a la mitad (mín. 7 días)."""
    pct = _disk_usage_pct()
    if pct is None:
        return configured
    cfg = get_retention_config()
    if pct >= cfg["aggressive_prune_disk_pct"]:
        reduced = max(MIN_RETENTION_DAYS, configured // 2)
        logger.warning(
            "Retención agresiva: disco %.0f%% — %d → %d días",
            pct, configured, reduced,
        )
        return reduced
    return configured


def _ensure_table() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL DEFAULT (datetime('now')),
                source TEXT NOT NULL,
                ip TEXT NOT NULL,
                name TEXT DEFAULT '',
                device_type TEXT DEFAULT 'generic',
                prev_status TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT DEFAULT '',
                latency_ms INTEGER,
                loss_pct REAL,
                batch_id TEXT DEFAULT '',
                wan_snapshot TEXT DEFAULT '',
                maintenance INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_status_events_ts ON status_events (ts);
            CREATE INDEX IF NOT EXISTS idx_status_events_ip_ts ON status_events (ip, ts);
            CREATE INDEX IF NOT EXISTS idx_status_events_batch ON status_events (batch_id);

            CREATE TABLE IF NOT EXISTS network_outage_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at_utc TEXT NOT NULL UNIQUE,
                probable_cause TEXT DEFAULT '',
                confirmed_cause TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                confirmed_by TEXT DEFAULT '',
                confirmed_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS outage_report_sent (
                started_at_utc TEXT NOT NULL,
                report_type TEXT NOT NULL,
                sent_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (started_at_utc, report_type)
            );
        """)
        for col, ddl in (
            ("wan_snapshot", "ALTER TABLE status_events ADD COLUMN wan_snapshot TEXT DEFAULT ''"),
            ("maintenance", "ALTER TABLE status_events ADD COLUMN maintenance INTEGER DEFAULT 0"),
        ):
            try:
                conn.execute(f"SELECT {col} FROM status_events LIMIT 1")
            except Exception:
                try:
                    conn.execute(ddl)
                except Exception:
                    pass
        conn.commit()


def run_data_retention_prune(*, force: bool = False) -> Dict[str, int]:
    """Poda status_events, infra_events, event_log y notas antiguas. Protege disco."""
    global _PRUNE_LAST_RUN
    now = time.time()
    if not force and _PRUNE_LAST_RUN and (now - _PRUNE_LAST_RUN) < _PRUNE_INTERVAL_SEC:
        return {}
    _PRUNE_LAST_RUN = now

    cfg = get_retention_config()
    status_days = _effective_retention_days(cfg["status_retention_days"])
    infra_days = _effective_retention_days(cfg["infra_events_retention_days"])
    log_days = _effective_retention_days(cfg["event_log_retention_days"])
    deleted: Dict[str, int] = {}

    try:
        _ensure_table()
        with get_db() as conn:
            for label, sql, days in (
                ("status_events", "DELETE FROM status_events WHERE ts < datetime('now', ?)", status_days),
                ("infra_events", "DELETE FROM infra_events WHERE ts < datetime('now', ?)", infra_days),
                ("event_log", "DELETE FROM event_log WHERE created_at < datetime('now', ?)", log_days),
                (
                    "network_outage_notes",
                    "DELETE FROM network_outage_notes WHERE started_at_utc < datetime('now', ?)",
                    status_days,
                ),
                (
                    "outage_report_sent",
                    "DELETE FROM outage_report_sent WHERE sent_at < datetime('now', ?)",
                    status_days,
                ),
            ):
                try:
                    cur = conn.execute(sql, (f"-{days} days",))
                    if cur.rowcount:
                        deleted[label] = cur.rowcount
                except Exception as e:
                    if "no such table" not in str(e).lower():
                        logger.debug("prune %s: %s", label, e)
            conn.commit()
        if deleted:
            logger.info("Poda monitor: %s", deleted)
    except Exception as e:
        logger.warning("run_data_retention_prune: %s", e)
    return deleted


def _prune_old_status_events() -> None:
    run_data_retention_prune()


def _parse_ts(raw: str) -> datetime:
    s = (raw or "")[:19]
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _bogota_str(utc_ts: str) -> str:
    if not utc_ts:
        return ""
    local = _parse_ts(utc_ts) - timedelta(hours=5)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _context_snapshots() -> Tuple[str, int]:
    wan = "unknown"
    maint = 0
    r = get_redis()
    if r:
        try:
            wan = r.get("shomer:wan_status") or "unknown"
            maint = 1 if r.get("shomer_maintenance") == "1" else 0
        except Exception:
            pass
    return wan, maint


def _gateway_ips() -> set:
    ips = set()
    fw = (get_config("hunter.firewall_ip") or "").strip()
    if fw:
        ips.add(fw)
    gw = (get_config("base.gateway") or "").strip()
    if gw:
        ips.add(gw)
    return ips


def record_status_event(
    *,
    source: str,
    ip: str,
    name: str,
    device_type: str,
    prev_status: str,
    status: str,
    reason: str = "",
    latency_ms: Optional[int] = None,
    loss_pct: Optional[float] = None,
    batch_id: str = "",
) -> None:
    """Inserta una transición si prev != status."""
    if prev_status == status:
        return
    wan_snap, maint = _context_snapshots()
    try:
        _ensure_table()
        with get_db() as conn:
            conn.execute(
                """INSERT INTO status_events
                   (source, ip, name, device_type, prev_status, status, reason,
                    latency_ms, loss_pct, batch_id, wan_snapshot, maintenance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source,
                    ip,
                    name or ip,
                    device_type or "generic",
                    prev_status or "unknown",
                    status,
                    reason or "",
                    latency_ms,
                    loss_pct,
                    batch_id or "",
                    wan_snap,
                    maint,
                ),
            )
            conn.commit()
    except Exception as e:
        logger.debug("record_status_event %s: %s", ip, e)


def _has_router_in_cluster(cluster: List[Dict[str, Any]]) -> bool:
    gw_ips = _gateway_ips()
    return any(
        e["ip"] in gw_ips
        or (e.get("device_type") or "") in ("router", "gateway")
        for e in cluster
    )


def _wan_majority_down(cluster: List[Dict[str, Any]]) -> bool:
    snaps = [e.get("wan_snapshot") for e in cluster if e.get("wan_snapshot")]
    if not snaps:
        return False
    down = sum(1 for s in snaps if s == "down")
    return down > len(snaps) / 2


def _maintenance_active(cluster: List[Dict[str, Any]]) -> bool:
    return any(int(e.get("maintenance") or 0) for e in cluster)


def _classify_outage(ips: List[str], cluster: List[Dict[str, Any]]) -> tuple[str, str]:
    if _maintenance_active(cluster):
        return ("mantenimiento", CAUSE_CATALOG["mantenimiento"])

    ap_count = sum(1 for e in cluster if (e.get("device_type") or "") in ("access_point", "ap"))
    has_router = _has_router_in_cluster(cluster)
    total = len(ips)
    wan_down = _wan_majority_down(cluster)
    mass = total >= 10 or (ap_count >= 5 and has_router)

    if mass and wan_down:
        return ("wan_isp", CAUSE_CATALOG["wan_isp"])
    if mass and not wan_down:
        return ("wan_ok_interno", CAUSE_CATALOG["wan_ok_interno"])
    if mass:
        return ("microcorte_red_admin", CAUSE_CATALOG["microcorte_red_admin"])
    if total == 1:
        sample = cluster[0]
        r = sample.get("reason") or "revisar cable, PoE o alimentación"
        return ("equipo_aislado", f"{CAUSE_CATALOG['equipo_aislado']} — {r}")
    if wan_down and total >= 3:
        return ("wan_isp", CAUSE_CATALOG["wan_isp"])
    return ("sector_parcial", CAUSE_CATALOG["sector_parcial"])


def _load_outage_notes() -> Dict[str, Dict[str, Any]]:
    _ensure_table()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT started_at_utc, probable_cause, confirmed_cause, notes, confirmed_by, confirmed_at "
            "FROM network_outage_notes"
        ).fetchall()
    return {r["started_at_utc"]: dict(r) for r in rows}


def compute_outages(hours: int = 48) -> List[Dict[str, Any]]:
    """Agrupa transiciones a offline/no-internet en oleadas."""
    _ensure_table()
    run_data_retention_prune()

    with get_db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """SELECT ts, source, ip, name, device_type, prev_status, status,
                          reason, latency_ms, batch_id, wan_snapshot, maintenance
                   FROM status_events
                   WHERE ts >= datetime('now', ?)
                   ORDER BY ts ASC""",
                (f"-{hours} hours",),
            ).fetchall()
        ]

    notes_map = _load_outage_notes()

    if not rows:
        return []

    down_rows = [r for r in rows if r["status"] in DOWN_STATUSES]
    outages: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    cluster_start: Optional[datetime] = None

    def _flush(cluster: List[Dict[str, Any]]) -> None:
        if not cluster:
            return
        ips = sorted({e["ip"] for e in cluster})
        started = cluster[0]["ts"]
        started_dt = _parse_ts(started)
        online_after = [
            r
            for r in rows
            if r["status"] == "online"
            and r["ip"] in ips
            and _parse_ts(r["ts"]) >= started_dt
        ]
        ended = max((r["ts"] for r in online_after), default=None)
        duration_sec: Optional[int] = None
        if ended:
            duration_sec = int((_parse_ts(ended) - started_dt).total_seconds())

        cause, cause_label = _classify_outage(ips, cluster)
        note = notes_map.get(started, {})
        confirmed = note.get("confirmed_cause") or ""
        display_cause = confirmed if confirmed else cause
        display_label = CAUSE_CATALOG.get(confirmed, cause_label) if confirmed else cause_label

        outages.append(
            {
                "started_at_utc": started,
                "started_at_bogota": _bogota_str(started),
                "ended_at_utc": ended,
                "ended_at_bogota": _bogota_str(ended) if ended else None,
                "duration_sec": duration_sec,
                "devices_count": len(ips),
                "ap_count": sum(
                    1 for e in cluster if (e.get("device_type") or "") in ("access_point", "ap")
                ),
                "has_router": _has_router_in_cluster(cluster),
                "wan_down_at_event": _wan_majority_down(cluster),
                "probable_cause": cause,
                "probable_cause_label": cause_label,
                "confirmed_cause": confirmed,
                "confirmed_cause_label": display_label if confirmed else "",
                "display_cause": display_cause,
                "display_cause_label": display_label,
                "notes": note.get("notes") or "",
                "confirmed_by": note.get("confirmed_by") or "",
                "confirmed_at": note.get("confirmed_at") or "",
                "sample_ips": ips[:10],
                "sample_names": list({e.get("name") or e["ip"] for e in cluster})[:6],
                "sources": sorted({e["source"] for e in cluster}),
            }
        )

    for ev in down_rows:
        ts = _parse_ts(ev["ts"])
        if not current:
            current = [ev]
            cluster_start = ts
        elif cluster_start and (ts - cluster_start).total_seconds() <= CLUSTER_GAP_SEC:
            current.append(ev)
        else:
            _flush(current)
            current = [ev]
            cluster_start = ts
    _flush(current)

    outages.sort(key=lambda x: x["started_at_utc"], reverse=True)
    return outages


def _site_display_name() -> str:
    return (
        (get_config("base.site_name") or get_config("base.hostname") or "Shomer Sentinel").strip()
        or "Shomer Sentinel"
    )


def _format_duration_sec(sec: Optional[int]) -> str:
    if sec is None:
        return "desconocida"
    if sec < 60:
        return f"{sec} s"
    minutes, seconds = divmod(sec, 60)
    if minutes < 60:
        return f"{minutes} min {seconds} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def _outage_qualifies_for_report(outage: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    if outage.get("probable_cause") == "mantenimiento":
        return False
    if int(outage.get("ap_count") or 0) >= cfg["outage_report_min_aps"]:
        return True
    if int(outage.get("devices_count") or 0) >= cfg["outage_report_min_devices"]:
        return True
    return False


def _recovery_settled(outage: Dict[str, Any], settle_sec: int) -> bool:
    ended = outage.get("ended_at_utc")
    if not ended:
        return False
    elapsed = (datetime.now(timezone.utc) - _parse_ts(ended)).total_seconds()
    return elapsed >= settle_sec


def _report_already_sent(key: str, report_type: str) -> bool:
    _ensure_table()
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM outage_report_sent WHERE started_at_utc=? AND report_type=?",
            (key, report_type),
        ).fetchone()
    return row is not None


def _mark_report_sent(key: str, report_type: str) -> None:
    _ensure_table()
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO outage_report_sent (started_at_utc, report_type)
               VALUES (?, ?)""",
            (key, report_type),
        )
        conn.commit()


def format_outage_summary_message(outage: Dict[str, Any], site_name: str) -> str:
    """Resumen post-oleada — complementa (no sustituye) alertas individuales por AP."""
    cause = outage.get("display_cause") or outage.get("probable_cause") or "desconocido"
    label = outage.get("display_cause_label") or outage.get("probable_cause_label") or CAUSE_CATALOG.get(
        cause, cause
    )
    checklist = FIELD_CHECKLIST.get(cause) or FIELD_CHECKLIST.get("desconocido", [])
    checks = "\n".join(f"• {line}" for line in checklist[:4])
    names = ", ".join(outage.get("sample_names") or [])[:180]
    wan_note = "Internet del Shomer: OK" if not outage.get("wan_down_at_event") else "Internet del Shomer: posible caída WAN"
    recovered = "✅ Todos recuperados" if outage.get("ended_at_utc") else "⏳ Aún en curso"
    names_block = f"<i>Ej.: {names}</i>\n\n" if names else ""

    return (
        f"📋 <b>SALUD DE NODOS</b> {site_name}\n"
        f"<b>Resumen post-oleada</b> (informe automático)\n\n"
        f"🕐 {outage.get('started_at_bogota')} (Bogotá)\n"
        f"⏱ Duración: {_format_duration_sec(outage.get('duration_sec'))}\n"
        f"📡 {outage.get('ap_count', 0)} APs · {outage.get('devices_count', 0)} equipos\n"
        f"{recovered}\n"
        f"{wan_note}\n\n"
        f"<b>Causa probable:</b> {label}\n"
        f"{names_block}"
        f"<b>Revisar en sitio:</b>\n{checks}\n\n"
        f"ℹ️ Las alertas <b>por AP</b> que recibiste son normales — ayudan a reaccionar rápido. "
        f"Este mensaje es un <b>resumen adicional</b> cuando caen varios a la vez."
    )


def format_outage_repeat_message(
    cause: str,
    outages: List[Dict[str, Any]],
    site_name: str,
    window_hours: int,
) -> str:
    label = CAUSE_CATALOG.get(cause, cause)
    times = "\n".join(
        f"• {o.get('started_at_bogota')} — {o.get('ap_count', 0)} APs, "
        f"{_format_duration_sec(o.get('duration_sec'))}"
        for o in sorted(outages, key=lambda x: x["started_at_utc"], reverse=True)[:5]
    )
    checklist = FIELD_CHECKLIST.get(cause) or FIELD_CHECKLIST.get("desconocido", [])
    checks = "\n".join(f"• {line}" for line in checklist[:3])
    return (
        f"⚠️ <b>SALUD DE NODOS</b> {site_name}\n"
        f"<b>Patrón repetido</b> — misma causa {len(outages)} veces en {window_hours} h\n\n"
        f"<b>Causa:</b> {label}\n\n"
        f"{times}\n\n"
        f"<b>Acción recomendada:</b>\n{checks}\n\n"
        f"Las alertas individuales por AP siguen activas. Este aviso es para que "
        f"escales a infraestructura física (switch/PoE/uplink)."
    )


def process_outage_telegram_reports() -> int:
    """
    Nivel 1: resumen tras oleada grande recuperada.
    Nivel 2: aviso si la misma causa se repite N veces en 24 h.
    No altera watch_guardian_nodes ni alertas por AP.
    """
    cfg = get_outage_report_config()
    if not cfg["outage_report_enabled"]:
        return 0

    r = get_redis()
    if r:
        try:
            if r.get("shomer_maintenance") == "1":
                return 0
        except Exception:
            pass

    try:
        from app.api.shomer_guardian_lib import send_telegram_safe
    except Exception:
        return 0

    site = _site_display_name()
    window = cfg["outage_report_repeat_hours"]
    outages = compute_outages(hours=max(window + 2, 6))
    sent = 0

    for outage in outages:
        if not _outage_qualifies_for_report(outage, cfg):
            continue
        if not _recovery_settled(outage, cfg["outage_report_settle_sec"]):
            continue
        key = outage["started_at_utc"]
        if _report_already_sent(key, "summary"):
            continue
        send_telegram_safe(format_outage_summary_message(outage, site))
        _mark_report_sent(key, "summary")
        sent += 1
        logger.info(
            "Informe post-oleada enviado: %s APs, %s equipos, causa=%s",
            outage.get("ap_count"),
            outage.get("devices_count"),
            outage.get("probable_cause"),
        )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window)
    by_cause: Dict[str, List[Dict[str, Any]]] = {}
    for outage in outages:
        if not _outage_qualifies_for_report(outage, cfg):
            continue
        cause = outage.get("probable_cause") or "desconocido"
        if cause in ("mantenimiento", "equipo_aislado"):
            continue
        if not outage.get("ended_at_utc"):
            continue
        if _parse_ts(outage["started_at_utc"]) < cutoff:
            continue
        by_cause.setdefault(cause, []).append(outage)

    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for cause, items in by_cause.items():
        if len(items) < cfg["outage_report_repeat_min"]:
            continue
        repeat_key = f"repeat:{cause}:{bucket}"
        if _report_already_sent(repeat_key, "repeat"):
            continue
        send_telegram_safe(
            format_outage_repeat_message(cause, items, site, window)
        )
        _mark_report_sent(repeat_key, "repeat")
        sent += 1
        logger.info("Aviso patrón repetido enviado: causa=%s, count=%d", cause, len(items))

    return sent


class OutageConfirmBody(BaseModel):
    started_at_utc: str = Field(..., min_length=10)
    confirmed_cause: str = Field(..., min_length=1)
    notes: str = ""


class RetentionBody(BaseModel):
    status_retention_days: int = Field(DEFAULT_STATUS_RETENTION_DAYS, ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS)
    infra_events_retention_days: int = Field(DEFAULT_INFRA_EVENTS_RETENTION_DAYS, ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS)
    event_log_retention_days: int = Field(DEFAULT_EVENT_LOG_RETENTION_DAYS, ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS)
    aggressive_prune_disk_pct: int = Field(DEFAULT_AGGRESSIVE_DISK_PCT, ge=70, le=98)
    outage_report_enabled: Optional[bool] = None
    outage_report_min_aps: Optional[int] = Field(None, ge=1, le=100)
    outage_report_min_devices: Optional[int] = Field(None, ge=1, le=500)
    outage_report_repeat_hours: Optional[int] = Field(None, ge=1, le=168)
    outage_report_repeat_min: Optional[int] = Field(None, ge=2, le=20)
    outage_report_settle_sec: Optional[int] = Field(None, ge=30, le=600)


_retention_task: Optional[asyncio.Task] = None
_outage_report_task: Optional[asyncio.Task] = None


async def retention_prune_loop() -> None:
    """Poda horaria en background — evita crecimiento ilimitado de BD."""
    await asyncio.sleep(120)
    while True:
        try:
            await asyncio.to_thread(run_data_retention_prune, force=True)
        except Exception as e:
            logger.debug("retention_prune_loop: %s", e)
        await asyncio.sleep(_PRUNE_INTERVAL_SEC)


def start_retention_prune_loop() -> None:
    global _retention_task
    try:
        loop = asyncio.get_event_loop()
        if _retention_task is None or _retention_task.done():
            _retention_task = loop.create_task(retention_prune_loop())
    except Exception as e:
        logger.warning("start_retention_prune_loop: %s", e)


async def outage_report_loop() -> None:
    """Revisa oleadas recuperadas y envía resumen Telegram (solo worker líder)."""
    await asyncio.sleep(45)
    while True:
        try:
            await asyncio.to_thread(process_outage_telegram_reports)
        except Exception as e:
            logger.debug("outage_report_loop: %s", e)
        await asyncio.sleep(OUTAGE_REPORT_LOOP_SEC)


def start_outage_report_loop() -> None:
    global _outage_report_task
    try:
        loop = asyncio.get_event_loop()
        if _outage_report_task is None or _outage_report_task.done():
            _outage_report_task = loop.create_task(outage_report_loop())
    except Exception as e:
        logger.warning("start_outage_report_loop: %s", e)


@router.get("/api/network/retention")
async def api_get_retention(user=Depends(get_current_user)):
    cfg = get_retention_config()
    disk = _disk_usage_pct()
    return {
        "success": True,
        **cfg,
        "disk_usage_pct": disk,
        "cause_catalog": CAUSE_CATALOG,
        "defaults": {
            "status_retention_days": DEFAULT_STATUS_RETENTION_DAYS,
            "infra_events_retention_days": DEFAULT_INFRA_EVENTS_RETENTION_DAYS,
            "event_log_retention_days": DEFAULT_EVENT_LOG_RETENTION_DAYS,
        },
    }


@router.post("/api/network/retention")
async def api_save_retention(body: RetentionBody, user=Depends(get_current_user)):
    """Técnico y admin pueden ajustar retención — evita llenar disco en campo."""
    set_config("monitor.status_retention_days", body.status_retention_days)
    set_config("monitor.infra_events_retention_days", body.infra_events_retention_days)
    set_config("monitor.event_log_retention_days", body.event_log_retention_days)
    set_config("monitor.aggressive_prune_disk_pct", body.aggressive_prune_disk_pct)
    if body.outage_report_enabled is not None:
        set_config("monitor.outage_report_enabled", body.outage_report_enabled)
    if body.outage_report_min_aps is not None:
        set_config("monitor.outage_report_min_aps", body.outage_report_min_aps)
    if body.outage_report_min_devices is not None:
        set_config("monitor.outage_report_min_devices", body.outage_report_min_devices)
    if body.outage_report_repeat_hours is not None:
        set_config("monitor.outage_report_repeat_hours", body.outage_report_repeat_hours)
    if body.outage_report_repeat_min is not None:
        set_config("monitor.outage_report_repeat_min", body.outage_report_repeat_min)
    if body.outage_report_settle_sec is not None:
        set_config("monitor.outage_report_settle_sec", body.outage_report_settle_sec)
    try:
        deleted = run_data_retention_prune(force=True)
    except Exception as e:
        logger.warning("retention save prune: %s", e)
        deleted = {}
    return {"success": True, "config": get_retention_config(), "pruned": deleted}


@router.post("/api/network/outages/confirm")
async def api_confirm_outage(body: OutageConfirmBody, user=Depends(get_current_user)):
    cause = body.confirmed_cause.strip()
    if cause not in CAUSE_CATALOG:
        raise HTTPException(status_code=400, detail="Causa no válida")
    _ensure_table()
    username = ""
    if isinstance(user, dict):
        username = user.get("username") or user.get("sub") or ""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO network_outage_notes
               (started_at_utc, confirmed_cause, notes, confirmed_by, confirmed_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(started_at_utc) DO UPDATE SET
                 confirmed_cause=excluded.confirmed_cause,
                 notes=excluded.notes,
                 confirmed_by=excluded.confirmed_by,
                 confirmed_at=excluded.confirmed_at""",
            (body.started_at_utc[:19], cause, body.notes or "", username, now),
        )
        conn.commit()
    return {"success": True}


@router.get("/api/network/outages")
async def api_network_outages(
    hours: int = Query(48, ge=1, le=720),
    user=Depends(get_current_user),
):
    items = compute_outages(hours=hours)
    return {"success": True, "hours": hours, "count": len(items), "outages": items}


@router.get("/api/network/status-events")
async def api_status_events(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(200, ge=1, le=2000),
    ip: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    _ensure_table()
    run_data_retention_prune()
    sql = """SELECT id, ts, source, ip, name, device_type, prev_status, status,
                    reason, latency_ms, loss_pct, batch_id, wan_snapshot, maintenance
             FROM status_events
             WHERE ts >= datetime('now', ?)"""
    params: List[Any] = [f"-{hours} hours"]
    if ip:
        sql += " AND ip = ?"
        params.append(ip.strip())
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    for r in rows:
        r["ts_bogota"] = _bogota_str(r.get("ts") or "")
    return {"success": True, "events": rows, "count": len(rows)}


@router.get("/api/network/outages/export")
async def api_outages_export(
    hours: int = Query(168, ge=1, le=720),
    user=Depends(get_current_user),
):
    items = compute_outages(hours=hours)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "inicio_bogota",
            "fin_bogota",
            "duracion_seg",
            "equipos",
            "aps",
            "causa_probable",
            "causa_confirmada",
            "detalle",
            "notas",
            "ips_muestra",
        ]
    )
    for o in items:
        w.writerow(
            [
                o.get("started_at_bogota"),
                o.get("ended_at_bogota") or "",
                o.get("duration_sec") or "",
                o.get("devices_count"),
                o.get("ap_count"),
                o.get("probable_cause"),
                o.get("confirmed_cause") or "",
                o.get("display_cause_label"),
                o.get("notes") or "",
                ";".join(o.get("sample_ips") or []),
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=shomer_outages.csv"},
    )
