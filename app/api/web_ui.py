"""
Vistas web: app/templates/ es el ÚNICO lugar para las vistas.
Todas las rutas HTML sirven plantillas Jinja2 desde ahí.
Sidebar: SHOMER=/, INVENTARIO=/inventory, FIREWALL=/security, BACKUPS=/backups.
Protección de rutas: /, /inventory, /security, /backups exigen token válido (cookie access_token o Bearer); si no, 302 a /login.
"""
import os
import socket
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.auth_api import verify_token

router = APIRouter(tags=["Web UI"])

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _docs_tecnico_vars(request: Request) -> dict:
    """Contexto para /docs/tecnico: red desde get_network_context(), URL panel sin hardcodear."""
    ctx: dict = {"request": request, "active_module": "docs_tecnico"}
    n: dict = {}
    try:
        from app.scripts.network_context import get_network_context

        n = get_network_context() or {}
    except Exception:
        pass
    server_ip = (n.get("server_ip") or "").strip()
    subnet = (n.get("subnet") or "").strip()
    gateway = (n.get("gateway") or "").strip()
    interface = (n.get("interface") or "").strip()
    public_url = (os.environ.get("SHOMER_PUBLIC_HTTPS_URL") or "").strip()
    if not public_url and server_ip:
        public_url = f"https://{server_ip}:8443"
    elif not public_url:
        public_url = "https://<IP-DEL-SHOMER-DETECTADA-EN-RED>:8443"
    raw = (os.environ.get("SHOMER_BEHIND_PROXY") or "").strip().lower()
    try:
        report_content = _build_informe_report()
    except Exception as e:
        report_content = "Error al generar el resumen: %s" % str(e)[:500]
    ctx.update(
        {
            "panel_url_sugerida": public_url,
            "server_ip": server_ip or "—",
            "subnet": subnet or "—",
            "gateway": gateway or "—",
            "interface": interface or "—",
            "behind_proxy": raw in ("1", "true", "yes"),
            "cors_origins": (os.environ.get("SHOMER_CORS_ORIGINS") or "").strip() or "—",
            "report_content": report_content,
            "install_doc_url": "/static/docs/Instalacion_Shomer_Produccion_Tecnico.md",
            "sistema_doc_url": "/static/docs/SISTEMA_SHOMER.md",
            "tracker_cuenta_doc_url": "/static/docs/Tracker_cuenta_servicio_inventario.md",
            "hunter_campo_doc_url": "/static/docs/Hunter_pruebas_campo_checklist.md",
            "manual_doc_url": "/static/docs/Pasos_Instalacion_Shomer_v2422026.md",
            "compendio_doc_url": "/static/docs/Shomer_Compendio_Completo.md",
            "usb_install_doc_url": "/static/docs/Instalacion_Ubuntu_USB_Particiones.md",
            "tailscale_doc_url": "/static/docs/Instalacion_Remota_Tailscale.md",
            "soporte_doc_url": "/static/docs/SOPORTE_TECNICO.md",
            "telegram_doc_url": "/static/docs/Manual_Telegram_Bot.md",
        }
    )
    return ctx


def _build_informe_report() -> str:
    """Texto copiable para soporte: hora UTC, hostname, red desde BD/detección (sin archivos externos)."""
    lines = [
        "=== SHOMER SENTINEL — Resumen técnico (soporte) ===",
        "",
        "Pegue este bloque en correo o ticket si se lo piden.",
        "",
        f"Generado (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}Z",
        "",
    ]
    try:
        lines.append(f"Hostname: {socket.gethostname()}")
        lines.append("")
    except Exception:
        pass
    try:
        from app.scripts.network_context import get_network_context

        ctx = get_network_context()
        lines.append("Contexto de red (BD / detección):")
        for key, label in (
            ("interface", "interfaz"),
            ("subnet", "subred"),
            ("gateway", "gateway"),
            ("server_ip", "IP servidor"),
        ):
            val = ctx.get(key)
            if val:
                lines.append(f"  {label}: {val}")
        lines.append("")
    except Exception:
        lines.append("(Contexto de red no disponible en este momento.)")
        lines.append("")
    lines.append("Documentación en panel: menú «Guía técnica» → /docs/tecnico")
    lines.append("Instalación producción: /static/docs/Instalacion_Shomer_Produccion_Tecnico.md")
    lines.append("Guía maestra del sistema: /static/docs/SISTEMA_SHOMER.md")
    lines.append("Tracker — cuenta de servicio (WMI/SSH): /static/docs/Tracker_cuenta_servicio_inventario.md")
    lines.append("Hunter — pruebas en campo: /static/docs/Hunter_pruebas_campo_checklist.md")
    lines.append("Anexo detallado (MikroTik/TFTP): /static/docs/Pasos_Instalacion_Shomer_v2422026.md")
    lines.append("")
    return "\n".join(lines)


def _get_token_from_request(request: Request) -> Optional[str]:
    """Token desde cookie access_token o cabecera Authorization: Bearer."""
    token = request.cookies.get("access_token")
    if token:
        return token
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def _require_auth_redirect(request: Request) -> Optional[RedirectResponse]:
    """Si no hay token válido, devuelve RedirectResponse a /login. Si hay sesión válida, devuelve None."""
    token = _get_token_from_request(request)
    if not verify_token(token):
        return RedirectResponse(url="/login", status_code=302)
    return None


@router.get("/setup", response_class=HTMLResponse, include_in_schema=False)
async def setup_page(request: Request):
    """Setup — requiere sesión admin. Sin sesión → /login. Sin rol admin → /."""
    token = _get_token_from_request(request)
    payload = verify_token(token)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    if (payload.get("role") or "") != "admin":
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "setup.html",
        {"request": request, "active_module": "setup"},
    )


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page(request: Request):
    """Licencia, usuarios y contraseña — solo admin."""
    token = _get_token_from_request(request)
    payload = verify_token(token)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    if (payload.get("role") or "") != "admin":
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "active_module": "admin"},
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def monitor_page(request: Request):
    """Raíz: Monitor, tabla de nodos. Requiere autenticación. Sin config de red → /setup (si admin)."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    from app.api.shomer import get_config
    from app.api.auth_api import verify_token as _vt
    if get_config("base.subnet", None) is None:
        payload = _vt(_get_token_from_request(request))
        if payload and payload.get("role") == "admin":
            return RedirectResponse(url="/setup", status_code=302)
    return templates.TemplateResponse(
        "guardian.html",
        {"request": request, "active_page": "monitor"},
    )


@router.get("/inventory", response_class=HTMLResponse, include_in_schema=False)
async def inventory_page(request: Request):
    """Inventario: tabla 39 campos, drawer 32 campos, QR y motor de guardado. Requiere autenticación."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "inventory.html",
        {"request": request, "active_page": "inventory"},
    )


@router.get("/tracker", response_class=HTMLResponse, include_in_schema=False)
async def tracker_page(request: Request):
    """Inventario IT (Tracker): misma vista que /inventory. Ruta alternativa para evitar conflicto con API /inventory/ en proxy."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "inventory.html",
        {"request": request, "active_page": "inventory"},
    )


@router.get("/backups", response_class=HTMLResponse, include_in_schema=False)
async def backups_page(request: Request):
    """Backups (Restic): snapshots y salud. Requiere autenticación."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "backups.html",
        {"request": request, "active_page": "backups"},
    )


@router.get("/security", response_class=HTMLResponse, include_in_schema=False)
async def security_page(request: Request):
    """Panel de Ciberseguridad: Suricata, Wazuh, Guía de Mitigación (Casador). Requiere autenticación."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "hunter.html",
        {"request": request, "active_page": "security"},
    )


@router.get("/incidentes", response_class=HTMLResponse, include_in_schema=False)
async def incidents_page(request: Request):
    """Incidentes de seguridad — R2."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "incidents.html",
        {"request": request, "active_module": "hunter"},
    )


@router.get("/audit", response_class=HTMLResponse, include_in_schema=False)
async def audit_page(request: Request):
    """Auditoría del sistema — R8/R12. Solo admin."""
    token = _get_token_from_request(request)
    payload = verify_token(token)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    if (payload.get("role") or "") != "admin":
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "audit.html",
        {"request": request, "active_module": "audit"},
    )


@router.get("/infra", response_class=HTMLResponse, include_in_schema=False)
async def inframonitor_page(request: Request):
    """Inframonitor — monitoreo ICMP dispositivos de red."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "inframonitor.html",
        {"request": request, "active_module": "inframonitor"},
    )


@router.get("/reportes", response_class=HTMLResponse, include_in_schema=False)
async def reportes_page(request: Request):
    """Reportes — generación PDF por rango de fechas."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "reportes.html",
        {"request": request, "active_module": "reportes"},
    )


@router.get("/index.html", include_in_schema=False)
async def redirect_index():
    """Acceso directo a index.html redirige a la raíz unificada."""
    return RedirectResponse(url="/", status_code=302)


@router.get("/8000", include_in_schema=False)
async def redirect_8000():
    """Ruta literal /8000 redirige a la raíz para unificar acceso."""
    return RedirectResponse(url="/", status_code=302)


@router.get("/firewall", include_in_schema=False)
async def redirect_firewall():
    """Ruta legacy /firewall unificada a /security."""
    return RedirectResponse(url="/security", status_code=302)


@router.get("/docs/tecnico", response_class=HTMLResponse, include_in_schema=False)
async def docs_tecnico_page(request: Request):
    """Documentación técnica — solo admin."""
    token = _get_token_from_request(request)
    payload = verify_token(token)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    if (payload.get("role") or "") != "admin":
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "docs_tecnico.html",
        _docs_tecnico_vars(request),
    )


@router.get("/system-status", response_class=HTMLResponse, include_in_schema=False)
async def system_status_page(request: Request):
    """Estado del sistema: servicios, recursos, logs en vivo. Requiere autenticación."""
    redirect = _require_auth_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "system_status.html",
        {"request": request, "active_module": "system_status"},
    )


@router.get("/docs/fallas", response_class=HTMLResponse, include_in_schema=False)
async def docs_fallas_page(request: Request):
    """Glosario de fallas — solo admin."""
    token = _get_token_from_request(request)
    payload = verify_token(token)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)
    if (payload.get("role") or "") != "admin":
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "docs_fallas.html",
        {"request": request, "active_module": "docs_fallas"},
    )


@router.get("/informe", include_in_schema=False)
async def informe_page(request: Request):
    """Legacy: el resumen copiable vive en /docs/tecnico#resumen-soporte."""
    redir = _require_auth_redirect(request)
    if redir is not None:
        return redir
    return RedirectResponse(url="/docs/tecnico#resumen-soporte", status_code=302)

