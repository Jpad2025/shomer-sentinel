"""Archivo shomer-local.rules y recarga Suricata."""
import logging
import os
import re
import subprocess
from typing import Dict, List

from app.api.casador_support_constants import SURICATA_LOCAL_RULES, SURICATA_YAML_PATH

_log = logging.getLogger("casador.rules_file")


def _ensure_local_rules_file():
    """7 sep 2026 (auditoría Hunter): antes fallaba en silencio -- se llama
    en cada GET/POST /remedies/rules; si el proceso no tiene permiso de
    escritura sobre suricata.yaml (no corre como root), esto nunca se
    aplicaba y nadie se enteraba. El chequeo `if fname not in yaml_text`
    ya evita reescribir el YAML si no hace falta -- solo agregamos log en
    el camino de error, sin cambiar cuándo se llama."""
    if not os.path.isfile(SURICATA_LOCAL_RULES):
        try:
            os.makedirs(os.path.dirname(SURICATA_LOCAL_RULES), exist_ok=True)
            with open(SURICATA_LOCAL_RULES, "w") as f:
                f.write("# Shomer Sentinel — Reglas locales personalizadas\n")
                f.write("# Formato Suricata: action proto src_ip src_port -> dst_ip dst_port (opciones)\n")
        except Exception as e:
            _log.warning("_ensure_local_rules_file: no se pudo crear %s: %s", SURICATA_LOCAL_RULES, e)

    try:
        with open(SURICATA_YAML_PATH, "r") as f:
            yaml_text = f.read()
        fname = os.path.basename(SURICATA_LOCAL_RULES)
        if fname not in yaml_text:
            new_text = yaml_text.replace(
                "  - suricata.rules",
                f"  - suricata.rules\n  - {fname}",
            )
            if new_text != yaml_text:
                with open(SURICATA_YAML_PATH, "w") as f:
                    f.write(new_text)
    except Exception as e:
        _log.warning("_ensure_local_rules_file: no se pudo actualizar %s: %s", SURICATA_YAML_PATH, e)


def _parse_local_rules() -> List[Dict]:
    """Incluye reglas comentadas como enabled=False (panel toggle)."""
    rules = []
    if not os.path.isfile(SURICATA_LOCAL_RULES):
        return rules
    try:
        with open(SURICATA_LOCAL_RULES, "r") as f:
            lines = f.readlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue
            enabled = True
            if stripped.startswith("#"):
                inner = stripped[1:].strip()
                # 7 sep 2026 (auditoría Hunter): las 2 líneas de encabezado
                # del archivo se mostraban como reglas fantasma con
                # sid=None -- sus botones de encender/borrar apuntaban a
                # /remedies/rules/null (422).
                #
                # 7 sep 2026, re-auditoría: el primer fix solo exigía "->",
                # pero la SEGUNDA línea del encabezado ("Formato Suricata:
                # ... -> ...") también contiene esa flecha como parte del
                # texto explicativo -- seguía colándose. Una regla Suricata
                # real (y toda regla que este mismo código genera, ver
                # casador_rules.py) siempre trae "sid:NNNN"; un comentario
                # descriptivo, aunque mencione "->", no. Exigir ambos
                # elimina las 2 líneas de encabezado sin excepción.
                if (
                    not inner
                    or inner.startswith("#")
                    or "->" not in inner
                    or not re.search(r"\bsid\s*:\s*\d+", inner)
                ):
                    continue
                content = inner
                enabled = False
            else:
                content = stripped
            sid_match = re.search(r"\bsid\s*:\s*(\d+)", content)
            sid = int(sid_match.group(1)) if sid_match else None
            msg_match = re.search(r'\bmsg\s*:\s*"([^"]*)"', content)
            msg = msg_match.group(1) if msg_match else content[:80]
            rules.append(
                {
                    "lineno": lineno,
                    "sid": sid,
                    "msg": msg,
                    "enabled": enabled,
                    "raw": content,
                }
            )
    except Exception:
        pass
    return rules


def _next_local_sid() -> int:
    rules = _parse_local_rules()
    sids = [r["sid"] for r in rules if r["sid"] and r["sid"] >= 9000000]
    return max(sids) + 1 if sids else 9000001


def _reload_suricata() -> bool:
    """SIGUSR2 al proceso suricata (igual que POST /remedies/rules/reload)."""
    try:
        pid_proc = subprocess.run(["pidof", "suricata"], capture_output=True, text=True, timeout=5)
        pid = (pid_proc.stdout or "").strip().split()
        if pid:
            r = subprocess.run(["sudo", "kill", "-USR2", pid[0]], capture_output=True, timeout=5)
            return r.returncode == 0
        r2 = subprocess.run(
            ["sudo", "systemctl", "reload-or-restart", "suricata"],
            capture_output=True,
            timeout=10,
        )
        return r2.returncode == 0
    except Exception:
        return False
