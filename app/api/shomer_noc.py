"""
NOC Display — Dashboard TV tiempo real.
Lee Guardian (infra_nodes + devices) + Inframonitor (infra_devices + infra_status).
Token simple en URL, sin login. No expone IPs ni credenciales.

Zona operativa (estilo Zabbix ligero):
  - Problemas activos (offline / degraded / Pulse / Hunter open)
  - ACK por problema (noc_problem_acks)
  - Historial corto de caídas (infra_events)
"""
import json
import logging
import re
import secrets
import socket
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.api.auth_api import require_admin
from app.api.shomer_common import get_config, get_db, set_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["noc"])

import os as _os
_TEMPLATES_DIR = _os.path.join(_os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

SEVERITY_LABEL = {1: "CRÍTICO", 2: "ALTO", 3: "MEDIO", 4: "BAJO", 5: "INFO"}
SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "WARNING": 2, "INFO": 3}


class NocAckBody(BaseModel):
    problem_id: str = Field(..., min_length=2, max_length=120)
    by: str = Field("noc", max_length=80)


# ──────────────────────────────────────────────
# Token helpers
# ──────────────────────────────────────────────

def _get_or_create_token() -> str:
    token = get_config("noc.display_token")
    if not token:
        token = secrets.token_urlsafe(24)
        set_config("noc.display_token", token)
    return token


def _validate_token(token: str | None) -> None:
    if not token:
        raise HTTPException(status_code=403, detail="Token requerido")
    stored = get_config("noc.display_token")
    if not stored or token != stored:
        raise HTTPException(status_code=403, detail="Token NOC inválido")


# ──────────────────────────────────────────────
# Data aggregation
# ──────────────────────────────────────────────

def _guardian_nodes() -> list:
    try:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT n.ip_address, n.status, n.latency_ms, n.last_heartbeat,
                          d.name, d.device_type, d.location
                   FROM infra_nodes n
                   LEFT JOIN devices d ON d.ip_address = n.ip_address
                   ORDER BY n.status, d.name"""
            ).fetchall()
        result = []
        for r in rows:
            result.append({
                "ip_hidden": True,
                "name": r["name"] or r["ip_address"],
                "device_type": r["device_type"] or "access_point",
                "location": r["location"] or "",
                "status": r["status"] or "unknown",
                "latency_ms": r["latency_ms"],
                "last_seen": r["last_heartbeat"],
                "source": "guardian",
            })
        return result
    except Exception as e:
        logger.error("noc guardian_nodes: %s", e)
        return []


def _infra_devices() -> tuple:
    """Returns (devices list, outages_24h count)."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT d.ip, d.name, d.device_type, d.location,
                          s.status, s.latency_ms, s.checked_at, s.snmp_ok, s.snmp_data
                   FROM infra_devices d
                   LEFT JOIN infra_status s ON s.ip = d.ip
                   WHERE d.active = 1
                   ORDER BY CASE WHEN s.status='offline' THEN 0 ELSE 1 END, d.name"""
            ).fetchall()

            outages = conn.execute(
                """SELECT COUNT(DISTINCT ip) FROM infra_status
                   WHERE status='offline' AND checked_at > datetime('now', '-24 hours')"""
            ).fetchone()[0]

        result = []
        for r in rows:
            snmp_info = {}
            if r["snmp_data"]:
                try:
                    sd = json.loads(r["snmp_data"])
                    ifaces = sd.get("interfaces", [])
                    ports_up    = sum(1 for i in ifaces if i.get("oper", "").lower() == "up")
                    ports_total = len(ifaces)
                    ports_errors = sum(
                        (i.get("in_errors") or 0) + (i.get("out_errors") or 0)
                        for i in ifaces
                    )
                    snmp_info = {
                        "model": (sd.get("model") or sd.get("sys_descr") or "")[:40],
                        "uptime": sd.get("uptime") or sd.get("sys_uptime") or "",
                        "hostname": sd.get("hostname") or sd.get("sys_name") or "",
                        "ports_up": ports_up,
                        "ports_total": ports_total,
                        "ports_errors": ports_errors,
                        "printer": sd.get("printer"),  # {status, toner_pct, paper_current, paper_max}
                    }
                except Exception:
                    pass
            result.append({
                "ip_hidden": True,
                "name": r["name"],
                "device_type": r["device_type"] or "generic",
                "location": r["location"] or "",
                "status": r["status"] or "unknown",
                "latency_ms": r["latency_ms"],
                "last_seen": r["checked_at"],
                "source": "inframonitor",
                "snmp_ok": r["snmp_ok"],
                "snmp": snmp_info,
            })
        return result, outages
    except Exception as e:
        logger.error("noc infra_devices: %s", e)
        return [], 0


def _wan_status() -> dict:
    # 1. Redis (escrito por Guardian cuando hace WAN check)
    try:
        import redis as _redis
        _r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=1)
        wan = _r.get("shomer:wan_status") or _r.get("wan_status")
        if wan:
            ok = wan.lower() in ("online", "up", "ok")
            return {"ok": ok, "status": "online" if ok else "offline", "latency_ms": None}
    except Exception:
        pass
    # 2. Fallback: TCP a DNS de Google
    try:
        import socket as _socket, time as _time
        t0 = _time.monotonic()
        s  = _socket.create_connection(("8.8.8.8", 53), timeout=3)
        s.close()
        latency = round((_time.monotonic() - t0) * 1000, 1)
        return {"ok": True, "status": "online", "latency_ms": latency}
    except Exception:
        pass
    # 3. Fallback: curl (ignora routing por interfaz)
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "4", "-o", "/dev/null", "-w", "%{time_total}", "http://api.ipify.org"],
            capture_output=True, text=True, timeout=6,
        )
        if r.returncode == 0 and r.stdout.strip():
            latency = round(float(r.stdout.strip()) * 1000, 1)
            return {"ok": True, "status": "online", "latency_ms": latency}
    except Exception:
        pass
    return {"ok": False, "status": "offline", "latency_ms": None}


def _hunter_stats() -> dict:
    try:
        with get_db() as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM blocked_ips WHERE unblocked_at IS NULL"
            ).fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM blocked_ips WHERE blocked_at >= datetime('now','-1 day')"
            ).fetchone()[0]
            last = conn.execute(
                "SELECT alert_signature, severity, blocked_at FROM blocked_ips ORDER BY blocked_at DESC LIMIT 1"
            ).fetchone()
        return {
            "active_blocks": active,
            "blocks_24h": today,
            "last_alert": {
                "signature": last["alert_signature"] if last else None,
                "severity": SEVERITY_LABEL.get(last["severity"], "?") if last else None,
                "blocked_at": last["blocked_at"] if last else None,
            },
        }
    except Exception as e:
        logger.error("noc hunter_stats: %s", e)
        return {"active_blocks": 0, "blocks_24h": 0, "last_alert": {}}


def _risk_findings() -> dict:
    try:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT severity, COUNT(*) as cnt
                   FROM network_audit_findings
                   WHERE finding_status != 'terminado'
                   GROUP BY severity"""
            ).fetchall()
        counts = {"critico": 0, "alto": 0, "medio": 0, "bajo": 0}
        for r in rows:
            if r["severity"] in counts:
                counts[r["severity"]] = r["cnt"]
        total = sum(counts.values())
        # Overall color: worst active severity
        if counts["critico"] > 0:
            level = "critico"
        elif counts["alto"] > 0:
            level = "alto"
        elif counts["medio"] > 0:
            level = "medio"
        elif counts["bajo"] > 0:
            level = "bajo"
        else:
            level = "ok"
        return {"counts": counts, "total": total, "level": level}
    except Exception as e:
        logger.error("noc risk_findings: %s", e)
        return {"counts": {"critico": 0, "alto": 0, "medio": 0, "bajo": 0}, "total": 0, "level": "ok"}


def _server_resources() -> dict:
    try:
        # interval=None: lectura instantánea vs. la última muestra, sin bloquear
        # el event loop. Como este endpoint se sondea cada 30s, el delta entre
        # llamadas ya es representativo — no hace falta el sleep de 0.5s.
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        disks = []
        for path, label in [("/", "OS"), ("/srv", "Backups"), ("/var", "Logs")]:
            try:
                u = psutil.disk_usage(path)
                disks.append({"label": label, "percent": u.percent, "free_gb": round(u.free / 1e9, 1)})
            except Exception:
                pass
        return {
            "cpu_percent": round(cpu, 1),
            "ram_percent": round(vm.percent, 1),
            "ram_used_gb": round(vm.used / 1e9, 1),
            "ram_total_gb": round(vm.total / 1e9, 1),
            "disks": disks,
        }
    except Exception as e:
        logger.error("noc server_resources: %s", e)
        return {"cpu_percent": 0, "ram_percent": 0, "disks": []}


def _services_status() -> list:
    services = [
        ("shomer-guardian", "Guardian"),
        ("shomer-tools", "Tools"),
        ("nginx", "Nginx"),
        ("redis-server", "Redis"),
        ("suricata", "Suricata"),
    ]
    result = []
    for svc, label in services:
        try:
            ret = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True, timeout=3
            )
            active = ret.stdout.strip() == "active"
        except Exception:
            active = False
        result.append({"name": label, "active": active})
    return result


def _recent_events(limit: int = 5) -> list:
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT event_type, details, created_at FROM event_log ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"type": r["event_type"], "details": r["details"], "at": r["created_at"]} for r in rows]
    except Exception:
        return []


def _ensure_noc_ack_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS noc_problem_acks (
            problem_id TEXT PRIMARY KEY,
            acked_at TEXT NOT NULL,
            acked_by TEXT DEFAULT 'noc'
        )
        """
    )


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    raw = str(ts).strip()
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if "+" in raw[10:] or raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        # SQLite datetime('now') → UTC naive
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _age_seconds(ts: Optional[str]) -> int:
    dt = _parse_ts(ts)
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))


def _fmt_duration(sec: int) -> str:
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 86400:
        h, m = divmod(sec // 60, 60)
        return f"{h}h {m}m" if m else f"{h}h"
    d, rem = divmod(sec, 86400)
    h = rem // 3600
    return f"{d}d {h}h" if h else f"{d}d"


def _offline_since(conn, ip: str, fallback_ts: Optional[str]) -> str:
    """Inicio estimado del offline: status_events / infra_events, no last_heartbeat."""
    # 1) Última transición → offline en status_events (Guardian + Infra)
    try:
        row = conn.execute(
            """
            SELECT ts FROM status_events
            WHERE ip = ? AND status = 'offline'
            ORDER BY ts DESC LIMIT 1
            """,
            (ip,),
        ).fetchone()
        if row and row["ts"]:
            later = conn.execute(
                """
                SELECT 1 FROM status_events
                WHERE ip = ? AND status = 'online' AND ts > ?
                LIMIT 1
                """,
                (ip, row["ts"]),
            ).fetchone()
            if not later:
                return row["ts"]
    except Exception:
        pass
    # 2) infra_events (poller Inframonitor)
    try:
        row = conn.execute(
            """
            SELECT ts FROM infra_events
            WHERE ip = ? AND event = 'offline'
            ORDER BY ts DESC LIMIT 1
            """,
            (ip,),
        ).fetchone()
        if row and row["ts"]:
            later = conn.execute(
                """
                SELECT 1 FROM infra_events
                WHERE ip = ? AND event = 'online' AND ts > ?
                LIMIT 1
                """,
                (ip, row["ts"]),
            ).fetchone()
            if not later:
                return row["ts"]
    except Exception:
        pass
    # 3) fallback: NO usar last_heartbeat (sigue actualizándose en offline)
    return fallback_ts or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _load_acks(conn) -> Dict[str, dict]:
    _ensure_noc_ack_table(conn)
    rows = conn.execute(
        "SELECT problem_id, acked_at, acked_by FROM noc_problem_acks"
    ).fetchall()
    return {r["problem_id"]: dict(r) for r in rows}


def _active_problems() -> List[Dict[str, Any]]:
    """Problemas abiertos para el NOC: offline, degraded, Pulse, Hunter."""
    problems: List[Dict[str, Any]] = []
    try:
        with get_db() as conn:
            acks = _load_acks(conn)
            name_by_ip: Dict[str, str] = {}

            # Guardian APs
            try:
                grows = conn.execute(
                    """
                    SELECT n.ip_address, n.status, n.last_heartbeat,
                           COALESCE(d.name, n.ip_address) AS name
                    FROM infra_nodes n
                    LEFT JOIN devices d ON d.ip_address = n.ip_address
                    WHERE n.status IN ('offline', 'unknown', 'no-internet')
                    """
                ).fetchall()
                for r in grows:
                    ip = r["ip_address"]
                    name_by_ip[ip] = r["name"]
                    pid = f"g:{ip}"
                    # No usar last_heartbeat como inicio (sigue escribiéndose en offline)
                    since = _offline_since(conn, ip, None)
                    age = _age_seconds(since)
                    ack = acks.get(pid)
                    sev = "CRITICAL" if r["status"] == "offline" else "WARNING"
                    problems.append({
                        "id": pid,
                        "name": r["name"],
                        "kind": "ap",
                        "source": "guardian",
                        "severity": sev,
                        "status": r["status"],
                        "message": "Access Point sin respuesta" if r["status"] == "offline"
                                   else f"AP estado {r['status']}",
                        "since": since,
                        "time_active_sec": age,
                        "time_active": _fmt_duration(age),
                        "acknowledged": bool(ack),
                        "acked_at": ack["acked_at"] if ack else None,
                        "acked_by": ack["acked_by"] if ack else None,
                        "fresh": age < 600 and not ack,
                    })
            except Exception as e:
                logger.debug("noc problems guardian: %s", e)

            # Inframonitor
            try:
                irows = conn.execute(
                    """
                    SELECT d.ip, d.name, d.device_type, s.status, s.checked_at
                    FROM infra_devices d
                    JOIN infra_status s ON s.ip = d.ip
                    WHERE d.active = 1
                      AND s.status IN ('offline', 'degraded', 'unknown')
                    """
                ).fetchall()
                for r in irows:
                    ip = r["ip"]
                    # Evitar duplicar APs ya listados por Guardian
                    if r["device_type"] == "ap" and f"g:{ip}" in {p["id"] for p in problems}:
                        continue
                    name_by_ip[ip] = r["name"]
                    pid = f"i:{ip}"
                    since = _offline_since(conn, ip, r["checked_at"])
                    age = _age_seconds(since)
                    ack = acks.get(pid)
                    if r["status"] == "offline":
                        sev, msg = "CRITICAL", "Equipo sin respuesta"
                    elif r["status"] == "degraded":
                        sev, msg = "WARNING", "Equipo degradado (pérdida/latencia)"
                    else:
                        sev, msg = "WARNING", "Sin datos de monitoreo"
                    problems.append({
                        "id": pid,
                        "name": r["name"],
                        "kind": r["device_type"] or "generic",
                        "source": "inframonitor",
                        "severity": sev,
                        "status": r["status"],
                        "message": msg,
                        "since": since,
                        "time_active_sec": age,
                        "time_active": _fmt_duration(age),
                        "acknowledged": bool(ack),
                        "acked_at": ack["acked_at"] if ack else None,
                        "acked_by": ack["acked_by"] if ack else None,
                        "fresh": age < 600 and not ack,
                    })
            except Exception as e:
                logger.debug("noc problems infra: %s", e)

            # Pulse EWMA — degradando (aún online)
            try:
                prows = conn.execute(
                    """
                    SELECT p.ip, p.pulse_state, p.degrade_ticks, p.ewma_latency_ms,
                           p.updated_at, d.name, d.device_type, s.status
                    FROM infra_pulse p
                    JOIN infra_devices d ON d.ip = p.ip AND d.active = 1
                    LEFT JOIN infra_status s ON s.ip = p.ip
                    WHERE p.pulse_state = 'degrading'
                      AND COALESCE(s.status, 'online') = 'online'
                    """
                ).fetchall()
                for r in prows:
                    ip = r["ip"]
                    pid = f"p:{ip}"
                    age = _age_seconds(r["updated_at"])
                    ack = acks.get(pid)
                    lat = r["ewma_latency_ms"]
                    lat_s = f"{lat:.0f} ms" if lat is not None else "—"
                    problems.append({
                        "id": pid,
                        "name": r["name"] or ip,
                        "kind": r["device_type"] or "generic",
                        "source": "pulse",
                        "severity": "WARNING",
                        "status": "degrading",
                        "message": f"Pulse: empeorando (latencia ~{lat_s})",
                        "since": r["updated_at"],
                        "time_active_sec": age,
                        "time_active": _fmt_duration(age),
                        "acknowledged": bool(ack),
                        "acked_at": ack["acked_at"] if ack else None,
                        "acked_by": ack["acked_by"] if ack else None,
                        "fresh": age < 600 and not ack,
                    })
            except Exception as e:
                logger.debug("noc problems pulse: %s", e)

            # Hunter — incidentes abiertos recientes (tope 5; el resto vive en /incidentes)
            try:
                hrows = conn.execute(
                    """
                    SELECT id, ip, alert_signature, severity, status, opened_at, ack_at, ack_by
                    FROM incidents
                    WHERE status IN ('open', 'acknowledged')
                      AND opened_at > datetime('now', '-7 days')
                    ORDER BY
                      CASE WHEN status = 'open' THEN 0 ELSE 1 END,
                      severity ASC,
                      opened_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                for r in hrows:
                    pid = f"h:{r['id']}"
                    age = _age_seconds(r["opened_at"])
                    sev_n = int(r["severity"] or 3)
                    sev = "CRITICAL" if sev_n <= 1 else ("HIGH" if sev_n == 2 else "WARNING")
                    sig = (r["alert_signature"] or "Amenaza Hunter")[:80]
                    acked = r["status"] == "acknowledged" or bool(r["ack_at"])
                    problems.append({
                        "id": pid,
                        "name": f"Hunter · {r['ip']}",
                        "kind": "security",
                        "source": "hunter",
                        "severity": sev,
                        "status": r["status"],
                        "message": sig,
                        "since": r["opened_at"],
                        "time_active_sec": age,
                        "time_active": _fmt_duration(age),
                        "acknowledged": acked,
                        "acked_at": r["ack_at"],
                        "acked_by": r["ack_by"],
                        "fresh": age < 600 and not acked,
                    })
            except Exception as e:
                logger.debug("noc problems hunter: %s", e)

            # Limpiar ACKs de problemas que ya no existen
            active_ids = {p["id"] for p in problems}
            for pid in list(acks.keys()):
                if pid not in active_ids:
                    try:
                        conn.execute(
                            "DELETE FROM noc_problem_acks WHERE problem_id = ?", (pid,)
                        )
                    except Exception:
                        pass
            conn.commit()
    except Exception as e:
        logger.error("noc active_problems: %s", e)
        return []

    problems.sort(
        key=lambda p: (
            1 if p.get("acknowledged") else 0,
            SEVERITY_RANK.get(p.get("severity") or "INFO", 9),
            -(p.get("time_active_sec") or 0),
        )
    )
    return problems


def _outage_history(limit: int = 15) -> List[Dict[str, Any]]:
    """Historial corto de caídas/recuperaciones (7 días)."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT e.ip, e.event, e.ts,
                       COALESCE(d.name, e.ip) AS name,
                       COALESCE(d.device_type, '') AS device_type
                FROM infra_events e
                LEFT JOIN infra_devices d ON d.ip = e.ip
                WHERE e.event IN ('offline', 'online')
                  AND e.ts > datetime('now', '-7 days')
                ORDER BY e.ts DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "name": r["name"],
                "kind": r["device_type"] or "generic",
                "event": r["event"],
                "at": r["ts"],
                "ago": _fmt_duration(_age_seconds(r["ts"])),
            }
            for r in rows
        ]
    except Exception as e:
        logger.debug("noc outage_history: %s", e)
        return []


def _ia_log(limit: int = 8) -> list:
    """Lee las últimas acciones IA desde Redis noc:ia_log."""
    try:
        import redis as _redis
        import json as _json
        r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=1)
        raw = r.lrange("noc:ia_log", 0, limit - 1)
        result = []
        for item in raw:
            try:
                result.append(_json.loads(item))
            except Exception:
                pass
        return result
    except Exception:
        return []


def _site_name() -> str:
    return (
        get_config("base.client_name")
        or get_config("base.site_name")
        or get_config("base.hostname")
        or ""
    )


def _agent_status() -> dict:
    state = "unknown"
    uptime_label = None
    try:
        r = subprocess.run(
            ["docker", "inspect", "shomer-agent",
             "--format", "{{.State.Status}}|{{.State.StartedAt}}"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split("|")
            state = parts[0]
            if len(parts) > 1 and parts[1]:
                from datetime import datetime as _dt, timezone as _tz
                try:
                    raw = parts[1].split(".")[0] + "+00:00"
                    started = _dt.fromisoformat(raw)
                    diff = int((_dt.now(_tz.utc) - started).total_seconds())
                    days, rem = divmod(diff, 86400)
                    hours, rem = divmod(rem, 3600)
                    mins = rem // 60
                    if days:
                        uptime_label = f"{days}d {hours}h"
                    elif hours:
                        uptime_label = f"{hours}h {mins}m"
                    else:
                        uptime_label = f"{mins}m"
                except Exception:
                    pass
    except Exception:
        pass
    provider = "groq"
    model = ""
    try:
        with open("/storage/shomer-agent/.env") as f:
            for line in f:
                line = line.strip()
                if line.startswith("LLM_PROVIDER_INTERACTIVE="):
                    provider = line.split("=", 1)[1].strip() or "groq"
                elif line.startswith("OPENAI_MODEL="):
                    model = line.split("=", 1)[1].strip()
    except Exception:
        pass
    return {
        "ok":           state == "running",
        "state":        state,
        "uptime":       uptime_label,
        "llm_provider": provider,
        "llm_model":    model,
    }


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.get("/noc", response_class=HTMLResponse, include_in_schema=False)
async def noc_page(request: Request, token: str = ""):
    _validate_token(token)
    return templates.TemplateResponse(
        "noc.html",
        {"request": request, "token": token, "site_name": _site_name()},
    )


@router.get("/noc/data")
async def noc_data(token: str = ""):
    """Datos agregados para el NOC display. Sin IPs expuestas."""
    _validate_token(token)

    guardian = _guardian_nodes()
    infra, outages_24h = _infra_devices()
    all_devices = guardian + infra

    g_online = sum(1 for d in guardian if d["status"] == "online")
    g_total = len(guardian)
    i_online = sum(1 for d in infra if d["status"] == "online")
    i_total = len(infra)

    problems = _active_problems()
    history = _outage_history(15)
    open_unacked = sum(1 for p in problems if not p.get("acknowledged"))

    return {
        "success": True,
        "site_name": _site_name(),
        "guardian": {
            "devices": guardian,
            "online": g_online,
            "total": g_total,
        },
        "inframonitor": {
            "devices": infra,
            "online": i_online,
            "total": i_total,
            "outages_24h": outages_24h,
        },
        "summary": {
            "total_devices": len(all_devices),
            "online": sum(1 for d in all_devices if d["status"] == "online"),
            "offline": sum(1 for d in all_devices if d["status"] == "offline"),
        },
        "problems": {
            "active": problems,
            "open_count": len(problems),
            "unacked_count": open_unacked,
        },
        "outage_history": history,
        "wan": _wan_status(),
        "hunter": _hunter_stats(),
        "risks": _risk_findings(),
        "server": _server_resources(),
        "services": _services_status(),
        "events": _recent_events(),
        "agent": _agent_status(),
        "ia_log": _ia_log(),
    }


@router.post("/noc/problems/ack")
async def noc_ack_problem(body: NocAckBody, token: str = ""):
    """Marca un problema NOC como visto (ACK). Token de display requerido."""
    _validate_token(token)
    pid = (body.problem_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="problem_id requerido")

    # Hunter: reutilizar tabla incidents
    if pid.startswith("h:"):
        try:
            inc_id = int(pid.split(":", 1)[1])
        except ValueError:
            raise HTTPException(status_code=400, detail="ID Hunter inválido")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, status FROM incidents WHERE id = ?", (inc_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Incidente no encontrado")
            if row["status"] == "closed":
                return {"success": True, "problem_id": pid, "status": "closed"}
            conn.execute(
                """
                UPDATE incidents
                SET status = 'acknowledged',
                    ack_at = COALESCE(ack_at, ?),
                    ack_by = COALESCE(ack_by, ?)
                WHERE id = ?
                """,
                (now, (body.by or "noc")[:80], inc_id),
            )
            conn.commit()
        return {"success": True, "problem_id": pid, "acknowledged": True}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        _ensure_noc_ack_table(conn)
        conn.execute(
            """
            INSERT INTO noc_problem_acks (problem_id, acked_at, acked_by)
            VALUES (?, ?, ?)
            ON CONFLICT(problem_id) DO UPDATE SET
                acked_at = excluded.acked_at,
                acked_by = excluded.acked_by
            """,
            (pid, now, (body.by or "noc")[:80]),
        )
        conn.commit()
    return {"success": True, "problem_id": pid, "acknowledged": True}


@router.get("/noc/token")
async def noc_token_info():
    """Muestra el token NOC actual (requiere acceso al backend)."""
    from app.api.auth_api import get_current_user
    token = _get_or_create_token()
    return {"token": token, "hint": f"URL: /noc?token={token}"}


@router.post("/noc/token/regenerate")
async def noc_token_regenerate(user=Depends(require_admin)):
    """Regenera el token NOC (invalida accesos anteriores)."""
    new_token = secrets.token_urlsafe(24)
    set_config("noc.display_token", new_token)
    return {"token": new_token, "message": "Token regenerado — actualizar URL en el TV"}
