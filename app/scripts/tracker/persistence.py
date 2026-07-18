"""
Tracker - Capa de datos: schema inventory.db, credenciales, overrides, save_assets.
Solo recibe conn; el orquestador usa get_connection_inventory() de app.backend.db.
"""
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict, List

from .discovery import _is_real_mac

# Logger industrial en tracker.log
def _log():
    from . import get_logger
    return get_logger("tracker.persistence")


def _ensure_network_credentials(conn: sqlite3.Connection) -> None:
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


def _existing_columns(conn: sqlite3.Connection, table: str) -> set:
    cur = conn.execute("PRAGMA table_info(%s)" % table)
    return {row[1] for row in cur.fetchall()}


def _assets_columns_ordered(conn: sqlite3.Connection) -> List[str]:
    """Columnas de assets en orden de definición (PRAGMA table_info) para INSERT correcto."""
    cur = conn.execute("PRAGMA table_info(assets)")
    return [row[1] for row in cur.fetchall()]


# Lista maestra: todas las columnas que debe tener la tabla assets (estándar orquestador v2.0).
# Si falta alguna, ensure_schema ejecuta ALTER TABLE assets ADD COLUMN <col> TEXT.
ASSETS_MASTER_COLUMNS = [
    "mac",
    "ip",
    "hostname",
    "vendor",
    "asset_type",
    "os_family",
    "os_version",
    "os_name",           # estándar v2.0 (equivalente a os_detected)
    "os_detected",       # legacy, se mantiene para compatibilidad
    "last_seen",         # timestamp último contacto
    "last_audit",
    "cpu",
    "ram",
    "storage_cap",
    "serial_number",
    "firmware_version",
    "ports_open",
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
    "software_list",
    "warranty_exp",
    "override_user",
    "override_pass",
    "override_snmp",
    "it_remedy",
    "it_command",
    "created_at",
    "updated_at",
    "wmi_status",
    "snmp_status",
    "ssh_status",
    "ownership_type",    # cliente | leasing | prestamo | propio
    "owner_name",        # nombre del dueño o empresa
    "last_maintenance",  # fecha último mantenimiento (YYYY-MM-DD)
    "reviewed",
    "monitor_count",           # 1-3 monitores (validación física)
    "monitors_json",           # manual: [{model, serial}, ...]
    "monitors_detected_json",  # auto escaneo
    "peripherals_detected_json",
    "peripherals_manual",
    "local_printers_json",
    "logged_user",
    "logged_user_at",
    "integrated_monitor",
    "integrated_monitor_model",
    "integrated_monitor_serial",
]

_SYSTEMINFO_REQUIRED_COLUMNS = [
    "asset_model", "ram", "cpu", "os_detected", "serial_number",
    "firmware_version", "storage_cap",
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    _ensure_network_credentials(conn)
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
            os_name TEXT,
            os_detected TEXT,
            last_seen TEXT,
            last_audit TEXT,
            cpu TEXT,
            ram TEXT,
            storage_cap TEXT,
            serial_number TEXT,
            firmware_version TEXT,
            ports_open TEXT,
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
            ssh_status TEXT,
            ownership_type TEXT,
            owner_name TEXT,
            last_maintenance TEXT
        )
        """
    )
    conn.commit()
    # Auto-sanado: comparar columnas actuales con lista maestra y añadir las que falten
    existing = _existing_columns(conn, "assets")
    for col in ASSETS_MASTER_COLUMNS:
        if col in existing:
            continue
        try:
            conn.execute("ALTER TABLE assets ADD COLUMN %s TEXT" % col)
            conn.commit()
            _log().info("ALTER TABLE assets ADD COLUMN %s (auto-sanado)", col)
        except sqlite3.OperationalError as e:
            _log().debug("ALTER TABLE assets ADD COLUMN %s failed: %s", col, e)


def get_credentials(conn: sqlite3.Connection) -> Dict[str, str]:
    cur = conn.execute(
        "SELECT user, password, domain, snmp_community FROM network_credentials ORDER BY id LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        return {}
    return {
        "user": (row[0] or "").strip(),
        "password": (row[1] or "").strip(),
        "domain": (row[2] or "").strip(),
        "snmp_community": (row[3] or "public").strip() or "public",
    }


def get_overrides_by_ip(conn: sqlite3.Connection) -> Dict[str, Dict[str, str]]:
    """Devuelve dict ip -> {user, password, snmp} desde assets (override_user, override_pass, override_snmp)."""
    overrides: Dict[str, Dict[str, str]] = {}
    cur = conn.execute(
        "SELECT ip, override_user, override_pass, override_snmp FROM assets"
    )
    for row in cur.fetchall():
        ip = (row[0] or "").strip() if len(row) > 0 else ""
        if not ip:
            continue
        overrides[ip] = {
            "user": (row[1] or "").strip() if len(row) > 1 else "",
            "password": (row[2] or "").strip() if len(row) > 2 else "",
            "snmp": (row[3] or "").strip() if len(row) > 3 else "",
        }
    return overrides


def _ensure_master_columns(conn: sqlite3.Connection) -> None:
    """Asegura que existan todas las columnas de la lista maestra. ALTER si falta alguna."""
    existing_set = _existing_columns(conn, "assets")
    for col in ASSETS_MASTER_COLUMNS:
        if col in existing_set:
            continue
        try:
            conn.execute("ALTER TABLE assets ADD COLUMN %s TEXT" % col)
            conn.commit()
        except sqlite3.OperationalError:
            _log().debug("ALTER TABLE %s failed", col)


def merge_quick_scan_assets(assets: List[Dict[str, Any]], conn: sqlite3.Connection) -> None:
    """
    Upsert no-destructivo para escaneo rápido (ping sweep).
    Para filas existentes solo actualiza ip/vendor/hostname/last_seen/last_audit
    y los status; NUNCA sobrescribe asset_type, ram, cpu, etc. con vacío.
    Para filas nuevas inserta solo los campos básicos.
    """
    if not assets:
        return
    log = _log()
    now_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _ensure_master_columns(conn)
    for a in assets:
        mac = (a.get("mac") or "").strip()
        if mac and _is_real_mac(mac):
            mac = mac.upper()
        if not mac:
            mac = "ip-%s" % ((a.get("ip") or "").strip() or "unknown")
        ip       = (a.get("ip")       or "").strip()
        vendor   = (a.get("vendor")   or "").strip()
        hostname = (a.get("hostname") or "").strip()
        asset_type = (a.get("asset_type") or "").strip()

        # INSERT new row with minimal fields; on conflict (existing mac) do
        # non-destructive update: only write non-empty values and preserve enriched data.
        conn.execute(
            """
            INSERT INTO assets (mac, ip, vendor, hostname, asset_type,
                                wmi_status, snmp_status, ssh_status,
                                last_seen, last_audit)
            VALUES (?, ?, ?, ?, ?,
                    'NOT_ATTEMPTED', 'NOT_ATTEMPTED', 'NOT_ATTEMPTED',
                    ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                ip         = CASE WHEN excluded.ip         != '' THEN excluded.ip         ELSE ip         END,
                vendor     = CASE WHEN excluded.vendor     != '' THEN excluded.vendor     ELSE vendor     END,
                hostname   = CASE WHEN excluded.hostname   != '' THEN excluded.hostname   ELSE hostname   END,
                asset_type = CASE WHEN excluded.asset_type != '' THEN excluded.asset_type ELSE asset_type END,
                -- Quick scan no toca WMI/SSH/SNMP: preserva resultado del deep scan.
                last_seen  = excluded.last_seen,
                last_audit = excluded.last_audit
            """,
            (mac, ip, vendor, hostname, asset_type, now_ts, now_ts),
        )
    conn.commit()
    log.info("[INFO] Persistence: merge_quick_scan_assets finished: %d assets", len(assets))


def save_assets(assets: List[Dict[str, Any]], conn: sqlite3.Connection) -> None:
    if not assets:
        return
    log = _log()
    log.info("[INFO] Persistence: save_assets started (%d assets)", len(assets))
    now_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _ensure_master_columns(conn)
    cols = _assets_columns_ordered(conn)
    if not cols:
        log.warning("save_assets: no columns from assets table")
        log.info("[INFO] Persistence: save_assets finished (0 written)")
        return
    # Persistencia garantizada: cero descartes. MAC sintético si vacío (ip-<ip>).
    for a in assets:
        mac = (a.get("mac") or "").strip()
        if mac and _is_real_mac(mac):
            mac = mac.upper()
            a["mac"] = mac
        if not mac:
            a["mac"] = "ip-%s" % ((a.get("ip") or "").strip() or "unknown")
        mac = (a.get("mac") or "").strip()
        if mac and _is_real_mac(mac):
            ip = (a.get("ip") or "").strip()
            if ip:
                conn.execute("DELETE FROM assets WHERE mac = ?", ("ip-%s" % ip,))
    conn.commit()
    # Columnas que siempre se sobreescriben (timestamps garantizados no-vacíos).
    _ALWAYS_UPDATE = {"last_audit", "last_seen", "mac"}
    non_pk_cols = [c for c in cols if c != "mac"]
    # UPDATE: non-empty wins — preserva datos manuales o de escaneos previos.
    update_clause = ", ".join(
        f"{c} = excluded.{c}"
        if c in _ALWAYS_UPDATE
        else f"{c} = CASE WHEN excluded.{c} != '' THEN excluded.{c} ELSE {c} END"
        for c in non_pk_cols
    )
    placeholders = ",".join(["?"] * len(cols))
    sql = (
        "INSERT INTO assets (%s) VALUES (%s) ON CONFLICT(mac) DO UPDATE SET %s"
        % (",".join(cols), placeholders, update_clause)
    )

    for a in assets:
        mac = (a.get("mac") or "").strip()
        if mac and _is_real_mac(mac):
            mac = mac.upper()
            a["mac"] = mac
        if not mac:
            a["mac"] = "ip-%s" % ((a.get("ip") or "").strip() or "unknown")
        a["last_audit"] = now_ts
        a["last_seen"] = now_ts
        a["os_name"] = (a.get("os_name") or a.get("os_detected") or "").strip() or ""
        vals = [(a.get(c) if a.get(c) is not None else "") for c in cols]
        try:
            conn.execute(sql, vals)
        except sqlite3.Error as e:
            log.exception("SQLite error in save_assets: %s", e.args)
            raise
    conn.commit()
    log.info("[INFO] Persistence: save_assets finished: %d assets written", len(assets))
