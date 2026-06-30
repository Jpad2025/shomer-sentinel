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


def _lab_no_span() -> bool:
    """Lab sin espejo SPAN: sin tráfico en NIC mirror es normal — no degradar pipeline por EVE vacío."""
    return os.environ.get("SHOMER_LAB_NO_SPAN", "").strip().lower() in ("1", "true", "yes")


def _collect_pipeline_health() -> Dict[str, Any]:
    stale_sec = int(os.environ.get("HUNTER_PIPELINE_STALE_SEC", "900"))  # 15 min default
    lab_no_span = _lab_no_span()
    traffic_path = SURICATA_EVE_PATH
    alerts_path = _resolve_suricata_alerts_file()
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

    # Liveness = tráfico en eve.json (flow, dns, stats…). Las alertas en eve-alerts.json
    # pueden estar quietas de noche aunque el espejo reciba tráfico WAN normal.
    checks["eve_traffic_log_path"] = traffic_path
    checks["eve_traffic_log_exists"] = os.path.isfile(traffic_path) if traffic_path else False
    checks["eve_alerts_log_path"] = alerts_path
    checks["eve_log_path"] = traffic_path  # compat panel / bot
    checks["eve_log_exists"] = checks["eve_traffic_log_exists"]

    if not checks["eve_traffic_log_exists"]:
        issues.append(
            "No existe eve.json — Suricata no escribe o ruta incorrecta "
            f"({traffic_path})"
        )
    else:
        try:
            st = os.stat(traffic_path)
            checks["eve_log_size_bytes"] = st.st_size
            checks["eve_log_mtime_age_sec"] = max(0.0, datetime.now().timestamp() - st.st_mtime)
        except OSError as e:
            checks["eve_log_stat_error"] = str(e)
            issues.append(f"No se pudo leer metadatos de eve.json: {e}")

    last_traffic_age = (
        _last_eve_event_age_sec(traffic_path) if checks["eve_traffic_log_exists"] else None
    )
    last_alert_age = (
        _last_eve_event_age_sec(alerts_path)
        if alerts_path and os.path.isfile(alerts_path)
        else None
    )
    checks["last_traffic_age_sec"] = last_traffic_age
    checks["last_alert_age_sec"] = last_alert_age
    checks["last_event_age_sec"] = last_traffic_age  # compat bot watch_pipeline
    checks["lab_no_span"] = lab_no_span
    checks["stale_threshold_sec"] = stale_sec

    if last_traffic_age is not None and last_traffic_age > stale_sec:
        stale_msg = (
            f"Sin tráfico reciente en eve.json hace {int(last_traffic_age // 60)} min "
            f"(> {stale_sec // 60} min) — revisar espejo SPAN, cable NIC mirror (Hunter) o Suricata"
        )
        if lab_no_span:
            warnings.append(stale_msg + " (lab sin SPAN — esperado)")
        else:
            issues.append(stale_msg)
    elif last_traffic_age is None and checks.get("eve_traffic_log_exists"):
        traffic_size = os.path.getsize(traffic_path) if traffic_path else 0
        if traffic_size > 0:
            warnings.append("No se pudo parsear timestamp en eve.json — revisar formato")
        elif lab_no_span and suricata == "active":
            warnings.append("eve.json vacío — lab sin espejo SPAN (normal)")

    alert_stale_sec = int(
        os.environ.get("HUNTER_PIPELINE_ALERT_STALE_SEC", str(max(stale_sec * 4, 3600)))
    )
    checks["alert_stale_threshold_sec"] = alert_stale_sec
    if (
        last_alert_age is not None
        and last_traffic_age is not None
        and last_traffic_age <= stale_sec
        and last_alert_age > alert_stale_sec
    ):
        warnings.append(
            f"Sin alertas IDS en eve-alerts hace {int(last_alert_age // 60)} min "
            f"(tráfico espejo OK) — habitual de noche en WAN"
        )

    overall_ok = len(issues) == 0
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
