"""Tests — inventory_suricata_eve (archivo temporal)."""
import json
import os
import tempfile
import unittest

from app.api.inventory_suricata_eve import (
    SURICATA_EVE_DEFAULT_PATH,
    enrich_assets_with_suricata_alerts,
    read_suricata_alerts_for_ips,
)


class TestReadSuricataAlerts(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        out = read_suricata_alerts_for_ips(
            {"10.0.0.1"},
            eve_path="/nonexistent/eve-no-file.json",
        )
        self.assertEqual(out, {})

    def test_empty_ip_set_returns_empty(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            out = read_suricata_alerts_for_ips(set(), eve_path=path)
            self.assertEqual(out, {})
        finally:
            os.unlink(path)

    def test_matches_src_and_dest(self):
        line_ok = {
            "timestamp": "2021-01-01T00:00:00",
            "event_type": "alert",
            "src_ip": "192.168.50.10",
            "dest_ip": "1.1.1.1",
            "alert": {"signature": "ET SCAN", "severity": 1},
        }
        noise = {"event_type": "flow", "src_ip": "192.168.50.10"}
        buf = (json.dumps(noise) + "\n" + json.dumps(line_ok) + "\n").encode()

        fd, path = tempfile.mkstemp(suffix=".json")
        os.write(fd, buf)
        os.close(fd)
        try:
            out = read_suricata_alerts_for_ips(
                {"192.168.50.10"},
                eve_path=path,
                max_bytes=4096,
            )
            self.assertIn("192.168.50.10", out)
            self.assertEqual(len(out["192.168.50.10"]), 1)
            self.assertEqual(out["192.168.50.10"][0]["signature"], "ET SCAN")
        finally:
            os.unlink(path)

    def test_default_path_constant(self):
        self.assertIn("suricata", SURICATA_EVE_DEFAULT_PATH.lower())


class TestEnrichAssets(unittest.TestCase):
    def test_empty_ips_no_crash(self):
        assets = [{"mac": "x", "hostname": "a"}]
        enrich_assets_with_suricata_alerts(assets)
        self.assertEqual(assets[0].get("suricata_alert_count", 0), 0)


if __name__ == "__main__":
    unittest.main()
