"""Salud pipeline Suricata / Wazuh desde logs y systemctl."""
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List

from app.api.casador_support_constants import SURICATA_EVE_PATH
from app.api.casador_support_suricata import _last_eve_event_age_sec, _resolve_suricata_alerts_file


def _systemctl_is_active(unit: str) -> str:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (r.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def _collect_pipeline_health() -> Dict[str, Any]:
    stale_sec = int(os.environ.get("HUNTER_PIPELINE_STALE_SEC", "900"))  # 15 min default
    path = _resolve_suricata_alerts_file()
    issues: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, Any] = {}

    suricata = _systemctl_is_active("suricata.service")
    checks["suricata_service"] = suricata
    if suricata != "active":
        issues.append(f"Suricata no activo (systemctl: {suricata})")

    wazuh = _systemctl_is_active("wazuh-manager.service")
    checks["wazuh_manager_service"] = wazuh
    if wazuh not in ("active", "activating"):
        warnings.append(
            f"wazuh-manager no activo (systemctl: {wazuh}) — bloqueo automático vía integración no funcionará"
        )

    eve_path = path if path and os.path.isfile(path) else SURICATA_EVE_PATH
    checks["eve_log_path"] = eve_path
    checks["eve_log_exists"] = os.path.isfile(eve_path) if eve_path else False
    if not checks["eve_log_exists"]:
        issues.append("No existe el archivo de eventos EVE configurado — Suricata no escribe o ruta incorrecta")
    else:
        try:
            st = os.stat(eve_path)
            checks["eve_log_size_bytes"] = st.st_size
            checks["eve_log_mtime_age_sec"] = max(0.0, datetime.now().timestamp() - st.st_mtime)
        except OSError as e:
            checks["eve_log_stat_error"] = str(e)
            issues.append(f"No se pudo leer metadatos del log: {e}")

    last_age = _last_eve_event_age_sec(eve_path) if checks["eve_log_exists"] else None
    checks["last_event_age_sec"] = last_age
    if last_age is not None and last_age > stale_sec:
        issues.append(
            f"Último evento en EVE hace {int(last_age // 60)} min (> {stale_sec // 60} min) — "
            "revisar espejo SPAN, cable de la NIC mirror (Hunter) o red sin tráfico"
        )
    elif last_age is None and checks.get("eve_log_exists") and os.path.getsize(eve_path) > 0:
        warnings.append("No se pudo parsear timestamp en la cola del log — revisar formato")

    overall_ok = len(issues) == 0
    checks["stale_threshold_sec"] = stale_sec
    all_notes = issues + warnings
    return {
        "success": True,
        "overall_ok": overall_ok,
        "issues": issues,
        "warnings": warnings,
        "notes": all_notes,
        "checks": checks,
        "hint": "GET periódico (cron); ver manual — política de severidad y checklist de entrega.",
    }
