from fastapi import APIRouter, HTTPException, Response, Query
from fastapi.responses import JSONResponse
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

from db import get_connection

router = APIRouter(prefix="/api/devices", tags=["devices"])

# Sin caché: el cliente siempre recibe el estado más reciente de la BD
NO_CACHE_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}

# TTL del monitor (device_status) y TTL del discovery (más amplio)
DS_TTL_SECONDS = 120
DISCOVERY_TTL_SECONDS = 900  # 15 min para considerar "online" si discovery lo vio recientemente

def cutoffs_now():
    ds_cutoff = (datetime.utcnow() - timedelta(seconds=DS_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S.%f")
    dd_cutoff = (datetime.utcnow() - timedelta(seconds=DISCOVERY_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S.%f")
    return dd_cutoff, ds_cutoff

# Prioridad a discovery ONLINE reciente:
# 1) dd.last_seen reciente y dd.status='online' => online
# 2) ds.last_check reciente => ds.status
# 3) else => offline
DERIVED_SQL = """
CASE
  WHEN dd.last_seen IS NOT NULL AND dd.last_seen >= ? AND IFNULL(dd.status,'unknown')='online' THEN 'online'
  WHEN ds.last_check IS NOT NULL AND ds.last_check >= ? THEN IFNULL(ds.status,'unknown')
  ELSE 'offline'
END
"""

def filters_sql(dev_type: Optional[str], q: Optional[str]) -> Tuple[str, List]:
    clauses = ["d.is_active = 1"]; params: List = []
    if dev_type:
        clauses.append("d.device_type = ?"); params.append(dev_type)
    if q:
        like = f"%{q}%"
        clauses.append("(d.name LIKE ? OR d.ip_address LIKE ? OR d.mac_address LIKE ? OR d.location LIKE ?)")
        params.extend([like, like, like, like])
    return " AND ".join(clauses), params

def _row_to_device(r) -> dict:
    """Convierte una fila (sqlite3.Row) a diccionario plano para JSON."""
    d = dict(r)  # sqlite3.Row es convertible a dict
    return {
        "id": d.get("id"),
        "name": d.get("name"),
        "type": d.get("device_type"),
        "ip_address": d.get("ip_address"),
        "mac_address": d.get("mac_address"),
        "brand": d.get("brand"),
        "model": d.get("model"),
        "location": d.get("location"),
        "is_active": bool(d.get("is_active")),
        "status": d.get("status") or "unknown",
        "last_check": d.get("last_check"),
        "response_time": d.get("response_time"),
    }


@router.get("/")
async def get_devices(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                      status: Optional[str] = Query(None), type: Optional[str] = Query(None),
                      q: Optional[str] = Query(None)):
    try:
        where_base, params = filters_sql(type, q)
        count_sql = f"""
        WITH last_ds AS (
          SELECT s.* FROM device_status s
          JOIN (SELECT device_id, MAX(last_check) AS last_check FROM device_status GROUP BY device_id) m
            ON m.device_id = s.device_id AND m.last_check = s.last_check
        ),
        last_dd AS (
          SELECT dd.* FROM discovered_devices dd
          JOIN (SELECT ip_address, MAX(last_seen) AS last_seen FROM discovered_devices GROUP BY ip_address) m
            ON m.ip_address = dd.ip_address AND m.last_seen = dd.last_seen
        )
        SELECT COUNT(*) AS total
        FROM devices d
        LEFT JOIN last_ds ds ON ds.device_id = d.id
        LEFT JOIN last_dd dd ON dd.ip_address = d.ip_address
        WHERE {where_base}
        """
        params_count = list(params)
        if status:
            count_sql += " AND COALESCE(TRIM(d.status), 'unknown') = ?"
            params_count.append(status)
        data_sql = f"""
        WITH last_ds AS (
          SELECT s.* FROM device_status s
          JOIN (SELECT device_id, MAX(last_check) AS last_check FROM device_status GROUP BY device_id) m
            ON m.device_id = s.device_id AND m.last_check = s.last_check
        ),
        last_dd AS (
          SELECT dd.* FROM discovered_devices dd
          JOIN (SELECT ip_address, MAX(last_seen) AS last_seen FROM discovered_devices GROUP BY ip_address) m
            ON m.ip_address = dd.ip_address AND m.last_seen = dd.last_seen
        )
        SELECT
          d.id, d.name, d.device_type, d.ip_address, d.mac_address, d.brand, d.model, d.location, d.is_active,
          COALESCE(TRIM(d.status), 'unknown') AS status,
          ds.last_check, ds.response_time
        FROM devices d
        LEFT JOIN last_ds ds ON ds.device_id = d.id
        LEFT JOIN last_dd dd ON dd.ip_address = d.ip_address
        WHERE {where_base}
        """
        params_data = list(params)
        if status:
            data_sql += " AND COALESCE(TRIM(d.status), 'unknown') = ?"
            params_data.append(status)
        data_sql += " ORDER BY d.name LIMIT ? OFFSET ?"
        params_data += [limit, offset]

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(count_sql, params_count)
            total_row = cur.fetchone()
            total = int(total_row["total"]) if total_row else 0
            cur.execute(data_sql, params_data)
            rows = cur.fetchall()
        devices = [_row_to_device(r) for r in rows]
        next_offset = offset + limit if (offset + limit) < total else None
        prev_offset = offset - limit if (offset - limit) >= 0 else None
        payload = {"success": True, "count": len(devices), "total": total, "limit": limit,
                "offset": offset, "next_offset": next_offset, "prev_offset": prev_offset,
                "devices": devices}
        return JSONResponse(content=payload, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.head("/")
async def head_devices():
    return Response(status_code=200)

@router.get("/stats")
async def get_devices_stats():
    try:
        dd_cutoff, ds_cutoff = cutoffs_now()
        sql = f"""
        WITH last_ds AS (
          SELECT s.* FROM device_status s
          JOIN (SELECT device_id, MAX(last_check) AS last_check FROM device_status GROUP BY device_id) m
            ON m.device_id = s.device_id AND m.last_check = s.last_check
        ),
        last_dd AS (
          SELECT dd.* FROM discovered_devices dd
          JOIN (SELECT ip_address, MAX(last_seen) AS last_seen FROM discovered_devices GROUP BY ip_address) m
            ON m.ip_address = dd.ip_address AND m.last_seen = dd.last_seen
        )
        SELECT
          SUM(CASE WHEN ({DERIVED_SQL})='online'  THEN 1 ELSE 0 END) AS online,
          SUM(CASE WHEN ({DERIVED_SQL})='offline' THEN 1 ELSE 0 END) AS offline,
          SUM(CASE WHEN ({DERIVED_SQL})='warning' THEN 1 ELSE 0 END) AS warning,
          SUM(CASE WHEN ({DERIVED_SQL})='unknown' THEN 1 ELSE 0 END) AS unknown,
          COUNT(*) AS total
        FROM devices d
        LEFT JOIN last_ds ds ON ds.device_id = d.id
        LEFT JOIN last_dd dd ON dd.ip_address = d.ip_address
        WHERE d.is_active = 1
        """
        params = [dd_cutoff, ds_cutoff] * 4
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            r = cur.fetchone()
        row_dict = dict(r) if r else {}
        return {
            "success": True,
            "online": row_dict.get("online") or 0,
            "offline": row_dict.get("offline") or 0,
            "warning": row_dict.get("warning") or 0,
            "unknown": row_dict.get("unknown") or 0,
            "total": row_dict.get("total") or 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{device_id}")
async def get_device(device_id: int):
    try:
        dd_cutoff, ds_cutoff = cutoffs_now()
        sql = f"""
        WITH last_ds AS (
          SELECT s.* FROM device_status s
          JOIN (SELECT device_id, MAX(last_check) AS last_check FROM device_status GROUP BY device_id) m
            ON m.device_id = s.device_id AND m.last_check = s.last_check
        ),
        last_dd AS (
          SELECT dd.* FROM discovered_devices dd
          JOIN (SELECT ip_address, MAX(last_seen) AS last_seen FROM discovered_devices GROUP BY ip_address) m
            ON m.ip_address = dd.ip_address AND m.last_seen = dd.last_seen
        )
        SELECT
          d.id, d.name, d.device_type, d.ip_address, d.mac_address, d.brand, d.model, d.location, d.is_active,
          {DERIVED_SQL} AS status,
          ds.last_check, ds.response_time
        FROM devices d
        LEFT JOIN last_ds ds ON ds.device_id = d.id
        LEFT JOIN last_dd dd ON dd.ip_address = d.ip_address
        WHERE d.id = ?
        """
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, [dd_cutoff, ds_cutoff, device_id])
            r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
        device = _row_to_device(r)
        return {"success": True, "device": device}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def create_device(
    name: str = Query(..., description="Nombre del dispositivo"),
    device_type: str = Query("router", description="Tipo: router, access_point, switch"),
    ip_address: str = Query(..., description="Dirección IP"),
    mac_address: Optional[str] = Query(None, description="Dirección MAC"),
    brand: Optional[str] = Query(None, description="Marca del dispositivo"),
    model: Optional[str] = Query(None, description="Modelo del dispositivo"),
    location: Optional[str] = Query(None, description="Ubicación"),
    ssh_user: Optional[str] = Query(None, description="Usuario SSH"),
    ssh_password: Optional[str] = Query(None, description="Contraseña SSH"),
    ssh_port: int = Query(22, description="Puerto SSH"),
    snmp_community: Optional[str] = Query(None, description="Community SNMP"),
    reboot_method: str = Query("ssh", description="Método de reboot: ssh, http, snmp"),
    reboot_command: str = Query("reboot", description="Comando de reboot")
):
    """
    POST /api/devices/ - Crear nuevo dispositivo
    
    Ejemplo de uso:
    curl -X POST "http://192.168.1.205:8000/api/devices/?name=GL-MT6000-Piloto-01&device_type=router&ip_address=192.168.1.210&mac_address=94:83:C4:C4:1A:DF&brand=GL.iNet&model=GL-MT6000&location=Oficina-Piloto&ssh_user=root&ssh_password=TuContraseña"
    """
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM devices WHERE ip_address = ?", (ip_address,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail=f"Ya existe un dispositivo con IP {ip_address}")
            cur.execute("""
                INSERT INTO devices (
                    name, device_type, ip_address, mac_address, 
                    brand, model, location, 
                    ssh_user, ssh_password, ssh_port, 
                    snmp_community, reboot_method, reboot_command,
                    is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
            """, (
                name, device_type, ip_address, mac_address,
                brand, model, location,
                ssh_user, ssh_password, ssh_port,
                snmp_community, reboot_method, reboot_command
            ))
            device_id = cur.lastrowid
            cur.execute("""
                INSERT INTO events_log (device_id, event_type, description, severity, created_at)
                VALUES (?, 'created', 'Dispositivo creado exitosamente', 'info', datetime('now'))
            """, (device_id,))
            conn.commit()
        return {
            "success": True,
            "device_id": device_id,
            "message": "Dispositivo creado exitosamente",
            "device": {
                "id": device_id,
                "name": name,
                "ip_address": ip_address
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creando dispositivo: {str(e)}")


@router.put("/{device_id}")
async def update_device(
    device_id: int,
    name: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    ip_address: Optional[str] = Query(None),
    mac_address: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    ssh_user: Optional[str] = Query(None),
    ssh_password: Optional[str] = Query(None),
    ssh_port: Optional[int] = Query(None)
):
    """
    PUT /api/devices/{id} - Actualizar dispositivo
    """
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM devices WHERE id = ?", (device_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
            updates = []
            params = []
            if name:
                updates.append("name = ?")
                params.append(name)
            if device_type:
                updates.append("device_type = ?")
                params.append(device_type)
            if ip_address:
                updates.append("ip_address = ?")
                params.append(ip_address)
            if mac_address:
                updates.append("mac_address = ?")
                params.append(mac_address)
            if brand:
                updates.append("brand = ?")
                params.append(brand)
            if model:
                updates.append("model = ?")
                params.append(model)
            if location:
                updates.append("location = ?")
                params.append(location)
            if ssh_user:
                updates.append("ssh_user = ?")
                params.append(ssh_user)
            if ssh_password:
                updates.append("ssh_password = ?")
                params.append(ssh_password)
            if ssh_port:
                updates.append("ssh_port = ?")
                params.append(ssh_port)
            if not updates:
                raise HTTPException(status_code=400, detail="No se proporcionaron campos para actualizar")
            updates.append("updated_at = datetime('now')")
            params.append(device_id)
            cur.execute(f"UPDATE devices SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        return {
            "success": True,
            "message": "Dispositivo actualizado exitosamente"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{device_id}")
async def delete_device(device_id: int):
    """
    DELETE /api/devices/{id} - Elimina el dispositivo de la tabla devices y sus registros en device_status.
    """
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name FROM devices WHERE id = ?", (device_id,))
            device = cur.fetchone()
            if not device:
                raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
            cur.execute("DELETE FROM device_status WHERE device_id = ?", (device_id,))
            cur.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            conn.commit()
        return {
            "success": True,
            "message": f"Dispositivo '{device['name']}' eliminado del panel"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
