"""16 sep 2026: /remedies/stats no tenía forma de responder "cuántos ataques
ha detenido Shomer en total" -- solo exponía alerts_today (solo de hoy) y
active_blocks (solo lo que sigue bloqueado ahora, excluye lo que se bloqueó
y después se liberó solo, como una regla de ruido ya corregida). Verificado
en Ópera: 156 bloqueos históricos reales contra 118 activos -- un chat que
solo viera active_blocks subestimaría el total real en 38 casos.
"""
import importlib

import pytest


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def hunter(tmp_path, monkeypatch):
    from app.backend import db as db_module
    from app.api import casador_blocking as cb

    db_path = str(tmp_path / "network_monitor_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    importlib.reload(cb)

    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE blocked_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT, blocked_at TEXT, blocked_by TEXT,
            alert_signature TEXT, severity INTEGER, unblocked_at TEXT
        )
        """
    )
    con.commit()
    con.close()
    yield cb


def _insert_block(db_path, ip, blocked_by="auto", unblocked=False):
    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO blocked_ips (ip, blocked_at, blocked_by, unblocked_at) VALUES (?,?,?,?)",
        (ip, "2026-09-01 00:00:00", blocked_by, "2026-09-02 00:00:00" if unblocked else None),
    )
    con.commit()
    con.close()


@pytest.mark.anyio
async def test_total_historico_incluye_los_ya_liberados(hunter, tmp_path):
    db_path = str(tmp_path / "network_monitor_test.db")
    _insert_block(db_path, "1.1.1.1", unblocked=True)   # ya liberado -- solo cuenta en el total
    _insert_block(db_path, "2.2.2.2", unblocked=False)  # sigue activo
    _insert_block(db_path, "3.3.3.3", unblocked=False)  # sigue activo

    r = await hunter.hunter_stats(user={})

    assert r["active_blocks"] == 2
    assert r["total_blocks_historico"] == 3


@pytest.mark.anyio
async def test_sin_ningun_bloqueo_da_cero_no_error(hunter):
    r = await hunter.hunter_stats(user={})
    assert r["active_blocks"] == 0
    assert r["total_blocks_historico"] == 0
