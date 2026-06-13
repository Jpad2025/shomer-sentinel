"""Tests — inventory_label_pdf (QR payload; PDF opcional si hay deps)."""
import json
import unittest

from app.api.inventory_label_pdf import (
    asset_label_qr_json,
    asset_label_qr_payload,
)


class TestQrPayload(unittest.TestCase):
    def test_version_and_mac(self):
        p = asset_label_qr_payload({"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.0.0.5"})
        self.assertEqual(p["v"], 1)
        self.assertEqual(p["mac"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(p["ip"], "10.0.0.5")

    def test_truncates_long_hostname(self):
        long_h = "x" * 200
        p = asset_label_qr_payload({"hostname": long_h})
        self.assertEqual(len(p["hostname"]), 120)

    def test_qr_json_roundtrip(self):
        asset = {"mac": "11:22:33:44:55:66", "hostname": "pc-1"}
        s = asset_label_qr_json(asset)
        data = json.loads(s)
        self.assertEqual(data["v"], 1)
        self.assertEqual(data["hostname"], "pc-1")


class TestBuildPdfOptional(unittest.TestCase):
    def test_build_pdf_returns_bytes_if_deps(self):
        from app.api.inventory_label_pdf import build_asset_label_pdf

        b = build_asset_label_pdf(
            {
                "mac": "AA:BB:CC:DD:EE:FF",
                "ip": "192.168.1.10",
                "hostname": "test",
                "asset_type": "pc",
            }
        )
        self.assertIsInstance(b, (bytes, bytearray))
        self.assertGreater(len(b), 100)
        self.assertTrue(b.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
