#!/usr/bin/env python3
"""
SHOMER Core API — Puerto 8000.
Módulos críticos 24/7: Guardian (monitoreo) + Hunter (seguridad).
Tracker y Protector corren en puerto 8001 (shomer-tools.service) — accesibles
via proxies /tracker/* y /backups/* definidos en shomer.py.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth_api import router as auth_router
from app.api.cors_util import cors_allow_origins
from app.api.login_html import read_login_html
from app.api.security_http import (
    SecurityHeadersMiddleware,
    install_proxy_headers_middleware,
    install_trusted_host_middleware,
)
from app.api.web_ui import router as web_router
from app.api.shomer import router as shomer_router
from app.api.casador import router as casador_router
from app.api.shomer_guardian_server_health import (
    router as server_health_router,
    start_server_health_tasks,
)
from app.api.shomer_inframonitor import router as inframonitor_router
from app.api.shomer_noc import router as noc_router
from app.api.shomer_incidents import router as incidents_router
from app.api.shomer_audit import router as audit_router, install_audit_middleware
from app.api.shomer_audit_export import router as audit_export_router
from app.api.shomer_audit_network import router as audit_network_router
from app.api.shomer_reports import router as reports_router

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_STATIC_DIR = os.path.join(_APP_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.api.shomer_guardian_nodes import start_node_poller
    from app.api.shomer_inframonitor import start_inframonitor_poller
    start_node_poller()
    start_server_health_tasks()
    start_inframonitor_poller()
    yield


app = FastAPI(
    title="SHOMER API",
    description="API de comunicación con el Monitor Pro v2.0",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: SHOMER_CORS_ORIGINS=lista separada por comas, o * (default)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
install_trusted_host_middleware(app)
install_proxy_headers_middleware(app)
install_audit_middleware(app)

# Archivos estáticos (CSS, JS, imágenes de marca)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# ========== RUTAS DE LOGIN PRIMERO (antes de cualquier router) ==========
@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page():
    return HTMLResponse(read_login_html())


@app.get("/api/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page_api():
    return HTMLResponse(read_login_html())


@app.get("/login/ok")
@app.get("/api/login/ok")
async def login_ok():
    return {"login": "ok", "rutas_activas": True}

# ========== Fin rutas login ==========

app.include_router(auth_router)
# Guardian — monitoreo 24/7 (nodes, heartbeat, reboot, config, maintenance, events)
app.include_router(shomer_router)
# Guardian server health — WAN quorum, métricas servidor, heartbeat report
app.include_router(server_health_router)
# Hunter — seguridad 24/7 (bloqueo, alertas Suricata, reglas, guía mitigación)
app.include_router(casador_router)
# Inframonitor — monitoreo ICMP de switches, servidores y cualquier equipo de red
app.include_router(inframonitor_router)
# NOC Display — dashboard TV tiempo real (token en URL, sin login)
app.include_router(noc_router)
# Incidentes — R2: tabla de seguridad con ack/cierre y MTTA/MTTR
app.include_router(incidents_router)
# Auditoría — R8: log de cambios POST/PUT/DELETE con usuario y resultado
app.include_router(audit_router)
# Auditoría export — R12: reporte cruzado auditoría + incidentes + drills
app.include_router(audit_export_router)
# Auditoría de Red — escaneo nmap, hallazgos por severidad/estado, badges Inframonitor
app.include_router(audit_network_router)
app.include_router(reports_router)
# Web UI — templates Jinja2 (todas las vistas del panel)
app.include_router(web_router)

# Endpoints Guardian: un solo punto de verdad en app.api.shomer


@app.get("/api/info")
async def root():
    """Información de la API SHOMER."""
    return {
        "api": "SHOMER",
        "version": "1.0.0",
        "endpoints": {
            "nodes": "GET /nodes - Estado de nodos (Redis + datos heartbeat)",
            "heartbeat": "POST /heartbeat - Heartbeat con clients/uptime/puntos; a 1 fallo reinicio SSH (lab)",
            "reboot": "POST /reboot/{ip} - Reinicio manual por SSH (llave privada)",
            "reset_failures": "POST /reset_failures/{ip} - Resetea contador fallos (panel actualiza tras reinicio)",
            "logs": "GET /logs - Últimos 50 registros infra_nodes",
            "health": "GET /health - Estado de Redis y monitor",
            "network_context": "GET /network_context - Subnet e interfaz para el panel",
            "config_scan": "POST /config/scan - Escaneo con subnets (body: { subnets })",
            "config_save_nodos": "POST /config/save_nodos - Guardar nodos elegidos",
            "maintenance": "GET/POST /maintenance - Modo mantenimiento (no reinicios auto)",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
