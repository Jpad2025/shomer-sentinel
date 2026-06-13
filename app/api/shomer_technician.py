"""
Gestión de técnicos — métricas de rendimiento para bono.
Lee knowledge.db del agente (mismo filesystem).
Solo accesible para rol admin.
"""
import sqlite3
import datetime
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from app.api.auth_api import require_admin
import io, csv

logger = logging.getLogger(__name__)
router = APIRouter()

KNOWLEDGE_DB = "/storage/shomer-agent/data/knowledge.db"


def _db_rw():
    conn = sqlite3.connect(KNOWLEDGE_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS technician_names (
        telegram_id TEXT PRIMARY KEY,
        nombre      TEXT NOT NULL,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS technician_actions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        device_ip   TEXT DEFAULT '',
        device_name TEXT DEFAULT '',
        created_at  TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS incident_knowledge (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        device_ip   TEXT,
        device_name TEXT,
        problem     TEXT NOT NULL,
        action      TEXT NOT NULL,
        result      TEXT DEFAULT 'resuelto',
        saved_by    TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit()
    return conn


def _get_stats(month: str) -> list:
    try:
        conn = _db_rw()
        techs = conn.execute(
            "SELECT DISTINCT telegram_id FROM technician_actions "
            "WHERE strftime('%Y-%m', created_at) = ?", (month,)
        ).fetchall()
        names_rows = conn.execute("SELECT telegram_id, nombre FROM technician_names").fetchall()
        names = {r["telegram_id"]: r["nombre"] for r in names_rows}

        result = []
        for t in techs:
            tid = t["telegram_id"]
            total = conn.execute(
                "SELECT COUNT(*) FROM technician_actions WHERE telegram_id=? AND strftime('%Y-%m',created_at)=?",
                (tid, month)
            ).fetchone()[0]
            reboots = conn.execute(
                "SELECT COUNT(*) FROM technician_actions WHERE telegram_id=? AND action_type='reboot' AND strftime('%Y-%m',created_at)=?",
                (tid, month)
            ).fetchone()[0]
            blocks = conn.execute(
                "SELECT COUNT(*) FROM technician_actions WHERE telegram_id=? AND action_type='block' AND strftime('%Y-%m',created_at)=?",
                (tid, month)
            ).fetchone()[0]
            docs = conn.execute(
                "SELECT COUNT(*) FROM incident_knowledge WHERE saved_by=? AND strftime('%Y-%m',created_at)=?",
                (tid, month)
            ).fetchone()[0]
            rep_rows = conn.execute(
                """SELECT device_ip, COUNT(*) as cnt
                   FROM technician_actions
                   WHERE telegram_id=? AND action_type='reboot'
                     AND strftime('%Y-%m',created_at)=?
                     AND device_ip != ''
                   GROUP BY device_ip HAVING cnt > 2""",
                (tid, month)
            ).fetchall()
            reboots_repetidos = len(rep_rows)
            rep_detail = [{"ip": r["device_ip"], "veces": r["cnt"]} for r in rep_rows]

            doc_rate = round((docs / reboots * 100) if reboots > 0 else 100)
            penalty  = min(reboots_repetidos * 10, 30)
            score    = max(0, min(100, doc_rate - penalty))

            result.append({
                "telegram_id":       tid,
                "nombre":            names.get(tid, f"Técnico {tid[-4:]}"),
                "mes":               month,
                "acciones_total":    total,
                "reboots":           reboots,
                "blocks":            blocks,
                "soluciones_doc":    docs,
                "reboots_repetidos": reboots_repetidos,
                "rep_detail":        rep_detail,
                "doc_rate_pct":      doc_rate,
                "score":             score,
            })
        conn.close()
        return sorted(result, key=lambda x: x["score"], reverse=True)
    except Exception as e:
        logger.error("technician stats: %s", e)
        return []


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/api/technician/stats")
async def get_stats(month: str = "", user=Depends(require_admin)):
    if not month:
        month = datetime.datetime.now().strftime("%Y-%m")
    return JSONResponse({"ok": True, "month": month, "technicians": _get_stats(month)})


@router.get("/api/technician/names")
async def get_names(user=Depends(require_admin)):
    try:
        conn = _db_rw()
        rows = conn.execute("SELECT * FROM technician_names ORDER BY nombre").fetchall()
        conn.close()
        return JSONResponse({"ok": True, "names": [dict(r) for r in rows]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/api/technician/names")
async def save_name(request: Request, user=Depends(require_admin)):
    body = await request.json()
    tid    = str(body.get("telegram_id", "")).strip()
    nombre = str(body.get("nombre", "")).strip()
    if not tid or not nombre:
        return JSONResponse({"ok": False, "error": "telegram_id y nombre requeridos"}, status_code=400)
    try:
        conn = _db_rw()
        conn.execute(
            "INSERT INTO technician_names (telegram_id, nombre) VALUES (?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET nombre=excluded.nombre",
            (tid, nombre)
        )
        conn.commit()
        conn.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.delete("/api/technician/names/{telegram_id}")
async def delete_name(telegram_id: str, user=Depends(require_admin)):
    try:
        conn = _db_rw()
        conn.execute("DELETE FROM technician_names WHERE telegram_id=?", (telegram_id,))
        conn.commit()
        conn.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.get("/api/technician/export")
async def export_csv(month: str = "", user=Depends(require_admin)):
    if not month:
        month = datetime.datetime.now().strftime("%Y-%m")
    stats = _get_stats(month)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Técnico", "Mes", "Acciones", "Reboots", "Bloqueos",
                "Soluciones doc.", "Reboots repetidos", "Tasa doc. %", "Score"])
    for s in stats:
        w.writerow([s["nombre"], s["mes"], s["acciones_total"], s["reboots"],
                    s["blocks"], s["soluciones_doc"], s["reboots_repetidos"],
                    s["doc_rate_pct"], s["score"]])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="gestion_{month}.csv"'},
    )


@router.get("/gestion")
async def gestion_page(request: Request, user=Depends(require_admin)):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse("gestion.html", {
        "request": request,
        "active_module": "gestion",
    })
