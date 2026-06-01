"""Guardian — discovery, promoción a nodos, eliminación."""
import json
import os

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_db, get_redis
from app.api.shomer_guardian_lib import (
    ALLOWED_IP_PATTERN,
    FAILURES_KEY_PREFIX,
    NODE_DATA_PREFIX,
    log_event,
)
from app.backend.db import NODOS_GL_PATH

router = APIRouter(tags=["Shomer Guardian"])


@router.get("/discovered")
async def get_discovered(user=Depends(get_current_user)):
    """
    Lista dispositivos descubiertos que aún no han sido promovidos a infra_nodes.
    Muestra todos (sin límite de tiempo) para que el operador decida agregar o descartar.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT ip_address, mac_address, vendor, hostname, status, inferred_type, last_seen
                FROM discovered_devices
                WHERE status = 'online'
                  AND ip_address NOT IN (SELECT ip_address FROM infra_nodes)
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
    Promueve un dispositivo descubierto a infra_nodes (status='unknown') si no existe.
    Luego lo elimina de discovered_devices y agrega la IP a nodos_gl.json para el monitor.
    """
    ip = ip.strip()
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR IGNORE INTO infra_nodes (ip_address, status, last_heartbeat, latency_ms)
                VALUES (?, 'unknown', datetime('now'), NULL)
                """,
                (ip,),
            )
            cur.execute(
                "DELETE FROM discovered_devices WHERE ip_address = ?",
                (ip,),
            )
            conn.commit()

        os.makedirs(os.path.dirname(NODOS_GL_PATH), exist_ok=True)
        try:
            if os.path.exists(NODOS_GL_PATH):
                with open(NODOS_GL_PATH, "r", encoding="utf-8") as f:
                    nodos = json.load(f)
            else:
                nodos = []
            ips_existentes = {n.get("ip") for n in nodos if isinstance(n, dict)}
            if ip not in ips_existentes:
                nodos.append({"ip": ip, "nombre": ip, "activo": True})
                with open(NODOS_GL_PATH, "w", encoding="utf-8") as f:
                    json.dump(nodos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[PROMOTE] Error actualizando nodos_gl.json: {e}")

        return {"success": True, "message": f"{ip} promovido a infra_nodes"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/nodes/{ip}")
async def delete_node(ip: str):
    """Elimina un nodo de infra_nodes y de nodos_gl.json (quitar del monitoreo)."""
    ip = ip.strip()
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM infra_nodes WHERE ip_address = ?", (ip,))
            conn.commit()

        if os.path.exists(NODOS_GL_PATH):
            try:
                with open(NODOS_GL_PATH, "r", encoding="utf-8") as f:
                    nodos = json.load(f)
                nodos = [n for n in nodos if isinstance(n, dict) and n.get("ip") != ip]
                with open(NODOS_GL_PATH, "w", encoding="utf-8") as f:
                    json.dump(nodos, f, ensure_ascii=False, indent=2)
                if not nodos:
                    try:
                        with get_db() as conn2:
                            conn2.execute("DELETE FROM infra_nodes")
                            conn2.commit()
                        print("[DELETE_NODE] nodos_gl.json vacío — infra_nodes limpiado")
                    except Exception as e2:
                        print(f"[DELETE_NODE] Error limpiando infra_nodes: {e2}")
            except Exception as e:
                print(f"[DELETE_NODE] Error actualizando nodos_gl.json: {e}")

        r = get_redis()
        if r is not None:
            try:
                r.delete(f"status:{ip}")
                r.delete(f"{FAILURES_KEY_PREFIX}{ip}")
                r.delete(f"{NODE_DATA_PREFIX}{ip}")
            except Exception:
                pass

        log_event(r, "warning", "GUARDIAN", f"Nodo {ip} eliminado del monitoreo")
        return {"success": True, "message": f"{ip} eliminado del monitoreo"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/discovered/{ip}")
async def delete_discovered(ip: str):
    """Elimina una IP de discovered_devices. Requiere rol admin (panel)."""
    ip = ip.strip()
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
