#!/usr/bin/env python3
"""
Migración urgente: añade la columna status a la tabla devices si no existe.
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

def main():
    conn = connect()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(devices)")
    cols = [row[1] for row in cur.fetchall()]
    if "status" in cols:
        print("La columna status ya existe en devices.")
        conn.close()
        return 0
    try:
        conn.execute("ALTER TABLE devices ADD COLUMN status TEXT DEFAULT 'unknown'")
        conn.commit()
        print("Columna status añadida a devices (DEFAULT 'unknown').")
    except sqlite3.OperationalError as e:
        print("Error:", e, file=sys.stderr)
        conn.close()
        return 1
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
