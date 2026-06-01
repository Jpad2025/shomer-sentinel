#!/usr/bin/env python3
"""
Fuerza la actualización de status para 192.168.1.20 y 192.168.1.27.
BD desde app.backend.db (/storage/db/).
"""
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend.db import connect
PING_CMD = "/usr/bin/ping"
TARGETS = [("192.168.1.20", 6), ("192.168.1.27", 7)]  # (ip, device_id)


def ping_ok(ip):
    try:
        r = subprocess.run(
            [PING_CMD, "-c", "1", "-W", "2", ip],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def main():
    now = datetime.utcnow()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")
    conn = connect(timeout=30)
    cur = conn.cursor()

    for ip, device_id in TARGETS:
        ok = ping_ok(ip)
        status = "online" if ok else "offline"
        cur.execute("UPDATE devices SET status = ? WHERE id = ?", (status, device_id))
        cur.execute(
            "INSERT INTO device_status (device_id, status, last_check) VALUES (?, ?, ?)",
            (device_id, status, now_str),
        )
        print(f"{ip} (id={device_id}): ping={'OK' if ok else 'FAIL'} -> status={status}")

    conn.commit()
    conn.close()
    print("BD actualizada. Refresca el panel para ver el estado en verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
