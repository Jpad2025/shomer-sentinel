#!/usr/bin/env python3
"""
SHOMER Tools API — Puerto 8001.
Módulos ocasionales: Tracker (inventario) + Protector (backups).
Guardian y Hunter corren en puerto 8000 (shomer-core.service).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.auth_api import router as auth_router
from app.api.cors_util import cors_allow_origins
from app.api.login_html import read_login_html
from app.api.security_http import (
    SecurityHeadersMiddleware,
    install_proxy_headers_middleware,
    install_trusted_host_middleware,
)
from app.api.inventory import router as assets_inventory_router
from app.api.inventory import export_router, rescan_router, snapshot_router
from app.api.backups import router as backups_router, start_backup_scheduler
from app.api.shomer_drill import router as drill_router
from app.api.shomer_reports import router as reports_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.scripts.restore_drill import start_drill_scheduler
    from app.api.shomer_reports import start_report_scheduler
    start_backup_scheduler()
    start_drill_scheduler()
    start_report_scheduler()
    yield


app = FastAPI(
    title="SHOMER Tools API",
    description="Tracker (inventario) + Protector (backups) — puerto 8001",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
install_trusted_host_middleware(app)
install_proxy_headers_middleware(app)

@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page():
    return HTMLResponse(read_login_html())


@app.get("/login/ok")
async def login_ok():
    return {"login": "ok", "service": "tools", "port": 8001}


app.include_router(auth_router)
# Tracker — inventario de activos
app.include_router(assets_inventory_router)
app.include_router(export_router)
app.include_router(snapshot_router)
app.include_router(rescan_router)
# Protector — backups
app.include_router(backups_router)
# Drill — R3: restore drill mensual + trigger manual
app.include_router(drill_router)
# Reports — R1: reporte mensual PDF
app.include_router(reports_router)


@app.get("/health")
async def health():
    import os
    from app.backend.db import INVENTORY_DB_PATH
    return {
        "success": True,
        "service": "tools",
        "port": 8001,
        "db_exists": os.path.exists(INVENTORY_DB_PATH),
    }


@app.get("/api/info")
async def info():
    from app.backend.db import INVENTORY_DB_PATH
    return {"api": "SHOMER Tools", "version": "1.0.0", "port": 8001,
            "modules": ["tracker", "protector"], "db": INVENTORY_DB_PATH}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
