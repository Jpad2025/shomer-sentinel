"""
Exportación Tracker → Excel: columnas cliente, filas globales y texto de software en snapshots.
Sin FastAPI (refactor por bloques desde inventory.py).
"""
from __future__ import annotations

import io
import json
from typing import Any, Dict, List

import pandas as pd

from app.api.inventory_asset_model import compute_risk_observations

# Excel global “cliente” (mismo orden que export_global_inventory_excel)
GLOBAL_INVENTORY_COLUMNS = [
    "ip",
    "mac",
    "hostname",
    "vendor",
    "asset_type",
    "os_detected",
    "cpu",
    "ram",
    "storage_cap",
    "serial_number",
    "ports_open",
    "user_assigned",
    "location",
    "asset_model",
    "purchase_date",
    "warranty_expiration",
    "software_list",
    "wmi_status",
    "ssh_status",
    "snmp_status",
    "last_audit",
    "last_seen",
    "ownership_type",
    "owner_name",
    "last_maintenance",
    "Observaciones_de_Riesgo",
]

GLOBAL_INVENTORY_HEADER_ES: Dict[str, str] = {
    "ip": "IP",
    "mac": "MAC",
    "hostname": "Nombre del Equipo",
    "vendor": "Fabricante",
    "asset_type": "Tipo de Activo",
    "os_detected": "Sistema Operativo",
    "cpu": "Procesador",
    "ram": "RAM",
    "storage_cap": "Almacenamiento",
    "serial_number": "Número de Serie",
    "asset_model": "Modelo",
    "ports_open": "Puertos Abiertos",
    "user_assigned": "Usuario Asignado",
    "location": "Ubicación",
    "purchase_date": "Fecha de Compra",
    "warranty_expiration": "Garantía",
    "software_list": "Software Instalado",
    "wmi_status": "Estado WMI",
    "ssh_status": "Estado SSH",
    "snmp_status": "Estado SNMP",
    "last_audit": "Última Auditoría",
    "last_seen": "Última Vez Visto",
    "ownership_type": "Tipo de Propiedad",
    "owner_name": "Propietario / Empresa",
    "last_maintenance": "Último Mantenimiento",
    "Observaciones_de_Riesgo": "Observaciones de Riesgo",
}

# Anchos por título de columna ya traducido (headers en fila 0)
GLOBAL_INVENTORY_COL_WIDTHS: Dict[str, int] = {
    "IP": 15,
    "MAC": 20,
    "Nombre del Equipo": 25,
    "Fabricante": 25,
    "Tipo de Activo": 15,
    "Sistema Operativo": 30,
    "Procesador": 25,
    "RAM": 10,
    "Almacenamiento": 30,
    "Número de Serie": 20,
    "Modelo": 20,
    "Puertos Abiertos": 25,
    "Usuario Asignado": 20,
    "Ubicación": 20,
    "Fecha de Compra": 15,
    "Garantía": 15,
    "Software Instalado": 50,
    "Estado WMI": 15,
    "Estado SSH": 15,
    "Estado SNMP": 15,
    "Última Auditoría": 20,
    "Última Vez Visto": 20,
    "Tipo de Propiedad": 18,
    "Propietario / Empresa": 25,
    "Último Mantenimiento": 18,
    "Observaciones de Riesgo": 40,
}


def prepare_rows_for_global_client_excel(
    normalized_assets: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Una fila por activo: añade Observaciones_de_Riesgo y software_list legible (JSON → nombres).
    """
    rows_out: List[Dict[str, Any]] = []
    for a in normalized_assets:
        row = dict(a)
        row["Observaciones_de_Riesgo"] = compute_risk_observations(a)
        sw = row.get("software_list")
        if sw and isinstance(sw, str) and sw.startswith("["):
            try:
                items = json.loads(sw)
                row["software_list"] = ", ".join(
                    i.get("DisplayName", "") for i in items if i.get("DisplayName")
                )
            except Exception:
                pass
        rows_out.append(row)
    return rows_out


# Snapshot archivado — columnas export_snapshot_excel
SNAPSHOT_INVENTORY_COLUMNS = [
    "ip",
    "mac",
    "hostname",
    "vendor",
    "asset_type",
    "os_detected",
    "cpu",
    "ram",
    "storage_cap",
    "serial_number",
    "ports_open",
    "user_assigned",
    "location",
    "asset_model",
    "purchase_date",
    "warranty_expiration",
    "software_list",
    "wmi_status",
    "ssh_status",
    "snmp_status",
    "last_audit",
    "last_seen",
]

SNAPSHOT_INVENTORY_HEADER_ES: Dict[str, str] = {
    "ip": "IP",
    "mac": "MAC",
    "hostname": "Nombre del Equipo",
    "vendor": "Fabricante",
    "asset_type": "Tipo",
    "os_detected": "Sistema Operativo",
    "cpu": "CPU",
    "ram": "RAM",
    "storage_cap": "Almacenamiento",
    "serial_number": "N° Serie",
    "ports_open": "Puertos Abiertos",
    "user_assigned": "Usuario Asignado",
    "location": "Ubicación",
    "asset_model": "Modelo",
    "purchase_date": "Fecha Compra",
    "warranty_expiration": "Garantía hasta",
    "software_list": "Software",
    "wmi_status": "WMI",
    "ssh_status": "SSH",
    "snmp_status": "SNMP",
    "last_audit": "Último Escaneo",
    "last_seen": "Última vez visto",
}


def parse_software_list_dicts(raw_sw: Any) -> List[Dict[str, Any]]:
    """Lista de dicts desde software_list JSON (export Excel por IP)."""
    if not raw_sw:
        return []
    try:
        data = json.loads(raw_sw) if isinstance(raw_sw, str) else raw_sw
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except Exception:
        pass
    return []


def hardware_row_with_observaciones_riesgo(asset: Dict[str, Any]) -> Dict[str, Any]:
    """Fila hardware con columna Observaciones de Riesgo (nombre con espacio, modal Excel)."""
    out = dict(asset)
    out["Observaciones de Riesgo"] = compute_risk_observations(asset)
    return out


def prepare_snapshot_inventory_dataframe(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """DataFrame listo para escribir Excel de snapshot (columnas fijas + software formateado)."""
    df = pd.DataFrame(rows)
    for col in SNAPSHOT_INVENTORY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[SNAPSHOT_INVENTORY_COLUMNS].rename(columns=SNAPSHOT_INVENTORY_HEADER_ES)
    sw_col = SNAPSHOT_INVENTORY_HEADER_ES.get("software_list", "Software")
    if sw_col in df.columns:
        df[sw_col] = df[sw_col].apply(format_snapshot_software_cell)
    return df


def format_snapshot_software_cell(val: Any) -> str:
    """Texto de columna software en Excel de snapshot (histórico export_snapshot_excel)."""
    if not val:
        return ""
    try:
        items = json.loads(val) if isinstance(val, str) else val
        if isinstance(items, list):
            return "; ".join(
                i.get("DisplayName") or i.get("Name") or str(i)
                for i in items
                if isinstance(i, dict)
            )
    except Exception:
        pass
    return str(val)


# Anchos columnas Excel export snapshot (archivo histórico)
SNAPSHOT_EXCEL_COL_WIDTHS = [
    14, 18, 22, 18, 12, 22, 18, 10, 14, 16, 18, 20, 16, 18, 14, 14, 40, 8, 8, 8, 18, 18,
]


def render_single_asset_excel_bytes(asset: Dict[str, Any]) -> bytes:
    """Hoja Hardware + Software para un activo ya normalizado."""
    sw_list = parse_software_list_dicts(asset.get("software_list") or "")
    asset_with_obs = hardware_row_with_observaciones_riesgo(asset)
    df_hw = pd.DataFrame([asset_with_obs])
    df_sw = pd.DataFrame(sw_list or [], columns=["DisplayName", "DisplayVersion"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df_hw.to_excel(writer, sheet_name="Hardware", index=False)
        df_sw.to_excel(writer, sheet_name="Software", index=False)
    buf.seek(0)
    return buf.read()


def render_global_client_excel_bytes(normalized_assets: List[Dict[str, Any]]) -> bytes:
    """Excel global cliente (formato teal, filtros, freeze) — activos ya normalizados."""
    rows_with_obs = prepare_rows_for_global_client_excel(normalized_assets)
    df = pd.DataFrame(rows_with_obs)
    cols = [c for c in GLOBAL_INVENTORY_COLUMNS if c in df.columns]
    if not cols:
        cols = list(GLOBAL_INVENTORY_COLUMNS)
        df = pd.DataFrame(columns=cols)
    else:
        df = df[cols]
    df = df.rename(columns=GLOBAL_INVENTORY_HEADER_ES)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Inventario", index=False, startrow=1, header=False)
        workbook = writer.book
        worksheet = writer.sheets["Inventario"]

        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#0d6e6e", "font_color": "#ffffff",
            "border": 1, "align": "center", "valign": "vcenter",
            "font_name": "Arial", "font_size": 10
        })
        cell_fmt = workbook.add_format({
            "font_name": "Arial", "font_size": 9,
            "valign": "top", "text_wrap": True, "border": 1
        })
        sw_fmt = workbook.add_format({
            "font_name": "Arial", "font_size": 9,
            "valign": "top", "text_wrap": True, "border": 1,
            "bg_color": "#f0f8f0"
        })
        col_names = [GLOBAL_INVENTORY_HEADER_ES.get(c, c) for c in cols]
        for col_num, col_name in enumerate(col_names):
            worksheet.write(0, col_num, col_name, header_fmt)

        for row_num, row_data in enumerate(df.values):
            for col_num, value in enumerate(row_data):
                col_key = cols[col_num] if col_num < len(cols) else ""
                fmt = sw_fmt if col_key == "software_list" else cell_fmt
                if pd.isna(value) or value is None:
                    worksheet.write(row_num + 1, col_num, "", fmt)
                else:
                    worksheet.write(row_num + 1, col_num, str(value), fmt)

        for col_num, col_name in enumerate(col_names):
            width = GLOBAL_INVENTORY_COL_WIDTHS.get(col_name, 20)
            worksheet.set_column(col_num, col_num, width)

        for row_num in range(1, len(df) + 1):
            worksheet.set_row(row_num, 45)

        if len(df) > 0 and len(col_names) > 0:
            worksheet.autofilter(0, 0, len(df), len(col_names) - 1)
        worksheet.freeze_panes(1, 0)

    buf.seek(0)
    return buf.read()


def render_snapshot_archive_excel_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """Excel de snapshot archivado (mismo layout que export_snapshot_excel)."""
    df = prepare_snapshot_inventory_dataframe(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Inventario", startrow=1, header=False, index=False)
        wb = writer.book
        ws = writer.sheets["Inventario"]
        header_fmt = wb.add_format({
            "bold": True, "bg_color": "#0d6e6e", "font_color": "#ffffff",
            "border": 1, "valign": "vcenter", "align": "center", "font_size": 11,
        })
        cell_fmt = wb.add_format({"border": 1, "valign": "vcenter", "text_wrap": True, "font_size": 10})
        for col_num, col_name in enumerate(df.columns):
            ws.write(0, col_num, col_name, header_fmt)
        ws.set_row(0, 22)
        for i, w in enumerate(SNAPSHOT_EXCEL_COL_WIDTHS[: len(df.columns)]):
            ws.set_column(i, i, w, cell_fmt)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)
        ws.freeze_panes(1, 0)
    return buf.getvalue()
