"""Tests unitarios — Pulse EWMA (shomer_infra_pulse), auditoría Inframonitor Sesión 82.

Cubre dos bugs reales encontrados y corregidos:
1. Un equipo "degradando" que cae del todo a offline se etiquetaba como
   "exit_degrading"/"recovered" (reportaba "se recuperó" para una caída real).
2. _persist_poll_results nunca devolvía pulse_events -- _poll_fast_once lo
   referenciaba desde un scope donde no existía (NameError silencioso en cada
   ciclo), dejando infra:poll:context sin escribirse nunca en Redis.
"""
import sqlite3
import unittest

from app.api.shomer_infra_pulse import ensure_pulse_table, pulse_config, update_pulse


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_pulse_table(conn)
    return conn


def _cfg(**overrides):
    cfg = pulse_config()
    cfg["enabled"] = True
    cfg["persist_ticks"] = 3
    cfg.update(overrides)
    return cfg


def _prime_baseline(conn, ip: str, name: str, cfg: dict, latency_ms: float = 5.0, cycles: int = 20):
    """Varios ciclos a latencia normal -- baseline (alpha lenta) converge antes
    de introducir el pico que debe disparar 'degrading'."""
    snap = None
    for _ in range(cycles):
        snap = update_pulse(
            conn, ip=ip, name=name,
            latency_ms=latency_ms, loss_pct=0.0, status="online", cfg=cfg,
        )
    return snap


class TestPulseOfflineDoesNotClaimRecovery(unittest.TestCase):
    def test_degrading_to_offline_is_not_exit_degrading(self):
        conn = _make_conn()
        cfg = _cfg()
        _prime_baseline(conn, "10.0.0.5", "switch-test", cfg)
        # Pico sostenido de latencia -- dispara degrading (transition solo en
        # el ciclo exacto donde cruza el umbral persist_ticks, no en los siguientes).
        snap = None
        transitions = []
        for _ in range(5):
            snap = update_pulse(
                conn, ip="10.0.0.5", name="switch-test",
                latency_ms=500.0, loss_pct=0.0, status="online", cfg=cfg,
            )
            transitions.append(snap["transition"])
        self.assertEqual(snap["pulse_state"], "degrading")
        self.assertIn("enter_degrading", transitions)

        # El equipo se cae del todo -- no es una recuperación.
        snap_offline = update_pulse(
            conn, ip="10.0.0.5", name="switch-test",
            latency_ms=None, loss_pct=100.0, status="offline", cfg=cfg,
        )
        self.assertIsNone(
            snap_offline["transition"],
            "una caída total no debe reportarse como exit_degrading/recovered",
        )
        self.assertEqual(snap_offline["pulse_state"], "stable")

    def test_genuine_recovery_still_reports_exit_degrading(self):
        conn = _make_conn()
        cfg = _cfg()
        _prime_baseline(conn, "10.0.0.6", "switch-test-2", cfg)
        snap = None
        for _ in range(5):
            snap = update_pulse(
                conn, ip="10.0.0.6", name="switch-test-2",
                latency_ms=500.0, loss_pct=0.0, status="online", cfg=cfg,
            )
        self.assertEqual(snap["pulse_state"], "degrading")

        # Vuelve a latencia normal sin caerse -- recuperación real. EWMA con
        # alpha=0.25 decae gradual, no en un solo ciclo -- da margen amplio.
        transitions = []
        for _ in range(100):
            snap_recovered = update_pulse(
                conn, ip="10.0.0.6", name="switch-test-2",
                latency_ms=5.0, loss_pct=0.0, status="online", cfg=cfg,
            )
            transitions.append(snap_recovered["transition"])
            if snap_recovered["transition"] == "exit_degrading":
                break
        self.assertIn("exit_degrading", transitions)


class TestPersistPollResultsReturnsPulseEvents(unittest.TestCase):
    def test_pulse_events_key_present_in_return(self):
        """_poll_fast_once lee persist_result.get('pulse_events') -- si la clave
        no existe, write_poll_context nunca corre (bug real, Redis infra:poll:context
        nunca se escribía). Import perezoso: requiere el paquete app completo."""
        import inspect

        from app.api import shomer_inframonitor as mod

        src = inspect.getsource(mod._persist_poll_results)
        self.assertIn(
            '"pulse_events": pulse_events', src,
            "_persist_poll_results debe devolver pulse_events en su dict de retorno",
        )
        src_fast = inspect.getsource(mod._poll_fast_once)
        self.assertIn(
            'persist_result.get("pulse_events"', src_fast,
            "_poll_fast_once debe leer pulse_events desde persist_result, no una variable suelta",
        )


if __name__ == "__main__":
    unittest.main()
