"""Casador — reglas locales Suricata (shomer-local.rules)."""
import os
import re
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.auth_api import get_current_user
import subprocess

from app.api.casador_support import (
    SURICATA_LOCAL_RULES,
    _ensure_local_rules_file,
    _next_local_sid,
    _parse_local_rules,
)

router = APIRouter()


@router.get("/rules")
async def list_suricata_rules(user=Depends(get_current_user)) -> Dict[str, Any]:
    _ensure_local_rules_file()
    rules = _parse_local_rules()
    return {
        "success": True,
        "rules": rules,
        "count": len(rules),
        "rules_file": SURICATA_LOCAL_RULES,
    }


@router.post("/rules")
async def add_suricata_rule(body: Dict[str, Any] = Body(...), user=Depends(get_current_user)) -> Dict[str, Any]:
    _ensure_local_rules_file()

    raw_rule = (body.get("rule") or "").strip()

    if not raw_rule:
        action = body.get("action", "alert")
        proto = body.get("proto", "tcp")
        src = body.get("src", "any")
        dst = body.get("dst", "any")
        port = body.get("port", "any")
        msg = body.get("msg", "Regla Shomer")
        content = body.get("content", "").strip()
        sid = _next_local_sid()

        content_opt = f' content:"{content}";' if content else ""
        raw_rule = (
            f"{action} {proto} {src} any -> {dst} {port} "
            f'(msg:"{msg}";{content_opt} sid:{sid}; rev:1;)'
        )

    if not re.search(r"\bsid\s*:\s*\d+", raw_rule):
        sid = _next_local_sid()
        raw_rule = raw_rule.rstrip(")").rstrip(";") + f"; sid:{sid}; rev:1;)"

    try:
        with open(SURICATA_LOCAL_RULES, "a") as f:
            f.write(f"\n{raw_rule}\n")
        return {"success": True, "message": "Regla agregada", "rule": raw_rule}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{sid}")
async def delete_suricata_rule(sid: int) -> Dict[str, Any]:
    if not os.path.isfile(SURICATA_LOCAL_RULES):
        raise HTTPException(status_code=404, detail="Archivo de reglas no encontrado")
    try:
        with open(SURICATA_LOCAL_RULES, "r") as f:
            lines = f.readlines()
        new_lines = [l for l in lines if not re.search(rf"\bsid\s*:\s*{sid}\b", l)]
        if len(new_lines) == len(lines):
            raise HTTPException(status_code=404, detail=f"SID {sid} no encontrado")
        with open(SURICATA_LOCAL_RULES, "w") as f:
            f.writelines(new_lines)
        return {"success": True, "message": f"Regla SID {sid} eliminada"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/rules/{sid}")
async def toggle_suricata_rule(sid: int, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    enabled = bool(body.get("enabled", True))
    if not os.path.isfile(SURICATA_LOCAL_RULES):
        raise HTTPException(status_code=404, detail="Archivo de reglas no encontrado")
    try:
        with open(SURICATA_LOCAL_RULES, "r") as f:
            lines = f.readlines()
        new_lines = []
        found = False
        for line in lines:
            if re.search(rf"\bsid\s*:\s*{sid}\b", line):
                found = True
                stripped = line.strip()
                if enabled:
                    new_lines.append(stripped.lstrip("#").strip() + "\n")
                else:
                    if not stripped.startswith("#"):
                        new_lines.append("# " + stripped + "\n")
                    else:
                        new_lines.append(line)
            else:
                new_lines.append(line)
        if not found:
            raise HTTPException(status_code=404, detail=f"SID {sid} no encontrado")
        with open(SURICATA_LOCAL_RULES, "w") as f:
            f.writelines(new_lines)
        return {
            "success": True,
            "message": f"SID {sid} {'activado' if enabled else 'desactivado'}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules/reload")
async def reload_suricata_rules(user=Depends(get_current_user)) -> Dict[str, Any]:
    try:
        check = subprocess.run(["systemctl", "is-active", "suricata"], capture_output=True, text=True, timeout=5)
        if check.stdout.strip() != "active":
            return {"success": False, "message": "Suricata no está activo"}

        pid_proc = subprocess.run(["pidof", "suricata"], capture_output=True, text=True, timeout=5)
        pid = pid_proc.stdout.strip()
        if pid:
            subprocess.run(["sudo", "kill", "-USR2", pid.split()[0]], capture_output=True, timeout=5)
            return {"success": True, "message": "Reglas recargadas (SIGUSR2 enviado)"}
        subprocess.run(["sudo", "systemctl", "reload", "suricata"], capture_output=True, timeout=15)
        return {"success": True, "message": "Reglas recargadas (systemctl reload)"}
    except Exception as e:
        return {"success": False, "message": str(e)}
