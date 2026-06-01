#!/usr/bin/env python3
"""
Discovery/inventario invocado por la API (POST /api/discovery/scan).
Inventario pasivo: lee la tabla ARP del router vía SSH; no hace pings ni escaneo masivo.
Rutas de BD desde app.backend.db (/storage/db/).
"""
import json
import sys
import os
import sqlite3
from typing import List, Dict

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend.db import connect

# Importar run_discovery del script de backend (ARP vía SSH)
_BACKEND = "/opt/network_monitor/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from scripts.discovery import run_discovery


def get_conn():
    return connect(timeout=30, check_same_thread=False)


def list_discovered_for_api() -> List[Dict]:
    """Última vista por ip_address (misma lógica que el API de results)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT dd.ip_address AS ip, dd.mac_address AS mac, dd.hostname,
                   dd.open_ports, dd.inferred_type, dd.status
            FROM discovered_devices dd
            JOIN (
                SELECT ip_address, MAX(last_seen) AS last_seen
                FROM discovered_devices
                GROUP BY ip_address
            ) m ON m.ip_address = dd.ip_address AND m.last_seen = dd.last_seen
            ORDER BY dd.last_seen DESC
            LIMIT 500
        """)
        rows = cur.fetchall()
        out = []
        for r in rows:
            try:
                ports = json.loads(r["open_ports"] or "[]")
            except Exception:
                ports = []
            out.append({
                "ip": r["ip"],
                "mac": r["mac"],
                "hostname": r["hostname"] or "",
                "open_ports": ports,
                "inferred_type": r["inferred_type"] or "unknown",
                "status": r["status"] or "unknown",
            })
        return out
    finally:
        conn.close()


def main(argv=None):
    # Inventario pasivo: ARP del router vía SSH (sin pings masivos)
    count = run_discovery()
    results = list_discovered_for_api()
    subnets = list(argv) if argv else []
    return {"count": count, "subnets": subnets, "results": results}


if __name__ == "__main__":
    out = main(sys.argv[1:])
    print(json.dumps(out, indent=2))
