#!/usr/bin/env python3
"""
Añade o actualiza en devices las IPs 192.168.1.20 (Laptop Prueba) y 192.168.1.27 (MacBook Prueba)
para que el panel y el monitor los incluyan. BD desde app.backend.db (/storage/db/).
"""
import os
import sqlite3
import sys
from datetime import datetime
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend.db import connect

DEVICES = [
    ("192.168.1.20", "Laptop Prueba"),
    ("192.168.1.27", "MacBook Prueba"),
]


def main():
    conn = connect(timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    for ip, name in DEVICES:
        cur.execute("SELECT id FROM devices WHERE ip_address = ?", (ip,))
        r = cur.fetchone()
        if r:
            cur.execute(
                "UPDATE devices SET name = ?, is_active = 1, updated_at = ? WHERE id = ?",
                (name, now, r["id"]),
            )
            print(f"Actualizado: {ip} -> {name} (id={r['id']})")
        else:
            cur.execute(
                """INSERT INTO devices (name, device_type, ip_address, is_active, created_at, updated_at)
                   VALUES (?, 'workstation', ?, 1, ?, ?)""",
                (name, ip, now, now),
            )
            did = cur.lastrowid
            cur.execute(
                "INSERT INTO device_status (device_id, status, last_check) VALUES (?, 'unknown', ?)",
                (did, now),
            )
            print(f"Creado: {ip} -> {name} (id={did})")

    conn.commit()
    conn.close()
    print("Listo. Laptop Prueba y MacBook Prueba en panel y en bucle de ping del monitor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
