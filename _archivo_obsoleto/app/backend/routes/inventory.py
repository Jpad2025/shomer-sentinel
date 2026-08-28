"""
API de inventario permanente (tabla assets).
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException

from db import get_connection

router = APIRouter(prefix="/api", tags=["inventory"])

# Solo mostrar activos vistos en los últimos 30 minutos (ignorar IPs viejas)
ASSETS_LAST_SEEN_MINUTES = 30


@router.get("/assets")
async def list_assets(limit: int = 500, q: str = ""):
    """
    Lista el inventario permanente (assets): MAC, IP, hostname, vendor, first_seen, last_seen.
    Usado por inventory.html (Inventario de Huéspedes).
    """
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            # Crear tabla si no existe (compatibilidad)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac_address TEXT NOT NULL UNIQUE,
                    ip_address TEXT,
                    hostname TEXT,
                    vendor TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    source TEXT
                )
            """)
            conn.commit()
            cutoff = (datetime.utcnow() - timedelta(minutes=ASSETS_LAST_SEEN_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
            if q and q.strip():
                search = f"%{q.strip()}%"
                cur.execute(
                    """
                    SELECT id, mac_address, ip_address, hostname, vendor, first_seen, last_seen, source
                    FROM assets
                    WHERE last_seen >= ? AND (mac_address LIKE ? OR ip_address LIKE ? OR IFNULL(hostname,'') LIKE ? OR IFNULL(vendor,'') LIKE ?)
                    ORDER BY last_seen DESC
                    LIMIT ?
                    """,
                    (cutoff, search, search, search, search, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, mac_address, ip_address, hostname, vendor, first_seen, last_seen, source
                    FROM assets
                    WHERE last_seen >= ?
                    ORDER BY last_seen DESC
                    LIMIT ?
                    """,
                    (cutoff, limit),
                )
            rows = cur.fetchall()
        items = [dict(r) for r in rows]
        return {"success": True, "count": len(items), "assets": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
