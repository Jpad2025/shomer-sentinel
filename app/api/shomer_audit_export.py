"""
R12 — Export de auditoría cruzado.
Combina audit_log + incidents + drill_results en un período dado.
Formatos: PDF (resumen ejecutivo) o ZIP (3 CSVs independientes).
GET /audit/report?from=YYYY-MM-DD&to=YYYY-MM-DD&format=pdf|zip
"""
import csv
import io
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.auth_api import require_admin
from app.api.shomer_common import get_config, get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit-export"])

SEVERITY_LABEL = {1: "CRITICO", 2: "ALTO", 3: "MEDIO", 4: "BAJO", 5: "INFO"}


# ──────────────────────────────────────────────
# Recolección de datos
# ──────────────────────────────────────────────

def _iso(date_str: str, end: bool = False) -> str:
    """Convierte YYYY-MM-DD a ISO con hora 00:00 o 23:59:59."""
    suffix = "T23:59:59" if end else "T00:00:00"
    return date_str + suffix if date_str else ""


def _collect(from_iso: str, to_iso: str) -> dict:
    with get_db() as conn:
        audit = conn.execute(
            "SELECT * FROM audit_log WHERE ts BETWEEN ? AND ? ORDER BY ts DESC",
            (from_iso, to_iso),
        ).fetchall()

        incidents = conn.execute(
            "SELECT * FROM incidents WHERE opened_at BETWEEN ? AND ? ORDER BY opened_at DESC",
            (from_iso, to_iso),
        ).fetchall()

        drills = conn.execute(
            "SELECT * FROM drill_results WHERE ran_at BETWEEN ? AND ? ORDER BY ran_at DESC",
            (from_iso, to_iso),
        ).fetchall()

        # Estadísticas agregadas
        audit_users = conn.execute(
            "SELECT username, COUNT(*) as cnt, "
            "SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as errors "
            "FROM audit_log WHERE ts BETWEEN ? AND ? GROUP BY username ORDER BY cnt DESC",
            (from_iso, to_iso),
        ).fetchall()

        audit_paths = conn.execute(
            "SELECT method, path, COUNT(*) as cnt FROM audit_log "
            "WHERE ts BETWEEN ? AND ? GROUP BY method, path ORDER BY cnt DESC LIMIT 10",
            (from_iso, to_iso),
        ).fetchall()

        inc_by_sev = conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM incidents "
            "WHERE opened_at BETWEEN ? AND ? GROUP BY severity ORDER BY severity",
            (from_iso, to_iso),
        ).fetchall()

    return {
        "audit": [dict(r) for r in audit],
        "incidents": [dict(r) for r in incidents],
        "drills": [dict(r) for r in drills],
        "audit_users": [dict(r) for r in audit_users],
        "audit_paths": [dict(r) for r in audit_paths],
        "inc_by_sev": [dict(r) for r in inc_by_sev],
    }


# ──────────────────────────────────────────────
# ZIP — 3 CSVs independientes
# ──────────────────────────────────────────────

def _build_zip(data: dict, period_label: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # 1. audit_log.csv
        a_out = io.StringIO()
        a_fields = ["id", "ts", "username", "role", "method", "path",
                    "status_code", "duration_ms", "body_summary", "ip_client"]
        w = csv.DictWriter(a_out, fieldnames=a_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(data["audit"])
        zf.writestr("audit_log.csv", a_out.getvalue())

        # 2. incidents.csv
        i_out = io.StringIO()
        i_fields = ["id", "ip", "alert_signature", "severity", "blocked_by",
                    "firewall_blocked", "status", "opened_at", "ack_at",
                    "ack_by", "closed_at", "closed_by", "notes"]
        w = csv.DictWriter(i_out, fieldnames=i_fields, extrasaction="ignore")
        w.writeheader()
        for inc in data["incidents"]:
            row = dict(inc)
            row["severity"] = SEVERITY_LABEL.get(row.get("severity", 3), str(row.get("severity", "")))
            w.writerow(row)
        zf.writestr("incidents.csv", i_out.getvalue())

        # 3. drill_results.csv
        d_out = io.StringIO()
        d_fields = ["id", "ran_at", "snapshot_id", "snapshot_short",
                    "success", "duration_sec", "files_restored", "error", "trigger"]
        w = csv.DictWriter(d_out, fieldnames=d_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(data["drills"])
        zf.writestr("drill_results.csv", d_out.getvalue())

        # 4. README.txt con contexto
        site = get_config("base.site_name") or "Shomer Sentinel"
        readme = (
            f"Reporte de auditoria exportado\n"
            f"Sitio: {site}\n"
            f"Periodo: {period_label}\n"
            f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Archivos incluidos:\n"
            f"  audit_log.csv     - Actividad del panel (quien cambio que)\n"
            f"  incidents.csv     - Incidentes de seguridad Hunter\n"
            f"  drill_results.csv - Verificaciones de restauracion de backups\n\n"
            f"Totales del periodo:\n"
            f"  Acciones de panel: {len(data['audit'])}\n"
            f"  Incidentes:        {len(data['incidents'])}\n"
            f"  Drills:            {len(data['drills'])}\n"
        )
        zf.writestr("README.txt", readme)

    return buf.getvalue()


# ──────────────────────────────────────────────
# PDF — resumen ejecutivo cruzado
# ──────────────────────────────────────────────

def _safe(text: str) -> str:
    return (str(text)
            .replace("\u2014", "--").replace("\u2013", "-")
            .replace("\u2019", "'").replace("\u2018", "'")
            .encode("latin-1", errors="replace").decode("latin-1"))


def _fmt_secs(s: int) -> str:
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s//60}m"
    return f"{s//3600}h {(s%3600)//60}m"


def _build_pdf(data: dict, period_label: str) -> bytes:
    from fpdf import FPDF, XPos, YPos

    class PDF(FPDF):
        def header(self):
            self.set_fill_color(15, 23, 42)
            self.rect(0, 0, 210, 18, "F")
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 12)
            self.set_xy(10, 4)
            self.cell(0, 10, "  SHOMER SENTINEL - Reporte de Auditoria")
            self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-11)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5,
                f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  |  "
                f"Pagina {self.page_no()}", align="C")
            self.set_text_color(0, 0, 0)

    def section(pdf, title, color=(30, 58, 138)):
        pdf.ln(5)
        pdf.set_fill_color(*color)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, f"  {_safe(title)}", fill=True,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    def row(pdf, label, value, bold_value=True, value_color=None):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(15)
        pdf.cell(65, 6, _safe(label + ":"))
        if value_color:
            pdf.set_text_color(*value_color)
        pdf.set_font("Helvetica", "B" if bold_value else "", 9)
        pdf.cell(0, 6, _safe(str(value)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    def table_header(pdf, cols, widths):
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(226, 232, 240)
        pdf.set_x(12)
        for col, w in zip(cols, widths):
            pdf.cell(w, 6, _safe(col), fill=True, border=1)
        pdf.ln()

    def table_row(pdf, values, widths, color=None):
        pdf.set_font("Helvetica", "", 8)
        pdf.set_x(12)
        if color:
            pdf.set_text_color(*color)
        for val, w in zip(values, widths):
            pdf.cell(w, 5, _safe(str(val or ""))[:int(w*0.55)], border=1)
        pdf.set_text_color(0, 0, 0)
        pdf.ln()

    site = get_config("base.site_name") or "Shomer Sentinel"
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_margins(10, 22, 10)

    # ── TÍTULO ──
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 9, _safe(period_label), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, _safe(site), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    # ── RESUMEN ──
    section(pdf, "RESUMEN DEL PERIODO")
    row(pdf, "Acciones registradas en panel", len(data["audit"]))
    row(pdf, "Incidentes de seguridad", len(data["incidents"]))
    inc_open = sum(1 for i in data["incidents"] if i.get("status") == "open")
    inc_closed = sum(1 for i in data["incidents"] if i.get("status") == "closed")
    row(pdf, "  Abiertos / Cerrados", f"{inc_open} / {inc_closed}",
        value_color=(220, 38, 38) if inc_open > 0 else None)
    row(pdf, "Drills de restauracion", len(data["drills"]))
    drills_ok = sum(1 for d in data["drills"] if d.get("success"))
    row(pdf, "  Exitosos / Fallidos",
        f"{drills_ok} / {len(data['drills']) - drills_ok}",
        value_color=(22, 163, 74) if drills_ok == len(data["drills"]) and data["drills"] else None)

    # ── ACTIVIDAD PANEL ──
    section(pdf, "ACTIVIDAD DEL PANEL - Auditoria", color=(50, 50, 80))
    audit_errors = sum(1 for a in data["audit"] if (a.get("status_code") or 0) >= 400)
    row(pdf, "Total acciones", len(data["audit"]))
    row(pdf, "Errores (4xx/5xx)", audit_errors,
        value_color=(220, 38, 38) if audit_errors > 5 else None)

    if data["audit_users"]:
        pdf.ln(2)
        pdf.set_x(12)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 5, "Usuarios mas activos:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        table_header(pdf, ["Usuario", "Acciones", "Errores"], [50, 25, 25])
        for u in data["audit_users"][:8]:
            err_color = (220, 38, 38) if (u.get("errors") or 0) > 3 else None
            table_row(pdf, [u["username"], u["cnt"], u.get("errors", 0)],
                      [50, 25, 25])

    if data["audit_paths"]:
        pdf.ln(2)
        pdf.set_x(12)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 5, "Rutas mas usadas:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        table_header(pdf, ["Metodo", "Ruta", "Veces"], [20, 130, 20])
        for p in data["audit_paths"][:8]:
            table_row(pdf, [p["method"], p["path"], p["cnt"]], [20, 130, 20])

    # ── SEGURIDAD ──
    section(pdf, "INCIDENTES DE SEGURIDAD - Hunter", color=(127, 29, 29))
    row(pdf, "Total incidentes", len(data["incidents"]))
    if data["inc_by_sev"]:
        for s in data["inc_by_sev"]:
            lbl = SEVERITY_LABEL.get(s["severity"], str(s["severity"]))
            color = {1:(220,38,38), 2:(234,88,12), 3:(202,138,4)}.get(s["severity"])
            row(pdf, f"  {lbl}", s["cnt"], value_color=color)

    if data["incidents"]:
        pdf.ln(2)
        table_header(pdf,
            ["Firma de alerta", "Sev.", "Por", "Estado", "Abierto"],
            [90, 18, 20, 22, 25])
        for inc in data["incidents"][:20]:
            sev = SEVERITY_LABEL.get(inc.get("severity", 3), "?")
            st  = inc.get("status", "?")[:8]
            opened = (inc.get("opened_at") or "")[:10]
            sig = (inc.get("alert_signature") or "")[:55]
            sev_color = {1:(220,38,38), 2:(234,88,12), 3:(202,138,4)}.get(inc.get("severity"))
            pdf.set_font("Helvetica", "", 8)
            pdf.set_x(12)
            pdf.cell(90, 5, _safe(sig), border=1)
            if sev_color:
                pdf.set_text_color(*sev_color)
            pdf.cell(18, 5, sev[:6], border=1)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(20, 5, _safe(str(inc.get("blocked_by") or ""))[:8], border=1)
            pdf.cell(22, 5, _safe(st), border=1)
            pdf.cell(25, 5, opened, border=1)
            pdf.ln()
        if len(data["incidents"]) > 20:
            pdf.set_font("Helvetica", "I", 7)
            pdf.set_x(12)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 5, f"... y {len(data['incidents'])-20} incidentes mas. Ver CSV para lista completa.")
            pdf.set_text_color(0, 0, 0)
            pdf.ln()

    # ── DRILLS ──
    section(pdf, "VERIFICACION DE BACKUPS - Drills", color=(20, 83, 45))
    row(pdf, "Drills ejecutados", len(data["drills"]))
    row(pdf, "Exitosos", drills_ok,
        value_color=(22,163,74) if drills_ok == len(data["drills"]) and data["drills"] else (220,38,38) if drills_ok < len(data["drills"]) else None)

    if data["drills"]:
        pdf.ln(2)
        table_header(pdf, ["Fecha", "Snapshot", "Archivos", "Duracion", "Resultado"],
                     [28, 22, 22, 22, 25])
        for d in data["drills"]:
            ok = bool(d.get("success"))
            dur = _fmt_secs(d["duration_sec"]) if d.get("duration_sec") else "-"
            files = str(d.get("files_restored") or "-")
            result_str = "OK" if ok else "FALLO"
            result_color = (22,163,74) if ok else (220,38,38)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_x(12)
            pdf.cell(28, 5, (d.get("ran_at") or "")[:10], border=1)
            pdf.cell(22, 5, _safe(str(d.get("snapshot_short") or "-")), border=1)
            pdf.cell(22, 5, files, border=1)
            pdf.cell(22, 5, dur, border=1)
            pdf.set_text_color(*result_color)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(25, 5, result_str, border=1)
            pdf.set_text_color(0, 0, 0)
            pdf.ln()

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


# ──────────────────────────────────────────────
# Endpoint principal
# ──────────────────────────────────────────────

@router.get("/audit/report")
async def audit_report(
    from_date: str = Query(..., alias="from", description="Fecha inicio YYYY-MM-DD"),
    to_date: str   = Query(..., alias="to",   description="Fecha fin YYYY-MM-DD"),
    format: str    = Query("pdf", description="pdf | zip"),
    user=Depends(require_admin),
):
    """
    R12 — Export cruzado: audit_log + incidents + drill_results.
    format=pdf  → PDF resumen ejecutivo
    format=zip  → ZIP con 3 CSVs independientes + README
    """
    try:
        datetime.strptime(from_date, "%Y-%m-%d")
        datetime.strptime(to_date, "%Y-%m-%d")
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Fechas deben ser YYYY-MM-DD")

    from_iso = _iso(from_date, end=False)
    to_iso   = _iso(to_date,   end=True)
    period_label = f"{from_date} al {to_date}"

    data = _collect(from_iso, to_iso)

    if format == "zip":
        content = _build_zip(data, period_label)
        fname = f"auditoria_{from_date}_{to_date}.zip"
        return StreamingResponse(
            iter([content]),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    else:
        content = _build_pdf(data, period_label)
        fname = f"auditoria_{from_date}_{to_date}.pdf"
        return StreamingResponse(
            iter([content]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
