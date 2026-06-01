"""
Estado del sistema — servicios systemd, recursos hardware, NICs, discos, logs.
Endpoints:
  GET /api/system-health   — servicios + recursos + NICs + discos + resumen ejecutivo
  GET /api/system-logs     — últimas N líneas journalctl
"""
from __future__ import annotations

import re
import socket
import sqlite3
import subprocess
import time
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, Depends, Query

from app.api.auth_api import get_current_user
from app.backend.db import STORAGE_DB

router = APIRouter(tags=["System Status"])

SERVICES: List[tuple] = [
    ("shomer-guardian", "Guardian + Hunter",       "APIs principales — panel y detección"),
    ("shomer-tools",    "Tracker + Protector",     "Inventario de equipos y backups"),
    ("nginx",           "Proxy Web",               "Acceso al panel HTTPS"),
    ("redis-server",    "Redis",                   "Caché y eventos en tiempo real"),
    ("shomer-agent",    "Bot Telegram",            "Asistente IA — Docker"),
    ("suricata",        "Suricata IDS",            "Captura y análisis de tráfico espejo"),
    ("wazuh-manager",   "Wazuh SIEM",              "Registros de seguridad y alertas"),
    ("shomer-monitor",  "Monitor infraestructura", "Script de monitoreo de red (opcional)"),
]

DISK_PARTITIONS: List[tuple] = [
    ("/",    "Sistema",  "general"),
    ("/srv", "Backups",  "backup"),
    ("/var", "Logs",     "logs"),
]

_ALLOWED_SERVICES = {name for name, *_ in SERVICES}
_NIC_IGNORE = {"lo", "docker0"}


def _svc_status(name: str) -> str:
    # shomer-agent corre como container Docker — leer su estado real, no systemd
    if name == "shomer-agent":
        try:
            r = subprocess.run(
                ["docker", "inspect", "shomer-agent", "--format", "{{.State.Status}}"],
                capture_output=True, text=True, timeout=3,
            )
            if r.returncode == 0:
                st = r.stdout.strip()
                return "active" if st == "running" else st or "inactive"
        except Exception:
            pass
        return "inactive"

    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=3,
        )
        status = r.stdout.strip()
        # Verificar si la unidad realmente existe (is-active puede devolver "inactive"
        # aunque la unidad no esté instalada en ninguna versión de systemd)
        if status in ("inactive", "unknown", ""):
            r2 = subprocess.run(
                ["systemctl", "status", name, "--no-pager"],
                capture_output=True, text=True, timeout=3,
            )
            combined = (r2.stdout + r2.stderr).lower()
            if "could not be found" in combined or r2.returncode == 4:
                return "not_installed"
        return status or "unknown"
    except Exception:
        return "unknown"


def _safe_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "—"


def _get_config(key: str, default: Any = None) -> Any:
    try:
        con = sqlite3.connect(f"{STORAGE_DB}/network_monitor.db")
        row = con.execute(
            "SELECT value FROM system_state WHERE key=?", (key,)
        ).fetchone()
        con.close()
        if row and row[0] is not None:
            return str(row[0]).strip('"')
    except Exception:
        pass
    return default


def _get_nics() -> List[Dict[str, Any]]:
    addrs   = psutil.net_if_addrs()
    stats   = psutil.net_if_stats()
    result  = []
    for name in sorted(addrs.keys()):
        if name in _NIC_IGNORE:
            continue
        stat = stats.get(name)
        ipv4 = next(
            (a.address for a in addrs[name]
             if (a.family.name if hasattr(a.family, "name") else str(a.family)) == "AF_INET"),
            None
        )
        result.append({
            "name":  name,
            "is_up": stat.isup if stat else False,
            "ipv4":  ipv4,
        })
    return result


def _get_disks() -> List[Dict[str, Any]]:
    result = []
    for path, label, kind in DISK_PARTITIONS:
        try:
            d = psutil.disk_usage(path)
            result.append({
                "path":     path,
                "label":    label,
                "kind":     kind,
                "percent":  round(d.percent, 1),
                "used_gb":  round(d.used  / 1024 ** 3, 1),
                "free_gb":  round(d.free  / 1024 ** 3, 1),
                "total_gb": round(d.total / 1024 ** 3, 1),
            })
        except Exception:
            result.append({"path": path, "label": label, "kind": kind,
                           "error": "no disponible"})
    return result


def _get_uptime() -> Dict[str, Any]:
    up_sec = int(time.time() - psutil.boot_time())
    days, rem = divmod(up_sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        label = f"{days}d {hours}h {mins}m"
    elif hours:
        label = f"{hours}h {mins}m"
    else:
        label = f"{mins}m"
    return {"seconds": up_sec, "label": label}


def _ping_host(host: str) -> Dict[str, Any]:
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "2", host],
            capture_output=True, text=True, timeout=4,
        )
        if r.returncode == 0:
            m = re.search(r"rtt .* = [\d.]+/([\d.]+)/", r.stdout)
            latency = round(float(m.group(1)), 1) if m else None
            return {"reachable": True, "latency_ms": latency}
        return {"reachable": False, "latency_ms": None}
    except Exception:
        return {"reachable": False, "latency_ms": None}


def _get_wan_status() -> Dict[str, Any]:
    # Primero Redis (escrito por Guardian)
    try:
        import redis as _redis
        r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=1)
        wan = r.get("wan_status")
        if wan:
            ok = wan.lower() in ("online", "up", "ok")
            return {"ok": ok, "status": wan, "source": "guardian"}
    except Exception:
        pass
    # Fallback: ping directo
    res = _ping_host("8.8.8.8")
    return {
        "ok": res["reachable"],
        "status": "online" if res["reachable"] else "offline",
        "latency_ms": res.get("latency_ms"),
        "source": "ping",
    }


def _get_guardian_summary() -> Dict[str, Any]:
    try:
        import redis as _redis
        r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=1)
        keys = r.keys("status:*")
        total   = len(keys)
        online  = sum(1 for k in keys if r.get(k) == "online")
        offline = total - online
        if total > 0:
            return {"total": total, "online": online, "offline": offline, "ok": offline == 0}
    except Exception:
        pass
    try:
        con = sqlite3.connect(f"{STORAGE_DB}/network_monitor.db")
        rows = con.execute(
            "SELECT status FROM devices WHERE is_active=1"
        ).fetchall()
        con.close()
        total   = len(rows)
        online  = sum(1 for r in rows if r[0] == "online")
        offline = total - online
        return {"total": total, "online": online, "offline": offline, "ok": offline == 0}
    except Exception:
        return {"total": 0, "online": 0, "offline": 0, "ok": True}


def _get_last_backup() -> Dict[str, Any]:
    try:
        con = sqlite3.connect(f"{STORAGE_DB}/network_monitor.db")
        last = con.execute(
            "SELECT name, last_backup_at, last_status FROM backup_devices "
            "WHERE is_active=1 AND last_backup_at IS NOT NULL "
            "ORDER BY last_backup_at DESC LIMIT 1"
        ).fetchone()
        failed = con.execute(
            "SELECT COUNT(*) FROM backup_devices WHERE is_active=1 AND last_status='failed'"
        ).fetchone()
        total = con.execute(
            "SELECT COUNT(*) FROM backup_devices WHERE is_active=1"
        ).fetchone()
        con.close()
        n_failed = failed[0] if failed else 0
        n_total  = total[0]  if total  else 0
        if not last:
            return {"ok": None, "last_at": None, "failed": n_failed, "total": n_total}
        return {
            "ok":          n_failed == 0,
            "last_at":     last[1],
            "last_name":   last[0],
            "last_status": last[2],
            "failed":      n_failed,
            "total":       n_total,
        }
    except Exception:
        return {"ok": None, "last_at": None, "failed": 0, "total": 0}


def _get_hunter_stats() -> Dict[str, Any]:
    try:
        con = sqlite3.connect(f"{STORAGE_DB}/network_monitor.db")
        active = con.execute(
            "SELECT COUNT(*) FROM blocked_ips WHERE unblocked_at IS NULL"
        ).fetchone()
        h24 = con.execute(
            "SELECT COUNT(*) FROM blocked_ips WHERE blocked_at > datetime('now', '-24 hours')"
        ).fetchone()
        con.close()
        n = active[0] if active else 0
        return {"active_blocks": n, "blocks_24h": h24[0] if h24 else 0, "ok": n == 0}
    except Exception:
        return {"active_blocks": 0, "blocks_24h": 0, "ok": True}


def _get_agent_status() -> Dict[str, Any]:
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


@router.get("/api/system-health")
async def system_health(_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    services = [
        {"name": n, "label": lbl, "desc": desc, "status": st}
        for n, lbl, desc in SERVICES
        if (st := _svc_status(n)) != "not_installed"
    ]
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    return {
        "hostname":    _safe_hostname(),
        "services":    services,
        "resources": {
            "cpu_percent":  round(cpu, 1),
            "ram_percent":  round(mem.percent, 1),
            "ram_used_gb":  round(mem.used  / 1024 ** 3, 1),
            "ram_total_gb": round(mem.total / 1024 ** 3, 1),
        },
        "uptime":        _get_uptime(),
        "nics":          _get_nics(),
        "disks":         _get_disks(),
        "wan":           _get_wan_status(),
        "guardian":      _get_guardian_summary(),
        "last_backup":   _get_last_backup(),
        "hunter_stats":  _get_hunter_stats(),
        "agent":         _get_agent_status(),
    }


@router.get("/api/system-logs")
async def system_logs(
    service: str = Query("shomer-guardian"),
    lines:   int  = Query(60, ge=20, le=200),
    _user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    if service not in _ALLOWED_SERVICES:
        return {"service": service, "lines": [], "error": "servicio no permitido"}
    try:
        r = subprocess.run(
            ["journalctl", "-u", service, "-n", str(lines),
             "--no-pager", "--output=short"],
            capture_output=True, text=True, timeout=5,
        )
        log_lines = r.stdout.splitlines()
    except Exception as e:
        log_lines = [f"Error obteniendo logs: {e}"]
    return {"service": service, "lines": log_lines}
