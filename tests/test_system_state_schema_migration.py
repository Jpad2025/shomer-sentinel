"""17 sep 2026: system_state se crea con CREATE TABLE IF NOT EXISTS en DOS
lugares distintos con esquemas diferentes -- monitor.py con columna
`updated_at`, shomer_guardian_events.py sin ella. El que corre primero en
un sitio nuevo define el esquema para siempre (SQLite no migra solo).

Caso real: shomer245 y shomer243 (equipos de laboratorio, a punto de
enviarse como hardware nuevo para clientes) quedaron con el esquema viejo.
set_config() fallaba en silencio (excepción atrapada, solo logueada) en
CUALQUIER escritura de configuración -- incluida la protección real de
Hunter contra autobloquear DNS público (INFRA_CRITICA_IPS vía
hunter.auto_block_exceptions): se intentó guardar la excepción y no pasó
nada, sin ningún error visible para quien lo estaba configurando.
"""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.api import shomer_common


class TestAutoreparacionSystemState(unittest.TestCase):
    def setUp(self):
        # Aislar el flag "ya reparado" entre pruebas -- si no, una prueba
        # anterior en el mismo proceso deja el esquema "ok" en falso positivo.
        shomer_common._system_state_schema_ok = False

    def _con_conexion_temporal(self, conn):
        @contextmanager
        def _fake_get_db():
            try:
                yield conn
            finally:
                pass
        return patch.object(shomer_common, "get_db", _fake_get_db)

    def test_repara_tabla_con_esquema_viejo_sin_updated_at(self):
        """El caso real de shomer245/243: la tabla ya existe, pero sin la
        columna updated_at -- set_config debe autorepararla y funcionar."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE system_state (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()

        with self._con_conexion_temporal(conn):
            ok = shomer_common.set_config("hunter.auto_block_exceptions", ["8.8.8.8"])

        self.assertTrue(ok, "set_config debe autorepararse y guardar, no fallar en silencio")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(system_state)").fetchall()]
        self.assertIn("updated_at", cols)

    def test_sitio_completamente_nuevo_sin_tabla_tambien_funciona(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        with self._con_conexion_temporal(conn):
            ok = shomer_common.set_config("clave", "valor")
            valor = shomer_common.get_config("clave")

        self.assertTrue(ok)
        self.assertEqual(valor, "valor")

    def test_tabla_ya_correcta_no_se_toca(self):
        """No debe romper el caso ya sano (Ópera, shomer205)."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE system_state (key TEXT PRIMARY KEY, value TEXT, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()

        with self._con_conexion_temporal(conn):
            ok = shomer_common.set_config("otra_clave", 123)
            valor = shomer_common.get_config("otra_clave")

        self.assertTrue(ok)
        self.assertEqual(valor, 123)


if __name__ == "__main__":
    unittest.main()
