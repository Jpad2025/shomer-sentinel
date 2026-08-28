from fastapi import APIRouter, HTTPException, Body
from typing import List, Optional, Any, Dict
import json
import re
import subprocess
import sqlite3
from datetime import datetime, timedelta

from db import get_connection

# Solo mostrar dispositivos vistos en los últimos 30 minutos (ignorar IPs viejas)
DISCOVERY_LAST_SEEN_MINUTES = 30

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

CIDR_RE = re.compile(r"^(?P<ip>(?:\d{1,3}\.){3}\d{1,3})(?:/(?P<c>\d{1,2}))?$")

def norm_subnets(subnets: Optional[List[str]]) -> List[str]:
    if not subnets:
        return []
    out: List[str] = []
    for s in subnets:
        s = (s or "").strip()
        if not s:
            continue
        m = CIDR_RE.match(s)
        if not m:
            continue
        ip = m.group("ip")
        cidr = m.group("c")
        if cidr is None:
            out.append(ip)
        else:
            try:
                c = int(cidr)
                if 0 <= c <= 32:
                    out.append(f"{ip}/{c}")
            except:
                continue
    return out

@router.get("/results")
async def list_results(limit: int = 100, q: Optional[str] = None):
    cutoff = (datetime.utcnow() - timedelta(minutes=DISCOVERY_LAST_SEEN_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    params: List[Any] = [cutoff, cutoff]
    where = "WHERE dd.last_seen >= ?"
    if q:
        where += " AND (dd.ip_address LIKE ? OR IFNULL(dd.hostname,'') LIKE ? OR IFNULL(dd.vendor,'') LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    sql = f"""
        SELECT dd.*
        FROM discovered_devices dd
        JOIN (
            SELECT ip_address, MAX(last_seen) AS last_seen
            FROM discovered_devices
            WHERE last_seen >= ?
            GROUP BY ip_address
        ) m ON m.ip_address = dd.ip_address AND m.last_seen = dd.last_seen
        {where}
        ORDER BY dd.last_seen DESC
        LIMIT ?
    """
    params.append(limit)
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        try: r["open_ports"] = json.loads(r.get("open_ports") or "[]")
        except: r["open_ports"] = []
    return {"success": True, "count": len(rows), "results": rows}

@router.post("/scan")
async def scan_now(payload: Optional[Any] = Body(default=None)):
    """
    Acepta:
      - Lista directa: ["192.168.1.0/24","192.168.1.205"]
      - Objeto: { "subnets": ["192.168.1.0/24","192.168.1.205"] }
      - Vacío: autodetección de /24 locales
    """
    subnets: Optional[List[str]] = None
    if payload is None:
        subnets = None
    elif isinstance(payload, list):
        subnets = payload
    elif isinstance(payload, dict):
        v = payload.get("subnets")
        if v is None:
            subnets = None
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            subnets = v
        else:
            raise HTTPException(status_code=422, detail="El campo 'subnets' debe ser lista de strings")
    else:
        raise HTTPException(status_code=422, detail="Body inválido: lista o {subnets: [...]}")

    nets = norm_subnets(subnets) if subnets else []
    cmd = ["/opt/network_monitor/venv/bin/python", "/opt/network_monitor/app/scripts/discovery.py"]
    if nets:
        cmd.extend(nets)

    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=600)
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or "Error interno en discovery.py"
            raise HTTPException(status_code=500, detail=detail)
        data = json.loads(proc.stdout or "{}")
        return {"success": True, "subnets": data.get("subnets"), "count": data.get("count"), "results": data.get("results")}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="El escaneo tardó demasiado")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/promote")
async def promote_device(payload: Dict[str, Any] = Body(...)):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Body JSON inválido")
    did = payload.get("id")
    ip = payload.get("ip") or payload.get("ip_address")
    name = payload.get("name") or "Sin nombre"
    device_type = payload.get("device_type") or "router"
    location = payload.get("location") or ""
    brand = payload.get("brand") or ""
    model = payload.get("model") or ""
    is_guest = 1 if payload.get("is_guest") else 0
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            row = None
            if did:
                cur.execute("SELECT * FROM discovered_devices WHERE id=?", (did,))
                row = cur.fetchone()
            elif ip:
                cur.execute("SELECT * FROM discovered_devices WHERE ip_address=?", (ip,))
                row = cur.fetchone()
            if row:
                ip = ip or row["ip_address"]
                if not brand:
                    brand = row["vendor"] or ""
                if not device_type:
                    device_type = row["inferred_type"] or "router"
            if not ip:
                raise HTTPException(status_code=400, detail="Falta ip/ip_address en payload o en discovered")
            cur.execute("SELECT id FROM devices WHERE ip_address=?", (ip,))
            ex = cur.fetchone()
            if ex:
                return {"success": True, "message": "Ya existía en devices", "device_id": ex["id"]}
            mac = (dict(row).get("mac_address") if row else None) or payload.get("mac_address") or payload.get("mac") or None
            cur.execute("""
                INSERT INTO devices (name, device_type, ip_address, mac_address, brand, model, location, is_active, is_guest)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (name, device_type, ip, mac, brand, model, location, is_guest))
            device_id = cur.lastrowid
            now_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
            cur.execute("""
                INSERT INTO device_status (device_id, status, last_check)
                VALUES (?, ?, ?)
            """, (device_id, "unknown", now_ts))
            cur.execute("DELETE FROM discovered_devices WHERE ip_address=?", (ip,))
            conn.commit()
            return {"success": True, "message": "Promovido a dispositivo gestionado", "device_id": device_id}
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail=f"Conflicto: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
