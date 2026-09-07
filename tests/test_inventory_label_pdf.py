"""Tests — inventory_label_pdf (PDF de etiqueta de activo)."""
import unittest


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
