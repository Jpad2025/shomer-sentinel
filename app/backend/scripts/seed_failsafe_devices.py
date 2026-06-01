#!/usr/bin/env python3
"""
Script de seed DEV — NO usar en producción.
Configura la BD con dispositivos del entorno de desarrollo.
En producción: registrar dispositivos desde el panel o via INSERT directo con credenciales del cliente.
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

ROUTER_IP = os.environ.get("SEED_ROUTER_IP", "")
ROUTER_USER = os.environ.get("SEED_ROUTER_USER", "root")
ROUTER_PASSWORD = os.environ.get("SEED_ROUTER_PASSWORD", "")
LAPTOP_IP = os.environ.get("SEED_LAPTOP_IP", "")
MACBOOK_IP = os.environ.get("SEED_MACBOOK_IP", "")


def main():
    conn = connect(timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Router GL: debe quedar siempre como id=5 (API y monitor usan GL_ROUTER_DEVICE_ID=5)
    cur.execute("SELECT id FROM devices WHERE id = 5")
    row5 = cur.fetchone()
    cur.execute("SELECT id FROM devices WHERE ip_address = ?", (ROUTER_IP,))
    row_ip = cur.fetchone()
    if row5:
        if row_ip and row_ip["id"] != 5:
            cur.execute("UPDATE devices SET ip_address = ? WHERE id = ?", (ROUTER_IP + ".bak", row_ip["id"]))
        cur.execute(
            """UPDATE devices SET name = ?, device_type = 'router', ip_address = ?, ssh_user = ?, ssh_password = ?, is_active = 1, updated_at = ?
               WHERE id = 5""",
            ("GL-MT6000", ROUTER_IP, ROUTER_USER, ROUTER_PASSWORD, now),
        )
        print(f"Router {ROUTER_IP} configurado (id=5)")
    else:
        if row_ip:
            cur.execute("UPDATE devices SET ip_address = ? WHERE id = ?", (ROUTER_IP + ".bak", row_ip["id"]))
        cur.execute(
            """INSERT INTO devices (id, name, device_type, ip_address, is_active, ssh_user, ssh_password, created_at, updated_at)
               VALUES (5, ?, 'router', ?, 1, ?, ?, ?, ?)""",
            ("GL-MT6000", ROUTER_IP, ROUTER_USER, ROUTER_PASSWORD, now, now),
        )
        cur.execute("INSERT INTO device_status (device_id, status, last_check) VALUES (5, 'unknown', ?)", (now,))
        print(f"Router {ROUTER_IP} creado (id=5)")

    # Laptop
    cur.execute("SELECT id FROM devices WHERE ip_address = ?", (LAPTOP_IP,))
    r = cur.fetchone()
    if r:
        cur.execute(
            "UPDATE devices SET name = ?, is_active = 1, updated_at = ? WHERE id = ?",
            ("Laptop", now, r["id"]),
        )
        print(f"Laptop {LAPTOP_IP} actualizado (id={r['id']})")
    else:
        cur.execute(
            """INSERT INTO devices (name, device_type, ip_address, is_active, created_at, updated_at)
               VALUES (?, 'workstation', ?, 1, ?, ?)""",
            ("Laptop", LAPTOP_IP, now, now),
        )
        lid = cur.lastrowid
        cur.execute(
            "INSERT INTO device_status (device_id, status, last_check) VALUES (?, 'unknown', ?)",
            (lid, now),
        )
        print(f"Laptop {LAPTOP_IP} creado (id={lid})")

    # MacBook
    cur.execute("SELECT id FROM devices WHERE ip_address = ?", (MACBOOK_IP,))
    r = cur.fetchone()
    if r:
        cur.execute(
            "UPDATE devices SET name = ?, is_active = 1, updated_at = ? WHERE id = ?",
            ("MacBook", now, r["id"]),
        )
        print(f"MacBook {MACBOOK_IP} actualizado (id={r['id']})")
    else:
        cur.execute(
            """INSERT INTO devices (name, device_type, ip_address, is_active, created_at, updated_at)
               VALUES (?, 'workstation', ?, 1, ?, ?)""",
            ("MacBook", MACBOOK_IP, now, now),
        )
        mid = cur.lastrowid
        cur.execute(
            "INSERT INTO device_status (device_id, status, last_check) VALUES (?, 'unknown', ?)",
            (mid, now),
        )
        print(f"MacBook {MACBOOK_IP} creado (id={mid})")

    conn.commit()
    conn.close()
    print("Seed completado. Router, Laptop y MacBook listos para monitoreo y reportes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
