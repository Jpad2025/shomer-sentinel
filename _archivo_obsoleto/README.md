# Archivo obsoleto

Código del backend anterior a la reescritura del proyecto, conservado aquí
en vez de borrarlo del historial de git. No lo usa ningún servicio, ningún
script de despliegue y ningún import del código activo lo referencia —
verificado con `grep` sobre `app/`, `tools/` y `tests/`.

**Por qué sigue aquí y no se borró sin más:** sirve de referencia si algún
día hace falta recordar cómo se resolvía algo antes (por ejemplo,
`reboot_playwright.py` o `router_http_manager.py`), sin tener que ir a
excavar commits viejos.

**Se puede borrar sin riesgo** cuando alguien confirme que ya no hace falta
esa referencia — no rompe nada porque nada lo usa hoy.

`tools/fleet_estado.py` y `fleet_sync_core.sh` ya excluyen esta carpeta de
la comparación y sincronización entre sitios: es historia del maestro, nunca
llegó a los labs ni debe llegar.
