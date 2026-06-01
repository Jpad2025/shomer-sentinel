"""
Núcleo Guardian: agrega sub-routers (nodos, eventos, discovery, devices).

Extraído y modularizado desde shomer.py; rutas y comportamiento sin cambios.
"""
from fastapi import APIRouter

from app.api.shomer_guardian_devices import router as shomer_guardian_devices_router
from app.api.shomer_guardian_discovery import router as shomer_guardian_discovery_router
from app.api.shomer_guardian_events import router as shomer_guardian_events_router
from app.api.shomer_guardian_nodes import router as shomer_guardian_nodes_router

router = APIRouter(tags=["Shomer Guardian"])
router.include_router(shomer_guardian_nodes_router)
router.include_router(shomer_guardian_events_router)
router.include_router(shomer_guardian_discovery_router)
router.include_router(shomer_guardian_devices_router)
