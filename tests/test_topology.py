"""Tests shomer_topology — correlación multimarca."""
import unittest

from app.api.shomer_topology import NetworkLink, correlate_outage_to_switches, upsert_link, _ensure_tables


class TestTopology(unittest.TestCase):
    def setUp(self):
        _ensure_tables()
        with __import__("app.api.shomer_common", fromlist=["get_db"]).get_db() as conn:
            conn.execute("DELETE FROM network_links WHERE child_ip LIKE '10.99.%'")
            conn.commit()

    def test_correlate_groups_by_parent(self):
        upsert_link(
            NetworkLink(
                child_ip="10.99.0.1",
                parent_ip="10.99.1.1",
                parent_port="Port 12",
                source="manual",
                child_name="AP-A",
                parent_name="SW-Piso3",
            )
        )
        upsert_link(
            NetworkLink(
                child_ip="10.99.0.2",
                parent_ip="10.99.1.1",
                parent_port="Port 13",
                source="manual",
                child_name="AP-B",
                parent_name="SW-Piso3",
            )
        )
        result = correlate_outage_to_switches(["10.99.0.1", "10.99.0.2", "10.99.0.9"])
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["parent_ip"], "10.99.1.1")
        self.assertEqual(result["groups"][0]["count"], 2)
        self.assertIn("10.99.0.9", result["unmapped"])


if __name__ == "__main__":
    unittest.main()
