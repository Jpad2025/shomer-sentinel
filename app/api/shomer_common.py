"""
Estado compartido del Guardian: BD system_state, Redis, licencia de módulos, URL interna Tools.
Extraído de shomer.py para acotar el monolito sin cambiar comportamiento.
"""
import logging
import sqlite3
from contextlib import contextmanager
from typing import Optional

from app.backend.db import TOOLS_INTERNAL_BASE, connect

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_DB = 0

_LOG_PRUNE_LAST_RUN: Optional[float] = None
LOG_RETENTION_DAYS = 30
LOG_PRUNE_INTERVAL_SEC = 3600

ALL_MODULES = ["guardian", "hunter", "tracker", "protector", "inframonitor", "noc", "incidents", "audit"]
MODULES_ENABLED_KEY = "modules.enabled"


def _tools_url(path: str) -> str:
    p = path if path.startswith("/") else f"/{path}"
    return f"{TOOLS_INTERNAL_BASE}{p}"


def get_redis():
    if not REDIS_AVAILABLE:
        return None
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        r.ping()
        return r
    except Exception:
        return None


@contextmanager
def get_db():
    conn = connect(timeout=10, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def get_config(key: str, default=None):
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT value FROM system_state WHERE key = ?", (key,)
            ).fetchone()
            if row:
                import json as _json
                try:
                    return _json.loads(row["value"])
                except Exception:
                    return row["value"]
    except Exception as e:
        logger.debug("get_config(%s) error: %s", key, e)
    return default


def set_config(key: str, value) -> bool:
    try:
        import json as _json
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_state (key, value, updated_at) "
                "VALUES (?, ?, datetime('now'))",
                (key, _json.dumps(value) if not isinstance(value, str) else value),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("set_config error: %s", e)
        return False


def get_enabled_modules() -> list:
    val = get_config(MODULES_ENABLED_KEY, None)
    if isinstance(val, list):
        return val
    set_config(MODULES_ENABLED_KEY, ALL_MODULES)
    return ALL_MODULES


def is_module_enabled(name: str) -> bool:
    return name in get_enabled_modules()


def require_module(name: str):
    from fastapi import HTTPException as _HTTPException

    if not is_module_enabled(name):
        raise _HTTPException(
            status_code=403,
            detail=f"Módulo '{name}' no habilitado en esta instalación",
        )


def _prune_old_logs() -> None:
    import time

    global _LOG_PRUNE_LAST_RUN
    now = time.time()
    if _LOG_PRUNE_LAST_RUN is not None and (now - _LOG_PRUNE_LAST_RUN) < LOG_PRUNE_INTERVAL_SEC:
        return
    _LOG_PRUNE_LAST_RUN = now
    days = LOG_RETENTION_DAYS
    try:
        v = get_config("monitor.event_log_retention_days")
        if v is not None:
            days = max(7, min(365, int(v)))
    except Exception:
        pass
    try:
        with get_db() as conn:
            cur = conn.execute(
                "DELETE FROM event_log WHERE created_at < datetime('now', ?)",
                (f"-{days} days",),
            )
            deleted = cur.rowcount
            conn.commit()
            if deleted and deleted > 0:
                print(f"[SHOMER] Prune event_log: eliminados {deleted} registros > {days} días")
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e).lower():
            print(f"[SHOMER] Prune event_log error: {e}")
    except Exception as e:
        print(f"[SHOMER] Prune event_log error: {e}")
