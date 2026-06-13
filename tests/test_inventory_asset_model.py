"""
Unit tests — app.api.inventory_asset_model (sin FastAPI ni BD).

Ejecutar desde /opt/network_monitor:
  PYTHONPATH=/opt/network_monitor ./venv/bin/python -m unittest tests.test_inventory_asset_model -v
"""
import json
import unittest

from app.api.inventory_asset_model import (
    KEYWORDS_RISK,
    compute_risk_observations,
    normalize_asset_for_frontend,
)


class TestNormalizeAssetForFrontend(unittest.TestCase):
    def test_os_name_maps_to_os_detected(self):
        a = {"mac": "aa:bb", "os_name": "Windows 10"}
        out = normalize_asset_for_frontend(a)
        self.assertEqual(out["os_detected"], "Windows 10")
        self.assertEqual(out["os_name"], "Windows 10")

    def test_os_detected_takes_precedence_over_os_name(self):
        a = {"os_detected": "Ubuntu", "os_name": "Other"}
        out = normalize_asset_for_frontend(a)
        self.assertEqual(out["os_detected"], "Ubuntu")

    def test_status_fields_null_become_empty_string(self):
        a = {"wmi_status": None, "ssh_status": None, "snmp_status": None}
        out = normalize_asset_for_frontend(a)
        self.assertEqual(out["wmi_status"], "")
        self.assertEqual(out["ssh_status"], "")
        self.assertEqual(out["snmp_status"], "")

    def test_drawer_key_missing_added_as_empty(self):
        out = normalize_asset_for_frontend({"mac": "x"})
        self.assertIn("internal_notes", out)
        self.assertEqual(out["internal_notes"], "")

    def test_keywords_risk_non_empty(self):
        self.assertTrue(any(KEYWORDS_RISK))


class TestComputeRiskObservations(unittest.TestCase):
    def test_empty_asset(self):
        self.assertEqual(compute_risk_observations({}), "")

    def test_laptop_note(self):
        s = compute_risk_observations({"asset_type": "laptop"})
        self.assertIn("portátil", s.lower())

    def test_software_json_keyword(self):
        sw = json.dumps([{"DisplayName": "AnyDesk 123"}])
        s = compute_risk_observations({"software_list": sw, "asset_type": "pc"})
        self.assertIn("anydesk", s.lower())

    def test_invalid_software_json_no_crash(self):
        s = compute_risk_observations({"software_list": "not-json{"})
        self.assertIsInstance(s, str)


if __name__ == "__main__":
    unittest.main()
