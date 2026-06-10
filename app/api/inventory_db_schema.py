"""
Esquema SQLite inventario (assets, credenciales, snapshots).
Sin FastAPI — usado por `inventory.py` y reusable en tests.
"""
from __future__ import annotations

import sqlite3
from typing import Set

# Columnas para migrar BDs antiguas (ALTER ADD COLUMN)
ASSETS_NEW_COLUMNS = [
    "reviewed",
    "monitor_count",
    "monitors_json",
    "monitors_detected_json",
    "peripherals_detected_json",
    "peripherals_manual",
    "local_printers_json",
    "logged_user",
    "logged_user_at",
    "integrated_monitor",
    "integrated_monitor_model",
    "integrated_monitor_serial",
    "asset_type",
    "os_family",
    "os_version",
    "cpu",
    "ram",
    "storage_cap",
    "firmware_version",
    "purchase_date",
    "warranty_expiration",
    "status_audit",
    "physical_state",
    "visual_details",
    "last_physical_cleaning",
    "hardware_changes",
    "software_updates",
    "internal_notes",
    "created_at",
    "updated_at",
    "wmi_status",
    "snmp_status",
    "ssh_status",
    "override_user",
    "override_pass",
    "override_snmp",
    "it_remedy",
    "it_command",
]


def existing_columns(conn: sqlite3.Connection, table: str) -> Set[str]:
    cur = conn.execute("PRAGMA table_info(%s)" % table)
    return {row[1] for row in cur.fetchall()}


def ensure_network_credentials(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS network_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            password TEXT,
            domain TEXT,
            snmp_community TEXT
        )
        """
    )
    conn.commit()


def ensure_assets_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS inventory_assets")
    conn.commit()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
            mac TEXT PRIMARY KEY,
            ip TEXT,
            hostname TEXT,
            vendor TEXT,
            asset_type TEXT,
            os_family TEXT,
            os_version TEXT,
            cpu TEXT,
            ram TEXT,
            storage_cap TEXT,
            serial_number TEXT,
            firmware_version TEXT,
            ports_open TEXT,
            last_audit TEXT,
            user_assigned TEXT,
            location TEXT,
            asset_model TEXT,
            purchase_date TEXT,
            warranty_expiration TEXT,
            status_audit TEXT,
            physical_state TEXT,
            visual_details TEXT,
            last_physical_cleaning TEXT,
            hardware_changes TEXT,
            software_updates TEXT,
            internal_notes TEXT,
            os_detected TEXT,
            software_list TEXT,
            warranty_exp TEXT,
            override_user TEXT,
            override_pass TEXT,
            override_snmp TEXT,
            it_remedy TEXT,
            it_command TEXT,
            created_at TEXT,
            updated_at TEXT,
            wmi_status TEXT,
            snmp_status TEXT,
            ssh_status TEXT
        )
        """
    )
    conn.commit()
    have = existing_columns(conn, "assets")
    for col in ASSETS_NEW_COLUMNS:
        if col in have:
            continue
        try:
            conn.execute("ALTER TABLE assets ADD COLUMN %s TEXT" % col)
            conn.commit()
        except sqlite3.OperationalError:
            pass


def ensure_snapshots_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            asset_count INTEGER DEFAULT 0,
            data TEXT NOT NULL
        )
        """
    )
    conn.commit()
