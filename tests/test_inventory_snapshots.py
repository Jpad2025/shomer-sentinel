"""Tests — inventory_snapshots."""
import sqlite3
import unittest

from app.api.inventory_db_schema import ensure_assets_table
from app.api.inventory_snapshots import (
    close_and_archive_inventory,
    list_snapshot_metadata,
    load_snapshot_assets,
)


class TestSnapshots(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_archive_clears_assets_and_roundtrip(self):
        ensure_assets_table(self.conn)
        self.conn.execute(
            "INSERT INTO assets (mac, ip, hostname) VALUES (?, ?, ?)",
            ("aa:bb:cc:dd:ee:ff", "10.0.0.1", "pc"),
        )
        self.conn.commit()
        out = close_and_archive_inventory(self.conn, "Test Snap", "2026-01-01T00:00:00")
        self.assertEqual(out["asset_count"], 1)
        n = self.conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        self.assertEqual(n, 0)
        meta = list_snapshot_metadata(self.conn)
        self.assertEqual(len(meta), 1)
        sid = meta[0]["id"]
        loaded = load_snapshot_assets(self.conn, sid)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        name, _dt, assets = loaded
        self.assertEqual(name, "Test Snap")
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["mac"], "aa:bb:cc:dd:ee:ff")

    def test_load_missing_returns_none(self):
        ensure_assets_table(self.conn)
        self.assertIsNone(load_snapshot_assets(self.conn, 999))


if __name__ == "__main__":
    unittest.main()
