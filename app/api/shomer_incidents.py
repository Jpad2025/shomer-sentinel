"""
R2 — Tabla de incidentes de seguridad.
Auto-creado por Hunter al bloquear. Ack/cierre manual. MTTA/MTTR.
Módulo independiente: Hunter llama create_incident() con 2 líneas.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["incidents"])

SEVERITY_LABEL = {1: "CRÍTICO", 2: "ALTO", 3: "MEDIO", 4: "BAJO", 5: "INFO"}
STATUS_OPEN = "open"
STATUS_ACK = "acknowledged"
STATUS_CLOSED = "closed"


# ──────────────────────────────────────────────
# DB init
# ──────────────────────────────────────────────

_table_ready = False


def _init_table():
    # Guard de una sola vez evita CREATE TABLE repetido en el hilo único de Guardian por request.
    global _table_ready
    if _table_ready:
        return
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                alert_signature TEXT,
                severity INTEGER DEFAULT 3,
                blocked_by TEXT DEFAULT 'auto',
                firewall_blocked INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                opened_at TEXT NOT NULL,
                ack_at TEXT,
                ack_by TEXT,
                closed_at TEXT,
                closed_by TEXT,
                notes TEXT DEFAULT ''
            );
        """)
        conn.commit()
    _table_ready = True


# ──────────────────────────────────────────────
# Public API — llamado desde casador_blocking.py
# ──────────────────────────────────────────────

def close_incidents_on_unblock(
    ip: str,
    closed_by: str,
    *,
    incident_id: Optional[int] = None,
    notes: str = "",
) -> int:
    """Cierra incidente(s) al desbloquear una IP. Retorna cantidad cerrada."""
    _init_table()
    now = datetime.now(timezone.utc).isoformat()
    note = (notes or "IP desbloqueada — falso positivo").strip()
    closed = 0
    try:
        with get_db() as conn:
            if incident_id is not None:
                row = conn.execute(
                    "SELECT status FROM incidents WHERE id = ? AND ip = ?",
                    (incident_id, ip),
                ).fetchone()
                if row and row["status"] != STATUS_CLOSED:
                    conn.execute(
                        """UPDATE incidents SET status=?, closed_at=?, closed_by=?,
                           ack_at=COALESCE(ack_at, ?), ack_by=COALESCE(ack_by, ?),
                           notes=CASE WHEN notes='' THEN ? ELSE notes||' | '||? END
                           WHERE id=?""",
                        (
                            STATUS_CLOSED,
                            now,
                            closed_by,
                            now,
                            closed_by,
                            note,
                            note,
                            incident_id,
                        ),
                    )
                    closed = 1
            else:
                cur = conn.execute(
                    """UPDATE incidents SET status=?, closed_at=?, closed_by=?,
                       ack_at=COALESCE(ack_at, ?), ack_by=COALESCE(ack_by, ?),
                       notes=CASE WHEN notes='' THEN ? ELSE notes||' | '||? END
                       WHERE ip=? AND status IN (?, ?)""",
                    (
                        STATUS_CLOSED,
                        now,
                        closed_by,
                        now,
                        closed_by,
                        note,
                        note,
                        ip,
                        STATUS_OPEN,
                        STATUS_ACK,
                    ),
                )
                closed = cur.rowcount
            conn.commit()
    except Exception as e:
        logger.error("close_incidents_on_unblock error (ip=%s): %s", ip, e)
    return closed


def create_incident(
    ip: str,
    alert_signature: str,
    severity: int,
    blocked_by: str,
    firewall_blocked: bool,
) -> int:
    """Crea un incidente al bloquear una IP. Retorna el ID."""
    _init_table()
    try:
        with get_db() as conn:
            cur = conn.execute(
                """INSERT INTO incidents
                   (ip, alert_signature, severity, blocked_by, firewall_blocked, status, opened_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ip,
                    alert_signature or "",
                    severity,
                    blocked_by,
                    1 if firewall_blocked else 0,
                    STATUS_OPEN,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("create_incident error: %s", e)
        return -1


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────

class AckBody(BaseModel):
    notes: Optional[str] = ""


class CloseBody(BaseModel):
    notes: Optional[str] = ""


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _mtta_str(opened_at: str, ack_at: Optional[str]) -> Optional[str]:
    if not ack_at:
        return None
    try:
        o = datetime.fromisoformat(opened_at)
        a = datetime.fromisoformat(ack_at)
        secs = int((a - o).total_seconds())
        return _fmt_secs(secs)
    except Exception:
        return None


def _mttr_str(opened_at: str, closed_at: Optional[str]) -> Optional[str]:
    if not closed_at:
        return None
    try:
        o = datetime.fromisoformat(opened_at)
        c = datetime.fromisoformat(closed_at)
        secs = int((c - o).total_seconds())
        return _fmt_secs(secs)
    except Exception:
        return None


def _fmt_secs(s: int) -> str:
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h {m}m"


def _row_to_dict(r) -> dict:
    d = dict(r)
    d["severity_label"] = SEVERITY_LABEL.get(d.get("severity", 3), "?")
    d["mtta"] = _mtta_str(d["opened_at"], d.get("ack_at"))
    d["mttr"] = _mttr_str(d["opened_at"], d.get("closed_at"))
    return d


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.get("/incidents")
async def list_incidents(
    status: Optional[str] = Query(None, description="open|acknowledged|closed"),
    limit: int = Query(50, le=500),
    user=Depends(get_current_user),
):
    """Lista incidentes, opcionalmente filtrado por estado."""
    _init_table()
    # El frontend manda status=all para "sin filtro" -- sin este guard, "all" se
    # trataba como valor literal (WHERE status='all') y nunca coincidía con ninguna
    # fila real (open/acknowledged/closed), dejando la tabla vacía aunque /stats
    # (sin este filtro) sí contaba bien.
    if status in ("all", ""):
        status = None
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM incidents WHERE status = ? ORDER BY opened_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM incidents ORDER BY opened_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return {"success": True, "incidents": [_row_to_dict(r) for r in rows]}


@router.get("/incidents/stats")
async def incident_stats(user=Depends(get_current_user)):
    """Conteos y métricas MTTA/MTTR globales."""
    _init_table()
    with get_db() as conn:
        totals = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM incidents GROUP BY status"
        ).fetchall()
        # Promedio MTTA (segundos entre opened_at y ack_at)
        mtta = conn.execute(
            """SELECT AVG(
                 (julianday(ack_at) - julianday(opened_at)) * 86400
               ) as avg_sec
               FROM incidents WHERE ack_at IS NOT NULL"""
        ).fetchone()
        # Promedio MTTR (segundos entre opened_at y closed_at)
        mttr = conn.execute(
            """SELECT AVG(
                 (julianday(closed_at) - julianday(opened_at)) * 86400
               ) as avg_sec
               FROM incidents WHERE closed_at IS NOT NULL"""
        ).fetchone()
        # Últimas 24h
        last24 = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE opened_at >= datetime('now','-1 day')"
        ).fetchone()[0]

    counts = {r["status"]: r["cnt"] for r in totals}
    return {
        "success": True,
        "open": counts.get(STATUS_OPEN, 0),
        "acknowledged": counts.get(STATUS_ACK, 0),
        "closed": counts.get(STATUS_CLOSED, 0),
        "last_24h": last24,
        "avg_mtta": _fmt_secs(int(mtta["avg_sec"])) if mtta["avg_sec"] else None,
        "avg_mttr": _fmt_secs(int(mttr["avg_sec"])) if mttr["avg_sec"] else None,
    }


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: int, user=Depends(get_current_user)):
    _init_table()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    return {"success": True, "incident": _row_to_dict(row)}


@router.post("/incidents/{incident_id}/ack")
async def ack_incident(incident_id: int, body: AckBody, user=Depends(get_current_user)):
    """Reconocer (Ack) un incidente abierto."""
    _init_table()
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Incidente no encontrado")
        if row["status"] != STATUS_OPEN:
            raise HTTPException(status_code=409, detail=f"Incidente ya está en estado '{row['status']}'")
        conn.execute(
            "UPDATE incidents SET status=?, ack_at=?, ack_by=?, notes=? WHERE id=?",
            (STATUS_ACK, datetime.now(timezone.utc).isoformat(), user.get("username", "?"), body.notes or "", incident_id),
        )
        conn.commit()
    return {"success": True, "message": f"Incidente {incident_id} reconocido"}


@router.post("/incidents/{incident_id}/close")
async def close_incident(incident_id: int, body: CloseBody, user=Depends(get_current_user)):
    """Cerrar un incidente (open o acknowledged)."""
    _init_table()
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Incidente no encontrado")
        if row["status"] == STATUS_CLOSED:
            raise HTTPException(status_code=409, detail="Incidente ya cerrado")
        conn.execute(
            "UPDATE incidents SET status=?, closed_at=?, closed_by=?, notes=CASE WHEN notes='' THEN ? ELSE notes||' | '||? END WHERE id=?",
            (STATUS_CLOSED, datetime.now(timezone.utc).isoformat(), user.get("username", "?"), body.notes or "", body.notes or "", incident_id),
        )
        conn.commit()
    return {"success": True, "message": f"Incidente {incident_id} cerrado"}


@router.get("/incidents/export/csv")
async def export_incidents_csv(
    status: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    """Descarga CSV de incidentes."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    _init_table()
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM incidents WHERE status = ? ORDER BY opened_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM incidents ORDER BY opened_at DESC"
            ).fetchall()

    output = io.StringIO()
    fields = ["id", "ip", "alert_signature", "severity", "blocked_by",
              "firewall_blocked", "status", "opened_at", "ack_at", "closed_at", "notes"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=incidents.csv"},
    )
