"""
Edición de activos en inventory.db — campos permitidos y upsert SQL.
Sin FastAPI.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from app.api.inventory_db_schema import existing_columns

# mac es PK (URL); estos campos acepta PATCH /inventory/update/{mac}
ASSET_EDITABLE_FIELDS = frozenset(
    {
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
        "internal_notes",
        "os_detected",
        "software_list",
        "warranty_exp",
        "override_user",
        "override_pass",
        "override_snmp",
        "ownership_type",
        "owner_name",
        "last_maintenance",
        "reviewed",
        "monitor_count",
        "monitors_json",
        "peripherals_manual",
        "integrated_monitor",
        "integrated_monitor_model",
        "integrated_monitor_serial",
    }
)


def sanitize_asset_updates(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Filtra a ASSET_EDITABLE_FIELDS y normaliza strings (trim). last_audit lo añade la ruta."""
    updates: Dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if k not in ASSET_EDITABLE_FIELDS:
            continue
        updates[k] = (v or "").strip() if isinstance(v, str) else (v if v is not None else "")
    return updates


def upsert_asset_row(conn: sqlite3.Connection, mac: str, updates: Dict[str, Any]) -> None:
    """
    INSERT (todas las columnas menos mac con default '') o UPDATE por mac.
    `updates` debe incluir ya last_audit si aplica.
    """
    cur = conn.cursor()
    cur.execute("SELECT mac FROM assets WHERE mac = ?", (mac,))
    if not cur.fetchone():
        all_cols = existing_columns(conn, "assets")
        cols = [c for c in all_cols if c != "mac"]
        cur.execute(
            "INSERT INTO assets (mac, "
            + ", ".join(cols)
            + ") VALUES (?, "
            + ", ".join(["?"] * len(cols))
            + ")",
            [mac] + [updates.get(c, "") for c in cols],
        )
    else:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [mac]
        cur.execute(f"UPDATE assets SET {set_clause} WHERE mac = ?", vals)
    conn.commit()
