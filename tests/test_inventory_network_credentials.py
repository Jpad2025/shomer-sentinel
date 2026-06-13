"""Tests — inventory_network_credentials."""
import sqlite3
import unittest

from app.api.inventory_db_schema import ensure_network_credentials
from app.api.inventory_network_credentials import (
    fetch_network_credentials,
    save_network_credentials,
)


class TestNetworkCredentials(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_fetch_none_then_save_then_fetch(self):
        ensure_network_credentials(self.conn)
        self.assertIsNone(fetch_network_credentials(self.conn))
        save_network_credentials(
            self.conn,
            {"user": "u", "password": "p", "domain": "d", "snmp_community": "c"},
        )
        c = fetch_network_credentials(self.conn)
        self.assertIsNotNone(c)
        assert c is not None
        self.assertEqual(c["user"], "u")
        self.assertEqual(c["password"], "p")


if __name__ == "__main__":
    unittest.main()
