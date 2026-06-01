import sqlite3
import os
from contextlib import contextmanager
from typing import Generator

# Partición p10 (Datos Persistentes) - única fuente de verdad para rutas de BD.
# Red de seguridad: symlinks en /opt/network_monitor/*.db -> /storage/db/*.db
STORAGE_DB = "/storage/db"
DB_PATH = os.path.join(STORAGE_DB, "network_monitor.db")
# Entregables Tracker / informes (Restic Protector respalda el mismo árbol)
PATH_REPORTS = (os.environ.get("SHOMER_PATH_REPORTS") or "/storage/reports").rstrip("/") or "/storage/reports"
INVENTORY_DB_PATH = os.path.join(STORAGE_DB, "inventory.db")
# Config nodos (override con SHOMER_NODOS_GL)
NODOS_GL_PATH = os.environ.get("SHOMER_NODOS_GL", "/opt/network_monitor/config/nodos_gl.json")
# API interna Tools (Tracker/Protector) — mismo host, otro proceso
TOOLS_INTERNAL_BASE = os.environ.get("SHOMER_TOOLS_URL", "http://127.0.0.1:8001").rstrip("/")
# OEM / campo: nombre de NIC de gestión y de mirror (evita hardcode en código; ej. export SHOMER_MANAGEMENT_INTERFACE=enp2s0)
SHOMER_MANAGEMENT_INTERFACE = (os.environ.get("SHOMER_MANAGEMENT_INTERFACE") or "").strip() or None
SHOMER_MIRROR_INTERFACE = (os.environ.get("SHOMER_MIRROR_INTERFACE") or "").strip() or None
REMEDIES_JSON_PATH = os.path.join(STORAGE_DB, "remedies.json")
OUI_PATH = os.path.join(STORAGE_DB, "oui.txt")
CONNECT_TIMEOUT = 30


def _ensure_db_dir() -> None:
    """Asegura que el directorio en la partición de datos exista."""
    os.makedirs(STORAGE_DB, exist_ok=True)


def connect(timeout: float = CONNECT_TIMEOUT, row_factory=None, check_same_thread: bool = True) -> sqlite3.Connection:
    """Abre una conexión a network_monitor.db en /storage con modo WAL."""
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH, timeout=timeout, check_same_thread=check_same_thread)
    conn.execute("PRAGMA journal_mode=WAL;")
    if row_factory is not None:
        conn.row_factory = row_factory
    else:
        conn.row_factory = sqlite3.Row
    return conn


def connect_inventory(timeout: float = CONNECT_TIMEOUT, check_same_thread: bool = False) -> sqlite3.Connection:
    """Abre una conexión a inventory.db en /storage (Rastreador/escaneos). Modo WAL."""
    _ensure_db_dir()
    conn = sqlite3.connect(INVENTORY_DB_PATH, timeout=timeout, check_same_thread=check_same_thread)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection_inventory(timeout: float = CONNECT_TIMEOUT) -> Generator[sqlite3.Connection, None, None]:
    """Context manager para operaciones seguras en inventory.db. Modo WAL; cierre garantizado para evitar locks."""
    conn = connect_inventory(timeout=timeout, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_connection(timeout: float = CONNECT_TIMEOUT) -> Generator[sqlite3.Connection, None, None]:
    """Context manager para operaciones seguras en network_monitor.db."""
    conn = connect(timeout=timeout)
    try:
        yield conn
    finally:
        conn.close()
