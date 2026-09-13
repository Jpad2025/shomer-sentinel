"""
Etiqueta imprimible Tracker:
  - build_asset_label_pdf   → PDF 90×50 mm individual (1 etiqueta)
  - build_labels_sheet_pdf  → PDF carta con cuadrícula 3×6 = 18 etiquetas/hoja (52×30 mm c/u)
Sin FastAPI. Código de barras Code128 (IP) via python-barcode + pillow.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List

from fpdf import FPDF

_PLACEHOLDER = "-"


def _make_barcode_bytes(text: str) -> bytes:
    """Code128 PNG en memoria. Devuelve b'' si falla."""
    if not text:
        return b""
    try:
        import barcode
        from barcode.writer import ImageWriter
        buf = io.BytesIO()
        barcode.get_barcode_class("code128")(text, writer=ImageWriter()).write(
            buf,
            options={"write_text": False, "module_height": 8.0, "quiet_zone": 2.0},
        )
        buf.seek(0)
        return buf.read()
    except Exception:
        return b""


def _fpdf_safe(s: str, max_len: int | None = None) -> str:
    """Texto seguro para pdf.cell con fuentes core (Latin-1)."""
    t = (s or "").strip()
    if max_len is not None:
        t = t[:max_len]
    t = t.replace("\u2014", _PLACEHOLDER).replace("\u2013", _PLACEHOLDER)
    t = t.replace("\u2018", "'").replace("\u2019", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    return t.encode("latin-1", errors="replace").decode("latin-1") or _PLACEHOLDER


def _fmt_date(raw: str) -> str:
    """Extrae YYYY-MM-DD de timestamp SQLite 'YYYY-MM-DD HH:MM:SS'."""
    return (raw or "").strip()[:10]


def _get_site_name() -> str:
    """Lee base.client_name desde system_state. Devuelve '' si no existe."""
    try:
        from app.backend.db import get_connection
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT value FROM system_state WHERE key = 'base.client_name' LIMIT 1"
            )
            row = cur.fetchone()
            return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


# ── Etiqueta individual 90×50 mm ─────────────────────────────────────────────

def build_asset_label_pdf(asset: Dict[str, Any], num: int = 1) -> bytes:
    """PDF 90×50 mm solo texto: nombre sitio + datos + RAM/disco/ubicación/mantenimiento."""
    site_name = _get_site_name() or "SHOMER SENTINEL"

    pdf = FPDF(orientation="P", unit="mm", format=(90, 50))
    pdf.set_auto_page_break(False)
    pdf.add_page()

    # Encabezado oscuro
    pdf.set_fill_color(30, 30, 30)
    pdf.rect(0, 0, 90, 7, "F")
    pdf.set_font("Helvetica", "B", 6)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(2, 1)
    pdf.cell(60, 5, _fpdf_safe(site_name, 48), align="L")
    num_str = "#%03d" % num if num else ""
    if num_str:
        pdf.set_xy(60, 1)
        pdf.cell(28, 5, num_str, align="R")
    pdf.set_text_color(0, 0, 0)

    # Datos — columna completa
    hostname = _fpdf_safe(asset.get("hostname") or "", 50)
    ip       = _fpdf_safe(asset.get("ip") or "", 40)
    mac      = _fpdf_safe(asset.get("mac") or "", 24)
    tipo     = _fpdf_safe(asset.get("asset_type") or "", 40)
    modelo   = _fpdf_safe(asset.get("asset_model") or "", 50)
    serial   = _fpdf_safe(asset.get("serial_number") or "", 40)
    cpu      = _fpdf_safe(asset.get("cpu") or "", 55)
    ram      = _fpdf_safe(asset.get("ram") or "", 30)
    disco    = _fpdf_safe(asset.get("storage_cap") or "", 30)
    ubicac   = _fpdf_safe(asset.get("location") or "", 50)
    mant     = _fmt_date(asset.get("last_maintenance") or "")
    fecha    = _fmt_date(asset.get("last_audit") or "")

    lx, tw = 3.0, 84.0
    y = 9.0

    pdf.set_xy(lx, y)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(tw, 4.5, hostname)
    y += 4.5

    pdf.set_xy(lx, y)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.cell(tw, 3.5, "IP: " + ip + "   MAC: " + mac)
    y += 3.5

    pdf.set_xy(lx, y)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(tw, 3, tipo + ("  |  " + modelo if modelo and modelo != _PLACEHOLDER else ""))
    pdf.set_text_color(0, 0, 0)
    y += 3

    if serial and serial != _PLACEHOLDER:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(tw, 3, "S/N: " + serial)
        pdf.set_text_color(0, 0, 0)
        y += 3

    # RAM / Disco
    hw_parts = []
    if ram and ram != _PLACEHOLDER:
        hw_parts.append("RAM: " + ram)
    if disco and disco != _PLACEHOLDER:
        hw_parts.append("Disco: " + disco)
    if hw_parts:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(tw, 3, "   ".join(hw_parts))
        y += 3

    if cpu and cpu != _PLACEHOLDER:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(tw, 3, "CPU: " + cpu)
        pdf.set_text_color(0, 0, 0)
        y += 3

    if ubicac and ubicac != _PLACEHOLDER:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(tw, 3, "Ubicacion: " + ubicac)
        y += 3

    if mant:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(tw, 3, "Ult. mant.: " + mant)
        pdf.set_text_color(0, 0, 0)
        y += 3

    # Código de barras Code128 (IP) — zona fija y=39..45
    bc_bytes = _make_barcode_bytes(ip or mac)
    if bc_bytes:
        pdf.image(io.BytesIO(bc_bytes), x=lx, y=39, w=tw, h=6)

    if fecha:
        pdf.set_xy(lx, 46)
        pdf.set_font("Helvetica", "", 5.5)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(tw, 3, "Inv.: " + fecha, align="R")
        pdf.set_text_color(0, 0, 0)

    out = pdf.output()
    return bytes(out) if out else b""


# ── Hoja de etiquetas — carta 3×6 (18 etiquetas de 52×30 mm) ─────────────────

_CARTA_W = 215.9
_CARTA_H = 279.4

_MARGIN_LEFT = 9.95
_MARGIN_TOP  = 10.7

_LBL_W = 52.0
_LBL_H = 30.0

_GAP_X = 3.0
_GAP_Y = 3.0

_COLS = 3
_ROWS = 6


def _draw_one_label(
    pdf: FPDF,
    asset: Dict[str, Any],
    x0: float,
    y0: float,
    num: int = 0,
    site_name: str = "",
) -> None:
    """Dibuja etiqueta de 52×30 mm en (x0, y0). Solo texto, sin QR."""
    # Borde
    pdf.set_draw_color(180, 180, 180)
    pdf.rect(x0, y0, _LBL_W, _LBL_H)
    pdf.set_draw_color(0, 0, 0)

    # Franja encabezado oscura
    pdf.set_fill_color(30, 30, 30)
    pdf.rect(x0, y0, _LBL_W, 5.5, "F")

    num_str = "#%03d" % num if num else "# -"
    pdf.set_font("Helvetica", "B", 5.5)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(x0 + 1.5, y0 + 0.8)
    pdf.cell(12, 4, num_str, align="L")

    header_text = _fpdf_safe(site_name or "SHOMER SENTINEL", 28)
    pdf.set_font("Helvetica", "", 4.5)
    pdf.set_xy(x0 + 14, y0 + 0.8)
    pdf.cell(_LBL_W - 16, 4, header_text, align="R")
    pdf.set_text_color(0, 0, 0)

    # Datos — ancho completo
    lx = x0 + 1.5
    tw = _LBL_W - 3.0
    y = y0 + 6.5

    hostname = _fpdf_safe(asset.get("hostname") or "", 32)
    ip       = _fpdf_safe(asset.get("ip") or "", 18)
    mac      = _fpdf_safe(asset.get("mac") or "", 17)
    tipo     = _fpdf_safe(asset.get("asset_type") or "", 24)
    modelo   = _fpdf_safe(asset.get("asset_model") or "", 26)
    serial   = _fpdf_safe(asset.get("serial_number") or "", 22)
    cpu      = _fpdf_safe(asset.get("cpu") or "", 36)
    ram      = _fpdf_safe(asset.get("ram") or "", 16)
    disco    = _fpdf_safe(asset.get("storage_cap") or "", 16)
    ubicac   = _fpdf_safe(asset.get("location") or "", 28)
    mant     = _fmt_date(asset.get("last_maintenance") or "")
    fecha    = _fmt_date(asset.get("last_audit") or "")

    pdf.set_xy(lx, y)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.cell(tw, 3.3, hostname)
    y += 3.3

    pdf.set_xy(lx, y)
    pdf.set_font("Helvetica", "", 5.0)
    pdf.cell(tw, 2.6, ip + "  " + mac)
    y += 2.6

    tipo_modelo = tipo
    if modelo and modelo != _PLACEHOLDER:
        tipo_modelo = tipo + " / " + modelo
    pdf.set_xy(lx, y)
    pdf.set_font("Helvetica", "I", 4.8)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(tw, 2.5, tipo_modelo[:38])
    pdf.set_text_color(0, 0, 0)
    y += 2.5

    if serial and serial != _PLACEHOLDER:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 4.5)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(tw, 2.3, "S/N: " + serial)
        pdf.set_text_color(0, 0, 0)
        y += 2.3

    hw_parts = []
    if ram and ram != _PLACEHOLDER:
        hw_parts.append("RAM " + ram)
    if disco and disco != _PLACEHOLDER:
        hw_parts.append("Disco " + disco)
    if hw_parts:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 4.8)
        pdf.cell(tw, 2.4, "  ".join(hw_parts))
        y += 2.4

    if cpu and cpu != _PLACEHOLDER:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 4.3)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(tw, 2.2, "CPU: " + cpu)
        pdf.set_text_color(0, 0, 0)
        y += 2.2

    if ubicac and ubicac != _PLACEHOLDER:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 4.8)
        pdf.cell(tw, 2.4, "Ubic: " + ubicac)
        y += 2.4

    if mant:
        pdf.set_xy(lx, y)
        pdf.set_font("Helvetica", "", 4.3)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(tw, 2.3, "Mant.: " + mant)
        pdf.set_text_color(0, 0, 0)
        y += 2.3

    # Código de barras Code128 (IP) — posición dinámica tras el último campo
    bc_bytes = _make_barcode_bytes(ip or mac)
    inv_y = y0 + _LBL_H - 3.8
    bc_h = 3.5
    bc_y = y + 0.4
    if bc_bytes and bc_y + bc_h + 0.3 <= inv_y:
        pdf.image(io.BytesIO(bc_bytes), x=lx, y=bc_y, w=tw, h=bc_h)

    if fecha:
        pdf.set_xy(lx, inv_y)
        pdf.set_font("Helvetica", "", 4.0)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(tw, 3, "Inv.: " + fecha, align="R")
        pdf.set_text_color(0, 0, 0)


def build_labels_sheet_pdf(assets: List[Dict[str, Any]]) -> bytes:
    """
    PDF tamaño carta 3×6 (18 etiquetas de 52×30 mm por hoja).
    Cada etiqueta lleva número secuencial #001, #002... y nombre del hotel.
    Sin QR ni código de barras.
    """
    if not assets:
        return b""

    site_name = _get_site_name()

    pdf = FPDF(orientation="P", unit="mm", format=(_CARTA_W, _CARTA_H))
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)

    idx = 0
    total = len(assets)

    while idx < total:
        pdf.add_page()
        for row in range(_ROWS):
            for col in range(_COLS):
                if idx >= total:
                    break
                x0 = _MARGIN_LEFT + col * (_LBL_W + _GAP_X)
                y0 = _MARGIN_TOP  + row * (_LBL_H + _GAP_Y)
                _draw_one_label(pdf, assets[idx], x0, y0, num=idx + 1, site_name=site_name)
                idx += 1

    out = pdf.output()
    return bytes(out) if out else b""
