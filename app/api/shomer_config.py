"""
Configuración de sistema, red, Telegram, escaneo panel y nodos_gl.json.
Extraído de shomer.py.
"""
import asyncio
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.api.auth_api import get_current_user, require_admin
from app.api.shomer_common import (
    ALL_MODULES,
    MODULES_ENABLED_KEY,
    get_config,
    get_db,
    get_enabled_modules,
    set_config,
)
from app.backend.db import NODOS_GL_PATH

router = APIRouter(tags=["Shomer Guardian"])


@router.get("/config/system")
async def get_system_config(user=Depends(require_admin)):
    """
    Retorna la configuración completa del sistema.
    Si no hay configuración guardada, detecta automáticamente con get_network_context().
    """
    try:
        from app.scripts.network_context import get_network_context

        auto = get_network_context()
    except Exception:
        auto = {"subnet": None, "interface": None, "gateway": None}

    return {
        "success": True,
        "base": {
            "interface": get_config("base.interface", auto.get("interface")),
            "subnet": get_config("base.subnet", auto.get("subnet")),
            "gateway": get_config("base.gateway", auto.get("gateway")),
            "server_ip": get_config("base.server_ip", auto.get("server_ip")),
            "site_timezone": get_config("base.site_timezone", "UTC"),
        },
        "guardian": {
            "subnets": get_config("guardian.subnets", [auto.get("subnet")] if auto.get("subnet") else []),
            "monitor_enabled": get_config("guardian.monitor_enabled", True),
            "fail_threshold": get_config("guardian.fail_threshold", 3),
            "cooldown_sec": get_config("guardian.cooldown_sec", 360),
            "telegram_token": get_config("guardian.telegram_token", ""),
            "telegram_chat_id": get_config("guardian.telegram_chat_id", ""),
            "check_dns_enabled": get_config("guardian.check_dns_enabled", True),
            "check_http_enabled": get_config("guardian.check_http_enabled", True),
            "check_latency_enabled": get_config("guardian.check_latency_enabled", True),
            "dns_probe_host": get_config("guardian.dns_probe_host", "google.com"),
            "dns_probe_server": get_config("guardian.dns_probe_server", "8.8.8.8"),
            "http_probe_url": get_config(
                "guardian.http_probe_url", "http://connectivitycheck.gstatic.com/generate_204"
            ),
            "http_probe_expect": get_config("guardian.http_probe_expect", "204"),
            "ping_count": get_config("guardian.ping_count", 3),
            "ping_loss_degraded_pct": get_config("guardian.ping_loss_degraded_pct", 60),
            "ping_rtt_degraded_ms": get_config("guardian.ping_rtt_degraded_ms", 400),
            "degraded_persist_ticks": get_config("guardian.degraded_persist_ticks", 3),
            "degraded_alert_cooldown_sec": get_config("guardian.degraded_alert_cooldown_sec", 1800),
            "health_interval_sec": get_config("guardian.health_interval_sec", 30),
            "wan_check_ips": get_config("guardian.wan_check_ips", "8.8.8.8,1.1.1.1,208.67.222.222"),
            "wan_min_fail": get_config("guardian.wan_min_fail", 2),
            "wan_fail_sec": get_config("guardian.wan_fail_sec", 120),
            "wan_cooldown_sec": get_config("guardian.wan_cooldown_sec", 1800),
            "ram_alert_pct": get_config("guardian.ram_alert_pct", 90),
            "heartbeat_hours": get_config("guardian.heartbeat_hours", "0,8,16"),
        },
        "tracker": {
            "subnets": get_config("tracker.subnets", [auto.get("subnet")] if auto.get("subnet") else []),
        },
        "hunter": {
            "interfaces": get_config("hunter.interfaces", [auto.get("interface")] if auto.get("interface") else []),
            "subnets": get_config("hunter.subnets", [auto.get("subnet")] if auto.get("subnet") else []),
            "firewall_ip": get_config("hunter.firewall_ip", ""),
            "firewall_user": get_config("hunter.firewall_user", "admin"),
            "firewall_pass": get_config("hunter.firewall_pass", ""),
            "auto_block_enabled": get_config("hunter.auto_block_enabled", False),
            "auto_block_min_severity": get_config("hunter.auto_block_min_severity", 2),
            "auto_block_only_external": get_config("hunter.auto_block_only_external", True),
            "auto_block_exceptions": get_config("hunter.auto_block_exceptions", []),
            "high_recurrence_min": get_config("hunter.high_recurrence_min", 3),
            "high_recurrence_window_sec": get_config("hunter.high_recurrence_window_sec", 600),
            "high_recurrence_warn_at": get_config("hunter.high_recurrence_warn_at", 2),
            "integration_key": get_config("hunter.integration_key", ""),
            "wazuh_dashboard_url": get_config("hunter.wazuh_dashboard_url", ""),
            "firewall_type": get_config("hunter.firewall_type", "openwrt"),
            "firewall_port": get_config("hunter.firewall_port", 22),
            "firewall_timeout": get_config("hunter.firewall_timeout", 10),
            "routeros_auto_drop_enabled": get_config("hunter.routeros_auto_drop_enabled", False),
        },
        "protector": {
            "backup_sources": get_config("protector.backup_sources", []),
            "retention_days": get_config("protector.retention_days", 7),
        },
        "monitor": {
            "status_retention_days": get_config("monitor.status_retention_days", 90),
            "infra_events_retention_days": get_config("monitor.infra_events_retention_days", 90),
            "event_log_retention_days": get_config("monitor.event_log_retention_days", 30),
            "aggressive_prune_disk_pct": get_config("monitor.aggressive_prune_disk_pct", 85),
            "outage_report_enabled": get_config("monitor.outage_report_enabled", True),
            "outage_report_min_aps": get_config("monitor.outage_report_min_aps", 5),
            "outage_report_min_devices": get_config("monitor.outage_report_min_devices", 10),
            "outage_report_repeat_hours": get_config("monitor.outage_report_repeat_hours", 24),
            "outage_report_repeat_min": get_config("monitor.outage_report_repeat_min", 2),
            "outage_report_settle_sec": get_config("monitor.outage_report_settle_sec", 90),
        },
        "auto_detected": auto,
    }


@router.post("/config/system")
async def save_system_config(payload: Dict[str, Any] = Body(...), user=Depends(get_current_user)):
    """
    Guarda configuración del sistema por módulo.
    Solo guarda los campos que vengan en el payload — no sobreescribe los demás.
    """
    saved = []
    errors = []

    base = payload.get("base", {})
    for field in ["interface", "subnet", "gateway", "server_ip", "site_timezone"]:
        if field in base and base[field] is not None:
            if set_config(f"base.{field}", base[field]):
                saved.append(f"base.{field}")
            else:
                errors.append(f"base.{field}")

    guardian = payload.get("guardian", {})
    for field in [
        "subnets", "monitor_enabled", "fail_threshold", "cooldown_sec",
        "telegram_token", "telegram_chat_id",
        "check_dns_enabled", "check_http_enabled", "check_latency_enabled",
        "dns_probe_host", "dns_probe_server",
        "http_probe_url", "http_probe_expect",
        "ping_count", "ping_loss_degraded_pct", "ping_rtt_degraded_ms",
        "degraded_persist_ticks", "degraded_alert_cooldown_sec",
        "health_interval_sec", "wan_check_ips", "wan_min_fail",
        "wan_fail_sec", "wan_cooldown_sec",
        "ram_alert_pct", "heartbeat_hours",
    ]:
        if field in guardian:
            if set_config(f"guardian.{field}", guardian[field]):
                saved.append(f"guardian.{field}")
            else:
                errors.append(f"guardian.{field}")

    tracker = payload.get("tracker", {})
    if "subnets" in tracker:
        if set_config("tracker.subnets", tracker["subnets"]):
            saved.append("tracker.subnets")
        else:
            errors.append("tracker.subnets")

    hunter = payload.get("hunter", {})
    for field in [
        "interfaces",
        "subnets",
        "firewall_ip",
        "firewall_user",
        "firewall_pass",
        "auto_block_enabled",
        "auto_block_min_severity",
        "auto_block_only_external",
        "auto_block_exceptions",
        "high_recurrence_min",
        "high_recurrence_window_sec",
        "high_recurrence_warn_at",
        "integration_key",
        "wazuh_dashboard_url",
        "firewall_type",
        "firewall_port",
        "firewall_timeout",
        "routeros_auto_drop_enabled",
    ]:
        if field in hunter:
            if set_config(f"hunter.{field}", hunter[field]):
                saved.append(f"hunter.{field}")
            else:
                errors.append(f"hunter.{field}")

    protector = payload.get("protector", {})
    for field in ["backup_sources", "retention_days"]:
        if field in protector:
            if set_config(f"protector.{field}", protector[field]):
                saved.append(f"protector.{field}")
            else:
                errors.append(f"protector.{field}")

    monitor = payload.get("monitor", {})
    for field in [
        "status_retention_days",
        "infra_events_retention_days",
        "event_log_retention_days",
        "aggressive_prune_disk_pct",
        "outage_report_enabled",
        "outage_report_min_aps",
        "outage_report_min_devices",
        "outage_report_repeat_hours",
        "outage_report_repeat_min",
        "outage_report_settle_sec",
    ]:
        if field in monitor and monitor[field] is not None:
            if set_config(f"monitor.{field}", monitor[field]):
                saved.append(f"monitor.{field}")
            else:
                errors.append(f"monitor.{field}")

    if monitor:
        try:
            from app.api.shomer_status_events import run_data_retention_prune
            run_data_retention_prune(force=True)
        except Exception:
            pass

    return {"success": len(errors) == 0, "saved": saved, "errors": errors}


@router.get("/config/site-timezone")
async def get_site_timezone():
    """Zona horaria del sitio — lectura pública para el frontend."""
    return {"success": True, "timezone": get_config("base.site_timezone", "UTC")}


@router.get("/config/modules")
async def get_modules_config():
    """Lista los módulos habilitados en esta instalación."""
    enabled = get_enabled_modules()
    return {
        "success": True,
        "enabled": enabled,
        "all": ALL_MODULES,
        "disabled": [m for m in ALL_MODULES if m not in enabled],
    }


@router.post("/config/modules")
async def save_modules_config(body: Dict[str, Any] = Body(...), user=Depends(require_admin)):
    """Guarda los módulos habilitados. Solo admin. Body: {enabled: ['guardian','hunter',...]}"""
    enabled = body.get("enabled", [])
    if not isinstance(enabled, list):
        raise HTTPException(status_code=400, detail="'enabled' debe ser una lista")
    enabled = [m for m in enabled if m in ALL_MODULES]
    if set_config(MODULES_ENABLED_KEY, enabled):
        return {
            "success": True,
            "enabled": enabled,
            "disabled": [m for m in ALL_MODULES if m not in enabled],
        }
    raise HTTPException(status_code=500, detail="Error guardando configuración de módulos")


@router.post("/telegram/test")
async def telegram_test(user=Depends(get_current_user)):
    """Envía un mensaje de prueba por Telegram para verificar la configuración."""
    try:
        from app.scripts.alerts import send_telegram_alert

        ok = send_telegram_alert(
            "🧪 <b>SALUD DE NODOS</b> SHOMER: Prueba de configuración Telegram — conexión exitosa."
        )
        if ok:
            return {"success": True, "message": "Mensaje enviado correctamente"}
        return JSONResponse(
            status_code=400,
            content={"success": False, "detail": "Token o Chat ID inválidos, o mensaje bloqueado por filtro"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/network_context")
async def network_context(user=Depends(get_current_user)):
    """
    Contexto de red del Shomer.
    Interfaz y subred desde get_network_context() + system_state (sin asumir nombre fijo de NIC).
    """
    try:
        from app.scripts.network_context import get_network_context

        auto = get_network_context(None)
    except Exception:
        auto = {"subnet": None, "interface": None, "gateway": None}

    det_iface = auto.get("interface")
    saved_iface = get_config("base.interface", None)
    iface = saved_iface or det_iface

    det_ip = auto.get("server_ip")
    saved_ip = get_config("base.server_ip", None)
    return {
        "success": True,
        "interface": iface,
        "subnet": get_config("base.subnet", auto.get("subnet")),
        "gateway": get_config("base.gateway", auto.get("gateway")),
        "server_ip": saved_ip or det_ip,
        "auto_detected": {
            "interface": det_iface,
            "subnet": auto.get("subnet"),
            "gateway": auto.get("gateway"),
            "server_ip": det_ip,
        },
    }


@router.post("/config/scan")
async def config_scan(payload: Optional[Any] = Body(default=None), user=Depends(get_current_user)):
    """
    Escaneo para el panel. Acepta { "subnets": ["192.168.1.0/24", ...] }.
    No modifica nada de /reboot ni /nodes.
    """
    subnets = None
    if payload is not None:
        if isinstance(payload, dict):
            subnets = payload.get("subnets")
        else:
            raise HTTPException(status_code=400, detail="Body debe ser un JSON con 'subnets'")
    if not subnets or not isinstance(subnets, list):
        raise HTTPException(status_code=400, detail="Campo 'subnets' requerido con lista de rangos")

    try:
        from app.scripts.discovery import run_discovery  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo importar run_discovery: {e}")

    def _blocking_scan():
        with get_db() as conn:
            conn.execute("DELETE FROM discovered_devices")
        run_discovery()
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT ip_address AS ip, mac_address AS mac, hostname, status, inferred_type, last_seen
                FROM discovered_devices
                WHERE status = 'online'
                  AND ip_address NOT IN (SELECT ip_address FROM infra_nodes)
                ORDER BY last_seen DESC
                """
            )
            return [dict(r) for r in cur.fetchall()]

    try:
        rows = await asyncio.to_thread(_blocking_scan)
        devices = [
            {
                "ip": r["ip"],
                "mac": r["mac"],
                "hostname": r["hostname"] or "",
                "status": r["status"],
                "inferred_type": r["inferred_type"] or "unknown",
                "last_seen": r["last_seen"] or "",
            }
            for r in rows
        ]
        return {"success": True, "devices": devices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/save_nodos")
async def config_save_nodos(
    payload: Dict[str, Any] = Body(...),
    _admin: dict = Depends(require_admin),
):
    """
    Guarda nodos elegidos en el panel. Escribe en devices y en nodos_gl.json para monitor.py.
    Requiere rol admin.
    """
    nodos = payload.get("nodos")
    if not isinstance(nodos, list) or not nodos:
        raise HTTPException(status_code=400, detail="Se requiere lista de nodos")
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    ip TEXT PRIMARY KEY,
                    name TEXT,
                    location TEXT,
                    is_shomer_node INTEGER DEFAULT 0
                )
                """
            )
            for n in nodos:
                ip = (n.get("ip") or "").strip()
                if not ip:
                    continue
                loc = (n.get("ubicacion") or ip).strip()
                cur.execute(
                    "INSERT OR REPLACE INTO devices (ip, name, location, is_shomer_node) VALUES (?, ?, ?, 1)",
                    (ip, n.get("nombre") or ip, loc),
                )
            conn.commit()
        try:
            with open(NODOS_GL_PATH, "w", encoding="utf-8") as f:
                import json as _json

                _json.dump(nodos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[CONFIG SAVE NODOS] Error escribiendo nodos_gl.json: {e}")
        return {"success": True, "message": "Nodos Shomer guardados correctamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/nodos")
async def config_get_nodos(user=Depends(get_current_user)):
    """
    Lee nodos_gl.json y devuelve la lista de nodos configurados.
    Si el archivo no existe, devuelve array vacío.
    """
    import json as _json

    try:
        if os.path.exists(NODOS_GL_PATH):
            with open(NODOS_GL_PATH, "r", encoding="utf-8") as f:
                nodos = _json.load(f)
        else:
            nodos = []
        return {"success": True, "nodos": nodos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
