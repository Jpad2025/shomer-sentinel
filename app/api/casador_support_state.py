"""system_state, blocked_ips y subredes Hunter."""
import json
import ipaddress
from typing import Any, Dict, List

from app.backend.db import get_connection


def _ensure_blocked_ips_table():
    with get_connection(timeout=10) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_ips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL UNIQUE,
                blocked_at TEXT NOT NULL,
                blocked_by TEXT DEFAULT 'auto',
                alert_sid INTEGER,
                alert_signature TEXT,
                severity INTEGER,
                unblocked_at TEXT,
                firewall_blocked INTEGER DEFAULT 0
            )
            """
        )
        # Migración: agregar columna si la tabla ya existía sin ella
        try:
            conn.execute("ALTER TABLE blocked_ips ADD COLUMN firewall_blocked INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()


_ensure_blocked_ips_table()


def _get_config(key: str, default=None):
    try:
        with get_connection(timeout=10) as conn:
            row = conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
    except Exception:
        pass
    return default


def _get_firewall_creds() -> Dict[str, Any]:
    port_raw = _get_config("hunter.firewall_port", 22)
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 22
    timeout_raw = _get_config("hunter.firewall_timeout", 10)
    try:
        timeout = max(3, int(timeout_raw))
    except (TypeError, ValueError):
        timeout = 10
    fw_type = _get_config("hunter.firewall_type", "openwrt") or "openwrt"
    if fw_type not in ("openwrt", "routeros"):
        fw_type = "openwrt"
    return {
        "ip": _get_config("hunter.firewall_ip", ""),
        "user": _get_config("hunter.firewall_user", ""),
        "pass": _get_config("hunter.firewall_pass", ""),
        "port": port,
        "timeout": timeout,
        "type": fw_type,
    }


def _get_hunter_subnets() -> List[str]:
    subnets = _get_config("hunter.subnets", [])
    if isinstance(subnets, str):
        return [subnets]
    return subnets or []


def _is_external_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        for subnet in _get_hunter_subnets():
            try:
                if addr in ipaddress.ip_network(subnet, strict=False):
                    return False
            except ValueError:
                continue
        return True
    except ValueError:
        return False


def _is_blocked(ip: str) -> bool:
    try:
        with get_connection(timeout=10) as conn:
            row = conn.execute(
                "SELECT id FROM blocked_ips WHERE ip = ? AND unblocked_at IS NULL", (ip,)
            ).fetchone()
            return row is not None
    except Exception:
        return False
