"""
R1 — Reporte mensual PDF.
Genera el día 1 de cada mes a las 03:00 hora local.
Fuentes: incidentes (R2), drills (R3), Guardian, Hunter, auditoría (R8), servidor.
Envía por Telegram y guarda en /srv/shomer_reports/.
Trigger manual vía POST /reports/generate.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel


class ReportRangeRequest(BaseModel):
    from_date: str | None = None
    to_date: str | None = None


def _custom_range(from_date: str, to_date: str) -> tuple[str, str, str]:
    """Construye (label, from_iso, to_iso) desde fechas YYYY-MM-DD."""
    import calendar as _cal
    from datetime import date
    d0 = date.fromisoformat(from_date)
    d1 = date.fromisoformat(to_date)
    label = f"{d0.strftime('%-d %b')} – {d1.strftime('%-d %b %Y')}"
    return label, f"{from_date}T00:00:00", f"{to_date}T23:59:59"

from fastapi import Query
from fastapi.responses import StreamingResponse
from app.api.auth_api import require_admin
from app.api.shomer_common import get_config, get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])

REPORTS_DIR = "/srv/shomer_reports"
_report_running = False

# ──────────────────────────────────────────────
# Helpers de datos
# ──────────────────────────────────────────────

def _prev_month_range(now: datetime) -> tuple[str, str, str]:
    """Retorna (label 'Abril 2026', from_iso, to_iso) del mes anterior."""
    import calendar
    year, month = now.year, now.month - 1
    if month == 0:
        month, year = 12, year - 1
    last_day = calendar.monthrange(year, month)[1]
    label = f"{_month_name(month)} {year}"
    from_iso = f"{year:04d}-{month:02d}-01T00:00:00"
    to_iso   = f"{year:04d}-{month:02d}-{last_day:02d}T23:59:59"
    return label, from_iso, to_iso


def _month_name(m: int) -> str:
    names = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    return names[m]


def _collect_data(from_iso: str, to_iso: str) -> dict:
    """Recopila todas las métricas del período para el reporte."""
    data = {}
    with get_db() as conn:

        def _count(sql, params=()):
            try:
                return conn.execute(sql, params).fetchone()[0] or 0
            except Exception:
                return 0

        def _fetchall(sql, params=()):
            try:
                return conn.execute(sql, params).fetchall()
            except Exception:
                return []

        def _fetchone_dict(sql, params=()):
            try:
                row = conn.execute(sql, params).fetchone()
                return dict(row) if row else None
            except Exception:
                return None

        # — Incidentes —
        data["inc_total"]  = _count("SELECT COUNT(*) FROM incidents WHERE opened_at BETWEEN ? AND ?", (from_iso, to_iso))
        data["inc_open"]   = _count("SELECT COUNT(*) FROM incidents WHERE status='open' AND opened_at BETWEEN ? AND ?", (from_iso, to_iso))
        data["inc_closed"] = _count("SELECT COUNT(*) FROM incidents WHERE status='closed' AND opened_at BETWEEN ? AND ?", (from_iso, to_iso))
        try:
            mtta_row = conn.execute(
                "SELECT AVG((julianday(ack_at)-julianday(opened_at))*86400) FROM incidents "
                "WHERE ack_at IS NOT NULL AND opened_at BETWEEN ? AND ?", (from_iso, to_iso)
            ).fetchone()[0]
            mttr_row = conn.execute(
                "SELECT AVG((julianday(closed_at)-julianday(opened_at))*86400) FROM incidents "
                "WHERE closed_at IS NOT NULL AND opened_at BETWEEN ? AND ?", (from_iso, to_iso)
            ).fetchone()[0]
        except Exception:
            mtta_row = mttr_row = None
        data["inc_mtta"] = _fmt_secs(int(mtta_row)) if mtta_row else "N/A"
        data["inc_mttr"] = _fmt_secs(int(mttr_row)) if mttr_row else "N/A"
        data["inc_top"] = _fetchall(
            "SELECT alert_signature, COUNT(*) as cnt FROM incidents "
            "WHERE opened_at BETWEEN ? AND ? GROUP BY alert_signature ORDER BY cnt DESC LIMIT 5",
            (from_iso, to_iso)
        )

        # — Bloqueos Hunter —
        data["blocks_total"]    = _count("SELECT COUNT(*) FROM blocked_ips WHERE blocked_at BETWEEN ? AND ?", (from_iso, to_iso))
        data["blocks_firewall"] = _count("SELECT COUNT(*) FROM blocked_ips WHERE firewall_blocked=1 AND blocked_at BETWEEN ? AND ?", (from_iso, to_iso))
        data["blocks_rows"] = _fetchall(
            "SELECT ip, blocked_at, alert_signature, unblocked_at FROM blocked_ips "
            "WHERE blocked_at BETWEEN ? AND ? ORDER BY blocked_at DESC LIMIT 50",
            (from_iso, to_iso)
        )

        # — Auditoría de red (hallazgos) —
        data["net_findings"] = _fetchall(
            "SELECT ip, port, protocol, service, title, severity, finding_status, recommendation "
            "FROM network_audit_findings "
            "WHERE found_at BETWEEN ? AND ? "
            "ORDER BY CASE severity WHEN 'critico' THEN 1 WHEN 'alto' THEN 2 WHEN 'medio' THEN 3 WHEN 'bajo' THEN 4 ELSE 5 END, ip",
            (from_iso, to_iso)
        )
        data["net_scans"] = _fetchall(
            "SELECT started_at, finished_at, status, total_hosts, findings_count "
            "FROM network_audit_scans WHERE started_at BETWEEN ? AND ? ORDER BY started_at DESC LIMIT 10",
            (from_iso, to_iso)
        )

        # — Drills —
        data["drill_total"] = _count("SELECT COUNT(*) FROM drill_results WHERE ran_at BETWEEN ? AND ?", (from_iso, to_iso))
        data["drill_ok"]    = _count("SELECT COUNT(*) FROM drill_results WHERE success=1 AND ran_at BETWEEN ? AND ?", (from_iso, to_iso))
        data["drill_last"]  = _fetchone_dict("SELECT * FROM drill_results WHERE ran_at BETWEEN ? AND ? ORDER BY ran_at DESC LIMIT 1", (from_iso, to_iso))

        # — Auditoría panel —
        data["audit_total"]     = _count("SELECT COUNT(*) FROM audit_log WHERE ts BETWEEN ? AND ?", (from_iso, to_iso))
        data["audit_errors"]    = _count("SELECT COUNT(*) FROM audit_log WHERE status_code >= 400 AND ts BETWEEN ? AND ?", (from_iso, to_iso))
        data["audit_top_users"] = _fetchall(
            "SELECT username, COUNT(*) as cnt FROM audit_log WHERE ts BETWEEN ? AND ? "
            "GROUP BY username ORDER BY cnt DESC LIMIT 5", (from_iso, to_iso)
        )

        # — Nodos Guardian (estado actual) —
        data["nodes_online"] = _count("SELECT COUNT(*) FROM infra_nodes WHERE status='online'")
        data["nodes_total"]  = _count("SELECT COUNT(*) FROM infra_nodes")
        data["nodes"] = _fetchall(
            "SELECT n.ip_address, n.status, n.latency_ms, d.name, d.location "
            "FROM infra_nodes n LEFT JOIN devices d ON d.ip_address=n.ip_address"
        )

        # — Inframonitor (estado actual) —
        data["infra_online"] = _count(
            "SELECT COUNT(DISTINCT d.ip) FROM infra_devices d "
            "JOIN infra_status s ON d.ip=s.ip WHERE d.active=1 AND s.status='online'"
        )
        data["infra_total"] = _count("SELECT COUNT(*) FROM infra_devices WHERE active=1")

    # — Servidor —
    try:
        import psutil
        data["cpu"] = psutil.cpu_percent(interval=0.5)
        vm = psutil.virtual_memory()
        data["ram"] = round(vm.percent, 1)
        data["ram_gb"] = f"{round(vm.used/1e9,1)}/{round(vm.total/1e9,1)} GB"
        disks = []
        for path, label in [("/", "OS"), ("/srv", "Backups"), ("/var", "Logs")]:
            try:
                u = psutil.disk_usage(path)
                disks.append((label, u.percent, round(u.free/1e9, 1)))
            except Exception:
                pass
        data["disks"] = disks
    except Exception:
        data["cpu"] = data["ram"] = 0
        data["ram_gb"] = "N/A"
        data["disks"] = []

    data["site_name"] = get_config("base.site_name") or get_config("base.hostname") or "Shomer Sentinel"
    data["hostname"] = get_config("base.hostname") or "shomer"
    return data


def _fmt_secs(s: int) -> str:
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s//60}m"
    return f"{s//3600}h {(s%3600)//60}m"


# ──────────────────────────────────────────────
# Generador PDF
# ──────────────────────────────────────────────

def _safe(text: str) -> str:
    """Reemplaza caracteres fuera de Latin-1 para compatibilidad con Helvetica."""
    return (str(text)
            .replace("\u2014", "--").replace("\u2013", "-")  # em/en dash
            .replace("\u2019", "'").replace("\u2018", "'")    # comillas curvas
            .replace("\u201c", '"').replace("\u201d", '"')
            .encode("latin-1", errors="replace").decode("latin-1"))


def _generate_pdf(period_label: str, data: dict, out_path: str) -> str:
    from fpdf import FPDF, XPos, YPos

    class PDF(FPDF):
        def header(self):
            self.set_fill_color(15, 23, 42)
            self.rect(0, 0, 210, 20, "F")
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 14)
            self.set_xy(10, 5)
            self.cell(0, 10, "  SHOMER SENTINEL - Reporte Mensual", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 5, f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  |  Página {self.page_no()}", align="C")
            self.set_text_color(0, 0, 0)

    def section(pdf, title: str, color=(30, 58, 138)):
        pdf.ln(4)
        pdf.set_fill_color(*color)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, f"  {_safe(title)}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    def kv(pdf, label: str, value: str, value_color=None):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(15)
        pdf.cell(60, 6, _safe(label + ":"))
        if value_color:
            pdf.set_text_color(*value_color)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, _safe(str(value)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    def status_color(ok: bool):
        return (22, 163, 74) if ok else (220, 38, 38)

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(10, 22, 10)

    # ── TÍTULO ──
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 10, _safe(period_label), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, _safe(data["site_name"]), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # ── RESUMEN EJECUTIVO ──
    section(pdf, "RESUMEN EJECUTIVO")
    nodes_ok = data["nodes_online"] == data["nodes_total"] and data["nodes_total"] > 0
    infra_ok = data["infra_total"] == 0 or data["infra_online"] == data["infra_total"]
    drill_ok  = data["drill_total"] == 0 or data["drill_ok"] > 0
    sec_ok    = data["inc_open"] == 0

    summary_items = [
        ("Red Guardian", f"{data['nodes_online']}/{data['nodes_total']} nodos en linea", nodes_ok),
        ("Inframonitor",  f"{data['infra_online']}/{data['infra_total']} equipos en linea", infra_ok),
        ("Seguridad",     f"{data['inc_total']} incidentes, {data['inc_open']} abiertos", sec_ok),
        ("Backups drill", f"{data['drill_ok']}/{data['drill_total']} drills exitosos", drill_ok),
    ]
    for label, value, ok in summary_items:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(15)
        icon = "[OK]" if ok else "[ATENCION]"
        color = (22, 163, 74) if ok else (220, 38, 38)
        pdf.set_text_color(*color)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(20, 6, icon)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(50, 6, _safe(label + ":"))
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, _safe(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── SEGURIDAD — HUNTER ──
    section(pdf, "SEGURIDAD — Hunter", color=(127, 29, 29))
    kv(pdf, "Total bloqueos", str(data["blocks_total"]))
    kv(pdf, "  con firewall efectivo", str(data["blocks_firewall"]))
    kv(pdf, "Incidentes creados", str(data["inc_total"]))
    kv(pdf, "  cerrados", str(data["inc_closed"]),
       value_color=(22,163,74) if data["inc_closed"] == data["inc_total"] and data["inc_total"] > 0 else None)
    kv(pdf, "  abiertos", str(data["inc_open"]),
       value_color=(220,38,38) if data["inc_open"] > 0 else (100,100,100))
    kv(pdf, "MTTA (tiempo hasta ack)", data["inc_mtta"])
    kv(pdf, "MTTR (tiempo hasta cierre)", data["inc_mttr"])

    if data["inc_top"]:
        pdf.ln(2)
        pdf.set_x(15)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 5, "Amenazas mas frecuentes:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for row in data["inc_top"]:
            pdf.set_x(20)
            sig = _safe(str(row["alert_signature"] or "")[:70])
            pdf.cell(0, 5, f"- {sig}  ({row['cnt']}x)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    # ── BACKUPS & DRILLS ──
    section(pdf, "BACKUPS Y VERIFICACIÓN — Protector", color=(20, 83, 45))
    kv(pdf, "Drills ejecutados", str(data["drill_total"]))
    kv(pdf, "Drills exitosos", str(data["drill_ok"]),
       value_color=status_color(drill_ok))
    kv(pdf, "Drills fallidos", str(data["drill_total"] - data["drill_ok"]),
       value_color=(220,38,38) if data["drill_total"] - data["drill_ok"] > 0 else (100,100,100))
    if data["drill_last"]:
        d = data["drill_last"]
        kv(pdf, "Último drill", d.get("ran_at", "")[:10])
        kv(pdf, "  snapshot", (d.get("snapshot_short") or "?"))
        kv(pdf, "  archivos restaurados", str(d.get("files_restored") or "N/A"))
        kv(pdf, "  duración", _fmt_secs(d["duration_sec"]) if d.get("duration_sec") else "N/A")

    # ── RED — GUARDIAN ──
    section(pdf, "RED — Guardian", color=(30, 58, 138))
    kv(pdf, "Nodos monitoreados", str(data["nodes_total"]))
    kv(pdf, "En línea ahora", str(data["nodes_online"]),
       value_color=status_color(nodes_ok))
    if data["nodes"]:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_x(15)
        pdf.set_fill_color(226, 232, 240)
        pdf.cell(55, 5, "Nombre", fill=True)
        pdf.cell(30, 5, "Estado", fill=True)
        pdf.cell(30, 5, "Latencia", fill=True)
        pdf.cell(0,  5, "Ubicación", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for n in data["nodes"]:
            st = n["status"] or "?"
            color = (22,163,74) if st == "online" else (220,38,38)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_x(15)
            pdf.cell(55, 5, _safe(str(n["name"] or n["ip_address"] or "")[:35]))
            pdf.set_text_color(*color)
            pdf.cell(30, 5, _safe(st))
            pdf.set_text_color(0, 0, 0)
            lat = f"{n['latency_ms']:.1f} ms" if n["latency_ms"] is not None else "-"
            pdf.cell(30, 5, lat)
            pdf.cell(0,  5, _safe(str(n["location"] or "")[:30]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if data["infra_total"] > 0:
        pdf.ln(2)
        kv(pdf, "Inframonitor — equipos", str(data["infra_total"]))
        kv(pdf, "  en línea", str(data["infra_online"]),
           value_color=status_color(infra_ok))

    # ── SERVIDOR ──
    section(pdf, "SERVIDOR", color=(67, 20, 140))
    kv(pdf, "CPU (actual)", f"{data['cpu']}%",
       value_color=(220,38,38) if data["cpu"] > 85 else None)
    kv(pdf, "RAM (actual)", f"{data['ram']}%  ({data['ram_gb']})",
       value_color=(220,38,38) if data["ram"] > 85 else None)
    for label, pct, free_gb in data.get("disks", []):
        color = (220,38,38) if pct > 85 else (245,158,11) if pct > 70 else None
        kv(pdf, f"Disco {label}", f"{pct}%  ({free_gb} GB libres)", value_color=color)

    # ── ACTIVIDAD DEL PANEL — AUDITORÍA ──
    if data["audit_total"] > 0:
        section(pdf, "ACTIVIDAD DEL PANEL — Auditoría", color=(50, 50, 80))
        kv(pdf, "Total acciones registradas", str(data["audit_total"]))
        kv(pdf, "Errores (4xx/5xx)", str(data["audit_errors"]),
           value_color=(220,38,38) if data["audit_errors"] > 10 else None)
        if data["audit_top_users"]:
            pdf.ln(2)
            pdf.set_x(15)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 5, "Usuarios mas activos:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            for row in data["audit_top_users"]:
                pdf.set_x(20)
                pdf.cell(0, 5, f"- {_safe(row['username'])}  ({row['cnt']} acciones)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)

    # ── AUDITORÍA DE RED ──
    net_findings = data.get("net_findings", [])
    if net_findings:
        section(pdf, "AUDITORÍA DE RED — Hallazgos", color=(20, 83, 45))
        sev_counts: dict = {}
        for f in net_findings:
            sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
        kv(pdf, "Total hallazgos", str(len(net_findings)))
        for sev, label in [("critico","Críticos"), ("alto","Altos"), ("medio","Medios"), ("bajo","Bajos"), ("info","Info")]:
            if sev_counts.get(sev, 0) > 0:
                color_map = {"critico":(220,38,38),"alto":(234,88,12),"medio":(161,120,24),"bajo":(37,99,235),"info":(100,100,100)}
                kv(pdf, f"  {label}", str(sev_counts[sev]), value_color=color_map[sev])

        scans = data.get("net_scans", [])
        if scans:
            kv(pdf, "Escaneos en el período", str(len(scans)))

        pdf.ln(2)
        # Tabla de hallazgos
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(30, 42, 58)
        pdf.set_text_color(255, 255, 255)
        col_w = [28, 22, 18, 20, 102]
        headers = ["IP", "Puerto", "Severidad", "Estado", "Hallazgo / Cómo resolverlo"]
        for i, h in enumerate(headers):
            ln = (i == len(headers) - 1)
            pdf.cell(col_w[i], 5, h, border=1, fill=True, new_x=XPos.LMARGIN if ln else XPos.RIGHT, new_y=YPos.NEXT if ln else YPos.TOP)

        SEV_COLORS = {"critico":(220,38,38),"alto":(234,88,12),"medio":(161,120,24),"bajo":(37,99,235),"info":(100,100,100)}
        for f in net_findings:
            clr = SEV_COLORS.get(f["severity"], (100,100,100))
            port_str = f'{f["port"]}/{f["protocol"] or "tcp"}' if f["port"] else "--"
            title = _safe((f["title"] or "")[:40])
            rec   = _safe((f["recommendation"] or "—")[:80])
            row_text = f"{title}  |  {rec}"

            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(6, 182, 212)
            pdf.cell(col_w[0], 5, _safe(f["ip"]), border=1)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(col_w[1], 5, port_str, border=1)
            pdf.set_text_color(*clr)
            pdf.cell(col_w[2], 5, (f["severity"] or "").upper(), border=1)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(col_w[3], 5, _safe(f["finding_status"] or "—"), border=1)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(col_w[4], 5, row_text, border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── BLOQUEOS HUNTER DETALLE ──
    blocks_rows = data.get("blocks_rows", [])
    if blocks_rows:
        section(pdf, "BLOQUEOS HUNTER — Detalle", color=(127, 29, 29))
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(30, 42, 58)
        pdf.set_text_color(255, 255, 255)
        for h, w in [("IP", 35), ("Bloqueado", 38), ("Firma", 95), ("Desbloqueado", 22)]:
            pdf.cell(w, 5, h, border=1, fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        for row in blocks_rows:
            pdf.set_font("Helvetica", "", 7)
            pdf.cell(35, 5, _safe(row["ip"] or ""), border=1)
            pdf.cell(38, 5, _safe((row["blocked_at"] or "")[:16]), border=1)
            pdf.cell(95, 5, _safe((row["alert_signature"] or "—")[:55]), border=1)
            unbl = "Sí" if row["unblocked_at"] else "No"
            pdf.cell(22, 5, unbl, border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    pdf.output(out_path)
    return out_path


# ──────────────────────────────────────────────
# Telegram — envía el PDF como documento
# ──────────────────────────────────────────────

def _send_report_telegram(pdf_path: str, period_label: str, data: dict):
    try:
        from app.api.shomer_common import get_config as _gc
        import requests as _req
        token = _gc("guardian.telegram_token")
        chat  = _gc("guardian.telegram_chat_id")
        if not token or not chat:
            logger.warning("Telegram no configurado — reporte PDF no enviado")
            return
        caption = (
            f"📊 <b>Reporte mensual — {period_label}</b>\n"
            f"🛡️ {data['site_name']}\n"
            f"🔴 Incidentes: {data['inc_total']} ({data['inc_open']} abiertos)\n"
            f"🔒 Bloqueos: {data['blocks_total']}\n"
            f"💾 Drills: {data['drill_ok']}/{data['drill_total']} OK"
        )
        with open(pdf_path, "rb") as f:
            _req.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat, "caption": caption, "parse_mode": "HTML"},
                files={"document": f},
                timeout=30,
            )
    except Exception as e:
        logger.warning("report telegram error: %s", e)


# ──────────────────────────────────────────────
# Runner principal (blocking → asyncio.to_thread)
# ──────────────────────────────────────────────

def _run_report_blocking(now: Optional[datetime] = None, trigger: str = "scheduled") -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    period_label, from_iso, to_iso = _prev_month_range(now)
    filename = f"shomer_report_{period_label.replace(' ', '_').lower()}.pdf"
    out_path = os.path.join(REPORTS_DIR, filename)

    try:
        data = _collect_data(from_iso, to_iso)
        _generate_pdf(period_label, data, out_path)
        _send_report_telegram(out_path, period_label, data)
        return {
            "success": True,
            "period": period_label,
            "path": out_path,
            "filename": filename,
            "trigger": trigger,
        }
    except Exception as e:
        logger.error("report generation error: %s", e)
        return {"success": False, "error": str(e)[:400], "trigger": trigger}


# ──────────────────────────────────────────────
# Scheduler mensual
# ──────────────────────────────────────────────

_report_scheduler_running = False


async def _report_scheduler_loop():
    """Día 1 de cada mes a las 03:05 hora local (5 min después del drill)."""
    while True:
        try:
            from app.api.backups import _scheduler_now
            now = _scheduler_now()
            if now.day == 1 and now.hour == 3 and now.minute == 5:
                from app.api.shomer_common import get_config, set_config
                today_str = now.strftime("%Y-%m-%d")
                if get_config("reports.last_run") != today_str:
                    set_config("reports.last_run", today_str)
                    logger.info("Reporte mensual iniciando — %s", today_str)
                    result = await asyncio.to_thread(_run_report_blocking, now, "scheduled")
                    logger.info("Reporte mensual: %s", result)
        except Exception as e:
            logger.error("report scheduler error: %s", e)
        await asyncio.sleep(60)


def start_report_scheduler():
    """shomer-tools.service corre --workers 2 -- solo el worker líder (`reports`) corre
    este loop, para no generar el reporte mensual duplicado (ver CLAUDE.md §AZ)."""
    global _report_scheduler_running
    if _report_scheduler_running:
        return
    from app.api.shomer_poller_leader import try_acquire_poller_leader
    if not try_acquire_poller_leader("reports"):
        logger.info("Report scheduler: worker pid=%s omitido — otro worker es líder", os.getpid())
        return
    _report_scheduler_running = True
    asyncio.create_task(_report_scheduler_loop())
    logger.info("Report scheduler iniciado (día 1 de cada mes, 03:05 hora local)")


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/reports/generate")
async def generate_report_manual(body: ReportRangeRequest | None = None, user=Depends(require_admin)):
    """Genera reporte manual — mes anterior o rango personalizado (from_date/to_date YYYY-MM-DD)."""
    global _report_running
    if _report_running:
        return {"success": False, "message": "Hay un reporte en generación — espera."}

    use_custom = body and body.from_date and body.to_date

    async def _bg():
        global _report_running
        _report_running = True
        try:
            if use_custom:
                period_label, from_iso, to_iso = _custom_range(body.from_date, body.to_date)
                import re, os as _os
                safe = re.sub(r'[^\w]', '_', period_label)
                filename = f"shomer_report_{safe}.pdf"
                out_path = _os.path.join(REPORTS_DIR, filename)
                _os.makedirs(REPORTS_DIR, exist_ok=True)
                data = _collect_data(from_iso, to_iso)
                _generate_pdf(period_label, data, out_path)
                _send_report_telegram(out_path, period_label, data)
                result = {"success": True, "period": period_label, "filename": filename, "trigger": "manual_range"}
            else:
                now = datetime.now(timezone.utc)
                result = await asyncio.to_thread(_run_report_blocking, now, "manual")
            logger.info("Reporte manual: %s", result)
        except Exception as e:
            logger.error("Reporte manual error: %s", e)
        finally:
            _report_running = False

    asyncio.create_task(_bg())
    return {
        "success": True,
        "message": "Reporte en generación — recibirás el PDF por Telegram en unos segundos.",
    }


@router.get("/reports/list")
async def list_reports(user=Depends(require_admin)):
    """Lista los PDFs generados disponibles."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    files = []
    for f in sorted(os.listdir(REPORTS_DIR), reverse=True):
        if f.endswith(".pdf"):
            full = os.path.join(REPORTS_DIR, f)
            files.append({
                "filename": f,
                "size_kb": round(os.path.getsize(full) / 1024, 1),
                "generated_at": datetime.fromtimestamp(
                    os.path.getmtime(full), tz=timezone.utc
                ).isoformat(),
            })
    return {"success": True, "reports": files}


@router.get("/reports/download/{filename}")
async def download_report(filename: str, user=Depends(require_admin)):
    """Descarga un reporte PDF por nombre de archivo."""
    # Sanitizar — solo letras, números, guiones bajos y puntos
    import re
    if not re.match(r'^[\w\-. ]+\.pdf$', filename):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")
    path = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/reports/generate/now")
async def generate_report_now(user=Depends(require_admin)):
    """
    Genera el reporte del mes en curso (útil para pruebas — datos parciales).
    Usa el mes actual en lugar del mes anterior.
    """
    global _report_running
    if _report_running:
        return {"success": False, "message": "Hay un reporte en generación."}

    async def _bg():
        global _report_running
        _report_running = True
        try:
            now = datetime.now(timezone.utc)
            # Usar mes actual, no el anterior
            from calendar import monthrange
            year, month = now.year, now.month
            last_day = monthrange(year, month)[1]
            label = f"{_month_name(month)} {year} (parcial)"
            from_iso = f"{year:04d}-{month:02d}-01T00:00:00"
            to_iso   = now.isoformat()

            data = _collect_data(from_iso, to_iso)
            os.makedirs(REPORTS_DIR, exist_ok=True)
            filename = f"shomer_report_{year}_{month:02d}_test.pdf"
            out_path = os.path.join(REPORTS_DIR, filename)
            _generate_pdf(label, data, out_path)
            _send_report_telegram(out_path, label, data)
            logger.info("Reporte de prueba generado: %s", out_path)
        except Exception as e:
            logger.error("report/now error: %s", e)
        finally:
            _report_running = False

    asyncio.create_task(_bg())
    return {
        "success": True,
        "message": "Reporte del mes actual (datos parciales) en generación — llega por Telegram.",
    }


# ──────────────────────────────────────────────
# Descarga directa por rango de fechas
# ──────────────────────────────────────────────

@router.get("/reports/export")
async def export_report_range(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date:   str = Query(..., description="YYYY-MM-DD"),
    user = Depends(require_admin),
):
    """Genera y descarga PDF sincrónicamente para el período indicado."""
    import re, tempfile

    period_label, from_iso, to_iso = _custom_range(from_date, to_date)

    def _build():
        data = _collect_data(from_iso, to_iso)
        safe = re.sub(r"[^\w\-]", "_", period_label)
        filename = f"shomer_reporte_{safe}.pdf"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        _generate_pdf(period_label, data, tmp_path)
        return tmp_path, filename

    tmp_path, filename = await asyncio.to_thread(_build)

    def _stream():
        try:
            with open(tmp_path, "rb") as fh:
                while chunk := fh.read(8192):
                    yield chunk
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    return StreamingResponse(
        _stream(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ──────────────────────────────────────────────
# Reporte de solo Auditoría de Red (Riesgos de Red)
# ──────────────────────────────────────────────

def _generate_audit_pdf(period_label: str, data: dict, out_path: str) -> str:
    """PDF liviano: solo hallazgos de red y bloques Hunter del período."""
    from fpdf import FPDF, XPos, YPos

    class PDF(FPDF):
        def header(self):
            self.set_fill_color(15, 23, 42)
            self.rect(0, 0, 210, 20, "F")
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 13)
            self.set_xy(10, 5)
            site = _safe(data.get("site_name", "Shomer Sentinel"))
            self.cell(0, 10, _safe(f"{site} -- Riesgos de Red {period_label}"))

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5, _safe(f"Pagina {self.page_no()} -- Shomer Sentinel -- Generado {datetime.now().strftime('%Y-%m-%d %H:%M')}"))

    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_text_color(0, 0, 0)

    def section(title, color=(13, 110, 110)):
        pdf.ln(3)
        pdf.set_fill_color(*color)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, _safe(f"  {title}"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    net_findings = data.get("net_findings", [])
    if not net_findings:
        section("AUDITORIA DE RED -- Sin hallazgos para el periodo")
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_xy(15, pdf.get_y() + 5)
        pdf.cell(0, 8, "No se encontraron hallazgos de seguridad en el período seleccionado.")
    else:
        section("AUDITORIA DE RED -- Resumen", color=(20, 83, 45))
        sev_counts: dict = {}
        for f in net_findings:
            sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(15)
        pdf.cell(0, 6, f"Total: {len(net_findings)} hallazgos", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for sev, label in [("critico","Críticos"), ("alto","Altos"), ("medio","Medios"), ("bajo","Bajos"), ("info","Info")]:
            cnt = sev_counts.get(sev, 0)
            if cnt > 0:
                clr = {"critico":(220,38,38),"alto":(234,88,12),"medio":(161,120,24),"bajo":(37,99,235),"info":(100,100,100)}[sev]
                pdf.set_x(20)
                pdf.set_text_color(*clr)
                pdf.cell(0, 5, f"{label}: {cnt}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

        section("HALLAZGOS DETALLADOS", color=(20, 83, 45))
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(30, 42, 58)
        pdf.set_text_color(255, 255, 255)
        col_w = [28, 22, 18, 20, 102]
        headers = ["IP", "Puerto", "Severidad", "Estado", "Hallazgo / Cómo resolverlo"]
        for i, h in enumerate(headers):
            ln = (i == len(headers) - 1)
            pdf.cell(col_w[i], 5, h, border=1, fill=True, new_x=XPos.LMARGIN if ln else XPos.RIGHT, new_y=YPos.NEXT if ln else YPos.TOP)

        SEV_COLORS = {"critico":(220,38,38),"alto":(234,88,12),"medio":(161,120,24),"bajo":(37,99,235),"info":(100,100,100)}
        for f in net_findings:
            clr = SEV_COLORS.get(f["severity"], (100,100,100))
            port_str = f'{f["port"]}/{f["protocol"] or "tcp"}' if f["port"] else "--"
            title = _safe((f["title"] or "")[:40])
            rec   = _safe((f["recommendation"] or "—")[:80])
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(6, 182, 212)
            pdf.cell(col_w[0], 5, _safe(f["ip"]), border=1)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(col_w[1], 5, port_str, border=1)
            pdf.set_text_color(*clr)
            pdf.cell(col_w[2], 5, (f["severity"] or "").upper(), border=1)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(col_w[3], 5, _safe(f["finding_status"] or "—"), border=1)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(col_w[4], 5, f"{title}  |  {rec}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.output(out_path)
    return out_path


@router.get("/reports/network-audit")
async def export_network_audit_report(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date:   str = Query(..., description="YYYY-MM-DD"),
    user = Depends(require_admin),
):
    """Genera y descarga PDF con solo hallazgos de Auditoría de Red del período."""
    import re, tempfile

    period_label, from_iso, to_iso = _custom_range(from_date, to_date)

    def _build():
        data = _collect_data(from_iso, to_iso)
        data["site_name"] = get_config("base.site_name") or get_config("base.hostname") or "Shomer Sentinel"
        safe = re.sub(r"[^\w\-]", "_", period_label)
        filename = f"shomer_auditoria_{safe}.pdf"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        _generate_audit_pdf(period_label, data, tmp_path)
        return tmp_path, filename

    tmp_path, filename = await asyncio.to_thread(_build)

    def _stream():
        try:
            with open(tmp_path, "rb") as fh:
                while chunk := fh.read(8192):
                    yield chunk
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    return StreamingResponse(
        _stream(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
