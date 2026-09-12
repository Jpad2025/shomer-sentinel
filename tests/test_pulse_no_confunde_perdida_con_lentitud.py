"""Un equipo que no contesta no es un equipo lento.

12 sep 2026, caso real en Ópera. Cuatro datáfonos e impresoras POS salieron por
Telegram como "⚠️ Pulse — degradando — latencia EWMA 401 ms (normal ~0 ms)"
mientras respondían al ping en 0,3 ms con 0% de pérdida. Medido a mano en ese
mismo momento: 0,221 a 0,578 ms los cuatro.

La causa: cuando el equipo no contestaba, se metía el valor del TIMEOUT en el
promedio de latencia como si fuera una medición. Esos cuatro POS fallan pings a
diario —32 caídas al mes cada uno— así que su promedio quedaba envenenado de
forma permanente y el estado "degradando" no tenía salida: la línea base solo se
recalcula cuando el equipo está estable, y no podía volver a estarlo.

Encima el mensaje decía "normal ~0 ms", que al técnico no le dice nada y lo
manda a buscar un problema de lentitud donde hay uno de respuesta.

La señal NO se pierde: que un equipo deje de contestar lo cuenta el EWMA de
pérdida, y la caída total la avisa el evento de offline aparte.
"""
import unittest

from app.api import shomer_infra_pulse as pulse


CFG = {
    "alpha": 0.3, "timeout_ms": 1000.0, "latency_floor_ms": 80.0,
    "latency_factor": 3.0, "loss_ewma_pct": 20.0, "persist_ticks": 3,
}


class TestNoSeInventaLatencia(unittest.TestCase):
    def test_sin_respuesta_no_hay_medicion_de_latencia(self):
        """El fallo exacto: el timeout entraba al promedio como si fuera latencia."""
        self.assertIsNone(
            pulse._sample_latency(None, 100.0, "offline", 1000.0),
            "un equipo que no contesta no midió 1000 ms de latencia",
        )
        self.assertIsNone(pulse._sample_latency(None, 50.0, "degraded", 1000.0))

    def test_una_medicion_real_si_se_usa(self):
        self.assertEqual(pulse._sample_latency(0.3, 0.0, "online", 1000.0), 0.3)

    def test_un_equipo_rapido_que_falla_pings_no_queda_marcado_como_lento(self):
        """El caso de los 4 POS, reproducido: rápido de verdad, pings perdidos."""
        prev = 0.3
        for _ in range(20):
            # alterna: responde rapidísimo / no contesta
            for lat, loss, estado in ((0.3, 0.0, "online"), (None, 100.0, "offline")):
                s = pulse._sample_latency(lat, loss, estado, CFG["timeout_ms"])
                if s is not None:
                    prev = pulse.ewma(prev, s, CFG["alpha"])
        self.assertLess(prev, 5.0,
                        "el promedio debe seguir reflejando los 0,3 ms reales")

    def test_con_el_promedio_limpio_no_dispara_degradacion(self):
        disparo, _ = pulse._degrade_trigger(0.3, 0.0, 0.3, "online", CFG)
        self.assertFalse(disparo, "0,3 ms contra una base de 0,3 ms no es degradación")


class TestLaSenalDePerdidaSobrevive(unittest.TestCase):
    """Lo que no puede pasar: callar un equipo que de verdad no responde."""

    def test_perdida_alta_sigue_disparando(self):
        disparo, motivo = pulse._degrade_trigger(0.3, 60.0, 0.3, "online", CFG)
        self.assertTrue(disparo)
        self.assertIn("pérdida", motivo)

    def test_sin_latencia_valida_la_perdida_manda(self):
        disparo, motivo = pulse._degrade_trigger(None, 60.0, None, "online", CFG)
        self.assertTrue(disparo, "nunca midió latencia, pero sí que no responde")
        self.assertIn("pérdida", motivo)

    def test_sin_latencia_y_sin_perdida_no_inventa_un_problema(self):
        disparo, _ = pulse._degrade_trigger(None, 0.0, None, "online", CFG)
        self.assertFalse(disparo)

    def test_una_lentitud_real_sigue_detectandose(self):
        """El equipo que sí se puso lento tiene que seguir avisando."""
        disparo, motivo = pulse._degrade_trigger(900.0, 0.0, 200.0, "online", CFG)
        self.assertTrue(disparo)
        self.assertIn("latencia", motivo)

    def test_offline_lo_avisa_el_evento_aparte_no_pulse(self):
        disparo, _ = pulse._degrade_trigger(500.0, 100.0, 0.3, "offline", CFG)
        self.assertFalse(disparo)


class TestLaBaseNoSeCalibraConUnFantasma(unittest.TestCase):
    def test_la_linea_base_solo_usa_mediciones_reales(self):
        """Si la base se calibra con timeouts, el equipo queda atrapado: para
        salir de 'degradando' hace falta estar estable, y con la base
        envenenada nunca vuelve a estarlo."""
        import inspect
        fuente = inspect.getsource(pulse.update_pulse)
        self.assertIn("sample_lat is not None and prev_state in", fuente)


if __name__ == "__main__":
    unittest.main()
