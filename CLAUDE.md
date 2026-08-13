# Shomer Sentinel 2.0 — Manifiesto vivo

Este archivo une **dos cosas** en un solo lugar: (1) **qué hace el sistema hoy**, según instalación real y laboratorio USB; (2) **normas de diseño y referencia técnica** sin perder línea base del producto.

Los manuales de instalación detallados (cableado, modelo por modelo) y las tablas QA fila por fila **no** caben completos aquí; el equipo debe entregarlos en el mismo paquete de instalación donde corresponda. Este archivo concentra arquitectura, normas y estado sintético.

**Última unificación:** 13 ago 2026 (Bot `2bf8202` v1.1.1 — fix "recuperado" repetido en equipos flapeando, ver Sesión 71 abajo) · Sesión 71 · Idioma: español · Código: `/opt/network_monitor/` + `/storage/shomer-agent/`

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
- **Bot/IA**: 2 IAs — **Groq** (fondo/monitores, plan **FREE**) + **OpenAI** gpt-4o-mini (chat, con topes). Contenedor **`TZ=America/Bogota`**. Briefing **08:00** (resumen + puertos); mant. nocturno **sin Telegram si OK**. `/guardar` → `knowledge_decision()` (consejo en alertas/IA, no piloto auto). Token prod **solo Ópera**; lab bot activo en **.245** (token distinto). `.205`/`.243` bot off hasta token propio.

## Lecciones vivas (bugs cerrados que importan)
- **sudo/root**: tras cualquier `sudo restic` o correr módulos como root → revisar dueño del **repo** Y de `~/.cache/restic` Y de `__pycache__`; fix `chown -R usb_admin`. (Causó panel Protector "sin snapshots" y `.pyc` de Hunter en root.)
- **Protector "sin snapshots" en panel**: casi siempre caché restic root o locks huérfanos → `restic unlock` + chown caché. **Los datos NO se pierden.**
- **Groq "caído"**: es límite del plan **FREE** (RPM/TPM/RPD), no una caída. `watch_groq` chequea con `models.list()` (sin gastar tokens); un 429 de fondo **no** pausa el bot; alerta máx **1/día**.
- **Guardian mantenimiento**: revisar que solo los APs que deben estén en `node_maintenance` (TTL −1 = permanente y silencioso).
- **BD symlink**: `/opt/network_monitor/*.db` deben apuntar a `/storage/db/*.db` reales (no a archivos vacíos).

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
