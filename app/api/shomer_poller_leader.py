"""Un solo worker uvicorn ejecuta pollers — evita SQLite locked y eventos triplicados."""
from __future__ import annotations

import fcntl
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_LOCK_PATH = os.environ.get("SHOMER_POLLER_LOCK", "/tmp/shomer-poller.lock")
_lock_fd: Optional[int] = None


def try_acquire_poller_leader() -> bool:
    """Intenta lock exclusivo no bloqueante. True = este proceso ejecuta pollers."""
    global _lock_fd
    if _lock_fd is not None:
        return True
    try:
        fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd = fd
        logger.info("Poller líder adquirido (pid=%s, lock=%s)", os.getpid(), _LOCK_PATH)
        return True
    except BlockingIOError:
        logger.info("Worker pid=%s omitido — otro proceso es poller líder", os.getpid())
        return False
    except Exception as e:
        logger.warning("try_acquire_poller_leader: %s — ejecutando pollers en este worker", e)
        return True


def is_poller_leader() -> bool:
    return _lock_fd is not None
