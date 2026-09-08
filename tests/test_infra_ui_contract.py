"""Contrato UI ↔ backend de Inframonitor — auditoría Sesión 82 (capa panel/NOC).

Cubre bugs reales encontrados revisando los botones y el NOC, no solo el poller:
1. El contador "caídas 24h" (panel y NOC) leía infra_status (estado ACTUAL, con
   checked_at reescrito cada 30s) en vez de infra_events (historial). En Ópera
   mostraba 1 cuando en 24h hubo 11 caídas reales sobre 10 equipos.
2. pollStatus() repintaba la columna "Uptime 24h" con campos que /infra/status
   no devuelve -> a los 30s la columna se borraba sola para toda la tabla.
3. Nombre/ubicación se inyectaban sin escapar en la tabla y dentro de onclick.
4. pc_server_ip solo se podía fijar al crear el equipo (botón "Cola" muerto).
"""
import os
import re
import unittest

_TPL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "templates", "inframonitor.html",
)


def _tpl() -> str:
    with open(_TPL, encoding="utf-8") as fh:
        return fh.read()


class TestOutages24hUsesHistory(unittest.TestCase):
    """El contador de 24h debe salir del historial, no del estado actual."""

    def test_panel_counter_reads_infra_events(self):
        import inspect

        from app.api import shomer_inframonitor as mod

        src = inspect.getsource(mod.list_devices)
        self.assertIn("FROM infra_events", src)
        self.assertNotRegex(
            src,
            r"COUNT\(DISTINCT ip\)\s*\"?\s*\n?\s*\"?FROM infra_status",
            "el contador de caídas 24h no puede salir de infra_status (estado actual)",
        )

    def test_noc_counter_reads_infra_events(self):
        import inspect

        from app.api import shomer_noc as noc

        src = inspect.getsource(noc._infra_devices)
        self.assertIn("FROM infra_events", src)
        self.assertNotIn(
            "FROM infra_status\n                   WHERE status='offline'", src,
        )

    def test_counts_differ_on_real_shaped_data(self):
        """Un equipo que se cayó y se recuperó cuenta como caída del día aunque
        ahora esté online -- exactamente lo que la query vieja perdía."""
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE infra_status (ip TEXT PRIMARY KEY, status TEXT, checked_at TEXT);
            CREATE TABLE infra_events (id INTEGER PRIMARY KEY, ip TEXT, event TEXT,
                                       ts TEXT DEFAULT (datetime('now')));
        """)
        # Estado actual: todos online (se recuperaron).
        for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
            conn.execute(
                "INSERT INTO infra_status (ip, status, checked_at) "
                "VALUES (?, 'online', datetime('now'))", (ip,),
            )
            conn.execute(
                "INSERT INTO infra_events (ip, event, ts) "
                "VALUES (?, 'offline', datetime('now','-3 hours'))", (ip,),
            )
        vieja = conn.execute(
            "SELECT COUNT(DISTINCT ip) FROM infra_status "
            "WHERE status='offline' AND checked_at > datetime('now','-24 hours')"
        ).fetchone()[0]
        nueva = conn.execute(
            "SELECT COUNT(DISTINCT ip) FROM infra_events "
            "WHERE event='offline' AND ts > datetime('now','-24 hours')"
        ).fetchone()[0]
        self.assertEqual(vieja, 0, "la query vieja pierde las caídas ya recuperadas")
        self.assertEqual(nueva, 3, "la nueva sí cuenta las 3 caídas de las últimas 24h")


class TestStatusEndpointContract(unittest.TestCase):
    """pollStatus() no puede repintar con campos que /infra/status no manda."""

    def test_uptime_repaint_is_guarded(self):
        html = _tpl()
        m = re.search(r"// Uptime.*?uptimeBadge\(st\.uptime_24h", html, re.S)
        self.assertIsNotNone(m, "no se encontró el repintado de uptime en pollStatus")
        bloque = m.group(0)
        self.assertIn(
            "st.uptime_24h !== undefined", bloque,
            "el repintado debe estar condicionado a que el dato realmente venga",
        )

    def test_full_refresh_scheduled(self):
        html = _tpl()
        self.assertRegex(
            html, r"setInterval\(loadDevices,\s*\d+\)",
            "hace falta un refresco completo periódico o uptime queda congelado",
        )


class TestTemplateEscaping(unittest.TestCase):
    def test_helpers_exist(self):
        html = _tpl()
        self.assertIn("function esc(", html)
        self.assertIn("function escAttr(", html)

    def test_name_and_location_escaped_in_row(self):
        html = _tpl()
        self.assertIn("${esc(dev.name)}", html)
        self.assertIn("esc(dev.location)", html)

    def test_no_raw_name_inside_onclick(self):
        html = _tpl()
        crudos = re.findall(r"onclick=\"[^\"]*\$\{dev\.name\}[^\"]*\"", html)
        self.assertEqual(
            crudos, [],
            f"dev.name sin escapar dentro de onclick rompe el botón: {crudos}",
        )

    def test_dead_ago_helper_removed(self):
        html = _tpl()
        self.assertNotIn("function ago(", html, "ago() no se usaba en ningún lado")


class TestDeviceEditCoversPrinterPc(unittest.TestCase):
    def test_pc_server_ip_is_editable(self):
        from app.api.shomer_inframonitor import DeviceEdit

        self.assertIn("pc_server_ip", DeviceEdit.model_fields)

    def test_profile_recalculated_when_inputs_change(self):
        import inspect

        from app.api import shomer_inframonitor as mod

        src = inspect.getsource(mod.edit_device)
        self.assertIn("monitor_profile = ''", src)

    def test_ui_prompts_for_pc_ip_on_printers(self):
        html = _tpl()
        self.assertIn("PC_IP_TYPES.includes(type)", html)
        self.assertIn("payload.pc_server_ip", html)


class TestStreamUrlIsPerDevice(unittest.TestCase):
    """La ruta RTSP no puede venir hardcodeada (norma B.1)."""

    def test_no_hardcoded_stream_path(self):
        import inspect

        from app.api import shomer_inframonitor as mod

        src = inspect.getsource(mod.device_action)
        self.assertNotIn(
            '554/stream1', src,
            "la ruta RTSP no puede estar fija: depende del fabricante y del canal",
        )
        self.assertIn("rtsp_path", src)

    def test_rtsp_path_editable(self):
        from app.api.shomer_inframonitor import DeviceEdit, DeviceIn

        self.assertIn("rtsp_path", DeviceIn.model_fields)
        self.assertIn("rtsp_path", DeviceEdit.model_fields)

    def test_ui_prompts_for_rtsp_on_cameras(self):
        html = _tpl()
        self.assertIn("payload.rtsp_path", html)
        self.assertIn("Streaming/Channels/101", html)


class TestSnmpRebootRemoved(unittest.TestCase):
    def test_action_gone_from_inframonitor(self):
        import inspect

        from app.api import shomer_inframonitor as mod

        src = inspect.getsource(mod.device_action)
        self.assertNotIn(
            'action == "snmp_reboot"', src,
            "snmp_reboot era inalcanzable y duplicaba la ruta de Guardian",
        )

    def test_guardian_still_owns_snmp_reboot(self):
        from app.api import shomer_guardian_lib

        self.assertTrue(hasattr(shomer_guardian_lib, "_run_snmp_reboot"))


if __name__ == "__main__":
    unittest.main()
