"""Rutas y límites Suricata vía entorno (sin hardcoding de IPs)."""
import os

SURICATA_EVE_PATH = os.environ.get("SURICATA_EVE_PATH", "/var/log/suricata/eve.json")
SURICATA_ALERTS_PATH = os.environ.get("SURICATA_ALERTS_PATH", "").strip()
SURICATA_TAIL_MAX_BYTES = int(os.environ.get("SURICATA_TAIL_MAX_BYTES", str(12 * 1024 * 1024)))
SURICATA_LOCAL_RULES = os.environ.get("SURICATA_LOCAL_RULES", "/etc/suricata/rules/shomer-local.rules")
SURICATA_YAML_PATH = os.environ.get("SURICATA_YAML_PATH", "/etc/suricata/suricata.yaml")
_DEFAULT_EVE_ALERTS = "/var/log/suricata/eve-alerts.json"
