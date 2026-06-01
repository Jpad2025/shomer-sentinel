"""
Modelo de activo para Tracker — normalización API↔frontend y observaciones de riesgo.
Extraído de inventory.py (refactor por bloques; sin dependencias FastAPI).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

KEYWORDS_RISK = [
    "anydesk",
    "teamviewer",
    "nmap",
    "wireshark",
    "vnc",
    "putty",
    "java",
    "python",
]


def normalize_asset_for_frontend(asset: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sincronización Tracker -> Front: compatibilidad de modelos.
    - os_detected: el motor puede escribir os_name; el front espera os_detected.
    - wmi_status, snmp_status, ssh_status: nunca null.
    - Campos del Drawer como claves presentes ("" si faltan).
    """
    out = dict(asset)
    os_val = (out.get("os_detected") or out.get("os_name") or "").strip()
    out["os_detected"] = os_val
    if not out.get("os_name"):
        out["os_name"] = os_val
    for key in ("wmi_status", "snmp_status", "ssh_status"):
        v = out.get(key)
        if v is None:
            out[key] = ""
        elif not isinstance(v, str):
            out[key] = str(v)
    drawer_keys = [
        "ip",
        "hostname",
        "vendor",
        "asset_type",
        "os_family",
        "os_version",
        "cpu",
        "ram",
        "storage_cap",
        "serial_number",
        "firmware_version",
        "ports_open",
        "last_audit",
        "user_assigned",
        "location",
        "asset_model",
        "purchase_date",
        "warranty_expiration",
        "status_audit",
        "physical_state",
        "visual_details",
        "last_physical_cleaning",
        "hardware_changes",
        "software_updates",
        "software_list",
        "internal_notes",
        "warranty_exp",
        "override_user",
        "override_pass",
        "override_snmp",
    ]
    for k in drawer_keys:
        if k not in out:
            out[k] = ""
        elif out[k] is None:
            out[k] = ""
    return out


def compute_risk_observations(asset: Dict[str, Any]) -> str:
    """Texto de Observaciones de Riesgo a partir de software_list y tipo de activo."""
    notes: List[str] = []
    raw_sw = asset.get("software_list") or ""
    if raw_sw:
        try:
            sw = json.loads(raw_sw)
        except Exception:
            sw = []
    else:
        sw = []
    if isinstance(sw, list):
        names = " ".join(
            (app.get("DisplayName") or "").lower()
            for app in sw
            if isinstance(app, dict)
        )
        for kw in KEYWORDS_RISK:
            if kw in names:
                notes.append("Software sensible detectado: %s" % kw)
    if (asset.get("asset_type") or "").lower() == "laptop":
        notes.append("Equipo portátil – riesgo de pérdida/robo.")
    return "; ".join(notes)
