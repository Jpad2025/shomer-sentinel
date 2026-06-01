"""
Reporte PDF de un activo (hardware + notas + resto de campos).
Sin FastAPI (refactor por bloques desde inventory.py).
"""
from __future__ import annotations

from typing import Any, Dict

from fpdf import FPDF

_ASSET_REPORT_HARDWARE_KEYS = frozenset(
    {
        "mac",
        "ip",
        "hostname",
        "asset_type",
        "asset_model",
        "cpu",
        "ram",
        "storage_cap",
        "os_detected",
        "os_family",
        "os_version",
        "serial_number",
        "firmware_version",
        "last_audit",
        "software_list",
    }
)


def build_asset_report_pdf_bytes(a: Dict[str, Any]) -> bytes:
    """Reporte formal de un activo (mismo contenido que export /asset/pdf/{ip})."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, "Reporte de Activo IT", ln=1)
    pdf.set_font("Arial", "", 10)
    pdf.ln(4)
    header_lines = [
        f"IP: {a.get('ip')}",
        f"MAC: {a.get('mac')}",
        f"Hostname: {a.get('hostname')}",
        f"Tipo de activo: {a.get('asset_type')}",
        f"Modelo: {a.get('asset_model')}",
        f"CPU: {a.get('cpu')}",
        f"RAM: {a.get('ram')}",
        f"Disco: {a.get('storage_cap')}",
        f"Sistema Operativo: {a.get('os_detected') or a.get('os_family')}",
        f"Serial: {a.get('serial_number')}",
        f"Firmware: {a.get('firmware_version')}",
        f"Última auditoría: {a.get('last_audit')}",
    ]
    for line in header_lines:
        pdf.cell(0, 6, line or "", ln=1)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 6, "Notas internas:", ln=1)
    pdf.set_font("Arial", "", 10)
    notes = (a.get("internal_notes") or "").strip() or "(sin notas)"
    for p in notes.splitlines():
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, p)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 6, "Campos administrativos:", ln=1)
    pdf.set_font("Arial", "", 10)
    for key in sorted(a.keys()):
        if key in _ASSET_REPORT_HARDWARE_KEYS:
            continue
        value = "" if a.get(key) is None else str(a.get(key))
        label = key.replace("_", " ").capitalize()
        # multi_cell puede dejar x al borde derecho; cada campo desde margen izquierdo.
        pdf.set_x(pdf.l_margin)
        text = f"{label}: {value}"
        text = text.encode("latin-1", errors="replace").decode("latin-1")
        pdf.multi_cell(0, 5, text)

    out = pdf.output()
    if out is None:
        return b""
    return bytes(out)
