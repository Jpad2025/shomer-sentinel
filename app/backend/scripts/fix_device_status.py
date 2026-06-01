#!/usr/bin/env python3
"""
Migración: añade uptime_percentage (y response_time si falta) a device_status si no existen.
BD desde app.backend.db (/storage/db/).
"""
import os
import sqlite3
import sys
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend.db import connect


def column_exists(conn, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    return any(row[1] == column for row in cur.fetchall())


def main():
    try:
        conn = connect(timeout=30)
        added = []
        for col, typ in [("response_time", "REAL"), ("uptime_percentage", "REAL")]:
            if not column_exists(conn, "device_status", col):
                conn.execute("ALTER TABLE device_status ADD COLUMN %s %s" % (col, typ))
                conn.commit()
                added.append(col)
        conn.close()
        if added:
            print("Columnas añadidas a device_status:", ", ".join(added))
        else:
            print("device_status ya tenía las columnas necesarias.")
        return 0
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
