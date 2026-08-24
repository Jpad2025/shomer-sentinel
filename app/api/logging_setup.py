"""Configuración de logging de la app (Sesión 75).

Hallazgo: ningún logger.warning()/error()/info() de la app llegaba
FORMATEADO al log -- no es que se perdieran (sí llegaban), sino que el
root logger nunca tuvo un handler propio, así que Python usaba su
`logging.lastResort` (fallback silencioso a stderr) con formato
`%(message)s` puro -- sin nivel, sin timestamp, sin nombre de logger.
Verificado con un caso real: "AUTO-BLOCK 192.168.0.27 sid=..." SÍ estaba
en el log (api.log.2.gz, 22 ago), pero sin ningún prefijo -- indistinguible
de un print() a simple vista, e invisible para cualquier `grep WARNING` o
`grep ERROR` normal (que es como se buscaba hasta ahora).

Esto NO afecta a uvicorn.*/uvicorn.access (esos ya tienen su propio
handler con propagate=False -- por eso las líneas "INFO:     " sí se ven
bien formateadas). Configurar el root logger acá no las duplica.
"""
from __future__ import annotations

import logging

_CONFIGURED = False


def configure_app_logging(level: int = logging.WARNING) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)
