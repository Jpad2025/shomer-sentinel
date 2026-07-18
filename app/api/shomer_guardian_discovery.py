"""Guardian — discovery, promoción a nodos, eliminación."""
import json
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_api import get_current_user, require_admin
from app.api.shomer_common import get_db, get_redis
from app.api.shomer_guardian_lib import (
    ALLOWED_IP_PATTERN,
    FAILURES_KEY_PREFIX,
    LAST_REBOOT_ATTEMPT_KEY_PREFIX,
    LAST_REBOOT_KEY_PREFIX,
    NODE_DATA_PREFIX,
    NODE_MAINTENANCE_PREFIX,
    log_event,
)
from app.backend.db import NODOS_GL_PATH

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Shomer Guardian"])

_INFERRED_TO_DEVICE = {
    "access_point": "access_point",
    "ap": "access_point",
    "wifi": "access_point",
    "router": "router",
    "gateway": "gateway",
    "switch": "switch",
    "firewall": "firewall",
}


def _map_device_type(inferred: Optional[str]) -> str:
    key = (inferred or "").strip().lower()
    return _INFERRED_TO_DEVICE.get(key, "access_point")


def _sync_nodos_gl_from_devices(conn) -> None:
    """Espejo legacy: nodos_gl.json = devices activos (poller real usa devices)."""
    rows = conn.execute(
        "SELECT ip_address, name FROM devices WHERE is_active=1 ORDER BY ip_address"
    ).fetchall()
    nodos = [
        {
            "ip": r["ip_address"],
            "nombre": (r["name"] or r["ip_address"]).strip(),
            "activo": True,
        }
        for r in rows
        if r["ip_address"]
    ]
    os.makedirs(os.path.dirname(NODOS_GL_PATH) or ".", exist_ok=True)
    with open(NODOS_GL_PATH, "w", encoding="utf-8") as f:
        json.dump(nodos, f, ensure_ascii=False, indent=2)


def _clean_redis_for_ip(ip: str) -> None:
    r = get_redis()
    if r is None:
        return
    for key in (
        f"status:{ip}",
        f"{FAILURES_KEY_PREFIX}{ip}",
        f"{LAST_REBOOT_KEY_PREFIX}{ip}",
        f"{LAST_REBOOT_ATTEMPT_KEY_PREFIX}{ip}",
        f"{NODE_MAINTENANCE_PREFIX}{ip}",
        f"{NODE_DATA_PREFIX}{ip}",
        f"degraded_notified:{ip}",
        f"degraded_streak:{ip}",
        f"offline_streak:{ip}",
    ):
        try:
            r.delete(key)
        except Exception:
            pass


@router.get("/discovered")
async def get_discovered(user=Depends(get_current_user)):
    """
    Lista dispositivos descubiertos aún no en devices activos (lista real del poller).
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT ip_address, mac_address, vendor, hostname, status, inferred_type, last_seen
                FROM discovered_devices
                WHERE status = 'online'
                  AND ip_address NOT IN (
                      SELECT ip_address FROM devices WHERE is_active = 1
                  )
                ORDER BY last_seen DESC
                """,
            )
            rows = cur.fetchall()
        devices = [
            {
                "ip": row["ip_address"],
                "mac": row["mac_address"],
                "vendor": row["vendor"] or "",
                "hostname": row["hostname"] or "",
                "status": row["status"] or "unknown",
                "inferred_type": row["inferred_type"] or "unknown",
                "last_seen": row["last_seen"] or "",
            }
            for row in rows
        ]
        return {"success": True, "count": len(devices), "devices": devices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/promote/{ip}")
async def promote_device(ip: str, user=Depends(get_current_user)):
    """
    Promueve un descubierto a la tabla devices (poller) con reboot_method=ssh.
    También espeja infra_nodes + nodos_gl.json. No pisa credenciales existentes.
    """
    ip = ip.strip()
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")
    try:
        with get_db() as conn:
            cur = conn.cursor()
            disc = cur.execute(
                "SELECT hostname, inferred_type FROM discovered_devices WHERE ip_address = ?",
                (ip,),
            ).fetchone()
            hostname = ""
            inferred = ""
            if disc:
                hostname = (disc["hostname"] or "").strip()
                inferred = (disc["inferred_type"] or "").strip()
            name = hostname or ip
            dtype = _map_device_type(inferred)

            existing = cur.execute(
                "SELECT id, ssh_password FROM devices WHERE ip_address = ?", (ip,)
            ).fetchone()
            if existing:
                cur.execute(
                    "UPDATE devices SET is_active=1, updated_at=datetime('now') "
                    "WHERE ip_address = ?",
                    (ip,),
                )
            else:
                # Ópera / producto: reinicio por SSH (decisión sitio). Sin inventar pass.
                cur.execute(
                    """
                    INSERT INTO devices (
                        name, ip_address, device_type, ssh_user, ssh_password, ssh_port,
                        location, is_active, reboot_method, created_at, updated_at
                    ) VALUES (?, ?, ?, '', '', 22, '', 1, 'ssh', datetime('now'), datetime('now'))
                    """,
                    (name, ip, dtype),
                )

            cur.execute(
                """
                INSERT OR IGNORE INTO infra_nodes (ip_address, status, last_heartbeat, latency_ms)
                VALUES (?, 'unknown', datetime('now'), NULL)
                """,
                (ip,),
            )
            cur.execute("DELETE FROM discovered_devices WHERE ip_address = ?", (ip,))
            try:
                _sync_nodos_gl_from_devices(conn)
            except Exception as e:
                logger.warning("[PROMOTE] nodos_gl sync: %s", e)
            conn.commit()

        return {
            "success": True,
            "message": f"{ip} agregado a devices (monitoreo) — reboot SSH",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/nodes/{ip}")
async def delete_node(ip: str, _admin: Dict[str, Any] = Depends(require_admin)):
    """
    Quita IP del monitoreo: is_active=0 en devices + limpia espejo/Redis.
    Misma semántica que POST /api/router-devices/by-ip/{ip}/deactivate.
    No borra el catálogo ni vacía infra_nodes completo.
    """
    ip = ip.strip()
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM devices WHERE ip_address = ?", (ip,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE devices SET is_active=0, updated_at=datetime('now') "
                    "WHERE ip_address = ?",
                    (ip,),
                )
            conn.execute("DELETE FROM infra_nodes WHERE ip_address = ?", (ip,))
            try:
                _sync_nodos_gl_from_devices(conn)
            except Exception as e:
                logger.warning("[DELETE_NODE] nodos_gl sync: %s", e)
            conn.commit()

        _clean_redis_for_ip(ip)
        r = get_redis()
        log_event(r, "warning", "GUARDIAN", f"Nodo {ip} eliminado del monitoreo")
        return {"success": True, "message": f"{ip} quitado del monitoreo"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/discovered/{ip}")
async def delete_discovered(
    ip: str,
    _user: Dict[str, Any] = Depends(get_current_user),
):
    """Elimina una IP de discovered_devices."""
    ip = ip.strip()
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM discovered_devices WHERE ip_address = ?",
                (ip,),
            )
            conn.commit()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
