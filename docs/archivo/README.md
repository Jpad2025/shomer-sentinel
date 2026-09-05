# Archivo — informes cerrados

Auditorías e informes de un momento específico, ya resueltos, que se guardan
como referencia histórica (no se borran — tienen valor para consultar qué se
encontró y cómo se arregló) pero no describen trabajo pendiente ni se
conectan a la IA (chat/cerebro).

**Antes de mover algo aquí:** verificar en el código real que lo que describe
el documento efectivamente se hizo — no basta con que "suene viejo" o tenga
fecha antigua. Ver sesión 81 (4 sep 2026): dos documentos que parecían
informes cerrados por su fecha resultaron ser planes de trabajo a medio
implementar (`AUDITORIA_POLLERS_CONSOLIDADA.md`, `AUDITORIA_POLL_ONCE_INFRAMONITOR.md`)
y se quedaron activos en `docs/` en vez de archivarse aquí.

| Documento | Por qué está cerrado |
|-----------|----------------------|
| `AUDITORIA_ASYNC_BLOQUEANTE.md` | Los 2 hallazgos reales (crash loop de `/health`) están arreglados y probados con carga real. El resto es una lista de referencia a propósito sin tocar. |
| `Auditoria_Seguridad_Beta_2026-05-30.md` | Auditoría pre-lanzamiento beta — 21/21 controles verificados, sin pendientes bloqueantes. |
