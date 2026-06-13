"""
Humo API sin red externa: import de apps, rutas críticas, submódulos refactor.

Ejecutar desde /opt/network_monitor:
  PYTHONPATH=/opt/network_monitor ./venv/bin/python -m unittest tests.test_smoke_api -v
"""
import unittest

from fastapi.testclient import TestClient


def _paths(app) -> set:
    return {getattr(route, "path", "") for route in app.routes}


class TestCoreSmoke(unittest.TestCase):
    """Puerto 8000 — main:app."""

    @classmethod
    def setUpClass(cls):
        from app.api.main import app

        cls.app = app
        cls.client = TestClient(app)
        cls.paths = _paths(app)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_security_headers_present_on_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertIn("x-frame-options", {k.lower() for k in r.headers.keys()})

    def test_login_ok(self):
        r = self.client.get("/login/ok")
        self.assertEqual(r.status_code, 200)

    def test_api_info_core(self):
        r = self.client.get("/api/info")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("api", data)
        self.assertIn("endpoints", data)

    def test_docs_tecnico_route_exists(self):
        self.assertIn("/docs/tecnico", self.paths)

    def test_manual_markdown_static_served(self):
        r = self.client.get("/static/docs/Pasos_Instalacion_Shomer_v2422026.md")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Shomer Sentinel", r.content[:500])

    def test_proxy_routes_on_core(self):
        self.assertIn("/tracker/assets", self.paths)
        self.assertIn("/backups/snapshots", self.paths)

    def test_setup_routes_on_core(self):
        self.assertIn("/setup/status", self.paths)
        self.assertIn("/setup/apply", self.paths)

    def test_setup_status_includes_factory_block(self):
        r = self.client.get("/setup/status")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("factory", data)
        self.assertIn("ip", data["factory"])
        self.assertIn("subnet", data["factory"])

    def test_config_routes_on_core(self):
        self.assertIn("/config/system", self.paths)
        self.assertIn("/network_context", self.paths)
        self.assertIn("/config/nodos", self.paths)

    def test_guardian_routes_on_core(self):
        self.assertIn("/nodes", self.paths)
        self.assertIn("/heartbeat", self.paths)
        self.assertIn("/discovered", self.paths)

    def test_casador_routes_on_core(self):
        self.assertIn("/remedies/block", self.paths)
        self.assertIn("/remedies/pipeline/health", self.paths)

    def test_network_status_routes_on_core(self):
        self.assertIn("/api/network/outages", self.paths)
        self.assertIn("/api/network/status-events", self.paths)
        self.assertIn("/api/network/outages/export", self.paths)
        self.assertIn("/api/network/retention", self.paths)

    def test_pipeline_health_returns_json(self):
        r = self.client.get("/remedies/pipeline/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, dict)


class TestToolsSmoke(unittest.TestCase):
    """Puerto 8001 — main_tools:app."""

    @classmethod
    def setUpClass(cls):
        from app.api.main_tools import app

        cls.app = app
        cls.client = TestClient(app)
        cls.paths = _paths(app)

    def test_login_ok_tools(self):
        r = self.client.get("/login/ok")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("service"), "tools")

    def test_api_info_tools(self):
        r = self.client.get("/api/info")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("modules", data)

    def test_tracker_routes_registered(self):
        self.assertIn("/inventory/list", self.paths)
        self.assertIn("/export/global/inventory/excel", self.paths)

    def test_inventory_list_returns_json(self):
        r = self.client.get("/inventory/list")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("assets", data)

    def test_backups_devices_route(self):
        self.assertIn("/backups/devices", self.paths)

    def test_security_headers_tools(self):
        r = self.client.get("/api/info")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")


class TestShomerRefactor(unittest.TestCase):
    """Contratos del split shomer_* / proxies."""

    def test_get_config_reexported(self):
        from app.api import shomer
        from app.api import shomer_common

        self.assertIs(shomer.get_config, shomer_common.get_config)

    def test_proxies_router_included(self):
        from app.api.shomer import router as main_guardian_router

        paths = {getattr(r, "path", "") for r in main_guardian_router.routes}
        self.assertIn("/tracker/assets", paths)
        self.assertIn("/backups/health", paths)
        self.assertIn("/setup/detect_nics", paths)
        self.assertIn("/config/modules", paths)


class TestCasadorRefactor(unittest.TestCase):
    """Submódulos casador_* importables (deuda modular)."""

    def test_support_import(self):
        from app.api import casador_support

        self.assertTrue(hasattr(casador_support, "_collect_pipeline_health"))

    def test_blocking_import(self):
        from app.api import casador_blocking  # noqa: F401

    def test_rules_import(self):
        from app.api import casador_rules  # noqa: F401

    def test_casador_aggregate_prefix(self):
        from app.api.casador import router

        self.assertEqual(getattr(router, "prefix", ""), "/remedies")

    def test_intel_routes_declared(self):
        from app.api.casador_intel import router as intel

        paths = {getattr(r, "path", "") for r in intel.routes}
        self.assertIn("/pipeline/health", paths)
        self.assertIn("/suricata/recent", paths)


class TestLoginHtmlModule(unittest.TestCase):
    """login_html compartido entre Core y Tools."""

    def test_read_login_html_returns_str(self):
        from app.api.login_html import read_login_html, LOGIN_HTML_PATH

        self.assertIn("login", LOGIN_HTML_PATH.lower())
        s = read_login_html()
        self.assertIsInstance(s, str)
        self.assertGreater(len(s), 50)


if __name__ == "__main__":
    unittest.main()
