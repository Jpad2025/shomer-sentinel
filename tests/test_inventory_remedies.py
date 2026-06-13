"""Tests — inventory_remedies."""
import json
import os
import tempfile
import unittest

from app.api.inventory_remedies import load_remedies_json


class TestLoadRemedies(unittest.TestCase):
    def test_loads_dict(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"a": {"fix": "x"}}, f)
            data = load_remedies_json(path)
            self.assertIn("a", data)
        finally:
            os.unlink(path)

    def test_non_object_root_becomes_empty(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("[1,2]")
            data = load_remedies_json(path)
            self.assertEqual(data, {})
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
