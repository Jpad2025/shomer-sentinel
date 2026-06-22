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
    Diseñado para verificar sin descargar el snapshot completo (un solo backup de
    cliente puede pesar varios GB y saturar la red/Shomer solo para "comprobar que
    sirve" — ver discusión 19-20 jun 2026, Hotel Ópera).

    1. Lista snapshots B2
    2. Elige uno aleatorio
    3. Capa 1 — compara el hash del árbol (Merkle tree) contra el snapshot local de
       origen. Costo ~0 (solo JSON de metadatos). Si coincide, los datos son
       bit-por-bit idénticos local↔nube.
    4. Capa 2 — restaura SOLO el archivo más pequeño del snapshot (no todo). Prueba
       que la cadena cifrado→nube→descifrado→archivo funciona de punta a punta con
       costo de red mínimo (KB-MB, no GB).
    5. Capa 3 — restic check del repo local (metadatos/índice, sin --read-data).
    6. Limpia directorio temporal.
    7. Retorna resultado con las 3 verificaciones.
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
    snap_tree = chosen.get("tree", "")
    snap_original = chosen.get("original", "")  # id del snapshot local de origen (si "restic copy" lo registró)

    # 3. Capa 1 -- comparar el hash del árbol (Merkle tree) contra el snapshot local
    # de origen. Costo: dos llamadas "snapshots --json" (KB de JSON, nada de datos).
    # Si los hashes coinciden, es prueba criptográfica de que la copia en B2 es
    # bit-por-bit idéntica al backup local -- sin descargar un solo archivo.
    tree_match = None  # None = no se pudo comparar (snapshot local ya rotado por retención)
    tree_check_msg = "Sin snapshot local de origen para comparar."
    if snap_tree and snap_original:
        try:
            from app.backend.protector import RESTIC_REPOSITORY, get_restic_password
            local_env = {**os.environ, "RESTIC_PASSWORD": get_restic_password()}
            lr = subprocess.run(
                [RESTIC_BIN, "-r", RESTIC_REPOSITORY, "snapshots", "--json"],
                env=local_env, capture_output=True, text=True, timeout=30,
            )
            if lr.returncode == 0:
                local_snaps = json.loads(lr.stdout or "[]")
                local_match = next((s for s in local_snaps if s.get("id") == snap_original), None)
                if local_match:
                    tree_match = local_match.get("tree") == snap_tree
                    tree_check_msg = (
                        "Árbol idéntico local↔nube (verificado por hash)." if tree_match
                        else "¡El árbol de archivos NO coincide entre local y B2! Posible corrupción."
                    )
                else:
                    tree_check_msg = "Snapshot local de origen ya no existe (rotado por retención) -- sin comparación posible."
            else:
                tree_check_msg = f"No se pudo leer el repo local: {(lr.stderr or lr.stdout)[:200]}"
        except Exception as e:
            tree_check_msg = f"Error comparando árbol: {str(e)[:150]}"

    if tree_match is False:
        return {
            "success": False,
            "snapshot_id": snap_full_id,
            "error": tree_check_msg,
            "tree_match": False,
            "trigger": trigger,
            "duration_sec": int(time.monotonic() - t0),
        }

    target_dir = os.path.join(DRILL_TARGET_BASE, snap_id)
    os.makedirs(target_dir, exist_ok=True)

    try:
        env, b2_repo = _b2_env_and_repo()
    except ValueError as e:
        return {"success": False, "error": str(e), "trigger": trigger}

    # 4. Capa 2 -- elegir el archivo MÁS PEQUEÑO del snapshot y restaurar solo ese -- no el
    # snapshot completo. Un PMS/contable puede tener un solo snapshot de varios GB
    # (visto en producción: 1.1 MB a 2.2 GB dentro del mismo backup); descargarlo
    # entero cada vez que se quiere *solo confirmar que es recuperable* satura CPU/
    # disco del Shomer y, peor, el ancho de banda real del cliente (WAN del hotel).
    # Un archivo de muestra restaurado con éxito ya prueba que la cadena
    # cifrado→nube→descifrado→archivo funciona de punta a punta.
    try:
        ls_r = subprocess.run(
            [RESTIC_BIN, "-r", b2_repo, "ls", snap_full_id, "--long", "--json"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        files = []
        for line in (ls_r.stdout or "").splitlines():
            try:
                obj = json.loads(line)
                if obj.get("type") == "file" and obj.get("size") is not None:
                    files.append((obj["size"], obj.get("path", "")))
            except Exception:
                continue
        if ls_r.returncode != 0 or not files:
            _cleanup(target_dir)
            return {
                "success": False,
                "snapshot_id": snap_full_id,
                "error": f"No se pudo listar archivos del snapshot: {(ls_r.stderr or ls_r.stdout)[:300]}",
                "trigger": trigger,
                "duration_sec": int(time.monotonic() - t0),
            }
        total_files_in_snapshot = len(files)
        sample_size, sample_path = min(files, key=lambda f: f[0])
    except subprocess.TimeoutExpired:
        _cleanup(target_dir)
        return {
            "success": False,
            "snapshot_id": snap_full_id,
            "error": "Timeout listando archivos del snapshot.",
            "trigger": trigger,
            "duration_sec": int(time.monotonic() - t0),
        }

    # 4. Restore -- solo el archivo de muestra elegido arriba
    try:
        r = subprocess.run(
            [RESTIC_BIN, "-r", b2_repo, "restore", snap_full_id, "--target", target_dir,
             "--include", sample_path],
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
            "error": "Timeout durante restore del archivo de muestra.",
            "trigger": trigger,
            "duration_sec": DRILL_TIMEOUT_SEC,
        }

    # 5. Verificar que el archivo de muestra quedó en disco con el tamaño esperado
    files_restored = sum(len(fs) for _, _, fs in os.walk(target_dir))
    restored_path = os.path.join(target_dir, sample_path.lstrip("/"))
    sample_ok = os.path.isfile(restored_path) and os.path.getsize(restored_path) == sample_size
    if not sample_ok:
        _cleanup(target_dir)
        return {
            "success": False,
            "snapshot_id": snap_full_id,
            "error": f"Archivo de muestra restaurado no coincide en tamaño/no existe: {sample_path}",
            "trigger": trigger,
            "duration_sec": int(time.monotonic() - t0),
        }

    # 6. Capa 3 -- restic check del repo LOCAL (estructura/índice, sin --read-data --
    # no descarga ni relee los datos, solo verifica consistencia de metadatos).
    # NOTA: el import de RESTIC_REPO (sin "SITORY") nunca existió -- bug latente que
    # crasheaba esta sección con ImportError cada vez que se llegaba hasta aquí.
    check_ok = True
    check_msg = ""
    try:
        from app.backend.protector import RESTIC_REPOSITORY, get_restic_password
        local_env = {**os.environ, "RESTIC_PASSWORD": get_restic_password()}
        cr = subprocess.run(
            [RESTIC_BIN, "-r", RESTIC_REPOSITORY, "check"],
            env=local_env, capture_output=True, text=True, timeout=300,
        )
        # Lock viejo de una operación anterior interrumpida (ej. un kill -9) -- liberar
        # y reintentar una vez antes de reportar falla real.
        if cr.returncode != 0 and "lock" in (cr.stderr or "").lower():
            subprocess.run([RESTIC_BIN, "-r", RESTIC_REPOSITORY, "unlock"],
                            env=local_env, capture_output=True, text=True, timeout=30)
            cr = subprocess.run(
                [RESTIC_BIN, "-r", RESTIC_REPOSITORY, "check"],
                env=local_env, capture_output=True, text=True, timeout=300,
            )
        check_ok = cr.returncode == 0
        check_msg = (cr.stdout.strip() or cr.stderr.strip())[:200]
    except Exception as e:
        check_ok = False
        check_msg = str(e)[:200]

    # 7. Limpiar directorio temporal
    _cleanup(target_dir)

    duration = int(time.monotonic() - t0)
    return {
        "success": True,
        "snapshot_id": snap_full_id,
        "snapshot_short": snap_id,
        "snapshot_date": snap_date,
        "snapshot_tags": snap_tags,
        "files_restored": files_restored,
        "total_files_in_snapshot": total_files_in_snapshot,
        "sample_file": os.path.basename(sample_path),
        "sample_file_size_mb": round(sample_size / 1024 / 1024, 3),
        "tree_match": tree_match,
        "tree_check_msg": tree_check_msg,
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
        check = result.get("repo_check_ok")
        tree_match = result.get("tree_match")
        sample_file = result.get("sample_file")
        sample_mb = result.get("sample_file_size_mb")
        total_files = result.get("total_files_in_snapshot")

        if ok:
            check_line = "🔍 Repo local: ✅ OK" if check else "🔍 Repo local: ⚠️ advertencias"
            if tree_match is True:
                tree_line = "🌳 Hash árbol local↔nube: ✅ idéntico"
            elif tree_match is False:
                tree_line = "🌳 Hash árbol local↔nube: 🔴 NO COINCIDE"
            else:
                tree_line = "🌳 Hash árbol: sin snapshot local para comparar (rotado por retención)"
            sample_line = (
                f"📄 Muestra restaurada: <code>{sample_file}</code> ({sample_mb} MB de {total_files} archivos del snapshot)"
                if sample_file else ""
            )
            tags_line = ""
            if result.get("snapshot_tags"):
                tags_line = f"\n🏷️ Tags: {', '.join(result['snapshot_tags'][:3])}"
            msg = (
                f"{icon} <b>Protector — Drill de restore {trigger}</b>\n"
                f"📦 Snapshot: <code>{snap}</code> ({snap_date}){tags_line}\n"
                f"{tree_line}\n"
                f"{sample_line}\n"
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
    """shomer-tools.service corre --workers 2 -- solo el worker líder (`restore-drill`)
    corre este loop, para no disparar el drill mensual duplicado (ver CLAUDE.md §AZ)."""
    global _drill_scheduler_running
    if _drill_scheduler_running:
        return
    from app.api.shomer_poller_leader import try_acquire_poller_leader
    if not try_acquire_poller_leader("restore-drill"):
        logger.info("Restore drill scheduler: worker pid=%s omitido — otro worker es líder", os.getpid())
        return
    _drill_scheduler_running = True
    asyncio.create_task(_drill_scheduler_loop())
    logger.info("Restore drill scheduler iniciado (día 1 de cada mes, 03:00 hora local)")
