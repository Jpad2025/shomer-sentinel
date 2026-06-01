#!/usr/bin/env python3
"""
Actualiza la tabla devices con nombres profesionales para USB SHOMER.
Las IPs se leen de system_state (base de datos), nunca hardcodeadas.

DEV — ejecutar manualmente si se necesita etiquetar dispositivos conocidos.
Uso: python3 update_professional_names.py
"""
import os
import json
import sqlite3
import sys
from datetime import datetime

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.backend.db import connect, DB_PATH


def _get_config(key: str, default=None):
    """Lee un valor de system_state en network_monitor.db."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        row = conn.execute(
            "SELECT value FROM system_state WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                return row[0]
    except Exception:
        pass
    return default


def main():
    server_ip  = _get_config("base.server_ip", "")
    gateway_ip = _get_config("base.gateway", "")

    if not server_ip and not gateway_ip:
        print("No hay IPs configuradas en system_state (base.server_ip, base.gateway).")
        print("Ejecuta primero el wizard de setup o configura la red desde el panel.")
        return 1

    names = {}
    if server_ip:
        names[server_ip] = "USB SHOMER (Server)"
    if gateway_ip:
        names[gateway_ip] = "Gateway principal"

    conn = connect(timeout=30)
    cur = conn.cursor()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    for ip, name in names.items():
        cur.execute(
            "UPDATE devices SET name = ?, updated_at = ? WHERE ip_address = ?",
            (name, now, ip)
        )
        if cur.rowcount:
            print(f"Actualizado: {ip} -> {name}")
        else:
            cur.execute(
                "INSERT INTO devices (name, device_type, ip_address, is_active, created_at, updated_at) "
                "VALUES (?, 'server', ?, 1, ?, ?)",
                (name, ip, now, now),
            )
            print(f"Creado: {ip} -> {name}")
    conn.commit()
    conn.close()
    print("Nombres profesionales aplicados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
