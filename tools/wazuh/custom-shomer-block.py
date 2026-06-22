#!/usr/bin/env python3
"""
Wazuh → Shomer: bloqueo automático vía POST /remedies/block (blocked_by=wazuh).
Reglas disparadoras: 100100 (Critical), 100101 (High), 100102 (Medium).
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

ERR_BAD_ARGUMENTS = 2
ERR_FILE_NOT_FOUND = 6
ERR_INVALID_JSON = 7

_DB_PATH = "/storage/db/network_monitor.db"
_DEFAULT_PORT = 8000
_MAX_RETRIES = 3
_RETRY_DELAY_S = 5
SHOMER_BLOCK_RULES = {"100100", "100101", "100102"}


def _get_config(key: str, default: str = "") -> str:
    try:
        with sqlite3.connect(_DB_PATH, timeout=3) as conn:
            row = conn.execute(
                "SELECT value FROM system_state WHERE key=?", (key,)
            ).fetchone()
            if row and row[0] is not None:
                return str(row[0]).strip()
    except Exception:
        pass
    return default


def _get_api_endpoint() -> str:
    ip = _get_config("base.server_ip")
    host = ip or "127.0.0.1"
    return f"http://{host}:{_DEFAULT_PORT}/remedies/block"


def _get_integration_key() -> str:
    env = (os.environ.get("SHOMER_WAZUH_INTEGRATION_KEY") or "").strip()
    if env:
        return env
    kf = (os.environ.get("SHOMER_WAZUH_KEY_FILE") or "/var/ossec/etc/shomer-integration.key").strip()
    if kf and os.path.isfile(kf):
        try:
            with open(kf, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
        except OSError:
            pass
    return _get_config("hunter.integration_key")


def _log(msg: str) -> None:
    try:
        with open("/var/ossec/logs/integrations.log", "a", encoding="utf-8") as f:
            f.write(f"shomer-integration: {msg}\n")
    except Exception:
        pass


def _post_block(endpoint: str, payload: bytes, key: str) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Shomer-Integration-Key": key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:300]
            return True, f"HTTP {resp.status}: {body}"
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:300]
        return False, f"HTTP {e.code}: {err}"
    except Exception as e:
        return False, str(e)


def _severity_from_alert(alert: dict) -> int:
    data = alert.get("data") or {}
    a = data.get("alert") if isinstance(data.get("alert"), dict) else {}
    try:
        return int(a.get("severity") or alert.get("rule", {}).get("level") or 3)
    except (TypeError, ValueError):
        return 3


def main(args):
    if len(args) < 3:
        _log(f"ERROR: argumentos insuficientes: {args}")
        sys.exit(ERR_BAD_ARGUMENTS)

    alert_file = args[1]
    if not os.path.exists(alert_file):
        _log(f"ERROR: archivo alerta no encontrado: {alert_file}")
        sys.exit(ERR_FILE_NOT_FOUND)

    try:
        with open(alert_file, "r", encoding="utf-8") as f:
            alert = json.load(f)
    except Exception as e:
        _log(f"ERROR: JSON inválido: {e}")
        sys.exit(ERR_INVALID_JSON)

    rule_id = str(alert.get("rule", {}).get("id", ""))
    if rule_id not in SHOMER_BLOCK_RULES:
        sys.exit(0)

    data = alert.get("data") or {}
    src_ip = data.get("src_ip") or data.get("srcip") or alert.get("srcip")
    if not src_ip:
        _log(f"ERROR: src_ip no encontrado rule={rule_id}")
        sys.exit(0)

    alert_obj = data.get("alert") if isinstance(data.get("alert"), dict) else {}
    signature = (
        alert_obj.get("signature")
        or alert.get("rule", {}).get("description")
        or "Wazuh Suricata"
    )
    sid = alert_obj.get("signature_id") or 0
    severity = _severity_from_alert(alert)
    key = _get_integration_key()
    if not key:
        _log("ERROR: hunter.integration_key vacío — no se puede autenticar con Shomer")
        sys.exit(1)

    endpoint = _get_api_endpoint()
    payload = json.dumps(
        {
            "ip": src_ip,
            "blocked_by": "wazuh",
            "alert_signature": str(signature)[:400],
            "alert_sid": sid,
            "severity": severity,
        }
    ).encode("utf-8")

    _log(f"INFO: bloqueando {src_ip} rule={rule_id} sev={severity}")

    for attempt in range(1, _MAX_RETRIES + 1):
        ok, detail = _post_block(endpoint, payload, key)
        if ok:
            _log(f"OK: {src_ip} rule={rule_id} intento={attempt} → {detail}")
            sys.exit(0)
        _log(f"WARN: intento {attempt}/{_MAX_RETRIES} fallido: {detail}")
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_DELAY_S)

    _log(f"ERROR: {src_ip} NO bloqueado tras {_MAX_RETRIES} intentos")
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
