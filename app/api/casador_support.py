"""
Casador — fachada de lógica compartida (re-exporta submódulos).
Sin rutas FastAPI. Imports existentes: from app.api.casador_support import ...
"""
from fastapi import HTTPException

from app.backend.db import REMEDIES_JSON_PATH

from app.api.casador_support_constants import (
    SURICATA_ALERTS_PATH,
    SURICATA_EVE_PATH,
    SURICATA_LOCAL_RULES,
    SURICATA_TAIL_MAX_BYTES,
    SURICATA_YAML_PATH,
)
from app.api.casador_support_firewall import _mikrotik_block, _mikrotik_sync_block, _mikrotik_unblock
from app.api.casador_support_health import _collect_pipeline_health, _systemctl_is_active
from app.api.casador_support_redis_cb import (
    _CB_FAIL_KEY,
    _CB_STATUS_KEY,
    _CB_THRESHOLD,
    _cb_is_open,
    _cb_record_failure,
    _cb_record_success,
    _get_redis,
)
from app.api.casador_support_remedies import _context_from_asset, _load_remedies
from app.api.casador_support_rules_file import (
    _ensure_local_rules_file,
    _next_local_sid,
    _parse_local_rules,
    _reload_suricata,
)
from app.api.casador_support_state import (
    _ensure_blocked_ips_table,
    _get_config,
    _get_firewall_creds,
    _get_hunter_subnets,
    _is_blocked,
    _is_external_ip,
)
from app.api.casador_support_suricata import (
    _last_eve_event_age_sec,
    _parse_suricata_timestamp,
    _read_file_tail_lines,
    _read_suricata_recent_alerts,
    _resolve_suricata_alerts_file,
)

__all__ = [
    "REMEDIES_JSON_PATH",
    "SURICATA_ALERTS_PATH",
    "SURICATA_EVE_PATH",
    "SURICATA_LOCAL_RULES",
    "SURICATA_TAIL_MAX_BYTES",
    "SURICATA_YAML_PATH",
    "_CB_FAIL_KEY",
    "_CB_STATUS_KEY",
    "_CB_THRESHOLD",
    "_cb_is_open",
    "_cb_record_failure",
    "_cb_record_success",
    "_collect_pipeline_health",
    "_context_from_asset",
    "_ensure_blocked_ips_table",
    "_ensure_local_rules_file",
    "_get_config",
    "_get_firewall_creds",
    "_get_hunter_subnets",
    "_get_redis",
    "_is_blocked",
    "_is_external_ip",
    "_last_eve_event_age_sec",
    "_load_remedies",
    "_mikrotik_block",
    "_mikrotik_sync_block",
    "_mikrotik_unblock",
    "_next_local_sid",
    "_parse_local_rules",
    "_parse_suricata_timestamp",
    "_read_file_tail_lines",
    "_read_suricata_recent_alerts",
    "_reload_suricata",
    "_require_hunter",
    "_resolve_suricata_alerts_file",
    "_systemctl_is_active",
]


def _require_hunter():
    try:
        from app.api.shomer import is_module_enabled

        if not is_module_enabled("hunter"):
            raise HTTPException(
                status_code=403,
                detail="Módulo Hunter no habilitado en esta instalación",
            )
    except ImportError:
        pass
