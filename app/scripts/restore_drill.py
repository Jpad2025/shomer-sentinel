"""
R3 — Restore drill mensual.
Toma un snapshot aleatorio de B2, hace restore temporal, verifica integridad
con 'restic check', limpia el directorio temporal y envía resultado por Telegram.
También accesible via API para drill manual desde el panel.
"""
import asyncio
import json
import logging
import os
import random
import shutil
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DRILL_TARGET_BASE = "/srv/shomer_drill"
DRILL_TIMEOUT_SEC = 3600


# ──────────────────────────────────────────────
# DB (resultados históricos para R1 — PDF mensual)
# ──────────────────────────────────────────────

def _init_table():
    from app.api.shomer_common import get_db
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS drill_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at TEXT NOT NULL,
                snapshot_id TEXT,
                snapshot_short TEXT,
                success INTEGER NOT NULL,
                duration_sec INTEGER,
                files_restored INTEGER,
                error TEXT,
                trigger TEXT DEFAULT 'scheduled'
            );
        """)
        conn.commit()


def _save_result(result: dict):
    from app.api.shomer_common import get_db
    _init_table()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO drill_results
               (ran_at, snapshot_id, snapshot_short, success, duration_sec, files_restored, error, trigger)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                result.get("snapshot_id"),
                (result.get("snapshot_id") or "")[:8],
                1 if result["success"] else 0,
                result.get("duration_sec"),
                result.get("files_restored"),
                result.get("error"),
                result.get("trigger", "scheduled"),
            ),
        )
        conn.commit()


# ──────────────────────────────────────────────
# Core drill — blocking (run in thread)
# ──────────────────────────────────────────────

def _run_drill_blocking(trigger: str = "scheduled") -> dict:
    """
    Flujo completo del drill. Blocking — llamar con asyncio.to_thread().
    1. Lista snapshots B2
    2. Elige uno aleatorio
    3. restic restore → /srv/shomer_drill/<snapshot_short>
    4. restic check del repo local (integridad)
    5. Limpia directorio temporal
    6. Retorna resultado con métricas
    """
    import time
    t0 = time.monotonic()

    # Importamos aquí para evitar circular imports
    from app.api.backups import (
        RESTIC_BIN,
        _b2_env_and_repo,
        _b2_list_snapshots_blocking,
    )

    # 1. Obtener lista de snapshots B2
    snap_result = _b2_list_snapshots_blocking()
    if not snap_result["success"]:
        return {
            "success": False,
            "error": f"No se pudo listar snapshots B2: {snap_result.get('message', '')}",
            "trigger": trigger,
        }

    snapshots = snap_result.get("snapshots", [])
    if not snapshots:
        return {
            "success": False,
            "error": "No hay snapshots en B2 para hacer drill.",
            "trigger": trigger,
        }

    # 2. Elegir snapshot aleatorio
    chosen = random.choice(snapshots)
    snap_id = chosen.get("short_id") or chosen.get("id", "")
    snap_full_id = chosen.get("id", snap_id)
    snap_date = chosen.get("time", "")[:10]
    snap_tags = chosen.get("tags") or []

    target_dir = os.path.join(DRILL_TARGET_BASE, snap_id)
    os.makedirs(target_dir, exist_ok=True)

    try:
        env, b2_repo = _b2_env_and_repo()
    except ValueError as e:
        return {"success": False, "error": str(e), "trigger": trigger}

    # 3. Restore
    try:
        r = subprocess.run(
            [RESTIC_BIN, "-r", b2_repo, "restore", snap_full_id, "--target", target_dir],
            env=env, capture_output=True, text=True, timeout=DRILL_TIMEOUT_SEC,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout)[:400]
            _cleanup(target_dir)
            return {
                "success": False,
                "snapshot_id": snap_full_id,
                "error": f"Restore falló: {err}",
                "trigger": trigger,
                "duration_sec": int(time.monotonic() - t0),
            }
    except subprocess.TimeoutExpired:
        _cleanup(target_dir)
        return {
            "success": False,
            "snapshot_id": snap_full_id,
            "error": "Timeout durante restore (>1h). Snapshot puede ser muy grande.",
            "trigger": trigger,
            "duration_sec": DRILL_TIMEOUT_SEC,
        }

    # 4. Contar archivos restaurados
    files_restored = sum(len(fs) for _, _, fs in os.walk(target_dir))

    # 5. restic check del repo local (opcional — verifica integridad del repo, no del restore)
    check_ok = True
    check_msg = ""
    try:
        from app.backend.protector import RESTIC_REPO, get_restic_password
        local_env = {**os.environ, "RESTIC_PASSWORD": get_restic_password()}
        cr = subprocess.run(
            [RESTIC_BIN, "-r", RESTIC_REPO, "check"],
            env=local_env, capture_output=True, text=True, timeout=300,
        )
        check_ok = cr.returncode == 0
        check_msg = (cr.stdout.strip() or cr.stderr.strip())[:200]
    except Exception as e:
        check_ok = False
        check_msg = str(e)[:200]

    # 6. Limpiar directorio temporal
    _cleanup(target_dir)

    duration = int(time.monotonic() - t0)
    return {
        "success": True,
        "snapshot_id": snap_full_id,
        "snapshot_short": snap_id,
        "snapshot_date": snap_date,
        "snapshot_tags": snap_tags,
        "files_restored": files_restored,
        "duration_sec": duration,
        "repo_check_ok": check_ok,
        "repo_check_msg": check_msg,
        "trigger": trigger,
    }


def _cleanup(path: str):
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
    except Exception as e:
        logger.warning("drill cleanup error %s: %s", path, e)


# ──────────────────────────────────────────────
# Telegram notify
# ──────────────────────────────────────────────

def _notify(result: dict):
    try:
        from app.scripts.alerts import send_telegram_alert
        ok = result["success"]
        icon = "✅" if ok else "🔴"
        snap = result.get("snapshot_short", "?")
        snap_date = result.get("snapshot_date", "?")
        trigger = result.get("trigger", "scheduled")
        duration = result.get("duration_sec", 0)
        files = result.get("files_restored", 0)
        check = result.get("repo_check_ok")

        if ok:
            check_line = "🔍 Repo local: ✅ OK" if check else "🔍 Repo local: ⚠️ advertencias"
            tags_line = ""
            if result.get("snapshot_tags"):
                tags_line = f"\n🏷️ Tags: {', '.join(result['snapshot_tags'][:3])}"
            msg = (
                f"{icon} <b>Protector — Drill de restore {trigger}</b>\n"
                f"📦 Snapshot: <code>{snap}</code> ({snap_date}){tags_line}\n"
                f"📁 Archivos verificados: <b>{files}</b>\n"
                f"⏱️ Duración: {duration}s\n"
                f"{check_line}"
            )
        else:
            err = result.get("error", "Error desconocido")[:200]
            msg = (
                f"{icon} <b>Protector — Drill FALLÓ</b>\n"
                f"Trigger: {trigger}\n"
                f"Error: {err}"
            )
        send_telegram_alert(msg)
    except Exception as e:
        logger.warning("drill telegram error: %s", e)


# ──────────────────────────────────────────────
# Scheduler mensual
# ──────────────────────────────────────────────

_drill_scheduler_running = False


async def _drill_scheduler_loop():
    """Dispara drill el día 1 de cada mes a las 03:00 hora local del sitio."""
    import time as _time_mod
    while True:
        try:
            from app.api.backups import _scheduler_now
            now = _scheduler_now()
            if now.day == 1 and now.hour == 3 and now.minute == 0:
                from app.api.shomer_common import get_config
                last_drill = get_config("protector.drill_last_run") or ""
                today_str = now.strftime("%Y-%m-%d")
                if last_drill != today_str:
                    logger.info("Drill mensual iniciando — %s", today_str)
                    from app.api.shomer_common import set_config
                    set_config("protector.drill_last_run", today_str)
                    result = await asyncio.to_thread(_run_drill_blocking, "scheduled")
                    _save_result(result)
                    _notify(result)
        except Exception as e:
            logger.error("drill scheduler error: %s", e)
        await asyncio.sleep(60)


def start_drill_scheduler():
    global _drill_scheduler_running
    if _drill_scheduler_running:
        return
    _drill_scheduler_running = True
    asyncio.create_task(_drill_scheduler_loop())
    logger.info("Restore drill scheduler iniciado (día 1 de cada mes, 03:00 hora local)")
