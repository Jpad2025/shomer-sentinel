"""
SHOMER Guardian — agregador de routers para la API en puerto 8000.

- shomer_guardian: nodos, heartbeat, discovery, maintenance, router-devices
- shomer_config: system_state, network_context, escaneo panel
- shomer_setup: wizard primera instalación
- shomer_proxies: Tracker y Protector → 8001
"""
from fastapi import APIRouter

from app.api.shomer_common import (
    get_config,
    get_enabled_modules,
    is_module_enabled,
    require_module,
    set_config,
)
from app.api.shomer_config import router as shomer_config_router
from app.api.shomer_guardian import router as shomer_guardian_router
from app.api.shomer_proxies import router as shomer_proxies_router
from app.api.shomer_setup import router as shomer_setup_router
from app.api.shomer_system_status import router as shomer_system_status_router

router = APIRouter(tags=["Shomer Guardian"])
router.include_router(shomer_proxies_router)
router.include_router(shomer_setup_router)
router.include_router(shomer_config_router)
router.include_router(shomer_guardian_router)
router.include_router(shomer_system_status_router)

__all__ = [
    "router",
    "get_config",
    "set_config",
    "get_enabled_modules",
    "is_module_enabled",
    "require_module",
]
