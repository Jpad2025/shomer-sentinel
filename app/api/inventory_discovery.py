"""
Discovery y jobs de escaneo del Tracker (subprocess, sync con inventory.db).
Sin FastAPI. Rutas de scripts relativas a la raíz del proyecto (app/api → ../../).
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.backend.db import DB_PATH, connect, get_connection_inventory
from app.api.inventory_db_schema import ensure_assets_table, ensure_network_credentials

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCANNER_PATH = os.path.join(_REPO_ROOT, "app", "scripts", "scanner.py")
DISCOVERY_SCRIPT_PATH = os.path.join(_REPO_ROOT, "app", "scripts", "discovery.py")
VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "bin", "python")
TRACKER_LOG = "/var/log/shomer/tracker.log"
SCANNER_LOG = "/var/log/shomer/scanner.log"


def run_discovery_script(timeout: int = 300) -> bool:
    """Ejecuta app/scripts/discovery.py (ARP + ping). Escribe en network_monitor.db."""
    if not os.path.isfile(DISCOVERY_SCRIPT_PATH):
        return False
    try:
        proc = subprocess.run(
            [VENV_PYTHON, DISCOVERY_SCRIPT_PATH],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_REPO_ROOT,
            env=os.environ.copy(),
        )
        return proc.returncode in (0, None)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def read_discovered_devices(network_db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lee discovered_devices de network_monitor.db (ip, mac, hostname, vendor)."""
    path = network_db_path or DB_PATH
    if not os.path.isfile(path):
        return []
    conn = connect(timeout=15, check_same_thread=False)
    try:
        cur = conn.execute(
            """
            SELECT ip_address AS ip, mac_address AS mac, hostname, vendor
            FROM discovered_devices
            WHERE ip_address IS NOT NULL AND ip_address != ''
              AND mac_address IS NOT NULL AND mac_address != ''
            ORDER BY last_seen DESC
            """
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def enrich_hostname_nmap(ips: List[str], timeout_sec: int = 90) -> Dict[str, str]:
    """Hostname por IP con nmap -sn. Devuelve dict ip -> hostname."""
    if not ips:
        return {}
    try:
        proc = subprocess.run(
            ["nmap", "-sn", "-n", "--max-retries", "1", "--host-timeout", "3s"] + ips[:254],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    result: Dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if "Nmap scan report for " not in line:
            continue
        rest = line.split("Nmap scan report for ", 1)[-1].strip()
        if not rest:
            continue
        if "(" in rest and rest.endswith(")"):
            hostname, ip_part = rest.rsplit("(", 1)
            ip = ip_part.rstrip(")").strip()
            result[ip] = hostname.strip() or ""
        else:
            ip = rest
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                result[ip] = ""
    return result


def vendor_from_oui(mac: str) -> str:
    """Fabricante aproximado desde OUI (6 hex)."""
    if not mac:
        return ""
    oui = re.sub(r"[-:]", "", (mac or "").strip().upper())[:6]
    if len(oui) < 6:
        return ""
    _oui_map: Dict[str, str] = {
        "001A2B": "Cisco", "000C29": "VMware", "0050C2": "Microsoft",
        "080027": "PCS Systemtechnik", "000E35": "Intel", "001E65": "Intel",
        "3C5AB4": "Apple", "001E52": "Apple", "001EC2": "Apple",
        "F0DBF8": "Apple", "001D4F": "Apple", "001F5B": "Apple",
        "B827EB": "Raspberry Pi", "DCA6F5": "Raspberry Pi",
        "E45F01": "GL.iNet", "64B473": "GL.iNet",
        "001B63": "Netgear", "F4F26D": "TP-Link", "50C7BF": "TP-Link",
    }
    return _oui_map.get(oui, "")


def sync_discovered_to_inventory(devices: List[Dict[str, Any]]) -> int:
    """
    Inserta o actualiza assets en inventory.db desde dispositivos descubiertos.
    Preserva columnas existentes; actualiza ip, hostname, vendor, last_audit.
    """
    if not devices:
        return 0
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection_inventory(timeout=30) as conn:
        ensure_network_credentials(conn)
        ensure_assets_table(conn)
        count = 0
        for d in devices:
            mac = (d.get("mac") or "").strip()
            ip = (d.get("ip") or "").strip()
            hostname = (d.get("hostname") or "").strip() or None
            vendor = (d.get("vendor") or "").strip() or None
            if not mac or not ip:
                continue
            cur = conn.execute("SELECT mac FROM assets WHERE mac = ?", (mac,))
            row = cur.fetchone()
            if row:
                conn.execute(
                    "UPDATE assets SET ip = ?, hostname = COALESCE(?, hostname), vendor = COALESCE(?, vendor), last_audit = ? WHERE mac = ?",
                    (ip, hostname, vendor, now, mac),
                )
            else:
                conn.execute(
                    """INSERT INTO assets (mac, ip, hostname, vendor, last_audit)
                       VALUES (?, ?, ?, ?, ?)""",
                    (mac, ip, hostname, vendor, now),
                )
            count += 1
        conn.commit()
        return count


def run_inventory_quick_scan_background() -> None:
    """scanner.py en modo quick (ping sweep). Log en TRACKER_LOG."""
    cmd = ["nice", "-n", "19", VENV_PYTHON, SCANNER_PATH]
    env = os.environ.copy()
    env["INVENTORY_SCAN_MODE"] = "quick"
    os.makedirs(os.path.dirname(TRACKER_LOG), exist_ok=True)
    try:
        with open(TRACKER_LOG, "a", encoding="utf-8") as log_file:
            subprocess.run(
                cmd,
                env=env,
                cwd=_REPO_ROOT,
                stdout=log_file,
                stderr=log_file,
                text=True,
                timeout=300,
            )
    except Exception as e:
        logger.debug("quick scan background: %s", e)


def run_inventory_deep_scan_background(env: Dict[str, str]) -> None:
    """scanner.py en modo deep. Log en SCANNER_LOG."""
    cmd = ["nice", "-n", "19", VENV_PYTHON, SCANNER_PATH]
    merged = os.environ.copy()
    merged.update(env)
    os.makedirs(os.path.dirname(SCANNER_LOG), exist_ok=True)
    try:
        with open(SCANNER_LOG, "a", encoding="utf-8") as log_file:
            subprocess.run(
                cmd,
                env=merged,
                cwd=_REPO_ROOT,
                stdout=log_file,
                stderr=log_file,
                text=True,
                timeout=7200,
            )
    except Exception as e:
        logger.debug("deep scan background: %s", e)


def build_deep_scan_environment(payload: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Entorno subprocess para scanner.py modo deep (targets/replace desde body)."""
    env = os.environ.copy()
    env["INVENTORY_SCAN_MODE"] = "deep"
    if payload and isinstance(payload, dict):
        targets = payload.get("targets") or payload.get("subnets")
        if isinstance(targets, str):
            env["INVENTORY_SCAN_TARGETS"] = targets
        elif isinstance(targets, list):
            env["INVENTORY_SCAN_TARGETS"] = " ".join(
                str(t).strip() for t in targets if str(t).strip()
            )
        if payload.get("replace") is True:
            env["INVENTORY_SCAN_REPLACE"] = "1"
    return env
