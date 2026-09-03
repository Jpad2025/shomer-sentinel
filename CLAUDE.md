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

Detalle credenciales Tracker AD: §AI.3 · Usuario servicio sitio: §D.2 · Protector Zeus (cuenta local distinta): §AV.

---


---

# 🔑 Estado vivo — LÉEME PRIMERO (resumen curado)

> Arranque de sesión: lo esencial y **vigente**. Partes A–N (abajo) = manual estable.
> Historia completa (Sesiones 1–68, antiguas partes O–§BK) → **`CLAUDE_historico.md`**.
> Config específica del sitio → **`SITE.md`** (NO va a git).

## Disciplina (obligatoria)
- **Un módulo por tarea** (Tracker / Protector / Hunter / Guardian / Bot). No cruzar credenciales.
- Producción Ópera: sin la palabra **adelante** → no deploy, no restart, no SQL de escritura, no scripts no pedidos.
- **Nunca** correr código de módulos con `sudo`/root → siembra archivos root que rompen servicios (ver lecciones).
- Regla Cursor: `.cursor/rules/shomer-modulos-disciplina.mdc`.

## Dónde vive todo
- Core/Guardian/Hunter/Tracker/Protector: `/opt/network_monitor/` — en Ópera es **copia desplegada (NO git)**; el git vive en labs/GitHub.
- Agente/Bot: `/storage/shomer-agent/` — repo git propio (`github:jpad2025/shomer-agent`).
- BD reales: `/storage/db/network_monitor.db` (Guardian/Hunter/Protector) · `/storage/db/inventory.db` (Tracker). Los symlinks en `/opt/*.db` son solo red de seguridad → deben apuntar a estos.
- Servicios: `shomer-guardian` (Core :8000) y `shomer-tools` (:8001) como **usb_admin**; `shomer-agent` en Docker (root, por diseño). `CLAUDE.md` se monta read-only en el contenedor del bot.
- Config (deuda: 3 fuentes, consolidar a futuro): `system_state` (BD) + `.env` (agente) + Redis.

## Estado por módulo (vigente)
- **Guardian**: 52 nodos / 30 APs. Auto-reboot SSH (umbral 3 / cooldown 300 s). Estado en **Redis**: `failures:`, `last_reboot:`, `node_maintenance:`. ⚠️ `node_maintenance:*` con TTL −1 suprime alertas **en silencio**.
- **Hunter**: bloqueo IPs en MikroTik. `only_external` se respeta **también** en la cadena Wazuh (internas de `hunter.subnets` no se autobloquean). Bloqueo manual siempre disponible.
- **Protector**: 1 equipo (Zeus PMS `.5`) → Restic local `/srv/shomer_backups/staging` → B2. Retención **5 local / 3 B2** (decisión del sitio; **no** subir a 30 sin pedido del hotel). Backup 05:00 / sync B2 05:30.
- **Tracker**: inventario en `inventory.db` (assets + snapshots). Solo credenciales Tracker.
- **Bot/IA**: 2 IAs — **Groq** (fondo/monitores, plan **FREE**) + **OpenAI** gpt-4o-mini (chat, con topes). Contenedor **`TZ=America/Bogota`**. Briefing **08:00** (resumen + puertos); mant. nocturno **sin Telegram si OK**. `/guardar` → `knowledge_decision()` (consejo en alertas/IA, no piloto auto). **Desde Sesión 80: los 4 sitios (Ópera, .205, .243, .245) tienen cada uno su propio bot y su propio grupo de Telegram, nunca compartido** — antes .243/.245 compartían el bot de .205 y los 4 compartían el chat personal de Juan Pablo.

## Lecciones vivas (bugs cerrados que importan)
- **sudo/root**: tras cualquier `sudo restic` o correr módulos como root → revisar dueño del **repo** Y de `~/.cache/restic` Y de `__pycache__`; fix `chown -R usb_admin`. (Causó panel Protector "sin snapshots" y `.pyc` de Hunter en root.)
- **Protector "sin snapshots" en panel**: casi siempre caché restic root o locks huérfanos → `restic unlock` + chown caché. **Los datos NO se pierden.**
- **Groq "caído"**: es límite del plan **FREE** (RPM/TPM/RPD), no una caída. `watch_groq` chequea con `models.list()` (sin gastar tokens); un 429 de fondo **no** pausa el bot; alerta máx **1/día**.
- **Guardian mantenimiento**: revisar que solo los APs que deben estén en `node_maintenance` (TTL −1 = permanente y silencioso).
- **BD symlink**: `/opt/network_monitor/*.db` deben apuntar a `/storage/db/*.db` reales (no a archivos vacíos).

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

## Sesión 69 (5 ago 2026) — reducción de ruido Telegram

Análisis de `memoria_alertas.db` (1535 mensajes, 40 días) mostró que VPN (267 msgs,
17% del total) y ~10 APs/impresoras crónicamente flapping (AP REST SCALA 29
críticos, Bixolon .60/.243 con 94 c/u) concentraban más de la mitad del volumen
reciente de alertas. Cambios en `/storage/shomer-agent/core/monitor.py`
(commits `e516bf7`, `ca02017`, merge `e936ae2` — pusheados a GitHub, desplegados
en Ópera y en lab `.205`):

- **VPN → digest agrupado**: conexiones/desconexiones ya no mandan un mensaje
  por evento; se acumulan y se envían en un solo mensaje cada
  `VPN_DIGEST_INTERVAL_SEC` (default 1800s/30 min). No se pierde información
  (sigue en `memoria_alertas`), solo baja la frecuencia de interrupciones.
- **Guardian/Inframonitor → alerta compacta para flappers crónicos**: cuando
  `pattern_analysis` (`patrones_detectados`) ya tiene a la entidad con
  `ocurrencias >= BOT_CHRONIC_ALERT_MIN_OCURRENCIAS` (default 5), la caída se
  avisa con una línea corta ("caída #N de un patrón ya conocido") en vez de
  repetir el bloque completo impacto/acción/sugerencia. **No suprime nada** —
  sigue avisando cada caída real, solo deja de repetir texto ya sabido de un
  problema físico ya reportado a campo.

**Deliberadamente NO tocado esta sesión** (documentado, no resuelto — ver
`docs/PENDIENTES_LAB.md`):
- Impresoras Bixolon POS `.60`/`.243` — 94 caídas c/u en 40 días: es un problema
  físico (cable/PoE/firmware), no de software. Pendiente de campo.
- Reinicios del contenedor `shomer-agent` (42 veces en 40 días, con ráfagas) y
  errores DNS intermitentes del contenedor (`Temporary failure in name
  resolution`, causando alertas con `sent_ok=0`) — sin causa raíz confirmada
  todavía, requieren investigación antes de un fix.

**Pendiente de sincronizar:** labs `.245` y `.243` tienen trabajo local sin
commitear en `core/` (más features que su propio HEAD de git) — no se tocaron
para no arriesgar ese WIP. `.205` sí quedó al día (`git pull` limpio).

## Sesión 70 (10-11 ago 2026) — Auditoría Ópera: verificación honesta, causa real de caídas

Auditoría completa del sitio Ópera pedida por Juan Pablo. Primera pasada tuvo errores de
interpretación (se afirmó "problema físico de red, no de software" sin verificarlo, y que 7
equipos con >100 caídas —incl. 2 switches y 2 terminales Ingenico— "se replicarían" en otros
hoteles, cuando son hardware físico de un solo sitio). Corregido tras aviso de Juan Pablo: se
rehizo la auditoría **solo lectura**, marcando explícitamente VERIFICADO (dato/código real)
vs. no confirmado.

Hallazgos verificados contra código/datos reales:

- **La duración "180-240s" de caída que aparece en reportes NO es downtime real** — es
  artefacto de diseño: `INFRA_PULSE_PERSIST_TICKS=6` (config Ópera,
  `/etc/shomer/shomer-runtime.env`) × sondeo cada 30s (`FAST_POLL_INTERVAL_SEC`) = 6 lecturas
  malas seguidas para marcar degradado + 6 buenas para marcar recuperado → 180-240s por
  matemática del contador, sin importar cuánto duró la falla real.
- **Hallazgo grande, sin resolver:** 20-21 equipos completamente distintos del hotel (switches,
  cámaras, terminales de pago, etc. — monitoreados por **Inframonitor**, no Guardian) caen
  exactamente en el mismo segundo, varias veces por semana. No puede ser 20 fallas físicas
  independientes — hay una causa compartida sin identificar. Ver pendiente en
  `docs/PENDIENTES_LAB.md`.
- **Investigado y descartado como causa:** NIC de gestión del servidor (`eno1`) — descarta
  paquetes activamente (~5-6/s constante, medido en vivo) pero sin ninguna señal de tarjeta
  fallando: no está en modo promiscuo, Suricata usa su propia NIC USB dedicada
  (`enx9c69d33bc55f`, 3.300M paquetes con solo 1.367 descartes), `ethtool -S` casi limpio (17
  eventos de buffer en 26 días), `fq_codel` con 0 descartes. Compatible con ruido normal de
  tráfico broadcast/multicast del hotel — no explica la caída sincronizada.
- **Confirmado por separado:** los 7 equipos con >100 caídas (incl. 2 switches y 2 terminales
  Ingenico) sí son indicio de problema físico de cable/puerto/PoE — pero local a ese hardware
  específico de Ópera, no algo que "viaje" a otro hotel. Lo que sí es igual en cada instalación
  es el código/umbrales de **Inframonitor**: si se sospecha falso positivo por sensibilidad,
  revisar ese umbral (no el de Guardian).

**Sin cambios de código ni de config esta sesión** — solo lectura, por pedido explícito de
Juan Pablo tras la corrección.

## Sesión 71 (13 ago 2026) — Fix: "Nodo recuperado" repetido en equipos flapeando

Juan Pablo reportó que estaban llegando 70+ mensajes de Telegram. Verificado contra
`/storage/shomer-agent/data/memoria.db`: **54 mensajes en 24h, 192 en 48h**, y el **81% de
las 24h (44 de 54) eran el mismo mensaje repetido** — "✅ Nodo recuperado — AP OFC-COCINA
(192.168.0.113)" — un AP entrando y saliendo de línea cada 4-8 min.

**Causa (verificada leyendo el código):** el lado de las caídas ya está protegido —
`incident_escalation.py` (Sesión 69→v1.1.0) agrupa fallas repetidas en una ventana de 1h y
solo manda un resumen/escalamiento. Pero el aviso de **recuperación**, en
`monitor.py::watch_guardian_nodes` (~línea 1588), se mandaba directo en cada transición a
`online`, sin pasar por esa misma ventana — por eso el flapping generaba un "recuperado" por
cada blip aunque la caída correspondiente ya estuviera silenciada.

**Fix (`shomer-agent` v1.1.1, commit `2bf8202`):**
- `incident_escalation.is_flapping(ip)` — true si el incidente activo de esa IP ya acumuló
  2+ eventos dentro de la ventana de agregación.
- `watch_guardian_nodes` suprime "Nodo recuperado" si `is_flapping(ip)` — la primera
  recuperación de un incidente se sigue avisando normal, solo se calla la repetición.

**Desplegado:** `py_compile` OK · push a GitHub · `docker restart shomer-agent` en Ópera
(logs limpios, sin tracebacks) · propagado a `shomer205`/`shomer243`/`shomer245` con
`tools/fleet_sync.sh` (sin stash necesario, salud OK en los 3, sin rollback).

**Pendiente de confirmar con datos:** aún no se verificó con tráfico real posterior al fix
que bajó el conteo de mensajes de OFC-COCINA — revisar `memoria.db` en unas horas.

### Addendum — `eno1` re-verificado en vivo, causa del "dropped" identificada

Juan Pablo pidió revisar de nuevo la interfaz `eno1` (la tarjeta que en Sesión 70 se había
descartado como causa de las caídas sincronizadas). Re-verificado en vivo, 3 días después:

- **Hardware sigue limpio, sin cambios:** `rx_errors=0`, `tx_errors=0`, `rx_crc_errors=0`,
  `rx_no_buffer_count=17` (idéntico al de Sesión 70, no subió), `promiscuity 0`, `tc -s qdisc`
  0 drops de salida.
- **Tasa de "dropped" medida en vivo:** 5.19 pkt/s (delta real de 78 paquetes en 15.0s) —
  igual que los "~5-6/s" de hace 3 días, estable, no empeora.
- **Nuevo — identificado con qué tráfico coincide** (captura `tcpdump -e` de 20s en `eno1`):
  **97 tramas RRCP** (ethertype `0x8899`, protocolo propietario Realtek de detección de loop
  entre switches en cascada — Linux no tiene manejador para ese ethertype, se cuentan como
  drop siempre) desde **5 switches distintos** (OUI `00:9e:1e:16:*`, ~1/s cada uno) + 195
  tramas 802.1Q sin ninguna interfaz VLAN configurada en este host (`ip -br link` no tiene
  `eno1.X`) que tampoco tienen a dónde entregarse.
- **Conclusión:** el "dropped" de `eno1` es ruido normal de capa 2 entre los switches del
  hotel (RRCP/VLAN), no una tarjeta fallando ni relacionado con la caída sincronizada de
  20+ equipos — esa causa raíz sigue sin identificar (ver `PENDIENTES_LAB.md` §Sesión 70).

## Sesión 72 (13 ago 2026) — Caída masiva: se encuentra el patrón, se suprime con tope

Se le preguntó a RRCP si podía causar el falso positivo de caídas sincronizadas (Sesión 70) —
**descartado, sin evidencia** (ver detalle abajo). Pero investigando el mecanismo se encontró
algo más útil: revisando `/var/log/shomer/api.log.1` aparecieron **80 "ciclo lento" de
Guardian en un solo día**, y cruzando `status_events` contra `infra_blip_events` se confirmó
que **5/5 caídas masivas (8+ equipos) de los últimos 14 días nunca activaron el guardia de
blip** — el gateway nunca aparecía unhealthy en esos ciclos, así que se avisaron como caídas
reales, equipo por equipo.

**Nueva herramienta — `tools/analizar_caidas_masivas.py`** (solo lectura): clasifica lotes de
caída masiva según su firma de recuperación. Corrida contra los 14 días reales: **los 5
incidentes clasifican como SOSPECHOSO** — 92-100% de los equipos se recuperaron solos en
<15min, 73-100% de esas recuperaciones cayeron en la misma ventana de 60s. Firma de origen
host, no de fallas físicas independientes.

**Observabilidad (desplegado):** los logs de ciclo de Guardian (`shomer_guardian_nodes.py`)
iban a `/var/log/shomer/api.log` sin timestamp (el logger no tiene `basicConfig`, así que solo
pasan WARNING+, nunca INFO — por diseño de Python, no es un bug a arreglar). Se agregó hora
Bogotá + `batch_id` a los WARNING de "ciclo lento" y de blip; Inframonitor (ya tenía hora vía
journald) se le agregó `batch_id`. Nuevo WARNING específico en `shomer_network_blip.py` para
cuando el umbral de caída masiva se cumple pero el gateway no lo refleja.

**Fix de comportamiento (desplegado, `shomer_network_blip.py`):** ahora una caída masiva
(8+/20+/50% inventario) se suprime **aunque el gateway se vea sano** — la firma real es la
recuperación sincronizada, no el estado del gateway. El propio ciclo del poller (10-30s) hace
de recheck natural. **Tope de seguridad `INFRA_BLIP_MASS_MAX_SEC=600s`** (racha en memoria,
por poller): si la caída masiva sigue después de 10 min, se deja de suprimir y se avisa como
real — para no tapar para siempre una falla ancha genuina. Verificado con prueba manual del
estado (suprime, deja de suprimir pasado el tope, limpia el tracker al recuperarse) antes de
desplegar. `py_compile` OK, `shomer-guardian` + `shomer-inframonitor-poller` reiniciados,
`/health` OK, sin errores en los logs tras reiniciar.

**Pendiente:** confirmar con la próxima caída masiva real que el nuevo WARNING aparece y que
de verdad bajó el volumen de alertas — no se pudo probar en vivo (no se puede forzar una caída
masiva real de forma segura). Causa raíz de fondo (por qué caen juntos) sigue sin identificar.

## Sesión 73 (14 ago 2026) — causa raíz del gateway + reconciliación IP-por-MAC

**Investigando la causa de fondo de Sesión 72** se encontró que las caídas masivas GRANDES
(21-30 de N equipos, no un subconjunto) sí tienen causa identificada: el **gateway del hotel
(`192.168.0.1`) se cae de verdad, con frecuencia** — confirmado en el log real
(`shomer-inframonitor-poller`, 13 ago 10:20:26: "gateway offline, 100% pérdida" junto con 22/22
equipos de Inframonitor cayendo a la vez). **No es un bug de Shomer — es la red física del
hotel** (router/ISP). Ya se detecta y se silencia bien por el `host_network_blip` clásico.
Frecuencia real (`infra_blip_events`): **509 veces en julio, 125 en lo que va de agosto**, ~17/día
en julio. Puesto en pausa como pendiente de campo — ver `PENDIENTES_LAB.md`. El grupo más chico
de caídas parciales (gateway sano) sigue sin causa identificada, aparte de este hallazgo.

**Hallazgo aparte, mismo día:** al revisar por qué el equipo Bixolon `.60` dejó de reportar
(9 jul), se armó `tools/detectar_cambio_ip.py` (cruza la MAC guardada de cada equipo Guardian/
Inframonitor contra el último escaneo de Tracker) — `.60` resultó realmente desconectado (su MAC
no aparece en ningún lado), pero encontró un caso real distinto: **AP LOBBY RECEPCION** estaba
configurado en `.121` y ya vivía en `.137` — cambio de IP nunca detectado, causaba una alerta de
"caído" permanente y falsa.

**Nuevo — `app/api/shomer_mac_reconcile.py`, automático, corriendo ya:** en vez de depender de
que alguien corra un escaneo de Tracker (son manuales, pueden pasar semanas), hace su propio
barrido cada `MAC_RECONCILE_INTERVAL_SEC` (default 1800s/30min): pinguea el `/24` en paralelo y
lee la tabla ARP del kernel (`ip neigh`, sin necesitar root — a diferencia de `nmap -sn`, que
solo muestra MAC con privilegios; Guardian corre como `usb_admin`, **el primer intento con nmap
devolvía 0 resultados siempre, en silencio**, se cambió de método antes de desplegar). Si la MAC
de un equipo **offline** aparece en otra IP, actualiza `devices.ip_address` (Guardian) o
`infra_devices.ip` (Inframonitor) sola y deja un `WARNING` en el log. No toca equipos que estén
online. No migra estado de Redis — el siguiente ciclo de poll lo reconstruye solo, con la IP
correcta. Arranca junto con `shomer-guardian.service` (`main.py::lifespan`, mismo patrón que los
demás pollers). Aplicado ya a mano una vez: AP LOBBY RECEPCION corregido en ambas tablas,
verificado con `tools/detectar_cambio_ip.py` (0 discrepancias tras el fix).

## Sesión 74 (23-24 ago 2026) — un solo canal de Telegram (Opción 2)

**El problema, encontrado por Juan Pablo contando mensajes a mano:** contó ~130 mensajes reales
un día, el sistema (`memoria_alertas` del bot) solo tenía 23 registrados. Causa: Guardian tenía
su **propio canal directo** a la API de Telegram (`app/scripts/alerts.py::send_telegram_alert`,
usado por 13 archivos — reboots fallidos, backups, bloqueos Hunter, salud de nodos) que nunca
pasaba por ningún filtro ni quedaba registrado en `memoria_alertas`. Formato distinto también
("PÉRDIDA DE SERVICIO SHOMER" vs "🔴 AP X sin LAN" del bot) — no se veía como el mismo sistema.

**Paso 1 — contador de verdad (`telegram_enviados.db`):** tabla nueva en
`/storage/shomer-agent/data/` (escribible desde el host Y desde el contenedor del bot —
`/storage/db` es solo-lectura para el bot, por diseño, por eso no se usó esa base). Se registra
en el punto exacto donde Telegram confirma envío (HTTP 200), sin importar qué camino lo mandó.

**Paso 2 — Opción 2, un solo canal real:** `send_telegram_alert()` ya **no manda directo** — encola
en `notificaciones_pendientes` (misma BD compartida). El bot (`watch_pending_guardian`, nuevo,
revisa cada 10s) lo releva por `_send()` — mismo formato, mismo prefijo de sitio, misma auditoría
que todo lo demás del bot. Si el bot no releva en 60s (caído/lento), `shomer_telegram_relay.py`
(nuevo, revisa cada 20s del lado network_monitor) lo manda directo como respaldo — nada se pierde
solo porque el bot esté caído en ese momento exacto. Los 13 callers de `send_telegram_alert` no
cambiaron — misma firma, mismo comportamiento desde su punto de vista.

**Antes de construirlo se verificó** que depender del bot como canal principal fuera razonable:
revisando el log del contenedor (14 días disponibles), los únicos reinicios fueron deliberados
(despliegues de este mismo proyecto) — cero caídas inesperadas en ese período. La nota vieja de
"42 reinicios en 40 días" (Sesión 69) no se sostiene con los datos recientes.

**Verificado en vivo con un evento real** (no una simulación): al reiniciar Guardian, generó su
aviso normal de "sistema reiniciado" — se encoló, el bot lo relevó 22s después (dentro del
margen de 60s), llegó a Telegram con el prefijo `[Hotel Opera]` igual que cualquier otro mensaje
del bot. `py_compile` OK en los 5 archivos tocados, ambos servicios reiniciados sin errores,
desplegado en Ópera + los 3 labs.

**Pendiente:** no se probó en vivo el camino de respaldo (Guardian mandando directo porque el bot
no contestó en 60s) — para eso hay que apagar el bot a propósito, no se hizo hoy para no
interferir con la comparación de conteos que Juan Pablo está haciendo en paralelo.

## Sesión 74 (cont.) — "salud del propio Shomer" en 2 reportes: 07:00 y 22:00

Del inventario completo de mensajes (14 tipos, agrupados por propósito — equipos de red, VPN,
seguridad, backups, IA, y "salud del propio Shomer"), Juan Pablo pidió unificar el último grupo:
antes `watch_docker` (agente reiniciado), `watch_network_audit` (auditoría atrasada/riesgos) y
`watch_port_errors` (errores de puerto, ya corría a las 08:00) mandaban su propio mensaje suelto
cada uno, en momentos distintos del día.

**Ahora, 2 reportes nada más:**
- **07:00** (`daily_summary`, movido de 08:00) — el resumen completo de siempre (red, Hunter, IA)
  + servidor (CPU/RAM/disco/servicios) + lo que se acumuló en la libreta compartida.
- **22:00** (`evening_summary`, nuevo) — más liviano: solo servidor + libreta desde la mañana, o
  "sin novedades" si no hay nada (para confirmar que el sistema sigue vivo, no que nadie miró).

Mecanismo: `watch_docker`/`watch_network_audit`/`watch_port_errors` ya no llaman `_send()` —
anotan en `notas_reporte` (tabla nueva en `knowledge.db`, persistida, no en memoria) y los dos
reportes la leen y la vacían. `watch_port_errors` se corrió de 08:00 a 06:58 para que su nota
esté lista cuando corre el reporte de las 07:00. `_build_server_line()` extraído como función
compartida para no duplicar la lógica CPU/RAM/disco/servicios entre los dos reportes.

Probado en vivo antes de desplegar: escribir + leer + vaciar la libreta, dentro del contenedor.
`py_compile` OK, bot reiniciado sin errores, desplegado en Ópera + los 3 labs.

**Pendiente:** confirmar mañana que el reporte de las 07:00 sale bien con las notas incluidas
(no se pudo esperar a que pasaran las 07:00 reales para verlo en vivo) — y el de las 22:00 hoy
mismo.

## Sesión 74 (cont. 2) — etiqueta única para "equipos de red" (equipos_red)

Del punto 1 del inventario de mensajes: 8 etiquetas internas distintas (`watch_guardian_nodes`,
`watch_infra_equipment`, `watch_infra_printer`, `watch_infra_service`, `watch_infra_pulse`,
`watch_infra_flap`, `watch_infra_snmp`, `guardian_relay`) para lo que conceptualmente es una
sola cosa. Unificadas todas en **`equipos_red`** — mismo mensaje, mismo ícono, mismo momento de
envío, solo cambia la etiqueta interna que usan los reportes para contar/agrupar.

**Hallazgo de paso, corregido:** `incident_escalation.py` etiquetaba TODOS sus digests/
recordatorios como `watch_guardian_nodes` aun cuando el equipo era de Inframonitor (switches/
impresoras/cámaras) — mislabeling real desde que ese módulo se compartió entre los dos en
v1.1.3 (Sesión 73). Ya corregido de paso al unificar.

**Nota sin resolver, no bloqueante:** encontrado un caso real (verificado con datos de hoy, no
solo teoría) donde el buffer de `triage.py` hace que un mensaje de AP termine etiquetado `bot`
en vez de la etiqueta correcta — no pierde ni cambia el contenido del mensaje que ve el técnico,
solo desvía el conteo agregado en un pequeño % de los casos. No se investigó la causa raíz hoy.

`py_compile` OK en los 2 archivos tocados, bot reiniciado sin errores, desplegado en Ópera + los
3 labs.

## Sesión 74 (cont. 3) — revisión a fondo del bot: 1 bug real encontrado y corregido

Juan Pablo pidió perseguir la nota "sin resolver" de arriba y revisar el bot/monitores a fondo
en busca de más errores.

**Bug real confirmado y arreglado — `core/triage.py`:** `TriageManager.emit()`/`_flush()`
llamaban a `self._send(...)` **sin pasar `monitor=`** — la etiqueta correcta (`event.origen`,
armada bien por el closure `_dispatch` de `_emit()`) se recibía en `notify()` como parámetro
`send_fn` pero **se descartaba sin usar**: una vez que el manager de triage existe, se llama
`mgr.emit(event)` en vez de ese `send_fn`. Como el triage está activo en producción ("Triage
activo" en el log de arranque), **todo mensaje que pasara por el buffer perdía su etiqueta real**
y caía al default `"bot"` — no era un caso raro del 1%, era sistemático para cualquier evento
bufferizado. `ShomerEvent` ya traía `origen` en el dataclass, `TriageManager` simplemente nunca
lo leía. Fix: usar `event.origen` (camino sin buffer) y `events[-1].origen` (camino con buffer,
mismo criterio que ya se usaba para `severity`) en las dos llamadas a `self._send`.

Probado en vivo sin tocar Telegram real: `ShomerEvent` simulado con `origen='equipos_red'`,
confirmado que `_send` recibe el monitor correcto en vez de perderlo.

**Encontrado de paso, informativo, no se tocó:**
- `_monitor_ctx` (ContextVar declarado en `monitor.py`) **nunca se usa** — se declara y se lee
  (`_resolve_monitor`) pero ningún lugar del código llama `.set()` sobre él. Es código muerto;
  no rompe nada, pero sugiere una capacidad de etiquetado automático que en realidad no existe.
- `auto_tasks.py::_notify_result` tampoco pasa `monitor=` explícito — hereda el mismo default
  `"bot"` genérico. Dado que `_monitor_ctx` está muerto (punto anterior), esto es consistente
  y esperado, no un bug — solo significa que los resultados de auto-tareas siempre se cuentan
  como "bot" en los reportes, sin categoría propia.
- **Investigado y descartado como bug:** `auto_unblock`'s docstring dice "sin reincidencia" —
  se verificó el esquema real de `blocked_ips` (`ip UNIQUE` + `INSERT OR REPLACE`) y confirmé
  que una reincidencia sí resetea `blocked_at` correctamente. La lógica es correcta como está.

`py_compile` OK, bot reiniciado sin errores, desplegado en Ópera + los 3 labs.

---

## Sesión 75 (24 ago 2026) — revisión a fondo de los 28 monitores por bloques

Juan Pablo pidió dividir la revisión de los monitores en bloques y revisarlos a fondo,
sospechando que había más bugs. Se dividieron en 6 bloques temáticos (red/equipos,
seguridad, backups/protector, sistema/recursos, otros/pipeline, IA/reportes) y se revisó
cada función línea por línea, verificando cada hallazgo con datos/ejecución real antes de
tocar código (regla de la sesión: nunca afirmar sin verificar).

**Bug grave — `watch_wan_outage` (Bloque 5), `core/monitor.py`:** `_wan_outage_start` y
`_wan_last_repeat` se asignaban dentro de la función sin declararlas `global` — Python las
trata como variables locales para TODA la función porque se les asigna en algún punto, y
se leían ANTES de esa asignación local. Resultado: `UnboundLocalError` garantizado cada vez
que había 2+ grupos offline o 2+ nodos Guardian offline — exactamente el escenario que esta
función existe para detectar (caída de switch/WAN a nivel de sector u hotel completo). La
excepción quedaba atrapada por el `except` genérico de siempre — **probablemente nunca
mandó la alerta de "Conectividad WAN" ni "Red interna" en la vida del sistema.** Reproducido
el error en aislado, confirmado a nivel de bytecode (`co_varnames`) que el fix lo resuelve, y
corrido un barrido estático (`ast`) sobre las 28 funciones buscando el mismo patrón — validado
el script contra la versión sin el fix (sí lo detecta) y confirmado que era el único caso.

**Bug grave — `watch_security()` no vigilaba nada, nunca (Bloque 2), movido a network_monitor:**
la "Capa 1" de seguridad (fuerza bruta SSH, login en horario inusual, copia de archivos
sensibles, USB conectado) corría dentro del contenedor Docker del bot y nunca tuvo acceso real
a lo que decía vigilar. Verificado en vivo con `docker exec`: `/var/log/auth.log` no existe en
el contenedor (sí en el host, no está montado), `who` solo ve sesiones del contenedor (vacío),
`journalctl` ni siquiera está instalado, `/proc/mounts` es el namespace de montajes propio del
contenedor. Las 4 detecciones nunca dispararon una sola alerta real, en silencio, desde que
existían. Se decidió con Juan Pablo la opción "correcta" (no la fácil): mover la lógica a
network_monitor (proceso host, igual que Guardian/Hunter/Protector), nuevo archivo
`app/api/security_watch.py`. Además de reubicar, se corrigieron 2 detecciones que ni
conceptualmente iban a funcionar aunque corrieran en el host: login inusual ahora lee líneas
"Accepted ... from" de `auth.log` en vez de `who` (que solo ve sesiones activas en el instante
exacto del poll); copia de archivos sensibles ahora escanea procesos `scp/rsync/sftp/tar`
activos vía `/proc` en vez de `journalctl -u ssh` (sshd no registra el comando ejecutado en su
unidad systemd — ese patrón nunca iba a matchear nada, ni corriendo en el host). Probado en
vivo contra datos reales del host antes de desplegar (auth.log real parseado correctamente,
fuerza bruta y login inusual con líneas sintéticas, copia sensible con un proceso real
disfrazado de rsync tocando `/opt/network_monitor` — detectado). `watch_security()` se eliminó
del bot (28 tasks en vez de 29); se agregó el tag `SEGURIDAD —` a `ALLOWED_TAGS` en
`alerts.py` (mismo canal auditado de `send_telegram_alert`/Opción 2).

**Bugs medianos — `_tick()` faltante en éxito (Bloques 1 y 6):** `weekly_backup` y
`watch_protector_retry` solo llamaban `_tick(name, error=...)` en el `except`, nunca
`_tick(name)` en éxito. Efecto en `/monitores`: si nunca fallaban, mostraban "sin datos aún"
para siempre; si fallaban una vez, quedaban con el error **pegado permanentemente** aunque
después funcionaran bien meses. `watch_openai` tenía el mismo gap pero acotado a los primeros
~10 min de una caída activa (antes de cruzar el umbral de alerta). Los 3 corregidos.

**Bug — `watch_port_errors` crasheaba cada fin de mes:** `target.replace(day=target.day + 1)`
lanza `ValueError` (día inválido) cada vez que se calcula "mañana" en el último día de un mes
(ej. 31 ago → día 32). Cambiado a `target + timedelta(days=1)`, que maneja el rollover de
mes/año correctamente (probado con 31-ago, 31-dic y 28-feb).

**Bug menor — `watch_pending_guardian`:** la conexión sqlite no se cerraba si `_send()` o el
`UPDATE` fallaban a mitad del loop. Envuelto en `try/finally`.

**`/monitores` (bot.py) tenía 5 monitores invisibles:** `evening_summary`, `watch_infra_pulse`,
`watch_pending_guardian`, `watch_memoria_sync` y `watch_pattern_analysis` corrían pero no
estaban en `MONITOR_LABELS`/`MONITOR_GROUPS` — el técnico no podía ver su estado de salud.
Agregados. Corregido también el label de `watch_port_errors` (decía "informe diario 08:00",
ya no manda mensaje propio desde Sesión 74 cont.).

**Descartado tras investigar (no era bug):** sospecha de desfase de timezone en
`watch_backups` (`ultimo.replace("Z","")`) — verificado que `last_backup_at` se escribe con
`datetime.now()` naive en hora local (Bogotá) tanto en el host como en el contenedor del bot
(mismo TZ en ambos), sin sufijo "Z" real — el `.replace` es vestigial pero inofensivo, no hay
desfase.

**Hallazgo aparte, CORREGIDO — logging de network_monitor sin formato (no invisible):**
la primera lectura de este hallazgo decía que los `logger.warning()` se perdían del todo —
**eso era incorrecto, verificado y corregido en la misma sesión.** Root logger sin handler
propio → Python usa su `lastResort` (fallback silencioso a stderr) con formato `%(message)s`
puro: sin nivel, sin timestamp, sin nombre de logger. Los mensajes SÍ llegaban al archivo,
pero indistinguibles a simple vista de un `print()` — por eso un `grep "^WARNING"` normal
(como se hizo en la primera pasada) nunca los encontraba. Prueba concluyente: se buscó un
caso YA OCURRIDO con evidencia independiente (`blocked_ips` con `blocked_by='auto'`,
IP 192.168.0.27 bloqueada el 22 ago) y se encontró la línea real en `api.log.2.gz`:
`AUTO-BLOCK 192.168.0.27 sid=2035089 sig=...` — sin ningún prefijo. Fix: nuevo
`app/api/logging_setup.py` con `configure_app_logging()` — agrega handler al root logger con
formato `timestamp [NIVEL] nombre: mensaje`, mismo nivel WARNING de antes (no se sube a INFO
para no inflar el volumen — 133 call sites de `.info()` en el árbol). Llamado al inicio de
`main.py` (8000, Guardian/Hunter) y `main_tools.py` (8001, Tracker/Protector), antes de
cualquier otro import de la app. Verificado que uvicorn.*/uvicorn.access no se duplican
(tienen su propio handler con `propagate=False` en su `LOGGING_CONFIG`) — probado en vivo
que "Started server process" aparece exactamente 1 vez tras el cambio. Desplegado y
verificado (`/health` limpio) en `shomer-guardian.service` + `shomer-tools.service` de Ópera
y en los 3 labs.

Deploy: `py_compile` en cada cambio, pruebas en vivo contra datos/ejecución real antes de
desplegar (simulaciones con `docker exec`, reproducción aislada del `UnboundLocalError`,
inspección de bytecode, barrido estático `ast`). Desplegado y verificado (`/health` limpio,
logs sin errores nuevos) en Ópera + los 3 labs, en 3 tandas de commits
(`bc75243`→`58eb9b6`→`a27071f` en shomer-agent; `9272696` en network_monitor).

### ✅ Revisión 24 ago 2026 — checklist de la auditoría a fondo

| Bloque | Monitores | Estado | Bugs encontrados |
|---|---|---|---|
| 1. Red/equipos | `watch_guardian_nodes`, `watch_infra`, `watch_connectivity`, `watch_active_threats`, `watch_network_audit`, `watch_port_errors` | ✅ revisado | `watch_port_errors` (crash fin de mes), `watch_pending_guardian` (fuga sqlite), 5 monitores invisibles en `/monitores` |
| 2. Seguridad | `watch_hunter`, `watch_hunter_verify`, `watch_security`, `watch_mikrotik_security` | ✅ revisado | `watch_security` — **grave**, nunca funcionó dentro del contenedor, movido al host |
| 3. Backups/Protector | `watch_backups`, `watch_protector_sample`, `watch_protector_retry` | ✅ revisado | `watch_protector_retry` (`_tick` faltante en éxito) |
| 4. Sistema/recursos | `watch_resources`, `watch_disk`, `watch_docker`, `watch_log_truncate`, `watch_services` | ✅ revisado | ninguno nuevo |
| 5. Otros/pipeline | `watch_wan_outage`, `watch_pipeline`, `watch_devices`, `watch_pattern_analysis`, `watch_memoria_sync`, `watch_pending_guardian` | ✅ revisado | `watch_wan_outage` — **grave**, `UnboundLocalError` garantizado en caída de 2+ grupos/WAN |
| 6. IA/reportes | `watch_groq`, `watch_openai`, `daily_summary`, `evening_summary` | ✅ revisado | `watch_openai` (`_tick` faltante primeros 10 min de caída) |
| Aparte | logging de `network_monitor` (Guardian/Hunter/Tracker/Protector, todo el host, no solo el bot) | ✅ revisado y corregido | root logger sin formato — mensajes llegaban pero sin nivel/timestamp/nombre |
| Aparte (cont.) | los 24 `except Exception: pass` de `core/monitor.py`, revisados uno por uno | ✅ revisado | `watch_hunter`, `watch_hunter_verify` (grave), `watch_pipeline` — seed de estado sin reintento |

**Total: 2 bugs graves, 7 menores, 1 sospecha descartada tras verificar, 2 hallazgos transversales corregidos (logging + seeds sin reintento). Los 28 monitores del bot + los 2 procesos host de network_monitor quedaron cubiertos por lo menos una vez cada uno, más una auditoría línea-por-línea de todos los `except Exception: pass` del bot.**

**Sesión 75 (cont. 2) — auditoría de los 24 `except: pass`:** revisado cada uno con su
contexto completo. 21 son degradaciones seguras por diseño (fallan hacia inacción o un
fallback razonable). 3 no lo eran — `watch_hunter`, `watch_hunter_verify` y `watch_pipeline`
sembraban su estado inicial (qué IPs/pipeline ya estaban en X condición al arrancar, para no
re-alertar sobre algo pre-existente) con un try/except de **un solo intento, antes del loop
principal** — si ese intento fallaba (transitorio, API aún no lista en los primeros
15-100s tras el arranque), el estado quedaba sembrado vacío **para siempre**, nunca se
reintentaba. Efecto real: en el peor caso (`watch_hunter_verify`, sin red de seguridad
adicional) el próximo ciclo hubiera reportado TODAS las IPs privadas ya bloqueadas como
"IP interna bloqueada — revisar" de golpe. Fix: mismo patrón ya usado por `watch_infra`
(`_infra_seed_done`) — el seed vive dentro del loop, gateado por un flag, se reintenta cada
ciclo hasta que funciona. Verificado en vivo con `docker exec` (fallo simulado del primer
intento + éxito del segundo: 0 alertas falsas en los 3 casos, y `watch_hunter_verify`
confirmado que sigue detectando una IP genuinamente nueva). Confirmado también en producción
real tras el deploy: log de arranque mostró "watch_hunter: 92 IPs pre-existentes cargadas
(sin alerta)" — sin ninguna alerta falsa.

**Sesión 75 (cont. 3) — puntos 1, 2 y 3 de los faltantes:**

1. **Confirmar en producción real** — todavía no ha ocurrido una caída de 2+ grupos
   (`watch_wan_outage`) ni ningún evento de seguridad real (`security_watch.py`); ambos siguen
   vivos y sin errores (confirmado: proceso estable, `/health` limpio, sin crashes desde el
   deploy). Sigue como pendiente de observación — no se puede forzar sin simular un incidente
   real. **De paso, revisando logs para confirmar esto, apareció otro bug real y activo:**
   `llama-3.3-70b-versatile` (el modelo Groq hardcodeado en 5 sitios de `groq_helper.py`,
   usado por `explain()` — el chokepoint de TODA la IA de diagnóstico del bot: pattern_analysis,
   hunter_context, journal_context, resúmenes, diagnóstico de puertos) fue retirado del catálogo
   Groq — 404 `model_not_found` cada ~15-40 min desde al menos el 23 ago (verificado con
   `models.list()` real: ya no aparece en el catálogo). `watch_groq` no lo detectó porque su
   healthcheck solo prueba conectividad/credencial (`models.list()`), no un chat real con el
   modelo específico. Fix: nueva constante `GROQ_MODEL` (env var, default
   `openai/gpt-oss-20b`) en vez de hardcodear — mismo patrón que `OPENAI_MODEL`. Probado contra
   la API real antes de elegir el reemplazo (texto simple + tool calling, ambos OK) y
   end-to-end con `explain()` tras el cambio.
2. **Barrido estático (`ast`) extendido** a los 112 archivos de `network_monitor` (antes solo
   `security_watch.py`) y a los 35 de `core/` en shomer-agent (antes solo `monitor.py`) — script
   validado contra un caso sintético con el mismo bug de `watch_wan_outage` antes de confiar en
   el resultado. **0 problemas nuevos en 147 archivos** — confirma que `watch_wan_outage` era el
   único caso en todo el sistema, no solo en `monitor.py`.
3. **Revisión de lógica de negocio, Bloques 3-4:** `watch_disk` y `watch_services` revisados a
   fondo — histéresis y "reintento único, luego escala al humano" son diseño intencional, no
   bugs. Encontrado un patrón repetido en 6 sitios (`daily_summary`, `evening_summary`,
   `watch_log_truncate`, `watch_backups`, `watch_protector_sample`, `weekly_backup`): comparaban
   solo el día del mes o la semana ISO (`now.day`, `now.isocalendar()[1]`) para saber "¿ya
   revisé esto?" — si el proceso corre >1 mes/año seguido y se pierde una ventana de chequeo
   completa, la próxima coincidencia del mismo día-de-mes/semana (ej. 31 ago vs 31 oct) se
   salta por error. Verificado el caso concreto (`datetime(2026,8,31).day ==
   datetime(2026,10,31).day` → `True`, el bug real). Severidad baja (se autocorrige al día
   siguiente, requiere una combinación rara), pero el fix es barato y se aplicó en los 6 sitios
   (`now.day` → `now.date()`, `isocalendar()[1]` → `isocalendar()[:2]`).

Deploy de esta ronda: `82b77c0` (Groq) y `8465a6a` (fechas) en shomer-agent, verificado en
Ópera + 3 labs.

### 📋 Tabla maestra — falla y solución, monitor por monitor (30 de shomer-agent + 2 de network_monitor)

| Monitor | Bloque | Falla encontrada | Solución aplicada |
|---|---|---|---|
| `watch_hunter` | 2 | Seed de IPs pre-existentes de un solo intento — si fallaba, quedaba vacío para siempre (riesgo mitigado por chequeo de antigüedad ya existente) | Seed movido dentro del loop, reintenta cada ciclo hasta funcionar (`b663970`) |
| `watch_devices` | 5 | "✅ Equipo recuperado" huérfano en blips de 1-2 ciclos (nunca se alertó la caída porque no llegó a los 3 ciclos necesarios) — mismo bug ya arreglado en `watch_groq` el 8 jun 2026, nunca replicado acá | `_device_down_alerted` (set) — mismo criterio que `_guardian_down_alerted`, "recuperado" solo si hubo "caído" real antes (`a3b696e`) |
| `daily_summary` | 6 | Comparaba solo día-del-mes (`now.day`); **además** marcaba el día como "ya enviado" ANTES de confirmar que `_send()` funcionara — un fallo en cualquier paso previo (API, Groq, etc.) perdía el reporte del día completo sin reintento | `now.day` → `now.date()`; bandera movida a después del `_send()` exitoso (`8465a6a`, `d28ee65`) |
| `evening_summary` | 6 | Mismo bug de fecha + mismo bug de bandera-antes-de-confirmar que `daily_summary`; además estaba invisible en `/monitores` | Fecha y orden de bandera corregidos + agregado a `MONITOR_LABELS`/`MONITOR_GROUPS` (`bc75243`, `8465a6a`, `d28ee65`) |
| `watch_resources` | 4 | Ninguna (histéresis CPU/RAM revisada a fondo, correcta por diseño) | — |
| `watch_backups` | 3 | Mismo bug de fecha (día-del-mes) para "¿ya revisé este equipo hoy?" | `now.day` → `now.date()` (`8465a6a`) |
| `watch_wan_outage` | 5 | **GRAVE** — `_wan_outage_start`/`_wan_last_repeat` sin `global`, `UnboundLocalError` garantizado en caída de 2+ grupos/WAN — probablemente nunca mandó esta alerta | `global` agregado; verificado con reproducción aislada + inspección de bytecode (`58eb9b6`) |
| `watch_disk` | 4 | Ninguna (umbrales 80/85/92% e histéresis de reset revisados a fondo, correctos) | — |
| `watch_log_truncate` | 4 | Mismo bug de fecha (día-del-mes) | `now.day` → `now.date()` (`8465a6a`) |
| `watch_protector_sample` | 3 | Mismo bug pero de semana ISO (`isocalendar()[1]`) | `isocalendar()[1]` → `isocalendar()[:2]` (año+semana) (`8465a6a`) |
| `watch_pipeline` | 5 | Seed de "pipeline ya degradado al arrancar" de un solo intento — peor caso: 1 alerta redundante (no falsa) | Seed movido dentro del loop, reintenta cada ciclo (`b663970`) |
| `watch_services` | 4 | Ninguna ("reintento único, luego escala al humano" es diseño intencional) | — |
| `watch_guardian_nodes` | 1 | Ninguna | — |
| `preventive_reboot` | — | Ninguna | — |
| `weekly_backup` | 3 | `_tick()` faltante en éxito → `/monitores` mostraba "sin datos" para siempre o un error pegado permanente; además mismo bug de semana ISO | `_tick()` agregado (`bc75243`); fecha corregida (`8465a6a`) |
| `watch_protector_retry` | 3 | Mismo bug de `_tick()` faltante en éxito | `_tick()` agregado (`bc75243`) |
| `watch_hunter_verify` | 2 | **GRAVE** — mismo bug de seed que `watch_hunter` pero SIN red de seguridad: un fallo transitorio hubiera reportado TODAS las IPs privadas ya bloqueadas como "revisar" de golpe | Seed movido dentro del loop (`b663970`); confirmado en producción real: "92 IPs pre-existentes cargadas (sin alerta)" |
| `watch_docker` | 4 | Ninguna (limitación de `docker.sock` ya documentada y resuelta en sesión previa) | — |
| `watch_connectivity` | 1 | Ninguna | — |
| `watch_groq` | 6 | Ninguna en el monitor mismo — pero su healthcheck (`models.list()`) no detecta que el modelo de chat específico esté roto (ver hallazgo aparte abajo) | — |
| `watch_openai` | 6 | `_tick()` faltante durante los primeros ~10 min de una caída activa (antes de cruzar el umbral de alerta) | `_tick()` agregado en la rama que faltaba (`a27071f`) |
| `watch_mikrotik_security` | 2 | Ninguna (usa API/SSH real vía network_monitor, no archivos locales) | — |
| `auto_unblock` | — | Sospecha de bug (docstring "sin reincidencia") investigada y descartada — el esquema real (`ip UNIQUE` + `INSERT OR REPLACE`) sí resetea correctamente | — (ruled out) |
| `watch_infra` | 1 | Menor: `watch_infra_vpn` usa `snmp_alert` en vez de un flag propio para su "última alerta" (cosmético, no afecta el contenido del mensaje) | No corregido — bajo impacto, solo afecta el timestamp de `/monitores` |
| `watch_active_threats` | 1 | Ninguna (sin lógica de diff/alerta, solo mantiene estado) | — |
| `watch_network_audit` | 1 | Ninguna | — |
| `watch_port_errors` | 1 | **Crash cada fin de mes** — `target.replace(day=target.day+1)` inválido en meses con distinto número de días | `timedelta(days=1)` en vez de `.replace(day=+1)`, probado con 31-ago/dic/28-feb (`bc75243`) |
| `watch_pattern_analysis` | 5 | Ninguna | — |
| `watch_memoria_sync` | 5 | Ninguna | — |
| `watch_pending_guardian` | 1 y 5 | Conexión sqlite no se cerraba si `_send()`/`UPDATE` fallaban a mitad de loop; además invisible en `/monitores` | `try/finally` agregado; agregado a `MONITOR_LABELS`/`MONITOR_GROUPS` (`bc75243`) |
| `watch_security` (bot) | 2 | **GRAVE** — corría en el contenedor, sin acceso real a `auth.log`, `who`, `journalctl` ni `/proc/mounts` del host. Nunca detectó nada, nunca, desde que existía | Eliminado del bot; reescrito como `security_watch.py` en network_monitor (host real), con 2 de las 4 detecciones también corregidas conceptualmente (`9272696`). **Ya en producción generó un falso positivo real** (22:58 del 24 ago: marcó un `deploy.sh` legítimo como "copia de archivos sensibles", porque deploy.sh usa rsync tocando `/opt/network_monitor` igual que un atacante real lo haría) — corregido el mismo día con `_has_trusted_ancestor()` (deploy.sh/fleet_sync.sh como ancestro del proceso = confiable), verificado con relación padre-hijo real antes de desplegar y confirmado con un deploy real después (`c380bfc`, 0 alertas) |
| logging de `network_monitor` (host, todo el proceso, no un monitor) | aparte | Root logger sin handler propio → formato `lastResort` sin nivel/timestamp/nombre — mensajes llegaban pero invisibles a un `grep` normal | `logging_setup.py` con formato correcto, mismo nivel WARNING de antes (`c3688a6`) |
| modelo Groq (`groq_helper.py`, usado por casi todos los diagnósticos IA) | aparte | `llama-3.3-70b-versatile` retirado del catálogo Groq — 404 desde hace 1+ día, sin detectar por `watch_groq` | `GROQ_MODEL` configurable (env var), probado contra la API real antes de elegir `openai/gpt-oss-20b` (`82b77c0`) |

**Sesión 75 (cont. 5) — Bloque 5 a fondo + barrido de todos los "recuperado":** revisado
`watch_devices` línea por línea — el mensaje "✅ Equipo recuperado" se mandaba comparando solo
el estado anterior crudo, sin verificar si esa caída había llegado a los 3 ciclos necesarios
para mandar la alerta de "🔴 sin respuesta" en primer lugar. Un blip de 1-2 ciclos generaba un
"recuperado" huérfano. Mismo bug ya encontrado y arreglado en `watch_groq` el 8 jun 2026, nunca
replicado en este monitor hermano. Fix: `_device_down_alerted` (set), mismo criterio que
`_guardian_down_alerted`. Verificado en vivo: blip de 1 ciclo → 0 mensajes; caída real de 4
ciclos → "sin respuesta" + "recuperado", ambos correctos (`a3b696e`).

Aprovechando el hallazgo, se revisaron **todos** los mensajes de "recuperado" del archivo
(`grep` de las 20 ocurrencias) para descartar el mismo patrón en otro lado: `watch_resources`,
`watch_wan_outage` (grupo y red), `watch_services`, `watch_guardian_nodes` (nodo y post-reboot),
`watch_connectivity`, `watch_groq`, `watch_openai`, `watch_infra` (equipo/impresora, servicio
TCP, puerto SNMP) — todos correctamente gateados por un flag de "se alertó antes" (o, en
`watch_connectivity`, sin ventana de riesgo porque no hay debounce entre detectar y alertar).
`watch_devices` era el único caso.

**Sesión 75 (cont. 6) — `daily_summary`/`evening_summary` perfeccionados:** encontrado un
segundo bug en ambos, más serio que el de fecha: la bandera "ya se envió hoy" se asignaba
ANTES de confirmar que el envío realmente funcionara — un fallo en cualquier paso previo
(`shomer_api.summary_text()`, `get_daily_health()`, la llamada a Groq, etc.) perdía el reporte
del día **completo**, sin reintento, con la bandera ya diciendo "hecho". Mismo patrón de fondo
que el bug de `weekly_backup`/`watch_protector_retry` del Bloque 1, aplicado ahora a los 2
reportes diarios más importantes. Fix: la bandera se asigna después del `_send()` exitoso.
Verificado en vivo simulando un fallo en el primer paso — confirmado que el siguiente ciclo
(60s después, dentro de la misma ventana de 2 min) reintenta y sí manda el reporte.
`watch_pattern_analysis`/`watch_memoria_sync` confirmados sin bugs — su lógica de negocio real
vive en módulos aparte (`pattern_analysis.py`, `memoria_central.py`), fuera del alcance de "los
monitores". **Con esto, los 30 monitores de shomer-agent quedan con revisión de negocio
completa, no solo estructural.**

**Bloque nuevo — lógica propia de network_monitor (Guardian/Hunter/Infra/Protector):** la
revisión anterior cubrió los monitores del BOT que *consumen* estos datos vía `shomer_api`,
pero no la implementación real del lado host. Por pedido explícito de Juan Pablo ("si es un
monitor muy grande, haz solo ese en el bloque, bien línea por línea, y dejamos los demás para
luego"): se hizo `shomer_guardian_nodes.py` completo (1227 líneas, el poller central de
Guardian) a fondo; `casador_autoblock_poller.py`, `shomer_inframonitor.py` (2230 líneas),
`backups.py` y el resto quedan para una sesión futura.

**Hallazgo grave — reinicio automático podía disparar antes de confirmar "offline":** el
umbral para REINICIAR un equipo por SSH/SNMP (`guardian.fail_threshold`, configurable desde el
panel) y el umbral para CONFIRMAR oficialmente que está offline (`SHOMER_OFFLINE_PERSIST_TICKS`,
solo por env var) son dos contadores independientes que incrementan igual, sin validación
cruzada entre ellos. En Ópera hoy ambos valen 3 — coincidencia, no diseño — así que no ha
causado un problema real todavía. Pero si alguien bajara `fail_threshold` por debajo de
`offline_persist_ticks` (algo razonable de querer, para reiniciar más rápido), Guardian
reiniciaría el equipo por SSH/SNMP **antes** de que el panel lo mostrara como caído: el
técnico vería "⚡ reinicio en progreso" sin ningún "🔴 caída" previo, y el equipo se seguiría
viendo "online" en el panel mientras se reiniciaba de verdad.

Fix: nueva bandera `reboot_confirmed_ok` — el reinicio ahora requiere `new_failures>=threshold`
**y** que el estado ya esté confirmado offline, efectivamente `max(threshold,
offline_persist_ticks)` en vez de solo `threshold` (sin sumar ambos, para no duplicar el tiempo
de espera). Verificado con 3 simulaciones directas de `_build_node_outcome()` a lo largo de
varios ciclos (sin tocar Redis/SSH real): config actual de Ópera (3,3) → reboot en tick 3, SIN
CAMBIO; escenario vulnerable (threshold=1, persist=3) → reboot ahora espera al tick 3 en vez
de disparar en el tick 1, confirmado que el status nunca se ve "offline" antes del reinicio
real; config más conservadora (5,3) → reboot en tick 5, sin cambio.

**Sistema en modo mantenimiento** (`shomer_maintenance=1`, sin TTL) — Juan Pablo lo activó él
mismo antes de pedir este fix, a propósito. Sigue activo; queda pendiente de él decidir cuándo
desactivarlo (no se tocó).

Desplegado y verificado (`/health` limpio) en Ópera + los 3 labs (`b32ef48`).

## Sesión 76 (26 ago 2026) — checklist repasado: 2 hallazgos reales más en `security_watch.py`

Al retomar, se repasó el checklist de verificación de la Sesión 75 contra producción real
(`telegram_enviados.db`, `docker logs`, `/health`) antes de seguir con el bloque nuevo:

- ✅ `daily_summary`/`evening_summary` llegaron sin falta los 2 días siguientes (25 y 26 ago).
- ✅ Cero errores nuevos de Groq `model_not_found` en 24h+.
- ⏳ Sin caída real de 2+ grupos todavía — `watch_wan_outage` sigue sin poder confirmarse en
  vivo (no depende de nosotros, hay que esperar).
- ⚠️ **`security_watch.py` — 2 hallazgos reales de ruido, ambos corregidos hoy:**
  1. Los 2 falsos positivos de "copia sensible" del 24 ago (deploy.sh) resultaron ser ambos de
     la ventana entre el commit del fix (`c380bfc`, 22:42:37) y el restart real del servicio —
     el fix en sí es sólido (confirmado corriendo un `deploy.sh` real hoy: 0 alertas nuevas, y
     verificada la cadena de procesos real vía `/proc`: el hijo `rsync` de `deploy.sh` tiene a
     `deploy.sh` como ancestro directo, tal como se diseñó).
  2. **Nuevo, no visto antes:** alerta diaria "Acceso SSH en horario inusual" a las 03:00,
     TODOS los días — causada por un login SSH legítimo desde `127.0.0.1` (loopback),
     confirmado en `auth.log` que este login diario ya existía desde antes de esta sesión (no
     es nuevo comportamiento, solo nueva detección). Un login desde localhost no puede ser un
     acceso externo real. Fix: ignorar IPs `127.*` en `_check_unusual_login()` (`3556e89`).
     Verificado en vivo: el mismo login loopback ya no genera alerta, una IP externa real
     sigue alertando normalmente.

Desplegado y verificado (`/health` limpio) en Ópera + los 3 labs.

## Sesión 76 (cont.) — `shomer_inframonitor.py` (2230 líneas, poller de Infra) a fondo

Mismo criterio que Guardian: revisado línea por línea. Cubierto (~1200 de 2230 líneas): setup
de tablas/migraciones, pools de hilos (fast/snmp separados), `_send_infra_alert`, cálculo de
uptime 24h, sync bidireccional de APs Guardian↔Infra, `_poll_fast_once`/`_poll_snmp_once`/
`_poll_once`/`_poller_loop`/`start_inframonitor_poller`, `_persist_poll_results` completo, y
`_collect_snmp_map` (con backoff de fallos). Es decir: toda la lógica que corre 24/7 sin
supervisión humana. Quedan sin revisar con la misma profundidad las rutas del panel
(`add_device`, `remove_device`, `get_status`, `manual_ping`, `get_snmp_data`, `device_action`,
~1000 líneas) — menor riesgo porque solo corren cuando un humano interactúa, no en background.

**Hallazgo (inactivo hoy, corregido de todas formas):** `_send_infra_alert()` usaba una sola
clave de cooldown Redis para las dos direcciones (caída y recuperación) — si el equipo se
recuperaba dentro de los 5 min de cooldown de la alerta de caída, el "recuperado" quedaba
bloqueado por la misma clave, dejando un "🔴 caído" sin su "🟢 recuperado" correspondiente.
Verificado que esta ruta está inactiva en Ópera (requiere `INFRA_TELEGRAM_PANEL=1`, no
configurado — las alertas de Infra hoy las genera `watch_infra()` del lado del bot). Corregido
de todas formas con clave de cooldown separada por dirección, para cuando se active.

`derive_liveness()` (en `infra_monitor_profiles.py`) revisado también — SNMP anulando ping
para `network_gear`/`printer`, y "degraded" siempre promovido a "online" para impresoras
(ping poco confiable en WiFi) son decisiones de diseño intencionales, documentadas en
comentarios existentes, no bugs.

Desplegado y verificado (`/health` limpio) en Ópera + los 3 labs.

## Sesión 76 (cont.) — `casador_autoblock_poller.py` (sin bugs) + `backups.py` (1 bug, inactivo)

`casador_autoblock_poller.py` (122 líneas, motor de auto-bloqueo Hunter 24/7) revisado
completo — dedup acotado por tamaño (8000 claves), política de severidad coherente (incluida
la excepción explícita para amenazas críticas internas pese a "solo externas"), corre detrás
del mismo `poller_leader` que evita doble ejecución entre workers. **Sin bugs.**

`backups.py` (1646 líneas, Protector) — revisada la lógica autónoma: `_scheduler_loop` (dedup
por día correcto vía `fire_key`, sin fugas de memoria real), `_run_global_b2_sync`,
`_backup_windows` (ya limpia mount CIFS y credenciales al terminar, con `finally`).
Descartado como bug real el timezone default `"America/Denver"` en `_site_timezone()` —
`base.timezone` SÍ está configurado como `America/Bogota` en Ópera, el fallback nunca se usa.

**Hallazgo (inactivo hoy, corregido de todas formas) — `_backup_linux`:** el directorio de
staging SCP (`/srv/shomer_backups/staging_ssh/{device_id}`) nunca se limpiaba entre corridas —
`scp recurse` sobreescribe lo que sigue existiendo en el remoto pero nunca purga lo que ya se
borró ahí, así que crecía sin límite y cada backup Restic incluía basura vieja acumulada.
Verificado que el directorio existe desde mayo pero está **vacío** — ningún equipo Linux/macOS
configurado para backup todavía en Ópera, código nunca ejecutado en producción. Corregido de
todas formas (limpia el staging antes de cada corrida, mismo criterio que `_backup_windows` ya
usa para sus propios recursos) para cuando se configure el primer equipo Linux.

Desplegado y verificado (`/health` limpio, puerto 8001) en Ópera + los 3 labs.

**Faltantes para seguir:**
1. Seguir esperando el evento real para `watch_wan_outage` (sin acción posible más allá de
   observar). `security_watch.py` ya tiene 2 rondas de ajuste por ruido real encontrado —
   seguir vigilando unos días más antes de darlo por estable.
2. **Rutas del panel de `shomer_inframonitor.py`** (~1000 líneas) y del resto de `backups.py`
   sin revisar con la misma profundidad — menor prioridad por ser código human-triggered.
4. **Desactivar el modo mantenimiento** cuando Juan Pablo decida — lo activó él mismo a
   propósito antes del fix de reinicio de Guardian, sigue activo.
5. **Tarea pendiente 2** (rediseño de qué eventos deben interrumpir en tiempo real al técnico
   vs. solo quedar registrados) y **Tarea pendiente 3** (checkpoint: dejar correr el sistema
   unos días antes de retomar la 2) — ya documentadas en sesiones anteriores, siguen abiertas,
   no tocadas hoy.

## Sesión 76 (26-27 ago 2026) — revisión EXHAUSTIVA de TODO network_monitor, sin excepciones

Juan Pablo pidió explícitamente no decidir por criterio propio qué archivos "importan menos" —
revisar los 112 archivos de `app/` (`api/`, `backend/`, `scripts/`), uno por uno, sin saltarse
ninguno. Progreso de esta sesión: ~48 de 112 archivos revisados a fondo (el resto queda para
continuar la próxima sesión — ver lista en `PENDIENTES_LAB.md`).

**🔴 Hallazgo de seguridad real y activo, ya corregido — `shomer_audit.py`:** el middleware de
auditoría del panel (`AuditMiddleware`) guarda el body de cada POST/PUT/PATCH/DELETE
autenticado en `audit_log`, con una lista `_MASK_BODY_PATHS` de rutas cuyo body debía
enmascararse por llevar credenciales. Esa lista estaba incompleta. **Confirmado en la BD real
de producción** (80,258 filas en Ópera): 21 filas con contraseñas reales en texto plano —
`/tracker/credentials` (contraseña de dominio de red), `/backups/devices*` (contraseñas de
equipos de backup SMB/Windows), `/api/router-devices` (ssh_password de routers), `/auth/users`
(contraseña de un usuario del PANEL). `shomer205` tenía 6 filas más, incluyendo `/auth/register`
(ruta que ni siquiera había aparecido en Ópera). Fix: `_MASK_BODY_PATHS` ampliada +
`_MASK_BODY_PREFIXES` nuevo para `/backups/devices*` y **todo `/auth/*`** (en vez de enumerar
cada sub-ruta de auth una por una). Verificado que las rutas confirmadas quedan como
"[REDACTED]" en el body guardado.

**Redacción retroactiva del historial (a pedido explícito de Juan Pablo):** se hizo backup de
`network_monitor.db` antes de tocar nada (`network_monitor.db.bak_pre_redact_<timestamp>` junto
a la BD real, en Ópera y en shomer205). Se redactaron las 21 filas de Ópera + 6 de shomer205
(`UPDATE audit_log SET body_summary='[REDACTED...]' WHERE ...`), conservando fecha/usuario/ruta
— solo se reemplazó el contenido con la contraseña real. Verificado con `count(*)` que quedaron
en 0 en los 4 servidores tras el fix + la redacción.

**Pendiente de decisión de Juan Pablo, no tocado:** la contraseña de dominio de red expuesta en
`/tracker/credentials` y la contraseña de usuario del panel expuesta en `/auth/users` estuvieron
en texto plano en la BD desde junio 2026 hasta hoy — **recomendado rotarlas** (cambiarlas), ya
que estuvieron potencialmente expuestas a cualquiera con acceso a `audit_log` o a
`/audit/logs`/`/audit/export/csv` (solo admin, pero aun así). No se rotó ninguna credencial real
sin que el usuario lo pida explícitamente.

**Hallazgo de negocio (no de código) — `shomer_technician.py`:** el sistema de score de
técnicos (usado para bonos) calcula `doc_rate=100` por defecto cuando un técnico no tuvo
reinicios en el mes — un técnico sin reinicios saca nota perfecta sin que se evalúe su
documentación real. Señalado a Juan Pablo, sin tocar (requiere su decisión de negocio, no una
corrección de código).

**Bugs de código reales encontrados y corregidos esta sesión (además de los ya documentados
arriba en las secciones de Guardian/Infra/Hunter/Protector):**
- `inventory_asset_report_pdf.py` — crash real y reproducido (`FPDFUnicodeEncodingException`)
  al exportar el PDF de un activo si el hostname/modelo/notas tenían un emoji u otro carácter
  fuera de Latin-1. Endpoint real, sin manejo de excepción en el caller. Fix: helper `_latin1()`
  aplicado también al encabezado y las notas (antes solo a los campos administrativos).
- **3 ocurrencias independientes** del mismo bug ("success falso" al recargar/alternar
  Suricata — reporta éxito sin revisar si el comando `systemctl`/`kill` realmente funcionó):
  `casador_support_rules_file.py::_reload_suricata`, `casador_intel.py::/suricata/toggle`,
  `casador_rules.py::/rules/reload` (una reimplementación duplicada e independiente de la
  primera). Los 3 corregidos con el mismo criterio: verificar el resultado real antes de
  reportar éxito.

**Código muerto confirmado (nunca se conecta a la app real, no causa daño activo pero puede
confundir a futuro):**
- `app/backend/database.py` + `models.py` — SQLAlchemy, nunca importado por nada.
- **Todo `app/backend/routes/`** (`devices.py`, `discovery.py`, `reboot.py`, `backup.py`,
  `inventory.py`, ~845 líneas) — ningún router se monta en `main.py`/`main_tools.py`. 3 de 5
  archivos tienen `from db import get_connection` roto (ese módulo no existe en el path real de
  la app) — ni cargarían si alguien los intentara usar.
- `app/scripts/ssh_recovery.py` (paramiko) — nadie lo llama, el mecanismo real de reboot SSH es
  `_run_ssh_reboot` en `shomer_guardian_lib.py`.
- `app/backend/reboot_playwright.py` + `router_http_manager.py` — dos implementaciones
  redundantes de "reboot HTTP de router" (Playwright vs `requests`), ninguna importada.
- `app/backend/scripts/backup_system.py` — solo lo llamaba el ya-muerto `routes/backup.py`;
  además tiene su propio bug interno (no sigue symlinks al empaquetar, y `network_monitor.db`
  es un symlink) que lo haría inútil si se revivió sin arreglarlo — no se tocó por estar inerte.

**Código dormido (funciona si corriera, pero nada lo invoca hoy — sin systemd/cron):**
`app/backend/scripts/auto_recovery.py`, `app/backend/scripts/reboot_glinet.py` (alcanzable solo
desde código muerto/dormido). `app/backend/scripts/inventory_sync.py` también dormido, y además
usa `connect()` (→ `network_monitor.db`) en vez de `connect_inventory()` (→ `inventory.db`) —
si se revive sin corregir eso, crearía una tabla `assets` fantasma en la BD equivocada.

**Revisado y confirmado activo/correcto sin bugs:** `app/scripts/inframonitor_poller.py`
(confirmado que ES el poller real vía `shomer-inframonitor-poller.service`, no el embebido),
`shomer_mac_reconcile.py` (loop autónomo real), `shomer_infra_pulse.py` (confirmado
`INFRA_PULSE_ENABLED=1` activo — revisada la máquina de estados EWMA a fondo, histéresis
correcta), `shomer_guardian_events.py` (el toggle real de mantenimiento), `security_http.py`,
`infra_monitor_profiles.py`, `casador_autoblock_poller.py`, `casador_support_health.py`,
`casador_support_suricata.py`, `shomer_common.py`, `shomer_guardian_devices.py`,
`shomer_guardian_discovery.py`, `hunter_signature_labels.py`, `scripts/network_context.py`, y
~25 archivos pequeños más (migraciones one-shot idempotentes, helpers sin lógica de negocio).

Todo desplegado y verificado (`/health` limpio) en Ópera + los 3 labs tras cada fix.

**Faltantes al cierre de Sesión 76:** quedaban ~64 archivos por revisar — completados en
Sesión 77 (ver sección siguiente). Pendientes que siguen abiertos: rotación de las 2
credenciales expuestas, evento real para `watch_wan_outage`, modo mantenimiento, Tarea
pendiente 2/3.

## Sesión 77 (27 ago 2026) — revisión EXHAUSTIVA completada: 112/112 archivos, `network_monitor` cerrado

Continuación directa de Sesión 76. Se revisaron los ~64 archivos restantes (más 2 no listados
originalmente que resultaron ser código vivo: `app/scripts/discovery.py` y un cruce con
`shomer_drill.py`). **Con esto, los 112 archivos de `network_monitor` quedan 100% revisados.**

**🔴 Hallazgo de seguridad — puerta trasera de fábrica en `auth_api.py`, reportado, NO corregido
(requiere decisión de diseño de Juan Pablo):** `_ensure_users_table()` se ejecuta en casi cada
acción de login/gestión de usuarios y siempre hace "si no existe `root`, créalo con password de
fábrica `shomer2026` (hash fijo, mismo en cualquier instalación de este software)". Confirmado
que el usuario `root` existe HOY en la BD de Ópera (id=163, admin), junto al `admin` real. Si
alguien borra `root` pensando que queda eliminado, la siguiente acción del panel lo vuelve a
crear con la contraseña de fábrica — no se puede quitar esa cuenta desde el panel. No se tocó el
código: cambiar este comportamiento es una decisión de diseño (¿debe existir un failsafe de
recuperación siempre disponible, o no?), no un bug a corregir unilateralmente.

**🟡 Seguridad — 2 rondas más de `shomer_audit.py` (mismo patrón de Sesión 76), corregidas y
desplegadas:** la revisión sistemática (`grep` de todo endpoint que acepta `password`/`_pass`)
encontró 4 rutas más con campos de contraseña sin enmascarar en el audit_log, **sin exposición
histórica confirmada en ninguna** (0 filas en las 4):
- `/setup/apply` (wifi_pass, service_pass del wizard de red) — commit `a2270df`.
- `/api/topology/config` (unifi_pass), `/backups/b2config` (b2_password), prefijo
  `/tracker/asset` (override_pass por equipo) — commit `1d3df6d`.
Desplegado y verificado en Ópera + 3 labs ambas rondas.

**Hallazgos menores, reportados sin corregir (bajo impacto, requieren decisión o son solo
higiene de código):**
- `shomer_config.py::/config/save_nodos` — escribe en `devices` usando columnas `ip`/
  `is_shomer_node` que no existen en el esquema real (`ip_address`, sin `is_shomer_node`) — 500
  garantizado si se llama. Ningún botón del panel actual lo usa.
- `shomer_proxies.py` — 3 rutas (`PATCH`/`DELETE /tracker/asset/{mac}`, `GET
  /snapshot/{id}/excel`) no repiten el chequeo de auth que sí tienen casi todas las demás; el
  servicio destino (8001) sí lo exige, y además 8001 está bloqueado a IPs externas por firewall
  (`ufw`) en los 4 servidores — verificado. Sin riesgo real hoy, solo inconsistencia de estilo.
- `/tracker/credentials` (lee/escribe la contraseña de dominio) solo exige "usuario
  autenticado", no admin — cualquier operador puede leer/cambiar la credencial de red. Decisión
  de política pendiente.
- `shomer_drill.py::_drill_running` (guarda el disparo manual del drill) y el scheduler mensual
  automático en `restore_drill.py` **no comparten el mismo flag** — ventana estrecha donde un
  drill manual y el automático podrían correr a la vez contra el mismo repo restic. No corregido
  (afecta lógica de backups en producción, requiere decidir diseño del mutex compartido).
- `app/backend/scripts/discovery.py` — **corrección de un hallazgo previo**: no es código
  muerto (lo importa `app/scripts/discovery.py`, usado por `/config/scan` e
  `/inventory/discovery_scan`), pero dentro de él las funciones `promote_ip_to_panel()` y
  `auto_promote_live_ips()` sí son código muerto — nunca las llama `run_discovery()`, y
  apuntan a un endpoint `/api/discovery/promote` que no existe en ningún lado. Sin efecto
  práctico porque nunca se ejecutan.

**Código dormido confirmado (nuevo esta sesión):** `app/scripts/monitor.py` (el "SHOMER Monitor
Pro v2.0" legacy) — no existe ni la unidad systemd `shomer-monitor.service` en Ópera pese a estar
documentada en la Parte A de este archivo; el WAN quorum/failsafe/heartbeat real hoy vive en
`shomer_guardian_server_health.py`.

**Revisado y confirmado sin bugs (33 archivos, además de los ya nombrados arriba):**
`auth_api.py` (aparte del hallazgo de root), `web_ui.py`, `backend/protector.py`,
`shomer_setup.py`, `casador_blocking.py`, `shomer_reports.py`, `shomer_audit_network.py`,
`shomer_noc.py`, `shomer_status_events.py`, `inventory.py` (completo), `inventory_discovery.py`,
`inventory_excel_export.py`, `inventory_label_pdf.py`, `shomer_guardian_server_health.py`,
`shomer_guardian_health_checks.py`, `shomer_guardian_lib.py`, `shomer_system_status.py`,
`shomer_incidents.py`, `shomer_host_health.py`, `shomer_audit_export.py`, `shomer_topology.py`,
`shomer_network_blip.py`, `casador_support_firewall.py`, `scripts/restore_drill.py`,
`scripts/scanner.py`, `scripts/tracker/discovery.py`, `scripts/tracker/persistence.py`,
`scripts/tracker/lldp_helper.py`, `scripts/tracker/extractor.py` (1441 líneas), `app/scripts/
discovery.py`, y los 7 scripts pequeños de `backend/scripts/` (migraciones idempotentes o
utilidades DEV, ninguna automática).

## Sesión 77 (cont.) — cierre: mutex del drill, contraseña root, código muerto movido

Juan Pablo dijo explícitamente que por ahora solo él y el asistente usan el sistema ("nadie
más"), y que hará una auditoría de seguridad propia más adelante — prioridad: que el sistema
funcione. En base a eso se resolvieron 3 de los pendientes de arriba en la misma sesión:

- **Mutex compartido del drill (arreglado):** `restore_drill.py` ahora expone
  `is_drill_running()` / `_set_drill_running()` como estado único; `shomer_drill.py` (trigger
  manual) dejó de tener su propio flag `_drill_running` y usa el mismo. El scheduler mensual
  ahora se salta el drill automático (con log de advertencia) si hay uno manual en curso, en vez
  de correr los dos a la vez contra el mismo repo restic. Desplegado en Ópera + 3 labs.
- **Contraseña de `root` cambiada** en Ópera (producción) a pedido explícito de Juan Pablo —
  valor no documentado aquí a propósito (no guardar contraseñas reales en este archivo, que
  vive en git). No se tocó en los labs. La puerta trasera de auto-recreación
  (`_ensure_users_table`) **se eliminó en Sesión 79** (ver abajo) — ya no reaparece sola.
- **Código muerto movido a `_archivo_obsoleto/`:** a pedido explícito de Juan Pablo (eligió
  "mover, no borrar" entre las opciones dadas). Se movieron, preservando estructura de carpetas:
  `app/backend/database.py`, `app/backend/models.py`, todo `app/backend/routes/` (6 archivos),
  `app/scripts/ssh_recovery.py`, `app/backend/reboot_playwright.py`,
  `app/backend/router_http_manager.py`, `app/backend/scripts/backup_system.py`. Antes de mover,
  se re-confirmó con grep que nada fuera de ese grupo los importaba. Verificado tras mover:
  `main.py` y `main_tools.py` compilan e **importan** sin error (no solo sintaxis), los dos
  servicios (`shomer-guardian`, `shomer-tools`) reiniciaron limpios y `/health` respondió 200 en
  ambos. **No se tocó** el código dormido (`auto_recovery.py`, `reboot_glinet.py`,
  `inventory_sync.py`, `monitor.py`) ni las 2 funciones muertas dentro de
  `backend/scripts/discovery.py` (`promote_ip_to_panel`/`auto_promote_live_ips`) — quedan solo
  documentadas.

**Faltantes para la próxima sesión:**
1. ~~Puerta trasera `root` en `auth_api.py`~~ — **resuelto Sesión 79**, ver abajo.
2. Decidir: acceso a `/tracker/credentials` (¿admin-only o se mantiene para operadores?).
3. Guardar en un archivo protegido (fuera del repo, permisos 600) las credenciales legado
   extraídas de los backups pre-redacción de Sesión 76 — bloqueado por el clasificador de
   seguridad de la sesión de Claude Code; Juan Pablo debe crear el archivo manualmente o
   ajustar el permiso de Bash.
4. Rotación de las 2 credenciales expuestas (dominio de red, usuario panel) — pendiente desde
   Sesión 76 (Juan Pablo dijo que esto entra en su próxima auditoría de seguridad propia).
5. ~~Tarea pendiente 2/3~~ — **resuelto Sesión 80**, ver abajo (opciones 1, 3 y 4 desplegadas).
6. Decidir qué hacer con el código dormido restante (no movido esta vez).

## Sesión 78 (27 ago 2026) — auditoría completa + verificación funcional de cada módulo, 2 bugs reales

Juan Pablo pidió una auditoría profesional completa (código + ciberseguridad) de `network_monitor`
y `shomer-agent` antes de enviar los 3 labs (205/243/245) a Bogotá, y además verificar en vivo
(no solo leyendo código) que cada módulo de Shomer funcionara: Guardian, Hunter, Tracker,
Protector, Inframonitor, NOC, Incidents, Audit, Reports, Technician, Topología y el bot.

- **Bug real encontrado en vivo — `doc_rate_pct` de Technician mostraba 2100%**
  (`app/api/shomer_technician.py`, commit `2c0178d`): faltaba el tope superior. Fix: `min(100,
  ...)`. Verificado en vivo contra un técnico real.
- **Bug real recurrente en producción — `pattern_analysis` perdía hallazgos por JSON truncado**
  (`core/pattern_analysis.py`, shomer-agent, commit `f9ae49b`): pasaba ~4 veces/24h.
  `_salvage_truncated_json_array()` nuevo rescata los objetos completos de un array truncado por
  corte de tokens del LLM, en vez de descartar el lote entero.

## Sesión 79 (28-29 ago 2026) — puerta trasera de root eliminada, labs a estado de fábrica, acceso de Mauricio

- **🔴 Puerta trasera de `root` eliminada** (`app/api/auth_api.py`, `_ensure_users_table()`, commit
  `8835b55`): antes reinsertaba la cuenta `root` de fábrica en cada arranque aunque un admin la
  hubiera borrado a propósito (`INSERT OR IGNORE` incondicional). Ahora solo crea `root` si la
  tabla de usuarios está genuinamente vacía. Probado contra copia de la BD (root borrado se queda
  borrado). Desplegado en los 4 servidores.
- **Bug real — `/agregar` de Telegram crasheaba en silencio con puerto no numérico** (`core/bot.py`,
  `cmd_agregar`): faltaba validar `args[3]` antes de `int()`; el error solo quedaba en logs, sin
  respuesta al usuario. Ahora responde con el error claro antes de intentar convertir. (Quedó sin
  commitear hasta el 2 sep, ver Sesión 80.)
- **Los 3 labs se resetearon a estado de fábrica real** (no demo con datos de Ópera) porque van a
  instalarse en clientes nuevos, no a usarse como vitrina comercial — se limpiaron
  `network_monitor.db`/`inventory.db` (tablas específicas del sitio) y `nodos_gl.json`, sin tocar
  netplan. Verificado con login `root`/`shomer2026` devolviendo `/setup` en los 3.
- **Acceso remoto de Mauricio (USB Ingeniería) a Ópera real** vía Tailscale — 2 problemas de
  conectividad reales resueltos: IP de Tailscale distinta vista desde el tailnet compartido
  (no hay arreglo de código, solo diagnóstico), y "Invalid host header" de nginx/FastAPI — se fijó
  `proxy_set_header Host "shomer-hotelopera";` en `/etc/nginx/sites-enabled/network-monitor` en
  vez de tocar el archivo de entorno protegido (`/etc/shomer/shomer-runtime.env`, fuera del
  alcance de las herramientas de esta sesión).
- **Pendiente sin resolver de esta sesión:** upgrades de dependencias con CVE conocido
  (`pip-audit` en ambos repos, ~14-20 paquetes con versión atrasada) — documentado, no aplicado;
  necesita ventana de pruebas completa antes del envío a Bogotá.

## Sesión 80 (2-3 sep 2026) — Telegram separado por hotel + Tarea pendiente 2 (opciones 1, 3, 4) + resúmenes

- **Cada hotel/cliente pasa a tener su propio bot y grupo de Telegram, nunca compartido.** Al
  auditar se encontró que shomer243 y shomer245 usaban el bot de shomer205 (clonado por
  `fleet_sync.sh` sin regenerar) y los 4 sitios compartían el chat personal de Juan Pablo. Se
  crearon 3 bots nuevos vía BotFather y 4 grupos separados (Ópera con Mauricio incluido, 205,
  243, 245), verificados con mensaje de prueba en cada uno. Detalle en memoria del asistente
  (`project_shomer_telegram_por_hotel`), no en este archivo (contiene tokens).
- **Tarea pendiente 3 (checkpoint) cerrada:** `reporte_alertas_semanal.py --days 19` + revisión de
  `eventos_filtrados` en ambas BDs — volumen sano, nada suprimido incorrectamente. Detalle en
  `PENDIENTES_LAB.md`.
- **Tarea pendiente 2, opciones 1, 3 y 4 implementadas** en `core/monitor.py` (shomer-agent),
  commits `0f7fb28` y `c9e7e1e`, desplegadas en Ópera + los 3 labs:
  - Opción 1: reinicio automático de Guardian exitoso ya no interrumpe (solo si sigue caído a los
    3 min).
  - Opción 3: patrón crónico (5+ ocurrencias en `pattern_analysis`) deja de interrumpir en tiempo
    real (antes solo acortaba el mensaje).
  - Opción 4: criticidad de negocio por `infra_devices.device_type` (`pos`, `router`, `server`,
    `controller`, `switch` = inmediato; `printer` no-POS y `camera` = diferido) — configurable con
    `INFRA_CRITICAL_DEVICE_TYPES`. Solo aplica a Inframonitor (Guardian/APs no tienen subtipo).
  - Opción 2 descartada (redundante con 3+4+6, riesgo de contradecir la 4). Opciones 5 y 6 sin
    cambios (ya correctas).
  - Todo lo suprimido en las tres queda en `eventos_filtrados` con `motivo` distinto por causa
    (`auto_reboot_pendiente`/`auto_reboot_exitoso`, `patron_cronico`, `no_critico`,
    `recuperacion_no_avisada`) — nada se pierde, todo auditable.
- **Bug encontrado al probar en vivo — el recordatorio "Equipo sigue caído" de Inframonitor
  (`INFRA_STALE_REMINDER_MINS`, cada 2h) es un mecanismo APARTE del aviso inicial y no respetaba
  patrón crónico** (Bixolon .243, ya diagnosticado con 10 ocurrencias, generó 3 recordatorios en
  una noche). Fix (`core/monitor.py`, commit `bf4620f`): aplica el mismo filtro `_chronic` antes
  de mandar el recordatorio.
- **Pregunta real de Juan Pablo tras ver esto: si ya no avisa, ¿cómo se entera el técnico?**
  Verificado que el resumen de las 07:00 (`summary_text()`) YA lista por nombre cada equipo Infra
  actualmente caído (hasta 8, con "…y N más"), independiente de si el aviso en tiempo real se
  suprimió — no era un hueco nuevo, ya existía. Confirmado con Bixolon .243 real en el resumen.
- **Resumen de Hunter (IPs bloqueadas en 24h) agregado al resumen de las 07:00**
  (`core/shomer_api.py`, commit `c951cb4`): antes solo mostraba el total histórico de IPs
  contenidas activas, ahora también cuántas se bloquearon en las últimas 24h, con motivo
  (`alert_signature`) y origen (`blocked_by`: wazuh/auto/manual).
- **Reconciliación IP-por-MAC ahora queda registrada, y el resumen de las 07:00 siempre dice algo
  al respecto** (antes: `reconcile_once()` en `app/api/shomer_mac_reconcile.py` solo mandaba un
  `logger.warning()` que se perdía; ahora también inserta en `mac_reconcile_log`, tabla nueva en
  `network_monitor.db`). El resumen matutino (`core/shomer_api.py`) muestra los cambios de las
  últimas 24h, o "ninguno" explícito si no hubo — pedido de Juan Pablo para que el técnico sepa
  que el sistema sí revisó, no que se le olvidó.
- **Resuelto en la misma sesión:** se agregó `PATCH /infra/devices/{id}` (nombre/tipo/ubicación,
  valida `device_type` contra `DEVICE_ICONS`) + botón "Editar" en `inframonitor.html`
  (`prompt()` simple, no modal) — commit `7af80fb`. Ya no depende de editar la BD a mano para
  corregir o marcar un equipo crítico (opción 4).
- Las 6 opciones de la Tarea pendiente 2 en sí: ninguna sin resolver. Queda solo observar unos
  días que el volumen de mensajes bajó (repetir el checklist de la Tarea pendiente 3).
- **Backup e inventario agregados al resumen matutino** (pedido Juan Pablo 3 sep 2026): antes no
  aparecían. `_run_global_b2_sync()`/`sync_cloud` (`app/api/backups.py`, commit `05653fd`) ahora
  guardan `protector.last_b2_sync_at` en `system_state` al terminar OK -- antes esa confirmación
  solo se mandaba por Telegram y se perdía entre los demás mensajes, no quedaba en ningún lado
  consultable. El resumen (`core/monitor.py`, shomer-agent) agrega: backup local por equipo +
  última subida a B2 (o "sin registro todavía" si nunca ha corrido desde el fix), y último
  inventario de Tracker (fecha + cantidad de equipos, desde `inventory_snapshots`). Pendiente de
  verificar con datos reales tras el próximo sync B2 programado (05:30).
- **`AP HAB 103` (.148) en mantenimiento — verificado que SÍ funciona:** Juan Pablo notó que no
  se reinicia solo y sospechó que era por mantenimiento. Confirmado leyendo el código exacto
  (`shomer_guardian_nodes.py`, función de heartbeat): revisa `node_maintenance:{ip}` en Redis
  antes de intentar el reinicio automático — funciona como debe. El resumen ahora lo etiqueta
  explícito ("EN MANTENIMIENTO, sin auto-reboot") en vez de mostrar solo "offline" sin contexto.
- **`NIC eno1 RX dropped` — descartado el buffer chico como causa, sigue sin resolver.**
  Confirmado que NO es cable/puerto físico: `rx_errors`/`rx_missed_errors` llevan horas sin
  subir, enlace 1000Mb/s full-duplex sano — la nota vieja de "priorizar cable/puerto switch del
  servidor" era una suposición equivocada. Se probó subir el buffer RX de 256 a 4096
  (`ethtool -G eno1 rx 4096` + servicio systemd `eno1-ring-buffer.service`, queda aplicado y
  persiste tras reinicio) pero **medido antes/después: 5.23 vs 5.22 paquetes/seg — sin cambio
  real**, no era el cuello de botella. `eno1` solo tiene **una cola de recepción** (`ethtool -l`
  no soportado, un solo IRQ en `/proc/interrupts`) — un solo núcleo procesa todo su tráfico, lo
  que sugiere el límite real está ahí, no en el tamaño del buffer. Pendiente de investigar más a
  fondo; prioridad baja — no está empeorando y Guardian ya filtra bien los blips resultantes
  (13/24h).
- **Limpieza de comentarios editoriales en reportes reales:** se encontraron y quitaron 3
  frases del asistente coladas en mensajes que ve el equipo ("nunca se liberan solas", una
  explicación de más en el bloque de MAC-reconcile, instrucciones de `ethtool` en el mensaje de
  NIC). La línea de Hunter ahora trae la fecha de la IP bloqueada más antigua en vez de un
  número sin contexto temporal.
- **Bot de Telegram — 3 mejoras tras revisar su estado:** se quitaron 21 alias legacy
  (`shomer_*`/`guardian_*`/`hunter_*`/`infra_*`/`instalar_*`) que duplicaban comandos sin
  aportar nada; `/revertir` ahora también deshace modo mantenimiento y cambios de tipo de
  equipo (antes solo bloqueos/desbloqueos y agregar/quitar equipo); comando nuevo
  `/criticidad <ip> [tipo]` para ver/cambiar la criticidad de negocio de un equipo Infra desde
  Telegram (antes solo desde el panel).
- **Bot de Telegram — UX más fácil de usar sin memorizar comandos:** botones "Ver detalle" en
  `/equipos`/`/infra` para cada equipo con problema (sin copiar IP a mano); comando `/menu` con
  botones por categoría; teclado fijo de accesos rápidos (Salud/Equipos/Alertas/Menú) que
  aparece tras el primer saludo; `/start` nuevo (no existía — alguien nuevo no recibía nada al
  tocar "Iniciar"); texto libre reforzado como primera opción en `/ayuda`, antes que la lista de
  comandos. Todo en shomer-agent `core/bot.py`, versión 1.1.8.

---
# Parte A — Estado del sistema (realidad cotidiana)

## A.1 Servicios que debe tener el appliance

Si alguno falta, el panel puede abrir igual pero fallan módulos.

| Servicio systemd | Puerto / rol |
|------------------|----------------|
| `shomer-guardian.service` | **8000** — Core: panel proxy, Guardian, Hunter |
| `shomer-tools.service` | **8001** — Tracker, Protector (solo localhost tras hardening típico) |
| `nginx` | **80** redirect → **8443** HTTPS hacia backend |
| `shomer-health-watchdog.timer` | Reintenta 8000/8001 si mueren |
| `shomer-inframonitor-poller.service` | Poller ICMP/SNMP independiente de uvicorn. Arranca con el sistema, sobrevive reinicios de guardian. Si está activo, guardian omite el poller embebido. Instalar: ver §AS.3. |
| Opcionales cliente | `suricata`, stack Wazuh, `redis-server`, `lldpd`, etc. según alcance |
| `shomer-monitor.service` | Script de monitoreo de infraestructura (`monitor.py`). Instalar: `sudo cp /opt/network_monitor/etc/shomer-monitor.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now shomer-monitor`. Requiere Redis en 127.0.0.1:6379 y llave SSH `~/.ssh/id_rsa_shomer`. |

**Comprobación rápida:**  
`systemctl is-active shomer-guardian shomer-tools nginx shomer-health-watchdog.timer shomer-inframonitor-poller`

## A.2 Qué está bien probado en laboratorio (mayo 2026)

Encaje registro abril 2026: **35** ✅ de **52** casos; mayo 2026 suma Protector backups físicos confirmados (ver abajo).

| Área | ¿Qué está cubierto en lab `.205`? |
|------|-----------------------------------|
| **Smoke / sesión** | Login, nonce arranque, cuatro módulos visibles |
| **Pipeline Hunter** | `GET /setup/status`, `GET /remedies/pipeline/health` operativos (Suricata+Wazuh según ese entorno) |
| **Guardian** | Dashboard, Telegram prueba, descubrir/promover nodo `.210`, **reboot manual y automático** con failsafe WAN, Telegram en caídas y recuperaciones |
| **Failsafe extendido** | Estados `offline` / `no-internet` / `degraded` / `online`, anti-ráfagas y cooldown Telegram 🟡 (ver Parte F) |
| **Tracker F2** | `/inventory/` carga, quick/deep scan, campos y export cuando se cerró ese bloque en doc |
| **Hunter F3** | `/security/` alertas, bloqueo manual, políticas `auto_block_*`, Telegram asociado a prueba (28–29/04/2026 en doc de pruebas). **Sesión 23 (10/05/2026):** bugs corregidos, cadena Wazuh→API→OpenWrt `.206`→Telegram verificada end-to-end en hardware real. Ver Parte E §E.1. |
| **Protector — backups físicos** | Backup SSH Linux `.203` (Kali) ✅ · SSH macOS `.90` (`/Users/shomer/backups`) ✅ · SMB Windows `.50` (share `backups`) ✅ · B2 sync confirmado (`lab-usb-shomer`) ✅ · Scheduler dispara en hora local MT ✅ |
| **Bot Telegram (agente)** | Docker `shomer-agent` activo en `.205`. **Sin `/start`** — entrada `/consultas` · `/ayuda` · texto libre. **~25 comandos slash** + aliases por módulo + callbacks (reboot, guardar solución, bloqueo). **22 tools** function calling. **Chat interactivo:** OpenAI `gpt-4o-mini`. **Monitores:** Groq Llama 3.3-70b — **26 tareas** (30 líneas en `/salud monitores`, incl. 5 Infra). Alertas formato **una línea**; triage off por defecto (`BOT_TRIAGE_ENABLED=0`). **`knowledge.db`:** guardar solución post-reboot/desbloqueo/recuperación; antecedente en alertas (`📋`). `/salud` solo texto (sin botones repair). Menú ⋮ Telegram: 16 comandos. Rate-limit 5s/usuario. ✅ Sesión 52 (jun 2026) UX unificado. |
| **Inframonitor SNMP** | `/infra` monitorea switches/routers/firewalls/servidores via ICMP + TCP + **SNMP v2c**. Poll cada 30s paralelo. Datos: modelo, uptime, hostname, estado puertos, velocidad, tráfico Rx/Tx Mbps (delta entre polls), errores. Modal UI por equipo. Badge `SNMP ✓/✗`. ✅ Sesión 38 (27/05/2026). Ver §Z. |

## A.0 Entorno de laboratorio — estado permanente (no preguntar)

**Todo el hardware físico está conectado y disponible en todo momento.** Appliance `.205`, APs EAP `.210`, switches, espejo SPAN. B2 Backblaze configurado y operativo. WireGuard VPN activo en lab. Cualquier prueba física, de aplicación o en la nube se puede ejecutar sin preguntar al desarrollador.

---

## A.3 Estado pendientes lab — actualizado 14 mayo 2026

*Verificado contra código real en Sesión 29.*

| # | Ítem | Estado |
|---|------|--------|
| F0.2 | `GET /backups/health` autenticado | ✅ Resuelto — ruta existe, proxy OK, probado con sesión admin |
| F4 | Protector bloque completo (11 casos) | ✅ Resuelto — panel `/backups`, backup SSH/SMB/Mac, `POST /backups/b2/test`, sync, restore, descarga ZIP verificados Sesión 29 |
| F5 | No funcionales — CPU/RAM/disco bajo carga | **PENDIENTE campo** — requiere prueba coordinada scan+backup en hardware |
| — | Checklist despliegue nube externo | **PENDIENTE campo** — 5 criterios sin ejecutar en bloque |

**Práctica habitual campo (Hunter en sitio nuevo):**
- Validar SPAN hasta NIC espejo, SID 9009001 ante ICMP real, cadena Wazuh→API→bloque con manager real.
- **Lista B Hunter:** B4 obligatorio; B1, B3, B5 condicionados a tipo cliente.

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
| Core | **8000** | `app.api.main:app` | Auth, proxies `shomer_proxies` hacia tracker/backups en 8001, Guardian, Hunter |
| Tools | **8001** | `app.api.main_tools:app` | Tracker inventario (`inventory.db`), Protector Restic+B2 |

`system_state` en `network_monitor.db` guarda prefijos `base.* guardian.* hunter.* tracker.* protector.* modules.enabled`.

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

## E.1 Bugs corregidos Hunter — Sesión 23 (10 mayo 2026)

Todos los cambios en `app/api/casador_blocking.py` y `app/api/casador_support_firewall.py` / `casador_support_state.py`.

### 1. Excepción silenciada en bloqueo SSH (**CRÍTICO** — resuelto)

**Antes:** `if not ok: pass` — si SSH fallaba, la BD registraba la IP como bloqueada igualmente (`success: True`). Panel mostraba “bloqueado” pero la regla iptables **no existía** en el firewall.

**Después:** si el firewall está configurado y SSH falla → retorna `success: false`, **no inserta en BD**, log `ERROR` con detalle. Si el firewall no está configurado (`hunter.firewall_ip` vacío) → sigue insertando en BD en modo monitoreo (sin bloqueo real) con `WARNING` en log.

### 2. Validación de IP / inyección de comando SSH (**SEGURIDAD** — resuelto)

`POST /remedies/block` y `POST /remedies/unblock` ahora validan el campo `ip` con `ipaddress.ip_address()` antes de cualquier operación. Una IP malformada (`”1.2.3.4; rm -rf /”`) retorna `HTTP 400` sin llegar a SSH.

### 3. Circuit breaker no aplicaba a desbloqueo

`_mikrotik_unblock` ahora respeta el circuito abierto igual que `_mikrotik_block`. Si el firewall está unreachable, el desbloqueo retorna `success: False` con mensaje explícito (la IP permanece en BD como bloqueada hasta que el circuito se restaure).

### 4. Puerto SSH configurable (`hunter.firewall_port`)

El puerto SSH al firewall era hardcodeado en 22. Ahora se lee de `hunter.firewall_port` en `system_state` (default 22). Para cambiarlo:
```sql
UPDATE system_state SET value='2222' WHERE key='hunter.firewall_port';
```
O desde el panel si se agrega el campo al formulario Hunter.

## E.2 Estado verificado laboratorio firewall .206 (10 mayo 2026)

| Verificación | Resultado |
|---|---|
| Ping `.206` | ✅ 0 % pérdidas, ~1 ms |
| SO `.206` | ✅ OpenWrt Linux 5.15.167 (MIPS) |
| iptables `.206` | ✅ v1.8.8 (nf_tables) |
| asyncssh credenciales BD (ver `hunter.firewall_user` / `hunter.firewall_pass` en BD) | ✅ conecta y ejecuta |
| `iptables -I FORWARD -s 198.51.100.1 -j DROP` | ✅ regla aplicada, verificada con `iptables -L` |
| Desbloqueo `iptables -D …` | ✅ regla eliminada correctamente |
| Cadena Wazuh script → API → `.206` → Telegram | ✅ `telegram_sent: true` en respuesta |

**Prueba de validación Wazuh** ejecutada en lab:
```bash
echo '{“data”:{“src_ip”:”5.5.5.5”,”alert”:{“signature”:”ET SCAN test”,”signature_id”:9009001,”severity”:1}},”parameters”:{“message”:”test”}}' \
  | SHOMER_WAZUH_INTEGRATION_KEY=”Usbing08*@2026” \
    SHOMER_API_URL=”http://127.0.0.1:8000/remedies/block” \
    ./venv/bin/python tools/cazador/wazuh_shomer_block.py
# → {“success”:true,”firewall_ok”:true,”telegram_sent”:true}
```

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

## E.4 Pendientes Hunter (campo y producto)

**Resueltos Sesión 24 (10 mayo 2026):** P5 ✅ P6 ✅ P7 ✅ P8 ✅ P10 ✅

| # | Qué | Prioridad |
|---|-----|-----------|
| P1 | **Validar espejo SPAN real en sitio nuevo** — `tcpdump -i enp4s0 -c 20` antes de confiar alertas | Campo / obligatorio |
| P2 | **Active-response Wazuh real** — `ossec.conf` + `local_rules.xml` nunca ejecutado en cliente con manager real | Campo |
| P3 | **SID 9009001 en tráfico real espejo hotel** — lab OK, pero NIC espejo hotel diferente | Campo |
| P4 | **`hunter.auto_block_*` por sitio** — revalidar subnets y excepciones en cada nueva LAN | Campo / obligatorio |
| P5 | ~~Export CSV histórico bloqueos~~ — ✅ `GET /remedies/history/csv` (descarga directa) | ✅ Sesión 24 |
| P6 | ~~`hunter.firewall_port` en formulario UI~~ — ✅ campo Puerto SSH + Timeout SSH en panel Firewall | ✅ Sesión 24 |
| P7 | ~~`hunter.firewall_timeout` hardcodeado~~ — ✅ `hunter.firewall_timeout` en BD, `_get_firewall_creds()` lo lee, `run_timeout = connect_timeout - 2` | ✅ Sesión 24 |
| P8 | ~~Columna `firewall_blocked`~~ — ✅ migración automática `ALTER TABLE`, INSERT guarda `1` si SSH OK, `0` si solo-BD | ✅ Sesión 24 |
| P9 | **Retry automático al reabrir CB** — ✅ **CERRADO como diseño intencional**: sync manual disponible (`POST /remedies/firewall/sync`, botón en panel). Para hoteles de hasta ~100 hab. el flujo de dos pasos (Reset CB → Sincronizar) es suficiente; muchos clientes Colombia ni firewall tienen. Hacer el reset automático complicaría UX (botón lento) sin beneficio real en ese segmento. | ✅ Cerrado — decisión Juan Pablo |
| P10 | ~~Vista de bloqueos históricos~~ — ✅ `GET /remedies/history`, sección colapsable con tabla + CSV en panel Hunter | ✅ Sesión 24 |
| P11 | **Clave Wazuh con HMAC** — ~~prioridad media~~ → **DESCARTADO**: Wazuh y Shomer corren en el mismo servidor; la llamada va a `http://127.0.0.1:8000` (loopback, nunca sale al exterior). El riesgo real es exposición del puerto 8000 en UFW — ya está cubierto (solo localhost). No aplicar HMAC si no hay justificación arquitectural. | ✅ No aplica (mismo servidor) |
| P12 | **Flashear 2 MikroTik hEX S (RB760iGS) a OpenWrt** — para conectarlos como firewalls Hunter igual que el `.206`. Ver procedimiento completo abajo §E.5. | 🔴 **PRÓXIMA SESIÓN** |

## E.5 Pendiente — Flashear 2 MikroTik RB760iGS a OpenWrt (próxima sesión)

El `.206` ya corre OpenWrt 23.05.5 y está integrado con Hunter. Hay 2 unidades iguales (RB760iGS) con RouterOS que deben flashearse.

### Archivos a descargar (antes de empezar)

| Archivo | Versión | Uso |
|---|---|---|
| `openwrt-23.05.0-rc3-ramips-mt7621-mikrotik_routerboard-760igs-initramfs-kernel.bin` | **rc3 obligatorio** | Boot en RAM vía TFTP — las versiones finales no netbootean en este modelo |
| `openwrt-23.05.5-ramips-mt7621-mikrotik_routerboard-760igs-squashfs-sysupgrade.bin` | 23.05.5 estable | Flash permanente tras el boot en RAM |

### Procedimiento

**Paso 1 — Verificar RouterOS v6** (Winbox → `/system routerboard print`). Si tiene v7 bajar a 6.49.x primero.

**Paso 2 — Configurar netboot en el hEX** (web `192.168.88.1` o Winbox):
- System → Routerboard → Settings → Boot device: `try ethernet once then NAND`
- Boot protocol: `DHCP` · Force Backup Booter: ✅ · Shutdown (no reboot)

**Paso 3 — Servidor TFTP en .205** (cable directo .205 → Ether1 del hEX):
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
shomer*.py routers panel config guardian proxies setup
casador_blocking casador_intel casador_rules + casador_support_*
inventory_*.py  (después refactor Mayo 2026 — activos sólo trackers)
app/scripts/tracker/*       motor escaneos nmap wmi snmp
app/scripts/alerts*.py      telegram avisos
```

Tests humo habitual:  
`PYTHONPATH=/opt/network_monitor ./venv/bin/python -m unittest tests.test_smoke_api -v`

---

# Parte L — Product backlog abierto conocido tras lab abril 2026

**No cuenta cosas marcadas ✅ en plan pruebas** — integra mejoras conocidas producto código / historia antigua manifiesto:

| Ítem código / experiencia cliente | Estado abreviatura |
|-----------------------------------|-------------------|
| GL.iNet credenciales almacén panel tabla `devices` vs llave sólo SSH | ✅ parcial abril (ver fix reboot credenciales) — mejorar ergonomía captura nueva |
| Paquete ZIP masivo todas etiquetas QR inventario tabla | ✅ completado |
| Columna QR dentro Excel cliente global opcional backlog | ✅ completado |
| Mitigation flows UI confirmación granular mas allá sólo firewall IP blacklist | PLAN |
| Soporte configuración desde panel hunter firewalls modelo “4 WAN ports” algunos mikrotiks avanzados | PLAN |
| Pruebas Windows/mac Protector escritorio hotel real repetir cada vez cliente real distinta versión antivirus | ✅ completado |
| Inventario parametrizaciones NMAP intrusivas (requiere contrato DPIA cliente) — evaluacion auditor futura | PLAN |
| **Panel Estado del Sistema** — rediseño completo ✅ Sesión 25 (ver §N) | ✅ 11/05/2026 |
| **Pruebas Hunter campo (P1–P4)** — SPAN real, Wazuh manager cliente, SID hotel, auto_block por sitio | PENDIENTE campo |
| **Protector B2 restore desde panel** — listar snapshots B2, restaurar al Shomer, descarga ZIP al PC técnico ✅ Sesión 26 | ✅ 11/05/2026 |
| **Descarga ZIP restore B2 (panel web)** — endpoint GET `/backups/restore/{id}/download`. **Bug corregido Sesión 29:** proxy `_proxy_backups` hacía `r.json()` sobre respuesta binaria → 502. Fix: endpoint propio con `StreamingResponse` en `shomer_proxies.py`. Flujo completo verificado: sync→restore→ZIP→descarga. | ✅ 14/05/2026 |
| **Descarga backup bot Telegram** — REMOVIDO por falla de seguridad. El tarball contiene credenciales, DBs y tokens. Cualquier técnico con acceso al bot podría exfiltrarlo. | ❌ Eliminado Sesión 28 |
| **Toggle schedule por equipo** — botón Pausar/Activar auto en tabla snapshots locales ✅ Sesión 26 | ✅ 11/05/2026 |
| **Modelo de roles técnico vs admin** — análisis completado; operator = acceso completo panel excepto gestión de usuarios ✅ Sesión 26 | ✅ 11/05/2026 |

*B2 cuenta operativa empresa USB — credencial en tabla `protector.b2_*` según proyecto — sync UI Protector.*

---

# Parte N — Agente Shomer (shomer-agent)

Componente paralelo que corre en Docker **completamente separado** de `/opt/network_monitor/`. No modifica código ni base de datos de Shomer — solo lee sus APIs y BD como cliente.

## N.1 Ubicación y archivos

```
/storage/shomer-agent/
├── core/
│   ├── bot.py              ← Bot Telegram + handlers de comandos
│   ├── monitor.py          ← 20 monitores automáticos en background
│   ├── groq_helper.py      ← Groq — monitores, explain(), fallback chat
│   ├── openai_helper.py    ← OpenAI gpt-4o-mini — chat interactivo + tools
│   ├── llm_router.py       ← Router proveedor LLM (OpenAI / Groq)
│   ├── tools.py            ← 15 tool definitions (function calling compartido)
│   ├── memory.py           ← Memoria SQLite por usuario (conversations.db)
│   ├── maintenance.py      ← Modo mantenimiento global + rate-limit por usuario
│   ├── download_server.py  ← HTTP server puerto 8082 — links de descarga temporales
│   ├── access.py           ← Niveles de acceso developer/tecnico/none
│   ├── device_manager.py   ← CRUD de equipos en devices.json
│   ├── shomer_api.py       ← Cliente APIs Shomer :8000/:8001
│   ├── repair.py           ← Reinicio servicios via SSH
│   ├── backup_manager.py   ← Backups tarball + B2
│   ├── changelog.py        ← SQLite log de cambios y rollback
│   ├── identity.py         ← SITE_NAME del .env
│   └── fmt.py              ← Helpers de formato Telegram
├── drivers/
│   ├── base.py             ← Clase base DeviceDriver (FULL/API/PING)
│   ├── linux_generic.py    ← GL.iNet, OpenWrt, DD-WRT, RPi, genérico
│   ├── mikrotik.py         ← MikroTik RouterOS (comandos /system + logs firewall)
│   ├── tplink_eap.py       ← TP-Link EAP/Omada — SNMP v2c
│   ├── ubiquiti.py         ← Ubiquiti UniFi/EdgeRouter — SSH syswrapper
│   ├── aruba.py            ← ArubaOS Instant/Controller — show clients
│   ├── cisco.py            ← Cisco SG/SF switches IOS
│   ├── ssh_helper.py       ← SSH compartido con algoritmos legacy
│   └── detector.py         ← Auto-detección por banner SSH + hint explícito
├── data/                   ← Volumen montado — persiste entre rebuilds
│   ├── devices.json        ← Inventario equipos del agente
│   ├── conversations.db    ← Memoria SQLite por usuario (Sesión 27)
│   ├── dev_sessions.json   ← Sesiones developer persistentes
│   ├── backups/            ← Tarballs de backup (rotación 2 copias)
│   └── downloads/          ← Archivos temporales download server (auto-limpieza 30 min)
├── BEHAVIOR.md             ← Reglas de comportamiento LLM (montado :ro en container)
├── TECNICO_OPERACION.md    ← Guía operacional para técnicos (montado :ro)
├── Dockerfile
├── docker-compose.yml
└── .env                    ← Tokens y credenciales (chmod 600, NO al repo)
```

## N.2 Servicios y recursos

| Componente | Detalle |
|-----------|---------|
| Servicio systemd | `shomer-agent.service` — arranca con el sistema |
| Docker container | `shomer-agent` — `network_mode: host` (acceso directo a LAN) |
| RAM usada | ~120-150 MB |
| Disco imagen | ~250 MB |
| Datos persistentes | `/storage/shomer-agent/data/devices.json` |
| LLM chat interactivo | OpenAI `gpt-4o-mini` (pago, ~centavos/mes) vía `core/openai_helper.py` |
| LLM monitores / explain | Groq Llama 3.3-70b (free tier: 14,400 req/día) vía `core/groq_helper.py` |
| Router | `core/llm_router.py` — selecciona proveedor; fallback Groq |
| Bot Telegram | **Mismo bot y chat que Guardian** — Guardian solo envía, agente solo recibe |

## N.3 Variables de entorno (.env)

```
TELEGRAM_BOT_TOKEN=       # token único por cliente (BotFather)
TELEGRAM_CHAT_ID=         # chat del técnico del cliente
GROQ_API_KEY=             # console.groq.com — monitores + fallback (gratis)
AGENT_DEVELOPER_ID=       # Telegram user ID del desarrollador
AGENT_DEVELOPER_CHAT_ID=  # Chat personal del desarrollador (alertas críticas)

# Chat interactivo del técnico (texto libre con tools)
LLM_PROVIDER_INTERACTIVE=openai   # openai | groq (default groq si vacío)
OPENAI_API_KEY=                   # platform.openai.com/api-keys
OPENAI_MODEL=gpt-4o-mini
# Hard caps servidor (~$0.05–0.15/mes/Shomer además del límite web)
OPENAI_LIMIT_PER_MESSAGE=2000
OPENAI_LIMIT_PER_USER_DAILY=8000
OPENAI_LIMIT_DAILY=12000
# Lab dual-NIC (.205): IP WiFi si aplica; vacío en sitios con una sola ruta
OPENAI_BIND_IP=

# Umbrales globales (todos los proveedores) — modo mantenimiento IA
TOKEN_WARN_DAILY=80000
TOKEN_LIMIT_DAILY=120000

SHOMER_URL=http://127.0.0.1:8000
SHOMER_USER=admin
SHOMER_PASS=              # contraseña del panel Shomer
SHOMER_INTEGRATION_KEY=   # solo si Wazuh (normalmente vacío)
DEVICES_FILE=/app/data/devices.json
BACKUP_MAX_HOURS=26
SITE_NAME=                # nombre del sitio en mensajes del bot
```

**Límite de gasto OpenAI (obligatorio en campo):** Settings → Limits → monthly budget (ej. $5). El prepago de créditos es opcional; el límite mensual en la web **sí corta** la API al llegar.

## N.4 Niveles de acceso

| Nivel | Quién | Cómo se identifica |
|-------|-------|--------------------|
| `developer` | Desarrollador USB Ingeniería | `AGENT_DEVELOPER_ID` — funciona desde cualquier chat o DM directo |
| `tecnico` | Técnico del cliente | `TELEGRAM_CHAT_ID` — solo desde el chat configurado |
| `none` | Cualquier otro | Ignorado silenciosamente |

El bot tiene **un nombre por cliente** (ej. `Shomer Hotel Calle 26`) — se configura en BotFather. El developer puede hacer DM a cualquier bot cliente y tendrá nivel completo.

## N.5 Comandos Telegram

**Sin `/start`** (eliminado jun 2026). Entrada: `/consultas`, `/ayuda` o texto libre. Lista canónica en código: `_ayuda_text()` + `set_my_commands` en `core/bot.py`.

| Comando | Técnico | Developer | Acción |
|---------|---------|-----------|--------|
| `/consultas` | ✅ | ✅ | Ejemplos de texto libre por módulo |
| `/ayuda` | ✅ | ✅ | Lista completa comandos + 30 monitores |
| `/salud` | ✅ | ✅ | Estado servidor (solo texto: CPU, RAM, disco, servicios, Guardian, Infra, Hunter, WAN) |
| `/salud monitores` | ✅ | ✅ | Estado de cada monitor automático |
| `/salud resumen` | ✅ | ✅ | Reporte del día con IA |
| `/equipos` | ✅ | ✅ | Nodos Guardian + equipos agente |
| `/infra` | ✅ | ✅ | Lista equipos Infra |
| `/infra <ip>` | ✅ | ✅ | Detalle conexión: ping, TCP, SNMP, impresora |
| `/puertos <ip>` | ✅ | ✅ | Puertos SNMP (switch/router/server) |
| `/diagnostico <ip>` | ✅ | ✅ | Ping + estado Guardian + fallos + uptime |
| `/diagnostico <ip> reparar` | ✅ | ✅ | Diagnóstico + remediación automática |
| `/reboot <ip>` | ✅ | ✅ | Reboot con confirmación (`/reiniciar`, `guardian_reiniciar`) |
| `/clientes <ip>` | ✅ | ✅ | Dispositivos WiFi conectados al AP |
| `/modo on\|off` | ✅ | ✅ | Mantenimiento Guardian (`/mantenimiento`) — **Telegram al activar/desactivar** (panel o bot) |
| `/seguro on\|off` | ✅ | ✅ | **Autobloqueo Hunter** — activar/desactivar (alias `/autobloqueo`); guía al chat al cambiar |
| `/liberar` | ✅ | ✅ | Ver IPs bloqueadas + botón liberar (o `/liberar IP`) |
| `/alertas` | ✅ | ✅ | Alertas Hunter + IPs bloqueadas |
| `/bloquear <ip>` | ✅ | ✅ | Bloquear IP manualmente |
| `/desbloquear <ip>` | ✅ | ✅ | Desbloquear IP (+ botón guardar falso positivo) |
| `/guardar <ip> <texto>` | ✅ | ✅ | Guardar solución en `knowledge.db` |
| `/historial` | ✅ | ✅ | Últimos cambios del bot |
| `/revertir <id>` | ✅ | ✅ | Deshacer bloqueo/desbloqueo |
| `/instalar` | ✅ | ✅ | Guía instalación (10 pasos) |
| `/verificar` | ✅ | ✅ | Checklist final instalación |
| `/usuario` | ✅ | ✅ | Crear usuario servicio `shomer` |
| `/agregar` | ✅ | ✅ | Registrar equipo en agente |
| `/eliminar <ip>` | ✅ | ✅ | Quitar equipo |
| `/nuevo` | ✅ | ✅ | Limpiar historial conversación IA |
| Texto libre | ✅ | ✅ | OpenAI (o Groq fallback) con **22 tools** — ver §V |

**Aliases compatibilidad:** `shomer_salud`, `guardian_*`, `hunter_*`, `infra_equipos`, `infra_puertos`, `instalar_*`, `diag`→`diagnostico`.

## N.6 Monitores automáticos (background)

| Monitor | Intervalo | Alerta a | Qué hace |
|---------|-----------|----------|---------|
| `watch_hunter` | 60s | Técnico | IP bloqueada → filtra por `blocked_at` (<10 min = nueva) → Groq explica |
| `watch_devices` | 2 min | Técnico + developer | Caída tras 3 fallos / recuperación |
| `daily_summary` | 07:00 AM | Técnico | Resumen diario |
| `watch_resources` | 3 min | Técnico + developer | CPU >80% o RAM >85% |
| `watch_backups` | Configurable | Técnico + developer | Sin backup en 26h |
| `watch_wan_outage` | 90s | Técnico + developer | WAN caída — repite cada 10 min con duración |
| `watch_services` | 2 min | Técnico + developer | Guardian/Tools/Nginx caídos + journal |
| `watch_disk` | 5 min | Técnico + developer | Disco >80% alerta / >85% limpia / >92% crítico |
| `watch_pipeline` | 3 min | Técnico + developer | OK→degradado = alerta siempre; semilla startup suprime falso positivo |
| `preventive_reboot` | 04:00 AM | Técnico + developer | Reinicia APs con uptime >30 días |
| `weekly_backup` | Dom 02:00 | Developer | Backup automático semanal |
| `watch_guardian_nodes` | 30s | Técnico + developer | Cambios estado Guardian + botón reboot inline |
| `auto_unblock` | 30 min | Developer | Desbloquea IPs Hunter tras X horas sin reincidencia |
| `watch_protector_retry` | Configurable | Developer | Reintentos backup Protector fallido |
| `watch_hunter_verify` | 60s | Developer | Verifica bloqueo efectivo + detecta IPs internas bloqueadas |
| `watch_docker` | 10 min | Developer | Reinicios del container shomer-agent |
| `watch_connectivity` | 5 min | Developer | Conectividad general del servidor |
| `watch_groq` | 15 min | Developer | Estado API Groq |
| `watch_security` | 5 min | Developer | Logs firewall Linux/OpenWrt — spikes DROP |
| `watch_mikrotik_security` | 5 min | Developer | Logs firewall MikroTik — spikes + flood |
| `watch_openai` | 15 min | Developer | Estado API OpenAI (chat interactivo) |
| `watch_network_audit` | 6 h | Técnico | Riesgos de red pendientes (auditoría nmap/parches) |
| `watch_protector_sample` | Configurable | Developer | Revisión muestral backups Protector |
| `watch_log_truncate` | Periódico | Developer | Trunca logs grandes del servidor |
| `watch_active_threats` | 10 min | Técnico | Estado IPs bloqueadas (sin resumen periódico — fix jun 2026; nuevos bloqueos: `watch_hunter`) |
| `watch_infra_equipment` | 60s* | Técnico | Infra — caídas y recuperaciones |
| `watch_infra_printer` | 60s* | Técnico | Infra — tóner y papel bajo |
| `watch_infra_service` | 60s* | Técnico | Infra — servicio TCP desconectado |
| `watch_infra_snmp` | 60s* | Técnico | Infra — puertos SNMP DOWN (si `INFRA_SNMP_PORT_ALERTS=1`) |
| `watch_infra_flap` | 60s* | Técnico | Infra — flapping cable/PoE |
| `ia_diagnostico` | bajo demanda | Técnico | IA — diagnóstico OpenAI AP degradando (no es loop; se dispara desde `_emit_guardian`) |

\* Intervalo del loop `watch_infra`: `WATCH_INFRA_INTERVAL_SEC` (default **60** en Ópera; mínimo 30). Los cinco sub-monitores Infra comparten ese tick.

**Total:** 26 tareas en `start_all()` — 30 entradas en `/salud monitores` (Infra = 5 ticks del loop `watch_infra`) + etiqueta `ia_diagnostico` en `MONITOR_LABELS` / `memoria_alertas`.

**Limpieza automática de disco** (sin autorización):
- Journal >7 días, logs Shomer >7 días, /tmp >1 día, cache APT
- A 85%: ejecuta y notifica cuánto liberó
- A 92%: ejecuta + pide autorización developer para Docker prune (desde `/salud`)

## N.7 Lógica WAN coordinada (3 niveles)

```
1. Todos los APs de un grupo offline → “Switch del piso X caído”
2. Múltiples grupos offline → ping 8.8.8.8 desde firewall sonda
   ├── Ping falla → “CAÍDA WAN — contactar ISP” (repite cada 10 min)
   └── Ping OK   → “Problema infraestructura interna”
3. Recuperación → confirmación a técnico y developer
```

Para el hotel piloto agregar equipos con campo `grupo`:
```
/agregar 192.168.X.10 AP-Piso1-A admin pass linux piso1
/agregar 192.168.X.20 AP-Piso2-A admin pass linux piso2
```

## N.8 Reparación — `/salud` y post-acción (jun 2026)

**`/salud` ya no muestra botones** — solo reporte de estado. Reparación manual vía:
- `/diagnostico <ip> reparar` — reboot nodo caído, limpieza disco, restart servicios según contexto
- Callbacks `repair:*` siguen registrados si algún mensaje antiguo conserva botones

**Guardar solución (`knowledge.db`):** tras reboot manual, desbloqueo Hunter, recuperación Guardian/Infra → botones `save_know:r|u|o:IP`. Antecedente aparece en alertas (`📋` vía `_kn()` en `monitor.py`).

SSH repair usa clave `/storage/shomer-agent/data/agent_restart_key`. Clave pública en `~/.ssh/authorized_keys` del host.

## N.9 Lógica multi-vendor

| Nivel | Capacidad | Equipos |
|-------|-----------|---------|
| `FULL` | Ping + SSH + reboot + clientes | MikroTik, Ubiquiti, GL.iNet, OpenWrt, TP-Link EAP, Cisco |
| `PING` | Solo ICMP | TP-Link Archer consumer, modems ISP |

`”no_reboot”: true` en `devices.json` → bloquea `/reiniciar` y reboot preventivo aunque tenga SSH. Usado en `.206` (Firewall-Hunter).

## N.10 Comandos operación

```bash
# Estado
sudo docker compose -f /storage/shomer-agent/docker-compose.yml ps
sudo docker compose -f /storage/shomer-agent/docker-compose.yml logs --tail=30

# Reiniciar
sudo systemctl restart shomer-agent.service

# Reconstruir tras cambios de código
cd /storage/shomer-agent && sudo docker compose down && sudo docker compose build && sudo docker compose up -d
```

## N.11 Módulos nuevos — Sesión 16 (7 mayo 2026)

| Módulo | Archivo | Función |
|--------|---------|---------|
| `identity.py` | `core/identity.py` | `SITE_NAME` del `.env` → cabecera en todos los mensajes |
| `changelog.py` | `core/changelog.py` | SQLite log de cambios, `log_change()`, `revert()` |
| `backup_manager.py` | `core/backup_manager.py` | Backup completo via SSH, rotación 2 copias, B2 opcional |

### Comandos nuevos

| Comando | Nivel | Función |
|---------|-------|---------|
| `/historial` | técnico + developer | Últimos 10 cambios registrados |
| `/revertir <id>` | developer | Deshace bloqueo, desbloqueo, add/remove device |
| `/backup` | developer | Backup manual inmediato |
| `/restaurar` | developer | Solo informativo — lista backups disponibles (fecha + MB). Sin botones de acción. Restaurar = SSH manual |

### Identidad por cliente

Cada instalación configura en `.env`:
```
SITE_NAME=Hotel XYZ
```
Todos los mensajes del bot y alertas del monitor incluyen el nombre del sitio.

### Backup semanal automático

- Domingos 02:00 → `weekly_backup` monitor en `monitor.py`
- Destino local: `/storage/shomer-agent/data/backups/` (= `/app/data/backups/` en container)
- Rotación: máximo 2 backups, borra el más antiguo
- B2 opcional: `BACKUP_B2_KEY_ID` + `BACKUP_B2_APP_KEY` + `BACKUP_B2_BUCKET_ID` en `.env`
- Archivos críticos incluidos: `network_monitor.db`, `inventory.db`, `shomer-runtime.env`, `devices.json`, nginx configs, systemd units, suricata rules

### Changelog y rollback

Acciones reversibles: `block ↔ unblock`, `add_device ↔ remove_device`.
Acciones no reversibles pero logueadas: `reboot`, `restart_*`, `disk_cleanup`, `restore`.

## N.12 Driver SNMP TP-Link EAP — Sesión 17 (8 mayo 2026)

### Por qué SNMP y no SSH

El usuario `admin` del firmware TP-Link EAP (EAP225, EAP610) tiene SSH habilitado pero sin permisos para ejecutar `ping`, `reboot`, `curl`, `wget` ni `nslookup`. El driver original basado en SSH quedó inútil para reboot y checks WAN. Solución: SNMP v2c.

### Configuración requerida en el equipo EAP

En el panel web de cada EAP: **Management → SNMP**

| Campo | Valor recomendado |
|-------|-------------------|
| SNMP habilitado | ✅ |
| Comunidad GET (lectura) | `shomer2026` (o la del cliente) |
| Comunidad SET (escritura) | distinta de la GET, ej. `shomer2026@` |
| IP permitida | Solo `IP_del_Shomer` — nunca wildcard |
| Versión | v2c |

⚠️ Nunca dejar la comunidad GET como `public` en producción.

### OIDs verificados en lab

| OID | Tipo | Dato |
|-----|------|------|
| `1.3.6.1.2.1.1.1.0` | GET | sysDescr — firmware/kernel |
| `1.3.6.1.2.1.1.3.0` | GET | sysUpTime |
| `1.3.6.1.2.1.1.5.0` | GET | sysName (hostname) |
| `1.3.6.1.2.1.4.22` | WALK | ipNetToMediaTable — IP + MAC de clientes conectados |
| `1.3.6.1.4.1.11863.10.1.2.1.0` | **SET i 1** | **Reboot** — verificado en EAP225 y EAP610 |

### Convención fields en devices.json para tplink_eap

```
user     = comunidad SNMP GET  (lectura)
password = comunidad SNMP SET  (escritura / reboot)
port     = ignorado (SNMP siempre UDP 161)
```

### Agregar un EAP al agente bot

```
/agregar 192.168.X.254 EAP225-Piso1 shomer2026 shomer2026@ tplink_eap
/agregar 192.168.X.253 EAP610-Piso2 shomer2026 shomer2026  tplink_eap
```

### Capacidades resultantes tras SNMP

| Función | Estado |
|---------|--------|
| ICMP monitor (vivo/caído) | ✅ Guardian + agente bot |
| Info firmware/uptime | ✅ SNMP GET |
| Lista clientes (IP + MAC) | ✅ SNMP WALK tabla ARP |
| **Reboot** | ✅ SNMP SET OID 11863.10.1.2.1.0 |
| Reboot automático Guardian failsafe | ✅ integrado — `reboot_method='snmp'` en BD |
| SSH WAN / DNS / HTTP checks Guardian | ❌ desactivar para nodos EAP |

### Guardian — configuración correcta para nodos EAP

En panel Guardian al agregar nodo EAP:
- ICMP: ✅ activar
- SSH ping WAN: ❌ desactivar
- DNS check: ❌ desactivar
- HTTP check: ❌ desactivar

El reboot automático failsafe desde Guardian hacia EAPs usa SNMP SET — integrado en `shomer_guardian_lib.py::_run_ssh_reboot` (8 mayo 2026).

**Flujo de reboot en Guardian (prioridad):**
1. Si `reboot_method='snmp'` → SNMP SET directo (EAPs)
2. Si `reboot_method='ssh'` → SSH con credenciales BD
3. Fallback → llave SSH
4. Fallback → contraseña global `SSH_FALLBACK_PASSWORD`
5. Fallback final → SNMP si tiene `snmp_community_write`

**Campos BD requeridos para EAPs (`devices` tabla):**
- `reboot_method = 'snmp'`
- `snmp_community = 'shomer2026'` (GET)
- `snmp_community_write = 'shomer2026@'` (SET)

### Limitaciones conocidas firmware EAP (ambos modelos)

| Limitación | EAP225 (3.3.8) | EAP610 (4.4.198) |
|------------|----------------|------------------|
| `ping` como admin | ❌ permission denied | ❌ permission denied |
| `reboot` como admin SSH | ❌ not permitted | ❌ not permitted |
| `curl` / `wget` | ❌ no instalado | ❌ no instalado |
| `nslookup` / `dig` | ❌ no instalado | ❌ no instalado |
| `/dev/null` redirect | ❌ sin permiso | ✅ funciona |
| TLS panel web | v1.0/v1.1 (firmware viejo) | v1.0/v1.1 |
| SSH algoritmos | legacy ssh-rsa obligatorio | ECDSA estándar |

## N.13 Acceso remoto VPN WireGuard — OpenWrt (8 mayo 2026)

VPN WireGuard configurada en el OpenWrt del lab (`192.168.1.206`, OpenWrt 23.05.5, MT7621).

**Paquetes instalados:** `kmod-wireguard`, `wireguard-tools`

**Configuración servidor (OpenWrt):**
- IP VPN servidor: `10.99.0.1/24`
- Puerto: UDP `51820`
- Llaves en: `/etc/wireguard/server_private.key`, `/etc/wireguard/server_public.key`
- Peer técnico Bogotá: IP `10.99.0.2/32`, llave pública en `/etc/wireguard/client_bogota_public.key`
- Firewall: zona `vpn` (INPUT/FORWARD/OUTPUT ACCEPT), forwarding vpn→lan, regla UDP 51820 en WAN

**Config cliente (archivo `.conf` para laptop técnico):**
```ini
[Interface]
PrivateKey = <llave privada cliente — ver /etc/wireguard/client_bogota_private.key en OpenWrt>
Address = 10.99.0.2/24
DNS = 8.8.8.8

[Peer]
PublicKey = rzfu0cPzmYJSueo94+XrHaRO94xL3DP7RcuGrmNLWVE=
Endpoint = <IP_PUBLICA_HOTEL>:51820
AllowedIPs = 10.99.0.0/24, 192.168.1.0/24
PersistentKeepalive = 25
```

**Para lab local (mismo segmento):** usar `AllowedIPs = 10.99.0.0/24` solamente — evita conflicto de rutas cuando laptop está en la misma LAN.

**Para producción en cada hotel:**
1. Conectar WAN del OpenWrt a internet del hotel (o port-forward UDP 51820 desde router ISP)
2. Cambiar `Endpoint` a la IP pública o DDNS del hotel
3. Cada técnico adicional: nuevo par de llaves + nuevo `[Peer]` en OpenWrt via UCI

**Nota seguridad:** el WAN del OpenWrt y el LAN NO deben estar en la misma subred — causa conflicto de rutas (bug encontrado en lab: WAN tomó IP 192.168.1.89 vía DHCP en la misma red que LAN .206).

## N.14 Sesión 19 — Bot mejorado: acciones reales, monitoreo proactivo (8 mayo 2026)

### Bug corregido: Telegram Guardian no llegaba en reboots automáticos
El poller usaba etiquetas `"NODO CAÍDO — REINICIANDO"` y `"REINICIO ENVIADO"` que no estaban en el whitelist de `app/scripts/alerts.py` → bloqueadas silenciosamente.
**Fix:** mensajes del poller ahora usan `"REINICIO EN PROGRESO"` (éxito) y `"PÉRDIDA DE SERVICIO"` (fallo).

### Bug corregido: nombres de radio SNMP para EAPs MediaTek/Ralink
`_snmp_health_probes` no detectaba los radios del `.253` — devolvía `radio_24/5: None`.
**Fix:** agregados `ra0` (2.4GHz) y `rax0`/`rai0` (5GHz) al set de nombres conocidos en `shomer_guardian_health_checks.py`.

### Nuevas funciones bot (shomer-agent)

**Comandos agregados:**
- `/diagnostico <ip>` — ping + estado Guardian + fallos acumulados + tiempo desde último reboot + modo mantenimiento, en un solo mensaje con botón de reboot si aplica
- `/mantenimiento on/off` — activa/desactiva `shomer_maintenance=1` vía API Guardian; pausa reboots automáticos; **notifica Telegram** al chat configurado (igual que mantenimiento por nodo)
- `/alertas` — últimas 15 alertas Hunter con botones de bloqueo directo por IP

**Monitor proactivo nuevo (`watch_guardian_nodes`):**
- Detecta cambios de estado en nodos Guardian cada 30s
- Cuando un nodo cae a `offline`/`no-internet` envía aviso con **botón de reboot inline**
- Cuando recupera envía confirmación ✅

**Parametrización en `.env`:**
```
BOT_AUTO_REBOOT=true         # false = solo avisa, no ejecuta reboots
BOT_AUTO_UNBLOCK_HOURS=0     # >0 = desbloquea IPs Hunter automáticamente tras X horas
```

**Fix Groq:** prompt actualizado — el LLM ahora sabe que el bot puede ejecutar acciones reales y sugiere comandos cuando hay problemas activos en lugar de solo dar consejos de texto.

**Fix velocidad:** `/estado` y texto libre ya no cargan el doc completo (`include_doc=False`). El doc solo se usa en `/doc` (developer).

**13 monitores activos:**
`hunter, devices, daily, resources, backups, wan, services, disk, pipeline, reboot, weekly_backup, guardian_nodes, auto_unblock`

**Acceso a Redis desde el bot:**
El bot tiene `network_mode: host` y usa `redis` (Python lib) directo a `127.0.0.1:6379` para leer/escribir `shomer_maintenance` y leer `failures:{ip}` / `last_reboot:{ip}`.

**Nuevas funciones `shomer_api.py` (agente):**
- `get_interfaces()` — `ip -br link show` del host (estado enp2s0, enp4s0, etc.)
- `get_snmp_uptime(ip, community)` — uptime vía OID `1.3.6.1.2.1.1.3.0`
- `get_maintenance()` / `set_maintenance(on)` — Redis directo
- `get_node_failures(ip)` — failures + last_reboot desde Redis

### Fixes UX bot (sesión 19 continuación)

**`/equipos`:** fusiona dos fuentes — nodos Guardian (con estado + método reboot) y dispositivos del agente (con flag `no_reboot`).

**`/mantenimiento`:** botón toggle inline. Sin argumentos muestra estado con botón; callback `maint:on` / `maint:off`.

**`/salud`:** sección "Interfaces de red" con estado UP/DOWN de cada NIC del host (crítico para verificar `enp4s0` espejo Hunter).

**`/diagnostico <ip>`:** agrega uptime SNMP si el equipo responde ping (cubre EAPs sin SSH).

### Referencia de documentos para el bot (Groq context)
- **`/doc` (developer)** → `CLAUDE.md` — arquitectura real, fixes, módulos exactos
- **Texto libre / técnico** → `Juan_Pablo.md` — lenguaje operacional simple
- Ambos montados vía `docker-compose.yml` volumes como `:ro`
- Rutas dentro del container: `/app/docs/CLAUDE.md` y `/app/docs/Juan_Pablo.md`
- `groq_helper.py`: `get_doc_context(level)` cachea por path separado; `explain()` elige el doc según `level`

### Bug corregido: `get_guardian_nodes()` devolvía dict en vez de lista
`/nodes` retorna `{"success":true,"nodes":[...]}`. La función retornaba el dict completo.
Al iterar un dict Python entrega las keys como strings → `'str' object has no attribute 'get'` en `/estado`, `/equipos`, `cb_quickaction` y `msg_natural`.
**Fix:** `shomer_api.py` — `get_guardian_nodes()` extrae `data.get("nodes", [])` o retorna `[]`.

### Principio de diseño del agente
**Solo acciones reversibles y remediales:**
- ✅ Permitido: reiniciar APs, desbloquear IPs, reiniciar servicios Shomer, limpiar disco, scan inventario, modo mantenimiento
- ❌ Prohibido: modificar configuración de red, tocar UFW, borrar snapshots, restaurar sin doble confirmación, cambiar JWT/credenciales

## N.15 Pendiente (post Sesión 19)

| Ítem | Prioridad |
|------|-----------|
| VPN WireGuard producción: DDNS + port-forward por hotel | Alta |
| Prueba failsafe EAP completa: provocar caída real, verificar Telegram + reboot SNMP | Alta |
| Pruebas físicas módulos Tracker, Hunter, Protector en lab | Alta |
| Configurar SITE_NAME en panel Shomer (campo visual en dashboard) | Media |
| Informe mensual al cliente | Media |

**Nota docs bot:** `CLAUDE.md` y `Juan_Pablo.md` se montan como volúmenes read-only en el container — cualquier cambio en los archivos del host se refleja automáticamente sin rebuild.

---

---

# 📚 Historia completa (Sesiones 1–68)

El registro cronológico de sesiones (antiguas Partes O–§BK, ~4.200 líneas) se movió a
**`CLAUDE_historico.md`** para mantener este manual liviano. **Nada se borró**: consúltalo ahí
para el detalle de cada cambio/parche (incluye §BJ Protector, §BK IA/Groq + auditoría root, etc.).
