"""Tests — PDF reporte de activo."""
import unittest

from app.api.inventory_asset_report_pdf import build_asset_report_pdf_bytes


class TestAssetReportPdf(unittest.TestCase):
    def test_outputs_pdf_bytes(self):
        b = build_asset_report_pdf_bytes(
            {
                "ip": "192.168.1.1",
                "mac": "AA:BB:CC:DD:EE:FF",
                "hostname": "pc-test",
                "asset_type": "pc",
                "internal_notes": "ok",
            }
        )
        self.assertIsInstance(b, (bytes, bytearray))
        self.assertTrue(b.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
