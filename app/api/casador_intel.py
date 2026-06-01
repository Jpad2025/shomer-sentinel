"""Casador — remedios, alertas Suricata, salud del pipeline."""
import os
import subprocess
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.auth_api import get_current_user, require_admin

from app.api.casador_support import (
    REMEDIES_JSON_PATH,
    _collect_pipeline_health,
    _context_from_asset,
    _load_remedies,
    _read_suricata_recent_alerts,
)
from app.api.casador_support_state import _get_config
from app.backend.db import get_connection

router = APIRouter()


def _set_config(key: str, value) -> None:
    import json
    with get_connection(timeout=10) as conn:
        conn.execute(
            "INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        conn.commit()


@router.get("/suricata/status")
async def suricata_status(user=Depends(get_current_user)) -> Dict[str, Any]:
    """Estado actual de Suricata: activo/detenido + flag hunter.enabled en BD."""
    try:
        r = subprocess.run(["systemctl", "is-active", "suricata"], capture_output=True, text=True, timeout=5)
        running = (r.stdout or "").strip() == "active"
    except Exception:
        running = False
    enabled = bool(_get_config("hunter.enabled", True))
    return {"success": True, "running": running, "enabled": enabled}


@router.post("/suricata/toggle")
async def suricata_toggle(body: Dict[str, Any] = Body(...), user=Depends(require_admin)) -> Dict[str, Any]:
    """Activar o desactivar Suricata temporalmente. Body: {"enable": true|false}"""
    enable = bool(body.get("enable", True))
    action = "start" if enable else "stop"
    try:
        subprocess.run(["sudo", "systemctl", action, "suricata"], capture_output=True, timeout=15)
        _set_config("hunter.enabled", enable)
        try:
            r = subprocess.run(["systemctl", "is-active", "suricata"], capture_output=True, text=True, timeout=5)
            running = (r.stdout or "").strip() == "active"
        except Exception:
            running = enable
        return {"success": True, "enabled": enable, "running": running,
                "message": "Suricata iniciado" if enable else "Suricata detenido"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/guide")
async def get_mitigation_guide(body: Dict[str, Any] = Body(...), user=Depends(get_current_user)) -> Dict[str, Any]:
    software_list = body.get("software_list")
    os_detected = (body.get("os_detected") or "").strip()
    ports_open = (body.get("ports_open") or "").strip()
    asset_type = (body.get("asset_type") or "").strip()
    remedies = _load_remedies()
    if not remedies:
        return {"success": True, "recommendations": [], "message": "No hay glosario de remedios cargado."}
    context = _context_from_asset(software_list, os_detected, ports_open, asset_type)
    recommendations: List[Dict[str, str]] = []
    seen = set()
    for proto, rules in remedies.items():
        if not isinstance(rules, list):
            continue
        for rule in rules:
            patterns = [str(p).strip().upper() for p in rule.get("match_contains", []) if p]
            if patterns and not any(p in context for p in patterns):
                continue
            allowed_types = [str(t).lower() for t in rule.get("asset_types", []) if t]
            if allowed_types and (asset_type or "").lower() and not any(
                t in (asset_type or "").lower() for t in allowed_types
            ):
                continue
            msg = str(rule.get("message", "")).strip()
            cmd = str(rule.get("command", "")).strip()
            if not msg:
                continue
            key = (msg, cmd)
            if key in seen:
                continue
            seen.add(key)
            recommendations.append({"protocol": proto, "message": msg, "command": cmd or ""})
    return {"success": True, "recommendations": recommendations}


@router.get("/suricata/recent")
async def get_suricata_recent(limit: int = 200, user=Depends(get_current_user)) -> Dict[str, Any]:
    alerts, src = _read_suricata_recent_alerts(limit=min(limit, 200))
    return {
        "success": True,
        "alerts": alerts,
        "count": len(alerts),
        "source_file": os.path.basename(src) if src else "",
    }


@router.get("/pipeline/health")
async def get_pipeline_health(user=Depends(get_current_user)) -> Dict[str, Any]:
    return _collect_pipeline_health()


@router.get("/raw")
async def get_remedies_raw(user=Depends(get_current_user)) -> Dict[str, Any]:
    data = _load_remedies()
    if not data and REMEDIES_JSON_PATH and not os.path.isfile(REMEDIES_JSON_PATH):
        raise HTTPException(status_code=404, detail=f"remedies.json no encontrado en {REMEDIES_JSON_PATH}")
    return {"success": True, "remedies": data}
