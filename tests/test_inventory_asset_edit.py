"""Tests — inventory_asset_edit."""
import sqlite3
import unittest

from app.api.inventory_asset_edit import (
    ASSET_EDITABLE_FIELDS,
    sanitize_asset_updates,
    upsert_asset_row,
)
from app.api.inventory_db_schema import ensure_assets_table


class TestSanitize(unittest.TestCase):
    def test_keeps_allowed_trims_strings(self):
        u = sanitize_asset_updates({"ip": " 10.0.0.1 ", "location": " Sala "})
        self.assertEqual(u["ip"], "10.0.0.1")
        self.assertEqual(u["location"], "Sala")

    def test_drops_unknown_keys(self):
        u = sanitize_asset_updates({"ip": "1.1.1.1", "evil": "x"})
        self.assertIn("ip", u)
        self.assertNotIn("evil", u)

    def test_editable_set_covers_core(self):
        self.assertIn("user_assigned", ASSET_EDITABLE_FIELDS)
        self.assertIn("override_pass", ASSET_EDITABLE_FIELDS)


class TestUpsert(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_insert_then_update(self):
        ensure_assets_table(self.conn)
        upsert_asset_row(self.conn, "aa:bb:cc:dd:ee:ff", {"ip": "10.0.0.5", "last_audit": "t1"})
        row = self.conn.execute(
            "SELECT ip, last_audit FROM assets WHERE mac = ?", ("aa:bb:cc:dd:ee:ff",)
        ).fetchone()
        self.assertEqual(row["ip"], "10.0.0.5")
        upsert_asset_row(self.conn, "aa:bb:cc:dd:ee:ff", {"location": "Lab", "last_audit": "t2"})
        row2 = self.conn.execute(
            "SELECT ip, location, last_audit FROM assets WHERE mac = ?", ("aa:bb:cc:dd:ee:ff",)
        ).fetchone()
        self.assertEqual(row2["location"], "Lab")
        self.assertEqual(row2["last_audit"], "t2")


if __name__ == "__main__":
    unittest.main()
