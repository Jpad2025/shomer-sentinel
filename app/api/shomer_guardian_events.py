"""Guardian — eventos en tiempo real y modo mantenimiento (global y por nodo)."""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_db, get_redis
from app.api.shomer_guardian_lib import (
    EVENTS_KEY, MAINTENANCE_KEY, NODE_MAINTENANCE_PREFIX,
    ALLOWED_IP_PATTERN, log_event, send_telegram_safe
)

router = APIRouter(tags=["Shomer Guardian"])


@router.get("/events")
async def get_events(since: int = 0, user=Depends(get_current_user)):
    """Eventos recientes del Guardian (AUTO-REBOOT, COOLDOWN, MANTENIMIENTO) para el panel de logs."""
    r = get_redis()
    if r is None:
        return {"success": True, "events": []}
    try:
        raw = r.lrange(EVENTS_KEY, 0, 199)
        events = []
        for item in raw:
            try:
                e = json.loads(item)
                if e.get("ts", 0) > since:
                    events.append(e)
            except Exception:
                pass
        events.sort(key=lambda x: x.get("ts", 0))
        return {"success": True, "events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/maintenance")
async def get_maintenance(user=Depends(get_current_user)):
    """Estado de modo mantenimiento (no reiniciar nodos automáticamente)."""
    r = get_redis()
    if r:
        try:
            v = r.get(MAINTENANCE_KEY)
            return {"success": True, "maintenance": v == "1"}
        except Exception:
            pass
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.commit()
            cur.execute("SELECT value FROM system_state WHERE key = 'maintenance'")
            row = cur.fetchone()
            return {"success": True, "maintenance": (row and row[0] == "1")}
    except Exception:
        pass
    return {"success": True, "maintenance": False}


@router.post("/maintenance/on")
async def set_maintenance_on(user=Depends(get_current_user)):
    """Activa modo mantenimiento (no reinicios automáticos). No afecta reinicio manual."""
    r = get_redis()
    if r:
        try:
            r.set(MAINTENANCE_KEY, "1")
            log_event(r, "warning", "MANTENIMIENTO", "Modo mantenimiento ACTIVADO — reboots automáticos pausados")
            return {"success": True, "maintenance": True}
        except Exception:
            pass
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.commit()
            cur.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES ('maintenance', '1')"
            )
            conn.commit()
        return {"success": True, "maintenance": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/maintenance/off")
async def set_maintenance_off(user=Depends(get_current_user)):
    """Desactiva modo mantenimiento."""
    r = get_redis()
    if r:
        try:
            r.delete(MAINTENANCE_KEY)
            log_event(r, "success", "MANTENIMIENTO", "Modo mantenimiento DESACTIVADO — reboots automáticos reanudados")
            return {"success": True, "maintenance": False}
        except Exception:
            pass
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.commit()
            cur.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES ('maintenance', '0')"
            )
            conn.commit()
        return {"success": True, "maintenance": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Mantenimiento por nodo ────────────────────────────────────────────────────

class NodeMaintenanceRequest(BaseModel):
    minutes: Optional[int] = None  # None = sin expiración


@router.get("/node_maintenance/{ip}")
async def get_node_maintenance(ip: str):
    """Estado de mantenimiento de un nodo específico."""
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")
    r = get_redis()
    if r is None:
        return {"success": True, "ip": ip, "maintenance": False, "ttl": None}
    key = f"{NODE_MAINTENANCE_PREFIX}{ip}"
    val = r.get(key)
    ttl = r.ttl(key) if val else None
    return {
        "success": True,
        "ip": ip,
        "maintenance": val == "1",
        "ttl_seconds": ttl if ttl and ttl > 0 else None,
    }


@router.post("/node_maintenance/{ip}/on")
async def set_node_maintenance_on(ip: str, body: NodeMaintenanceRequest = NodeMaintenanceRequest(), user=Depends(get_current_user)):
    """
    Activa mantenimiento para un nodo específico.
    El nodo seguirá siendo monitoreado pero Guardian no lo reiniciará automáticamente.
    Parámetro opcional: minutes (TTL). Si se omite, no expira.
    """
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")
    r = get_redis()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    key = f"{NODE_MAINTENANCE_PREFIX}{ip}"
    if body.minutes and body.minutes > 0:
        r.setex(key, body.minutes * 60, "1")
        detail = f"por {body.minutes} min"
        tg_detail = f"por {body.minutes} minutos"
    else:
        r.set(key, "1")
        detail = "sin expiración"
        tg_detail = "sin límite de tiempo"
    log_event(r, "warning", "MANTENIMIENTO-NODO",
              f"Mantenimiento ACTIVADO en nodo {ip} ({detail})")
    try:
        send_telegram_safe(
            f"🔧 <b>MANTENIMIENTO NODO</b>: {ip} en modo mantenimiento ({tg_detail}) — "
            f"Guardian NO reiniciará este nodo automáticamente."
        )
    except Exception:
        pass
    return {
        "success": True,
        "ip": ip,
        "maintenance": True,
        "minutes": body.minutes,
    }


@router.post("/node_maintenance/{ip}/off")
async def set_node_maintenance_off(ip: str, user=Depends(get_current_user)):
    """Desactiva mantenimiento de un nodo específico."""
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")
    r = get_redis()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    key = f"{NODE_MAINTENANCE_PREFIX}{ip}"
    r.delete(key)
    log_event(r, "success", "MANTENIMIENTO-NODO",
              f"Mantenimiento DESACTIVADO en nodo {ip}")
    try:
        send_telegram_safe(
            f"✅ <b>MANTENIMIENTO NODO</b>: {ip} — mantenimiento desactivado. "
            f"Guardian reanuda reboots automáticos."
        )
    except Exception:
        pass
    return {"success": True, "ip": ip, "maintenance": False}
