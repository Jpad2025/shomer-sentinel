"""
Credenciales globales Tracker (tabla network_credentials en inventory.db).
Sin FastAPI.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from app.api.inventory_db_schema import ensure_network_credentials


def fetch_network_credentials(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """Primera fila como dict UI, o None si no hay filas."""
    ensure_network_credentials(conn)
    cur = conn.execute(
        "SELECT id, user, password, domain, snmp_community FROM network_credentials ORDER BY id LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "user": row["user"] or "",
        "password": row["password"] or "",
        "domain": row["domain"] or "",
        "snmp_community": row["snmp_community"] or "",
    }


def save_network_credentials(conn: sqlite3.Connection, payload: Dict[str, Any]) -> None:
    """Insert o update única fila (user, password, domain, snmp).

    Si password viene vacío o '***' (panel no reenvía el secreto), se conserva
    la contraseña ya guardada en BD.
    """
    ensure_network_credentials(conn)
    user = (payload.get("user") or "").strip()
    password = (payload.get("password") or "").strip()
    domain = (payload.get("domain") or "").strip()
    snmp_community = (payload.get("snmp_community") or "").strip()
    cur = conn.execute(
        "SELECT id, password FROM network_credentials ORDER BY id LIMIT 1"
    )
    row = cur.fetchone()
    if row:
        keep_pass = (not password or password == "***")
        password_val = row["password"] if keep_pass else password
        conn.execute(
            "UPDATE network_credentials SET user=?, password=?, domain=?, snmp_community=? WHERE id=?",
            (user, password_val, domain, snmp_community, row["id"]),
        )
    else:
        if password == "***":
            password = ""
        conn.execute(
            "INSERT INTO network_credentials (user, password, domain, snmp_community) VALUES (?, ?, ?, ?)",
            (user, password, domain, snmp_community),
        )
    conn.commit()
