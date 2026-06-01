"""
Cabeceras HTTP orientadas a producción y opciones de despliegue detrás de HTTPS.
El cifrado real lo hace un reverse proxy (Caddy/nginx); aquí: cabeceras y cookies alineadas.
"""
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Añade cabeceras recomendadas OWASP (sin CSP estricto — el panel usa scripts inline)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        xfo = (os.environ.get("SHOMER_X_FRAME_OPTIONS") or "DENY").strip()
        if xfo:
            response.headers["X-Frame-Options"] = xfo
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if _truthy("SHOMER_ENABLE_HSTS"):
            max_age = (os.environ.get("SHOMER_HSTS_MAX_AGE") or "15552000").strip()
            response.headers["Strict-Transport-Security"] = f"max-age={max_age}; includeSubDomains"
        return response


def install_trusted_host_middleware(app):
    """
    Si SHOMER_TRUSTED_HOSTS está definido (coma-separado), rechaza Host no listado.
    Ej.: 10.0.0.63,localhost,shomer.local
    """
    raw = (os.environ.get("SHOMER_TRUSTED_HOSTS") or "").strip()
    if not raw:
        return
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    if not hosts:
        return
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)


def install_proxy_headers_middleware(app):
    """
    Activo si SHOMER_BEHIND_PROXY=1. Confía en X-Forwarded-Proto / X-Forwarded-For
    del reverse proxy (p. ej. Caddy en 127.0.0.1). Sin esto, request.url.scheme sigue siendo http.
    SHOMER_PROXY_TRUSTED_HOSTS: coma-separado, default 127.0.0.1,::1. Usar * solo en entornos controlados.
    """
    if not _truthy("SHOMER_BEHIND_PROXY"):
        return
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    raw = (os.environ.get("SHOMER_PROXY_TRUSTED_HOSTS") or "127.0.0.1,::1").strip()
    if raw == "*":
        trusted = "*"
    else:
        parts = [h.strip() for h in raw.split(",") if h.strip()]
        if not parts:
            trusted = "127.0.0.1"
        elif len(parts) == 1:
            trusted = parts[0]
        else:
            trusted = parts
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted)


def cookie_secure_default() -> bool:
    """Fuerza cookie Secure vía entorno (útil sin proxy o para pruebas)."""
    return _truthy("SHOMER_COOKIE_SECURE")


def cookie_secure_for_request(request: Request) -> bool:
    """
    Cookie Secure si: SHOMER_COOKIE_SECURE=1, o bien proxy activo y el cliente llegó por HTTPS
    (requiere SHOMER_BEHIND_PROXY=1 y middleware de proxy headers).
    """
    if _truthy("SHOMER_COOKIE_SECURE"):
        return True
    if _truthy("SHOMER_BEHIND_PROXY") and request.url.scheme == "https":
        return True
    return False
