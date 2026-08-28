#!/usr/bin/env python3
"""
Backup del sistema: comprime la base de datos y la carpeta backend.
Mantiene solo las últimas 5 copias para no llenar el disco.
"""
import os
import tarfile
import glob
import logging
from datetime import datetime

# Rutas base (independientes del directorio de ejecución)
OPT_NETWORK = "/opt/network_monitor"
DATABASE_DIR = os.path.join(OPT_NETWORK, "database")
BACKEND_DIR = os.path.join(OPT_NETWORK, "app", "backend")
BACKUPS_DIR = os.path.join(OPT_NETWORK, "backups")
MAX_BACKUPS = 5
BACKUP_PREFIX = "backup_"
BACKUP_EXT = ".tar.gz"

# Log
LOG_DIR = "/var/log/shomer"  # Manifiesto p4
LOG_FILE = os.path.join(LOG_DIR, "backup_system.log")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(BACKUPS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("backup_system")


def _tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Excluir __pycache__, .pyc y archivos de backup temporales."""
    if "__pycache__" in tarinfo.name or tarinfo.name.endswith(".pyc"):
        return None
    if tarinfo.name.endswith(".py.bak") or tarinfo.name.endswith(".bak"):
        return None
    return tarinfo


def run_backup() -> tuple[bool, str]:
    """
    Crea un backup comprimido (BD + backend) y rota dejando solo las últimas MAX_BACKUPS.
    Returns:
        (True, path_del_backup) en éxito, (False, mensaje_error) en fallo.
    """
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(BACKUPS_DIR, f"{BACKUP_PREFIX}{stamp}{BACKUP_EXT}")
    try:
        with tarfile.open(out_path, "w:gz") as tar:
            if os.path.isdir(DATABASE_DIR):
                tar.add(DATABASE_DIR, arcname="database", filter=_tar_filter)
            else:
                logger.warning("No existe %s", DATABASE_DIR)
            if os.path.isdir(BACKEND_DIR):
                tar.add(BACKEND_DIR, arcname="backend", filter=_tar_filter)
            else:
                logger.warning("No existe %s", BACKEND_DIR)
        logger.info("Backup creado: %s", out_path)
        _rotate_backups()
        return True, out_path
    except Exception as e:
        logger.exception("Error creando backup: %s", e)
        if os.path.isfile(out_path):
            try:
                os.remove(out_path)
            except OSError:
                pass
        return False, str(e)


def _rotate_backups() -> None:
    """Mantiene solo las últimas MAX_BACKUPS copias; elimina el resto."""
    pattern = os.path.join(BACKUPS_DIR, f"{BACKUP_PREFIX}*{BACKUP_EXT}")
    files = glob.glob(pattern)
    if len(files) <= MAX_BACKUPS:
        return
    # Ordenar por fecha de modificación, más reciente primero
    files.sort(key=os.path.getmtime, reverse=True)
    for path in files[MAX_BACKUPS:]:
        try:
            os.remove(path)
            logger.info("Backup antiguo eliminado: %s", path)
        except OSError as e:
            logger.warning("No se pudo eliminar %s: %s", path, e)


if __name__ == "__main__":
    ok, result = run_backup()
    if ok:
        print(result)
    else:
        print("ERROR:", result, file=__import__("sys").stderr)
    exit(0 if ok else 1)
