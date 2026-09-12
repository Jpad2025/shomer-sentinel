"""El internet del hotel deja rastro, no solo alertas.

12 sep 2026. El monitor horario avisaba cuando había un problema, pero no
guardaba nada. La única evidencia de que el internet estuvo bien era que NO
llegaron alertas — indistinguible de un monitor atascado, que es justo el fallo
que ya apareció tres veces en este sistema (mecanismos que existían y nunca
corrían, sin error).

Tampoco se veían tendencias: un hotel que va perdiendo huéspedes poco a poco no
dispara ninguna alerta y nadie se enteraría.

La trampa al leer el historial es dar por bueno el silencio: cero lecturas NO
es cero problemas, es que nadie midió.
"""
import sqlite3
import unittest
from unittest.mock import patch

from app.api import shomer_wan_hotel as wh


class _Con:
    """Una conexión sqlite en memoria que sobrevive al `with`."""

    def __init__(self):
        self.con = sqlite3.connect(":memory:")

    def __enter__(self):
        return self.con

    def __exit__(self, *a):
        return False


class _Base(unittest.TestCase):
    def setUp(self):
        self.c = _Con()
        self.p = patch.object(wh, "get_db", return_value=self.c)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def _lectura(self, ok=True, sesiones=1000, hotspot=10, problemas=None, ts=None):
        wh._registrar_lectura({
            "ok": ok, "wan_arriba": True, "wan_ip": "1.2.3.4/29",
            "perdida_max": 0 if ok else 100, "sesiones": sesiones,
            "hotspot": hotspot, "problemas": problemas or [],
        })
        if ts:  # reubicar en el tiempo para simular historia
            self.c.con.execute(
                "UPDATE wan_hotel_lecturas SET ts=? WHERE rowid=(SELECT max(rowid) "
                "FROM wan_hotel_lecturas)", (ts,))
            self.c.con.commit()


class TestSeGuardaLaEvidencia(_Base):
    def test_una_lectura_queda_registrada(self):
        self._lectura()
        r = wh.resumen_historial(24)
        self.assertEqual(r["lecturas"], 1)
        self.assertEqual(r["ok"], 1)
        self.assertEqual(r["con_problemas"], 0)

    def test_guarda_el_uso_para_ver_tendencias(self):
        """Un hotel que pierde huéspedes de a poco no dispara alertas."""
        self._lectura(sesiones=1200, ts="2026-09-10 01:00:00")
        self._lectura(sesiones=400, ts="2026-09-10 02:00:00")
        with patch.object(wh, "INTERVALO_MINIMO_SEG", 0):
            self._lectura(sesiones=800)
        r = wh.resumen_historial(24 * 30)
        self.assertEqual(r["sesiones_min"], 400)
        self.assertEqual(r["sesiones_max"], 1200)

    def test_un_problema_queda_con_su_motivo(self):
        self._lectura(ok=False, problemas=["el router no llega a internet (100% de pérdida)"])
        r = wh.resumen_historial(24)
        self.assertEqual(r["con_problemas"], 1)
        self.assertIn("el router no llega a internet (100% de pérdida)", r["problemas"])

    def test_no_repite_el_mismo_motivo(self):
        self._lectura(ok=False, problemas=["la WAN no tiene dirección asignada"],
                      ts="2026-09-10 01:00:00")
        with patch.object(wh, "INTERVALO_MINIMO_SEG", 0):
            self._lectura(ok=False, problemas=["la WAN no tiene dirección asignada"])
        r = wh.resumen_historial(24 * 30)
        self.assertEqual(len(r["problemas"]), 1, "un motivo repetido no es dos hallazgos")


class TestSinLecturasNoEsTodoBien(_Base):
    def test_historial_vacio_no_cuenta_como_ok(self):
        """El fallo que esto viene a evitar: creerle al silencio."""
        r = wh.resumen_historial(24)
        self.assertEqual(r["lecturas"], 0)
        self.assertEqual(r["ok"], 0, "cero lecturas no puede leerse como cero problemas")

    def test_un_error_de_bd_no_inventa_un_resultado_bueno(self):
        with patch.object(wh, "get_db", side_effect=sqlite3.OperationalError("locked")):
            r = wh.resumen_historial(24)
        self.assertEqual(r["lecturas"], 0)


class TestNoSeInflaElHistorial(_Base):
    def test_dos_lecturas_seguidas_cuentan_como_una(self):
        """El panel abierto recargando no es historia."""
        self._lectura()
        self._lectura()
        self.assertEqual(wh.resumen_historial(24)["lecturas"], 1)

    def test_se_borra_lo_mas_viejo_que_la_retencion(self):
        self._lectura(ts="2026-01-01 00:00:00")
        with patch.object(wh, "INTERVALO_MINIMO_SEG", 0):
            self._lectura()
        n = self.c.con.execute("SELECT count(*) FROM wan_hotel_lecturas").fetchone()[0]
        self.assertEqual(n, 1, "la lectura de enero debe haberse purgado")


class TestLaMedicionRegistra(unittest.TestCase):
    def test_medir_wan_hotel_llama_al_registro(self):
        """Si se desconecta el registro, el historial queda vacío en silencio."""
        import inspect
        fuente = inspect.getsource(wh.medir_wan_hotel)
        self.assertIn("_registrar_lectura(datos)", fuente)


if __name__ == "__main__":
    unittest.main()
