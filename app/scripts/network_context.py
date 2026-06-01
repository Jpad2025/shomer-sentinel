#!/usr/bin/env python3
"""
Contexto de red para Suite SHOMER PRO: detección automática de subred e interfaz.
Usado por monitor.py (rango dinámico) y por API (config scan, inventario).
"""
import os
import re
import subprocess
from typing import Any


def _ipv4_on_interface(iface: str) -> str | None:
    """IPv4 principal configurada en la interfaz (primera inet)."""
    if not iface:
        return None
    try:
        r = subprocess.run(
            ["ip", "-4", "addr", "show", "dev", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return None
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", r.stdout or "")
        return m.group(1) if m else None
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return None


def get_network_context(
    interface_hint: str | None = None,
    skip_saved: bool = False,
) -> dict[str, Any]:
    """
    Detecta subred e interfaz usando ip route / ip addr.
    Primero intenta leer configuración guardada en system_state (BD), salvo skip_saved=True
    (p. ej. wizard de setup: forzar detección en vivo y no mezclar con ruta por defecto WiFi).
    Retorna: subnet (ej. 192.168.1.0/24), interface (ej. enp2s0), gateway, base_ip (ej. 192.168.1).
    """
    # Intentar leer configuración guardada en BD
    if not skip_saved:
        try:
            import sqlite3 as _sqlite3, json as _json, os as _os
            try:
                from app.backend.db import DB_PATH as db_path
            except Exception:
                db_path = "/storage/db/network_monitor.db"
            if _os.path.exists(db_path):
                _conn = _sqlite3.connect(db_path)
                _conn.row_factory = _sqlite3.Row
                saved: dict[str, Any] = {}
                for key in ["base.interface", "base.subnet", "base.gateway", "base.server_ip"]:
                    _row = _conn.execute(
                        "SELECT value FROM system_state WHERE key = ?", (key,)
                    ).fetchone()
                    if _row:
                        field = key.split(".")[1]
                        try:
                            saved[field] = _json.loads(_row["value"])
                        except Exception:
                            saved[field] = _row["value"]
                _conn.close()
                if saved.get("interface") and saved.get("subnet"):
                    subnet = saved["subnet"]
                    parts = subnet.split("/")[0].split(".")
                    base_ip = ".".join(parts[:3]) if len(parts) == 4 else None
                    mgmt_iface = saved["interface"]
                    srv = saved.get("server_ip")
                    if not srv:
                        srv = _ipv4_on_interface(mgmt_iface)
                    return {
                        "subnet":    subnet,
                        "interface": mgmt_iface,
                        "gateway":   saved.get("gateway"),
                        "base_ip":   base_ip,
                        "server_ip": srv,
                    }
        except Exception:
            pass

    try:
        from app.backend.db import SHOMER_MANAGEMENT_INTERFACE as _oem_mgmt
    except Exception:
        _oem_mgmt = (os.environ.get("SHOMER_MANAGEMENT_INTERFACE") or "").strip() or None

    out: dict[str, Any] = {
        "subnet": None,
        "interface": None,
        "gateway": None,
        "base_ip": None,
    }
    try:
        # Obtener ruta por defecto y dev
        r = subprocess.run(
            ["ip", "-4", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0 or not r.stdout.strip():
            # Sin default: intentar primera ruta no link
            r = subprocess.run(
                ["ip", "-4", "route"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        stdout = (r.stdout or "").strip()
        dev_match = re.search(r"\bdev\s+(\S+)", stdout)
        via_match = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)", stdout)
        if via_match:
            out["gateway"] = via_match.group(1)
        # Si se proporciona interface_hint, usarla directamente en lugar de la ruta por defecto
        hint = interface_hint or _oem_mgmt
        iface = hint if hint else (dev_match.group(1) if dev_match else None)
        if not iface:
            # No hay interfaz detectada ni hint — no asumir nombre fijo
            return out
        # Si usamos interface_hint, re-detectar gateway desde esa interfaz específica
        if hint:
            r_gw = subprocess.run(
                ["ip", "-4", "route", "show", "dev", hint],
                capture_output=True, text=True, timeout=5,
            )
            gw_match = re.search(r"default\s+via\s+(\d+\.\d+\.\d+\.\d+)", r_gw.stdout or "")
            if gw_match:
                out["gateway"] = gw_match.group(1)

        # Subred de la interfaz
        r2 = subprocess.run(
            ["ip", "-4", "addr", "show", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r2.returncode != 0:
            if hint:
                iface = hint
            else:
                # Fallback: primera interfaz con inet
                r2 = subprocess.run(
                    ["ip", "-4", "addr", "show"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
        addr_out = (r2.stdout or "").strip()
        # inet 192.168.1.205/24 ...
        inet_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", addr_out)
        if inet_match:
            ip_str, prefix = inet_match.group(1), int(inet_match.group(2))
            parts = ip_str.split(".")
            if len(parts) == 4 and prefix >= 8:
                try:
                    from ipaddress import IPv4Network
                    net = IPv4Network(f"{ip_str}/{prefix}", strict=False)
                    out["subnet"] = str(net)
                except Exception:
                    out["subnet"] = f"{ip_str}/{prefix}"
                out["base_ip"] = ".".join(parts[:3]) if prefix >= 24 else ".".join(parts[:2]) if prefix >= 16 else parts[0]
        out["interface"] = iface
        if iface and out.get("subnet"):
            out["server_ip"] = _ipv4_on_interface(iface)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    if not out["interface"]:
        out["interface"] = interface_hint or _oem_mgmt or None
    if not out["base_ip"] and out["subnet"]:
        # Derivar base_ip de la subred detectada
        parts = out["subnet"].split("/")[0].split(".")
        out["base_ip"] = ".".join(parts[:3])
    if not out["gateway"] and out["base_ip"]:
        out["gateway"] = f"{out['base_ip']}.1"
    return out
