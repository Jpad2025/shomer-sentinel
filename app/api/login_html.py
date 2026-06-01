"""
Plantilla de login compartida: Core (8000) y Tools (8001).
Un solo path al directorio de templates; fallback si no hay archivo."""
import os

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGIN_HTML_PATH = os.path.join(_APP_DIR, "templates", "login.html")

_FALLBACK_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Login</title></head>
<body style="font-family:sans-serif;background:#111;color:#ccc;padding:2rem;">
<h1>Shomer Sentinel</h1>
<p>No se pudo cargar la plantilla de login. Compruebe permisos en app/templates/login.html</p>
<p><a href="/">Volver</a></p>
</body></html>"""


def read_login_html() -> str:
    try:
        with open(LOGIN_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return _FALLBACK_HTML
