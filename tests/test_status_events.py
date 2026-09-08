"""Tests status_events — oleadas, retención y registro."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.api.shomer_status_events import (
    CAUSE_CATALOG,
    compute_outages,
    format_outage_summary_message,
    get_outage_report_config,
    get_retention_config,
    process_outage_telegram_reports,
    record_status_event,
    run_data_retention_prune,
    _classify_outage,
    _ensure_table,
    _mark_report_sent,
    _outage_qualifies_for_report,
    _parse_ts,
    _report_already_sent,
)


class TestStatusEvents(unittest.TestCase):
    def setUp(self):
        _ensure_table()
        with __import__("app.api.shomer_common", fromlist=["get_db"]).get_db() as conn:
            conn.execute("DELETE FROM status_events WHERE ip LIKE '192.168.0.9%'")
            conn.commit()

    def test_record_skips_same_status(self):
        ip = "192.168.0.91"
        record_status_event(
            source="guardian",
            ip=ip,
            name="Test",
            device_type="ap",
            prev_status="online",
            status="online",
        )
        with __import__("app.api.shomer_common", fromlist=["get_db"]).get_db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM status_events WHERE ip=?", (ip,)).fetchone()[0]
        self.assertEqual(n, 0)

    def test_record_inserts_transition(self):
        record_status_event(
            source="guardian",
            ip="192.168.0.99",
            name="AP Test",
            device_type="access_point",
            prev_status="online",
            status="offline",
            reason="sin respuesta LAN",
            batch_id="g-test",
        )
        with __import__("app.api.shomer_common", fromlist=["get_db"]).get_db() as conn:
            row = conn.execute(
                "SELECT source, status, reason FROM status_events WHERE ip=?",
                ("192.168.0.99",),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["source"], "guardian")
        self.assertEqual(row["status"], "offline")

    def test_compute_outages_empty(self):
        items = compute_outages(hours=1)
        self.assertIsInstance(items, list)

    def test_parse_ts(self):
        dt = _parse_ts("2026-06-12 22:53:51")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_classify_maintenance(self):
        cluster = [{"maintenance": 1, "ip": "10.0.0.1", "device_type": "ap"}]
        cause, label = _classify_outage(["10.0.0.1"], cluster)
        self.assertEqual(cause, "mantenimiento")
        self.assertEqual(label, CAUSE_CATALOG["mantenimiento"])

    def test_classify_mass_wan_down(self):
        cluster = [
            {"ip": f"10.0.0.{i}", "device_type": "access_point", "wan_snapshot": "down"}
            for i in range(12)
        ]
        ips = [e["ip"] for e in cluster]
        cause, _ = _classify_outage(ips, cluster)
        self.assertEqual(cause, "wan_isp")

    def test_retention_config_defaults(self):
        cfg = get_retention_config()
        self.assertGreaterEqual(cfg["status_retention_days"], 7)
        self.assertIn("aggressive_prune_disk_pct", cfg)

    def test_retention_prune_runs(self):
        deleted = run_data_retention_prune(force=True)
        self.assertIsInstance(deleted, dict)

    def test_outage_report_config_defaults(self):
        cfg = get_outage_report_config()
        self.assertIn("outage_report_enabled", cfg)
        self.assertGreaterEqual(cfg["outage_report_min_aps"], 1)

    def test_outage_qualifies_mass_aps(self):
        cfg = get_outage_report_config()
        o = {"probable_cause": "wan_ok_interno", "ap_count": 15, "devices_count": 15}
        self.assertTrue(_outage_qualifies_for_report(o, cfg))

    def test_outage_skips_maintenance(self):
        cfg = get_outage_report_config()
        o = {"probable_cause": "mantenimiento", "ap_count": 20, "devices_count": 20}
        self.assertFalse(_outage_qualifies_for_report(o, cfg))

    def test_summary_message_mentions_individual_alerts(self):
        msg = format_outage_summary_message(
            {
                "started_at_bogota": "2026-06-13 14:41:00",
                "duration_sec": 38,
                "ap_count": 15,
                "devices_count": 15,
                "ended_at_utc": "2026-06-13 14:41:38",
                "probable_cause": "wan_ok_interno",
                "probable_cause_label": CAUSE_CATALOG["wan_ok_interno"],
                "display_cause": "wan_ok_interno",
                "display_cause_label": CAUSE_CATALOG["wan_ok_interno"],
                "wan_down_at_event": False,
                "sample_names": ["AP-Lobby", "AP-Piso2"],
            },
            "Hotel Opera",
        )
        self.assertIn("por AP", msg)
        self.assertIn("resumen adicional", msg)

    @patch("app.api.shomer_guardian_lib.send_telegram_safe")
    def test_process_skips_unrecovered(self, mock_send):
        mock_send.reset_mock()
        with patch("app.api.shomer_status_events.compute_outages") as mock_co:
            mock_co.return_value = [
                {
                    "started_at_utc": "2026-06-13 14:41:00",
                    "ended_at_utc": None,
                    "ap_count": 15,
                    "devices_count": 15,
                    "probable_cause": "wan_ok_interno",
                }
            ]
            with patch("app.api.shomer_status_events.get_outage_report_config") as mock_cfg:
                mock_cfg.return_value = {
                    "outage_report_enabled": True,
                    "outage_report_min_aps": 5,
                    "outage_report_min_devices": 10,
                    "outage_report_repeat_hours": 24,
                    "outage_report_repeat_min": 2,
                    "outage_report_settle_sec": 90,
                }
                with patch("app.api.shomer_status_events.get_redis", return_value=None):
                    sent = process_outage_telegram_reports()
        self.assertEqual(sent, 0)
        mock_send.assert_not_called()

    def test_report_dedup(self):
        _mark_report_sent("2026-06-13 14:41:00", "summary")
        self.assertTrue(_report_already_sent("2026-06-13 14:41:00", "summary"))
        self.assertFalse(_report_already_sent("2026-06-13 14:41:00", "repeat"))

    def test_cluster_uses_rolling_gap_not_fixed_start(self):
        """Sesión 82: compute_outages() comparaba cada evento contra el TS del
        primer evento del cluster, no contra el último -- una oleada real con
        pasos de 2s (dentro de CLUSTER_GAP_SEC=3) pero 4s de punta a punta
        quedaba partida en dos incidentes en vez de uno solo."""
        from app.api.shomer_common import get_db

        ips = ["192.168.0.95", "192.168.0.96", "192.168.0.97"]
        base = datetime.now(timezone.utc) - timedelta(minutes=10)
        timestamps = [
            (base + timedelta(seconds=off)).strftime("%Y-%m-%d %H:%M:%S")
            for off in (0, 2, 4)
        ]
        with get_db() as conn:
            conn.execute("DELETE FROM status_events WHERE ip IN (?,?,?)", ips)
            for ip, ts in zip(ips, timestamps):
                conn.execute(
                    "INSERT INTO status_events "
                    "(ts, source, ip, name, device_type, prev_status, status, reason) "
                    "VALUES (?, 'infra', ?, ?, 'switch', 'online', 'offline', 'test')",
                    (ts, ip, ip),
                )
            conn.commit()

        outages = compute_outages(hours=48)
        matching = [o for o in outages if set(ips) & set(o["all_ips"])]
        self.assertEqual(
            len(matching), 1,
            "los 3 eventos (pasos de 2s, 4s de punta a punta) deben quedar en "
            "una sola oleada, no partidos en varias",
        )
        self.assertEqual(set(matching[0]["all_ips"]) & set(ips), set(ips))

        with get_db() as conn:
            conn.execute("DELETE FROM status_events WHERE ip IN (?,?,?)", ips)
            conn.commit()


if __name__ == "__main__":
    unittest.main()
