"""
R8 — Auditoría del panel.
Middleware que registra POST/PUT/DELETE con usuario, ruta, body y resultado.
Vista admin para consultar y exportar audit_log.
"""
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.auth_api import get_current_user, require_admin
from app.api.shomer_common import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])

# Rutas que NO se auditan aunque sean POST/PUT/DELETE
_SKIP_PATHS = {
    "/auth/login",
    "/auth/logout",
    "/api/login",
    "/noc/data",          # polling TV, demasiado frecuente
    "/noc/problems/ack",  # ACK desde TV (token NOC)
    "/api/server-metrics",
}

# Rutas cuyo body contiene credenciales — guardar solo campos seguros
_MASK_BODY_PATHS = {
    "/auth/login",
    "/auth/change-password",
    "/setup/site-info",
    "/config/system",
}


# ──────────────────────────────────────────────
# DB init
# ──────────────────────────────────────────────

def _init_table():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                username TEXT,
                role TEXT,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER,
                duration_ms INTEGER,
                body_summary TEXT,
                ip_client TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(username);
        """)
        conn.commit()


def _write_log(entry: dict):
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO audit_log
                   (ts, username, role, method, path, status_code, duration_ms, body_summary, ip_client)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry["ts"],
                    entry.get("username"),
                    entry.get("role"),
                    entry["method"],
                    entry["path"],
                    entry.get("status_code"),
                    entry.get("duration_ms"),
                    entry.get("body_summary"),
                    entry.get("ip_client"),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.error("audit_log write error: %s", e)


def _extract_user(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extrae username y role del JWT sin bloquear ni lanzar."""
    try:
        from app.api.auth_api import _decode_token
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
            payload = _decode_token(token)
            if payload:
                return payload.get("sub"), payload.get("role")
    except Exception:
        pass
    return None, None


async def _safe_body_summary(request: Request, path: str) -> Optional[str]:
    """Lee el body y retorna un resumen seguro (sin credenciales)."""
    try:
        body_bytes = await request.body()
        if not body_bytes:
            return None
        if path in _MASK_BODY_PATHS:
            return "[REDACTED]"
        text = body_bytes.decode("utf-8", errors="replace")
        # Truncar a 300 chars para no inflar la BD
        return text[:300] + ("…" if len(text) > 300 else "")
    except Exception:
        return None


# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        # Solo auditar escrituras, no GETs ni rutas excluidas
        if method not in ("POST", "PUT", "PATCH", "DELETE") or path in _SKIP_PATHS:
            return await call_next(request)

        t0 = time.monotonic()
        username, role = _extract_user(request)
        body_summary = await _safe_body_summary(request, path)

        response = await call_next(request)

        duration_ms = int((time.monotonic() - t0) * 1000)
        client_ip = request.client.host if request.client else None

        # Solo registrar si el usuario está autenticado o si es ruta sensible
        if username or path.startswith(("/remedies/", "/config/", "/setup/", "/backups/", "/nodes/", "/infra/")):
            from datetime import datetime, timezone
            _write_log({
                "ts": datetime.now(timezone.utc).isoformat(),
                "username": username or "anonymous",
                "role": role,
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "body_summary": body_summary,
                "ip_client": client_ip,
            })

        return response


def install_audit_middleware(app):
    _init_table()
    app.add_middleware(AuditMiddleware)


# ──────────────────────────────────────────────
# Endpoints — solo admin
# ──────────────────────────────────────────────

@router.get("/audit/logs")
async def audit_logs(
    username: Optional[str] = Query(None),
    path: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    user=Depends(require_admin),
):
    """Consulta el log de auditoría (solo admin)."""
    _init_table()
    filters = []
    params = []
    if username:
        filters.append("username = ?")
        params.append(username)
    if path:
        filters.append("path LIKE ?")
        params.append(f"%{path}%")
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY ts DESC LIMIT ?", params
        ).fetchall()
    return {"success": True, "count": len(rows), "logs": [dict(r) for r in rows]}


@router.get("/audit/stats")
async def audit_stats(user=Depends(require_admin)):
    """Resumen de actividad: top usuarios, rutas más usadas, errores recientes."""
    _init_table()
    with get_db() as conn:
        top_users = conn.execute(
            "SELECT username, COUNT(*) as cnt FROM audit_log GROUP BY username ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        top_paths = conn.execute(
            "SELECT path, method, COUNT(*) as cnt FROM audit_log GROUP BY path, method ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        errors = conn.execute(
            "SELECT * FROM audit_log WHERE status_code >= 400 ORDER BY ts DESC LIMIT 20"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        last_24h = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE ts >= datetime('now','-1 day')"
        ).fetchone()[0]
    return {
        "success": True,
        "total": total,
        "last_24h": last_24h,
        "top_users": [dict(r) for r in top_users],
        "top_paths": [dict(r) for r in top_paths],
        "recent_errors": [dict(r) for r in errors],
    }


@router.get("/audit/export/csv")
async def audit_export_csv(
    username: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    user=Depends(require_admin),
):
    """Exporta audit_log como CSV con filtros opcionales."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    _init_table()
    filters = []
    params = []
    if username:
        filters.append("username = ?")
        params.append(username)
    if from_date:
        filters.append("ts >= ?")
        params.append(from_date)
    if to_date:
        filters.append("ts <= ?")
        params.append(to_date)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY ts DESC", params
        ).fetchall()

    output = io.StringIO()
    fields = ["id", "ts", "username", "role", "method", "path", "status_code", "duration_ms", "body_summary", "ip_client"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
