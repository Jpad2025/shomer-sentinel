"""Glosario remedies.json y contexto para guía de mitigación."""
import json
import os
from typing import Any, Dict

from app.backend.db import REMEDIES_JSON_PATH

_REMEDIES_CACHE: Dict[str, Any] = {}


def _load_remedies() -> Dict[str, Any]:
    global _REMEDIES_CACHE
    if _REMEDIES_CACHE:
        return _REMEDIES_CACHE
    if not REMEDIES_JSON_PATH or not os.path.isfile(REMEDIES_JSON_PATH):
        return {}
    try:
        with open(REMEDIES_JSON_PATH, "r", encoding="utf-8") as f:
            _REMEDIES_CACHE = json.load(f)
    except Exception:
        _REMEDIES_CACHE = {}
    return _REMEDIES_CACHE


def _context_from_asset(software_list, os_detected, ports_open, asset_type) -> str:
    parts = [(os_detected or "").strip(), (ports_open or "").strip(), (asset_type or "").strip()]
    if software_list:
        if isinstance(software_list, str):
            try:
                arr = json.loads(software_list)
                if isinstance(arr, list):
                    for item in arr:
                        parts.append(
                            (item.get("DisplayName") or "" if isinstance(item, dict) else str(item)).strip()
                        )
            except Exception:
                parts.append(software_list[:2000])
        elif isinstance(software_list, list):
            for item in software_list[:200]:
                parts.append(
                    (item.get("DisplayName") or "" if isinstance(item, dict) else str(item)).strip()
                )
    return " ".join(p for p in parts if p).upper()
