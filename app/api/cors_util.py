"""Orígenes CORS configurables sin hardcoding (SHOMER_CORS_ORIGINS)."""
import os
from typing import List


def cors_allow_origins() -> List[str]:
    raw = os.environ.get("SHOMER_CORS_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]
