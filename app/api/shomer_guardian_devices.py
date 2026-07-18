"""Guardian — CRUD tabla devices (routers SSH para panel)."""
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.auth_api import get_current_user, require_admin
from app.api.shomer_common import get_db, get_redis
from app.api.shomer_guardian_discovery import _sync_nodos_gl_from_devices
from app.api.shomer_guardian_lib import (
    FAILURES_KEY_PREFIX,
    LAST_REBOOT_KEY_PREFIX,
    NODE_MAINTENANCE_PREFIX,
)

router = APIRouter(tags=["Shomer Guardian"])


@router.get("/api/router-devices")
async def list_router_devices(_user: Dict[str, Any] = Depends(get_current_user)):
    """Lista dispositivos SSH (tabla devices). No expone passwords."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, ip_address, device_type, ssh_user, ssh_port, "
            "       location, is_active, reboot_method, status "
            "FROM devices ORDER BY is_active DESC, name"
        ).fetchall()
    return {"success": True, "devices": [dict(r) for r in rows]}


@router.post("/api/router-devices")
async def save_router_device(
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Crea o actualiza un dispositivo en la tabla devices. Requiere admin."""
    name = (body.get("name") or "").strip()
    ip = (body.get("ip") or "").strip()
    if not name or not ip:
        raise HTTPException(status_code=400, detail="nombre e IP son requeridos")
    dtype = body.get("device_type", "router")
    user = (body.get("ssh_user") or "").strip()
    passwd = (body.get("ssh_password") or "").strip()
    port = int(body.get("ssh_port") or 22)
    loc = (body.get("location") or "").strip()
    active = int(bool(body.get("is_active", True)))
    method = body.get("reboot_method", "ssh")
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM devices WHERE ip_address=?", (ip,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE devices SET name=?,device_type=?,ssh_user=?,ssh_port=?,"
                "location=?,is_active=?,reboot_method=?,updated_at=datetime('now') "
                "WHERE ip_address=?",
                (name, dtype, user, port, loc, active, method, ip),
            )
            if passwd:
                conn.execute(
                    "UPDATE devices SET ssh_password=? WHERE ip_address=?", (passwd, ip)
                )
        else:
            conn.execute(
                "INSERT INTO devices (name,ip_address,device_type,ssh_user,ssh_password,ssh_port,"
                "location,is_active,reboot_method,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
                (name, ip, dtype, user, passwd, port, loc, active, method),
            )
        conn.commit()
    return {"success": True, "message": f"Dispositivo {name} guardado"}


@router.delete("/api/router-devices/{device_id}")
async def delete_router_device(
    device_id: int,
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Elimina un dispositivo de la tabla devices y limpia sus claves Redis."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT ip_address FROM devices WHERE id=?", (device_id,)
        ).fetchone()
        conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
        conn.execute(
            "DELETE FROM infra_nodes WHERE ip_address=?", (row["ip_address"],)
        ) if row else None
        try:
            _sync_nodos_gl_from_devices(conn)
        except Exception:
            pass
        conn.commit()

    if row:
        ip = row["ip_address"]
        r = get_redis()
        if r:
            for key in (
                f"status:{ip}",
                f"{FAILURES_KEY_PREFIX}{ip}",
                f"{LAST_REBOOT_KEY_PREFIX}{ip}",
                f"{NODE_MAINTENANCE_PREFIX}{ip}",
                f"degraded_notified:{ip}",
                f"degraded_streak:{ip}",
            ):
                r.delete(key)

    return {"success": True, "message": "Dispositivo eliminado"}


def _clean_redis_for_ip(ip: str) -> None:
    r = get_redis()
    if r:
        for key in (
            f"status:{ip}",
            f"{FAILURES_KEY_PREFIX}{ip}",
            f"{LAST_REBOOT_KEY_PREFIX}{ip}",
            f"{NODE_MAINTENANCE_PREFIX}{ip}",
            f"degraded_notified:{ip}",
            f"degraded_streak:{ip}",
        ):
            r.delete(key)


@router.post("/api/router-devices/by-ip/{ip}/deactivate")
async def deactivate_device(
    ip: str,
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Pausa el monitoreo (is_active=0) y limpia Redis. El registro queda en el catálogo."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM devices WHERE ip_address=?", (ip,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
        conn.execute(
            "UPDATE devices SET is_active=0, updated_at=datetime('now') WHERE ip_address=?", (ip,)
        )
        conn.execute("DELETE FROM infra_nodes WHERE ip_address=?", (ip,))
        try:
            _sync_nodos_gl_from_devices(conn)
        except Exception:
            pass
        conn.commit()
    _clean_redis_for_ip(ip)
    return {"success": True, "message": f"{ip} quitado del monitoreo"}


@router.post("/api/router-devices/by-ip/{ip}/activate")
async def activate_device(
    ip: str,
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Reactiva el monitoreo (is_active=1). El poller lo retoma en el siguiente tick."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM devices WHERE ip_address=?", (ip,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
        conn.execute(
            "UPDATE devices SET is_active=1, updated_at=datetime('now') WHERE ip_address=?", (ip,)
        )
        try:
            _sync_nodos_gl_from_devices(conn)
        except Exception:
            pass
        conn.commit()
    return {"success": True, "message": f"{ip} agregado al monitoreo"}
