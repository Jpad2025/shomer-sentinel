"""
Lectura de alertas Suricata desde eve.json (NDJSON) para enriquecer listado de activos.
Sin FastAPI. Ruta por defecto de instalación Shomer; override vía argumento.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Set

# Instalación típica — mismo contrato que antes en inventory.py
SURICATA_EVE_DEFAULT_PATH = "/var/log/suricata/eve.json"


def read_suricata_alerts_for_ips(
    asset_ips: Set[str],
    *,
    eve_path: Optional[str] = None,
    max_bytes: int = 400000,
    max_alerts_per_ip: int = 10,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Lee el final de eve.json, filtra event_type alert y agrupa por IP presente en asset_ips
    (coincidencia src_ip o dest_ip). No escribe BD.
    """
    path = eve_path or SURICATA_EVE_DEFAULT_PATH
    if not asset_ips or not os.path.isfile(path):
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {ip: [] for ip in asset_ips}
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - max_bytes))
            raw = f.read().decode("utf-8", errors="ignore")
        lines = [s.strip() for s in raw.split("\n") if s.strip()][-2000:]
        for line in lines:
            try:
                ev = json.loads(line)
                if ev.get("event_type") != "alert":
                    continue
                src = (ev.get("src_ip") or "").strip()
                dest = (ev.get("dest_ip") or "").strip()
                ip = src if src in asset_ips else (dest if dest in asset_ips else None)
                if not ip:
                    continue
                alert_obj = ev.get("alert") or {}
                entry = {
                    "timestamp": ev.get("timestamp") or "",
                    "signature": alert_obj.get("signature") or "",
                    "severity": alert_obj.get("severity"),
                }
                out[ip].append(entry)
            except (json.JSONDecodeError, TypeError):
                continue
        for ip in out:
            out[ip] = out[ip][-max_alerts_per_ip:]
    except (OSError, IOError):
        pass
    return out


def enrich_assets_with_suricata_alerts(assets: List[Dict[str, Any]]) -> None:
    """In-place: suricata_alert_count y suricata_alerts por IP (máx. 5 en lista)."""
    asset_ips = {a.get("ip") for a in assets if a.get("ip")}
    if not asset_ips:
        return
    alerts_by_ip = read_suricata_alerts_for_ips(asset_ips)
    for a in assets:
        ip = a.get("ip") or ""
        alerts = alerts_by_ip.get(ip, [])[:5]
        a["suricata_alert_count"] = len(alerts_by_ip.get(ip, []))
        a["suricata_alerts"] = alerts
