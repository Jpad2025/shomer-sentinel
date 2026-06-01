"""
Snapshots históricos del inventario (inventory_snapshots + volcado de assets).
Sin FastAPI.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from app.api.inventory_db_schema import ensure_assets_table, ensure_snapshots_table


def close_and_archive_inventory(
    conn: sqlite3.Connection,
    name: str,
    created_at_iso: str,
) -> Dict[str, Any]:
    """
    Inserta snapshot con JSON de todos los assets y vacía la tabla assets.
    name y created_at_iso deben venir ya validados (no vacíos).
    """
    ensure_assets_table(conn)
    ensure_snapshots_table(conn)
    cur = conn.execute("SELECT * FROM assets ORDER BY last_audit DESC NULLS LAST, mac")
    rows = [dict(r) for r in cur.fetchall()]
    asset_count = len(rows)
    data_json = json.dumps(rows, ensure_ascii=False)
    conn.execute(
        "INSERT INTO inventory_snapshots (name, created_at, asset_count, data) VALUES (?, ?, ?, ?)",
        (name, created_at_iso, asset_count, data_json),
    )
    conn.execute("DELETE FROM assets")
    conn.commit()
    return {
        "name": name,
        "asset_count": asset_count,
        "created_at": created_at_iso,
    }


def list_snapshot_metadata(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Filas sin columna data."""
    ensure_snapshots_table(conn)
    cur = conn.execute(
        "SELECT id, name, created_at, asset_count FROM inventory_snapshots ORDER BY created_at DESC"
    )
    return [dict(r) for r in cur.fetchall()]


def load_snapshot_assets(
    conn: sqlite3.Connection,
    snapshot_id: int,
) -> Optional[Tuple[str, str, List[Dict[str, Any]]]]:
    """
    Devuelve (name, created_at, assets_list) o None si no existe el id.
    """
    ensure_snapshots_table(conn)
    cur = conn.execute(
        "SELECT name, created_at, data FROM inventory_snapshots WHERE id = ?",
        (snapshot_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    assets = json.loads(row["data"])
    if not isinstance(assets, list):
        assets = []
    return row["name"], row["created_at"], assets
