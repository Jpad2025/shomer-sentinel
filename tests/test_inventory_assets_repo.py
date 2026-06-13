"""Tests — inventory_assets_repo."""
import sqlite3
import unittest

from app.api.inventory_assets_repo import (
    delete_asset_by_mac,
    fetch_all_assets_normalized,
    fetch_asset_by_ip_normalized,
    fetch_asset_by_mac_normalized,
)
from app.api.inventory_db_schema import ensure_assets_table


class TestAssetsRepo(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_fetch_by_ip_and_delete(self):
        ensure_assets_table(self.conn)
        self.conn.execute(
            "INSERT INTO assets (mac, ip, hostname) VALUES (?, ?, ?)",
            ("aa:bb:cc:dd:ee:01", "10.1.1.1", "h1"),
        )
        self.conn.commit()
        a = fetch_asset_by_ip_normalized(self.conn, "10.1.1.1")
        self.assertIsNotNone(a)
        assert a is not None
        self.assertEqual(a["hostname"], "h1")
        m = fetch_asset_by_mac_normalized(self.conn, "aa:bb:cc:dd:ee:01")
        self.assertIsNotNone(m)
        all_a = fetch_all_assets_normalized(self.conn)
        self.assertEqual(len(all_a), 1)
        delete_asset_by_mac(self.conn, "aa:bb:cc:dd:ee:01")
        self.assertEqual(fetch_asset_by_ip_normalized(self.conn, "10.1.1.1"), None)


if __name__ == "__main__":
    unittest.main()
