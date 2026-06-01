"""Lectura tail de eve / alertas recientes."""
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.api.casador_support_constants import (
    SURICATA_ALERTS_PATH,
    SURICATA_EVE_PATH,
    SURICATA_TAIL_MAX_BYTES,
    _DEFAULT_EVE_ALERTS,
)
from app.api.casador_support_state import _is_blocked, _is_external_ip


def _read_file_tail_lines(path: str, max_bytes: int) -> List[str]:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return []
            start = max(0, size - max_bytes)
            f.seek(start)
            chunk = f.read()
        text = chunk.decode("utf-8", errors="ignore")
        if start > 0 and "\n" in text:
            text = text.split("\n", 1)[1]
        return [ln.strip() for ln in text.splitlines() if ln.strip()]
    except (OSError, IOError):
        return []


def _parse_suricata_timestamp(ts: str) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        s = ts.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        elif re.search(r"[+-]\d{4}$", s):
            s = re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", s)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _last_eve_event_age_sec(path: str) -> Optional[float]:
    lines = _read_file_tail_lines(path, max_bytes=256 * 1024)
    now = datetime.now(timezone.utc)
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        ts = ev.get("timestamp")
        if not ts:
            continue
        dt = _parse_suricata_timestamp(ts)
        if dt is None:
            continue
        return (now - dt.astimezone(timezone.utc)).total_seconds()
    return None


def _resolve_suricata_alerts_file() -> str:
    if SURICATA_ALERTS_PATH and os.path.isfile(SURICATA_ALERTS_PATH):
        return SURICATA_ALERTS_PATH
    if os.path.isfile(_DEFAULT_EVE_ALERTS):
        return _DEFAULT_EVE_ALERTS
    return SURICATA_EVE_PATH


def _read_suricata_recent_alerts(limit: int = 200) -> tuple[List[Dict[str, Any]], str]:
    path = _resolve_suricata_alerts_file()
    out: List[Dict[str, Any]] = []
    if not path or not os.path.isfile(path):
        return [], path or ""
    lines = _read_file_tail_lines(path, max(SURICATA_TAIL_MAX_BYTES, 512 * 1024))
    for line in reversed(lines):
        if len(out) >= limit:
            break
        if '"event_type"' not in line:
            continue
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if ev.get("event_type") != "alert":
            continue
        alert_obj = ev.get("alert") or {}
        src_ip = ev.get("src_ip") or ""
        severity = alert_obj.get("severity") or 3
        out.append(
            {
                "timestamp": ev.get("timestamp") or "",
                "src_ip": src_ip,
                "src_port": ev.get("src_port") or 0,
                "dest_ip": ev.get("dest_ip") or "",
                "dest_port": ev.get("dest_port") or 0,
                "proto": ev.get("proto") or "",
                "signature": alert_obj.get("signature") or "",
                "sid": alert_obj.get("signature_id") or 0,
                "severity": severity,
                "category": alert_obj.get("category") or "",
                "action": alert_obj.get("action") or "allowed",
                "is_external": _is_external_ip(src_ip),
                "is_blocked": _is_blocked(src_ip),
            }
        )
    return out, path
