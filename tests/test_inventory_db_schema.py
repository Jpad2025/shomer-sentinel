"""Tests — esquema BD inventario (sqlite memoria)."""
import sqlite3
import unittest

from app.api.inventory_db_schema import (
    ASSETS_NEW_COLUMNS,
    ensure_assets_table,
    ensure_network_credentials,
    ensure_snapshots_table,
    existing_columns,
)


class TestInventorySchema(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_ensure_credentials_creates_table(self):
        ensure_network_credentials(self.conn)
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='network_credentials'"
        )
        self.assertIsNotNone(cur.fetchone())

    def test_ensure_assets_has_core_and_migration_columns(self):
        ensure_assets_table(self.conn)
        cols = existing_columns(self.conn, "assets")
        self.assertIn("mac", cols)
        self.assertIn("wmi_status", cols)
        for c in ASSETS_NEW_COLUMNS:
            self.assertIn(c, cols)

    def test_snapshots_table(self):
        ensure_snapshots_table(self.conn)
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_snapshots'"
        )
        self.assertIsNotNone(cur.fetchone())


if __name__ == "__main__":
    unittest.main()
