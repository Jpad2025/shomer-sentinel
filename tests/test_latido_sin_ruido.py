"""El latido deja de ser una radio y el reinicio solo avisa si es un problema.

12 sep 2026, medido sobre 30 días reales en Ópera (1.013 mensajes a Telegram):

- 55 mensajes "✅ SHOMER operativo — todos los sistemas OK", tres veces al día.
  El bloque identificable más grande de todo el tráfico, y no dice nada: el
  resumen diario ya publica CPU, RAM, disco y servicios, con MÁS detalle. Era
  duplicación pura. Un técnico con 2-3 hoteles recibía ~9 de estos al día.
- 32 mensajes "SISTEMA REINICIADO", casi todos despliegues nuestros. Que Shomer
  se reinicie no es un hecho del hotel; lo que el técnico necesita saber es que
  NO está levantando, y eso se ve cuando se reinicia varias veces seguidas.

Lo que NO puede pasar: perder la prueba de vida. Por eso el latido se sigue
registrando y el resumen diario lo publica una vez al día.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from app.api import shomer_guardian_server_health as sh


class _Redis:
    def __init__(self, valores=None):
        self.v = dict(valores or {})
        self.contador = 0

    def get(self, k):
        return self.v.get(k)

    def set(self, k, val, ex=None):
        self.v[k] = val

    def incr(self, k):
        self.contador += 1
        self.v[k] = str(self.contador)
        return self.contador

    def expire(self, k, s):
        pass


def _cfg(**extra):
    base = {"heartbeat_hours": list(range(24)), "heartbeat_telegram": False,
            "reinicios_para_avisar": 3}
    base.update(extra)
    return base


class TestElLatidoNoHabla(unittest.TestCase):
    def _tick(self, cfg, redis=None):
        r = redis or _Redis()
        enviados = []
        with patch.object(sh, "get_redis", return_value=r), \
             patch.object(sh, "send_telegram_safe", side_effect=lambda m: enviados.append(m)), \
             patch.object(sh, "_get_server_metrics", return_value=(5.0, 25.0, 48.0)), \
             patch.object(sh, "_failsafe_state_get", return_value=None), \
             patch.object(sh, "_failsafe_state_set"):
            sh._heartbeat_report_tick_sync(cfg)
        return enviados, r

    def test_con_todo_en_orden_no_manda_nada(self):
        enviados, _ = self._tick(_cfg())
        self.assertEqual(enviados, [], "'todo OK' no es una noticia")

    def test_pero_deja_registrada_la_prueba_de_vida(self):
        """Sin esto el cambio sí perdería información."""
        _, r = self._tick(_cfg())
        guardado = r.get(sh.HEARTBEAT_STATE_KEY)
        self.assertIsNotNone(guardado, "el latido tiene que quedar registrado")
        d = json.loads(guardado)
        self.assertEqual((d["cpu"], d["ram"], d["temp"]), (5.0, 25.0, 48.0))
        self.assertIn("ts", d)

    def test_un_sitio_puede_volver_a_activarlo(self):
        """Norma B.1: la decisión es del sitio, no del código."""
        enviados, _ = self._tick(_cfg(heartbeat_telegram=True))
        self.assertEqual(len(enviados), 1)
        self.assertIn("todos los sistemas OK", enviados[0])

    def test_fuera_de_las_horas_configuradas_no_hace_nada(self):
        enviados, r = self._tick(_cfg(heartbeat_hours=[]))
        self.assertEqual(enviados, [])
        self.assertIsNone(r.get(sh.HEARTBEAT_STATE_KEY))

    def test_no_se_repite_dentro_de_la_misma_hora(self):
        r = _Redis()
        self._tick(_cfg(heartbeat_telegram=True), redis=r)
        enviados, _ = self._tick(_cfg(heartbeat_telegram=True), redis=r)
        self.assertEqual(enviados, [], "ya se registró esta hora")


class TestElReinicioSoloAvisaSiEsUnProblema(unittest.TestCase):
    def _arranque(self, r, umbral=3):
        enviados = []
        with patch.object(sh, "get_redis", return_value=r), \
             patch.object(sh, "_STARTUP_TELEGRAM", True), \
             patch.object(sh, "send_telegram_safe", side_effect=lambda m: enviados.append(m)):
            sh._send_startup_message_once(umbral)
        return enviados

    def test_un_despliegue_normal_no_avisa(self):
        r = _Redis()
        self.assertEqual(self._arranque(r), [], "reiniciar tras un deploy no es noticia")

    def test_varios_reinicios_seguidos_si_avisan_y_dicen_cuantos(self):
        """El dato útil es el número: uno es un deploy, tres es que no levanta."""
        r = _Redis()
        for _ in range(2):
            self._arranque(r)
            r.v.pop(sh.STARTUP_SENT_KEY, None)  # cada arranque limpia su marca al expirar
        enviados = self._arranque(r)
        self.assertEqual(len(enviados), 1)
        self.assertIn("3 veces", enviados[0])
        self.assertIn("no está quedando estable", enviados[0])

    def test_no_repite_en_el_mismo_arranque(self):
        r = _Redis()
        self._arranque(r)
        self.assertEqual(self._arranque(r), [], "misma marca de arranque")

    def test_el_umbral_es_del_sitio(self):
        r = _Redis()
        enviados = self._arranque(r, umbral=1)
        self.assertEqual(len(enviados), 1, "con umbral 1 avisa desde el primero")

    def test_sin_redis_no_revienta(self):
        with patch.object(sh, "get_redis", return_value=None), \
             patch.object(sh, "_STARTUP_TELEGRAM", True):
            sh._send_startup_message_once(3)  # no debe lanzar


class TestNoSePierdeInformacion(unittest.TestCase):
    def test_el_resumen_diario_publica_lo_que_traia_el_latido(self):
        """CPU/RAM/disco/servicios ya estaban; la WAN es lo único que faltaba."""
        from pathlib import Path
        monitor = Path("/storage/shomer-agent/core/monitor.py")
        if not monitor.exists():
            self.skipTest("el agente no está en este equipo")
        t = monitor.read_text()
        i = t.find("def _build_server_line")
        bloque = t[i:i + 2500]
        self.assertIn("get_wan_status", bloque)
        self.assertIn("WAN", bloque)


if __name__ == "__main__":
    unittest.main()
