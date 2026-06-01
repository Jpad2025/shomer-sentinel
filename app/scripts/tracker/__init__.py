# SHOMER Tracker Suite: discovery, extractor, persistence.
# Log unificado: /var/log/shomer/tracker.log

from . import discovery
from . import persistence
from . import extractor

__all__ = ["discovery", "persistence", "extractor", "get_logger", "ensure_tracker_log_dir"]

TRACKER_LOG_FILE = "/var/log/shomer/tracker.log"
_logger = None


def ensure_tracker_log_dir() -> None:
    """Asegura que exista el directorio de log. Si no es escribible, no lanza (el logger fallará luego)."""
    import os
    log_dir = os.path.dirname(TRACKER_LOG_FILE)
    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError:
            pass


def get_logger(name: str):
    """Logger que escribe en /var/log/shomer/tracker.log. name ej: tracker.discovery."""
    global _logger
    import logging
    import os
    ensure_tracker_log_dir()
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    try:
        fh = logging.FileHandler(TRACKER_LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s"))
        log.addHandler(fh)
    except OSError:
        pass
    return log
