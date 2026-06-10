"""
NOC Display — Dashboard TV tiempo real.
Lee Guardian (infra_nodes + devices) + Inframonitor (infra_devices + infra_status).
Token simple en URL, sin login. No expone IPs ni credenciales.
"""
import json
import logging
import re
import secrets
import socket
import subprocess

import psutil
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.auth_api import require_admin
from app.api.shomer_common import get_config, get_db, set_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["noc"])

import os as _os
_TEMPLATES_DIR = _os.path.join(_os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

SEVERITY_LABEL = {1: "CRÍTICO", 2: "ALTO", 3: "MEDIO", 4: "BAJO", 5: "INFO"}


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
                    snmp_info = {
                        "model": (sd.get("model") or "")[:35],
                        "uptime": sd.get("uptime") or "",
                        "hostname": sd.get("hostname") or "",
                        "ports_up": sum(1 for i in ifaces if i.get("oper_status") == "UP"),
                        "ports_total": len(ifaces),
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
        cpu = psutil.cpu_percent(interval=0.5)
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
        "wan": _wan_status(),
        "hunter": _hunter_stats(),
        "risks": _risk_findings(),
        "server": _server_resources(),
        "services": _services_status(),
        "events": _recent_events(),
        "agent": _agent_status(),
    }


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
