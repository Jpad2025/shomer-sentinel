"""Tests — inventory_excel_export (sin BD)."""
import json
import unittest

from app.api.inventory_excel_export import (
    GLOBAL_INVENTORY_COLUMNS,
    SNAPSHOT_INVENTORY_COLUMNS,
    format_snapshot_software_cell,
    hardware_row_with_observaciones_riesgo,
    parse_software_list_dicts,
    prepare_rows_for_global_client_excel,
    prepare_snapshot_inventory_dataframe,
    render_global_client_excel_bytes,
    render_single_asset_excel_bytes,
    render_snapshot_archive_excel_bytes,
)


class TestPrepareGlobalRows(unittest.TestCase):
    def test_adds_risk_column_and_flattens_software(self):
        assets = [
            normalize_asset(
                {
                    "ip": "10.0.0.1",
                    "software_list": json.dumps(
                        [{"DisplayName": "App A"}, {"DisplayName": "App B"}]
                    ),
                    "asset_type": "pc",
                }
            )
        ]
        rows = prepare_rows_for_global_client_excel(assets)
        self.assertEqual(len(rows), 1)
        self.assertIn("Observaciones_de_Riesgo", rows[0])
        self.assertEqual(rows[0]["software_list"], "App A, App B")

    def test_invalid_json_software_left_unchanged(self):
        raw = "[not valid json"
        assets = [normalize_asset({"software_list": raw})]
        rows = prepare_rows_for_global_client_excel(assets)
        self.assertEqual(rows[0]["software_list"], raw)


class TestSnapshotSoftwareCell(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(format_snapshot_software_cell(None), "")
        self.assertEqual(format_snapshot_software_cell(""), "")

    def test_joins_with_semicolon_and_name_fallback(self):
        s = json.dumps(
            [{"DisplayName": "A"}, {"Name": "B"}, {"k": "v"}]
        )
        out = format_snapshot_software_cell(s)
        self.assertIn("A", out)
        self.assertIn("B", out)


class TestParseSoftwareList(unittest.TestCase):
    def test_parses_json_string(self):
        raw = '[{"DisplayName": "X", "DisplayVersion": "1"}]'
        rows = parse_software_list_dicts(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("DisplayName"), "X")

    def test_invalid_returns_empty(self):
        self.assertEqual(parse_software_list_dicts("not json"), [])


class TestHardwareRowObs(unittest.TestCase):
    def test_adds_spanish_column(self):
        asset = normalize_asset({"mac": "aa:bb", "asset_type": "laptop"})
        row = hardware_row_with_observaciones_riesgo(asset)
        self.assertIn("Observaciones de Riesgo", row)
        self.assertIn("portátil", row["Observaciones de Riesgo"].lower())


class TestSnapshotDataframe(unittest.TestCase):
    def test_columns_and_software_formatted(self):
        rows = [
            {
                "ip": "10.0.0.1",
                "mac": "m",
                "software_list": '[{"DisplayName": "App"}]',
            }
        ]
        df = prepare_snapshot_inventory_dataframe(rows)
        self.assertEqual(len(df), 1)
        self.assertIn("Software", df.columns)
        self.assertIn("App", df.iloc[0]["Software"])


class TestRenderExcelBytes(unittest.TestCase):
    def test_global_empty_still_xlsx(self):
        b = render_global_client_excel_bytes([])
        self.assertTrue(b.startswith(b"PK"))

    def test_single_asset_xlsx(self):
        b = render_single_asset_excel_bytes(
            normalize_asset({"mac": "m", "ip": "1.1.1.1", "hostname": "x"})
        )
        self.assertTrue(b.startswith(b"PK"))

    def test_snapshot_xlsx(self):
        b = render_snapshot_archive_excel_bytes([{"ip": "10.0.0.1", "mac": "a"}])
        self.assertTrue(b.startswith(b"PK"))


class TestColumnsContract(unittest.TestCase):
    def test_global_columns_include_risk(self):
        self.assertIn("Observaciones_de_Riesgo", GLOBAL_INVENTORY_COLUMNS)

    def test_snapshot_column_count(self):
        self.assertEqual(len(SNAPSHOT_INVENTORY_COLUMNS), 22)


def normalize_asset(d):
    """Misma forma que normalize_asset_for_frontend mínima para estas pruebas."""
    from app.api.inventory_asset_model import normalize_asset_for_frontend

    return normalize_asset_for_frontend(d)


if __name__ == "__main__":
    unittest.main()
