# Shomer Sentinel 2.0 — Manifiesto vivo

Este archivo une **dos cosas** en un solo lugar: (1) **qué hace el sistema hoy**, según instalación real y laboratorio USB; (2) **normas de diseño y referencia técnica** sin perder línea base del producto.

Los manuales de instalación detallados (cableado, modelo por modelo) y las tablas QA fila por fila **no** caben completos aquí; el equipo debe entregarlos en el mismo paquete de instalación donde corresponda. Este archivo concentra arquitectura, normas y estado sintético.

**Última unificación:** 26-27 ago 2026 (revisión exhaustiva de TODO `network_monitor` — bug de seguridad real corregido: audit_log guardaba contraseñas en texto plano, ver Sesión 76 abajo) · Sesión 76 · Idioma: español · Código: `/opt/network_monitor/` + `/storage/shomer-agent/`

---

## ⛔ Disciplina modular (OBLIGATORIA — agentes Cursor / técnicos)

Regla espejo: `.cursor/rules/shomer-modulos-disciplina.mdc` (`alwaysApply: true`).

1. **Leer primero** este `CLAUDE.md` (sección del módulo) + `SITE.md` del sitio **antes** de tocar código, BD o servicios.
2. **Un módulo por tarea:** Tracker · Protector · Hunter · Guardian/Infra — no mezclar en el mismo paso.
3. **Credenciales solo del módulo:** Tracker → `network_credentials`; Protector → `backup_devices`; Hunter → `hunter.firewall_*`; Guardian → `devices`. **Prohibido cruzar** (p. ej. pass Zeus/Protector para WMI Tracker o APs).
4. **Prohibido** scripts “de ayuda”, limpiezas o “ya que estoy…” no pedidos.
5. **Producción (Hotel Ópera):** deploy / rsync / restart / SQL de escritura **solo** con autorización explícita (**adelante**). Preferir lab `.205` para experimentos.
6. Si **no está en el pedido** → preguntar; no hacer.

Detalle usuario de servicio del sitio: Parte D.2, abajo. Credenciales Tracker AD y Protector con cuenta local distinta: mismo criterio, ver `docs/GUIA_PROYECTO_SHOMER.md`.

---

# 🔑 Estado vivo — LÉEME PRIMERO (resumen curado)

> Última reescritura completa: **13 sep 2026**, contra el sistema real corriendo (no memoria,
> no supuestos — cada dato de esta sección se verificó ese día contra código, configuración o
> el sistema en vivo). Partes A–N (abajo) = manual estable, revisado y corregido la misma fecha.
> Historia completa de sesiones (1–68 en `CLAUDE_historico.md`; 69–88 archivadas ahí mismo el
> 13 sep) → **`CLAUDE_historico.md`**. Config específica del sitio → **`SITE.md`** (NO va a git).

## Disciplina (obligatoria)
- **Un módulo por tarea** (Tracker / Protector / Hunter / Guardian / Inframonitor / Bot). No cruzar credenciales.
- Producción Ópera: sin autorización explícita → no deploy, no restart, no SQL de escritura, no scripts no pedidos (norma B.3).
- **Nunca** correr código de módulos con `sudo`/root → siembra archivos root que rompen servicios (ver lecciones).
- Nunca proponer cerrar/restringir Tailscale como "hallazgo de seguridad" — es el único puente de acceso remoto (norma B.4).
- Regla Cursor: `.cursor/rules/shomer-modulos-disciplina.mdc`.

## Dónde vive todo
- Core (Guardian/Hunter/Tracker/Protector/Inframonitor/NOC): `/opt/network_monitor/` — repo propio (`github:Jpad2025/shomer-sentinel`), Ópera es el maestro de la flota.
- Agente/Bot/Cerebro: `/storage/shomer-agent/` — repo git propio (`github:jpad2025/shomer-agent`).
- Flota: Ópera (producción real) + 3 labs (`shomer205`, `shomer245`, `shomer243`) — hoy laboratorio de desarrollo, destinados a convertirse en instalaciones de clientes nuevos. `tools/fleet_estado.py` (compara contenido real, no commits) y `tools/fleet_sync_core.sh` / `tools/fleet_sync.sh` (propagan y verifican) mantienen la flota consistente — correrlos tras cualquier cambio, nunca confiar en que "ya se sincronizó".
- BD reales: `/storage/db/network_monitor.db` (Guardian/Hunter/Protector/Inframonitor) · `/storage/db/inventory.db` (Tracker). Los symlinks en `/opt/*.db` son solo red de seguridad → deben apuntar a estos.
- Servicios Ópera: `shomer-guardian` (Core :8000), `shomer-tools` (:8001), `shomer-inframonitor-poller` (standalone, independiente de los dos anteriores) como **usb_admin**; `shomer-agent` en Docker (root, por diseño).
- Config: `system_state` (BD, prefijos `base.*`/`guardian.*`/`hunter.*`/`tracker.*`/`protector.*`) + `.env` por sitio (agente) + `/etc/shomer/shomer-runtime.env` (`JWT_SECRET`, permisos 750 `root:usuario_servicio`) + Redis (estado efímero). Deuda reconocida: 3 fuentes sin consolidar.

## Estado por módulo (vigente, verificado 13 sep 2026)
- **Guardian** (`app/api/shomer_guardian_nodes.py` + `_health_checks`/`_server_health`/`_lib`): 30 APs reales en Ópera. Auto-reboot SSH/SNMP (umbral configurable, cooldown tras éxito vs. `fail_retry_sec` tras fallo). Estado en **Redis**: `failures:`, `last_reboot:`, `node_maintenance:`. ⚠️ `node_maintenance:*` con TTL −1 suprime alertas **en silencio**. El latido "todo OK" y el aviso de reinicio de Shomer ya no interrumpen por Telegram salvo que el reinicio se repita (`guardian.reinicios_para_avisar`, 3 por defecto) — la prueba de vida se registra igual y sale en el resumen diario.
- **Hunter** (`app/api/casador_blocking.py` + `_support_*`): bloqueo de IPs, dos backends intercambiables por `hunter.firewall_type` — `routeros` (MikroTik nativo, el caso de Ópera, que usó un equipo ya existente) u `openwrt`/genérico (iptables por SSH, el caso de los firewalls que se flashean y se envían con cada servidor nuevo — procedimiento vigente, ver Parte E.5). Tras el incidente del 8 sep (bloqueó DNS de Google por error): existen listas de infraestructura crítica que nunca se autobloquean (`NUNCA_AUTOBLOQUEAR`, `INFRA_CRITICA_IPS/REDES` en `casador_blocking.py`) y `tools/simular_politica_hunter.py` para validar una política contra tráfico real antes de aplicarla. `only_external` se respeta también en la cadena Wazuh — pero **`_es_infra_critica`/`NUNCA_AUTOBLOQUEAR` NO se checkean en la cadena Wazuh** (solo en `blocked_by == "auto"`), únicamente `hunter.auto_block_exceptions` protege ese camino. Verificado 17 sep 2026 en Ópera (Wazuh activo de verdad, `hunter.integration_key` configurada): se agregó DNS público (Google/Cloudflare/OpenDNS/Quad9 — mismo set que `INFRA_CRITICA_IPS`) a `hunter.auto_block_exceptions` en los 4 sitios como cinturón adicional para ese camino. Al hacerlo se encontró que `shomer245`/`shomer243` tenían `system_state` con un esquema viejo (sin columna `updated_at` — dos `CREATE TABLE IF NOT EXISTS` distintos en el código, `monitor.py` vs `shomer_guardian_events.py`, definían el esquema según cuál corriera primero) y `set_config()` fallaba en silencio ahí; se unificó el esquema y `get_config`/`set_config` en `shomer_common.py` ahora se autoreparan solos si falta la columna.
- **Tracker** (`app/api/tracker*.py`, renombrado desde `inventory_*` el 13 sep — las rutas HTTP `/inventory/*` no cambiaron): inventario en `inventory.db` (assets + snapshots + credenciales). Solo credenciales Tracker.
- **Protector** (`app/api/backups.py`): Restic local → B2, convención `b2_path` por cliente obligatoria (Parte D.1). Retención decidida por sitio.
- **Inframonitor**: desde el 13 sep, separado en dos archivos — `app/api/shomer_inframonitor.py` (endpoints HTTP `/infra/*`, lo que consume el panel) y `app/api/shomer_inframonitor_poller.py` (motor: DB, sondeo ICMP/TCP/SNMP, el ciclo real). El proceso de producción es `app/scripts/inframonitor_poller.py` (`shomer-inframonitor-poller.service`), independiente de Guardian/Hunter — puede reiniciarse sin afectarlos. 51 equipos reales en Ópera (30 AP vía Guardian + 21 vía Inframonitor: switches, cámaras, impresoras, POS, router, servidores, controlador).
- **NOC** (`app/api/shomer_noc.py`): pantalla pública `/noc?token=` (token por sitio en `noc.display_token`), IPs ocultas en la vista de hotel. Vista técnica y vista cliente (`/noc/cliente`) comparten los mismos datos.
- **Cerebro** (`core/brain.py`, agente): correlaciona eventos de varios sistemas para encontrar causas compartidas. Filtro `aporta_algo()` decide si interrumpe por Telegram — solo si correlaciona 2+ equipos con una causa común; una conclusión de un solo equipo o "sin causa común" se guarda pero no se envía (medido: eso era el 86% de sus conclusiones). Usa contexto real del sitio (`SITE.md`, `EQUIPOS.md`, perfil de comportamiento por equipo desde `get_perfil_equipo()`) y una base de conocimiento técnico genérico (`core/conocimiento_general.py`, 263 conceptos + 173 reglas, cargados desde `core/data/*.json`).
- **Bot/IA** (`core/monitor.py`, `core/bot.py`): 2 LLM — **Groq** (fondo/monitores, plan FREE, default de `LLM_PROVIDER_INTERACTIVE`) + **OpenAI** gpt-4o-mini (chat interactivo, con topes de gasto). **41 monitores** en background (verificar con `tools/auditar_monitores.py`, que cruza lo que corre de verdad contra lo que se muestra en `/monitores`). **Cada sitio tiene su propio bot y su propio grupo de Telegram, nunca compartido** (desde Sesión 80). Informe periódico al coordinador por correo (`core/informe_coordinador.py`) — construido, pendiente solo de credenciales SMTP.

## Lecciones vivas (bugs cerrados que importan)
- **sudo/root**: tras cualquier `sudo restic` o correr módulos como root → revisar dueño del **repo** Y de `~/.cache/restic` Y de `__pycache__`; fix `chown -R usb_admin`. (Causó panel Protector "sin snapshots" y `.pyc` de Hunter en root.)
- **Protector "sin snapshots" en panel**: casi siempre caché restic root o locks huérfanos → `restic unlock` + chown caché. **Los datos NO se pierden.**
- **Groq "caído"**: es límite del plan **FREE** (RPM/TPM/RPD), no una caída. `watch_groq` chequea con `models.list()` (sin gastar tokens); un 429 de fondo **no** pausa el bot; alerta máx **1/día**.
- **Guardian mantenimiento**: revisar que solo los APs que deben estén en `node_maintenance` (TTL −1 = permanente y silencioso).
- **BD symlink**: `/opt/network_monitor/*.db` deben apuntar a `/storage/db/*.db` reales (no a archivos vacíos).
- **Medir contra el proceso real, no contra una consola nueva**: `JWT_SECRET`, `pulse_config()` y comandos SNMP dieron resultados falsos varias veces por leerse desde un proceso Python recién abierto en vez del servicio real, que hereda variables de entorno (`EnvironmentFile` de systemd) que una consola nueva no tiene. Verificar siempre contra el proceso vivo (`systemctl show <servicio> -p Environment`, o llamar la función real vía HTTP autenticado) antes de afirmar que algo está mal configurado.
- **rsync nunca borra**: un archivo renombrado o eliminado en el maestro sigue físicamente en los labs hasta que se borra a mano tras el sync — pasó dos veces (renombrado de Tracker, archivos huérfanos de la auditoría de arquitectura). Verificar con `fleet_estado.py` después de cualquier renombrado/borrado, no solo confiar en "sync exitoso".

## 🗺️ Mapa de decisión de alertas (leer antes de tocar sensibilidad/Telegram)

**Por qué existe esto:** en ~2 meses se agregaron 5-6 mecanismos independientes que deciden si
un evento se avisa o se calla, cada uno resolviendo el síntoma que se veía en ese momento
(Sesión 60-72). No hay un solo lugar que decida "¿aviso o no aviso?" — hay que conocer el orden.
**Antes de agregar un mecanismo nuevo, revisar si alguno de estos ya cubre el caso.**

**Orden real, por ciclo de poll (Guardian ~10s, Inframonitor ~30s), para UN equipo:**

| # | Filtro | Dónde | Qué hace | Si activa |
|---|--------|-------|----------|-----------|
| 1 | Ping/pérdida | `_ping` / `_ping_metrics` | 3 paquetes; offline solo si se pierden TODOS | equipo pasa a online/degraded/offline |
| 2 | **Blip gateway** | `shomer_network_blip.evaluate_host_network_blip_async` | Si gateway también unhealthy (offline, o degraded con pérdida/RTT altos) Y caída masiva (8+/20+/50%) → recheck 300ms → confirma | **silencia TODAS** las transiciones offline nuevas del ciclo |
| 3 | **Blip masivo puro** (Sesión 72) | mismo archivo, mismo función | Caída masiva (8+/20+/50%) aunque el gateway se vea sano — se reevalúa cada ciclo, tope 10 min (`INFRA_BLIP_MASS_MAX_SEC`) | igual que #2, con tope de seguridad |
| 4 | Umbral por nodo | Guardian: `threshold`/`cooldown` · Infra: `INFRA_OFFLINE_CONFIRM_CHECKS` | N fallos seguidos antes de declarar offline "de verdad" | evita 1 blip aislado por equipo individual |
| 5 | **Escalamiento crónico** | `incident_escalation.py` (agente) | 1ª falla avisa normal; repetidas en ventana 1h → solo cuenta; al cerrar ventana → 1 digest si hubo repetición | agrupa N caídas del MISMO equipo en 1-2 mensajes en vez de N |
| 6 | **Recuperación repetida** (Sesión 71) | `incident_escalation.is_flapping` + `watch_guardian_nodes`/`watch_infra` | Si el incidente activo ya tiene 2+ eventos → no repetir "recuperado" en cada blip | 1ª recuperación avisa, repetidas no |
| 7 | **Patrón crónico** (Sesión 69, suprime desde Sesión 80) | `pattern_analysis` / `BOT_CHRONIC_ALERT_MIN_OCURRENCIAS` | Si el equipo ya tiene 5+ ocurrencias conocidas | **suprime del todo** en tiempo real (antes solo acortaba el mensaje) — queda en `eventos_filtrados` |
| 8 | **Reinicio automático de Guardian** (Sesión 80) | `watch_guardian_nodes`, verificación 3 min | Si el auto-reboot funcionó, no interrumpe; si sigue caído, sí (crítico) | éxito = silencioso (registrado), fallo = avisa igual que antes |
| 9 | **Criticidad de negocio** (Sesión 80, solo Inframonitor) | `watch_infra` / `INFRA_CRITICAL_DEVICE_TYPES` | `pos`/`router`/`server`/`controller`/`switch` avisan ya; `printer` no-POS y `camera` esperan al resumen | no aplica a Guardian/APs (sin subtipo) |
| 10 | Digest VPN | `monitor.py`, aparte, solo conexiones/desconexiones VPN | Agrupa cada `VPN_DIGEST_INTERVAL_SEC` (30min) en 1 mensaje | no es por equipo, es por tipo de evento |
| 11 | **Cerebro** (12 sep 2026) | `brain.aporta_algo()`, corre después de todo lo anterior | Solo interrumpe si correlaciona 2+ equipos con causa común; "sin causa común" o un solo equipo se guarda pero no se envía | filtra el 86% de lo que el cerebro concluye — un equipo solo ya lo avisó su propio monitor |
| 12 | **Oleada de degradación Pulse** (12 sep 2026) | `pulse_correlate.format_ewma_wave_degrading`, en el agente | 3+ equipos "degradando" en el mismo ciclo (umbral del sitio) se agrupan en 1 mensaje; menos de eso, aviso individual | 10 equipos → 1 mensaje en vez de 10; si el gateway está en la lista, lo señala como causa probable |
| 13 | **Latido y reinicio de Shomer** (11-12 sep 2026) | `shomer_guardian_server_health.py` | El latido "todo OK" ya no se envía (se registra); el aviso de reinicio solo sale si se repite `guardian.reinicios_para_avisar` veces en 1h | de 3 latidos + 1 aviso de reinicio por día a 0, sin perder la prueba de vida (sale en el resumen diario) |

**Pasos 5-6, desde `shomer-agent` v1.1.3 (13 ago):** ya cubren tanto `watch_guardian_nodes` (wifi)
como `watch_infra` (switches/impresoras/cámaras/datáfonos) — antes solo Guardian los tenía, y un
switch/impresora flapeando podía mandar un mensaje completo por cada caída sin agrupar (el mismo
problema que tuvo OFC-COCINA, Sesión 71, pero del lado de Inframonitor sin arreglar hasta ahora).

**Aparte, en paralelo, no en esta cadena:** **Pulse EWMA** (`shomer_infra_pulse.py`) manda su propia
alerta "degradando" por tendencia de latencia, con su propio cooldown (`INFRA_PULSE_ALERT_COOLDOWN_SEC`)
— no pasa por los filtros de arriba porque no es un evento offline/online, es predictivo.

**Cómo medir si esto realmente funciona (no adivinar):** `python3 tools/reporte_alertas_semanal.py`
— cuenta mensajes reales enviados + cuántos se suprimieron por cada mecanismo, con datos de
`memoria_alertas`, `infra_blip_events` y `escalation_incidents`. Correrlo antes/después de tocar
cualquier umbral para comparar con números, no con la sensación de "parece que bajó".

**Deuda reconocida (no resuelta, no atacar sin plan):** 45+ variables de entorno independientes
(`INFRA_BLIP_*`, `ESCALATION_*`, `INFRA_PULSE_*`, `SHOMER_*`, `BOT_*`) repartidas en 7+ archivos.
Funciona, pero no es estandarizable para otro cliente sin que alguien entienda las 8 capas de
arriba primero. Consolidar en un solo módulo de decisión es un proyecto aparte — no un fix rápido.

# Parte A — Estado del sistema (realidad cotidiana)

## A.1 Servicios que debe tener el appliance

Si alguno falta, el panel puede abrir igual pero fallan módulos.

| Servicio systemd | Puerto / rol |
|------------------|----------------|
| `shomer-guardian.service` | **8000** — Core: panel proxy, Guardian, Hunter |
| `shomer-tools.service` | **8001** — Tracker, Protector (solo localhost tras hardening típico) |
| `nginx` | **80** redirect → **8443** HTTPS hacia backend |
| `shomer-health-watchdog.timer` | Reintenta 8000/8001 si mueren |
| `shomer-inframonitor-poller.service` | Poller ICMP/SNMP independiente de uvicorn (`app/scripts/inframonitor_poller.py`, motor real en `app/api/shomer_inframonitor_poller.py`). Arranca con el sistema, sobrevive reinicios de Guardian/Tools. |
| Opcionales cliente | `suricata`, stack Wazuh, `redis-server`, `lldpd`, etc. según alcance |

**Comprobación rápida:**
`systemctl is-active shomer-guardian shomer-tools nginx shomer-health-watchdog.timer shomer-inframonitor-poller`

## A.0 Entorno de laboratorio

**Todo el hardware físico de los labs está conectado y disponible en todo momento.** Cualquier prueba física, de aplicación o en la nube se puede ejecutar sin preguntar al desarrollador. Los labs (`shomer205`/`245`/`243`) hoy son laboratorio de desarrollo; están destinados a convertirse en instalaciones de cliente — antes de eso, cada uno debe pasar por `/setup` con la red real del sitio (ver Parte I).

**Resuelto (13 sep 2026, confirmado por Juan Pablo y verificado contra el sistema real):**
carga y despliegue en nube externa ya no son pendientes de mayo — B2 (Backblaze) corre en
producción real todos los días desde entonces, con Guardian/Hunter/Inframonitor/scans
corriendo en simultáneo (verificado: sync B2 del 13 sep a las 05:30 hora local, justo
después del backup local de las 05:00). Eso es carga real sostenida, no una prueba sintética
de laboratorio — más exigente, no menos.

---

# Parte B — Normas de diseño (obligatorio antes de código)

## B.1 Cero hardcoding en topología cliente

Red distinta cada hotel/empresa. **Prohibido** fijar en código IPs, subnets, nombre de NIC de cliente como constante mágica, credenciales. **Correcto:** `nodos_gl.json`, `devices`, helpers `app.backend.db` (`STORAGE_DB`, …), configuración BD `system_state`, consultas SQL dinámicas.

**Auto-control:** ¿funcionaría igual en red 10.x, 172.16.x sin recompilar? Si no → mal.

## B.2 Normas equipo de desarrollo y QA

| Regla corta |
|-------------|
| Pensar antes de tocar archivo equivocado |
| Solo editar líneas necesarias al cambio pedido |
| Leer función/caller antes de parche grande |
| Probar comando o vista real **con hardware donde aplique**; **no fingir estado** ni inflar Redis con contadores falsos |
| Si no se puede ejecutar una prueba auténtica, **dejarlo explícito en documento QA** como pendiente |

## B.4 Tailscale es el puente, no un hallazgo de seguridad (permanente, 12 sep 2026)

**Nunca proponer cerrar, restringir o "endurecer" el acceso Tailscale a los
labs ni a Ópera como si fuera una vulnerabilidad.** Juan Pablo opera desde
Estados Unidos; los servidores están en Colombia. Tailscale es el **único
puente** que permite llegar a esos equipos desde aquí — no hay otra vía
armada. Cerrarlo equivale a perder el acceso remoto por completo, sin forma
de reabrirlo desde afuera.

Cuando un hallazgo mencione que un equipo "es alcanzable por Tailscale"
(p. ej. una cuenta con contraseña de fábrica en un lab), el riesgo a resolver
es la cuenta o el permiso — nunca la vía de acceso. Explicarlo así, y no como
un problema de exposición de red.

---

## B.3 Deploy y producción — REGLA CRÍTICA (permanente, jun 2026)

**Autorización:** `deploy.sh`, rsync remoto o reinicio de servicios en equipos de **cliente / producción** (p. ej. Hotel Ópera) **solo con autorización explícita de Juan Pablo** y ventana de mantenimiento acordada.

**Deploy = solo código de la aplicación** (`app/`, código agente sin `.env`/`data/`). **Nunca** en el mismo flujo:
- Bases de datos del cliente (`network_monitor.db`, `inventory.db`)
- `SITE.md`, subnets, VLANs, credenciales, `hunter.firewall_*`, Telegram del sitio
- `/etc/shomer/shomer-runtime.env` remoto, `suricata.yaml`, netplan, UFW del hotel
- Flags de lab (`SHOMER_LAB_NO_SPAN`) en producción

Mezclar config de un sitio con otro **puede ser fatal**. Detalle: `docs/REGLAS_DEPLOY.md`.

---

# Parte C — Arquitectura de red esperada

- **Gestión**: NIC al switch principal cliente (HTTPS panel, ICMP/SSH desde Shomer).
- **Espejo / Hunter**: segunda NIC debe recibir mirror SPAN desde switching capa cliente hacia Suricata.
- **AP en otra VLAN** es normal → hace falta **routing L3** y reglas firewall; no hay regla mágica de “tarjeta tercera siempre necesaria`.

---

# Parte D — Módulos, puertos, datos persistentes clave

| Módulo | Puerto interno | Código entrada | Funciones |
|--------|----------------|----------------|-----------|
| Core | **8000** | `app.api.main:app` | Auth, proxies `shomer_proxies` hacia tracker/backups en 8001, Guardian, Hunter, Topología (LLDP/SNMP) |
| Tools | **8001** | `app.api.main_tools:app` | Tracker inventario (`inventory.db`, archivos `app/api/tracker*.py` — renombrados desde `inventory_*` el 13 sep 2026, rutas HTTP `/inventory/*` sin cambio), Protector Restic+B2 |
| Inframonitor | *(sin puerto propio — proceso standalone)* | `app.scripts.inframonitor_poller` (motor real: `app/api/shomer_inframonitor_poller.py`; endpoints HTTP `/infra/*`: `app/api/shomer_inframonitor.py` — separados el 13 sep 2026) | Monitorea `infra_devices` (switches, servidores, cámaras, POS, impresoras, router — **todo lo que NO es AP**; los APs los cubre Guardian vía `infra_nodes`). Capa rápida ping/tcp/mac cada `INFRA_FAST_POLL_INTERVAL_SEC`, SNMP en paralelo cada `INFRA_SNMP_POLL_INTERVAL_SEC`. Servicio systemd propio (`shomer-inframonitor-poller`), independiente de Core/Tools — puede reiniciarse sin afectar Guardian/Hunter/Tracker/Protector. En Ópera (verificado 13 sep 2026): 51 dispositivos reales, 49 online (ap:30 vía Guardian; switch:8, pos:4, camera:3, printer:2, server:2, router:1, controller:1 vía Inframonitor). |

`system_state` en `network_monitor.db` guarda prefijos `base.* guardian.* hunter.* tracker.* protector.* topology.* modules.enabled`.

**Ojo con la confusión de nombres**: "Guardian" NO es el sistema completo — es específicamente el módulo que monitorea nodos/APs (`infra_nodes`, heartbeat rápido). El sistema completo se llama **Shomer** (o "Shomer Sentinel"). Guardian, Hunter y el módulo de Topología comparten el mismo proceso/puerto 8000 por conveniencia de despliegue, pero son lógicamente distintos entre sí y distintos de Inframonitor (proceso separado) y de Tracker/Protector (puerto 8001).

Rutas lógicas: importar rutas físicas sólo desde `app.backend.db` (evita rutas tipo `/opt/network_monitor/hardcoded` dispersas).

## D.0 NOC — pantalla TV (Guardian/Infra)

- **URL:** `/noc?token=` + valor `system_state.noc.display_token` (por sitio).
- **API:** `/noc/data`, ACK opcional `/noc/problems/ack` — `app/api/shomer_noc.py` · plantilla `app/templates/noc.html`.
- **Rol:** display visual. **No** es canal de operación: Telegram (Guardian/Infra/Hunter) ya avisa con cooldowns existentes; no inventar alertas ni ACK Telegram desde el NOC.
- **28 jul 2026 (Ópera):** KPI Hunter “amenazas externas contenidas”; bloque **Shomer IA** (logo eyes + feed `noc:ia_log` espejo Telegram); soporte USB tipografía TV; sin logo en header; sin pill IA. Ver `docs/NOC.md`.
- Preview legado: `/noc/cliente`. Sync labs: rsync core **sin** `--delete`, **sin** `SITE.md` / `.env` / `*.db` (ver `docs/PENDIENTES_LAB.md`).

**Restic Protector:** `RESTIC_REPOSITORY` + `RESTIC_PASSWORD` o `RESTIC_PASSWORD_FILE`.  
`RESTIC_PASSWORD_FILE` en lab: `/home/usb_admin/.restic-local-pass`. El repo B2 usa la misma contraseña que el local — dejar `b2_password` vacío en el panel para que el código haga fallback automático.

## D.1 Protector — Convención multi-cliente B2 (OBLIGATORIA en campo)

Cada instalación cliente **debe** configurar `b2_path` en el panel Protector → sección B2.  
Sin esto, todos los hoteles/clientes comparten un mismo repositorio Restic indistinguible.

| Campo panel | Qué poner | Ejemplo |
|-------------|-----------|---------|
| **Bucket** | Bucket único de la empresa USB | `shomer-backups` |
| **b2_path** | Slug del cliente, sin espacios ni tildes | `hotel-plaza`, `empresa-abc`, `hotel-real` |
| **Nombre equipo** | Nombre humano legible para el técnico | `Hotel Plaza — Contabilidad` |

**Resultado en B2:**
```
shomer-backups/
  hotel-plaza/    ← repo Restic independiente, solo equipos de ese hotel
  hotel-real/     ← repo Restic independiente, otro hotel
  empresa-abc/    ← repo Restic independiente, otra empresa
```

**Tags por snapshot** — cada backup genera 3 tags legibles sin necesitar la BD:
- `device_7` — ID interno (para cruzar con BD si el Shomer está vivo)
- `ssh` / `smb` — protocolo de extracción
- `Hotel_Plaza_Contabilidad` — nombre del equipo (slug, max 40 chars)

**Comandos de recuperación de emergencia** (sin panel, solo credenciales B2):
```bash
# Listar snapshots de un hotel específico
RESTIC_PASSWORD_FILE=/home/usb_admin/.restic-local-pass \
B2_ACCOUNT_ID=<id> B2_ACCOUNT_KEY=<key> \
restic -r b2:shomer-backups:hotel-plaza snapshots

# Filtrar por equipo
restic -r b2:shomer-backups:hotel-plaza snapshots --tag Hotel_Plaza_Contabilidad

# Restaurar a carpeta de recuperación
restic -r b2:shomer-backups:hotel-plaza restore <snapshot_id> --target /recovery/

# Navegar como sistema de archivos (requiere FUSE)
restic -r b2:shomer-backups:hotel-plaza mount /mnt/recuperacion
```

**Flujo automático por equipo (Sesión 20, mayo 2026):**
```
HH:MM configurado por device →
  1. Backup SSH/SMB → Restic local (/srv/shomer_backups/staging)
  2. Si "☁ Subir a B2" activado → restic copy <snapshot_id> → B2 (solo ese delta)
  3. Telegram: copia local OK + sync B2 OK/FALLÓ
HH:MM global (hora local del sitio — ej. 04:00 MT — leída de `base.timezone`) →
  1. restic copy todo → B2 (catch-all para lo que no subió por device)
  2. restic forget --keep-daily=N --prune (prune local SOLO después de B2 confirmado)
  3. Telegram: sync global OK
```

**Campos BD relevantes** (`backup_devices` en `network_monitor.db`):
`schedule_enabled`, `schedule_time` (hora local del sitio según `base.timezone`), `schedule_b2_enabled`, `last_snapshot_id`, `last_files_count`, `last_size_mb`, `last_duration_sec`.

**Agente — regla emergencia disco**: `restic_prune` en `repair.py` (nivel `warn`, requiere autorización admin). El agente alerta disco 80/85/92% pero no pruena automáticamente — el prune automático vive en el scheduler global de Tools (8001).

---

## D.2 Usuario de servicio Shomer — cuenta única por instalación

Se configura en el **Wizard Setup → bloque Identificación del sitio** y se guarda en `system_state` como `base.service_user` y `base.service_password`. El panel Protector y Tracker lo pre-rellenan automáticamente al agregar equipos — se puede hacer override por equipo si alguno tiene credenciales distintas.

### Creación del usuario en cada equipo

| OS | Comando / acción |
|----|-----------------|
| **Linux** | `sudo adduser shomer` → establecer contraseña → agregar a grupos necesarios si aplica |
| **macOS** | Preferencias del sistema → Usuarios y grupos → Nuevo usuario → tipo Estándar, nombre `shomer` |
| **Windows (local)** | `net user shomer <password> /add` en CMD como Administrador |
| **Active Directory** | Crear usuario `shomer` en el AD con la misma contraseña — aplica a todos los equipos del dominio automáticamente |

### Rutas recomendadas por OS

| OS | Tipo | Ruta sugerida | Notas |
|----|------|---------------|-------|
| **Linux** | SSH | `/home/shomer/backups` | Crear con `mkdir ~/backups` |
| **Linux** | SSH | `/home/shomer/Documentos` | Si ya existe y tiene datos |
| **macOS** | SSH | `/Users/shomer/backups` | Crear con `mkdir ~/backups` |
| **macOS** | SSH | `/Users/shomer/Documents` | Estándar macOS |
| **Windows** | SMB | `backups` | Nombre del share (no ruta completa) — crear carpeta C:\backups → clic derecho → Compartir → nombre: `backups` |
| **Windows** | SMB | `Documentos` | Si ya hay share configurado |

**Puerto SSH:** 22 (Linux/Mac). **Puerto SMB:** 445 (Windows) — verificar que el firewall de Windows permita SMB desde la IP del Shomer.

### Configuración global (Wizard o post-setup)
- `base.service_user` → usuario (ej: `shomer`)
- `base.service_password` → contraseña (texto plano en system_state, protegido por permisos OS del DB)
- Editable post-setup sin reconfigurar red: `POST /setup/site-info` con `{"service_user":"...", "service_pass":"..."}`

### Zona horaria — opciones disponibles
Se elige en el wizard. El selector incluye zonas de América Latina, Norteamérica y **UTC** (disponible para servidores en datacenter o técnicos que lo prefieran). **No recomendado UTC en clientes LATAM** — si un técnico en Colombia lo selecciona, el scheduler dispara a hora incorrecta sin advertencia. Guardada en `base.timezone`, leída por el scheduler de Protector y (futuro) Guardian Telegram timestamps.

---

# Parte E — Hunter (Cazador) — uso operativo

- Wazuh consume alertas desde archivo **filtro tipo** `eve-alerts.json`, **no** el `eve.json` completo brutal.
- Cadena oficial autobloqueo “fuerte”: **manager Wazuh** → script **`wazuh_shomer_block.py`** → `POST /remedies/block` con cabecera `X-Shomer-Integration-Key`.
- Firewall remoto vía SSH (`hunter.firewall_*`): **OpenWrt/Linux** → `iptables` en `FORWARD` (automático). **MikroTik RouterOS nativo** → address-list `shomer-blocked` + **regla DROP manual obligatoria** en `chain=forward` (`hunter.firewall_type=routeros`). Ver §AF.1 y §AO.1; doc `HUNTER_MIKROTIK_ROUTEROS.md`.

**Auth HTTP `POST /remedies/block` (17 jul 2026):**  
- `blocked_by=wazuh` → solo `X-Shomer-Integration-Key` (integration Wazuh en localhost).  
- `manual` / `auto` **vía HTTP** → JWT (Bearer o cookie). El poller autoblock llama `execute_hunter_block` en proceso (no el endpoint abierto).  
- `DELETE` / `PATCH /remedies/rules/{sid}` → JWT.  
Config de subnets/excepciones por sitio → **`SITE.md` del servidor** (nunca hardcode en CLAUDE).

**Firma ICMP laboratorio SID 9009001** suele estar bajo **`/etc/suricata/rules/`** en un fichero tipo `shomer-local.rules`; recarga lógica: `POST /remedies/rules/reload`.

**Checklist campo Hunter (resumen contenido habitual del paquete de soporte):**
- NIC gestión vs NIC espejo acordes al hardware (ej. `enp2s0` / `enp4s0` sólo ejemplo).
- **`hunter.auto_block_*`** y **`hunter.subnets`** revalidar tras cambiar la LAN del cliente (quitar VLANs fantasma evita falsos “internos”).
- Integración Telegram: probar **`POST`** a `/remedies/block` y luego `/remedies/unblock` en **127.0.0.1:8000** con **`X-Shomer-Integration-Key`**, usando IP de prueba reservada (p. ej. `198.51.100.1`), **nunca** direcciones operativas del hotel.

## D.3 Pendiente — Recuperación remota de AP sin ruta de red (PoE vía SNMP)

**Origen (7 sep 2026):** al probar el reinicio automático real de Guardian se confirmó la
causa raíz de por qué la mayoría de los intentos fallan con `ssh: connect ... Connection
timed out` / `No route to host`: un AP normal (`device_type='access_point'`) solo puede
llegar al estado `offline` vía `classify_health()` cuando tiene **0% de respuesta en la
LAN** — la clasificación `no-internet` (WAN caída pero LAN viva) está reservada solo a
`device_type in ('router','gateway')`. Es decir: el reinicio automático de un AP **siempre**
se dispara justo cuando ya no hay ninguna ruta de red hacia él — y si no hay ruta, ningún
protocolo remoto (SSH, SNMP, lo que sea) puede llegarle tampoco. No es un bug de
credenciales ni de configuración por equipo — es una limitación física: sin ruta de red no
hay forma de mandarle ningún comando. Para un AP genuinamente caído (energía, PoE, firmware
colgado con la NIC muerta) hoy no existe ningún mecanismo remoto de recuperación —
solo intervención física.

**Propuesta pendiente (requiere estar en sitio / equipos ya viajaron a Bogotá, no se puede
validar ahora):** usar el descubrimiento de topología real por LLDP ya construido
(`shomer_topology.py`, tabla `network_links` — sabe a qué switch y qué puerto físico está
conectado cada AP) para, cuando SSH falle por falta total de ruta, apagar y volver a
prender por SNMP el puerto PoE específico de ese AP en su switch padre — un power-cycle
remoto real, capaz de revivir un equipo que SSH nunca podrá alcanzar.

**Qué falta confirmar antes de construirlo (todo requiere acceso físico a los switches):**
1. Que los switches reales tengan la comunidad SNMP configurada con **permiso de
   escritura** (`snmp_community_write`, ya existe el campo en `infra_devices` pero no se
   verificó que esté poblado con un valor que realmente autorice escritura en cada switch).
2. El OID correcto de control PoE por puerto para los modelos reales en sitio — el estándar
   es POWER-ETHERNET-MIB (`pethPsePortAdminEnable`, `1.3.6.1.2.1.105.1.1.1.3.1.<indice>`),
   pero varios fabricantes (TP-Link, Mikrotik, Ubiquiti) usan OIDs propietarios en vez del
   estándar — hay que confirmarlo contra el switch real, no asumir.
3. Probar el toggle en un puerto de prueba (con un equipo no crítico conectado) antes de
   usarlo contra un AP de producción — un OID equivocado podría apagar el puerto equivocado.

**Prioridad:** 🟡 Media — mejora real de disponibilidad, pero solo aplica al subconjunto de
caídas que son "AP realmente muerto" (no cubre WAN, DNS, ni degradación). De las 3 mejoras
discutidas el 7 sep 2026 para este mismo hallazgo, esta es la única que queda pendiente de
validación en campo — las otras dos (A: reinicio preventivo en `degraded` sostenido, B:
aviso diferenciado al técnico cuando SSH falla por falta total de ruta) no dependen de
acceso físico y se evalúan aparte.


## E.3 Configuraciones BD `hunter.*` — referencia completa

| Clave | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `hunter.firewall_ip` | str | `””` | IP del firewall OpenWrt (SSH) |
| `hunter.firewall_user` | str | `””` | Usuario SSH firewall |
| `hunter.firewall_pass` | str | `””` | Contraseña SSH firewall |
| `hunter.firewall_port` | int | `22` | Puerto SSH firewall (**nuevo Sesión 23**) |
| `hunter.auto_block_enabled` | bool | `false` | Habilita autobloqueo desde panel EVE |
| `hunter.auto_block_min_severity` | int | `2` | Severidad mínima (1=Critical, 2=High, 3=Medium) |
| `hunter.auto_block_only_external` | bool | `true` | No autobloquea IPs internas (exceto Critical) |
| `hunter.auto_block_exceptions` | list[str] | `[]` | IPs/CIDR excluidas de bloqueo auto y Wazuh |
| `hunter.high_recurrence_min` | int | `3` | N eventos ALTA en ventana para autobloquear |
| `hunter.high_recurrence_window_sec` | int | `600` | Ventana de tiempo recurrencia (seg) |
| `hunter.high_recurrence_warn_at` | int | `2` | Aviso Telegram al N-ésimo evento ALTA |
| `hunter.integration_key` | str | `””` | Clave compartida Wazuh↔Shomer |
| `hunter.subnets` | list[str] | `[]` | Subredes internas del cliente (para is_external_ip) |
| `hunter.interfaces` | list[str] | `[]` | NICs gestión + espejo |
| `hunter.wazuh_dashboard_url` | str | `””` | URL dashboard Wazuh (informativo, botón panel) |

## E.4 Pendientes Hunter (campo, se repiten en cada sitio nuevo)

| # | Qué | Prioridad |
|---|-----|-----------|
| P1 | **Validar espejo SPAN real en sitio nuevo** — `tcpdump -i enp4s0 -c 20` antes de confiar alertas | Campo / obligatorio |
| P2 | **Active-response Wazuh real** — `ossec.conf` + `local_rules.xml` nunca ejecutado en cliente con manager real | Campo |
| P3 | **SID 9009001 en tráfico real espejo hotel** — lab OK, pero NIC espejo hotel diferente | Campo |
| P4 | **`hunter.auto_block_*` por sitio** — revalidar subnets y excepciones en cada nueva LAN | Campo / obligatorio |

Decisiones ya cerradas (retry automático de circuit breaker descartado por UX, HMAC en la clave Wazuh descartado por ser tráfico loopback) y arreglos de la Sesión 24 (export CSV, timeout configurable, columna `firewall_blocked`) → `CLAUDE_historico.md`.

## E.5 Flashear MikroTik hEX S (RB760iGS) a OpenWrt — procedimiento vigente

**No es historia: es el procedimiento real para los firewalls que se envían con cada servidor nuevo a hoteles pequeños.** El `.206` (lab) corre OpenWrt 23.05.5 como modelo de referencia. **Ópera es la excepción**: usa un MikroTik que el hotel ya tenía, corriendo RouterOS nativo (`hunter.firewall_type=routeros`) en vez de un equipo flasheado — por eso Ópera no pasó por este procedimiento, pero los próximos clientes con firewall enviado desde aquí sí.

### Archivos a descargar (antes de empezar)

**Fuente:** `downloads.openwrt.org` (buscador oficial: `firmware-selector.openwrt.org`, modelo "MikroTik RouterBOARD 760iGS (hEX S)"). El rc3 no aparece en el buscador (es release candidate, no la versión estable) — bajarlo directo de la carpeta `releases/23.05.0-rc3/targets/ramips/mt7621/` del mismo dominio.

| Archivo | Versión | Uso |
|---|---|---|
| `openwrt-23.05.0-rc3-ramips-mt7621-mikrotik_routerboard-760igs-initramfs-kernel.bin` | **rc3 obligatorio** | Boot en RAM vía TFTP — las versiones finales no netbootean en este modelo |
| `openwrt-23.05.5-ramips-mt7621-mikrotik_routerboard-760igs-squashfs-sysupgrade.bin` | 23.05.5 estable | Flash permanente tras el boot en RAM |

### Procedimiento

**Paso 1 — Verificar RouterOS v6** (Winbox → `/system routerboard print`). Si tiene v7 bajar a 6.49.x primero.

**Paso 2 — Configurar netboot en el hEX** (web `192.168.88.1` o Winbox):
- System → Routerboard → Settings → Boot device: `try ethernet once then NAND`
- Boot protocol: `DHCP` · Force Backup Booter: ✅ · Shutdown (no reboot)

**Paso 3 — Servidor TFTP en .205** (cable directo .205 → Ether1 del hEX). **Verificado 14 sep 2026: `enp2s0` sigue siendo la interfaz correcta** (IP real `192.168.1.205/24`, no es la salida a internet de `.205` — esa va por `wlp3s0` — así que usarla no corta el equipo de la red general, solo el segmento LAN mientras dura el flasheo). `dnsmasq` no está instalado en `.205` hoy — el primer comando de abajo lo instala.
```bash
sudo apt-get install -y dnsmasq
# Archivo initramfs en directorio actual
sudo dnsmasq --no-daemon \
  --listen-address=192.168.1.10 --bind-interfaces -p0 \
  --dhcp-authoritative --dhcp-range=192.168.1.100,192.168.1.200 \
  --bootp-dynamic \
  --dhcp-boot=openwrt-23.05.0-rc3-ramips-mt7621-mikrotik_routerboard-760igs-initramfs-kernel.bin \
  --log-dhcp --enable-tftp --tftp-root=$(pwd)
# En otra terminal:
sudo ip addr replace 192.168.1.10/24 dev enp2s0
```

**Paso 4 — Forzar netboot:** desenchufa hEX → mantén Reset → enchúfalo → suelta al ver DHCP en consola (~15s).

**Paso 5 — Flash permanente** (cuando `ping 192.168.1.1` responda):
```bash
scp openwrt-23.05.5-*-sysupgrade.bin root@192.168.1.1:/tmp/
ssh root@192.168.1.1 "sysupgrade -n /tmp/openwrt-23.05.5-*-sysupgrade.bin"
```

**Paso 6 — Post-flash:** configurar IP fija del cliente, SSH key, contraseña, y registrar en Hunter (`hunter.firewall_ip/user/pass`).

### Referencia
- `.206` como modelo de config final (OpenWrt 23.05.5, MT7621, IP LAN fija, iptables, WireGuard opcional)
- Credenciales `.206` en BD Hunter: `hunter.firewall_*`

---

# Parte F — Guardian y failsafe nodos AP

Implementación núcleo:  
`shomer_guardian_nodes.py::_poller_tick` + chequeos **`shomer_guardian_health_checks.py`**.

Por tick (interval default 10 s configurables `SHOMER_POLL_INTERVAL_SEC` / BD):

| Orden breve check | Ejecutor | Switch OFF en BD si no aplica |
|-------------------|----------|-------------------------------|
| Latencia pérdidas ICMP Shomer→nodo LAN | Servidor Guardian | `guardian.check_latency_enabled` |
| Desde SSH en AP ping 8.8.8.8 | AP vía SSH | siempre importante para WAN outage |
| `nslookup probe` | AP vía SSH | `guardian.check_dns_enabled` |
| CURL HTTP esperado código (204 típ.) | AP vía SSH | `guardian.check_http_enabled` |

**Estados y consecuencias**

| Estado | Significado rápido | Reboot físico desde Shomer tras umbral solo si… |
|--------|---------------------|--------------------------------------------------|
| `offline` | LAN caída 100 % pérdidas | ✅ cumple thresholds + cooldown + no maintenance Redis |
| `no-internet` | LAN estable pero WAN AP caído | igual |
| `degraded` | DNS o HTTP probes mal o LAN “sucio” según pérdidas/RTT sostenidas | ❌ reboot **bloqueado** diseño • Telegram 🟡 con anti-spam `degraded_notified:*` TTL |
| `online` | OK o SSH no llega desde Shomer pero se asume nodo existe | reset contadores errores WAN-only |

Cooldown reboot y anti-ráfagas viven Redis (+ `failsafe_state` SQLite sobre todo para WAN/servidor).  
**Dos esperas de reboot de nodos (17 jul 2026):** tras reboot **OK** → `guardian.cooldown_sec` (típico 300 s, AP arrancando). Tras intento **fallido** → `guardian.fail_retry_sec` (default 150 s) en clave Redis `last_reboot_attempt:{ip}` — **no** reutilizar el cooldown de 5 min si SSH/SNMP falló.

Salud servidor propio WAN + métricas CPU/RAM: `shomer_guardian_server_health.py` exponiendo `/api/server-metrics`, `/api/wan-status`.

**End points útiles operación rápido:** `/nodes` incluye último reboot epoch si existe clave Redis `last_reboot:{ip}`.

### Extensión SNMP para dispositivos sin SSH útil (8 mayo 2026)

`shomer_guardian_health_checks.py` expone dos funciones nuevas:

- `_snmp_health_probes(ip, community)` — prueba uptime OID + ifOperStatus de radios wifi via SNMP walk. Detecta AP colgado (SNMP no responde) y radio caído (ifOperStatus=2).
- `classify_snmp_health(lan_ok, lan_loss, lan_rtt, snmp_result, cfg)` — clasifica estado para dispositivos SNMP-only: `offline` (ICMP falla), `no-internet` (SNMP no responde o radio caído), `online` (todo ok).

`shomer_guardian_nodes.py` — cambios (8 mayo 2026):

- `_get_devices_for_poll()` ahora selecciona también `name` y `snmp_community` de la tabla `devices`.
- `_poller_tick()` detecta `is_snmp_device = reboot_method == 'snmp'` y usa la rama SNMP en lugar de SSH probe.
- Mensajes Telegram de reboot mejorados: incluyen nombre del equipo, motivo exacto, método (SSH/SNMP) y confirmación post-reboot.

**Bug corregido:** `is_router` ahora excluye dispositivos con `reboot_method='snmp'` — antes el EAP225 con `device_type='router'` entraba al SSH probe de WAN, admin no tenía permisos de ping, acumulaba 42+ fallos y se reiniciaba en loop infinito.

**Interfaces SNMP detectadas en EAP225 (lab):**

| idx | Nombre | Tipo |
|-----|--------|------|
| 2 | eth0 | Puerto LAN físico |
| 4 | br0 | Bridge |
| 5 | wifi0 | Radio 2.4 GHz |
| 6 | wifi1 | Radio 5 GHz |
| 7 | ath0 / 8 ath10 | VAPs virtuales |

`_snmp_health_probes` busca interfaces por nombre (`wifi0/wlan0/ath0` → 2.4GHz, `wifi1/wlan1/ath1/ath10` → 5GHz) — funciona en EAP225, EAP610 y cualquier AP OpenWrt-like.

---

# Parte G — Tracker — modelo de datos y snapshot

Tracker **canónico** usa **`/storage/db/inventory.db`** — tablas `assets`, `network_credentials`, `inventory_snapshots`, etc.

Estructura paralela vieja dentro `network_monitor.db` debía quedar **sin servicio escritor zombie** tipo `network-inventory.service.disable…` cuando se migró abril 2026.

Exports API (puerto Tools o proxy HTTPS): Excel global por IP, etiquetas PDF, etc. Snapshot `POST /snapshot/close` archiva contenido tabla `inventory_snapshots` y vacía `assets` conforme especificación prod.

📌 **Peligro de restore:** copiar sobre el servidor un `inventory.db` **antiguo** después de un **`POST /snapshot/close`** puede **pisar el estado nuevo** del snapshot y dejar inconsistencias graves; el orden de backup/restore debe seguir el protocolo emitido por ingeniería con cada entrega physical.

Cliente Windows: usar cuentas de servicio WMI con permisos mínimos y acuerdos de privacidad con el cliente; el detalle de credenciales y checklist largo siguen las plantillas corporativas de instalación fuera de este párrafo.

**macOS (Darwin) — rama SSH del scanner:** cuando `uname -a` contiene Darwin, el extractor usa `system_profiler SPHardwareDataType` (modelo, CPU, RAM, serial), `sw_vers` (OS), `df -h /` (disco), `ls /Applications` (software). Mismos campos BD que Windows. Prerequisito: SSH activo en el Mac y credenciales en Tracker → Credenciales. Re-escanear: `cd /opt/network_monitor && ./venv/bin/python3 -m app.scripts.scanner` con el Mac en el rango de discovery. Verificar: `sqlite3 /storage/db/inventory.db "SELECT ip,hostname,cpu,ram,os_family FROM assets WHERE ip='IP_MAC';"`.

**Campos ficha Tracker (Sesión 51 — validación física + escaneo):**

| Campo BD | Origen | Descripción |
|----------|--------|-------------|
| `monitor_count` | Manual | Monitores **externos** adicionales (0–3) |
| `monitors_json` | Manual | `[{model, serial}, …]` monitores externos |
| `integrated_monitor` | Manual | `1` = portátil / All-in-One con pantalla integrada |
| `integrated_monitor_model` / `_serial` | Manual | Modelo y serial del panel integrado |
| `monitors_detected_json` | Escaneo WMI/SSH | Monitores detectados automáticamente |
| `peripherals_detected_json` | Escaneo WMI | USB / docks detectados |
| `peripherals_manual` | Manual | Docks, hubs, adaptadores |
| `local_printers_json` | Escaneo WMI | Impresoras locales del PC |
| `logged_user` / `logged_user_at` | Escaneo WMI | Usuario de sesión al escanear |

**Timeout WMI (Sesión 51):** `TIMEOUT_CRITICAL_SEC=90` en `scanner.py`; `EXTRACTOR_SSH_WMI_TIMEOUT=90` en `extractor.py`. Antes el extractor capaba en 30 s aunque el scanner pedía 45 s → falsos `ERROR: timeout (30s)` con datos parciales. Redes grandes (500+ PCs): deep scan por segmento/VLAN de noche; quick scan diario — ver §AK.6.

---

# Parte H — Seguridad típica despliegue

| Ítem tema | Implementación habitual |
|-----------|--------------------------|
| `JWT_SECRET` / `SHOMER_STRICT_AUTH=1` | `/etc/shomer/shomer-runtime.env` permiso 640 `root:usuario_ops` • rotar secreto fuerza nuevo login todas sesiones cookie |
| CORS aplicación | Env `SHOMER_CORS_ORIGINS` aplicación NO wildcard nginx antiguo |
| Tools sólo localhost | systemd drop-in sobrescribe `--host 127.0.0.1` |
| UFW entrada | Permitir sólo WAN gestión cliente hacia `{22,80,8443}` real del sitio LAN |
| Credenciales B2 Tracker Protector productivo | sólo tabla `protector.*` / archivos externos permisivos — **nunca texto plano en repo público Git** |

Detalle granular historial Sesión Hardener 2026-04-11 → ver Git commit ese dia.

---

# Parte I — Reset fábrica / wizard

Referencias variables entorno sólo modo empaquetado imagen inicial:

```
SHOMER_FACTORY_IP GW PREFIX
SHOMER_MANAGEMENT_INTERFACE  (default ejemplo `enp2s0`)
SHOMER_MIRROR_INTERFACE      (ejemplo habitual `enp4s0`)
```

Script herramienta: `tools/factory_reset_network.sh`  
Post reset IP fábrica → Wizard `/setup/` escaneo red escolar define dirección real cliente antes producción piloto Bogotá / hotel.

---

# Parte J — Protocolo desarrollador ante servicio Zombie puerto ocupado

**8000 / 8001** algunas veces quedó proceso huérfano uvicorn ocupando cuando hot reload falló systemd order.

```bash
sudo systemctl stop shomer-guardian.service  # igual tools
sudo lsof -ti:8000 | xargs sudo kill -9      # igual 8001 tools
sleep 2
sudo systemctl start shomer-guardian.service && sudo systemctl start shomer-tools.service
```

Después proxy cookies deben tener ambos levantados juntos porque login cookie es compartido firmado mismo `JWT_SECRET` + mismo boot nonce estable post fix abril 2026.

---

# Parte K — Mapa rápido módulos Python principales *(no exhaustivo pero navegable mismo día llegas repo)*

```
shomer*.py                  routers panel, config, guardian, proxies, setup
casador_blocking casador_intel casador_rules + casador_support_*    Hunter
tracker*.py                 Tracker (renombrado desde inventory_* el 13 sep 2026)
app/scripts/tracker/*       motor escaneos nmap wmi snmp
app/scripts/alerts*.py      telegram avisos
```

Tests humo habitual:  
`PYTHONPATH=/opt/network_monitor ./venv/bin/python -m unittest tests.test_smoke_api -v`

---

# Parte L — Backlog abierto (13 sep 2026)

Todo lo demás de este backlog se resolvió entre mayo y agosto (roles técnico/admin, restore B2 desde panel, toggle de schedule, etc. → `CLAUDE_historico.md`). Lo que sigue genuinamente sin construir:

| Ítem | Estado |
|------|--------|
| Flujos de mitigación en UI más allá del bloqueo de IP en Hunter (confirmación granular por tipo de acción) | PLAN, sin fecha |
| Panel Hunter: soporte de configuración para firewalls "4 WAN ports" (algunos MikroTik avanzados) | PLAN, sin fecha |
| Parametrizaciones NMAP intrusivas en Tracker (requiere contrato DPIA con el cliente) | PLAN, requiere decisión legal primero |
| D.3 — Recuperación remota de AP sin ruta de red (PoE vía SNMP) | Ver detalle arriba en Parte D.3 — requiere acceso físico a switches para confirmar OIDs |

---

# Parte N — Agente Shomer (shomer-agent) — reescrita 13 sep 2026 contra código real

Componente paralelo en Docker, **separado** de `/opt/network_monitor/`. No modifica código ni BD de Shomer — solo lee sus APIs como cliente. Es donde vive el bot de Telegram y el cerebro.

## N.1 Ubicación y archivos (40 módulos en `core/`, verificado 13 sep 2026)

```
/storage/shomer-agent/
├── core/
│   ├── bot.py                  ← Bot Telegram: comandos, callbacks, menú
│   ├── monitor.py              ← 41 monitores automáticos en background (orquestador; ya
│   │                              le cedió 5 módulos propios con el tiempo, ver abajo)
│   ├── brain.py                ← Cerebro: correlación entre sistemas, aporta_algo() filtra
│   │                              qué interrumpe por Telegram (ver Estado vivo, arriba)
│   ├── conocimiento_general.py ← Base de conocimiento técnico validado (CompTIA + industria
│   │                              hotelera), 263 conceptos + 173 reglas — datos en core/data/*.json
│   ├── informe_coordinador.py  ← Informe periódico al coordinador por correo (no Telegram)
│   ├── chronic_tickets.py      ← Tickets de hallazgos crónicos, cierre por evidencia real
│   ├── incident_escalation.py  ← Agrupa caídas repetidas del mismo equipo en 1 digest
│   ├── pulse_correlate.py      ← Agrupa oleadas de Pulse (degradación) y caídas masivas
│   ├── vpn_usuarios.py         ← Usuarios VPN conocidos (aprendizaje por ventana, 14 días)
│   ├── pattern_analysis.py     ← Detección de patrones crónicos por equipo
│   ├── agente_skills.py        ← Carga SITE.md/EQUIPOS.md/notas de campo para el cerebro
│   ├── memoria_central.py      ← Sincroniza hechos (backups, etc.) a memoria persistente
│   ├── learning.py             ← Aprendizaje activo (confirma/refuta reglas con el tiempo)
│   ├── investigacion.py        ← Diagnóstico asistido bajo demanda
│   ├── triage.py                ← Clasificación de severidad de eventos
│   ├── hunter_context.py / hunter_labels.py  ← Contexto y etiquetas legibles para Hunter
│   ├── journal_context.py      ← Contexto de journal/logs para diagnóstico
│   ├── groq_helper.py          ← Groq — monitores de fondo, fallback chat (plan FREE)
│   ├── openai_helper.py        ← OpenAI gpt-4o-mini — chat interactivo + tools
│   ├── llm_router.py           ← Selecciona proveedor LLM (interactivo vs. fondo)
│   ├── local_fallback.py       ← Respuestas sin LLM si ambos proveedores fallan
│   ├── tools.py                ← 35 tool definitions (function calling del chat)
│   ├── memory.py               ← Memoria SQLite por usuario (conversations.db)
│   ├── maintenance.py          ← Modo mantenimiento global + rate-limit por usuario
│   ├── download_server.py      ← HTTP server puerto 8082 — links de descarga temporales
│   ├── access.py               ← Niveles de acceso developer/tecnico/none
│   ├── device_manager.py       ← CRUD de equipos en devices.json
│   ├── shomer_api.py           ← Cliente APIs Shomer :8000/:8001
│   ├── repair.py                ← Reinicio de servicios vía SSH
│   ├── backup_manager.py       ← Backups tarball + B2
│   ├── changelog.py            ← SQLite log de cambios y rollback
│   ├── identity.py              ← SITE_NAME, leído de `base.client_name` vía API (no de .env)
│   ├── health.py / events.py / ui_notify.py / fmt.py / version.py  ← Helpers
├── drivers/
│   ├── base.py                 ← Clase base DeviceDriver (FULL/API/PING)
│   ├── linux_generic.py        ← GL.iNet, OpenWrt, DD-WRT, RPi, genérico
│   ├── mikrotik.py             ← MikroTik RouterOS
│   ├── tplink_eap.py           ← TP-Link EAP/Omada — SNMP v2c
│   ├── ubiquiti.py             ← Ubiquiti UniFi/EdgeRouter — SSH
│   ├── aruba.py                ← ArubaOS Instant/Controller
│   ├── cisco.py                ← Cisco SG/SF switches IOS
│   ├── printer.py              ← Impresoras (SNMP)
│   ├── ssh_helper.py           ← SSH compartido con algoritmos legacy
│   └── detector.py             ← Auto-detección por banner SSH + hint explícito
├── core/data/                  ← Contenido de PRODUCTO versionado en git (no confundir con
│   │                              data/ de abajo) — conocimiento_teoria.json, conocimiento_reglas.json
├── data/                       ← Volumen por SITIO, nunca a git — persiste entre rebuilds
│   ├── devices.json, knowledge.db, conversations.db, dev_sessions.json, backups/, downloads/
├── docs/                       ← CATALOGO_TASK.md, POLITICAS_AGENTE.md, PROTOCOLO_CAMBIOS_AGENTE.md
├── BEHAVIOR.md / TECNICO_OPERACION.md / CHANGELOG.md
├── Dockerfile / docker-compose.yml
└── .env                        ← Tokens y credenciales del sitio (chmod 600, NO al repo)
```

## N.2 Servicios y recursos

| Componente | Detalle |
|-----------|---------|
| Servicio systemd | `shomer-agent.service` — arranca con el sistema |
| Docker container | `shomer-agent` — `network_mode: host` (acceso directo a LAN) |
| LLM chat interactivo | OpenAI `gpt-4o-mini` si `LLM_PROVIDER_INTERACTIVE=openai`; **default `groq`** |
| LLM monitores / fondo | Groq Llama (free tier) vía `core/groq_helper.py` |
| Bot Telegram | **Un bot y un grupo por sitio, nunca compartido** (desde Sesión 80) |

## N.3 Variables de entorno (.env) — ver `.env.example` para la lista completa y actualizada

No se transcribe aquí completa a propósito: **`.env.example` en el repo es la fuente de verdad**, se mantiene junto al código y evita que esta referencia se desactualice otra vez. Las que más importan operativamente:

```
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID   # únicos por sitio
GROQ_API_KEY                            # console.groq.com, gratis
LLM_PROVIDER_INTERACTIVE=groq           # groq | openai (default groq)
OPENAI_API_KEY / OPENAI_MODEL           # solo si se usa OpenAI para el chat
SHOMER_URL / SHOMER_USER / SHOMER_PASS  # credenciales del panel Shomer del sitio
SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS
SUPPORT_EMAIL_FROM / SUPPORT_EMAIL_TO   # informe al coordinador (core/informe_coordinador.py)
INFORME_COORDINADOR_CADA / _HORA / _DIA # periodicidad del informe (diario|semanal)
MAC_RECONCILE_SUBNET                    # override explícito; por defecto se detecta solo (ver Estado vivo)
```

**Límite de gasto OpenAI (obligatorio en campo):** Settings → Limits → monthly budget. El límite mensual en la web sí corta la API al llegar.

## N.4 Niveles de acceso

| Nivel | Quién | Cómo se identifica |
|-------|-------|--------------------|
| `developer` | Desarrollador USB Ingeniería | `AGENT_DEVELOPER_ID` — funciona desde cualquier chat o DM directo |
| `tecnico` | Técnico del cliente | `TELEGRAM_CHAT_ID` — solo desde el chat configurado |
| `none` | Cualquier otro | Ignorado silenciosamente |

## N.5 Comandos Telegram

Lista canónica en código (`_ayuda_text()` + `set_my_commands` en `core/bot.py`) — **verificar con `tools/auditar_comandos.py`** antes de asumir que un comando existe o está en el menú; cruza `CommandHandler` reales contra lo publicado. Estado 13 sep 2026: 42 registrados, 38 funciones `cmd_*`, 37 publicados en el menú (5 registrados pero informativos/no publicados a propósito: `/aprobar_task`, `/autobloqueo`, `/silenciar`, `/start`, `/version`).

Categorías: salud del servidor (`/salud`), equipos e infra (`/equipos`, `/infra`, `/diagnostico`), Guardian (`/reboot`, `/modo`), Hunter (`/seguro`, `/liberar`, `/bloquear`, `/desbloquear`, `/alertas`), gestión de conocimiento (`/guardar`, `/historial`, `/revertir`), instalación (`/instalar`, `/verificar`, `/usuario`), inventario del agente (`/agregar`, `/eliminar`), y texto libre con 35 tools de function calling.

## N.6 Monitores automáticos (background)

**41 monitores activos** (verificado 13 sep 2026 con `tools/auditar_monitores.py`, que compara lo que corre de verdad contra lo que se muestra en `/monitores` — correrlo tras agregar o quitar uno). El orden en que deciden si algo interrumpe por Telegram está en el **Mapa de decisión de alertas** (arriba, en Estado vivo) — no repetido aquí para no desincronizarse de nuevo.

**Limpieza automática de disco** (sin autorización): journal >7 días, logs >7 días, `/tmp` >1 día, cache APT. A 85% ejecuta y notifica; a 92% pide autorización developer para Docker prune.

## N.7 Lógica WAN coordinada (3 niveles)

```
1. Todos los APs de un grupo offline → "Switch del piso X caído"
2. Múltiples grupos offline → ping 8.8.8.8 desde firewall sonda
   ├── Ping falla → "CAÍDA WAN — contactar ISP" (repite cada 10 min)
   └── Ping OK   → "Problema infraestructura interna"
3. Recuperación → confirmación a técnico y developer
```

Esto es sobre el internet DEL SERVIDOR. El internet de los HUÉSPEDES se mide aparte, desde el gateway (`shomer_wan_hotel.py` + `watch_internet_hotel`, ver Estado vivo) — son cosas distintas, no confundir.

## N.8 Reparación — `/salud` y post-acción

`/salud` es solo reporte de estado, sin botones. Reparación manual vía `/diagnostico <ip> reparar`. **Guardar solución** (`knowledge.db`): tras reboot/desbloqueo/recuperación → botones `save_know:*`, el antecedente aparece en alertas futuras (📋). SSH de reparación usa clave dedicada (`data/agent_restart_key`).

## N.9 Lógica multi-vendor

| Nivel | Capacidad | Equipos |
|-------|-----------|---------|
| `FULL` | Ping + SSH + reboot + clientes | MikroTik, Ubiquiti, GL.iNet, OpenWrt, TP-Link EAP, Cisco |
| `PING` | Solo ICMP | TP-Link Archer consumer, modems ISP |

`"no_reboot": true` en `devices.json` bloquea reboot aunque tenga SSH — usado en firewalls Hunter.

## N.10 Comandos de operación

```bash
sudo docker compose -f /storage/shomer-agent/docker-compose.yml ps
sudo docker compose -f /storage/shomer-agent/docker-compose.yml logs --tail=30
sudo systemctl restart shomer-agent.service
# Tras cambios de código: usar tools/fleet_sync.sh (propaga + reinicia + verifica salud + revierte si falla)
```

## N.11 Acceso remoto VPN WireGuard — OpenWrt (referencia, ver también Parte E.5)

VPN WireGuard sobre el mismo OpenWrt que se flashea para Hunter (Parte E.5). Servidor `10.99.0.1/24`, puerto UDP `51820`. Cada técnico adicional: nuevo par de llaves + `[Peer]` en OpenWrt vía UCI. **El WAN del OpenWrt y la LAN del hotel no deben compartir subred** — causa conflicto de rutas (bug real encontrado en lab).

## N.12 Backup del agente

Domingos 02:00 → `weekly_backup`. Local en `data/backups/` (rotación: máx. 2, borra el más antiguo). B2 opcional (`BACKUP_B2_*` en `.env`). Incluye BDs, `.env`, configs de servicios. Acciones reversibles con `changelog.py` (`block↔unblock`, `add_device↔remove_device`); reboot/restart/limpieza quedan logueados pero no son reversibles.

## N.13 Principio de diseño del agente

**Solo acciones reversibles y remediales:**
- ✅ Permitido: reiniciar APs, desbloquear IPs, reiniciar servicios Shomer, limpiar disco, scan inventario, modo mantenimiento
- ❌ Prohibido: modificar configuración de red, tocar UFW, borrar snapshots, restaurar sin doble confirmación, cambiar JWT/credenciales

---

# 📚 Historia completa

Sesiones 1-88 y las partes/sub-secciones ya resueltas o superadas por el estado real →
**`CLAUDE_historico.md`**. **Nada se borró**: ahí queda el detalle de cada cambio/parche.
`CLAUDE.md` y (si aplica) documentación de campo se montan `:ro` en el contenedor del bot —
un cambio en el host se refleja sin rebuild.
