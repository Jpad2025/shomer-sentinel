"""Un solo worker uvicorn ejecuta pollers/schedulers — evita SQLite locked, eventos
triplicados y backups/drills/reportes duplicados cuando un servicio corre --workers N."""
from __future__ import annotations

import fcntl
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)

_LOCK_PATH = os.environ.get("SHOMER_POLLER_LOCK", "/tmp/shomer-poller.lock")
_lock_fds: Dict[str, int] = {}


def try_acquire_poller_leader(lock_name: str = "default") -> bool:
    """Intenta lock exclusivo no bloqueante. True = este proceso es líder para `lock_name`.

    `lock_name` permite locks independientes para distintos schedulers dentro del mismo
    servicio (ej. Protector backup, restore drill y reportes en shomer-tools --workers 2)
    sin que adquirir uno bloquee a los demás. El valor por defecto ("default") preserva
    el comportamiento original usado por Guardian (un solo lock global de pollers).
    """
    if lock_name in _lock_fds:
        return True
    lock_path = _LOCK_PATH if lock_name == "default" else f"/tmp/shomer-poller-{lock_name}.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fds[lock_name] = fd
        logger.info("Líder adquirido (pid=%s, lock=%s)", os.getpid(), lock_path)
        return True
    except BlockingIOError:
        os.close(fd)
        logger.info("Worker pid=%s omitido — otro proceso es líder de %s", os.getpid(), lock_name)
        return False
    except Exception as e:
        logger.warning("try_acquire_poller_leader(%s): %s — ejecutando en este worker", lock_name, e)
        return True


def is_poller_leader(lock_name: str = "default") -> bool:
    return lock_name in _lock_fds
