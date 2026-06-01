"""
Consultas y mutaciones sobre la tabla assets (inventory.db).
Sin FastAPI. Conexión la abre el llamador (p. ej. get_connection_inventory).
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from app.api.inventory_asset_model import normalize_asset_for_frontend
from app.api.inventory_db_schema import ensure_assets_table, ensure_network_credentials


def fetch_all_assets_normalized(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    ensure_network_credentials(conn)
    ensure_assets_table(conn)
    cur = conn.execute("SELECT * FROM assets ORDER BY last_audit DESC NULLS LAST, mac")
    return [normalize_asset_for_frontend(dict(r)) for r in cur.fetchall()]


def fetch_asset_by_ip_normalized(
    conn: sqlite3.Connection, ip: str
) -> Optional[Dict[str, Any]]:
    ensure_network_credentials(conn)
    ensure_assets_table(conn)
    cur = conn.execute("SELECT * FROM assets WHERE ip = ?", (ip,))
    row = cur.fetchone()
    if not row:
        return None
    return normalize_asset_for_frontend(dict(row))


def fetch_asset_by_mac_normalized(
    conn: sqlite3.Connection, mac: str
) -> Optional[Dict[str, Any]]:
    """Solo ensure_assets (misma lógica que etiqueta PDF / rutas ligeras)."""
    ensure_assets_table(conn)
    cur = conn.execute("SELECT * FROM assets WHERE mac = ?", (mac,))
    row = cur.fetchone()
    if not row:
        return None
    return normalize_asset_for_frontend(dict(row))


def delete_asset_by_mac(conn: sqlite3.Connection, mac: str) -> int:
    """DELETE; commit; devuelve rowcount."""
    ensure_network_credentials(conn)
    ensure_assets_table(conn)
    cur = conn.execute("DELETE FROM assets WHERE mac = ?", (mac,))
    conn.commit()
    return cur.rowcount
