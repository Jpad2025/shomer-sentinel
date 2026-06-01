"""
Lectura de remedies.json (glosario mitigaciones Tracker).
Sin FastAPI.
"""
from __future__ import annotations

import json
from typing import Any, Dict


def load_remedies_json(remedies_path: str) -> Dict[str, Any]:
    """Carga JSON; si el root no es objeto, devuelve {}."""
    with open(remedies_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return data
