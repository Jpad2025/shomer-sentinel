"""14 sep 2026: revisión al detalle encontró que el botón "Activar Object
Lock" de Protector (backups.html) llamaba a `/backups/b2/object-lock/enable`
y `/backups/b2/object-lock/status` -- ambos implementados de verdad en
`backups.py` (puerto 8001), pero SIN proxy correspondiente en
`shomer_proxies.py` (puerto 8000, lo que el panel realmente usa). El botón
existía, el backend existía, y aun así daba 404 -- nadie lo notó porque
nada comparaba automáticamente "qué llama el HTML" contra "qué existe
registrado". Esta prueba escanea TODOS los templates por cada
`shomerFetch('/ruta')` y confirma que la ruta esté realmente registrada en
la app -- para que esta clase de botón fantasma no vuelva a colarse sin que
un test lo note.
"""
import re
from pathlib import Path

import pytest

from app.api.main import app

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "templates"
_FETCH_RE = re.compile(r"shomerFetch\(\s*['\"](/[^'\"]+)['\"]")

# Rutas usadas por el panel con parámetros embebidos en el JS (concatenación
# `'/ruta/' + id`) que no matchean un path-param de FastAPI ('{id}') por
# comparación literal -- se resuelven a su patrón real antes de comparar.
_TRAILING_SLASH_ES_PARAM = True


def _rutas_registradas() -> set[str]:
    return {r.path for r in app.routes if hasattr(r, "path")}


def _normalizar_para_comparar(path: str) -> str:
    """Quita querystring y, si termina en '/', asume que el JS iba a
    concatenar un id ahí -- se compara solo el prefijo."""
    path = path.split("?")[0]
    return path


def _matchea_alguna_ruta(llamado: str, registradas: set[str]) -> bool:
    llamado = _normalizar_para_comparar(llamado)
    if llamado in registradas:
        return True
    # Terminaba en '/': el JS le pega un id/ip después (concatenación).
    # Buscar una ruta registrada que empiece igual y tenga un {param} justo
    # después del mismo prefijo.
    if llamado.endswith("/"):
        prefijo = llamado
        for r in registradas:
            if r.startswith(prefijo) and "{" in r[len(prefijo):]:
                return True
            if r == prefijo.rstrip("/"):
                return True
    return False


def _llamadas_por_template() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for f in sorted(_TEMPLATES_DIR.glob("*.html")):
        texto = f.read_text(encoding="utf-8", errors="replace")
        llamadas = set(_FETCH_RE.findall(texto))
        if llamadas:
            out[f.name] = llamadas
    return out


@pytest.mark.parametrize("template,llamadas", _llamadas_por_template().items())
def test_cada_shomerfetch_tiene_una_ruta_registrada(template, llamadas):
    registradas = _rutas_registradas()
    huerfanas = sorted(
        l for l in llamadas if not _matchea_alguna_ruta(l, registradas)
    )
    assert not huerfanas, (
        f"{template} llama a estas rutas via shomerFetch() pero ninguna está "
        f"registrada en la app (botón fantasma -- 404 real al usarlo): {huerfanas}"
    )


def test_el_escaneo_encontro_templates_con_llamadas(tmp_path=None):
    """Guarda contra que el regex se rompa silenciosamente y la prueba de
    arriba pase vacía sin revisar nada."""
    llamadas = _llamadas_por_template()
    assert len(llamadas) >= 5, "se esperaban varios templates con shomerFetch()"
    total = sum(len(v) for v in llamadas.values())
    assert total >= 30, f"muy pocas llamadas detectadas ({total}) -- ¿se rompió el regex?"
