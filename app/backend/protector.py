#!/usr/bin/env python3
"""
Motor del Módulo Protector - Shomer Sentinel.
Realiza backups con restic: base de datos, reportes y configuración de la app.
Incluye pruning para mantener solo los últimos 7 días de backups diarios.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.backend.db import PATH_REPORTS

# --- Configuración (variables de entorno o valores por defecto) ---
def _env(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()


def _resolve_restic_password() -> str:
    """RESTIC_PASSWORD tiene prioridad; si está vacío, lee RESTIC_PASSWORD_FILE (como el CLI de restic)."""
    direct = _env("RESTIC_PASSWORD", "")
    if direct:
        return direct
    path = _env("RESTIC_PASSWORD_FILE", "")
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""
    return ""


RESTIC_REPOSITORY = _env("RESTIC_REPOSITORY", "/srv/shomer_backups/staging")
RESTIC_PASSWORD = _resolve_restic_password()
RESTIC_BINARY = _env("RESTIC_BINARY", "restic")


def get_restic_password() -> str:
    """Contraseña Restic en tiempo de uso (relee env / RESTIC_PASSWORD_FILE)."""
    return _resolve_restic_password()

LOG_FILE = "/var/log/shomer/protector.log"
KEEP_DAILY = 7

# Rutas a respaldar
PATH_DB = "/storage/db"
PATH_APP_CONFIG = "/opt/network_monitor/app"

_LOGDIR_CHECKED = False


def _ensure_log_dir_and_writable() -> None:
    """
    Verifica que /var/log/shomer/ exista y sea escribible.
    Si no es accesible, imprime mensaje claro y termina con código 1.
    Ejecutar al inicio del script (main).
    """
    global _LOGDIR_CHECKED
    if _LOGDIR_CHECKED:
        return
    log_dir = os.path.dirname(LOG_FILE)
    err_msg = (
        "[protector] ERROR: No se puede escribir en %s\n"
        "  Directorio requerido: %s\n"
        "  Cree el directorio y asigne permisos, por ejemplo:\n"
        "    sudo mkdir -p /var/log/shomer && sudo chown $(whoami) /var/log/shomer\n"
        "  O ejecute: /opt/network_monitor/ensure_shomer_log_dir.sh\n"
    ) % (LOG_FILE, log_dir)
    try:
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("")
    except OSError as e:
        sys.stderr.write(err_msg)
        sys.stderr.write("  Excepción: %s\n" % e)
        sys.exit(1)
    _LOGDIR_CHECKED = True


def _ensure_log_dir() -> None:
    """Asegura que exista el directorio de logs (ya verificado al arranque)."""
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)


def _log(message: str, also_stderr: bool = False) -> None:
    """Escribe una línea con timestamp en protector.log y opcionalmente en stderr."""
    _ensure_log_dir()
    line = "%s [protector] %s\n" % (datetime.utcnow().isoformat() + "Z", message)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
    if also_stderr:
        sys.stderr.write(line)


def _run_restic(args: List[str], env_extra: Optional[dict] = None) -> Tuple[int, str, str]:
    """
    Ejecuta restic con los argumentos dados. Devuelve (returncode, stdout, stderr).
    RESTIC_REPOSITORY y RESTIC_PASSWORD se inyectan en el entorno.
    """
    env = os.environ.copy()
    env["RESTIC_REPOSITORY"] = RESTIC_REPOSITORY
    # Relee en cada ejecución para evitar contraseña stale en procesos largos.
    env["RESTIC_PASSWORD"] = get_restic_password() or RESTIC_PASSWORD
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            [RESTIC_BINARY] + args,
            capture_output=True,
            text=True,
            timeout=3600,
            env=env,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        _log("ERROR: restic no encontrado (RESTIC_BINARY=%s)" % RESTIC_BINARY, also_stderr=True)
        return -1, "", "restic not found"
    except subprocess.TimeoutExpired:
        _log("ERROR: restic timeout (3600s)", also_stderr=True)
        return -1, "", "timeout"


def backup_database() -> bool:
    """Respalda el directorio /storage/db/ (base de datos)."""
    if not os.path.isdir(PATH_DB):
        _log("SKIP backup database: %s no existe" % PATH_DB)
        return True
    _log("Iniciando backup de base de datos: %s" % PATH_DB)
    code, out, err = _run_restic(["backup", PATH_DB, "--tag", "db"])
    _log(out)
    if err:
        _log("stderr: %s" % err)
    if code != 0:
        _log("ERROR backup database exit code=%s" % code, also_stderr=True)
        return False
    _log("Backup database OK")
    return True


def backup_reports() -> bool:
    """Respalda el directorio /storage/reports/ (reportes)."""
    if not os.path.isdir(PATH_REPORTS):
        _log("SKIP backup reports: %s no existe" % PATH_REPORTS)
        return True
    _log("Iniciando backup de reportes: %s" % PATH_REPORTS)
    code, out, err = _run_restic(["backup", PATH_REPORTS, "--tag", "reports"])
    _log(out)
    if err:
        _log("stderr: %s" % err)
    if code != 0:
        _log("ERROR backup reports exit code=%s" % code, also_stderr=True)
        return False
    _log("Backup reports OK")
    return True


def backup_app_config() -> bool:
    """Respalda la configuración de la app en /opt/network_monitor/app/."""
    if not os.path.isdir(PATH_APP_CONFIG):
        _log("SKIP backup app config: %s no existe" % PATH_APP_CONFIG)
        return True
    _log("Iniciando backup de app config: %s" % PATH_APP_CONFIG)
    code, out, err = _run_restic(["backup", PATH_APP_CONFIG, "--tag", "app"])
    _log(out)
    if err:
        _log("stderr: %s" % err)
    if code != 0:
        _log("ERROR backup app config exit code=%s" % code, also_stderr=True)
        return False
    _log("Backup app config OK")
    return True


def backup_all() -> bool:
    """
    Respalda base de datos, reportes y configuración de la app.
    Devuelve True si todos los backups fueron exitosos.
    """
    _log("=== Inicio backup_all ===")
    ok = backup_database() and backup_reports() and backup_app_config()
    _log("=== Fin backup_all (ok=%s) ===" % ok)
    return ok


def prune(keep_daily: int = KEEP_DAILY) -> bool:
    """
    Limpieza (pruning): mantiene solo los últimos keep_daily días de backups diarios.
    Ejecuta restic forget --keep-daily N y luego restic prune.
    """
    _log("Iniciando pruning (keep-daily=%s)" % keep_daily)
    code, out, err = _run_restic(["forget", "--keep-daily", str(keep_daily), "--prune"])
    _log(out)
    if err:
        _log("stderr: %s" % err)
    if code != 0:
        _log("ERROR prune exit code=%s" % code, also_stderr=True)
        return False
    _log("Pruning OK")
    return True


def run_backup_and_prune(keep_daily: int = KEEP_DAILY) -> bool:
    """Ejecuta backup de todos los orígenes y luego pruning. Ideal para cron diario."""
    if not backup_all():
        return False
    return prune(keep_daily=keep_daily)


def list_snapshots(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Lista los últimos snapshots del repositorio. Ejecuta restic snapshots --json,
    parsea la salida y devuelve una lista limpia: short_id, time, paths, hostname.
    Si el repositorio no está inicializado o falla el comando, devuelve lista vacía.
    """
    code, out, err = _run_restic(["snapshots", "--json"])
    if code != 0:
        _log("list_snapshots: repositorio no accesible o no inicializado (code=%s)" % code)
        return []
    try:
        raw = json.loads(out) if (out and out.strip()) else []
        if isinstance(raw, dict):
            data = raw.get("snapshots") if "snapshots" in raw else []
        elif isinstance(raw, list):
            data = raw
        else:
            data = []
        if not isinstance(data, list):
            return []
        snapshots = []
        for s in (data[-limit:] if len(data) > limit else data):
            paths = s.get("paths") or []
            paths_str = ", ".join(str(p) for p in paths)[:300] if paths else ""
            short_id = s.get("short_id") or (str(s.get("id", ""))[:8] if s.get("id") else "")
            snapshots.append({
                "id": s.get("id") or "",
                "short_id": short_id,
                "time": s.get("time") or "",
                "paths": paths_str,
                "hostname": s.get("hostname") or "",
                "tags": s.get("tags") or [],
            })
        return list(reversed(snapshots))
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        _log("list_snapshots: error al parsear JSON - %s" % e)
        return []


def sync_to_cloud() -> Dict[str, Any]:
    """
    Simula la sincronización a un destino externo (rclone sync / restic copy).
    En producción se reemplazaría por ejecución real de rclone o restic copy.
    Devuelve dict con success y log de resultado.
    """
    import time
    _log("sync_to_cloud: inicio (simulado)")
    time.sleep(1)  # simula trabajo
    log_msg = (
        "Sincronización simulada a destino externo. "
        "Para producción: configurar RCLONE_DEST o restic copy a segundo repositorio."
    )
    _log("sync_to_cloud: %s" % log_msg)
    return {"success": True, "log": log_msg}


def repository_health() -> Dict[str, Any]:
    """
    Comprueba que el repositorio sea accesible (restic snapshots).
    Devuelve { "status": "ok" | "error", "message": str }.
    """
    code, out, err = _run_restic(["snapshots"])
    if code == 0:
        return {"status": "ok", "message": "Repositorio accesible."}
    msg = (err or out or "Error desconocido").strip()[:500]
    return {"status": "error", "message": msg or "No se pudo acceder al repositorio."}


def restore_snapshot(snapshot_id: str, target_path: str = "/") -> Dict[str, Any]:
    """
    Restaura un snapshot Restic al path indicado.
    snapshot_id: short_id o ID completo.
    target_path: destino de la restauración (default: raíz, sobreescribe en sitio).
    Devuelve { success, output, error }.
    """
    if not snapshot_id or not snapshot_id.strip():
        return {"success": False, "error": "snapshot_id requerido"}
    sid = snapshot_id.strip()
    _log("restore_snapshot: id=%s target=%s" % (sid, target_path))
    code, out, err = _run_restic(["restore", sid, "--target", target_path])
    _log("restore_snapshot: code=%s" % code)
    if err:
        _log("restore_snapshot stderr: %s" % err[:500])
    return {
        "success": code == 0,
        "output": (out or "").strip()[:1000],
        "error": (err or "").strip()[:500] if code != 0 else "",
    }


def forget_snapshot(snapshot_id: str) -> Dict[str, Any]:
    """
    Elimina un snapshot del repositorio local (restic forget + prune).
    snapshot_id: short_id o ID completo.
    Devuelve { success, output, error }.
    """
    if not snapshot_id or not snapshot_id.strip():
        return {"success": False, "error": "snapshot_id requerido"}
    sid = snapshot_id.strip()
    _log("forget_snapshot: id=%s" % sid)
    code, out, err = _run_restic(["forget", sid, "--prune"])
    _log("forget_snapshot: code=%s" % code)
    if err:
        _log("forget_snapshot stderr: %s" % err[:500])
    return {
        "success": code == 0,
        "output": (out or "").strip()[:1000],
        "error": (err or "").strip()[:500] if code != 0 else "",
    }


if __name__ == "__main__":
    _ensure_log_dir_and_writable()
    import argparse
    parser = argparse.ArgumentParser(description="Shomer Sentinel - Módulo Protector (restic)")
    parser.add_argument("--db-only", action="store_true", help="Solo respaldar /storage/db/")
    parser.add_argument("--reports-only", action="store_true", help="Solo respaldar /storage/reports/")
    parser.add_argument("--app-only", action="store_true", help="Solo respaldar /opt/network_monitor/app/")
    parser.add_argument("--prune-only", action="store_true", help="Solo ejecutar pruning")
    parser.add_argument("--keep-daily", type=int, default=KEEP_DAILY, help="Días a mantener en pruning (default: %s)" % KEEP_DAILY)
    args = parser.parse_args()

    if args.prune_only:
        ok = prune(keep_daily=args.keep_daily)
    elif args.db_only:
        ok = backup_database()
    elif args.reports_only:
        ok = backup_reports()
    elif args.app_only:
        ok = backup_app_config()
    else:
        ok = run_backup_and_prune(keep_daily=args.keep_daily)

    sys.exit(0 if ok else 1)
