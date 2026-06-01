"""
Casador — Hunter: mitigación, bloqueo IP, alertas Suricata, reglas locales.
API unificada bajo /remedies (puerto 8000).
"""
from fastapi import APIRouter

from app.api.casador_blocking import router as casador_blocking_router
from app.api.casador_intel import router as casador_intel_router
from app.api.casador_rules import router as casador_rules_router

router = APIRouter(prefix="/remedies", tags=["Casador"])
router.include_router(casador_blocking_router)
router.include_router(casador_intel_router)
router.include_router(casador_rules_router)
