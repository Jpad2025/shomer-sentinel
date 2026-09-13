# Auditoría de arquitectura, organización y buenas prácticas

**Fecha:** 12 de septiembre de 2026
**Alcance:** los dos repositorios (`network_monitor` core + `shomer-agent`), verificado contra el estado real en disco y en git — nada de lo que sigue es supuesto.

---

## Resumen

El código está en buen estado de fondo: convenciones de commit consistentes, `.gitignore` cuidado (nada de `.db`, `.env`, backups o credenciales termina en git), y evidencia real de que el equipo ya divide un archivo en módulos cuando crece demasiado (`monitor.py` le cedió 5 responsabilidades a módulos propios con el tiempo). No es un proyecto descuidado.

Lo que sigue son focos concretos de desorden — todos verificados, ninguno inventado — ordenados por qué tan urgentes son.

---

## 1. Archivos huérfanos versionados en git

Cuatro archivos están en el repositorio y **nada los usa**. Confirmado con `grep` contra todo el código y `git log` de su último cambio real:

| Archivo | Última vez tocado | Por qué es huérfano |
|---|---|---|
| `etc/shomer-monitor.service` | Sesión 44 (el primer commit "limpio" del proyecto) | Describe una arquitectura vieja ("SHOMER Monitor Pro v2.0"); el instalador de hoy genera `shomer-guardian.service` con contenido totalmente distinto. Solo se le menciona en un comentario como algo que tenían "instalaciones viejas". |
| `database/schema.sql` | — | Nada lo invoca. Ni el instalador ni ningún script de migración lo lee. |
| `database/migrate_shomer_tables.sql` | — | Igual: huérfano. |
| `test_scripts/test_reboot_2222.py` | — | Vive fuera de `tests/` (que sí tiene 34 archivos activos), y no lo corre ningún runner. Segunda carpeta de pruebas, con un solo archivo. |

**Nota aparte:** `etc/shomer-frontpanel.service` y `etc/shomer-led-strip.service`, que están en la misma carpeta, **sí se usan** — `deploy.sh` los copia a `/etc/systemd/system/` para el hardware físico de los labs. No son huérfanos, solo están mal ubicados (ver punto 4).

**Recomendación:** borrar los 4 huérfanos. Es una limpieza de bajo riesgo — nada los referencia, así que no rompen nada al desaparecer.

---

## 2. Contenido específico de un sitio mezclado con documentación genérica — y ya se propagó

`docs/` es la carpeta de documentación del **producto**, y por eso el `fleet_sync_core.sh` que construí hoy la sincroniza a toda la flota. Pero `docs/REPORTE_CAIDAS_POS_HOTEL_OPERA.md` es un informe con nombres de equipos y hallazgos privados **de Ópera**, no del producto.

**Verificado ahora mismo: ese archivo ya está en los tres laboratorios.** No es un riesgo teórico — ya ocurrió, hoy, con la herramienta que yo mismo construí esta sesión.

Es la misma clase de problema que las normas B.1/B.3 del proyecto existen para evitar (nunca mezclar configuración o datos de un cliente con el producto genérico), aplicada esta vez a documentación en vez de a código o base de datos.

**Recomendación:** mover los reportes de un sitio específico (como este) a una carpeta que `fleet_sync_core.sh` excluya explícitamente — por ejemplo `docs/sitios/<nombre>/`, tratada igual que `.env` o `SITE.md`. `docs/` debería quedar reservada para lo que de verdad sirve en cualquier hotel (guías, reglas de despliegue, catálogos).

---

## 3. La carpeta `_archivo_obsoleto/` no explica su propio propósito

Tiene 13 archivos versionados (código del backend viejo antes de la reescritura), y la decisión de archivarlo en vez de borrarlo del historial es razonable — pero **no hay ni un README adentro** que diga por qué existe, desde cuándo, o si algún día se puede borrar. Cualquiera que abra el repo por primera vez no sabe si es basura o referencia.

**Recomendación:** un `_archivo_obsoleto/README.md` de tres líneas resuelve esto. Costo mínimo, aclara una ambigüedad real.

---

## 4. Inconsistencia de nombres: Tracker es `inventory_*` en un lado y `tracker/` en otro

En `app/api/` hay 12 archivos con prefijo `inventory_*` que son el módulo que en todo el resto del proyecto (documentación, UI, Telegram) se llama **Tracker**. Pero en `app/scripts/` sí existe una carpeta `tracker/` con ese nombre correcto.

No es un error funcional — es una fricción real para cualquiera que busque el código de "Tracker" y no encuentre nada con ese nombre en la carpeta de API.

Los otros prefijos sí tienen sentido: `shomer_*` (32 archivos, el grueso genérico), `casador_*` (14 archivos, "casador" es el nombre interno de Hunter, consistente en sí mismo).

**Recomendación:** de baja prioridad, solo cosmética — no vale la pena renombrar 12 archivos importados en decenas de lugares dos días antes de salir a producción. Dejarlo anotado para la próxima ventana de mantenimiento.

---

## 5. Archivos grandes que mezclan varias responsabilidades

| Archivo | Líneas | Qué mezcla |
|---|---:|---|
| `core/conocimiento_general.py` (agente) | 5.330 | 45% son literales de texto largos (contenido CompTIA validado) — es una base de conocimiento, no lógica desordenada. Debatible si debería vivir como JSON/YAML en vez de código Python, para separar "contenido" de "lógica" y hacer los diffs más legibles. **No urgente.** |
| `core/monitor.py` (agente) | 4.472 | El orquestador de los 38 monitores del agente. Ya le sacó 5 módulos propios con el tiempo (`pulse_correlate`, `chronic_tickets`, `incident_escalation`, `vpn_usuarios`, `informe_coordinador`). Su tamaño hoy es razonable para ser el punto central de tantos ciclos independientes — no es un monolito desorganizado, es un orquestador grande. |
| `core/bot.py` (agente) | 3.458 | 88 handlers de comandos/botones de Telegram. Mismo caso: muchas piezas pequeñas, no una lógica enredada. |
| `app/api/shomer_inframonitor.py` (core) | 2.358 | Este sí mezcla géneros distintos en un archivo: migraciones de esquema (líneas 110-412), helpers de red (413-925), poller completo (1098-1790) y 429 líneas de endpoints HTTP al final (1929-2358). Es el candidato más claro a dividir — el propio proyecto ya separó `shomer_infra_pulse.py` y `shomer_wan_hotel.py` de aquí antes; el patrón para hacerlo ya existe. |
| `app/api/backups.py` (core) | 1.744 | 4 secciones razonables (dispositivos, ejecución, scheduler, B2). Tamaño aceptable. |

**Recomendación:** ninguno de estos bloquea la salida a producción. Si se retoma después, `shomer_inframonitor.py` es el que más se beneficiaría de separar el poller y los endpoints en sus propios archivos — mismo patrón ya usado en el proyecto.

---

## 6. Dos estilos de comentario de sección conviviendo

`shomer_inframonitor.py` usa un bloque de dos líneas:
```python
# ──────────────────────────────────────────────
# Poller
# ──────────────────────────────────────────────
```
mientras `backups.py` usa una sola línea con el título adentro:
```python
# ── Scheduler de backups por equipo ──────────────────────────────────────────
```
Ambos son legibles; conviven en el mismo repositorio sin un criterio único. Cosmético, cero riesgo, se homogeniza solo si algún día se toca cada archivo por otra razón.

---

## Lo que está bien hecho (para no listar solo problemas)

- **`.gitignore` es serio**: cubre `.db`, `.env`, backups, `SITE.md` — verifiqué que nada de eso está en git en ninguno de los dos repos.
- **El patrón de dividir cuando crece ya existe y se usa**: 5 módulos nacieron de `monitor.py`, 2 nacieron de `shomer_inframonitor.py`. No es una decisión que haya que instaurar desde cero.
- **Los mensajes de commit y docstrings son consistentemente explicativos** — cada archivo grande revisado documenta el porqué de sus decisiones, no solo el qué.
- **Separación real por servicio**: puerto 8000 (Guardian/Hunter) y 8001 (Tracker/Protector) como procesos independientes, no una app monolítica.

---

## Prioridad sugerida

1. **Ahora, bajo riesgo**: mover `REPORTE_CAIDAS_POS_HOTEL_OPERA.md` fuera de `docs/` compartido — ya se propagó a los 3 labs.
2. **Ahora, bajo riesgo**: borrar los 4 archivos huérfanos.
3. **Cuando haya una ventana**: README en `_archivo_obsoleto/`, dividir `shomer_inframonitor.py`.
4. **Sin apuro**: renombrar `inventory_*` a `tracker_*`, homogeneizar el estilo de comentarios, evaluar mover `conocimiento_general.py` a datos.

Nada de esta lista es necesario para que el sistema funcione — es exclusivamente para que el código se mantenga ordenado a medida que crece.
