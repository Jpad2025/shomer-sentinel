#!/usr/bin/env python3
"""
Módulo de Inventario Permanente: sincroniza la tabla ARP del GL vía SSH cada 5 minutos.
Registra MACs en la tabla assets (nuevas: hostname y vendor; existentes: solo last_seen).
Router: primer dispositivo activo con SSH en tabla devices (sin device_id hardcodeado).
"""
import os
import re
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# Paths
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
for _p in (_ROOT, _BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from app.backend.db import connect, CONNECT_TIMEOUT
SSHPASS_PATH = "/usr/bin/sshpass"
SSH_PATH = "/usr/bin/ssh"
SSH_TIMEOUT_SEC = 15
SYNC_INTERVAL_SEC = 300  # 5 minutos
LOG_DIR = "/var/log/shomer"
LOG_FILE = os.path.join(LOG_DIR, "inventory_sync.log")

os.makedirs(LOG_DIR, exist_ok=True)
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("inventory_sync")


@contextmanager
def get_conn():
    conn = connect(timeout=CONNECT_TIMEOUT)
    try:
        yield conn
    finally:
        conn.close()


def ensure_assets_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT NOT NULL UNIQUE,
            ip_address TEXT,
            hostname TEXT,
            vendor TEXT,
            first_seen TEXT,
            last_seen TEXT,
            source TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_last_seen ON assets(last_seen)")
    conn.commit()


def get_credentials_from_db() -> Optional[Tuple[str, str, str]]:
    """Obtiene credenciales del primer router activo con SSH configurado."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT ip_address, ssh_user, ssh_password FROM devices "
                "WHERE is_active = 1 AND ssh_user IS NOT NULL AND ssh_user != '' "
                "ORDER BY id LIMIT 1"
            )
            row = cur.fetchone()
            if not row or not row["ip_address"] or not row["ssh_user"] or not row["ssh_password"]:
                return None
            return (row["ip_address"], row["ssh_user"], row["ssh_password"])
    except Exception as e:
        logger.error("Error leyendo credenciales: %s", e)
        return None


def run_ssh(host: str, user: str, password: str, command: str) -> Optional[str]:
    cmd = [
        SSHPASS_PATH, "-p", password, SSH_PATH,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "PreferredAuthentications=password",
        f"{user}@{host}",
        command,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SSH_TIMEOUT_SEC)
        if proc.returncode != 0:
            logger.warning("SSH falló (code %s): %s", proc.returncode, (proc.stderr or "").strip())
            return None
        return proc.stdout
    except subprocess.TimeoutExpired:
        logger.error("Timeout SSH")
        return None
    except FileNotFoundError:
        logger.error("sshpass/ssh no encontrado: %s", SSHPASS_PATH)
        return None
    except Exception as e:
        logger.exception("SSH error: %s", e)
        return None


def parse_arp(stdout: str) -> List[Dict[str, str]]:
    """Parsea salida de cat /proc/net/arp -> [{ip, mac}, ...]"""
    entries = []
    for line in (stdout or "").strip().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        ip_addr = parts[0]
        if ip_addr in ("IP", "0.0.0.0"):
            continue
        hw = parts[3]
        if hw == "00:00:00:00:00:00" or "*" in hw:
            continue
        mac = hw.upper().replace("-", ":")
        if re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
            entries.append({"ip": ip_addr, "mac": mac})
    return entries


def parse_dhcp_leases(stdout: str) -> Dict[str, str]:
    """Parsea /tmp/dhcp.leases (OpenWrt): timestamp mac ip hostname -> {ip: hostname}"""
    out = {}
    for line in (stdout or "").strip().splitlines():
        parts = line.split()
        if len(parts) >= 4:
            # lease_end mac ip hostname
            out[parts[2]] = parts[3]
    return out


def run_sync_cycle() -> int:
    creds = get_credentials_from_db()
    if not creds:
        logger.error("Sin credenciales del router — verifica tabla devices (is_active=1, ssh_user configurado)")
        return 0
    host, user, password = creds

    arp_out = run_ssh(host, user, password, "cat /proc/net/arp")
    arp_entries = parse_arp(arp_out or "")
    if not arp_entries:
        logger.info("Sin entradas ARP")
        return 0

    # Opcional: hostnames desde DHCP (OpenWrt)
    dhcp_out = run_ssh(host, user, password, "cat /tmp/dhcp.leases 2>/dev/null || true")
    ip_to_hostname = parse_dhcp_leases(dhcp_out or "")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    source = "inventory_sync"
    updated = 0
    with get_conn() as conn:
        ensure_assets_table(conn)
        cur = conn.cursor()
        for e in arp_entries:
            ip_addr, mac = e["ip"], e["mac"]
            hostname = ip_to_hostname.get(ip_addr) or None
            cur.execute("SELECT id, first_seen FROM assets WHERE mac_address = ?", (mac,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE assets SET ip_address = ?, last_seen = ?, hostname = COALESCE(?, hostname) WHERE mac_address = ?",
                    (ip_addr, now, hostname, mac),
                )
            else:
                cur.execute(
                    "INSERT INTO assets (mac_address, ip_address, hostname, vendor, first_seen, last_seen, source) VALUES (?, ?, ?, NULL, ?, ?, ?)",
                    (mac, ip_addr, hostname, now, now, source),
                )
            updated += 1
        conn.commit()
    logger.info("Sincronizados %d activos (ARP)", updated)
    return updated


def main() -> int:
    logger.info("Inventario permanente iniciado (intervalo=%ds)", SYNC_INTERVAL_SEC)
    try:
        while True:
            run_sync_cycle()
            time.sleep(SYNC_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Detenido por el usuario")
        return 0
    except Exception as e:
        logger.exception("Error fatal: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
