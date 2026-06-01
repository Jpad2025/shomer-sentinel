#!/usr/bin/env python3
"""
Migración: añade columnas faltantes a la tabla devices sin borrar datos.
Resuelve: no such column: status (y otras usadas por la API).
BD desde app.backend.db (/storage/db/).
"""
import os
import sqlite3
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend.db import DB_PATH, connect

# Columnas que la API/rutas esperan y que pueden no existir en el schema original
COLUMNS_TO_ADD = [
    ("status", "TEXT"),
    ("created_at", "TEXT"),
    ("updated_at", "TEXT"),
    ("ssh_user", "TEXT"),
    ("ssh_password", "TEXT"),
    ("ssh_port", "INTEGER"),
    ("snmp_community", "TEXT"),
    ("reboot_method", "TEXT"),
    ("reboot_command", "TEXT"),
    ("last_reboot_at", "TEXT"),
]


def column_exists(conn, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    for row in cur.fetchall():
        if row[1] == column:
            return True
    return False


def main():
    if not os.path.isfile(DB_PATH):
        print("BD no encontrada:", DB_PATH, file=sys.stderr)
        return 1
    conn = connect()
    added_devices = []
    for col_name, col_type in COLUMNS_TO_ADD:
        if column_exists(conn, "devices", col_name):
            continue
        try:
            conn.execute("ALTER TABLE devices ADD COLUMN %s %s" % (col_name, col_type))
            conn.commit()
            added_devices.append(col_name)
        except sqlite3.OperationalError as e:
            print("devices.%s: %s" % (col_name, e), file=sys.stderr)
    # events_log: la API usa severity y created_at; el schema original tiene timestamp
    for col_name, col_type in [("severity", "TEXT"), ("created_at", "TEXT")]:
        if not column_exists(conn, "events_log", col_name):
            try:
                conn.execute("ALTER TABLE events_log ADD COLUMN %s %s" % (col_name, col_type))
                conn.commit()
                added_devices.append("events_log." + col_name)
            except sqlite3.OperationalError as e:
                print("events_log.%s: %s" % (col_name, e), file=sys.stderr)
    conn.close()
    if added_devices:
        print("Columnas añadidas:", ", ".join(added_devices))
    else:
        print("Tablas ya tenían todas las columnas necesarias.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
