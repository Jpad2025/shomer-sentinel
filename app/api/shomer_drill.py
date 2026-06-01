"""
R3 — API endpoints para Restore Drill.
Trigger manual, historial de drills, último resultado.
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.auth_api import require_admin
from app.api.shomer_common import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["drill"])

_drill_running = False


def _fmt_dur(sec: Optional[int]) -> str:
    if sec is None:
        return "—"
    if sec < 60:
        return f"{sec}s"
    return f"{sec // 60}m {sec % 60}s"


@router.post("/drill/run")
async def run_drill_manual(user=Depends(require_admin)):
    """
    Dispara un drill de restore manual de forma asíncrona.
    Retorna inmediatamente con un mensaje — el resultado llega por Telegram.
    """
    global _drill_running
    if _drill_running:
        return {"success": False, "message": "Hay un drill en progreso — espera a que termine."}

    async def _bg():
        global _drill_running
        _drill_running = True
        try:
            from app.scripts.restore_drill import _run_drill_blocking, _save_result, _notify
            result = await asyncio.to_thread(_run_drill_blocking, "manual")
            _save_result(result)
            _notify(result)
        except Exception as e:
            logger.error("drill manual error: %s", e)
        finally:
            _drill_running = False

    asyncio.create_task(_bg())
    return {
        "success": True,
        "message": "Drill iniciado en background — recibirás el resultado por Telegram.",
        "note": "El drill puede tardar varios minutos dependiendo del tamaño del snapshot.",
    }


@router.get("/drill/status")
async def drill_status(user=Depends(require_admin)):
    """Estado actual y último resultado."""
    from app.scripts.restore_drill import _init_table
    _init_table()

    with get_db() as conn:
        last = conn.execute(
            "SELECT * FROM drill_results ORDER BY ran_at DESC LIMIT 1"
        ).fetchone()
        total = conn.execute("SELECT COUNT(*) FROM drill_results").fetchone()[0]
        ok_count = conn.execute("SELECT COUNT(*) FROM drill_results WHERE success=1").fetchone()[0]

    return {
        "success": True,
        "drill_running": _drill_running,
        "total_drills": total,
        "successful": ok_count,
        "failed": total - ok_count,
        "last_drill": dict(last) if last else None,
        "last_duration": _fmt_dur(last["duration_sec"] if last else None),
    }


@router.get("/drill/history")
async def drill_history(
    limit: int = Query(20, le=100),
    user=Depends(require_admin),
):
    """Historial de drills con métricas."""
    from app.scripts.restore_drill import _init_table
    _init_table()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM drill_results ORDER BY ran_at DESC LIMIT ?", (limit,)
        ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["duration_label"] = _fmt_dur(d.get("duration_sec"))
        results.append(d)

    return {"success": True, "history": results}


@router.get("/drill/history/csv")
async def drill_history_csv(user=Depends(require_admin)):
    """Exporta historial de drills como CSV."""
    import csv
    import io

    from app.scripts.restore_drill import _init_table
    _init_table()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM drill_results ORDER BY ran_at DESC"
        ).fetchall()

    output = io.StringIO()
    fields = ["id", "ran_at", "snapshot_id", "snapshot_short", "success",
              "duration_sec", "files_restored", "error", "trigger"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=drill_history.csv"},
    )
