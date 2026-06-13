"""Tests — inventory_discovery (sin subprocess nmap en CI salvo vacío)."""
import unittest

from app.api.inventory_discovery import (
    enrich_hostname_nmap,
    vendor_from_oui,
)


class TestVendorOui(unittest.TestCase):
    def test_known_gl_inet(self):
        self.assertIn("GL", vendor_from_oui("e4:5f:01:00:00:01"))

    def test_short_mac(self):
        self.assertEqual(vendor_from_oui("aa"), "")


class TestEnrichNmap(unittest.TestCase):
    def test_empty_ips(self):
        self.assertEqual(enrich_hostname_nmap([]), {})


if __name__ == "__main__":
    unittest.main()
