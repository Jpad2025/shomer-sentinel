"""Tests unitarios — detección host_network_blip compartida."""
import unittest

from app.api.shomer_network_blip import (
    compute_blip_skip_ips,
    evaluate_host_network_blip,
    gateway_unhealthy,
    mass_outage_threshold_met,
    metrics_to_status,
)


class TestGatewayUnhealthy(unittest.TestCase):
    def test_offline_is_unhealthy(self):
        self.assertTrue(gateway_unhealthy("offline", 100.0, None))

    def test_degraded_high_loss(self):
        self.assertTrue(gateway_unhealthy("degraded", 55.0, 50.0))

    def test_degraded_high_rtt(self):
        self.assertTrue(gateway_unhealthy("degraded", 10.0, 350.0))

    def test_degraded_mild_ok(self):
        self.assertFalse(gateway_unhealthy("degraded", 30.0, 100.0))

    def test_online_ok(self):
        self.assertFalse(gateway_unhealthy("online", 0.0, 5.0))


class TestMassOutageThreshold(unittest.TestCase):
    def test_eight_devices(self):
        self.assertTrue(mass_outage_threshold_met(8, 52))

    def test_twenty_devices(self):
        self.assertTrue(mass_outage_threshold_met(20, 100))

    def test_half_inventory(self):
        self.assertTrue(mass_outage_threshold_met(26, 52))

    def test_all_offline(self):
        self.assertTrue(mass_outage_threshold_met(10, 10))

    def test_below_threshold(self):
        self.assertFalse(mass_outage_threshold_met(3, 52))


class TestEvaluateBlip(unittest.TestCase):
    def test_blip_when_gateway_bad_and_mass_offline(self):
        cycle = {f"192.168.0.{i}": "offline" for i in range(1, 11)}
        existing = {ip: "online" for ip in cycle}
        is_blip, skip = evaluate_host_network_blip(
            "192.168.0.1", "offline", 100.0, None, cycle, existing, 10,
        )
        self.assertTrue(is_blip)
        self.assertEqual(len(skip), 10)

    def test_no_blip_if_gateway_ok(self):
        cycle = {f"192.168.0.{i}": "offline" for i in range(1, 11)}
        existing = {ip: "online" for ip in cycle}
        is_blip, skip = evaluate_host_network_blip(
            "192.168.0.1", "online", 0.0, 5.0, cycle, existing, 10,
        )
        self.assertFalse(is_blip)
        self.assertEqual(skip, set())

    def test_skip_only_newly_offline(self):
        cycle = {"192.168.0.2": "offline", "192.168.0.3": "offline"}
        existing = {"192.168.0.2": "offline", "192.168.0.3": "online"}
        skip = compute_blip_skip_ips(cycle, existing)
        self.assertEqual(skip, {"192.168.0.3"})


class TestMetricsToStatus(unittest.TestCase):
    def test_offline_on_total_loss(self):
        self.assertEqual(metrics_to_status(False, 100.0, None), "offline")

    def test_degraded_on_partial_loss(self):
        self.assertEqual(metrics_to_status(True, 70.0, 10.0), "degraded")

    def test_online(self):
        self.assertEqual(metrics_to_status(True, 0.0, 5.0), "online")


if __name__ == "__main__":
    unittest.main()
