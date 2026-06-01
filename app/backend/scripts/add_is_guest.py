#!/usr/bin/env python3
"""Añade columna is_guest (INTEGER DEFAULT 0) a devices si no existe. BD desde app.backend.db."""
import os
import sqlite3
import sys
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend.db import connect

def main():
    conn = connect(timeout=30)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(devices)")
    cols = [row[1] for row in cur.fetchall()]
    if "is_guest" not in cols:
        conn.execute("ALTER TABLE devices ADD COLUMN is_guest INTEGER DEFAULT 0")
        conn.commit()
        print("Columna is_guest añadida a devices.")
    else:
        print("Columna is_guest ya existe.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
