#!/usr/bin/env python3
"""
Active response / script auxiliar: Wazuh → Shomer POST /remedies/block (blocked_by=wazuh).

Uso (Wazuh manager): lee un JSON en stdin (formato de alerta active-response) y extrae
la IP de origen del evento. Variables de entorno:
  SHOMER_WAZUH_INTEGRATION_KEY  — misma clave que hunter.integration_key o cabecera
  SHOMER_API_URL                — default http://127.0.0.1:8000/remedies/block
"""
from __future__ import annotations

import ipaddress
import json
import os
import sys
import urllib.error
import urllib.request


def _is_ip(s: str) -> bool:
    s = s.strip()
    if not s or " " in s:
        return False
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _walk_src_ip(obj, depth: int = 0) -> str | None:
    """Busca el primer valor plausibles de IP en claves típicas Suricata/Wazuh."""
    if depth > 40:
        return None
    if isinstance(obj, dict):
        for key in (
            "srcip",
            "src_ip",
            "source_ip",
        ):
            v = obj.get(key)
            if isinstance(v, str) and _is_ip(v) and "255.255.255.255" not in v:
                return v.strip()
        for v in obj.values():
            r = _walk_src_ip(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _walk_src_ip(v, depth + 1)
            if r:
                return r
    return None


def _meta_from_alert(obj) -> tuple:
    """(signature, sid, severity) aproximados. Busca .alert en raíz, parameters o data."""
    sig = ""
    sid = None
    sev = 3
    if not isinstance(obj, dict):
        return sig, sid, sev
    parts = (obj, obj.get("parameters") or {}, obj.get("data") or {})
    for part in parts:
        if not isinstance(part, dict):
            continue
        a = part.get("alert")
        if isinstance(a, dict) and a.get("signature") is not None:
            sig = str(a.get("signature") or "")[:400]
            try:
                sid = int(a.get("signature_id") or 0) or None
            except (TypeError, ValueError):
                sid = None
            try:
                sev = int(a.get("severity") or 3)
            except (TypeError, ValueError):
                sev = 3
            return sig, sid, sev
    return sig, sid, sev


def main() -> int:
    key = (os.environ.get("SHOMER_WAZUH_INTEGRATION_KEY") or "").strip()
    kf = (os.environ.get("SHOMER_WAZUH_KEY_FILE") or "").strip()
    if not key and kf:
        try:
            with open(kf, "r", encoding="utf-8", errors="ignore") as f:
                key = f.read().strip()
        except OSError as e:
            print(f"wazuh_shomer_block: no se pudo leer SHOMER_WAZUH_KEY_FILE: {e}", file=sys.stderr)
            return 2
    if not key:
        print("wazuh_shomer_block: defina SHOMER_WAZUH_INTEGRATION_KEY o SHOMER_WAZUH_KEY_FILE", file=sys.stderr)
        return 2
    raw = sys.stdin.read()
    if not raw.strip():
        print("wazuh_shomer_block: sin JSON en stdin", file=sys.stderr)
        return 1
    try:
        j = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"wazuh_shomer_block: JSON inválido: {e}", file=sys.stderr)
        return 1

    ip = _walk_src_ip(j)
    if not ip:
        print("wazuh_shomer_block: no se encontró src_ip/srcip en el evento", file=sys.stderr)
        return 1

    sig, sid, sev = _meta_from_alert(j)
    m = (j.get("parameters") or {}).get("message") or (j.get("parameters") or {}).get("full_log")
    if isinstance(m, str) and m.strip():
        sig = m.strip()[:400]
    if not sig:
        sig = "Wazuh → Shomer"

    url = (os.environ.get("SHOMER_API_URL") or "http://127.0.0.1:8000/remedies/block").strip()
    body = {
        "ip": ip,
        "blocked_by": "wazuh",
        "alert_signature": sig or "Wazuh event",
        "severity": sev,
    }
    if sid is not None:
        body["alert_sid"] = sid

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Shomer-Integration-Key": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            out = resp.read().decode("utf-8", errors="replace")
            print(out)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"wazuh_shomer_block: HTTP {e.code} {err}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"wazuh_shomer_block: error de red: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
