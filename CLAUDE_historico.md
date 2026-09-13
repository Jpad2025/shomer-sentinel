# Shomer Sentinel 2.0 — Manifiesto vivo

Este archivo une **dos cosas** en un solo lugar: (1) **qué hace el sistema hoy**, según instalación real y laboratorio USB; (2) **normas de diseño y referencia técnica** sin perder línea base del producto.

Los manuales de instalación detallados (cableado, modelo por modelo) y las tablas QA fila por fila **no** caben completos aquí; el equipo debe entregarlos en el mismo paquete de instalación donde corresponda. Este archivo concentra arquitectura, normas y estado sintético.

**Última unificación:** 21 jul 2026 (Sesión 68 §BK — Hunter Wazuh respeta only_external; Protector permisos repo; bot watch_groq + auditoría IA/Groq §BK.4; Sesión 67 §BJ; Sesión 66 §BI; Sesión 65 §BH) · Idioma: español · Código: `/opt/network_monitor/` + `/storage/shomer-agent/`

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

# Parte O — Panel Estado del Sistema (Sesión 25 — 11 mayo 2026)

## O.1 Archivos involucrados

| Archivo | Cambio |
|---------|--------|
| `app/templates/system_status.html` | Rediseño completo — CSS + HTML + JS |
| `app/api/shomer_system_status.py` | Backend expandido con nuevos campos |

## O.2 Backend — `/api/system-health` campos nuevos

| Campo | Fuente | Descripción |
|-------|--------|-------------|
| `uptime` | `psutil.boot_time()` | Tiempo activo servidor: `{seconds, label}` |
| `temperature` | `psutil.sensors_temperatures()` | CPU temp: `{celsius, high, source}` o `null` |
| `firewall_ping` | `ping -c 1 hunter.firewall_ip` | Alcanzabilidad OpenWrt: `{host, reachable, latency_ms}` |
| `api_ports` | TCP connect 127.0.0.1:8000/8001 | Estado puertos Guardian y Tools: `[{name, port, reachable}]` |
| `hunter_stats` | `SELECT COUNT` tabla `blocked_ips` | `{active_blocks, blocks_24h}` |
| `nics[].mb_sent/mb_recv` | `psutil.net_io_counters()` | Tráfico acumulado por NIC desde boot |

Servicios monitoreados: 7 (añadidos `suricata` y `wazuh-manager` en Sesión 25).

## O.3 Frontend — layout final

```
Fila 1: 7 pills servicios systemd (flex-wrap)
Fila 2: 2 columnas equilibradas
         Izq: Recursos — gauges SVG semiarco CPU + RAM + res-row temp + uptime
         Der: Almacenamiento — 3 donuts SVG con % + GB usados/libres
Fila 3: NICs — fila horizontal (flex-wrap), tarjetas uniformes
         Cada NIC: nombre + UP/DOWN + 1 IPv4 + 1 IPv6 (truncada) + ↑↓ MB
Fila 4: Conectividad — pills: Firewall ping, Guardian :8000, Tools :8001, Hunter stats
Fila 5: Consola logs — tabs para los 7 servicios (añadidos suricata + wazuh)
```

## O.4 Decisiones de diseño

- **NICs separadas del grid recursos/discos** — evita columnas de altura desigual con espacio vacío
- **Gauges SVG puros** — sin dependencias externas (`stroke-dasharray` animado)
- **1 IPv4 + 1 IPv6 por NIC** — IPv6 truncada a 26 chars, elimina repetición de 3 IPv6 link-local
- **Health de APIs via TCP** — reemplaza fetch del navegador que fallaba por auth; `socket.create_connection` desde backend es confiable
- **Hunter stats en barra conectividad** — IPs activas + bloqueos 24h visible sin entrar al módulo Hunter

---

# Parte P — Agente Shomer: Sesiones 27–28 (13 mayo 2026)

## P.1 Nuevos módulos (core/)

| Módulo | Archivo | Función |
|--------|---------|---------|
| `memory.py` | `core/memory.py` | SQLite conversación por usuario — persiste en `/app/data/conversations.db` |
| `maintenance.py` | `core/maintenance.py` | Modo mantenimiento global + rate-limit por usuario |
| `download_server.py` | `core/download_server.py` | HTTP server stdlib en puerto 8082 — links temporales de descarga (TTL 30 min) |
| `tools.py` | `core/tools.py` | 15 tool definitions para function calling (Groq + OpenAI) |
| `llm_router.py` | `core/llm_router.py` | Router OpenAI chat / Groq monitores + fallback |
| `openai_helper.py` | `core/openai_helper.py` | Cliente OpenAI chat + tools |

## P.2 Tool Calling — `llm_router.chat()`

El bot ya no usa `explain()` para mensajes de texto libre. Usa `chat()` vía **`llm_router`** (OpenAI interactivo; Groq fallback y monitores):

```
Usuario: “cuántos nodos online?”
  → Router → OpenAI (o Groq si fallback)
  → Modelo recibe TOOLS + historial
  → Decide llamar get_system_status()
  → Bot ejecuta la tool → retorna datos reales
  → Segunda llamada → respuesta final con datos
```

**Tools disponibles (15 — `core/tools.py`):**
- `get_system_status` — nodos Guardian, CPU/RAM, IPs bloqueadas
- `get_guardian_nodes` — lista detallada de APs
- `ping_device` — ICMP a una IP
- `get_hunter_alerts` — últimas alertas Suricata
- `get_blocked_ips` — lista IPs bloqueadas en firewall
- `get_disk_usage` — particiones y espacio libre
- `search_manual` — búsqueda en manual de campo
- `get_services_status` — estado systemd
- `get_backup_status` — backups Protector
- `get_tracker_summary` — resumen Tracker
- `get_recent_events` — eventos Guardian
- `get_server_logs` — tail logs
- `get_network_interfaces` — NICs host
- `get_firewall_summary` — firewall Hunter
- `get_wan_status` — WAN servidor

**Manejo de errores en `chat()`:**
- OpenAI/Groq: fallback cruzado si proveedor primario falla o supera caps (`memory.check_openai_caps`)
- Groq: `parallel_tool_calls=False`; `400 tool_use_failed` → fallback `explain()`
- Groq `RateLimitError` → retry 4s → modo mantenimiento 90s

## P.3 Memoria SQLite por usuario

`memory.py` — `/app/data/conversations.db`:
- `MAX_STORED = 30` mensajes por usuario (auto-prune en INSERT)
- `GROQ_LIMIT = 10` mensajes pasados al LLM por llamada
- Tabla **`token_usage`**: `tokens`, `provider` (`openai`|`groq`), `user_id`, `created_at` — ver §V.3
- `add_message()` / `get_history()` / `clear_history()` / `check_openai_caps()`

`msg_natural` en `bot.py` — flujo simplificado:
```python
memory.add_message(user_id, “user”, text, level)
history   = memory.get_history(user_id)
respuesta = llm_router.chat(history, level=level, user_id=user_id)
memory.add_message(user_id, “assistant”, respuesta, level)
```

## P.4 Rate limiting y modo mantenimiento (`maintenance.py`)

```
USER_RATE_LIMIT_SECS = 5       # min entre mensajes del mismo usuario
COOLDOWN_SECS        = 90      # pausa global cuando se agota cuota Groq
```

- `is_paused()` — verifica si el bot está en modo mantenimiento (auto-expira)
- `check_user_rate(user_id)` — True si puede enviar, False si va muy rápido
- `pause(secs)` / `resume()` — control manual o automático

**Comandos developer nuevos:**
- `/pause [secs]` — pausa el asistente IA (comandos directos siguen activos)
- `/resume` — reactiva inmediatamente
- `/botstatus` — estado del bot: pausado/activo, nodos online, modelo

## P.5 Download server (puerto 8082)

`download_server.py` — stdlib puro, sin dependencias extra:
- HTTP server en `0.0.0.0:8082` (funciona gracias a `network_mode: host`)
- `register_file(data, filename, ttl=1800)` → URL `http://HOST_IP:8082/{token}/{filename}`
- Token único por descarga (`secrets.token_urlsafe`)
- Auto-limpieza de archivos expirados cada 5 min (background thread)

**Integrado en `/restaurar`:** cada backup ahora tiene dos botones:
- `🔄 Restaurar` — extrae tarball en servidor (flujo anterior)
- `⬇️ Descargar` — lee el tarball desde `/app/data/backups/`, genera link HTTP de 30 min

`SHOMER_HOST` y `DOWNLOAD_PORT=8082` en `.env`.

## P.6 System prompt — protocolo 3 niveles

`groq_helper.py` — `_SYSTEM_TECNICO` y `_SYSTEM_DEVELOPER` actualizados con:

1. **Diagnóstico primero**: usa tools antes de responder, nunca supone
2. **Nivel 1 — Informativo**: configuración o guía → paso a paso con comandos del bot
3. **Nivel 2 — Diagnóstico activo**: servicio degradado → reporta + sugiere acción
4. **Nivel 3 — Crítico**: ataque masivo o fallo hardware → informa, no actúa, escala al developer

`BEHAVIOR.md` (`/storage/shomer-agent/BEHAVIOR.md`) — actualizado 13/05/2026:
- Nueva sección `PROTOCOLO DE DIAGNÓSTICO — HERRAMIENTAS PRIMERO`
- Nueva sección `JERARQUÍA DE ACCIÓN — TRES NIVELES`
- Sección `ESTILO DE RESPUESTA` actualizada con tono técnico directo

## P.7 Anti-spam monitores (corrección de diseño)

### watch_hunter — problema resuelto
**Causa raíz:** `_blocked_ips` arrancaba vacío en cada restart del container → todas las IPs pre-existentes aparecían “nuevas” → spam.

**Fix correcto (dos capas):**
1. **Semilla al arrancar**: primera lectura carga el estado sin alertar
2. **Timestamp de bloqueo**: verifica `blocked_at` de la IP. Si fue bloqueada hace más de 10 min (`HUNTER_NEW_BLOCK_WINDOW_SECS = 600`) → pre-existente → no alerta. Si fue bloqueada hace menos de 10 min → evento real → alerta siempre, incluso en ciclos de bloqueo/desbloqueo

**Decisión de diseño — NO usar cooldown por IP:** si hay un ataque real en ciclo (IP bloqueada → auto-desbloqueada → rebloquee), el técnico DEBE recibir alerta en cada ciclo. El timestamp resuelve el problema sin suprimir alertas reales.

### watch_pipeline — problema resuelto
**Causa raíz:** `_pipeline_alerted = False` al arrancar → si pipeline ya estaba degradado → alerta en cada restart.

**Fix:** semilla al arrancar chequea el estado inicial. Si ya degradado → marca como notificado, no alerta. En ejecución normal: **sin cooldown** — cualquier transición `OK → degradado` alerta siempre. El hotel queda sin protección → urgente siempre.

## P.8 Cliente Groq actualizado

```python
_client = Groq(
    api_key=os.environ[“GROQ_API_KEY”],
    max_retries=4,   # reintentos automáticos con backoff
    timeout=20.0,    # timeout por request
)
```

## P.9 Comandos nuevos agregados

| Comando | Nivel | Función |
|---------|-------|---------|
| `/nuevo` | técnico + developer | Limpia historial de conversación (SQLite) |
| `/tokens` | developer | Consumo tokens hoy/semana; desglose OpenAI vs Groq + USD |
| `/botstatus` | developer | IA activa/pausada, proveedor LLM, caps OpenAI, nodos online |
| `/pause [s]` | developer | Pausa asistente IA por N segundos |
| `/resume` | developer | Reactiva asistente IA inmediatamente |

---

# Parte Q — Sesión 29 (14 mayo 2026) — Verificación general y fix ZIP

## Q.1 Auditoría de pendientes

Se verificó contra código real el estado de todos los pendientes documentados. Resultado: **sistema completo**, sin deuda técnica de código abierta.

| Módulo | Estado verificado |
|--------|------------------|
| Protector F4 — panel, backup, snapshots, B2/test, sync, restore | ✅ Todo en código |
| Hunter P9 retry CB | ✅ Cerrado por diseño (manual suficiente) |
| Hunter P11 HMAC Wazuh | ✅ Implementado; descartado por arquitectura (loopback) |
| Bot /instalar | ✅ `bot.py:982` — wizard 10 pasos |
| Bot RAG | No existe ni es necesario — docs (~16 KB) caben en context window directo |
| Etiquetas Tracker ZIP masivo | ✅ Cambiado a códigos de barras PDF sheet; flujo completo |

## Q.2 Bug corregido — proxy descarga ZIP

**Archivo:** `app/api/shomer_proxies.py`

**Problema:** `_proxy_backups()` (helper genérico) hacía `r.json()` sobre la respuesta del endpoint `/backups/restore/{id}/download`, que devuelve binario ZIP → excepción JSON decode → HTTP 502.

**Fix:** endpoint `proxy_backups_restore_download` reemplazado por implementación propia que usa `StreamingResponse` con `media_type=”application/zip”` y forwarding directo del stream desde puerto 8001.

```python
return StreamingResponse(
    r.aiter_bytes(),
    status_code=200,
    media_type=”application/zip”,
    headers={“Content-Disposition”: cd},
)
```

**Prueba ejecutada en lab:**
1. `POST /backups/sync_cloud` → sincronizó snapshot Mac `bc6d2b7b` → B2 como `fce41269` ✅
2. `POST /backups/b2/restore/fce41269...` → restauró `/srv/shomer_restore/fce41269.../srv/.../backups/test.txt` ✅
3. `GET /backups/restore/fce41269.../download` → HTTP 200, `application/zip`, 213 bytes, `test.txt` dentro ✅

## Q.3 Estado del bot verificado (14 mayo 2026)

| Aspecto | Detalle |
|---------|---------|
| Comandos | 31 slash + 7 callbacks |
| Groq/OpenAI tools | 15 (ver Parte P §P.2 — function calling compartido) |
| Memoria | SQLite `conversations.db` — 30 stored / 10 a Groq por llamada |
| Monitores | 19 watchers background |
| Drivers | 6 (Linux, MikroTik, Ubiquiti, Aruba, Cisco, TP-Link EAP) + auto-detect por banner SSH |
| Docs montados | CLAUDE.md, SISTEMA_SHOMER.md, TECNICO_OPERACION.md, SOPORTE_TECNICO.md, BEHAVIOR.md |
| RAG | No existe — context window directo suficiente para tamaño actual de docs |

## Q.4 Limpieza disco — 14 mayo 2026

Disco raíz quedó al **30 %** (`/dev/nvme0n1p3 25 G, 6.9 G usados`).

**Borrado permanente (validado antes de ejecutar):**

| Archivo / directorio | Razón |
|----------------------|-------|
| `app/backend/db.py.bak` | `.bak` de marzo — versión activa es de mayo y difiere |
| `/etc/systemd/system/*.disabled.bak.*` (8 archivos) | Servicios zombie migración abril 2026 — systemd los ignora |
| `/srv/shomer_backups/staging.old_20260407_050435/` | Repo Restic abandonado sin snapshots — activo es `staging/` (4 snaps) |
| `/tmp/shomer_requirements_full.txt` | Temporal sesión anterior |
| `/tmp/shomer_restore_fce41269.zip` | Archivo de prueba restore (213 bytes) |
| `__pycache__/` y `.pyc` | Python los regenera al arrancar |

**Truncado (sin cerrar fd abiertos):**

| Archivo | Tamaño antes |
|---------|-------------|
| `/var/log/suricata/` (todos los archivos) | ~511 MB |
| `/var/log/shomer/api.log` | ~41 MB |

**Journal vacuum:** `journalctl --vacuum-time=7d` → liberó **240 MB** de journals archivados.

**Conservado:** `/tmp/shomer-20260514.tar.gz` (59 MB) — paquete de documentación del día, pendiente de descargar.

---

# Parte R — Sesión 30 (19 mayo 2026) — Bot UX refactor + Telegram Setup + redirect fábrica

## R.1 Bot Telegram — cambios UX (shomer-agent)

| Cambio | Detalle |
|--------|---------|
| `/start` sin teclado inline | Se eliminó `_main_keyboard()` — el menú de botones era confuso; `/start` solo muestra texto de bienvenida |
| `/estado` eliminado | Redundante con `/salud` y estaba roto — removido completamente |
| `/tracker` eliminado | Sin comandos directos Tracker en el bot; se configura desde panel web |
| `/verificar` renombrado | Descripción cambiada a “✔️ Check final de instalación” |
| Comandos agrupados por módulo | `/ayuda` y `set_my_commands` ahora usan íconos: 👁️ Guardian, 🎯 Hunter, 🛡️ Protector, 🔍 Tracker |
| `/instalar` reescrito (10 pasos) | Flujo correcto: paso 1 = bot y Chat ID, paso 3 = panel 192.168.1.205 root/shomer2026, 3 sub-pasos wizard, paso 5 = `/verificar` aquí mismo, paso 7 = Guardian + Telegram, paso 9 = Protector, paso 10 = checklist final |
| `/resumen` agregado | Resumen on-demand del sistema vía IA (Groq explain o OpenAI según `.env`) |
| `/monitores` agregado | Muestra estado de los 20 monitores (✅/🔴/⚪ + última ejecución + última alerta) con labels legibles por módulo |
| `/usuario` agregado | Botones inline 🐧 Linux / 🍎 macOS / 🪟 Windows con comandos exactos para crear usuario de servicio `shomer` |
| Credenciales fábrica | Pasos de instalación usan `root/shomer2026` |

## R.2 monitor.py — sistema de tracking de monitores

Agregado al inicio del archivo:

```python
import time as _time_module
_monitor_status: Dict[str, Dict] = {}

def _tick(name: str, alerted: bool = False, error: str = “”) -> None:
    entry = _monitor_status.setdefault(name, {“last_ok”: None, “last_alert”: None, “error”: “”})
    now = _time_module.time()
    if error:
        entry[“error”] = error
    else:
        entry[“last_ok”] = now
        entry[“error”] = “”
    if alerted:
        entry[“last_alert”] = now

def get_monitor_status() -> Dict[str, Dict]:
    return dict(_monitor_status)
```

`_tick(name, error=str(e))` añadido en el `except` de los 20 monitores. `cmd_monitores` en bot.py lo consume para mostrar estado en tiempo real.

## R.3 shomer_api.py — fix fugas SQLite

`get_backup_devices()` y `get_config()` corregidos para usar `try/finally` al abrir conexión SQLite, evitando conexiones huérfanas bajo carga.

## R.4 Panel Setup — card Telegram

**Archivo:** `app/templates/setup.html`

Nueva card “TELEGRAM — BOT Y NOTIFICACIONES” insertada después de card0 (Identificación del sitio):

| Campo | Comportamiento |
|-------|---------------|
| Bot Token | Visible para todos; editable solo si rol = `admin` (detectado vía `/auth/me`). Campo `readonly` + opacidad 55% para no-admin |
| Chat ID | Editable para todos los usuarios |
| Botón Guardar | `POST /config/system` con `guardian.telegram_token` (solo si admin) + `guardian.telegram_chat_id` |
| Botón Probar Telegram | `POST /telegram/test` |
| Carga inicial | `GET /config/system` al abrir la página → pre-rellena ambos campos |

**Razón:** El técnico debe configurar su Chat ID al primer ingreso. El token lo preconfiguró USB antes de enviar el appliance — un operador no debe poder cambiarlo.

## R.5 Guardian panel — limpieza sección Telegram

**Archivo:** `app/templates/guardian.html`

- Removidos campos “Telegram Bot Token” y “Telegram Chat ID” de la sección “Guardian — Parámetros”
- Removido botón “Probar Telegram” de esa sección
- Agregada nota con link a `/setup` para gestionar Telegram
- `saveGuardianParams()` simplificado: solo guarda `fail_threshold` y `cooldown_sec`
- Removidas referencias a token/chat_id en la función de carga `loadGuardianConfig()`

## R.6 Redirect de fábrica root → /setup

**Archivo:** `app/api/auth_api.py` — función `login()`

```python
_factory_hash = hashlib.sha256(“shomer2026”.encode()).hexdigest()
_force_setup = (row[“username”] == “root” and row[“password_hash”] == _factory_hash)
content = {“token”: token, “username”: row[“username”], “role”: row[“role”]}
if _force_setup:
    content[“redirect”] = “/setup”
```

**Flujo:**
- `root` + `shomer2026` → respuesta incluye `”redirect”: “/setup”` → `login.html` ya usa `d.redirect || '/'` → va directo a instalación
- Una vez que el técnico cambia la contraseña de `root`, el hash ya no coincide → login normal al dashboard
- Sin flags en BD, sin columnas extra. El cambio de password es el interruptor natural

## R.7 Usuario root de fábrica

`_ensure_users_table()` en `auth_api.py` garantiza que `root/shomer2026` (rol admin) siempre exista en la BD (INSERT OR IGNORE). Es el usuario de primer acceso del técnico. El usuario `admin` (JP) existe por separado y su password no se toca por código.

---

# Parte S — Sesión 31 (21 mayo 2026) — Instalación Bogotá + fixes despliegue

## S.1 Instalación remota Bogotá (shomerbogota)

Primer appliance de campo instalado de forma completamente remota desde Utah vía Tailscale SSH.

| Dato | Valor |
|------|-------|
| Hostname | `shomerbogota` (renombrado a `shomer-hotelopera` el 7 jun 2026 — Sesión 50, ver nota abajo) |
| Tailscale IP | `100.103.148.119` |
| LAN IP | `192.168.10.206/24` *(instalación inicial; ver nota abajo)* |
| Gateway | `192.168.10.1` |
| NIC gestión | `eno1` |
| Hardware | Lenovo (single NIC física) |
| OS | Ubuntu 22.04 LTS Server |

**Particionado 256 GB SSD (GPT/UEFI):**

| Partición | Tamaño | FS | Mount |
|-----------|--------|-----|-------|
| sda1 | 1 GB | vfat | /boot/efi |
| sda2 | 1 GB | ext4 | /boot |
| sda3 | 20 GB | ext4 | / |
| sda4 | 20 GB | ext4 | /var |
| sda5 | 20 GB | ext4 | /opt |
| sda6 | 10 GB | ext4 | /home |
| sda7 | 133 GB | ext4 | /srv |
| sda8 | 4 GB | ext4 | /tmp |
| sda9 | 4 GB | swap | — |
| sda10 | 25 GB | ext4 | /storage |

**Teclado en español:** `sudo localectl set-keymap es`

> **Nota — IP LAN actual Hotel Ópera (verificado jun 2026):** red admin del hotel **`192.168.0.0/24`** — Shomer en **`192.168.0.250`** (`eno1`), gateway **`192.168.0.1`**, panel **`https://192.168.0.250:8443`**. Los valores `192.168.10.206` de esta bitácora son del primer despliegue; **no usar** en campo. Detalle vivo en `SITE.md` del servidor y `docs/EQUIPOS.md`.
>
> **Nota — convención de nombres por cliente (Sesión 50, 7 jun 2026):** el hostname `shomerbogota` se renombró a **`shomer-hotelopera`** (`hostnamectl set-hostname` + fix `/etc/hosts`). Razón: nombrar por **ciudad** deja de servir en cuanto haya más de un cliente en la misma ciudad — no se podría diferenciar entre ellos al gestionar varios equipos a la vez. La convención correcta es nombrar por **cliente/sitio** (`shomer-<nombre-cliente>`), igual que ya hace `SITE.md` (§AH.1). Actualizado en `tools/servers.txt` y referencias activas de este documento; las menciones a `shomerbogota` en bitácoras de sesiones anteriores se conservan tal cual como registro histórico (era el nombre real en ese momento).

## S.2 Bugs corregidos — instalaciones nuevas

### Bug 1 — `/health` crashea en BD nueva (CRÍTICO)

**Archivo:** `app/api/shomer_guardian_nodes.py` — función `health()`

**Problema:** el endpoint `GET /health` consultaba `infra_nodes` sin crearla. En instalaciones nuevas la tabla no existe → 500 → watchdog reinicia el servicio en loop cada 35s → panel da 502 permanente.

**Fix:** `CREATE TABLE IF NOT EXISTS infra_nodes` antes del SELECT en `health()`.

### Bug 2 — Guardian redirige siempre a /setup

**Problema:** `web_ui.py` redirige a `/setup` si `base.subnet` es None en `system_state`. En Bogotá el wizard se completó pero sin guardar `base.subnet` → loop redirect.

**Fix:** insertar `base.subnet` y `base.management_interface` en `system_state` vía wizard o directamente en BD.

### Bug 3 — Tablas BD faltantes en instalación nueva

La instalación no inicializa todas las tablas necesarias. Las tablas `infra_nodes`, `event_log`, `system_state`, `devices` se crean por distintos módulos al arrancar — si algún módulo no se ejecuta primero, la tabla no existe.

**Fix temporal Bogotá:** creadas manualmente vía Python. **Fix definitivo:** el `CREATE TABLE IF NOT EXISTS` en `health()` cubre `infra_nodes`; el resto se crea al primer uso de cada módulo.

## S.3 Fixes al pipeline de despliegue

### make_package.sh — ahora incluye shomer-agent

El paquete generado por `tools/make_package.sh` incluye `shomer-agent/` (sin `.env` ni `data/`). La carpeta se toma desde `/storage/shomer-agent/` en el lab.

### install_shomer.sh — paso 6b nuevo

Si el paquete incluye `shomer-agent/`, el instalador:
1. Copia el código a `/storage/shomer-agent/`
2. Crea directorios `data/backups` y `data/downloads`
3. Ejecuta `docker compose build` automáticamente

Lo que queda pendiente por cliente (no automatizable):
- Crear bot en BotFather → obtener token
- Crear grupo Telegram → obtener Chat ID
- Llenar `/storage/shomer-agent/.env`
- `sudo systemctl enable --now shomer-agent`

### Credenciales de fábrica corregidas en resumen

El script mostraba credenciales incorrectas. Corregido a `root / shomer2026`.

## S.4 Docs técnico — protección admin-only

`/docs/tecnico` y `/docs/fallas` ahora requieren `role == “admin”`. Operadores son redirigidos al dashboard. Documentos accesibles desde el panel:

- 📖 Shomer Compendio Completo
- 🛠️ Soporte Técnico
- 🌐 Tailscale VPN
- 💾 Ubuntu Particiones 256GB
- ✈️ Manual Telegram Bot

## S.5 Estado Bogotá al cierre de sesión

| Componente | Estado |
|-----------|--------|
| Panel HTTPS | ✅ `https://192.168.10.206:8443` |
| shomer-guardian :8000 | ✅ activo, estable |
| shomer-tools :8001 | ✅ activo |
| nginx | ✅ activo |
| redis | ✅ activo |
| Tracker scan | ✅ 12 equipos encontrados en 192.168.10.0/24 |
| shomer-agent Docker | ⏳ pendiente — falta Chat ID Telegram + GROQ_API_KEY |
| Telegram Guardian | ⏳ pendiente — configurar en /setup |
| Usuario admin | ✅ creado en BD |
| base.subnet | ✅ `192.168.10.0/24` |

**Equipos encontrados en red Bogotá:**
- `192.168.10.1` — Router ZTE
- `192.168.10.250` — Cisco/Linksys
- `192.168.10.213` — Cámara **Dahua**
- `192.168.10.212` — **Suprema** (control acceso biométrico)
- `192.168.10.121` — HP
- `192.168.10.2` — HP laptop
- `192.168.10.8` — ASRock
- + 5 más (vendor no identificado)

## S.6 Referencia ancho de banda B2

Con **11 MB/s subida** (medido en Bogotá, ~90 Mbps):

| Escenario | Tiempo estimado |
|-----------|----------------|
| 200 GB primer backup completo | ~5 horas |
| 200 GB con límite 2 MB/s (sin saturar red) | ~28 horas |
| Backups siguientes (solo deltas Restic) | 10–30 min |

**Recomendación:** primer backup en horario nocturno con `restic --limit-upload 2048` (2 MB/s). El scheduler de Protector ya usa `base.timezone = America/Bogota`.

---

# Parte T — Roadmap Fase 2 (Sesión 32 — 22 mayo 2026)

## T.1 Principio de diseño — regla para todo lo nuevo

**”No simplificar, no complicar — agregar sin tocar lo que funciona.”**

Antes de modificar un archivo existente, preguntarse: ¿esto puede vivir en un módulo nuevo?
- Módulos nuevos leen APIs/BD existentes como clientes — no modifican lógica interna.
- La única excepción válida: agregar una llamada de 2 líneas en un módulo existente para disparar algo nuevo (ej: Hunter crea incidente al bloquear). Nunca modificar lógica core.
- Guardian sigue siendo Guardian. Tracker sigue siendo Tracker. Los módulos nuevos se suman, no reemplazan.

**Origen:** Documento 3 — Roadmap honesto para llegar al 73% prometido (21 mayo 2026). Análisis completo en sesión 32.

---

## T.2 Arquitectura de módulos nuevos

```
Guardian (existente)         → APs, routers → reboot automático, failsafe, Telegram
Inframonitor (NUEVO)         → switches, servidores, cualquier IP → solo ping/estado
NOC Display (NUEVO)          → lee Guardian + Inframonitor → pantalla TV tiempo real
shomer_reports.py (NUEVO)    → R1 — PDF mensual KPIs
shomer_incidents.py (NUEVO)  → R2 — tabla incidentes con ack/cierre
restore_drill.py (NUEVO)     → R3 — drill automático mensual
shomer_audit.py (NUEVO)      → R8 — auditoría middleware panel web
shomer_audit_export.py (NVO) → R12 — export auditoría por período
```

Ningún módulo nuevo toca código existente salvo las excepciones documentadas en §T.4.

---

## T.3 Módulos priorizados — estado actualizado (1 jun 2026)

### Completados

| Módulo | Archivo | Estado | Sesión |
|--------|---------|--------|--------|
| **Inframonitor** | `app/api/shomer_inframonitor.py` | ✅ Producción | 32-38 |
| **NOC Display** | `app/api/shomer_noc.py` + `noc.html` | ✅ Producción | 32-39 |
| **R4 Object Lock B2** | `app/api/backups.py` línea 1266 | ✅ Producción | 35 |
| **R8 Auditoría panel** | `app/api/shomer_audit.py` | ✅ Producción | 32-33 |
| **R2 Tabla incidentes** | `app/api/shomer_incidents.py` | ✅ Producción | 32-33 |
| **R3 Restore drill** | `app/scripts/restore_drill.py` | ✅ Producción | 32-33 |
| **R1 PDF mensual** | `app/api/shomer_reports.py` | ✅ Producción | 32-41 |
| **R12 Export auditoría** | `app/api/shomer_audit_export.py` | ✅ Producción | 32-33 |
| **Auditoría de red (nmap)** | `app/api/shomer_audit_network.py` | ✅ Producción | 40 |
| **Auditoría de parches SSH** | `shomer_audit_network.py::_run_patch_audit` | ✅ Producción | 43 |

### Pendientes reales

| Módulo | Archivo | Estado | Descripción |
|--------|---------|--------|-------------|
| **WMI Windows parches** | `shomer_audit_network.py` | ✅ Sesión 43 | `_patch_check_wmi()` — impacket ya instalado. Severidad por días sin parchear (<60d=OK, <90d=medio, <180d=alto, >180d=crítico). |

### Descartados por ahora (decisión Juan Pablo)

| Módulo | Razón |
|--------|-------|
| **R11 2FA panel** | No urgente — panel ya tiene JWT + HTTPS. Retomar si cliente lo exige. |
| **R5 Retención SIEM** | Disco manejado por limpieza automática. Retomar si contrato lo requiere. |
| **R7 RACI alertas** | Toca 21 monitores — riesgo alto. Retomar cuando la base de clientes lo justifique. |

### Descartados / baja prioridad

| Módulo | Nota |
|--------|------|
| R6 CVE matching | Demasiado pesado en appliance. Evaluar servicio externo. |
| R9 Driver Sophos API | Solo si cliente lo exige. |
| R10 Diagrama topológico | Un diagrama manual cumple igual. |
| R13 Checklist post-DR | Formulario simple — cuando haya tiempo. |

---

## T.4 Excepciones — archivos existentes que SÍ se tocan (mínimo)

| Módulo nuevo | Archivo existente tocado | Qué se agrega | Por qué |
|---|---|---|---|
| R2 Incidentes | `app/api/casador_blocking.py` | 2 líneas: llamada a `create_incident()` al bloquear | Hunter necesita disparar creación del incidente |
| R1 PDF mensual | `app/api/main.py` | Registro de ruta nueva | FastAPI necesita importar el router |
| R8 Auditoría | `app/api/main.py` | Registro de middleware | FastAPI necesita el middleware al arrancar |
| NOC Display | `app/api/main.py` | Registro de ruta `/noc` | FastAPI necesita importar el router |
| Inframonitor | `app/api/main.py` | Registro de ruta `/infra` | FastAPI necesita importar el router |

---

## T.5 Inframonitor — especificación técnica

**Propósito:** Monitorear cualquier equipo de red por ICMP (ping) sin lógica de reboot ni failsafe. Switches, servidores, NAS, cámaras, impresoras — cualquier IP que responda ping.

**Diferencia con Guardian:**

| | Guardian | Inframonitor |
|---|---|---|
| Equipos | APs, routers con SSH | Cualquier equipo con ping |
| Acción automática | Reboot, alertas Telegram, failsafe | Solo registro de estado |
| Lógica | Compleja (CB, cooldown, Redis) | Simple (ping → vivo/muerto) |
| Alertas | Telegram con detalles y botones | Solo NOC display (sin spam) |

**Tabla BD:** `infra_devices` en `network_monitor.db`

```sql
CREATE TABLE IF NOT EXISTS infra_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    device_type TEXT DEFAULT 'generic',  -- switch, server, camera, printer, nas, generic
    location TEXT DEFAULT '',
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS infra_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    status TEXT NOT NULL,  -- online, offline
    latency_ms REAL,
    checked_at TEXT DEFAULT (datetime('now'))
);
```

**Endpoints:**
- `GET /infra/devices` — lista equipos registrados con último estado
- `POST /infra/devices` — agregar equipo
- `DELETE /infra/devices/{id}` — eliminar equipo
- `GET /infra/status` — estado actual de todos (para NOC)
- Poller interno cada 30s — ping a cada IP, actualiza Redis + `infra_status`

**Tipos de equipo y íconos NOC:**
- `switch` → 🔀
- `server` → 🖥️
- `camera` → 📷
- `printer` → 🖨️
- `nas` → 💾
- `generic` → 📡

---

## T.6 NOC Display — especificación técnica

**Propósito:** Pantalla de TV en tiempo real para personal interno. Sin login. Token en URL.

**URL:** `https://<IP>:8443/noc?token=<token>`
**Token:** Guardado en `system_state` como `noc.display_token`. Generado en Setup. Sin este token → página en blanco.

**Datos que muestra (sin info sensible):**

| Sección | Datos | Fuente |
|---|---|---|
| Header | SITE_NAME + fecha/hora + indicador EN VIVO | `system_state.base.site_name` |
| Infraestructura | Nombre equipo + tipo + 🟢🟡🔴 | Guardian `/nodes` + Inframonitor `/infra/status` |
| Seguridad | Conteo bloqueadas hoy, alerta más reciente (solo tipo, sin IP) | Hunter `/remedies/stats` |
| Servidor | CPU%, RAM%, disco% con barras visuales | `/api/server-metrics` |
| Servicios | Pills Guardian/Hunter/Nginx/Tools | `/api/system-health` |
| Ticker inferior | Últimos 5 eventos (sin IPs, solo tipo+hora) | Guardian `/events` |

**Refresh:** JavaScript puro, `fetch()` cada 30s a `GET /noc/data?token=<token>` — un solo endpoint que agrega todo.

**Diseño:** HTML/CSS puro, sin frameworks, fuente grande, alto contraste oscuro. Optimizado para 1920x1080.

**Archivos:**
- `app/api/shomer_noc.py` — router FastAPI, endpoint `/noc` (HTML) + `/noc/data` (JSON)
- `app/templates/noc.html` — template Jinja2 con CSS inline

---

## T.7 Flujo de desarrollo y despliegue

```
1. Desarrollar en lab .205 (Utah)
2. Probar con hardware físico conectado
3. Validar en QA
4. make_package.sh → genera paquete
5. install_shomer.sh → despliega en Bogotá o cualquier cliente
```

**Regla:** Nada se considera listo hasta probarlo en hardware real en .205.

---

## T.8 Pruebas requeridas por módulo

### Inframonitor
- [ ] Agregar switch del lab, verificar ping cada 30s
- [ ] Desconectar equipo físico → confirma `offline` en <1 min
- [ ] Reconectar → confirma `online`
- [ ] Verificar que Guardian no se ve afectado

### NOC Display
- [ ] Abrir en TV real o segundo monitor
- [ ] Sin token → página en blanco
- [ ] Token correcto → dashboard carga
- [ ] Simular caída de AP → nodo cambia a 🔴 en <35s
- [ ] Simular bloqueo Hunter → contador incrementa
- [ ] Dejar corriendo 1 hora → sin memory leaks ni crashes

### R4 Object Lock
- [ ] Activar desde wizard Protector
- [ ] Verificar en consola B2 que bucket tiene Object Lock
- [ ] Intentar borrar snapshot manualmente en B2 → debe fallar

### R8 Auditoría
- [ ] Login como admin, cambiar configuración Guardian → aparece en `audit_log`
- [ ] Login como operator, hacer cambio → aparece con rol correcto
- [ ] Export CSV → descarga correcta con todos los campos

---

# Parte U — Sistema unificado UI: botones + logs colapsables (Sesión 32 — 22 mayo 2026)

## U.1 Objetivo

Eliminar la duplicación de estilos en cada template (cada uno definía sus propios `.btn-*` con colores y formas distintas) y darle al panel un look profesional uniforme.

**Solo aplicado en Utah .205.** Bogotá .119 queda pendiente de replicación.

## U.2 Sistema de botones — base.html

Bloque CSS centralizado en `app/templates/base.html` (insertado en `<style>` global). Cada botón tiene **dos nombres equivalentes**: por color y por uso, para facilitar migración progresiva.

```css
.btn { display:inline-flex; align-items:center; gap:6px; padding:8px 16px; border-radius:6px;
       font-family:'Inter',sans-serif; font-size:13px; font-weight:600;
       cursor:pointer; transition:all 0.15s; white-space:nowrap; line-height:1; text-decoration:none; }
.btn:disabled { opacity:0.5; cursor:not-allowed; }

/* 1. Acción principal — TEAL SÓLIDO (corporativo, sin sombra) */
.btn-blue, .btn-ejecutar { background:var(--teal); color:#fff; border:none; }
.btn-blue:hover, .btn-ejecutar:hover { background:#0f8080; }

/* 2. Alternativa — OUTLINE TEAL */
.btn-outline, .btn-opcion { background:transparent; color:var(--teal); border:1px solid var(--teal); }
.btn-outline:hover, .btn-opcion:hover { background:rgba(13,110,110,0.12); }

/* 3. Peligroso — ROJO OUTLINE */
.btn-red, .btn-bloquear { background:transparent; color:var(--offline); border:1px solid rgba(220,38,38,0.5); }
.btn-red:hover, .btn-bloquear:hover { background:rgba(220,38,38,0.12); border-color:var(--offline); }

/* 4. Utilidad discreta — TRANSPARENTE GRIS */
.btn-ghost, .btn-toolbar { background:transparent; color:var(--muted); border:none; }
.btn-ghost:hover, .btn-toolbar:hover { background:rgba(30,42,58,0.5); color:var(--text); }

/* Modificadores */
.btn-sm    { padding:5px 10px; font-size:12px; }
.btn-lg    { padding:10px 20px; font-size:14px; }
.btn-icon  { padding:6px; }
.btn-block { width:100%; justify-content:center; }
```

**Convención de uso:**

| Cuándo | Clase | Ejemplo |
|--------|-------|---------|
| Acción principal / submit / refrescar | `btn btn-blue` | "Escanear", "Actualizar", "Guardar" |
| Acción secundaria / outline | `btn btn-outline` | "Cancelar", "Exportar CSV", "Ver historial" |
| Acción destructiva / bloqueo | `btn btn-red` | "Eliminar", "Bloquear IP", "Incidentes" |
| Acción minimalista / toolbar | `btn btn-ghost` | "Detalles", "Más opciones" |
| Botón pequeño (filas de tabla) | añadir `btn-sm` | `btn btn-outline btn-sm` |
| Botón completo (modal) | añadir `btn-block` | `btn btn-blue btn-block` |

## U.3 Templates migrados en Utah .205

| Template | Migrado | Notas |
|----------|---------|-------|
| `admin.html` | ✅ | Primer prototipo |
| `inventory.html` | ✅ | Más complejo — 8+ variantes locales eliminadas |
| `system_status.html` | ✅ | Solo `.btn-refresh` |
| `setup.html` | ✅ | Mantiene `.btn-teal` adicional para layout (width 100%, letter-spacing); botones inline-style con Orbitron migrados también |
| `backups.html` | ✅ | Header + filas dinámicas |
| `guardian.html` | ✅ | 9 variantes locales eliminadas |
| `hunter.html` | ✅ | 8 variantes + Wazuh (#c9aa71) → outline teal; Incidentes (rojo distinto) → btn-red unificado; Hunter toggle → btn-outline base con JS que solo cambia estado |
| `audit.html` | ✅ | Nuevo módulo Fase 2 |
| `incidents.html` | ✅ | Nuevo módulo Fase 2 |
| `inframonitor.html` | ✅ | Nuevo módulo Fase 2 |
| `noc.html` | — | Sin botones interactivos (dashboard) |
| `login.html` | — | Preservado (look único Orbitron + glow) |

## U.4 Bug arquitectónico común — `.btn-hdr { border:none }`

**Causa raíz:** `audit.html`, `incidents.html` e `inframonitor.html` (templates de Fase 2 creados antes de la unificación) tenían en su CSS local:

```css
.btn-hdr { display:flex; ... border:none; ... }
```

Este `border:none` está **después** del CSS global de `base.html` en el orden del documento → **pisaba** al `border:1px solid var(--teal)` de `.btn-outline` → botones aparecían sin marco.

**Fix:** eliminar la regla completa `.btn-hdr { ... }` y dejar solo `.btn-hdr svg { ... }`. El padding/font/border viene del sistema unificado.

```css
/* .btn-hdr: solo styles del SVG; padding/border/font los dan .btn .btn-blue/.btn-outline del sistema unificado en base.html */
.btn-hdr svg { width:15px; height:15px; fill:none; stroke:currentColor; stroke-width:2; }
```

## U.5 Hunter — layout final del header

Los 4 botones (Wazuh, Hunter toggle, Incidentes, Actualizar) ahora viven dentro de un wrapper `<div class="page-header-right">` para alinearlos a la derecha:

```html
<div class="page-header-right" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-left:auto;">
  <a id="btn-wazuh" class="btn btn-outline btn-hdr" ...>Wazuh</a>
  <button id="btn-hunter-toggle" class="btn btn-outline btn-hdr" onclick="toggleHunter()">Hunter</button>
  <a href="/incidentes" class="btn btn-red btn-hdr">Incidentes</a>
  <button class="btn btn-blue btn-hdr" id="btn-refresh">Actualizar Alertas</button>
</div>
```

**Toggle Hunter — JS ajustado:** cuando está **activo**, el JS deja vacíos `btn.style.background/borderColor/color` para que tome el `.btn-outline` corporativo (idéntico a botones de Tracker). Cuando está **pausado**, aplica gris explícito.

## U.6 Panel de logs colapsable lateral

Patrón originario de `inventory.html` replicado en Guardian, Hunter y Protector.

**CSS común (cada template tiene su propio ancho expandido):**

```css
.logs-panel { width: {N}px; min-width: {N}px; ... transition: width 0.2s ease, min-width 0.2s ease; }
.logs-panel.collapsed { width: 44px; min-width: 44px; }
.logs-panel.collapsed .logs-body,
.logs-panel.collapsed h3,
.logs-panel.collapsed .logs-count { display: none; }
.logs-panel.collapsed .logs-header { padding: 12px; justify-content: center; border-bottom: none; }
.logs-header { ... cursor: pointer; user-select: none; }
.logs-header:hover { background: rgba(30,42,58,0.4); }
```

**HTML:**

```html
<div class="logs-panel collapsed" id="logs-panel-wrap">
  <div class="logs-header" onclick="toggleLogs()">
    <svg ...></svg>
    <h3>Logs {Módulo}</h3>
    <span class="logs-count" id="logs-count">0</span>
  </div>
  <div class="logs-body" id="logs-panel"></div>
</div>
```

**JS común:**

```javascript
function toggleLogs() {
  const p = document.getElementById('logs-panel-wrap');
  if (p) p.classList.toggle('collapsed');
}
```

**Comportamiento:** Arranca colapsado (solo flecha 44px a la derecha). Click en el header → despliega/recoge. Los `addLog()` siguen escribiendo al panel oculto; al abrirlo se ve el historial acumulado.

**Decisión de diseño:** El `addLog()` **NO** auto-expande el panel — el usuario decide cuándo verlo. Esto evita que los logs iniciales del bootstrap (`'SYSTEM iniciado'`, etc.) abran la consola al cargar la página.

## U.7 Mapeo de nombres en logs

| Template | Texto anterior | Texto nuevo |
|----------|---------------|-------------|
| `inventory.html` | Actividad | **Logs Tracker** |
| `guardian.html` | Logs en Tiempo Real | **Logs Guardian** |
| `hunter.html` | Logs de Seguridad | **Logs Hunter** |
| `backups.html` | Logs de Respaldo | **Logs Protector** |

## U.8 Anchos por módulo (preservados al expandir)

| Módulo | Ancho expandido |
|--------|----------------|
| Tracker | 320px |
| Guardian | 340px |
| Protector | 320px |
| Hunter | 200px (filas estrechas de eventos) |

## U.9 Pendiente en Bogotá .119

Replicar en Bogotá (cuando se programe la siguiente ventana de mantenimiento):

1. CSS unificado de botones en `base.html`
2. Migración de templates comunes (admin, inventory, system_status, setup, backups, guardian, hunter)
3. Panel de logs colapsable en Guardian, Hunter, Protector
4. Rename `Actividad` → `Logs Tracker` en inventory

Los templates de Fase 2 (inframonitor, audit, incidents, noc) **no existen** en Bogotá — no aplica esa parte.

---

# Parte V — Sesión 34 (23 mayo 2026) — OpenAI chat + límites de costo

## V.1 Decisión de producto

- **Gemini descartado** (marzo 2026: proyectos nuevos sin free tier usable; consola Google sin tope duro simple; cuotas confusas).
- **OpenAI `gpt-4o-mini`** para conversación interactiva del técnico (texto libre + 15 tools).
- **Groq gratis** se mantiene para: 20 monitores background, `/doc`, `explain()`, resumen diario.
- **Fallback automático:** cualquier fallo o cap de OpenAI → Groq responde igual (el bot no se queda mudo).

## V.2 Archivos agente (`/storage/shomer-agent/core/`)

| Archivo | Rol |
|---------|-----|
| `llm_router.py` | **Nuevo** — punto único: `chat()` → OpenAI o Groq; `explain()` → siempre Groq |
| `openai_helper.py` | **Nuevo** — cliente OpenAI con tool calling (mismo schema `tools.py`) |
| `groq_helper.py` | Sin cambio de rol — monitores + fallback |
| `memory.py` | `token_usage.provider` (`openai`/`groq`), `user_id`; `check_openai_caps()` |
| `bot.py` | `msg_natural` usa `_llm.chat()`; `/tokens` desglose por proveedor + USD estimado |
| `gemini_helper.py` | **Eliminado** |

**Docker:** paquete `openai>=1.40` en `requirements.txt`; eliminado `google-generativeai`. Imagen base fijada `python:3.11-slim-bookworm`.

## V.3 Tres capas de límite de gasto

| Capa | Dónde | Qué hace |
|------|-------|----------|
| 1 | OpenAI web → Limits → **$5/mes** | Corta API al llegar (configuración cliente) |
| 2 | Crédito prepago OpenAI (opcional) | Techo absoluto de saldo |
| 3 | **Código** `.env` hard caps | Fallback Groq antes de gastar de más |

**Hard caps en código (lab `.205`, mayo 2026):**

| Variable | Valor | Efecto |
|----------|-------|--------|
| `OPENAI_LIMIT_PER_MESSAGE` | 2000 | Un mensaje no dispara costo |
| `OPENAI_LIMIT_PER_USER_DAILY` | 8000 | Tope por técnico/día |
| `OPENAI_LIMIT_DAILY` | 12000 | ~360k tokens/mes máx. → **~$0.05–0.15 USD/mes** |

Globales Groq (sin cambio): `TOKEN_WARN_DAILY=80000`, `TOKEN_LIMIT_DAILY=120000` → modo mantenimiento 30 min.

## V.4 Costo esperado (recalculado)

| Escenario | Tokens/mes (chat) | Costo ~USD/mes |
|-----------|-------------------|----------------|
| 1 Shomer, uso normal | ~150–450k | **$0.05–0.15** |
| 5 Shomers | ~750k–2.2M | **$0.25–0.70** |
| Tope web cliente | — | **$5** (red lejana) |
| Tope código/día 12k | 360k/mes máx. | **~$0.11** |

Monitores en Groq = **$0**.

## V.5 Lab `.205` — dual ruta (solo laboratorio)

El appliance `.205` tiene **dos default routes** (cable `enp2s0` → `.206` y WiFi `wlp3s0`). En mayo 2026 el cable no alcanzaba `api.openai.com` (Cloudflare); WiFi sí.

**Fix lab (no aplica en Bogotá / sitio con una sola NIC):**

- Script `/storage/shomer-agent/etc/openai-wifi-routes.sh`
- systemd `shomer-openai-routes.service` — rutas `api.openai.com` → gateway WiFi al arranque

En producción con **una sola salida a internet** no hace falta este servicio.

## V.6 Comandos operativos

```bash
# Ver proveedor activo
sudo docker exec shomer-agent python3 -c "from core import llm_router; print(llm_router.active_provider())"

# Consumo tokens (Telegram developer)
/tokens

# Volver a solo Groq (sin costo)
# .env → LLM_PROVIDER_INTERACTIVE=groq
cd /storage/shomer-agent && sudo docker compose down && sudo docker compose up -d
```

## V.5 Lab `.205` — cable funciona (actualizado Sesión 35)

En mayo 2026 el cable no alcanzaba `api.openai.com`. En Sesión 35 se confirmó que **cable funciona** (HTTP 401 = conectado). `OPENAI_BIND_IP` vaciado, `shomer-openai-routes.service` deshabilitado. **El workaround WiFi ya no aplica en ningún servidor.**

## V.7 Pendientes Sesión 34+

| # | Ítem | Prioridad |
|---|------|-----------|
| P1 | Rotar `OPENAI_API_KEY` (expuesta en chat durante setup) | Alta |
| P2 | ~~Desplegar OpenAI en Bogotá~~ ✅ Sesión 35 | ✅ Listo |
| P3 | Mejorar calidad de respuestas (prompts/tools) — diferido | Media |
| P4 | Documentar en wizard instalación: pasos OpenAI Limits + `.env` | Media |

---

# Parte W — Sesión 35 (23 mayo 2026) — Sync completo + fixes UI + OpenAI producción

## W.1 Sync .205 → shomerbogota

Primera sincronización completa de código entre servidores vía Tailscale SSH.

**Qué se sincronizó:**
- `/opt/network_monitor/app/` — código completo (templates, API, scripts)
- `/storage/shomer-agent/` — bot completo (excluyendo `.env` y `data/`)

**Qué NO se copió (datos locales de cada sitio):**
- `/storage/db/network_monitor.db` — BD de Bogotá tiene su propia red 192.168.10.x
- `/storage/shomer-agent/data/` — devices.json, conversations.db propios de Bogotá

**Post-sync en Bogotá:**
- `modules.enabled` actualizado a todos los módulos (inframonitor, noc, incidents, audit)
- Variables OpenAI agregadas al `.env` (misma key, mismos límites que .205)
- Bot reconstruido (`docker compose build --no-cache`) y reiniciado — 20 monitores activos

## W.2 OpenAI en producción (ambos servidores)

- `OPENAI_BIND_IP` vaciado — OpenAI funciona por cable en .205 y Bogotá
- `shomer-openai-routes.service` deshabilitado en .205 (workaround WiFi ya innecesario)
- Bogotá: mismo `gpt-4o-mini`, mismos límites (12k tokens/día), fallback Groq automático

## W.3 Tailscale SSH ACL

Configurada en consola Tailscale para permitir SSH server→server sin re-auth web:

```json
"ssh": [
    {
        "action": "accept",
        "src": ["juanpacerodiaz@gmail.com"],
        "dst": ["autogroup:self"],
        "users": ["autogroup:nonroot", "root"]
    }
]
```

**Nota formato:** La cuenta usa el formato nuevo `"grants"` — `dst: "autogroup:member"` e IPs directas son inválidos en este formato; solo `"autogroup:self"` funciona para dst SSH.

## W.4 Protector — UI compacta (3 tarjetas)

Reemplazados los 3 paneles colapsables grandes por una fila de 3 tarjetas compactas en `/backups`:

| Tarjeta | Contenido |
|---------|-----------|
| Restore Drill | Estadísticas 3 números + botón Ejecutar + historial toggle |
| Reportes PDF | Fecha último reporte + botón Mes actual + tabla compacta |
| Object Lock B2 | Estado + campo días retención (default 90) + botón Activar |

**Object Lock mejorado:**
- Campo `lock_days` (input numérico 7–365 días) en UI
- API `POST /b2/object-lock/enable` acepta `body.lock_days`
- B2 API recibe `defaultRetentionMode: "compliance"` + `defaultRetentionPeriod: {unit:"days", duration: N}`
- Período guardado en `protector.b2_lock_days` en `system_state`
- `GET /b2/object-lock/status` devuelve `lock_days` guardado
- Input se deshabilita si ya está activado

**Error B2 mejorado:** timeout muestra "Sin conexión a internet o credenciales B2 inválidas" en lugar de error genérico.

## W.5 Fix Inframonitor — botón Guardar

**Bug:** `addDevice()` usaba `document.querySelector('.btn-add')` pero el botón tiene clase `btn btn-blue`. `btn` era `null` → función fallaba silenciosamente → nada pasaba al hacer clic.

**Fix:** `document.querySelector('[onclick="addDevice()"]')` — selector por atributo, robusto al cambio de clases.

Aplicado en .205 y Bogotá.

## W.6 Módulos habilitados (ambos servidores)

`modules.enabled` en `system_state` incluye ahora todos los módulos:
```
['guardian', 'hunter', 'tracker', 'protector', 'inframonitor', 'noc', 'incidents', 'audit']
```

En instalaciones nuevas: `get_enabled_modules()` ya hace `set_config(MODULES_ENABLED_KEY, ALL_MODULES)` si el key no existe — pero en servers con BD antigua hay que ejecutar el set manualmente una vez.

---

# Parte X — Sesión 36 (27 mayo 2026) — Impresoras + Estado del Sistema

## X.1 Driver impresoras todo-terreno (`drivers/printer.py`)

Nuevo driver en el agente Shomer para monitorear cualquier impresora de red. Estrategia de detección por capas sin configuración manual:

```
1. Ping ICMP                → ¿está en la red?
2. TCP port 9100            → ¿tiene puerto de impresión?
3. SNMP GET sysDescr        → si responde: impresora laser/network (HP, Xerox, etc.)
   - hrPrinterStatus OID    → estado exacto (idle/printing/error)
   - Piper1OutputIndex walk → % tóner (aprox) si disponible
4. ESC/POS DLE EOT          → si no respondió SNMP: térmica/POS (Epson TM-U220, etc.)
   - bytes [0x10,0x04,0x01] → respuesta decodifica: papel OK/fuera, error, online
```

**Detección transparente:** el sistema prueba SNMP primero (laser), cae a ESC/POS (POS/térmicas). El técnico no configura el protocolo — solo agrega la IP.

**Campo `snmp_community`:** default `public` (cubre ~90% de lasers). Override opcional en Inframonitor si el cliente usa comunidad personalizada.

**Tools del bot (2 nuevas en `core/tools.py`):**

| Tool | Parámetros | Qué hace |
|------|-----------|---------|
| `get_printer_status` | `ip`, `snmp_community` | Ping + TCP + SNMP/ESC/POS → estado, papel, tóner, método detectado |
| `clear_print_queue` | `pc_ip` | SSH al PC Windows con `base.service_user/password` → `net stop spooler && del PRINTERS\\* && net start spooler` |

## X.2 Inframonitor — campo `snmp_community` + alertas impresora

**Migración BD:** `ALTER TABLE infra_devices ADD COLUMN snmp_community TEXT DEFAULT 'public'` — auto al init.

**UI (`inframonitor.html`):** selector de tipo tiene `onchange=”onTypeChange()”` — al elegir `printer` o `pos`:
- Muestra campo SNMP community (default `public`)
- Auto-rellena puerto sugerido `9100`

**Alertas Telegram (`_send_infra_alert`):** cuando `device_type in (“printer”, “pos”)` el mensaje usa “🖨️ IMPRESORA FUERA DE LÍNEA” en lugar del genérico “📡 EQUIPO SIN RESPUESTA”.

## X.3 Rediseño Estado del Sistema (`/system-status`)

### Backend (`shomer_system_status.py`) — cambios

| Campo nuevo | Fuente | Descripción |
|------------|--------|-------------|
| `wan` | Redis `wan_status` → fallback ping 8.8.8.8 | `{ok, status, source, latency_ms}` |
| `guardian` | Redis `status:*` → fallback SQLite `devices.status` | `{total, online, offline, ok}` |
| `last_backup` | `backup_devices` tabla | `{ok, last_at, last_name, last_status, failed, total}` |
| `hunter_stats` | `blocked_ips` tabla | `{active_blocks, blocks_24h, ok}` |

**Bug corregido:** Redis key era `node_status:*` pero Guardian escribe `status:*` → conteo siempre 0. Fix: buscar `status:*`.

**`shomer-agent` agregado** a lista `SERVICES` (ahora 8 servicios monitoreados).

**NICs simplificadas:** solo `name`, `is_up`, `ipv4` (removidos IPv6, contadores de tráfico).

### Frontend (`system_status.html`) — layout nuevo

```
Fila 1: 4 tarjetas ejecutivas (borde coloreado por estado)
   ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │ 🌐 WAN   │  │ 👁 Guardian  │  │ 🛡 Backup    │  │ 🎯 Amenazas  │
   │ ONLINE   │  │  3 / 3       │  │  Último OK   │  │  2 activas   │
   └──────────┘  └──────────────┘  └──────────────┘  └──────────────┘
Fila 2: 8 pills de servicios systemd (incl. shomer-agent)
Fila 3: Recursos (CPU%, RAM% con número grande + barra simple)
         Discos (3 particiones — Sistema/Backups/Logs con %)
Fila 4: NICs — chips horizontales con UP/DOWN + IPv4
Fila 5: Consola logs — colapsada por defecto, 8 tabs (incl. shomer-agent)
```

**Colores tarjetas ejecutivas:**
- Verde (`--online`): ok
- Ámbar (`#d97706`): degradado / sin datos
- Rojo (`var(--offline)`): fallo / WAN caída / IPs activas bloqueadas

**Auto-refresh:** cada 30 segundos.

## X.4 Guardian — IP color + Dockerfile fix

**IPs color:** `.td-ip` cambió de `var(--text)` → `#06b6d4` (mismo cyan que Tracker/Protector).

**Dockerfile agente:** `RUN --network=host apt-get update && apt-get install -y openssh-client sshpass iputils-ping snmp` — necesario para que BuildKit no pierda red durante el build de apt.

## X.5 Estado servidores al cierre Sesión 36

| Servidor | Guardian | WAN | Bot | Impresoras |
|---------|---------|-----|-----|-----------|
| .205 (Utah) | 3/3 online ✅ | online ✅ | activo ✅ | driver listo |
| Bogotá | sync ✅ | online ✅ | activo ✅ | driver listo |

---


# Parte Y — Sesión 37 (27 mayo 2026) — Bot/IA en NOC + Estado del Sistema + Inframonitor

## Y.1 Estado del Sistema — sección NICs + Bot/IA en grid 2 columnas

La sección "Interfaces de red" pasó de fila sola a **grid 2 columnas**:
- Columna izquierda: NICs (igual que antes)
- Columna derecha: tarjeta **Bot / Agente IA**

Tarjeta Bot muestra:
- Contenedor Docker: `running` / `stopped` (badge coloreado)
- Proveedor LLM: OPENAI / GROQ
- Modelo: `gpt-4o-mini` o `llama-3.3-70b`
- Uptime del contenedor

### Backend nuevo en `shomer_system_status.py`

`_get_agent_status()` — lee Docker inspect para estado + uptime (nanosegundos truncados), lee `.env` para proveedor y modelo. Añadido al response de `/api/system-health` como campo `agent`.

**Fix parsing uptime:** `datetime.fromisoformat` no acepta nanosegundos (9 decimales). Solución: `raw = parts[1].split(".")[0] + "+00:00"`.

## Y.2 Inframonitor — 4ta tarjeta "Caídas 24h"

Stat-bar tenía 3 tarjetas (En línea / Fuera de línea / Total) + timestamp.
Ahora tiene 4: se agrega **Caídas 24h** (⚠️ ámbar) contando equipos distintos que estuvieron offline en las últimas 24 horas.

Backend: `/infra/devices` devuelve campo `outages_24h` desde:
```sql
SELECT COUNT(DISTINCT ip) FROM infra_status
WHERE status='offline' AND checked_at > datetime('now', '-24 hours')
```

Frontend: `updateStats(devices, outages_24h)` recibe el valor y lo muestra.

## Y.3 NOC — tarjeta "Agente IA"

Columna derecha del NOC (Security + Resources) ahora tiene 3er card: **Agente IA**.

Grid 2×2 dentro de la tarjeta:
- Contenedor (estado + uptime)
- Proveedor LLM + modelo

Backend: `_agent_status()` en `shomer_noc.py` (lógica idéntica a `shomer_system_status.py`).
Campo `agent` añadido al response de `/noc/data`.

## Y.4 Estado al cierre

Ambos servidores sincronizados. Bot/IA visible en:
- `/system-status` — tarjeta lateral junto a NICs
- `/infra` — 4ta stat card Caídas 24h  
- `/noc?token=...` — 3er card columna derecha

---

# Parte Z — Sesión 38 (27 mayo 2026) — SNMP completo en Inframonitor

**Arquitectura actual (Sesión 57, 19 jun 2026):** el poller vive en `shomer-inframonitor-poller.service` independiente. `/infra/status` lee Redis-first. SQLite en WAL mode. Ver §AS para detalle completo.

## Z.1 Qué se implementó

SNMP v2c de lectura integrado al poller de Inframonitor. Sin código nuevo en Guardian ni en el bot — todo vive en `app/api/shomer_inframonitor.py` y `app/templates/inframonitor.html`.

### Datos que obtiene SNMP por equipo

| Dato | OID | Disponibilidad |
|------|-----|----------------|
| Modelo / firmware | `sysDescr` (1.3.6.1.2.1.1.1.0) | Universal |
| Uptime del equipo | `sysUpTime` (1.3.6.1.2.1.1.3.0) | Universal |
| Hostname configurado | `sysName` (1.3.6.1.2.1.1.5.0) | Universal |
| Estado puertos (UP/DOWN) | `ifOperStatus` (ifTable) | Universal |
| Velocidad negociada | `ifSpeed` (ifTable) | Universal |
| Tráfico Rx/Tx en Mbps | `ifInOctets` / `ifOutOctets` | Calculado entre polls |
| Errores por puerto | `ifInErrors` / `ifOutErrors` | Universal |

### Lo que NO hace (sin cambiar nada)
- No SSH, no reboot, no failsafe — Inframonitor sigue siendo solo monitoreo
- No SNMP SET — solo lectura (comunidad GET)
- CPU/RAM del equipo: no implementado (vendor-specific, baja prioridad)

## Z.2 Arquitectura técnica

### Nuevas funciones en `shomer_inframonitor.py`

| Función | Tipo | Descripción |
|---------|------|-------------|
| `_parse_iftable(output, prev_snmp)` | sync | Parsea walk de `1.3.6.1.2.1.2.2.1` — soporta output simbólico (`IF-MIB::ifDescr.2`) y numérico (`1.3.6.1.2.1.2.2.1.2.2`). Retorna `(interfaces list, raw_octets dict)` |
| `_snmp_poll(ip, community, prev_snmp)` | sync/thread | 2 llamadas: `snmpget` (sys info) + `snmpwalk` (ifTable completa). Calcula delta Mbps vs poll anterior. Maneja wrap Counter32 (4294967295). Timeout 4s. |

### Flujo en `_poll_once()`

```
1. Fetch devices + existing (con snmp_data) de BD
2. Ping + TCP en paralelo (sin cambios)
3. MAC lookups (sin cambios)
4. SNMP — para cada device con snmp_community != '':
   ├── Leer prev_snmp de existing[“snmp_data”] (para delta tráfico)
   └── asyncio.to_thread(_snmp_poll, ip, community, prev_snmp)
   Todo en paralelo → snmp_map: {ip → result}
5. INSERT infra_status con snmp_data (JSON) y snmp_ok (0/1/NULL)
```

**Impacto en latencia del poller:** SNMP corre en paralelo con MAC lookups y entre sí. Overhead máximo = 1 timeout (4s) independiente del número de equipos.

### DB — nuevas columnas en `infra_status`

```sql
ALTER TABLE infra_status ADD COLUMN snmp_data TEXT;       -- JSON completo con _raw_octets
ALTER TABLE infra_status ADD COLUMN snmp_ok INTEGER;      -- 1=OK, 0=falló, NULL=no configurado
```

Migración automática al arrancar `_init_tables()`.

### Nuevo endpoint

`GET /infra/snmp/{ip}` → JSON con sistema + interfaces (sin claves `_raw_*` internas).

## Z.3 UI — `inframonitor.html`

### Campo SNMP en formulario
Antes visible solo para `printer` / `pos`. Ahora visible para: `switch`, `router`, `server`, `nas`, `printer`, `pos`, `ups`, `controller`.

Puertos TCP sugeridos automáticamente al elegir tipo:
- `switch` / `router` → 443
- `server` → 443
- `nas` → 5000
- `printer` / `pos` → 9100

### Badge en tabla
- `SNMP ✓` verde → equipo responde SNMP
- `SNMP ✗` rojo → comunidad incorrecta o equipo no soporta SNMP
- Sin badge → sin comunidad configurada (NULL)

### Modal de detalle
Botón **SNMP** aparece en columna Acciones cuando `snmp_ok !== null`. Click abre modal con:

```
Modelo/firmware      Hostname SNMP       Uptime equipo
──────────────────   ─────────────────   ─────────────────
Cisco IOS 15.2...    SW-Piso1            8 días, 12:04:11

Interfaces (12)  ● 4 activas  ✕ 8 inactivas
Puerto   Estado  Velocidad  ↓ Rx        ↑ Tx         Errores
Gi0/1    UP      1G         1.24 Mbps   0.31 Mbps    0
Gi0/2    UP      100M       0.08 Mbps   0.02 Mbps    0
Gi0/5    DOWN    —          —           —             —
Gi0/8    UP      100M       0.00 Mbps   0.00 Mbps    14 ⚠️
```

Tráfico disponible a partir del segundo poll (30s después de agregar el equipo).

## Z.4 Configuración requerida en el equipo (lado cliente)

Todo switch/router/firewall managed necesita:

1. Activar SNMP v2c en su panel de administración
2. Definir comunidad de **solo lectura** (ej: `shomer2026` o el default `public`)
3. Restringir acceso SNMP **solo desde IP del Shomer** — nunca wildcard
4. Verificar que UDP 161 no esté bloqueado en el firewall del equipo

**Ejemplo configuración (Cisco IOS):**
```
snmp-server community shomer2026 RO
snmp-server host <IP_SHOMER> shomer2026
```

**Ejemplo configuración (panel web HP/Aruba/D-Link):**
Management → SNMP → Community → Read Only → `shomer2026` → Source: `<IP_SHOMER>`

## Z.5 Prueba rápida antes de agregar al panel

```bash
# Desde el Shomer, verificar que SNMP responde:
snmpget -v2c -c shomer2026 <IP_SWITCH> 1.3.6.1.2.1.1.1.0
# Respuesta esperada: STRING: “Cisco IOS Software...”

# Ver interfaces:
snmpwalk -v2c -c shomer2026 <IP_SWITCH> 1.3.6.1.2.1.2.2.1.2
# Respuesta: ifDescr.1 = lo, ifDescr.2 = Gi0/1, etc.
```

Si responde → agregar en `/infra` con esa comunidad.

---

# Parte AA — Sesión 41 (31 mayo 2026) — UI polish + fixes Hunter/NOC/PDF

## AA.1 Tracker — unificación indicador de progreso

`inventory.html` — las tres funciones de escaneo usan ahora `showProcessBanner` / `hideProcessBanner` (barra amarilla animada del header global) en lugar del spinner inline `setBtnRunning`. Aplica a:
- `handleScan()` — “Escaneando red — puede tardar hasta 90 segundos…”
- `handleDeepScan()` — “Escaneo profundo en progreso…”
- `rescanSegment()` — “Escaneando segmento…”

## AA.2 Reportes — rediseño de página

`app/templates/reportes.html` reescrito:
- Eliminados: botones de acceso rápido (Este mes / Mes anterior / etc.), ícono 📊 del título, spinner `<div>` inline, sección “Reportes generados” (tabla de historial)
- Mantenido: solo las fechas y el botón “Descargar PDF” — usa `showProcessBanner`/`hideProcessBanner`
- Agregada imagen de ojos Shomer al fondo (fuera del `.rep-wrap` para no recortarse): `<img src=”/static/img/shomer-eyes.png”>`
- `app/static/img/shomer-eyes.png` — imagen con SHOMER + ojos completos (sin barras grises), copiada desde fuente limpia, 228 KB
- `base.html` — agregado `<span class=”nav-dot”></span>` al ítem Reportes (estaba faltando)

## AA.3 Logos USB — tamaño aumentado

- **Login page** (`login.html`): `.logo-usb` 130px → 220px
- **Sidebar** (`base.html`): `.sb-logo-img img` 145px → 185px

## AA.4 Hunter — Riesgos de Red: bugs corregidos

**Archivo:** `app/templates/hunter.html`

| Bug | Fix |
|-----|-----|
| Contador “Total” incluía terminados | `findings.length` → `active.length`; renombrado “Total” → “Activos” |
| Terminados visibles por defecto | `applyRiskFilters` con status vacío ahora excluye `terminado`; solo se muestran al seleccionar “Terminado” en filtro |
| Re-escaneo no reseteaba terminados | `_save_findings()` en `shomer_audit_network.py`: si existing es `terminado` pero el puerto sigue abierto → cambia a `pendiente` |
| Hostname no visible | Fila IP ahora muestra hostname debajo en gris (`font-size:10px`) |
| Filtro IP no buscaba hostname | `applyRiskFilters` también busca en `f.hostname.toLowerCase()` |
| PDF no descargaba (error 500) | `downloadReport()` cambiado de `a.click()` a `fetch + blob + URL.createObjectURL` — maneja auth correctamente y muestra error real |

## AA.5 NOC — 5ta tarjeta KPI “Riesgos de Red”

**Archivo:** `app/templates/noc.html`

- **Eliminada** la barra horizontal `<!-- RISK BAR -->` (no escalaba con muchos equipos)
- **Agregada** 5ta tarjeta en `kpi-row`: `🛡️ Riesgos de Red`
- CSS `.kpi-row`: `repeat(4, 1fr)` → `repeat(5, 1fr)`
- `renderRisks()` eliminada — lógica folded dentro de `renderKpi(d)` usando `d.risks`
- Color de la tarjeta: verde (sin riesgos), ámbar (medios/bajos), rojo (críticos/altos)
- Subtítulo: desglose compacto `”4 🟡 · 2 🔴”` o `”sin riesgos pendientes”`
- `shomer_noc.py` ya tenía `_risk_findings()` desde Sesión 40 — sin cambios en backend

## AA.6 PDF Riesgos de Red — fix UnicodeError fpdf

**Archivo:** `app/api/shomer_reports.py`

**Causa raíz:** fpdf usa fuente Helvetica con encoding latin-1. El `period_label` de `_custom_range()` contiene `–` (en dash U+2013). Los literales de f-string en `header()`, `footer()` y `section()` contenían `—` (em dash U+2014). Ambos fuera del rango latin-1.

**Fixes:**
- `header()`: `_safe(f”{site} -- Riesgos de Red {period_label}”)` — aplica `_safe()` a toda la cadena
- `footer()`: `_safe(f”Pagina {n} -- Shomer Sentinel -- ...”)` — sin tildes ni em dash
- `section(title)`: `pdf.cell(..., _safe(f” {title}”), ...)` — saneado en la función
- Títulos de sección: `”AUDITORÍA DE RED — ...”` → `”AUDITORIA DE RED -- ...”` (ASCII directo)
- `port_str`: `”—“` → `”--”` cuando no hay puerto
- `os.makedirs(REPORTS_DIR)` eliminado de `_generate_audit_pdf` — usa tmpfile, no necesita esa carpeta

**Bogotá:** `/srv/shomer_reports` creado con `chown usb_admin:usb_admin` (faltaba en instalación nueva).

## AA.7 Estado servidores al cierre Sesión 41

| Servidor | Panel | PDF auditoria | NOC 5 KPIs | Sincronizado |
|---------|-------|--------------|-----------|-------------|
| .205 (Utah) | ✅ | ✅ 2.4 KB OK | ✅ | — |
| Bogotá `.119` | ✅ | ✅ 3.1 KB OK | ✅ | ✅ rsync completo |

---

# Parte AB — ✅ COMPLETO (Sesión 43)

*Todos los ítems implementados en Sesión 43. Ver §AC §AC.6 para detalle técnico.*

## AB.1 Estado final

### ~~1. Alerta Telegram cada 8h — hallazgos pendientes~~ ✅ Cubierto por `watch_network_audit`

**Qué hace:** si hay hallazgos activos (`finding_status != 'terminado'`) en `network_audit_findings`, el bot envía un resumen cada 8h al técnico hasta que todos queden en terminado.

**Dónde:** nuevo monitor en `/storage/shomer-agent/core/monitor.py` — `watch_audit_findings`.

**Lógica:**
```python
# cada 8 horas
findings = get_network_audit_findings()  # tool existente o shomer_api.py
active = [f for f in findings if f[“finding_status”] != “terminado”]
if active:
    counts = {critico, alto, medio, bajo}
    msg = “🔴 RIESGOS DE RED PENDIENTES\n{counts}\nRevisar en panel Hunter → Riesgos de Red”
    send_telegram(msg)
# si active vacío → no enviar nada (silencio = todo OK)
```

**Anti-spam:** no enviar si no hay activos. No repetir si ya se envió hace menos de 8h y el estado no cambió.

---

### 2. Tool del agente — ejecutar escaneo de auditoría

**Qué hace:** el técnico le dice al bot “escanea la red” o “actualiza riesgos” → el bot llama al endpoint `POST /audit/network/scan` → espera → informa resultado.

**Dónde:** `core/tools.py` — nueva tool `run_network_audit_scan` (tool 17).

```python
{
  “name”: “run_network_audit_scan”,
  “description”: “Ejecuta un escaneo de auditoría de red (nmap -sV) sobre los activos del Tracker. Tarda 2-5 minutos. Úsalo cuando el técnico pida actualizar riesgos, escanear la red o re-auditar.”,
  “parameters”: {}
}
```

**Implementación en `shomer_api.py`:**
```python
async def run_network_audit_scan() -> dict:
    r = await post(“/audit/network/scan”)
    # El endpoint retorna inmediatamente con scan_id
    # Esperar con polling /audit/network/status hasta status='completed'
    for _ in range(30):  # max 5 min
        await asyncio.sleep(10)
        s = await get(“/audit/network/status”)
        if s.get(“status”) in (“completed”, “failed”):
            return s
    return {“status”: “timeout”}
```

---

### 3. Auditoría de parches vía SSH (Tracker credentials)

**Contexto decidido en sesión:**
- `nmap --script vuln` → **DESCARTADO** (intrusivo, lento, puede disparar IDS)
- Credenciales de Tracker → **APROBADO** (SSH ya autorizado, misma conexión que inventario)

**Flujo en `shomer_audit_network.py` — después del nmap:**

```
Para cada IP escaneada:
  1. Consultar inventory.db → assets (os_family) + network_credentials (ssh user/pass)
  2. Si tiene credenciales SSH y os_family in ('linux', 'darwin'):
       → SSH → correr comando según OS
       → parsear salida
       → si hay actualizaciones pendientes → guardar hallazgo
  3. Windows: SKIP por ahora (impacket no instalado)
```

**Comandos por OS:**

| OS | Comando | Cómo parsear |
|----|---------|-------------|
| Linux apt | `apt list --upgradable 2>/dev/null \| grep -c “upgradable”` | número de paquetes |
| Linux apt (detalle) | `apt list --upgradable 2>/dev/null \| grep -v “Listing”` | lista con versiones |
| Linux yum/dnf | `yum check-update -q 2>/dev/null \| wc -l` | número de paquetes |
| macOS | `softwareupdate -l 2>&1` | líneas con `-` al inicio = updates |
| Linux (kernel) | `apt list --upgradable 2>/dev/null \| grep linux-image` | si hay → severidad crítico |

**Hallazgo generado:**
```python
{
  “category”: “actualizacion”,
  “title”: f”{N} actualizaciones pendientes ({os_label})”,
  “severity”: “critico” if kernel_update else “medio” if N > 10 else “bajo”,
  “description”: “Paquetes: openssh-server 9.2→9.6, curl 7.88→8.4...”,
  “recommendation”: “Ejecutar: sudo apt update && sudo apt upgrade -y”
}
```

**Problema técnico resuelto:** `network_audit_findings` está en `network_monitor.db` pero las credenciales están en `inventory.db`. Solución: abrir ambas DBs en la misma función usando `get_db()` para la primera y `sqlite3.connect(INVENTORY_DB)` para la segunda. El path de `inventory.db` se obtiene desde `app.backend.db.INVENTORY_DB` o `get_config(“tracker.db_path”)`.

**Windows (futuro):** cuando se instale `impacket` en el venv, consultar `Win32_QuickFixEngineering` y `Win32_ReliabilityStabilityMetrics` para saber cuántos días sin parchear.

## AB.2 Archivos a tocar en Sesión 42

| Archivo | Qué se agrega |
|---------|--------------|
| `app/api/shomer_audit_network.py` | función `_patch_check_ssh(ip, user, password, os_family)` + llamada después del nmap |
| `/storage/shomer-agent/core/monitor.py` | monitor `watch_audit_findings` cada 8h |
| `/storage/shomer-agent/core/tools.py` | tool 17 `run_network_audit_scan` |
| `/storage/shomer-agent/core/shomer_api.py` | `run_network_audit_scan()` con polling |

## AB.3 Máquinas de prueba disponibles para Sesión 42

Juan Pablo tiene disponibles para probar la auditoría de parches:

| Equipo | OS | Prueba esperada |
|--------|-----|----------------|
| 2× Windows | Windows | WMI — instalar `impacket` en venv primero |
| 2× Mac | macOS | SSH → `softwareupdate -l` |
| 1× Kali Linux | Linux (apt) | SSH → `apt list --upgradable` |

**Prerequisito:** agregar estas máquinas a Tracker con credenciales SSH/WMI antes de la sesión. El escaneo las tomará automáticamente desde `inventory.db → network_credentials`.

## AB.4 ⚠️ Por verificar — Switches no administrables

**Contexto:** cuando se escanea la red con nmap, los switches no administrables no aparecen. El cliente puede preguntarse por qué no ve sus switches en Inframonitor.

**Explicación técnica (para documentar y comunicar al cliente):**
Un switch no administrable es transparente a nivel IP — no tiene dirección IP, no responde ping, no tiene SNMP ni SSH. Es una limitación de capa 2, no de Shomer.

**Lo que SÍ aparece:** todos los dispositivos conectados detrás del switch (tienen IP y sí responden).

**Técnicas de detección indirecta — evaluar si vale la pena implementar:**

| Técnica | Implementación en Shomer | Complejidad |
|---------|--------------------------|-------------|
| ARP table del router/gateway vía SSH | SSH al router → `show arp` o `cat /proc/net/arp` → múltiples MACs en mismo puerto = switch ahí | Media |
| LLDP neighbors en equipos administrables | SSH → `lldpcli show neighbors` (OpenWrt) o `show lldp neighbors` (Cisco) → topología física | Media |
| DHCP leases del router | SSH → leer tabla DHCP → todos los hosts aparecen, incluso detrás de switch | Baja |
| Captura pasiva Suricata/SPAN | Broadcasts ARP revelan hosts → inferir presencia de switch por patrones | Alta |

**Caso especial a documentar:** algunos switches "no administrables" baratos (TP-Link TL-SG108E y similares) tienen IP de gestión web fija — esos sí se pueden agregar manualmente a Inframonitor y monitorear por ping.

**Acción de campo recomendada (sin código nuevo):**
El técnico agrega el switch manualmente en Inframonitor (`device_type=switch`) con la IP de gestión si la tiene. Si no tiene IP, se documenta en el inventario Tracker como activo físico sin monitoreo automático. Comunicar al cliente que es limitación de capa 2, no del sistema.

**⚠️ Pendiente decidir:** ¿vale la pena implementar detección via ARP/LLDP del router para Sesión 43+? Requiere que el router tenga credenciales en Tracker.

## AB.5 Dependencias y precondiciones

- `asyncssh` ya instalado en el agente → SSH listo
- `inventory.db` en `/storage/db/inventory.db` — verificar path antes de empezar
- El endpoint `POST /audit/network/scan` ya existe en `shomer_audit_network.py`
- Tool calling ya funciona (15 tools activas, agregar la 17 es trivial)
- El monitor 21 (`watch_audit_findings`) sería el monitor 22 si el de auditoría de red ya es el 21

---

# Parte AC — Sesión 42 (1 jun 2026) — Bot: mensajes claros + fixes UX

## AC.1 Resumen de cambios

Sesión enfocada exclusivamente en el agente Telegram (`/storage/shomer-agent/`). No se tocó el panel web ni el código de `/opt/network_monitor/`.

### Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `core/bot.py` | Comandos renombrados, identidad IA, fix reiniciar/agregar, todos los mensajes reescritos |
| `core/monitor.py` | Los 56 puntos de alerta reescritos en lenguaje claro para técnicos |
| `core/shomer_api.py` | Nueva función `reboot_guardian_node(ip)` → `POST /reboot/{ip}` en Guardian |

## AC.2 Cambios estructurales

### Comandos renombrados (organizados por módulo)

```
shomer_salud · shomer_reporte_dia · shomer_monitores · shomer_historial
shomer_revertir · shomer_nueva_consulta

guardian_equipos · guardian_diagnostico · guardian_reiniciar · guardian_ping
guardian_clientes · guardian_info · guardian_mantenimiento

hunter_alertas · hunter_bloquear · hunter_desbloquear

instalar · instalar_usuario · instalar_verificar · ayuda
```

### Fixes

| Bug | Fix |
|-----|-----|
| `/reiniciar` no funcionaba para nodos Guardian | Llama a `POST /reboot/{ip}` en Guardian API (tiene SSH/SNMP). Fallback a `devices.json`. |
| `/agregar` pedía password | Nuevo formato: `<ip> <nombre> [vendor]`. Credenciales de `base.service_user/password`. |
| `/sitio` seguía en el código | Eliminado: `cmd_sitio` + `cb_sitio_cancel` removidos. |
| Monitor 21 no aparecía en `/shomer_monitores` | Agregada etiqueta: “🔍 Auditoría de Red (riesgos pendientes)”. |

### Identidad y saludos

- Pregunta “¿quién eres?” → respuesta fija sin LLM (nuevo `_IDENTITY_WORDS`, `_IDENTITY_RESPONSE`)
- Saludos: sin nombre interno del sitio; dice “Hola, soy Shomer Sentinel — tu IA de red”
- `/start`: texto actualizado, mismo estilo

## AC.3 Mensajes reescritos — criterio

**Antes:** mensajes técnicos con jerga (Pipeline, NIC, SSH fallido, firewall_blocked, no_reboot=true, etc.)

**Después:** formato claro para cualquier persona:
- **Qué pasó** — una línea sin jerga
- **➡️ Qué hacer** — acción concreta

Ejemplos representativos:

| Antes | Ahora |
|-------|-------|
| “Pipeline Suricata — DEGRADADO” | “El sistema de detección de amenazas dejó de recibir datos” |
| “⚠️ Solo en BD (sin firewall SSH)” | “Solo registrada — no se aplicó en el firewall” |
| “Fallos acumulados: 3” | “Alertas registradas: 3 (Guardian reinicia al llegar a 5)” |
| “🔴 Patrón anormal — AP-Lobby / falla hardware / inspección” | “AP-Lobby se reinició 3 veces en 24 horas. ➡️ Posible problema de alimentación.” |
| “✅ IP: Reinicio enviado vía Guardian” | “✅ AP-Lobby se está reiniciando. Vuelve en ~60 segundos.” |
| “❌ Zombie :8000: output” | “✅ Puerto 8000 liberado correctamente.” |

Ver `project_sesion42.md` en memoria para tabla completa.

## AC.4 Estado §AB pendientes

| Ítem | Estado |
|------|--------|
| AB.1 — Alerta 8h riesgos pendientes | ✅ Cubierto — `watch_network_audit` (monitor 21) ya alerta cada 6h |
| AB.2 — Tool `run_network_audit_scan` | ✅ Sesión 43 — `core/tools.py` tool 21 + `core/shomer_api.py` |
| AB.3 — Auditoría de parches SSH | ✅ Sesión 43 — `shomer_audit_network.py::_run_patch_audit()` |

## AC.5 Estado bot al cierre Sesión 42/43

| Aspecto | Estado |
|---------|--------|
| Monitores | 21 activos |
| Tools function calling | 21 (agregada `run_network_audit_scan`) |
| Mensajes técnicos al técnico | 0 (todos reescritos) |
| Container | Activo en .205 y Bogotá |

## AC.6 Auditoría de parches — Sesión 43

**Archivos nuevos/modificados:**

| Archivo | Cambio |
|---------|--------|
| `app/api/shomer_audit_network.py` | 4 funciones nuevas: `_get_patchable_assets`, `_patch_check_single`, `_run_patch_audit`, `_extract_live_ips` |
| `/storage/shomer-agent/core/shomer_api.py` | Nueva función `run_network_audit_scan()` con polling |
| `/storage/shomer-agent/core/tools.py` | Tool 21 `run_network_audit_scan` + executor |

**Flujo:** nmap detecta hosts vivos → SSH paralelo (máx 5) a Linux/macOS con credenciales de Tracker → `apt list --upgradable` / `yum check-update` / `softwareupdate -l` → hallazgos categoría `parches` en misma tabla `network_audit_findings`.

**Pendiente:** Windows WMI — requiere instalar `impacket` en venv. Detectado pero marcado como hallazgo informativo hasta entonces.

## AC.5 Estado bot al cierre Sesión 42

| Aspecto | Estado |
|---------|--------|
| Monitores | 21 activos |
| Tools function calling | 20 |
| Mensajes técnicos al técnico | 0 (todos reescritos) |
| Container | Activo en .205. Bogotá pendiente sync. |

---

# Parte AD — Sesión 44 (1 jun 2026) — Hunter Bogotá + stack completo

## AD.1 Trabajo realizado

Bogotá recibió tarjeta de red USB (ASIX AX88179 Gigabit) para espejo de tráfico Hunter. Stack Hunter completo instalado y verificado.

### Cambios en Bogotá (`shomerbogota` — `100.103.148.119`)

| Cambio | Detalle |
|--------|---------|
| USB NIC mirror | `enx9c69d33bc55f` — PROMISC, sin IP, persistente en `/etc/netplan/60-shomer.yaml` |
| cloud-init deshabilitado | `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` — evita que netplan se pise |
| `suricata.yaml` | Interfaz cambiada a `enx9c69d33bc55f` (líneas 581 y 661). Backup en `.bak` |
| `eve-alerts.json` | Nuevo bloque `eve-log` en suricata.yaml — solo alertas para Wazuh (línea ~305) |
| Reglas Suricata | `suricata-update` ejecutado — 66,132 reglas ET activas |
| `wazuh-manager` 4.14.5 | Instalado via apt repo 4.x. Solo manager, sin indexer ni dashboard |
| `ossec.conf` | Copiado de .205 (config probada). Backup en `.bak2` |
| `custom-shomer-block` | Copiado de .205 a `/var/ossec/integrations/` — wrapper shell + script Python |
| `hunter.integration_key` | `1AUxiGFI80r6hQYB7WxAcxj08LetPi3V` (clave única Bogotá) |
| `hunter.enabled` | `true` |
| `hunter.interfaces` | `[“enx9c69d33bc55f”]` |

### Estado stack Bogotá verificado

| Servicio | Estado |
|---------|--------|
| `shomer-guardian` :8000 | ✅ activo |
| `shomer-tools` :8001 | ✅ activo |
| `nginx` :80/:8443 | ✅ activo |
| `redis-server` :6379 | ✅ activo |
| `shomer-agent` (Docker) | ✅ activo |
| `suricata` | ✅ activo — `enx9c69d33bc55f` |
| `wazuh-manager` | ✅ activo |
| `shomer-health-watchdog.timer` | ✅ activo |
| Disco máx | 22% (`/var`) |
| RAM disponible | 13 GB de 15 GB |

## AD.2 Por qué Hunter no muestra alertas todavía

Sin puerto SPAN configurado en el switch, Suricata solo ve tráfico broadcast y el destinado a la MAC de la USB NIC — no todo el tráfico de la red. Para pruebas reales se necesita una de estas dos opciones:

1. **Puerto SPAN en el switch** — configurar port mirroring hacia el puerto donde está la NIC USB
2. **Mirror en el firewall/gateway** — si todo el tráfico pasa por el firewall, configurar `tc mirror` o `ebtables` para copiar el tráfico a la interfaz USB

Para la segunda opción se necesita conocer la marca/modelo del firewall del cliente.

## AD.3 Pendiente antes de cliente real (semana 1 jun 2026)

| # | Ítem | Crítico |
|---|------|---------|
| 1 | Configurar SPAN en switch del cliente o mirror en firewall | ✅ Obligatorio para ver tráfico |
| 2 | Actualizar `base.subnet` y `hunter.subnets` a la red del cliente | ✅ Obligatorio |
| 3 | Agregar nodos Guardian (APs del cliente) desde el panel | ✅ Obligatorio |
| 4 | Configurar `hunter.firewall_ip/user/pass` si el cliente tiene firewall SSH | Opcional para bloqueo real |
| 5 | Cambiar `base.service_user/password` por credenciales del cliente | Recomendado |
| 6 | Configurar Protector B2 si se quieren backups en nube | Opcional |

## AD.4 Próximos pasos producto (post Sesión 44)

| # | Ítem | Estado |
|---|------|--------|
| 1 | **Git local + deploy.sh centralizado** — `tools/deploy.sh` + `tools/servers.txt`. Bogotá ya registrada (`100.103.148.119`). Un comando actualiza todos los servidores. | ✅ Sesión 45 |
| 2 | **Instalación 2 mini PCs Utah** — instalando Ubuntu 22.04 LTS (2 jun 2026). Siguiente paso: correr `install_shomer.sh` y agregar IPs a `servers.txt`. | 🔄 En progreso |
| 3 | B2 y Tailscale se configuran post-install desde wizard del panel y 2 comandos respectivamente — no van en el script | Pendiente post-OS |

## AE — Sesión 45 (2 jun 2026) — Git + deploy.sh + mini PCs

### AE.1 Git local + deploy.sh

Repositorio git local inicializado en `/opt/network_monitor`. Scripts de despliegue centralizados:

| Archivo | Ubicación | Función |
|---------|-----------|---------|
| `deploy.sh` | `tools/deploy.sh` | rsync `app/` + agente → todos los servers; reinicia servicios |
| `servers.txt` | `tools/servers.txt` | Registro de servidores: `tailscale_ip  nombre  descripcion` |

**Uso:**
```bash
# Actualizar todos los servidores registrados
cd /opt/network_monitor && bash tools/deploy.sh

# Actualizar solo uno
bash tools/deploy.sh 100.103.148.119
```

**Servidores registrados (2 jun 2026):**
- `100.103.148.119  shomer-hotelopera  "Hotel Ópera — Bogotá (cliente piloto)"` (renombrado de `shomerbogota` el 7 jun 2026 — nombre de cliente, no de ciudad, para diferenciar entre varios sitios en la misma ciudad)
- `100.75.182.116   shomer245     "Lab Utah — N100 (mini PC 1, LAN 192.168.1.245)"`
- `100.108.17.50    shomer243     "Lab Utah — N95  (mini PC 2, LAN 192.168.1.243)"`

**Al instalar un mini PC nuevo:** agregar su IP Tailscale a `servers.txt` después de la instalación.

### AE.2 Mini PCs nuevos Utah

2 mini PCs físicos en lab Utah. ✅ Instalados y en producción (2 jun 2026).

**Flujo una vez tengan Ubuntu:**
1. Generar paquete desde .205: `bash tools/make_package.sh`
2. SCP del paquete + `sudo bash tools/install_shomer.sh` con `MGMT_IFACE=enp4s0 MIRROR_IFACE=enp2s0`
3. `sudo tailscale up` → autenticar link en browser
4. Agregar IP Tailscale a `tools/servers.txt`
5. Configurar wizard panel + `.env` del agente

**Fixes aplicados al install_shomer.sh (2 jun 2026):**
- Agregado check internet con fallback `curl` (ping puede fallar si gateway LAN no tiene internet)
- Agregado `rsync` y `sqlite3` a la lista apt (no venían en Ubuntu minimal)
- Agregado `chown usb_admin` sobre `/storage/db/` después de crear las BDs (evita BD read-only)

### AE.3 Acceso remoto panel vía Tailscale

Panel nginx ya escucha en todas las interfaces. El bloqueo era UFW (ya tenía reglas 100.64.0.0/10) y `SHOMER_TRUSTED_HOSTS` en runtime.env que no incluía la IP Tailscale.

**Fix aplicado:** `deploy.sh` ahora detecta automáticamente la IP Tailscale de cada servidor y actualiza `SHOMER_TRUSTED_HOSTS` y `SHOMER_CORS_ORIGINS` en `/etc/shomer/shomer-runtime.env`.

**URLs de acceso (requiere Tailscale en el cliente):**

| Servidor | IP LAN | IP Tailscale | URL panel |
|---|---|---|---|
| .205 Utah lab | 192.168.1.205 | 100.100.188.87 | `https://100.100.188.87:8443` |
| shomer-hotelopera (Hotel Ópera) | `192.168.0.250` | 100.103.148.119 | `https://192.168.0.250:8443` (LAN) · `https://100.103.148.119:8443` (Tailscale) |
| shomer245 Utah | 192.168.1.245 | 100.75.182.116 | `https://100.75.182.116:8443` |
| shomer243 Utah | 192.168.1.243 | 100.108.17.50 | `https://100.108.17.50:8443` |

**Credenciales panel:** usuario `root` con contraseña fábrica `shomer2026` → redirige a `/setup`. Usuario `admin` es de uso interno USB Ingeniería (no documentar contraseña).

### AE.4 Tracker — indicador de ficha revisada

Campo `reviewed INTEGER DEFAULT 0` agregado a tabla `assets` en `inventory.db`.

- Al guardar la ficha de cualquier equipo → `reviewed = 1` automáticamente
- Fila en tabla: fondo verde suave + ícono ✓ verde (antes era lupa gris)
- Sin columna extra — mismo espacio en la tabla

**Archivos modificados:**
- `app/api/inventory_db_schema.py` — `reviewed` en `ASSETS_NEW_COLUMNS` (migración auto)
- `app/api/inventory_asset_edit.py` — `reviewed` en `ASSET_EDITABLE_FIELDS`
- `app/templates/inventory.html` — CSS `.row-reviewed`, renderTable, saveAsset

### AE.5 Tracker — header título arriba de botones

`inventory.html` — `.page-header` cambió de `flex-direction: row` a `flex-direction: column` con `gap: 12px`. Título “Tracker — Inventario IT” queda encima de los botones de acción (igual que Guardian y Hunter). Botones con `flex-wrap: wrap`.

---

# Parte AF — Sesión 46 (4 jun 2026) — Hunter RouterOS + Impresoras SNMP + Bot POS

## AF.1 Hunter — soporte MikroTik RouterOS nativo

Hunter ya no requiere enviar un router OpenWrt al cliente. Si el cliente tiene un MikroTik RouterOS, el bloqueo se hace directamente con comandos nativos `/ip firewall address-list`.

### Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `app/api/casador_support_firewall.py` | Nuevas funciones `_routeros_block`, `_routeros_unblock`, `_routeros_sync_block` via asyncssh |
| `app/api/casador_support_state.py` | Campo `type` en `_get_firewall_creds()` — lee `hunter.firewall_type` de BD |
| `app/api/casador_support.py` | Re-exports de las 3 funciones RouterOS |
| `app/api/casador_blocking.py` | Helpers `_fw_type()`, `_fw_block()`, `_fw_unblock()`, `_fw_sync_block()` — enrutan a RouterOS o OpenWrt según `hunter.firewall_type` |
| `app/templates/hunter.html` | Selector tipo firewall + hint de regla RouterOS + banners advertencia subredes |

### Lógica de bloqueo RouterOS

```python
_ROS_LIST = “shomer-blocked”

# Bloquear: agrega a address-list
'/ip firewall address-list add address={ip} list=shomer-blocked comment=”Shomer-Hunter”'

# Desbloquear: busca y elimina
'/ip firewall address-list remove [find where address=”{ip}” and list=shomer-blocked]'

# Sync (verifica antes de agregar):
'/ip firewall address-list print count-only where address=”{ip}” list=shomer-blocked'
```

**Configuración única en el MikroTik (una vez):**
```
/ip firewall filter add chain=forward src-address-list=shomer-blocked action=drop place-before=0
```

**BD:** `hunter.firewall_type` = `”openwrt”` (default) o `”routeros”`. Configurable desde panel Hunter → Firewall.

### Advertencias subredes en Hunter

UI agrega dos banners sobre el campo “Subredes internas”:
- **Teal info:** explica que las subredes aquí listadas **nunca serán bloqueadas** — agregar todas las VLANs del cliente incluida la de huéspedes
- **Rojo warning:** las subredes de huéspedes **no deben** ponerse en el espejo SPAN (Ley 1581 Colombia — privacidad de datos personales)

**Concepto clave — dos funciones distintas:**
| Campo | Función | Ejemplo Hotel Ópera |
|-------|---------|---------------------|
| Subredes internas | Lista de exclusión — IPs de aquí nunca se bloquean | 192.168.0.0/24, 192.168.1.0/24, 192.168.2.0/24, 192.168.3.0/24 |
| NIC espejo (SPAN) | Interface de captura de tráfico | Solo red admin + servidores — nunca VLAN huéspedes |

## AF.2 Inframonitor — impresoras tóner y papel via SNMP

### Bug corregido: OID formato HP JetDirect

**Causa raíz:** `snmpget` en equipos HP JetDirect retorna OIDs con prefijo `iso.` en lugar de `.1.`:
```
iso.3.6.1.2.1.1.1.0 = STRING: “HP ETHERNET MULTI-ENVIRONMENT”
```
El parser buscaba `”sysdescr” in lhs_l` o `lhs.endswith(“.1.3.6.1.2.1.1.1.0”)` — ambas condiciones falsas con prefijo `iso`.

**Fix:** usar `.endswith(“.2.1.1.1.0”)` que coincide con ambos formatos:
```python
elif lhs.endswith(“.2.1.1.1.0”):    # sysDescr — HP usa “iso.” prefix
    result[“sys_descr”] = rhs.strip('”')
elif lhs.endswith(“.2.1.1.3.0”):    # sysUpTime
    ...
elif lhs.endswith(“.2.1.1.5.0”):    # sysName
    ...
```

### OIDs impresora (Printer MIB — RFC 3805)

Cuando `device_type in (“printer”, “pos”)`, `_snmp_poll()` consulta además:

| OID | Dato | Valores |
|-----|------|---------|
| `1.3.6.1.2.1.25.3.5.1.1.1` | `hrPrinterStatus` | 3=idle, 4=printing, 5=warmup |
| `1.3.6.1.2.1.43.11.1.1.9.1.1` | `prtMarkerSuppliesLevel` | % tóner (0-100) |
| `1.3.6.1.2.1.43.8.2.1.10.1.1` | `prtInputCurrentLevel` | hojas actuales |
| `1.3.6.1.2.1.43.8.2.1.9.1.1` | `prtInputMaxCapacity` | hojas máximo |

**Campo `result[“printer”]`** en `snmp_data` JSON:
```python
{
    “status”:       “lista”,   # “lista”/”imprimiendo”/”calentando”/”desconocido”
    “toner_pct”:    97,        # 0-100 o None
    “paper_current”: 450,      # hojas o None
    “paper_max”:    500,
}
```

**UI modal:** barra visual tóner + indicador papel + estado.

### Firma de función corregida

```python
def _snmp_poll(ip, community, prev_snmp, device_type=”generic”):
```
Llamada en el poller:
```python
asyncio.to_thread(_snmp_poll, row[“ip”], community, prev_snmp, row[“device_type”] or “generic”)
```

## AF.3 Bot — tools POS y credenciales dinámicas

### `get_pc_credentials(ip)` en `shomer_api.py`

Jerarquía de credenciales para acceso SSH a PCs:
1. `assets.override_user/override_pass` en `inventory.db` (credencial específica del equipo)
2. Fallback → `base.service_user/password` en `system_state` (credencial global del sitio)

### Tool 22 — `get_print_queue_status`

```python
# PowerShell via SSH al PC
Get-PrintJob -ComputerName localhost | Select-Object JobStatus,Document,Size |
  ConvertTo-Json -Compress 2>$null
```
Retorna: `{total_jobs, stuck_jobs, jobs[]}`. Si `stuck_jobs > 0` → el bot sugiere `/hunter_borrar_cola`.

### Tool `clear_print_queue` — actualizada

Ahora usa `get_pc_credentials(pc_ip)` en lugar de credenciales globales hardcodeadas. El técnico puede limpiar la cola de cualquier impresora cuyos credenciales estén en Tracker.

## AF.4 deploy.sh — llaves SSH duales

**Antes:** una sola llave `id_rsa_shomer` para todos los servidores.
**Problema:** mini PCs usan `id_ed25519_shomer`.

**Fix:** `deploy.sh` detecta el servidor y elige la llave:
```bash
if [[ “$ip” == “100.103.148.119” ]]; then
    SSH_KEY=”$HOME/.ssh/id_rsa_shomer”      # Bogotá
else
    SSH_KEY=”$HOME/.ssh/id_ed25519_shomer”  # Mini PCs Utah
fi
```

## AF.5 Estado servidores al cierre Sesión 46

| Servidor | Hunter RouterOS | Impresoras SNMP | Bot tools | Sincronizado |
|---------|----------------|----------------|-----------|-------------|
| .205 (Utah lab) | ✅ código | ✅ código | ✅ 22 tools | — |
| Bogotá `.119` | ✅ sync | ✅ sync | ✅ sync | ✅ |
| shomer245 `.116` | ✅ sync | ✅ sync | ⏳ sin .env bot | ✅ |
| shomer243 `.050` | ✅ sync | ✅ sync | ⏳ sin .env bot | ✅ |

**Pendiente único próxima sesión:** flashear 2 MikroTik RB760iGS a OpenWrt — procedimiento en §E.5.

---

# Parte AG — Sesión 47 (4 jun 2026) — Gestión de Técnicos operativo

## AG.1 Qué se hizo

Módulo de métricas de rendimiento por técnico operativo end-to-end en `.205`.

### Bug corregido — auth `shomer_technician.py`

`_require_admin()` usaba `request.state.user` (nunca seteado en este sistema). Reemplazado por `Depends(require_admin)` igual que `shomer_reports.py` y el resto del código.

### `knowledge.db` inicializado

Creado en `/storage/shomer-agent/data/knowledge.db` via `docker exec`. Tablas: `technician_actions`, `incident_knowledge`, `technician_names`. Accesible desde el panel en modo read-only (mismo filesystem, volumen Docker montado).

### Prueba end-to-end

1. Técnico reinició AP `.210` desde bot Telegram
2. `knowledge.db` registró: `telegram_id=6513540405, action_type=reboot, device_ip=192.168.1.210`
3. `GET /api/technician/stats` devolvió métricas calculadas correctamente

## AG.2 Arquitectura

```
Bot Telegram                         Panel web (:8000)
core/bot.py                          app/api/shomer_technician.py
  reboot  → log_technician_action()  GET /api/technician/stats
  block   → log_technician_action()  GET /api/technician/names
  unblock → log_technician_action()  POST /api/technician/names
  guardar → save_knowledge()         GET /api/technician/export
        │                            GET /gestion  (HTML, solo admin)
        ▼
  /storage/shomer-agent/data/knowledge.db
  (volumen Docker — mismo filesystem que panel)
```

## AG.3 Métricas calculadas

| Métrica | Cálculo |
|---------|---------|
| Tasa documentación | `soluciones_guardadas / reboots * 100` |
| Reboots repetidos | mismo equipo >2 veces en el mes |
| Score | `doc_rate - min(reboots_repetidos * 10, 30)` (0–100) |

## AG.4 Pendiente menor

- Registrar nombre real del técnico en `/gestion` → “Técnicos registrados” → Telegram ID `6513540405`
- Sincronizar a Bogotá y mini PCs (cuando tengan bot activo con `.env`)
- El `doc_rate` sube automáticamente cuando el técnico usa “guardar solución” en el bot

## AG.5 Estado servidores al cierre

| Servidor | Panel | Bot | Gestión técnicos |
|---------|-------|-----|-----------------|
| .205 Utah | ✅ | ✅ | ✅ operativo |
| Bogotá `.119` | ✅ | ✅ | ⏳ pendiente sync |
| shomer245 `.116` | ✅ | ⏳ sin .env | ⏳ pendiente |
| shomer243 `.050` | ✅ | ⏳ sin .env | ⏳ pendiente |

---

# Parte M — Histórico “Sesión NN” y lectura única

Las bitácoras largas (migraciones, limpiezas de unidades systemd, bug telegram degradado, etc.) viven en el **historial Git** abril 2026 y en los **informes QA / failsafe** que el equipo físico archiva ese mes — no hay que reproducir ese volumen dentro de cada conversación nueva.

Este manifiesto es la lectura inicial: **estado (Parte A) + normas**. Al cerrar otro hito en campo actualizá la Parte A y la **fecha** del encabezado superior.

*Si esta versión necesita nueva revisión porque otro desarrollador reordena módulo entero Tracker otra vez, fecha encabezado arriba y diff PR pequeños preferidos sobre reescrito completo.*

---


---

# Parte AH — Documentación por sitio cliente (Sesión 47 — 5 jun 2026)

## AH.1 Norma: cada Shomer tiene su propio SITE.md

**CLAUDE.md en .205** = manual de desarrollo (arquitectura, código, normas). No cambia entre clientes.

**`/opt/network_monitor/SITE.md` en cada Shomer** = configuración específica de ese cliente:
- Red y subnets del sitio
- Equipos de red (router, switches, VLANs)
- Configuración SPAN/mirror para Hunter
- Subnets internas del cliente (lista exclusión Hunter)
- Contacto técnico del cliente
- Cualquier particularidad del despliegue

**Por qué:** cada hotel/empresa tiene red distinta, MikroTik distinto, VLANs distintas. Mezclar configs de clientes en CLAUDE.md crea caos. El técnico en sitio lee SITE.md, el desarrollador lee CLAUDE.md.

## AH.2 Plantilla SITE.md mínima

```markdown
# Shomer Sentinel — Sitio: [NOMBRE CLIENTE]

## Identificación
- Nombre: 
- Dirección:
- Contacto técnico (nombre, teléfono):
- Fecha instalación:

## Red
- Subnet admin: 
- Subnet huéspedes (NO bloquear):
- Otras subnets:
- Gateway:

## Router/Firewall
- Modelo:
- IP gestión:
- Usuario SSH/Winbox:
- WAN principal (interfaz):
- WAN respaldo (interfaz):

## SPAN / Mirror Hunter
- Puerto origen (mirror-source):
- Puerto destino (mirror-target):
- Comando aplicado:
- NIC espejo Shomer:

## Hunter — subnets internas
(Copiar aquí todas las subnets — estas IPs nunca se bloquean)

## Shomer
- IP LAN:
- IP Tailscale:
- NIC gestión:
- NIC espejo:

## AH.3 Matriz de equipos y Suricata lab (Sesión 52 — 10 jun 2026)

**Regla deploy producción:** `docs/REGLAS_DEPLOY.md` — autorización Juan Pablo; solo código, nunca config de sitio. `deploy.sh` bloquea Ópera sin `SHOMER_DEPLOY_AUTHORIZED=1`.

**Registro maestro:** `docs/EQUIPOS.md` — tabla de los 4 appliances (`.205`, Ópera, `.245`, `.243`), qué sincronizar con `deploy.sh` y qué **nunca** copiar entre sitios.

| Equipo | Suricata NIC | `SHOMER_LAB_NO_SPAN` | Notas |
|--------|--------------|----------------------|--------|
| `.205` lab | `enp4s0` | ✅ sí | Sin SPAN habitual; bot en desarrollo aquí |
| Ópera | `enx9c69d33bc55f` | ❌ **no** | Producción; SPAN real; `auto_block=false` |
| `.245` / `.243` | `enp2s0` | ✅ sí | Mini PCs Utah; gestión `enp4s0` |

**Post-instalación Suricata (lab):** `sudo MIRROR_IFACE=<nic> bash /opt/network_monitor/tools/suricata_lab_setup.sh` — ruleset ET, symlink `shomer-local.rules`, flag lab opcional.

**Ópera:** no ejecutar ese script sin ventana; ya tiene Suricata operativo con tráfico real.

---

# Parte AI — Sesión 49 (6 jun 2026) — Fix Tracker WMI Windows: software + dominio AD

## AI.1 Problema raíz — wmiexec se colgaba indefinidamente

El escáner Tracker usaba `wmiexec.py` (impacket) para extraer datos de PCs Windows. Esta herramienta funciona así:

```
Shomer → abre sesión WMI en el PC
       → pide a Windows que ejecute cmd.exe
       → cmd.exe intenta escribir resultado en \\127.0.0.1\ADMIN$\__output
       → ese proceso no tiene credenciales de red → cuelga para siempre
```

Resultado: timeout en 100% de PCs Windows. Hardware vacío, software vacío `[]`.

## AI.2 Solución — DCOM directo + PowerShell EncodedCommand + SMB

**Archivo modificado:** `app/scripts/tracker/extractor.py` — función `phase3_wmi`

### Flujo nuevo (3 pasos en paralelo)

```
PASO 1: Conectar a WMI via DCOM (impacket DCOMConnection)
        → NTLMLogin a //./root/cimv2
        → Lanzar PowerShell PRIMERO via Win32_Process.Create
          (corre en background mientras hacemos hardware)

PASO 2: Consultas hardware simultáneas (mientras PS corre)
        → Win32_ComputerSystem   → hostname, modelo, RAM, fabricante
        → Win32_OperatingSystem  → OS, versión, arquitectura
        → Win32_BIOS             → serial number
        → Win32_DiskDrive        → modelo disco, capacidad total

PASO 3: Esperar mínimo 12s desde lanzamiento PS, luego leer via SMB
        → SMBConnection.getFile("C$", "sho_sw.json", ...)
        → Parsear JSON → _filter_software()
        → Borrar archivo del PC remoto
```

**Tiempo total por PC:** ~13 segundos (vs colgarse indefinidamente antes)

### Por qué PowerShell necesita Base64 (EncodedCommand)

PowerShell lanzado via `Win32_Process.Create` recibe el comando como string de Windows. Las comillas anidadas dentro del comando confunden el parser — PowerShell arrancaba (ReturnValue=0, PID asignado) pero nunca escribía el archivo.

**Solución:**
```python
ps_script = "$p='HKLM:\\Software\\...\\Uninstall\\*';$sw=Get-ItemProperty $p..."
encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
ps_cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand " + encoded
```

Base64 en UTF-16LE es el encoding que espera PowerShell para `-EncodedCommand`. Elimina todos los problemas de comillas.

### Por qué Remote Registry (rrp) no funcionó

Primer intento fue leer el registro via SMB pipe `\winreg`. El pipe retorna `STATUS_OBJECT_NAME_NOT_FOUND` porque el servicio **Remote Registry está desactivado por defecto** en Windows 10/11. Intentamos iniciarlo via WMI `ExecMethod('Win32_Service.Name="RemoteRegistry"', 'StartService')` pero requiere permisos adicionales que el usuario de dominio no tiene. **Abandonado — usar PowerShell es más limpio.**

## AI.3 Credenciales dominio AD — convención

Para redes con Active Directory (como Hotel Ópera — dominio `HOTELOPERA`, AD en `192.168.0.4`):

| Campo Tracker | Valor |
|---|---|
| Usuario | `administrador` (sin dominio) |
| Contraseña | contraseña del usuario de dominio |
| Dominio | `HOTELOPERA` |

El código pasa estos 3 campos a `DCOMConnection(ip, username=user, password=password, domain=dom)`. Si el dominio está vacío usa `"."` (cuenta local).

**Equipos fuera del dominio** (PCs con cuenta local `.\sistemas`):
- Usuario: `sistemas`
- Dominio: dejar vacío o `.` — el código hace fallback automático

## AI.4 Bugs corregidos durante la sesión

| Bug | Causa | Fix |
|---|---|---|
| `TypeError: checkNullString` en ExecQuery | Se pasaba `wql.encode('utf-8')` — impacket espera `str` no `bytes` | `ExecQuery(wql)` sin `.encode()` |
| `_filter_software` no encontrado | Al reemplazar `phase3_wmi` se borraron `_SW_INCLUDE_KEYWORDS` y `_SW_EXCLUDE_KEYWORDS` (constantes debajo de la función) | Corregir `end_idx=641` (inicio de las constantes) |
| Timeout 30s insuficiente | Hardware (~12s) + sleep(12) + SMB = ~27s, al límite | Hardcode `t = 55` y PS en paralelo → tiempo real ~13s |
| Software vacío aunque PS arrancara | Comillas anidadas en cmd confundían el parser Windows | `-EncodedCommand` Base64 |

## AI.5 Rendimiento por escenario

| Escenario | Tiempo estimado |
|---|---|
| 100 PCs encendidas (20 paralelas) | ~2 minutos |
| 100 PCs con 20% apagadas | ~4-6 minutos |
| 200 PCs encendidas | ~4 minutos |

El cuello de botella son las PCs apagadas: cada una consume 55s de timeout en su lote.

**Optimización posible:** bajar timeout a 30s en horario de oficina cuando las PCs deben estar encendidas.

## AI.6 Servidores actualizados

`extractor.py` sincronizado a los 4 servidores el 6 jun 2026:
- `.205` Utah lab (local)
- `shomer-hotelopera` (ex-`shomerbogota`) `100.103.148.119` ✅
- `shomer245` `100.75.182.116` ✅
- `shomer243` `100.108.17.50` ✅

## AI.7 Resultado Hotel Ópera

| | |
|---|---|
| Total activos detectados | 76 |
| Windows con WMI OK + software | 13/13 ✅ |
| Impresoras Epson de red | 3 (`.57`, `.58`, `.240`) |
| Con error credenciales (`.\sistemas`) | 3 (`.41`, `.142`, `.170`) |
| Apagados durante escaneo | 2 (HDO-ALMACEN `.110`, `.41`) |
| Servidor restringido (SRVZEUSOP PMS Zeus) | 1 (`.5`) |

**Pendiente:** credenciales `.\sistemas` para los 3 equipos con logon failure.

---

# Parte AJ — Sesión 50 (7 jun 2026) — Bug crítico Suricata: ruleset ET no cargaba (hallazgo general, aplica a cualquier instalación)

## AJ.1 Síntoma

Suricata corría "activo" mostrando solo **1 firma cargada** — la regla de prueba de laboratorio `SHOMER TEST ICMP` (sid 9009001) — generando ~5,344 alertas/día de ruido por pings internos normales de Guardian/Inframonitor. El ruleset ET real de 66,132 reglas (descargado correctamente por `suricata-update`) **nunca se aplicaba** — el pipeline de detección estaba prácticamente ciego en producción.

## AJ.2 Causa raíz — descubre/aplica en cualquier sitio que use `suricata-update`

`suricata-update` descarga el ruleset a `/var/lib/suricata/rules/suricata.rules` (42MB, ~66k reglas), pero **no lo enlaza automáticamente** con el `default-rule-path` configurado en `suricata.yaml` (típicamente `/etc/suricata/rules`). Sin ese enlace, Suricata arranca con: `[ERRCODE: SC_ERR_NO_RULES(42)] - No rule files match the pattern /etc/suricata/rules/suricata.rules`.

**Diagnóstico:** `journalctl -u suricata` muestra ese error claro — revisar siempre tras instalar/actualizar el ruleset.

## AJ.3 Fix aplicado (replicable en cualquier Shomer)

```bash
# 1. Symlink del ruleset descargado al path que Suricata realmente lee
sudo ln -sf /var/lib/suricata/rules/suricata.rules /etc/suricata/rules/suricata.rules

# 2. Validar antes de reiniciar
sudo suricata -T -c /etc/suricata/suricata.yaml -v
# → debe reportar "NN rules successfully loaded, 0 rules failed"

# 3. Reiniciar
sudo systemctl restart suricata
```

Resultado verificado: **50,210 reglas cargadas** (de 50,215 procesadas — el resto son metadatos/clases). Confirmado con alertas reales post-reinicio: detección de SNMP probing externo, escaneo IKEv2 con criptografía débil, anomalías de stream — el pipeline pasó de ciego a funcional.

## AJ.4 Regla de prueba ruidosa — desactivada (general, no solo Ópera)

`shomer-local.rules` traía:
```
alert icmp any any -> $HOME_NET any (msg:"SHOMER TEST ICMP"; itype:8; sid:9009001; rev:1;)
```
Esta firma — pensada para validar el pipeline con un ping de prueba — coincide con **cualquier** ICMP echo request interno, generando alertas constantes por el tráfico normal de monitoreo (Guardian, Inframonitor). **Recomendación general:** comentar/desactivar esta regla tras la validación inicial del pipeline en cualquier sitio nuevo, o acotarla a una IP de prueba específica en vez de `any any`.

```
# DESACTIVADA - generaba ruido con ping interno normal
#alert icmp any any -> $HOME_NET any (msg:"SHOMER TEST ICMP"; itype:8; sid:9009001; rev:1;)
```

## AJ.5 Checklist — agregar a "Práctica habitual campo (Hunter en sitio nuevo)" (ver §A.3)

Tras instalar/activar Suricata en un sitio nuevo, **siempre verificar**:
1. `journalctl -u suricata | grep -i "rules successfully loaded"` — confirmar que el número de reglas cargadas coincide con lo esperado del ruleset (no solo 1)
2. Si el conteo es bajo → revisar symlink `default-rule-path` ↔ destino real de `suricata-update`
3. Desactivar o acotar la regla de prueba ICMP del lab antes de dejar el sitio en operación

## AJ.6 Nota — separación config general vs. config de cliente

Esta sección documenta un **bug de arquitectura/instalación que puede repetirse en cualquier Shomer** (de ahí su lugar en CLAUDE.md). Los valores específicos de Hotel Ópera (`hunter.subnets`, excepciones, NIC espejo, tipo FW) **NO van aquí**: viven en `/opt/network_monitor/SITE.md` del servidor `shomer-hotelopera`, conforme a la norma §AH.1.  

**Nota (17 jul 2026):** una mención antigua en bitácora listaba Eventos como `30.30.0.0/22`. En Ópera **ya no** forma parte de `hunter.subnets` (decisión sitio: `30.30.*` = externas / bloqueables). Fuente de verdad = `SITE.md` actualizado ese día. CLAUDE.md es manual de desarrollo (todos los sitios); SITE.md es config de cliente.

---

# Parte AK — Sesión 51 (9–10 jun 2026) — Tracker Hotel Ópera + monitor integrado + timeout WMI

## AK.1 Hotel Ópera — puesta en marcha Tracker/Hunter

| Corrección | Valor / resultado |
|------------|-------------------|
| `tracker.subnets` | `["192.168.0.0/24"]` (antes incorrecto `192.168.10.0/24`) |
| `base.service_user` | `administrador` + dominio AD `hotelopera` en credenciales Tracker |
| Auditoría de riesgos (scan_id=5) | **76 hosts**, **153 hallazgos** (puertos, web, compartidos, **4 parches** Windows) |
| Rescan Windows (12 PCs clasificados) | **12/12 WMI OK** tras fix timeout — software, usuario logueado, monitores detectados |
| Inventario total | 76 activos (APs UniFi, impresoras, cámaras, PCs) |

**Pendiente Ópera:** deep scan nocturno de toda la subred para clasificar PCs restantes; credenciales locales `.\sistemas` en `.142`, `.170`, `.41`; SPAN en switch para tráfico Hunter completo.

## AK.2 Bug crítico — timeout WMI capado en 30 s

**Síntoma:** PCs Windows con `ERROR: timeout (30s)` en `wmi_status` aunque software o usuario sí se guardaban en escaneos anteriores.

**Causa:** en `extractor.py` → `phase3_wmi()` la primera línea limitaba `t = min(timeout_sec, EXTRACTOR_SSH_WMI_TIMEOUT)` con `EXTRACTOR_SSH_WMI_TIMEOUT=30`, anulando `TIMEOUT_CRITICAL_SEC=45` de `scanner.py`.

**Fix (replicable en cualquier sitio):**

| Archivo | Cambio |
|---------|--------|
| `app/scripts/tracker/extractor.py` | `EXTRACTOR_SSH_WMI_TIMEOUT = 90`; cálculo `t = max(45, min(timeout_sec, 90))` |
| `app/scripts/scanner.py` | `TIMEOUT_CRITICAL_SEC = 90` |

**Verificación:** rescan 12 PCs Ópera → `with_protocol_ok=12`, ~67 s total.

## AK.3 Ficha Tracker — monitor integrado (portátil / All-in-One)

**Archivos:** `app/templates/inventory.html`, `inventory_db_schema.py`, `inventory_asset_edit.py`, `persistence.py`.

**UI:** checkbox *Monitor integrado (portátil / All-in-One)* + campos modelo/serial del panel; selector aparte *Monitores externos adicionales* (0–3). Al marcar integrado, pre-rellena desde `monitors_detected_json` si el escaneo detectó All-in-One o panel interno.

**BD:** `integrated_monitor`, `integrated_monitor_model`, `integrated_monitor_serial` (migración auto `ALTER TABLE`).

## AK.4 Auditoría de parches Windows (Hunter → Riesgos de Red)

**Archivo:** `app/api/shomer_audit_network.py` — parches vía Windows Update COM (PowerShell remoto + lectura SMB `sho_patch.json`), reutilizando helpers de `extractor.py`. Antes: `_patch_check_wmi` con QuickFixEngineering roto → **0 hallazgos parches** en Ópera.

**nmap:** timeout dinámico `min(900, max(300, len(ips)*10))`, `--host-timeout 45s`.

## AK.5 Deploy centralizado — 4 servidores

`bash tools/deploy.sh` (sin argumento) actualiza todos en `tools/servers.txt`:

| Servidor | Tailscale |
|----------|-----------|
| shomer-hotelopera | 100.103.148.119 |
| shomer245 (lab N100) | 100.75.182.116 |
| shomer243 (lab N95) | 100.108.17.50 |

**Origen:** `.205` Utah lab — no está en la lista (es desde donde se empuja). Tras deploy: migrar `inventory.db` con `ensure_assets_table()` en remotos si hay columnas nuevas.

## AK.6 Redes grandes (~750 equipos) — estrategia operativa

No escanear 750 de golpe en horario laboral.

| Fase | Acción |
|------|--------|
| Inicial | Quick scan todas las subredes → lista viva IP/MAC/vendor |
| Deep scan | Por VLAN/subred de noche: `INVENTORY_SCAN_TARGETS="192.168.X.0/24"` |
| Continuo | Quick diario + deep semanal rotando segmentos |
| Manual | Monitor integrado y docks en fichas de PCs críticos (~50–100) |

**Límites código actuales:** OS detection agresiva solo primeros **200 IPs** del discovery; auditoría nmap tope **15 min** global — en redes muy grandes usar escaneos por lote.

## AK.7 Estado servidores al cierre Sesión 51

| Servidor | Tracker WMI fix | Monitor integrado UI | Auditoría parches |
|----------|-----------------|----------------------|-------------------|
| .205 lab | ✅ | ✅ | ✅ |
| shomer-hotelopera | ✅ 12 PCs OK | ✅ | ✅ 153 hallazgos |
| shomer245 / shomer243 | ✅ sync | ✅ | ✅ sync código |

## AK.8 Matriz de políticas agente autónomo (10 jun 2026, v1.1)

Documento operativo: `/storage/shomer-agent/docs/POLITICAS_AGENTE.md`

**v1.1:** Autonomía por **catálogo TASK-001…010** (tareas explícitas), modos **`off` / `learning` / `approved`** por sitio — no IA eligiendo libre. **Capa A** (Guardian reboot, Hunter auto-block Suricata→Wazuh→API→iptables) **no pasa por el bot**. Catálogo ejemplos: limpieza logs ≥85 % (TASK-001), restart servicios Shomer (TASK-002–004), auditoría muestral Protector solo lectura (TASK-006).

Promoción `learning`→`approved`: decisión **USB** tras N éxitos Green State + stats; correlaciona `incident_knowledge` / guardar solución.

---

# Parte AL — Sesión 52 (jun 2026) — Bot Telegram UX unificado

## AL.1 Cambios de producto

| Cambio | Detalle |
|--------|---------|
| **`/start` eliminado** | Sin logo, sin foto, sin teclado inline de bienvenida. Entrada: `/consultas`, `/ayuda`, saludo en texto libre |
| **`/salud` sin botones** | Solo reporte; monitores y resumen vía `/salud monitores` y `/salud resumen` |
| **`/ayuda` completo** | Todos los comandos por módulo + lista de 30 monitores (incl. 5 Infra) |
| **Menú ⋮ Telegram** | 26 comandos en `set_my_commands` (incl. `/monitores`, `/resumen`, aliases; sin `start`) |
| **Alertas una línea** | `fmt.alert_line()` — monitores y triage off por defecto |
| **Knowledge post-acción** | Botones guardar tras reboot, desbloqueo, recuperación; callbacks `save_know:TIPO:IP` |
| **Infra en alertas** | 5 monitores: equipment, printer, service, snmp, flap — tools `get_infra_device` con `prior_solution` |

## AL.2 Archivos

| Archivo | Cambio |
|---------|--------|
| `core/bot.py` | Sin `/start`; `MONITOR_LABELS`/`MONITOR_GROUPS`; `_ayuda_text()` expandido |
| `core/monitor.py` | `_kn()` antecedentes; `_save_kb_after_reboot` / `_save_kb_recovery` |
| `core/fmt.py` | `alert_line()` formato unificado |
| `BEHAVIOR.md`, `TECNICO_OPERACION.md`, `docs/campo/*.md` | Comandos y monitores actualizados |

## AL.3 Docs montados en container

`CLAUDE.md`, `TECNICO_OPERACION.md`, `BEHAVIOR.md`, `SOPORTE_TECNICO.md` — volumen `:ro` en `docker-compose.yml`. Tras editar en host, el bot los ve sin rebuild.

---

# Parte AM — Catálogo TASK + protocolo cambios agente (10 jun 2026)

## AM.1 Catálogo TASK-* y política Ópera

Documento maestro: **`/storage/shomer-agent/docs/CATALOGO_TASK.md`** (v1.1).

**Ópera producción — automático (`approved`):** TASK-001, 002, 003, 004, 005, 006, 008, 009.  
**Siempre `off`:** TASK-007, TASK-010. Reboot AP / Hunter auto = Capa A (panel), no catálogo.

`.env` agente en cada sitio — ver bloque en `CATALOGO_TASK.md` §2. **No** commitear `.env`.

## AM.2 Feedback técnico → aprendizaje (L3–L5 implementado)

| Capa | Estado | Qué hace |
|------|--------|----------|
| **L3** | ✅ | `/guardar` + botones `save_know:*` → `incident_knowledge` + **`agente_skills`** + correlación TASK-* |
| **L4** | ✅ | `BOT_LEARN_AUTONOMOUS=1` — tras Green State OK en TASK-* → skill auto en `agente_skills` |
| **L5** | ✅ | Chat inyecta `agente_skills` + `SITE.md` + knowledge; tool **`get_agente_skills`** |
| Post-TASK | ✅ | Botones `save_task:y/n/o` tras TASK automática |
| Promoción | ✅ | `/aprobar_task TASK-001` (developer) + Telegram sugerencia tras 5 OK en learning |

**Tablas:** `knowledge.db` → `incident_knowledge`, `agente_skills`, `auto_task_stats`.  
**No confundir:** `memory.py` / `conversations.db` = chat IA por usuario.

**Módulos:** `core/agente_skills.py`, `core/learning.py`, `core/llm_router.py` (inyección L5).

## AM.3 Protocolo cambios (Cursor + Claude Code)

Checklist obligatorio al agregar comandos, TASK-011+, o tools:  
**`/storage/shomer-agent/docs/PROTOCOLO_CAMBIOS_AGENTE.md`**

| Documento | Rol |
|-----------|-----|
| `CLAUDE.md` | Dev USB — arquitectura, bitácora sesiones |
| `SITE.md` | **Por Shomer** — red/VLANs/SPAN/config cliente |
| `CATALOGO_TASK.md` | TASK-001…010 + modos por sitio |
| `POLITICAS_AGENTE.md` | Matriz T0–T4, Capas A–D |
| `PROTOCOLO_CAMBIOS_AGENTE.md` | Checklist sin romper prod |
| `BEHAVIOR.md` / manuales `docs/campo/` | IA + técnico campo |

**Deploy agente:** `tools/deploy.sh` desde lab `.205` — no copiar `core/` a mano entre sitios.

---

# Parte AN — Sesión 53 (11 jun 2026) — Bot: fix alertas duplicadas APs Guardian↔Infra

## AN.1 Problema (incidente real Hotel Ópera, 10 jun 2026)

Un parpadeo de red afectó a los ~30 APs UniFi del hotel. El técnico recibió **~41 mensajes de Telegram** en pocos minutos — alerta y recuperación de cada AP **duplicadas**: una vez desde `watch_guardian_nodes` y otra vez desde `watch_infra`.

**Causa:** `_sync_guardian_aps()` (`app/api/shomer_inframonitor.py` — función existente, sin cambios) refleja cada ~30s los APs de Guardian (`devices.device_type='access_point'`) hacia `infra_devices` como `device_type='ap'`, para que la página `/infra` los liste junto a switches/impresoras/etc. `watch_infra` (bot) no sabía distinguir estos reflejos y los trataba como equipos Infra normales → alerta propia además de la de Guardian.

**Bug adicional:** `watch_guardian_nodes` enviaba "✅ Nodo recuperado" en cualquier transición `offline/no-internet → online`, incluso si nunca se había enviado la alerta de caída (porque el debounce de 2 ciclos no llegó a disparar) → mensaje "recuperado" huérfano sin alerta previa.

## AN.2 Fix aplicado — solo `/storage/shomer-agent/core/monitor.py`

Sin tocar `/opt/network_monitor/` (panel/Guardian/Inframonitor) — principio §T.1, "agregar sin tocar lo que funciona".

1. **`watch_guardian_nodes`** — "recuperado" solo si `ip in _guardian_down_alerted` (es decir, solo si se había alertado la caída):
   ```python
   if prev in ("offline", "no-internet") and ip in _guardian_down_alerted and not _is_suppressed(ip):
   ```

2. **`watch_infra`** — ignora por completo `device_type == 'ap'` (son reflejo de Guardian, ya cubiertos por `watch_guardian_nodes`):
   - Excluidos de la lista `offline` usada para alertas grupales/stale.
   - `continue` inmediato en el loop principal por dispositivo.

## AN.3 Decisión de diseño — NOC y `/infra` sin cambios

- **NOC** (`/noc`): nunca tuvo duplicado real. La sección "Infraestructura" del NOC (`TYPE_GROUPS` en `noc.html`) no incluye tipo `'ap'` — esas filas de `infra_devices` son invisibles ahí. Los APs del NOC vienen exclusivamente de `guardian.devices` (cuadrícula superior), independiente de `infra_devices`.
- **`/infra` (panel Inframonitor)**: sigue listando los APs (vía `_sync_guardian_aps`) — es su única utilidad real, dar inventario completo al técnico en un solo lugar. **No se tocó.**
- **Solución "agrupar mensajes en uno solo" — descartada permanentemente** (decisión Juan Pablo, 10 jun 2026): si los mensajes son reales (caída real de 30 APs), no es ruido, es información real — no se debe ocultar agrupando.

## AN.4 Estado de despliegue

| Servidor | `core/monitor.py` actualizado | Bot reiniciado |
|----------|-------------------------------|-----------------|
| `.205` (origen) | ✅ | — (no corre prod aquí) |
| **Hotel Ópera** `100.103.148.119` | ✅ | ✅ — `docker compose restart shomer-agent`, 26 monitores activos, log limpio |
| shomer245 `100.75.182.116` | ✅ código sincronizado | ⏳ agente aún no arrancado (sin container activo — pendiente `.env`/arranque, tema aparte) |
| shomer243 `100.108.17.50` | ✅ código sincronizado | ⏳ ídem |

---

# Parte AO — Sesión 53 cont. (11 jun 2026) — Fix bug rotación backups del agente

## AO.1 Problema (descubierto al hacer backup de checkpoint en Hotel Ópera)

`/backup` (o `create_backup()` en `core/backup_manager.py`) reportaba éxito (`✅ shomer_backup_AAAAMMDD_HHMMSS.tar.gz — N MB`) pero el archivo **no quedaba** en `/storage/shomer-agent/data/backups/` — desaparecía justo después de crearse.

**Causa raíz:** `_rotate()` (mantiene máx. `MAX_BACKUPS=2`) ordenaba los archivos **alfabéticamente por nombre** con `sorted(glob(...))` y borraba `backups[0]` pensando que era el más antiguo. En Hotel Ópera había 2 backups viejos con prefijo `shomer_backup_bogota_...` (de antes del rename Sesión 50, ver §S.1 nota). Alfabéticamente `'2' < 'b'` → el backup **recién creado** (`shomer_backup_20260611_...`) ordenaba primero y `_rotate()` lo borraba a él, dejando los 2 viejos intactos.

**Por qué importa en cualquier sitio:** el bug no es exclusivo de nombres "bogota" — cualquier mezcla de prefijos de archivo cuyo orden alfabético no coincida con el orden cronológico (p. ej. tras un rename de sitio, o archivos copiados manualmente con otro nombre) produce el mismo efecto: el backup más nuevo se autodestruye en `_rotate()`.

## AO.2 Fix aplicado

**Archivo:** `/storage/shomer-agent/core/backup_manager.py` — `_rotate()` y `list_backups()` ahora ordenan por `p.stat().st_mtime` (fecha real de modificación) en vez de por nombre:

```python
def _rotate():
    backups = sorted(BACKUP_DIR_CONTAINER.glob("shomer_backup_*.tar.gz"), key=lambda p: p.stat().st_mtime)
    while len(backups) > MAX_BACKUPS:
        ...

def list_backups() -> list[dict]:
    ...
    for p in sorted(BACKUP_DIR_CONTAINER.glob("shomer_backup_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True):
        ...
```

## AO.3 Limpieza Hotel Ópera (autorizada por Juan Pablo)

Se borraron en `/storage/shomer-agent/data/backups/` los 2 backups obsoletos `shomer_backup_bogota_20260527_*.tar.gz` (231 KB c/u, pre-rename, ya superados) y un archivo de prueba `shomer_backup_test.tar.gz` generado durante el diagnóstico. Tras la limpieza se generó el backup de checkpoint:

- `shomer_backup_20260611_043907.tar.gz` (40 KB) — incluye `network_monitor.db`, `inventory.db`, `shomer-runtime.env`, `.env` agente, units `shomer-guardian`/`shomer-tools`, `nginx/sites-available/*`, `suricata/rules/*` (50,210 reglas ET) — checkpoint con los fixes de §AN ya aplicados.

**Nota `devices.json`:** no existe en Hotel Ópera (`--ignore-failed-read` lo omite sin error) — es el inventario de equipos del **bot** (`/agregar`), normal que no exista si los equipos se gestionan desde el panel web en vez del bot. Existe en `.205` porque ahí sí se usó `/agregar` en pruebas.

## AO.4 Estado de despliegue

| Servidor | `core/backup_manager.py` actualizado | Reinicio agente |
|----------|----------------------------------------|------------------|
| `.205` (origen) | ✅ | — (no corre prod aquí) |
| **Hotel Ópera** `100.103.148.119` | ✅ | ✅ — restart limpio, 26 monitores activos |
| shomer245 `100.75.182.116` | ✅ código sincronizado | ⏳ agente aún no arrancado (mismo pendiente de §AN.4) |
| shomer243 `100.108.17.50` | ✅ código sincronizado | ⏳ ídem |

**Despliegue dirigido** (primera parte): solo `core/monitor.py` (fix APs). **Más tarde el mismo día** (§AO): `deploy.sh` autorizado con código Hunter RouterOS + anti-spam monitores — ver §AO.5.

---

# Parte AO — Sesión 53 (11 jun 2026) — Hunter RouterOS DROP, anti-spam bot, backup lab

## AO.1 Hunter MikroTik RouterOS — regla DROP obligatoria (Hotel Ópera)

**Problema real (jun 2026):** `190.60.195.10` estaba en address-list `shomer-blocked` desde 7/jun y en BD como bloqueada, pero **faltaba** la regla `drop` en `chain=forward` del MikroTik `192.168.0.1`. Suricata (espejo/IDS) seguía generando alertas aunque el panel decía “bloqueada”.

**Fix campo:** regla manual (y verificada):
```
/ip firewall filter add chain=forward action=drop src-address-list=shomer-blocked place-before=0 comment="Shomer-Hunter"
```

**Código panel/API** (`app/api/casador_support_firewall.py`, `casador_blocking.py`, `hunter.html`):
- `GET /remedies/firewall/routeros/verify` — cuenta regla DROP + entradas en lista
- `POST /remedies/firewall/routeros/ensure-drop-rule` — crea regla si falta (**solo si** `hunter.routeros_auto_drop_enabled=true`)
- UI: caja de advertencia + *Verificar* / *Aplicar* (oculto en sitios manual-only)

**Política por sitio:**

| Sitio | `hunter.routeros_auto_drop_enabled` | Aplicar DROP desde panel |
|-------|-------------------------------------|--------------------------|
| Hotel Ópera | `false` (default / no set) | ❌ Solo manual Winbox/terminal |
| Lab `.205`, `.245`, `.243` | `true` | ✅ Botón disponible |

**Doc:** `app/static/docs/HUNTER_MIKROTIK_ROUTEROS.md` · checklist A5 en `SOPORTE_TECNICO.md`.

## AO.2 Hunter — fix conteo alertas en panel

Suricata generaba ~21k alertas/día en Ópera pero el panel mostraba tope **2000**. Fix: conteo completo del día en `casador_support_suricata.py` → `hunter_stats` en `casador_blocking.py`. Desplegado Ópera jun 2026.

## AO.3 Bot — anti-spam Hunter (tras bloqueo y riesgos resueltos)

**Síntoma:** técnico seguía recibiendo mensajes tipo *“Amenaza contenida”* y *“Riesgos de red pendientes”* aunque `.10` ya estaba bloqueada y los **18 altos** marcados `terminado` en panel.

**Causas en `core/monitor.py`:**

| Monitor | Problema | Fix |
|---------|----------|-----|
| `watch_active_threats` | Resumen cada **6 h** mientras hubiera IPs bloqueadas + alerta inmediata en cada **reinicio** del container | Eliminado resumen periódico; solo seed interno (avisos nuevos los cubre `watch_hunter`) |
| `watch_network_audit` | Repetía *“Riesgos altos pendientes”* cada 6 h con el **mismo** conteo | Alerta solo si sube `(criticos, altos)`; al llegar a 0 resetea |
| `watch_hunter_verify` | Tras reinicio, IPs viejas parecían “nuevas” | Seed de IPs pre-existentes al arrancar (igual que `watch_hunter`) |

**Estado Ópera verificado en BD (11/jun):** 1 IP bloqueada (`190.60.195.10`, `firewall_blocked=1`); 0 alto/crítico pendiente (30 bajo + 70 info).

**Nota:** Suricata en espejo **sigue registrando** tráfico de IPs bloqueadas en el panel Hunter — eso es IDS, no Telegram del bot.

## AO.4 Backup lab `.205` (11 jun 2026)

Backup manual completo sistema + bot:
- Archivo: `/storage/shomer-agent/data/backups/shomer_backup_20260611_042227.tar.gz` (**6,3 MB**)
- Incluye: BDs, `app/`, agente `core/`, `.env`, `devices.json`, `conversations.db`, `knowledge.db`, nginx, systemd, Suricata rules
- Enviado a **jpad** (`100.119.205.86`) vía `sudo tailscale file cp`

## AO.5 Deploy sesión — matriz final

| Servidor | Panel Hunter RouterOS | Bot `monitor.py` anti-spam | Notas |
|----------|----------------------|----------------------------|-------|
| `.205` lab | ✅ origen | ✅ | `routeros_auto_drop_enabled=true` |
| **Ópera** `.119` | ✅ | ✅ reiniciado | DROP **manual**; regla verificada en MikroTik |
| shomer245 `.116` | ✅ | ✅ código sync | `routeros_auto_drop_enabled=true` |
| shomer243 `.050` | ✅ | ✅ código sync | `routeros_auto_drop_enabled=true` |

**Claves BD nuevas (panel):** `hunter.firewall_type`, `hunter.firewall_port`, `hunter.firewall_timeout`, `hunter.routeros_auto_drop_enabled` — expuestas en `GET/POST /config/system` (`shomer_config.py`).

---

# Parte AP — Sesión 54 (13 jun 2026) — Historial incidentes + retención + deploy

## AP.1 Módulo `shomer_status_events.py`

Historial unificado Guardian + Inframonitor (APs solo en Guardian — no duplicar en Infra).

| Componente | Detalle |
|------------|---------|
| Tabla `status_events` | Transiciones online/offline/no-internet con WAN snapshot y flag mantenimiento |
| Tabla `network_outage_notes` | Causa confirmada en campo por oleada |
| Oleadas | Agrupación ~3 s; clasificación: microcorte, WAN ISP, sector parcial, mantenimiento, etc. |
| Retención | `monitor.status_retention_days` (90), `infra_events_retention_days` (90), `event_log_retention_days` (30); poda horaria + agresiva si disco ≥ 85 % |
| UI | `/system-status` — tabla 48 h, retención, confirmar causa, CSV |
| APIs | `GET/POST /api/network/retention`, `GET /api/network/outages`, `POST /api/network/outages/confirm` |

**No altera** alertas Telegram ni lógica reboot Guardian.

## AP.2 Deploy 13 jun 2026

| Servidor | Estado |
|----------|--------|
| **Ópera** `100.103.148.119` | ✅ `SHOMER_DEPLOY_AUTHORIZED=1` — app/ + agente; health OK (30 nodos) |
| **shomer245** `.116` | ✅ |
| **shomer243** `.050` | ✅ |
| **.205** lab | Código local + restart (no rsync a sí mismo vía Tailscale) |

`SITE.md` actualizado **en cada servidor** (no via deploy.sh). `docs/EQUIPOS.md` maestro en repo.

## AP.3 Fix acceso panel Ópera (mismo día)

- Creado `/etc/shomer/shomer-runtime.env` + systemd drop-in (faltaba post-instalación)
- Nginx: redirect 443→8443; proxy headers en `/auth/login`
- **No** relacionado con el módulo `status_events` — problema preexistente de URL/puerto/runtime

## AP.4 Incidente APs Contabilidad/Spa (13 jun 2026, ~1:11 AM Bogotá)

- Oleada breve post-deploy: AP CONTABILIDAD (`.217`) y AP SPA (`.204`) — caída real de ping en SPA; Contabilidad en recuperación de reboot
- **No causado** por `status_events` (solo registra). Coincidió con reinicio de `shomer-guardian` tras deploy
- **Recomendación producción:** activar `/modo on` antes de deploy; desactivar al terminar
- Guardian corre con **3 workers uvicorn** → poller triplicado (eventos `status_events` x3); pendiente corregir a 1 poller

---

# Parte AQ — Sesión 55 (13 jun 2026) — Telegram mantenimiento global

## AQ.1 Problema

Activar/desactivar mantenimiento **global** desde panel o bot **no enviaba Telegram** — solo log en panel o respuesta en el chat del bot. Mantenimiento **por nodo** sí notificaba.

## AQ.2 Fix

| Archivo | Cambio |
|---------|--------|
| `app/api/shomer_guardian_events.py` | `POST /maintenance/on` y `/off` → `send_telegram_safe` con etiqueta `MANTENIMIENTO` + usuario panel |
| `/storage/shomer-agent/core/shomer_api.py` | `set_maintenance()` usa API Guardian (Redis + Telegram); fallback Redis directo |

Mensajes: `🔧 MANTENIMIENTO GLOBAL ACTIVADO` / `✅ DESACTIVADO` — incluyen usuario (`root`, `admin`, etc.).

**Deploy:** Ópera 13/jun tras fix.

---

# Parte AR — Sesión 56 (16 jun 2026) — Seguro Hunter + deploy lab

## AR.1 Seguro Hunter — autobloqueo (dos canales, mismo estado)

| Canal | Cómo activar/desactivar |
|-------|-------------------------|
| **1. Panel web** | Botón **Seguro ON/OFF** (header Hunter) **o** Config → *Auto-bloqueo en Producción* → checkbox **Habilitado** → **Guardar** — los tres sincronizados |
| **2. Telegram** | `/seguro on` · `/seguro off` · `/seguro` (estado + botón) — alias `/autobloqueo`, `/hunter_seguro` |

Al cambiar estado (cualquier canal) → **Telegram al chat técnico** con guía: cómo apagar (panel + bot) y `/liberar` para IP puntual.

**Archivos:** `app/templates/hunter.html` (botón header), `app/api/shomer_config.py` (`_notify_hunter_seguro`), `/storage/shomer-agent/core/bot.py` (`cmd_seguro`), `core/shomer_api.py` (`set_hunter_autoblock`).

**Ópera (16 jun):** `hunter.auto_block_enabled=true` — activado con autorización JP; MikroTik `192.168.0.1`, subnets hotel en exclusión.

## AR.2 Deploy código — dos modos (`tools/deploy.sh`)

| Modo | Comando | Alcance |
|------|---------|---------|
| **Todos lab** | `bash tools/deploy.sh` | **243 + 245 + 205** — **omite Ópera** sin `SHOMER_DEPLOY_AUTHORIZED=1` |
| **Un servidor** | `bash tools/deploy.sh <IP_Tailscale>` | Solo ese equipo |
| **Lab + Ópera** | `SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh` | Todos en `tools/servers.txt` |

**.205:** código ya local — `deploy.sh` a sí mismo puede fallar por SSH; usar **restart local** (`shomer-guardian`, `shomer-tools`, `shomer-agent`).

**Deploy 16 jun:** ✅ 245 · ✅ 243 · ✅ 205 (restart) · Ópera ya desplegado sesión anterior + activación Seguro.

## AR.3 Telegram — notificaciones (dos modos posibles)

| Modo | Comportamiento |
|------|----------------|
| **Con sonido** | Mensaje normal — suena el tono que el técnico configuró **para ese chat** en la app Telegram |
| **Silencioso** | API `disable_notification=true` — sin sonido (útil para avisos informativos) |

**Limitación Telegram:** el bot **no** puede elegir sonidos distintos por tipo (alerta vs info vs warning) — solo un tono por chat. Shomer puede marcar severidades con emoji y, en el futuro, silenciar rutinarios vs críticos.

## AR.4 Liberar IP puntual

| Acción | Comando / UI |
|--------|----------------|
| Ver bloqueadas + botón | `/liberar` |
| Liberar una IP | `/desbloquear IP` o panel Hunter |

---

# Parte AS — Sesión 57 (19 jun 2026) — Inframonitor: poller independiente + Redis-first + WAL + visual

## AS.1 Resumen de cambios

| Cambio | Beneficio |
|--------|-----------|
| `shomer-inframonitor-poller.service` independiente | Poller sobrevive reinicios de uvicorn/guardian |
| SQLite WAL mode | Lecturas y escrituras concurrentes sin bloqueo |
| Redis-first en `/infra/status` | Datos en memoria; elimina N queries SQLite por dispositivo |
| Redis blob `infra:{ip}:data` | Estado completo por IP con TTL=120s |
| `outages_today` por dispositivo en `/infra/devices` | Badge de caídas del día en el panel |
| Visual: barras uptime + umbrales reales | Verde ≥99% / ámbar 98-99% / rojo <98% |

**Deploy 19 jun:** ✅ .205 · ✅ 245 · ✅ 243 · ✅ Ópera (autorizado JP)

## AS.2 Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `app/api/shomer_inframonitor.py` | WAL en `_init_tables()`, blob Redis en `_poll_once()`, `outages_today` en `_build_device_row()` y `list_devices()`, Redis-first en `GET /infra/status` |
| `app/templates/inframonitor.html` | `uptimeBadge()` con barra visual + umbrales 99/98, badge `⚠️ N caída(s)` |
| `app/api/main.py` | `_systemd_service_active()` — si poller externo activo, omite poller embebido |

**Archivos nuevos:**
- `app/scripts/inframonitor_poller.py` — runner standalone con SIGTERM limpio
- `/etc/systemd/system/shomer-inframonitor-poller.service`

## AS.3 Instalar poller en servidor nuevo

```bash
# 1. El código llega con deploy.sh (app/scripts/inframonitor_poller.py incluido)
# 2. Crear service file:
sudo tee /etc/systemd/system/shomer-inframonitor-poller.service > /dev/null << 'EOF'
[Unit]
Description=Shomer Inframonitor Poller
After=network.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=usb_admin
Group=usb_admin
WorkingDirectory=/opt/network_monitor
EnvironmentFile=-/etc/shomer/shomer-runtime.env
ExecStart=/opt/network_monitor/venv/bin/python -m app.scripts.inframonitor_poller
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=shomer-inframonitor-poller
MemoryMax=200M
CPUQuota=100%

[Install]
WantedBy=multi-user.target
EOF

# 3. Activar:
sudo systemctl daemon-reload
sudo systemctl enable --now shomer-inframonitor-poller.service

# 4. Reiniciar guardian para que detecte el poller externo:
sudo systemctl restart shomer-guardian.service
```

> **Nota Ópera (Sesión 62):** `CPUQuota=100%` — con 30% el poller no alcanzaba a completar ciclos fast con ~50 equipos y generaba ciclos >30 s. Ver §BD.2.

**Verificación:**
```bash
systemctl is-active shomer-inframonitor-poller   # → active
redis-cli keys "infra:*:data" | wc -l            # → N dispositivos
sqlite3 /storage/db/network_monitor.db "PRAGMA journal_mode;"  # → wal
```

## AS.4 Lógica Redis-first

`GET /infra/status` (usado por NOC y bot `watch_infra`):
1. Lee lista de dispositivos de SQLite (config estática)
2. Por cada IP: `redis.get(f"infra:{ip}:data")` → JSON con status/latency/tcp_ok/mac/snmp_ok/checked_at
3. Si Redis miss (TTL expirado) → usa fila del JOIN SQLite como fallback
4. **`uptime_24h` eliminado de `/infra/status`** — los callers no lo usan; `/infra/devices` (panel) sigue teniéndolo via batch

`GET /infra/devices` (panel, incluye uptime):
- Batch de uptime: 2 queries para todos los IPs (sin N queries individuales)
- Batch de caídas: 1 query `GROUP BY ip` para `outages_today` de todos los IPs
- Total queries para N dispositivos: 4 queries fijas, independiente de N

## AS.5 Visual panel Inframonitor

**`uptimeBadge(pct, outages)`:**
- `pct >= 99` → verde (clase `uptime-hi`)
- `98 <= pct < 99` → ámbar (clase `uptime-mid`)
- `pct < 98` → rojo (clase `uptime-lo`)
- Barra visual debajo del % con `width:${pct}%` y color reactivo, transición CSS 0.4s
- Si `outages > 0` → `⚠️ N caída(s)` debajo de la barra

**`outages_today`** viene del endpoint `/infra/devices` (1 query batch en BD). No disponible en `/infra/status` (callers NOC/bot no lo necesitan).

---

# Parte AT — Sesión 58 (19 jun 2026) — NOC: log de decisiones IA + fix crash loop /health

## AT.1 Bug crítico — `/health` causaba crash loop real en Hotel Ópera

**Síntoma:** ventana de 7 minutos (07:24–07:31 hora Bogotá) con ~14 reinicios forzados de
`shomer-guardian.service`, varios con `SIGKILL` porque el proceso no respondía a `SIGTERM`.

**Causa raíz:** `GET /health` (consultado por `shomer-health-check.sh` cada 30s, con timeout de
5s) hacía un `CREATE TABLE IF NOT EXISTS infra_nodes` en **cada chequeo** — una escritura
totalmente innecesaria, porque esa tabla ya se crea al arrancar (`app/scripts/monitor.py`).
Guardian corre con `--workers 1` (un solo event-loop): si esa escritura chocaba con cualquier
otra escritura en curso de Guardian/Hunter/Inframonitor sobre el mismo `network_monitor.db`,
`/health` quedaba esperando el lock (hasta 10s por el `timeout=10` del conector) — más que los
5s que tolera el watchdog. El watchdog declaraba "caído" y mataba el proceso, que en realidad
solo estaba ocupado un instante.

**Fix** (`app/api/shomer_guardian_nodes.py::health()`):
- Se eliminó el `CREATE TABLE IF NOT EXISTS` del camino caliente — la tabla ya existe.
- La lectura (ahora 100% de solo lectura) se movió a `asyncio.to_thread()` con una conexión
  propia de `busy_timeout=2`, para que ni siquiera bloquee el event-loop si algo sale mal.

**Prueba real:** se mantuvo un lock de escritura SQLite sostenido por 7 segundos (proceso Python
con `BEGIN IMMEDIATE` + `sleep(7)`) mientras se hacían 5 peticiones a `/health` exactamente en esa
ventana. Las 5 respondieron en 6-7ms — cero impacto. Antes del fix, esa misma prueba colgaba la
petición.

**Por qué nunca lo agarró ninguna auditoría:** es un bug de **concurrencia bajo carga real**, no
algo visible leyendo la función aislada. Hace falta saber a la vez: (1) que Guardian corre con un
solo worker, (2) que tres procesos más escriben al mismo archivo SQLite en paralelo, y (3) que
SQLite —incluso en WAL— solo permite un escritor a la vez. Ningún code review de una función sola
ve eso. Solo se manifiesta cuando coincide en el tiempo con otra escritura real — por diseño, casi
nunca aparece en pruebas QA tranquilas de laboratorio.

## AT.2 Bug confirmado — `/noc/data` se congelaba 0.5s garantizado en cada llamada

A diferencia de `/health`, este no dependía de contención — era un `sleep` de diseño:
`psutil.cpu_percent(interval=0.5)` en `_server_resources()` bloquea ese medio segundo siempre,
sin excepción. El NOC pide `/noc/data` cada 30s, así que cada 30s el servidor completo (logins,
bloqueos Hunter, heartbeats reales de APs) quedaba congelado mínimo 0.5s.

**Fix** (`app/api/shomer_noc.py::_server_resources()`): `interval=0.5` → `interval=None`
(lectura instantánea vs. la última muestra, sin bloquear). Como el NOC ya sondea cada 30s, el
delta entre llamadas es representativo igual. Medido: de 0.55s a 0.045s por llamada.

## AT.3 Auditoría completa del patrón — 75 funciones mapeadas, 2 reales, 73 sin tocar

Barrido AST de todo `app/` buscando `async def` que llaman SQLite/Redis síncronos o `subprocess`
sin pasar por `asyncio.to_thread()`. Encontró 75 funciones con el patrón. Probadas con carga real
(mismo lock de 7-8s) las de mayor tráfico (`/nodes`, `/infra/status`) — **0% de impacto**, porque
son solo lectura y en modo WAL los lectores no esperan a los escritores. El riesgo real nunca fue
"usar SQLite dentro de `async def`" en general — es **mezclar una escritura con alta frecuencia o
con vigilancia automática externa** (exactamente lo que tenía `/health`).

Inventario completo de las 75 ubicaciones, categorizado, en
[`docs/AUDITORIA_ASYNC_BLOQUEANTE.md`](docs/AUDITORIA_ASYNC_BLOQUEANTE.md) — no se tocó ninguna
de las 73 restantes (son CRUD de bajo tráfico, sin proceso automático que las castigue por
demorarse). Regla para revisarlas en el futuro: si alguna pasa a ser sondeada por un watchdog,
poller o el bot cada pocos segundos, ahí sí aplica el mismo fix — no antes.

## AT.4 NOC — Log de Decisiones IA ("SHOMER COGNITIVE CORE")

El ticker de eventos genérico (`📋 Eventos — Sin eventos recientes`) se reemplazó por un log en
vivo de lo que hace el agente IA, con motor (Groq/OpenAI) y hora exacta.

**Arquitectura:**
- `log_ia_action(engine, msg, action_type)` en `/storage/shomer-agent/core/shomer_api.py` —
  escribe a Redis `noc:ia_log` (lista, máx 20 entradas, `LPUSH` + `LTRIM`).
- `llm_router.py::chat()` registra cada consulta de técnico con el motor real usado (con fallback
  Groq↔OpenAI ya resuelto antes de loguear).
- `llm_router.py::explain()` registra cada alerta de monitor generada por Groq (filtra mensajes
  vacíos/de error).
- `shomer_noc.py::_ia_log()` lee las últimas 8 entradas de Redis, expuestas en `/noc/data` como
  `ia_log`.
- `noc.html`: pill con 🤖 pulsando en el header (`AGENTE IA ACTIVO` + modelo), tarjeta terminal
  `SHOMER COGNITIVE CORE` en el sidebar, y el log de decisiones reemplazando el ticker viejo
  (`renderIaLog()`).

**LEDs de hardware en Inframonitor (NOC):** switches/routers muestran `SNMP ✓/✗` + `PUERTOS OK` /
`⚠ N ERRORES`; impresoras muestran barra de tóner % + LED de papel (`OK`/`BAJO`/`SIN PAPEL`).

## AT.5 Estado de despliegue

| Cambio | `.205` | Hotel Ópera |
|---|---|---|
| NOC log IA + LEDs hardware | ✅ | ✅ |
| Fix `/health` (crash loop) | ✅ probado con carga real | ✅ |
| Fix `/noc/data` (0.5s bloqueo) | ✅ probado | ✅ |

Agente reconstruido (`docker compose build --no-cache`) en ambos — los cambios de
`llm_router.py`/`shomer_api.py` requieren rebuild, no solo restart.

---

# Parte AU — Sesión 58 cont. (19 jun 2026) — Hotel Ópera: causa real del ruido Infra/bot

## AU.1 Contexto

Juan Pablo sacó al bot del grupo de Telegram de Hotel Ópera por exceso de ruido. Pidió barrido
completo del sitio antes de actuar. Hallazgo principal: **los 8 switches de Ópera caían
"offline" juntos, en el mismo orden, con el mismo patrón escalonado (~10s entre cada uno),
varias veces al día** — no era hardware fallando por separado, era el poller de Inframonitor
quedándose sin hilos disponibles.

## AU.2 Causa raíz — pool de hilos insuficiente en el poller

Ópera tiene 4 CPUs. El executor por defecto de `asyncio.to_thread()` en Python es
`min(32, CPUs+4)` → solo **8 hilos**. Cada ciclo de 30s, `_poll_once()` lanza ~52 pings + ~45
chequeos TCP + 9 lecturas SNMP (hasta 4s cada una) — más de 100 tareas bloqueantes compitiendo
por 8 hilos. Cuando la cola se saturaba, varios pings no llegaban a ejecutarse a tiempo dentro
del ciclo, y esos equipos se registraban como "offline" por error — recuperándose solos 3-4
minutos después, en el siguiente ciclo.

**Evidencia:** tabla `infra_events`, 7 días — los 8 switches mostraban offline/online en el
mismo orden de iteración del poller, separados por ~10s cada uno, varias veces al día. Switches
con SNMP en 0 errores (`.118`, `.129`, `.133`) flapeaban igual que los que sí tienen hardware
dañado (`.168`, `.216`) — la correlación temporal exacta entre todos descartó causa física común
para los 6 sanos.

**Fix** (`app/api/shomer_inframonitor.py`):
```python
INFRA_THREAD_WORKERS = int(os.environ.get("INFRA_THREAD_WORKERS", "48"))

def _ensure_executor():
    """Pool de hilos dedicado más grande -- se llama una vez desde _init_tables(),
    tanto en el poller standalone (systemd) como en el embebido (Guardian)."""
    global _executor_configured
    if _executor_configured:
        return
    loop = asyncio.get_event_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=INFRA_THREAD_WORKERS))
    _executor_configured = True
```
Llamado al inicio de `_init_tables()`. En Ópera corre aislado (poller standalone, proceso propio
— no afecta a Guardian). En sitios sin el poller standalone instalado, beneficia también al
proceso embebido (más hilos disponibles, sin downside).

**Validado:** 8+ minutos monitoreados tras el restart — cero episodios de caída masiva
sincronizada (antes recurría cada 1-5 horas), cero errores en el log. Solo un blip aislado de un
switch (34 segundos) — exactamente el tipo de ruido residual que el fix de §AU.3 absorbe.

**`tools/deploy.sh` no reinicia `shomer-inframonitor-poller.service`** (solo Guardian/Tools) —
hay que reiniciarlo a mano tras cada deploy que toque `shomer_inframonitor.py`.

## AU.3 Debounce en alertas Infra — evita ruido de blips cortos

`watch_infra()` (agente, `core/monitor.py`) avisaba "Equipo Infra caído"/"recuperado" en la
**primera** lectura offline, sin esperar confirmación — con 8 switches flapeando varias veces al
día, eso eran ~40-50 mensajes de Telegram diarios solo por el bug de §AU.2.

**Fix:** nuevo contador `_infra_offline_streak[ip]` — requiere `INFRA_OFFLINE_CONFIRM_CHECKS`
(default 2, ciclos de ~120s c/u del propio watcher) viendo "offline" **consecutivo** antes de
considerar la caída confirmada y avisar. Si el equipo vuelve a "online" antes de confirmarse, no
se avisa nada — el blip queda silencioso. La recuperación sigue siendo inmediata una vez que SÍ
hubo una caída confirmada (no se debounce el aviso de vuelta, solo el de caída).

```python
_infra_offline_streak: Dict[str, int] = {}
_INFRA_OFFLINE_CONFIRM = int(os.environ.get("INFRA_OFFLINE_CONFIRM_CHECKS", "2"))
```

No se tocó la lógica de "varios equipos caídos en la misma ubicación" ni el recordatorio de
"sigue caído >2h" — ambas ya tienen su propia resistencia natural a blips (cooldown 30 min y
umbral de 120 min respectivamente).

**Validado:** desplegado y probado contra los 52 equipos reales de Ópera — sin excepciones en
dos ciclos reales. Un intento de envío a Telegram durante la prueba fue una alerta real y
correcta de "papel bajo" (impresora Recepción WF-M5899, 0 de 80 hojas) — no relacionada al fix,
bloqueada solo porque el bot sigue fuera del grupo.

## AU.4 SNMP del MikroTik gateway — estaba apagado, no mal configurado

`192.168.0.1` (MikroTik RB1100AHx2, mismo equipo que usa Hunter — `hunter.firewall_ip`) mostraba
`snmp_ok=0` siempre. Diagnóstico vía SSH (reutilizando `_get_firewall_creds()` +
`_connect_routeros()` de `casador_support_firewall.py`, sin exponer la contraseña en línea de
comandos): la comunidad `public` ya estaba bien configurada (lectura, sin restricción de IP) —
el servicio SNMP **estaba apagado** (`/snmp print` → `enabled: no`).

**Fix:** `/snmp set enabled=yes` vía SSH. Confirmado: `snmpget` responde
(`RouterOS RB1100AHx2 7.22.1`), `snmp_ok` pasa a 1 en el siguiente poll. Efecto secundario
menor: libera un hilo que antes se gastaba 4s completos cada ciclo esperando un timeout inútil.

## AU.5 Hallazgos confirmados, diferidos a pedido de Juan Pablo

| Hallazgo | Detalle | Estado |
|---|---|---|
| Hardware dañado real en `.168` (`SW1-P50-OFC-SISTEMAS`) y `.216` (`SW-POE-OFC-SISTEMAS`) | Errores SNMP acumulados reales: 95,534 + 50,587 en `.168`; 2,860 en `.216` — cable/transceiver/equipo conectado | Diferido — requiere revisión física en sitio |
| Scheduler de Protector duplicado | `shomer-tools.service` corre `--workers 2`; `start_backup_scheduler()` se dispara en el `lifespan` de **cada** worker → 2 schedulers paralelos capaces de lanzar el mismo backup programado a la vez | Diferido — no hay `backup_devices` configurados aún en Ópera, no es urgente todavía |
| Protector sin configurar en Ópera | Juan Pablo tiene la ubicación de un equipo (SMB/Windows) lista para dar de alta | Pendiente — pausado a pedido propio, retomar en sesión dedicada |

## AU.6 Auditoría general — sin deploys faltantes, sin riesgos nuevos

- Código (`app/`, templates, agente) **100% sincronizado** `.205` ↔ Ópera (rsync dry-run sin
  diferencias) — explicado por los deploys constantes de esta sesión.
- Servicios, disco, RAM, CPU — todo normal. Sin unidades systemd fallidas.
- `.bak`/`.disabled` sueltos de abril-mayo (plantillas, scripts viejos, `.env.bak` con permisos
  600 correctos) — cruft acumulado, cero riesgo real, limpieza opcional futura.
- `inventory.db` (Tracker) sin escanear desde el 10 de jun — manual, sin scheduler configurado,
  no es un bug.
- Bot confirmado fuera del grupo de Telegram (`Forbidden: bot was kicked from the group chat`)
  desde que Juan Pablo lo sacó — sigue generando alertas internamente (correctas), solo no llegan
  a nadie hasta que se re-agregue.

## AU.7 Pendiente — antes de re-agregar el bot al grupo

1. Dejar correr el fix de §AU.2 unas horas más para confirmar al 100% que el flapping masivo no
   recurre (5-8 min de monitoreo ya mostraron cero episodios, pero el patrón viejo recurría cada
   1-5h).
2. ~~Configurar Protector/backups en Ópera~~ ✅ Sesión 58 cont. (mismo día) — ver §AV.
3. Revisar físicamente `.168`/`.216` (cable, transceiver, equipo conectado al puerto dañado).
4. Solo entonces re-agregar el bot al grupo de Telegram — para no repetir el ciclo de ruido.

---

# Parte AV — Sesión 58 cont. (19 jun 2026) — Protector: Zeus PMS configurado + 3 bugs reales de Protector corregidos

## AV.1 Objetivo

Configurar Protector para respaldar solo los `.bak` diarios del PMS Zeus (`192.168.0.5`,
Hotel Ópera) desde `C$\back_bases\Copias Diarias`, sin tocar los jobs propios del hotel
(Zeus genera el `.bak` ~3 AM, copia a NAS hasta ~4:30 AM).

## AV.2 Bug real — `mount.cifs` no entiende `DOMINIO\usuario` embebido (causa real del "Permission denied")

El equipo Zeus estaba dado de alta con usuario `.\administrador` (convención de la GUI de
Windows para "cuenta local de esta máquina"). `_smb_mount_readonly()` y `_backup_windows()`
escribían ese valor **literal** en el archivo de credenciales de `mount.cifs`:
```
username=.\administrador
password=...
```
`mount.cifs` no interpreta el `.\` como lo hace Windows — lo toma como parte literal del
username, y la autenticación SMB falla con `mount error(13): Permission denied` **aunque la
contraseña sea 100% correcta**. Esto generaba el síntoma engañoso de "credencial mala" cuando
en realidad la contraseña guardada en BD era correcta desde el principio (verificado
descifrándola con la clave real del servicio — coincidía exactamente con la que dio Juan Pablo).

**Fix** (`app/api/backups.py`): nueva función `_cifs_credentials_content(username, password)`
que separa `DOMINIO\usuario` o `.\usuario` en líneas `domain=`/`username=` correctas para
`mount.cifs` (`.` o vacío → cuenta local, sin línea `domain=`; cualquier otro valor → se escribe
`domain=<valor>`). Usada tanto en `_smb_mount_readonly()` (test de conexión) como en
`_backup_windows()` (backup real) — antes tenían la lógica de credenciales duplicada e
inconsistente entre sí.

## AV.3 Bugs secundarios corregidos en el mismo barrido

| # | Bug | Fix |
|---|-----|-----|
| 1 | `_parse_smb_source_path()` no reconocía `C:` como error común (vs. el share real `C$`) — mount fallaba como si fuera credencial mala | Auto-corrige `^[A-Za-z]:$` → `{letra}$` antes de montar |
| 2 | Botón **Probar conexión** del panel reenvía el literal `***` si el técnico no vuelve a escribir la contraseña al editar un equipo ya guardado — el test fallaba siempre en ese flujo | `POST /backups/devices/test` acepta `device_id`; si `password` viene vacío o `***`, descifra la contraseña real de BD para ese equipo en vez de probar con el string literal |
| 3 | `backups.html`: `_localToUtc()`/`_utcToLocal()` seguían convirtiendo UTC↔local del navegador, pero el backend (desde Sesión 21, `_scheduler_loop()`) compara `schedule_time` **directo** contra la hora local del sitio (`base.timezone`) — diseño viejo nunca actualizado tras el fix de Sesión 21 | Ambas funciones ahora son pass-through; el panel guarda/muestra la hora tal cual la escribe el técnico, igual que la espera el backend |

**Por qué importa el bug #3 más allá de Zeus:** afecta a **cualquier** equipo de Protector con
horario configurado desde el panel, en cualquier sitio — no es exclusivo de Ópera. Verificado
en los 4 servidores (`.205`, Ópera, `.245`, `.243`): ningún otro equipo tenía horario activo
configurado todavía, así que no había daño hecho — pero el horario de Zeus que se configuró en
esta sesión (ver §AV.4) se habría roto en el momento en que alguien lo reabriera y guardara desde
el panel, sin tocar nada más.

## AV.4 Diagnóstico — orden real de los hallazgos (todo verificado antes de tocar Zeus)

1. Contraseña guardada en BD descifra correctamente con la clave real del servicio (`JWT_SECRET`
   vía `EnvironmentFile` de systemd) y **coincide exactamente** con la que dio Juan Pablo
   (`administrador` / `opera2023*`) — descartado problema de cifrado o de contraseña.
2. Con el fix de §AV.2 aplicado, el mount **autentica y monta correctamente** (`C$` accesible).
3. El subpath original en BD (`back_bases/copias_diarias`, sugerido verbalmente) no coincidía
   con el real en disco — se listó el contenido de `back_bases\` (solo lectura, desmontado
   inmediato) y se confirmó el nombre real: **`Copias Diarias`** (con espacio y mayúsculas, tal
   cual estaba guardado desde el principio).
4. Con la ruta real + fix de dominio, el test de conexión devuelve:
   `SMB OK — 192.168.0.5 — subcarpeta accesible: back_bases/Copias Diarias — 9 archivo(s)
   coinciden con filtro hoy` — coincide exactamente con los 9 `.bak` del 19 de junio que
   describió Juan Pablo.

Todo el diagnóstico y la corrección de configuración se hicieron llamando directamente a las
funciones reales y validadas del panel (`update_backup_device()`, `test_backup_device()` de
`app/api/backups.py`) vía script — **no** se usó SQL crudo contra la BD de producción ni se tocó
nada en el propio Zeus.

## AV.5 Configuración final — equipo "SRV Zeus PMS" (Hotel Ópera)

| Campo | Valor |
|-------|-------|
| IP | `192.168.0.5` |
| Usuario | `.\administrador` (cuenta local, ahora separada correctamente por el fix de §AV.2) |
| Ruta | `C$/back_bases/Copias Diarias` |
| Filtro | `*_{today}_*` (9 archivos `.bak` del día) |
| Horario | `05:00` hora Bogotá (después de que el hotel termine su copia a NAS ~4:30 AM) |
| Sync B2 | Desactivado por ahora (decisión Juan Pablo — solo copia local por el momento) |

## AV.6 Pendiente relacionado — reabre prioridad de un hallazgo ya documentado

§AU.5 había diferido el **scheduler duplicado de Protector** (`shomer-tools.service` con
`--workers 2` dispara `start_backup_scheduler()` una vez por worker) con la justificación de que
"no hay `backup_devices` configurados aún en Ópera, no es urgente todavía". Esa justificación
**ya no aplica** — Zeus ahora tiene `schedule_enabled=1`. Sigue diferido a pedido explícito de
Juan Pablo (no tocar sin que él lo pida), pero el riesgo real de que el scheduler duplicado
dispare el mismo backup dos veces en paralelo a las 05:00 ya existe a partir de esta sesión.

## AV.7 Archivos modificados y estado de despliegue

| Archivo | Cambio |
|---------|--------|
| `app/api/backups.py` | `_cifs_credentials_content()` nueva; `_parse_smb_source_path()` auto-corrige `C:`→`C$`; `/devices/test` acepta `device_id` y descifra contraseña de BD si viene `***`/vacío |
| `app/templates/backups.html` | `_utcToLocal()`/`_localToUtc()` pass-through (sin conversión de zona horaria) |
| `tests/test_backups_smb_path.py` | +8 tests nuevos (autocorrección `C:`, separación dominio/usuario, fallback contraseña `***`) — 15/15 OK |

| Servidor | Código desplegado | Equipo Zeus configurado |
|---------|-------------------|--------------------------|
| `.205` (origen) | ✅ | — (no aplica, lab) |
| **Hotel Ópera** `.119` | ✅ | ✅ probado end-to-end, horario activo 05:00 |
| shomer245 `.116` | ⏳ pendiente deploy | — sin equipos Protector configurados |
| shomer243 `.050` | ⏳ pendiente deploy | — sin equipos Protector configurados |

---

# Parte AW — Sesión 58 cont. (19 jun 2026) — Causa real del freeze recurrente de Guardian (más allá del fix de §AT)

## AW.1 El fix de §AT.1 era real pero insuficiente

El fix de `/health` (escritura SQLite innecesaria en el camino caliente del watchdog) era
correcto y sigue desplegado, pero **las rachas de freeze de Guardian siguieron pasando después**:
00:33, 02:58-03:05, 04:40-04:47, 07:24-07:30 (la que motivó §AT), 15:01-15:07, 15:57, 16:06-16:14,
19:58-20:00 y 20:42-20:44, todas el 19 jun. Cada racha: el watchdog detecta `/health` sin
respuesta, mata Guardian con `SIGKILL` (timeout de `stop-sigterm`), lo reinicia, y vuelve a
fallar ~30s después — auto-sostenido durante 5-9 minutos hasta que se resuelve solo.

## AW.2 Causa real — capturada con `py-spy` en vivo durante una racha

Se instaló `py-spy` (`pip install py-spy` en el venv) y se hizo `py-spy dump --pid <PID>
--nonblocking` exactamente durante una racha activa. Resultado:

```
Thread 0x... (active): "MainThread"
    run_data_retention_prune (api/shomer_status_events.py:253)
    lifespan (api/main.py:80)
    __aenter__ (contextlib.py:199)
    merged_lifespan (fastapi/routing.py:209)
    ...
```

`lifespan()` en `app/api/main.py` llamaba `run_data_retention_prune(force=True)`
**síncrona y bloqueante, antes del `yield`** — es decir, uvicorn no empieza a aceptar conexiones
en el puerto 8000 hasta que esa llamada termina. La función hace varios `DELETE` directos sobre
`network_monitor.db` (línea 253: `conn.execute(sql, (f"-{days} days",))`).

**Por qué choca justo desde la Sesión 57:** `shomer-inframonitor-poller.service` (proceso
independiente, §AS) escribe a esa misma BD cada 30 segundos. Si el arranque de Guardian coincide
con una escritura del poller, `conn.execute()` espera el lock de SQLite hasta el timeout interno
de la conexión (`timeout=10` en `shomer_common.py::get_db()`) — muy por encima de los 5s que
tolera el watchdog (`curl --max-time 5` en `shomer-health-check.sh`). El watchdog mata el proceso
pensando que está caído, lo reinicia, y el reinicio **vuelve a coincidir** con el siguiente ciclo
de 30s del poller — un bucle auto-sostenido que solo se rompe cuando el timing se desincroniza
por azar. Esto explica el patrón exacto observado: rachas de varios minutos que se resuelven solas.

## AW.3 Fix aplicado

**Archivo:** `app/api/main.py` — se eliminó la llamada síncrona `run_data_retention_prune(force=True)`
de `lifespan()` (y el import ahora no usado). No se perdió funcionalidad: la línea siguiente,
`start_retention_prune_loop()`, ya inicia `retention_prune_loop()` (en
`app/api/shomer_status_events.py`), que espera 120s y luego repite con
`await asyncio.to_thread(run_data_retention_prune, force=True)` — correctamente fuera del
camino de arranque, sin bloquear el `yield`. La poda al boot era pura redundancia con esa
segunda llamada, y la única responsable del freeze.

```python
# Antes (bloqueaba el arranque):
if try_acquire_poller_leader():
    run_data_retention_prune(force=True)
    start_retention_prune_loop()
    ...

# Después:
if try_acquire_poller_leader():
    start_retention_prune_loop()
    ...
```

## AW.4 Verificación

- `.205`: reinicio limpio (`/health` 200 en <1s), 40/43 tests (`test_smoke_api` +
  `test_backups_smb_path`) — mismas 3 fallas preexistentes de siempre, sin regresión.
- **Hotel Ópera:** desplegado, `/health` 200 inmediato tras el restart del deploy.
- Vigilante `py-spy` relanzado con ventana de 8h (`/tmp/_freeze_watcher.sh` →
  `/var/log/shomer/freeze_dump.log`) para confirmar con el tiempo que la racha no recurre.
  El primer intento de vigilante (lanzado antes de encontrar esta causa) tenía un bug de
  permisos propio (`sudo chmod 644` deja el log root:root, el script no podía escribirlo como
  `usb_admin`) — corregido (`chown usb_admin:usb_admin`) en el relanzamiento.

## AW.5 Pendiente

Confirmar en la próxima sesión que no hubo más rachas en `/var/log/shomer/watchdog.log` de Ópera
desde el deploy (19 jun ~20:50). Si el vigilante capturó algo en `freeze_dump.log`, hay una
segunda causa distinta por investigar; si no, el fix fue completo.

---

# Parte AX — Sesión 58 cont. (19 jun 2026) — Protector Zeus: 4 bugs más + primer backup real validado

Continuación de §AV. Tras configurar la conexión y el horario, se ejecutó un **backup real**
(`POST /devices/backup_now`) para validar el flujo completo antes de confiar en las 5am — y
aparecieron 4 problemas más, todos de **instalación/infraestructura de Ópera**, no del código
de `.205` (con la única excepción del bug de `restic --include`, que sí es de código y aplica a
cualquier sitio).

## AX.1 `RESTIC_PASSWORD_FILE` nunca configurado en Ópera

`/etc/shomer/shomer-runtime.env` no tenía `RESTIC_PASSWORD` ni `RESTIC_PASSWORD_FILE` —
`get_restic_password()` devolvía vacío y el backup fallaba con `503`. El repo (
`/srv/shomer_backups/staging`) y el archivo de contraseña (`/home/usb_admin/.restic-local-pass`,
mismo nombre que en `.205`) **ya existían**, creados el 21 de mayo durante la instalación — solo
faltaba la variable de entorno que conecta ambos. Agregado a `shomer-runtime.env`:
```
RESTIC_PASSWORD_FILE=/home/usb_admin/.restic-local-pass
RESTIC_REPOSITORY=/srv/shomer_backups/staging
```

## AX.2 Repo Restic completo propiedad de `root` desde su creación

`/srv/shomer_backups/staging/{data,keys,config,snapshots,index,locks}` pertenecían a `root:root`
modo `700` desde el 21 de mayo. `shomer-tools.service` corre como `usb_admin` (confirmado en el
unit file) — **nunca pudo leer ni escribir ese repo**, ni siquiera para el primer `restic init`
real (los 258 subdirectorios en `data/` sugieren que alguien corrió `sudo restic init` durante la
instalación, y nada volvió a tocarlo desde entonces). `restic snapshots` confirmó el repo
accesible pero con **0 snapshots** -- ningún backup se completó jamás en este sitio antes de hoy.

**Fix:** `sudo chown -R usb_admin:usb_admin /srv/shomer_backups/staging` — solo cambia
propietario de archivos existentes, no toca contenido.

## AX.3 `/mnt/shomer_smb` nunca creado en Ópera

`_backup_windows()` monta en `{SMB_MOUNT_BASE}/{device_id}` = `/mnt/shomer_smb/{id}`. En `.205`
ese directorio base existe (`usb_admin:usb_admin`, creado durante instalación/uso del lab) — en
Ópera **nunca se creó**, ni siquiera el directorio base, y `/mnt` es `root:root` así que
`os.makedirs()` fallaba con `PermissionError`. Creado igual que en `.205`:
```bash
sudo mkdir -p /mnt/shomer_smb && sudo chown usb_admin:usb_admin /mnt/shomer_smb
```

## AX.4 Bug de código real — `restic backup` no soporta `--include`

**Este aplica a cualquier sitio, no solo Ópera.** El flujo de `include_pattern` (construido esta
misma sesión, nunca antes probado contra el binario real) generaba
`restic backup <dir> --include <patrón> --tag ...` — pero `--include`/`--exclude` en restic
0.12.1 **no existen para `backup`** (solo para `restore`/`dump`/`ls`). El primer backup real
falló con `RuntimeError: unknown flag: --include`.

**Fix** (`app/api/backups.py::_backup_windows`): en vez de pasar el directorio + una bandera que
no existe, se resuelve el patrón con `glob` (igual que ya hacía el endpoint de test para el
conteo) y se pasan los **archivos reales encontrados** como targets directos de
`restic backup`:
```python
if include_pattern:
    targets = []
    for raw in str(include_pattern).split(","):
        pat = _expand_include_pattern(raw.strip())
        if pat:
            targets.extend(glob.glob(os.path.join(backup_target, pat)))
    targets = sorted(set(targets))
else:
    targets = [backup_target]
...
subprocess.run([RESTIC_BIN, "-r", RESTIC_REPO, "backup"] + targets + tags, ...)
```
Se eliminó `_restic_include_args()` (quedó muerta e incorrecta desde su creación) y sus tests;
se agregó `TestBackupWindowsIncludeTargets` que valida con archivos reales en disco temporal que
solo los que matchean el patrón se pasan como target, y que `--include` nunca aparece en el
comando.

## AX.5 Primer backup real de Zeus — validado completo

```
POST /devices/backup_now {device_id: 1}
→ {"success": true, "message": "Backup SMB — 192.168.0.5 (9 archivos | 37s)"}
```

Snapshot confirmado en el repo (`restic snapshots`): 9 archivos `.bak` del 19 jun
(ActivosFijos, Contabilidad, Inventario, Nomina, ZeusDnn, ZeusExcelComplementos,
ZeusGuestServices, ZeusImagenes, Zeus_Nueva), tags `device_1, smb, SRV_Zeus_PMS`. BD:
`last_status=ok, last_files_count=9, last_duration_sec=37, last_snapshot_id=f80f04bc`.

Telegram de confirmación falló (`403 Forbidden: bot was kicked from the group chat`) — esperado,
el bot sigue fuera del grupo desde §AU, no es un bug nuevo.

## AX.6 Archivos y despliegue

| Archivo | Cambio |
|---------|--------|
| `app/api/backups.py` | `_backup_windows()` resuelve `include_pattern` con `glob` en vez de `--include`; eliminada `_restic_include_args()` |
| `tests/test_backups_smb_path.py` | Eliminado `TestResticIncludeArgs`; agregado `TestBackupWindowsIncludeTargets` (14/14 tests OK) |

| Servidor | Código restic fix | `.env`/permisos Ópera-específicos |
|---------|--------------------|-----------------------------------|
| `.205` | ✅ | — (ya estaba bien desde instalación) |
| **Hotel Ópera** | ✅ | ✅ `RESTIC_PASSWORD_FILE`, `chown` repo, `mkdir /mnt/shomer_smb` |
| shomer245 / shomer243 | ⏳ pendiente deploy código | sin verificar (sin equipos Protector configurados aún) |

## AX.7 Nota — por qué importa para futuras instalaciones

Los 3 problemas de §AX.1-AX.3 son específicos de la instalación de Ópera (21 mayo) y **no
debían existir** si `install_shomer.sh` hubiera dejado todo en el estado correcto desde el
principio. Vale la pena revisar ese script para confirmar que crea `/mnt/shomer_smb` con dueño
correcto y que el `restic init` inicial (si lo hace) corre como `usb_admin`, no como `root` —
para que el próximo sitio nuevo no repita exactamente estos 3 huecos.

---

# Parte AY — Sesión 58 cont. (19-20 jun 2026) — Object Lock B2: oculto del panel, código intacto

## AY.1 Qué se pidió

Juan Pablo, durante el barrido completo de Protector: "quita la opción de Object Lock B2 del
panel y deja el código documentado por si algún día se necesita" — no eliminar la función, solo
sacarla de la vista del técnico en `/backups`.

## AY.2 Qué se hizo (solo `app/templates/backups.html`)

- La tarjeta HTML completa de "Object Lock B2" (status, campo días de retención, botón Activar)
  quedó envuelta en un comentario HTML con nota explicando por qué está oculta y cómo reactivarla.
- La llamada de inicialización `loadObjectLockStatus();` quedó comentada — ya no se ejecuta al
  cargar la página.
- La función JS `loadObjectLockStatus()` se dejó completa, con un comentario arriba aclarando que
  está sin uso actualmente pero se conserva para reactivación futura.

**Nada se tocó en el backend.** `app/api/backups.py::enable_b2_object_lock()` y el resto de los
endpoints `/b2/object-lock/*` siguen funcionando exactamente igual — accesibles vía API directa
(`curl`/Postman) aunque no haya botón en el panel. El docstring de `enable_b2_object_lock()` tiene
una nota apuntando a esta sección.

## AY.3 Por qué no se borró

Razón explícita de Juan Pablo: "por si algún día se necesita" — Object Lock B2 (WORM — Write
Once Read Many) es valioso si algún cliente con requisitos de cumplimiento (ransomware
insurance, retención legal) lo pide más adelante. Mantener el código vivo evita reescribirlo
desde cero; solo hace falta descomentar la tarjeta en `backups.html` y la llamada de init.

## AY.4 Cómo reactivar (futuro)

1. Abrir `app/templates/backups.html`, buscar el comentario `<!-- Object Lock B2 -- OCULTO...`
2. Quitar las etiquetas de comentario que envuelven la tarjeta HTML
3. Descomentar `loadObjectLockStatus();` en el bloque de inicialización
4. Nada más — el backend, el JS y los endpoints nunca dejaron de funcionar

## AY.5 Estado de despliegue

| Servidor | Card oculta |
|----------|-------------|
| `.205` | ✅ |
| Hotel Ópera | ✅ |

---

# Parte AZ — Sesión 58 cont. (19-20 jun 2026) — Fix scheduler duplicado (Protector/Drill/Reportes bajo Tools --workers 2)

## AZ.1 El riesgo real (no hipotético)

`shomer-tools.service` corre `uvicorn ... --workers 2` — confirmado vía `pstree` que esto
genera **2 procesos hijos reales** (no solo hilos) en cualquier sitio sin un drop-in que lo
sobreescriba. Cada uno de esos 2 procesos ejecuta su propio `lifespan()` de FastAPI — y por lo
tanto, sin protección, sus propios `asyncio.create_task()` de:

- `backups.py::start_backup_scheduler()` — dispara backups programados por equipo
- `restore_drill.py::start_drill_scheduler()` — dispara el drill mensual (día 1, 03:00)
- `shomer_reports.py::start_report_scheduler()` — dispara el PDF mensual

Antes de este fix, **los 3 corrían dos veces en paralelo** en cualquier servidor con 2 workers
reales. Mientras Protector no tenía ningún `backup_devices` configurado, el bug existía pero no
tenía consecuencia visible (ver `project_opera_inframonitor_noise.md`, nota ya actualizada). Eso
cambió en esta misma sesión: Zeus PMS quedó configurado con backup programado real a las 05:00
Bogotá (§AV) — el primer disparo real de un backup duplicado quedaba a horas de distancia,
de ahí la urgencia de corregirlo ya.

## AZ.2 Causa raíz por qué nadie lo notó antes

Cada worker uvicorn es un **proceso del sistema operativo separado** (confirmado con
`pstree -p <pid_padre>` — aparecen como hijos `multiprocessing.spawn.spawn_main`), no hilos. Los
globals a nivel de módulo (`_scheduler_running = False`, etc.) viven en la memoria de cada
proceso por separado — no sirven para coordinar entre los 2 workers. Cada uno arranca su propio
`_scheduler_loop()` creyendo ser el único.

**Confusión inicial en esta misma sesión:** al verificar el fix en `.205` primero, no se
encontraron logs de "omitido" — parecía que el fix no hacía nada. La causa: en `.205` existe un
drop-in (`/etc/systemd/system/shomer-tools.service.d/bind-localhost.conf`) que **sobreescribe
por completo** el `ExecStart` sin el flag `--workers 2`, dejando Tools con **un solo proceso**
real en el lab. El riesgo de duplicación nunca existió en `.205` — solo en sitios (como Hotel
Ópera) que conservan el `--workers 2` del unit file original sin ese drop-in. Antes de descartar
el fix como innecesario, verificar siempre con `pstree -p <PID>` cuántos procesos reales hay, no
asumir por el `ExecStart=` del archivo base.

## AZ.3 Fix — generalizar el lock de líder existente (`shomer_poller_leader.py`)

Guardian ya tenía desde antes un lock de archivo (`fcntl.flock` no bloqueante sobre
`/tmp/shomer-poller.lock`) para evitar que su propio poller corriera duplicado bajo múltiples
workers. Se generalizó la función para aceptar un `lock_name` — permite locks independientes por
scheduler dentro del mismo servicio, sin que adquirir uno bloquee a los demás:

```python
def try_acquire_poller_leader(lock_name: str = "default") -> bool:
    # lock_name="default" preserva el comportamiento original de Guardian (un solo lock global)
    ...
    lock_path = _LOCK_PATH if lock_name == "default" else f"/tmp/shomer-poller-{lock_name}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fds[lock_name] = fd
        return True
    except BlockingIOError:
        os.close(fd)  # evita fd leak en el worker que pierde el lock
        return False
```

Aplicado con 3 nombres de lock distintos (no compiten entre sí, cada scheduler tiene su propio
archivo en `/tmp/shomer-poller-<nombre>.lock`):

| Scheduler | Archivo | `lock_name` |
|-----------|---------|-------------|
| Protector backup | `backups.py::start_backup_scheduler()` | `"protector-backup"` |
| Restore Drill | `restore_drill.py::start_drill_scheduler()` | `"restore-drill"` |
| Reportes PDF | `shomer_reports.py::start_report_scheduler()` | `"reports"` |

## AZ.4 Verificación real en Hotel Ópera (no solo unit tests)

Tras desplegar y reiniciar `shomer-tools.service`, `pstree -p <PID_padre>` confirmó 2 procesos
hijos reales (`spawn_main`). El log crudo (`/var/log/shomer/tools_api.log`, sin systemd de por
medio) mostró:

```
[protector][scheduler] worker pid=1761288 omitido — otro worker es líder
```

Un solo worker se excluyó — el otro asumió el rol de líder y arrancó los 3 schedulers. **Nota
sobre logging:** los mensajes de `restore_drill.py`/`shomer_reports.py` usan `logger.info()` en
vez de `print()` — como nadie llama `logging.basicConfig()` en el proceso, el logger raíz no
tiene handler para nivel INFO (el "last resort handler" de Python solo emite WARNING+), así que
esos dos no se ven en el log aunque corran el mismo mecanismo ya probado. No es un bug — solo
significa que para depurar estos 2 específicos hay que confiar en el comportamiento del lock
(`fuser <archivo>.lock`), no en buscar texto en el log.

## AZ.5 Estado de despliegue

| Servidor | Workers reales Tools | Fix desplegado | Verificado con `pstree`/log real |
|----------|----------------------|-----------------|-----------------------------------|
| `.205` | 1 (drop-in `bind-localhost.conf` lo fuerza) | ✅ código | Sin riesgo real — verificado por qué no aplica |
| **Hotel Ópera** | 2 (sin drop-in que lo limite) | ✅ | ✅ — un worker omitido confirmado en log |
| shomer245 / shomer243 | sin verificar | ✅ código sync (deploy.sh sin Ópera) | sin equipos Protector configurados aún — no urgente |

## AZ.6 Archivos

| Archivo | Cambio |
|---------|--------|
| `app/api/shomer_poller_leader.py` | `lock_name` parametrizable + `os.close(fd)` en la rama de fd leak |
| `app/api/backups.py` | `start_backup_scheduler()` usa lock `"protector-backup"` |
| `app/scripts/restore_drill.py` | `start_drill_scheduler()` usa lock `"restore-drill"` |
| `app/api/shomer_reports.py` | `start_report_scheduler()` usa lock `"reports"` |

---

# Parte BA — Sesión 59 (19-20 jun 2026) — Protector Zeus: B2 producción + retención + Drill rediseñado (3 capas)

## BA.1 Backblaze B2 — configurado en Hotel Ópera

Bucket compartido de la empresa (`shomer-backups`, mismo account_id que `.205`), con `b2_path` efectivo `hotel-opera` (slug automático desde `base.client_name="Hotel Opera"` vía `_effective_b2_path()` — sin necesidad de fijar `protector.b2_path` a mano, ver §D.1).

**Validado real:** sync manual del snapshot de Zeus (9 archivos `.bak`, 3.9 GB) → confirmado en B2 con `restic snapshots` contra `b2:shomer-backups:hotel-opera`. `schedule_b2_enabled=1` en el equipo Zeus — cada backup de las 5am sube su delta a B2 automáticamente.

## BA.2 Política de retención — decidida con Juan Pablo (20 jun 2026)

**Antes de esta sesión no existía ningún borrado automático en B2** — `restic copy` solo agrega snapshots, nunca los quita. Sin intervención, B2 crece sin límite (~4GB/día → ~1.4TB/año por equipo).

**Decisión producto (20 jun 2026):** 30 días de retención, tanto local como en B2.  
**Ópera en vivo (18 jul 2026):** `protector.retention_days=5` / `protector.b2_retention_days=3` — ver `SITE.md` §Protector. No subir a 30 sin pedido explícito del hotel.

| Config (`system_state`) | Valor (decisión 20 jun) | Efecto |
|---|---|---|
| `protector.retention_days` | `30` (Ópera hoy: **5**) | `_prune_local()` — sin cambios, ya existía |
| `protector.b2_retention_days` | `30` (Ópera hoy: **3**) | **Nuevo** — `_prune_b2()`, no existía nada similar antes |
| `protector.b2_sync_enabled` | `1` | Activa el sync global nocturno (antes solo corría el sync por equipo) |
| `protector.b2_sync_time` | `05:30` | Media hora después del backup de Zeus (05:00) |

**Implementación** (`app/api/backups.py`):
- `_get_b2_retention_days()` — espejo de `_get_retention_days()`, default 30 si no está configurado.
- `_prune_b2()` — `restic forget --keep-daily=N --prune` contra el repo B2 (no el local). Usa las mismas credenciales B2 que el resto del módulo.
- `_run_global_b2_sync()` ahora llama a `_prune_local()` **y** `_prune_b2()` tras el sync exitoso — antes solo podaba local.

**Por qué no se fijó antes un número exacto:** restic es incremental por bloques (deduplicado) — un snapshot diario de una BD que cambia poco NO pesa lo mismo que el snapshot completo. Con solo 1 backup real (el de hoy) no había datos para estimar el costo real de 30 días; se decidió fijar el límite igual (sin riesgo, porque hoy nada se borraba solo) y medir el crecimiento real en los próximos días.

## BA.3 Bug real — `update_backup_device()` borraba el horario en cualquier edición parcial

**Síntoma:** al activar `schedule_b2_enabled` desde un script (mismo camino que usa el botón "Activar/Pausar auto" del panel), `schedule_enabled` y `schedule_time` de Zeus quedaron en `0`/`NULL`.

**Causa:** el `SELECT` inicial de `update_backup_device()` (`app/api/backups.py`) no traía las columnas `schedule_enabled`, `schedule_time`, `schedule_b2_enabled` — cualquier `PATCH` que no las incluyera explícitamente hacía que `cur.get(...)` cayera al default (0/`None`), sobreescribiendo lo que ya estaba guardado. El botón del panel (`toggleSchedule()` en `backups.html`) solo envía `{schedule_enabled: enable}` — **nunca** mandó `schedule_time`, así que este bug afectaba a cualquier equipo, en cualquier sitio, cada vez que un técnico togglea el auto-backup desde la tabla de snapshots.

**Fix:** el `SELECT` ahora incluye las 3 columnas. Verificado con tests (14/14 OK) y manualmente en Ópera (horario de Zeus restaurado a `05:00` tras el incidente).

## BA.4 Bug real — `/srv/shomer_drill` no existía en ningún servidor

Ni siquiera en `.205` (el lab). El Drill nunca se había ejecutado con éxito en ningún sitio — antes fallaba primero por B2 sin configurar (Ópera, 1 jun) o por este mismo motivo en cualquier intento real. `/srv` es `root:root`; `usb_admin` no puede crear subdirectorios ahí sin que alguien lo haga una vez con `sudo`. Creado en `.205` y Ópera (`sudo mkdir -p /srv/shomer_drill && sudo chown usb_admin:usb_admin /srv/shomer_drill`) — pendiente revisar `install_shomer.sh` para que lo cree en instalaciones nuevas (mismo tipo de hueco que `/mnt/shomer_smb` en §AX.3).

**Bug adicional encontrado en el mismo módulo:** `restore_drill.py` importaba `RESTIC_REPO` desde `app.backend.protector` — esa constante **nunca existió** (el nombre real es `RESTIC_REPOSITORY`). Crasheaba con `ImportError` cada vez que el flujo llegaba al paso de `restic check` local. Corregido.

## BA.5 Incidente real — el Drill original tumbó Guardian en producción

Al probar el Drill (versión original, restore de snapshot completo) en Ópera durante horas activas: descargar el snapshot de Zeus completo (3.9 GB) desde B2 saturó CPU/disco/red del servidor lo suficiente para que `/health` no respondiera a tiempo al watchdog → loop de `SIGKILL`/reinicio de `shomer-guardian` cada 30-45s durante varios minutos (mismo síntoma externo que el bug de §AT/§AW, pero causa distinta: contención de recursos real, no un bug de código). Apagó el panel (parecía "todo caído", incluyendo el monitoreo de Zeus) mientras Zeus PMS en sí — servidor físico separado — nunca dejó de funcionar.

**Lección operativa:** una prueba de "verificación de backup" no debería poder competir por los mismos recursos que el monitoreo en vivo del sitio. Motivó el rediseño completo de §BA.6 — no alcanza con "probarlo en una ventana de mantenimiento", el diseño en sí tenía que dejar de necesitar descargar gigas.

## BA.6 Rediseño del Restore Drill — verificación en 3 capas, sin descargar el snapshot completo

**Antes:** `restic restore <snapshot completo> --target ...` — para un backup de Zeus de 3.9 GB, eso es 3.9 GB de descarga real cada vez que se quiere solo *confirmar que es recuperable*. Arriesga tanto al Shomer (CPU/disco) como al WAN real del cliente (un hotel puede tener ancho de banda compartido con huéspedes).

**Ahora** (`app/scripts/restore_drill.py::_run_drill_blocking()`), 3 capas independientes:

| Capa | Qué hace | Costo de red | Qué detecta |
|---|---|---|---|
| 1 — Hash de árbol | Compara el hash Merkle (`tree`) del snapshot local de origen (campo `original` que `restic copy` registra) contra el de su copia en B2 | ~0 (solo 2 llamadas `snapshots --json`, JSON de metadatos) | Corrupción de cualquier byte en cualquier archivo del snapshot — cobertura del 100% de los datos, prueba criptográfica |
| 2 — Restore de muestra | `restic ls` para listar archivos del snapshot, elige el **más pequeño**, `restic restore --include <ese archivo>` | El tamaño de 1 archivo (visto en Zeus: 1.1 MB de un snapshot de 3.9 GB) | Que la cadena cifrado→nube→descifrado→escritura a disco funciona de punta a punta (la Capa 1 no prueba que el restore real funcione, solo que los bytes no cambiaron) |
| 3 — `restic check` local | Verificación de estructura/índice del repo local (sin `--read-data` — no relee los datos) | 0 (solo disco local) | Corrupción del repo local mismo |

**Si la Capa 1 dice que el árbol NO coincide** → falla inmediatamente como error grave (posible corrupción real), sin gastar tiempo en las capas 2/3.

**Si no hay snapshot local de origen** (ya rotado por retención) → Capa 1 queda en `None` (no aplica, no es error) y el flujo sigue con las capas 2/3 igual.

**Robustez agregada:** si `restic check` local falla por un lock viejo (ej. de un proceso anterior matado con `kill -9`), se reintenta una vez tras `restic unlock` antes de reportar fallo real.

**Resultado nuevo** (`_run_drill_blocking()` retorna además): `total_files_in_snapshot`, `sample_file`, `sample_file_size_mb`, `tree_match` (`True`/`False`/`None`), `tree_check_msg`. Mensaje de Telegram (`_notify()`) actualizado para mostrar las 3 capas.

**Validado real:**
- `.205` (lab, snapshot SSH viejo): árbol coincidió, muestra de 0.712 MB, 12s totales.
- **Hotel Ópera (producción, snapshot real de Zeus de 3.9 GB):** árbol coincidió, muestra de 1.1 MB (de 9 archivos), **15 segundos totales**, repo check OK. Confirmado con `journalctl` que Guardian no tuvo ni un reinicio durante la prueba — a diferencia del intento con el diseño viejo.

## BA.7 Origen de la idea — colaboración en vivo

El rediseño salió de dos ideas del usuario en la misma conversación, tras el incidente de §BA.5: (1) restaurar solo un archivo en vez de todo el snapshot, y (2) comparar el archivo que se copia del cliente contra lo que queda en el Shomer/la nube para validar igualdad — esa segunda idea, llevada a su forma más eficiente con el hash de árbol que restic ya calcula internamente, terminó siendo la Capa 1 (verificación de costo ~0 que cubre el 100% de los datos, más fuerte que el muestreo de la Capa 2 sola).

## BA.8 Archivos y despliegue

| Archivo | Cambio |
|---------|--------|
| `app/api/backups.py` | `_get_b2_retention_days()`, `_prune_b2()` nuevos; `_run_global_b2_sync()` invoca ambos prunes; `update_backup_device()` SELECT corregido (incluye schedule_*) |
| `app/scripts/restore_drill.py` | Rediseño completo de `_run_drill_blocking()` (3 capas) + fix `RESTIC_REPO`→`RESTIC_REPOSITORY` + `_notify()` actualizado |

| Servidor | B2 + retención | Fix horario | `/srv/shomer_drill` | Drill v2 |
|---|---|---|---|---|
| `.205` | n/a (lab, sin cliente real) | ✅ código | ✅ creado | ✅ probado real |
| **Hotel Ópera** | ✅ configurado y validado | ✅ Zeus restaurado | ✅ creado | ✅ probado real (15s, 1.1MB) |
| shomer245 / shomer243 | ⏳ pendiente deploy | ⏳ pendiente deploy | ⏳ pendiente crear | ⏳ pendiente deploy |

---

# Parte BB — Sesión 60 (21 jun 2026) — Causa de fondo de los apagones recurrentes en Ópera

## BB.1 Contexto

Tras §BA, Hotel Ópera siguió presentando rachas de "todo caído" varias veces el mismo día (incluyendo durante esta sesión, en vivo). Instrucción explícita de Juan Pablo: no más parches puntuales — encontrar la causa de fondo, dado el riesgo real de negocio (el cliente/inversionistas podían cancelar el proyecto por inestabilidad). Esta sesión auditó sistemáticamente el patrón completo, no solo la función que falló esa vez.

## BB.2 El defecto estructural común a todos los incidentes (§AT, §AW, y hoy)

Guardian corre con **un solo worker** (`--workers 1`, un solo hilo de event loop). Cualquier escritura SQLite síncrona puesta directamente en un endpoint `async def` (sin `asyncio.to_thread()`) bloquea **el proceso entero** si choca con otro escritor (el poller de Inframonitor cada 30s, Hunter, Protector) — no solo el endpoint que la causó. El watchdog, con un timeout más corto que la espera legítima de SQLite, mata el proceso pensando que está muerto, generando un reinicio en cascada.

**Se evaluó y se descartó pasar a multi-worker** (`--workers 3`): aunque reduciría el radio de explosión por incidente, también multiplica cuántos procesos de Guardian pueden escribir al mismo tiempo (de "Guardian nunca compite contra sí mismo" a "3 Guardians compitiendo entre sí") — una variable nueva e incierta que no se quiso introducir bajo presión. Se optó por cerrar las causas reales en su lugar.

## BB.3 Hallazgo 1 — 5 módulos con `_init_tables()` ejecutado en cada request

Patrón repetido, escrito en sesiones distintas (32 a 58), por el mismo hábito: cada módulo llama su propio guard de creación de tablas **en cada endpoint**, no solo al arrancar. Esas funciones hacen `CREATE TABLE`/`ALTER TABLE` reales — DDL, el tipo de escritura SQLite más propenso a chocar con otro escritor.

| Módulo | Función | Endpoint disparador real (capturado con `py-spy` en vivo) |
|--------|---------|------------------------------------------------------------|
| `shomer_inframonitor.py` | `_init_tables()` + `_sync_guardian_aps()` | `GET /infra/devices` — cada carga del panel Inframonitor |
| `shomer_audit_network.py` | `_init_tables()` | Cualquier endpoint de Auditoría de Red |
| `shomer_incidents.py` | `_init_table()` | Cualquier endpoint de Incidentes |
| `shomer_status_events.py` | `_ensure_table()` | `GET /api/network/status-events` (polled ~30s por `/system-status`) |
| `shomer_topology.py` | `_ensure_tables()` | Cualquier endpoint de Topología |

**Fix:** bandera "ya inicializado" por proceso en cada uno — la migración solo corre una vez al arrancar, nunca más en el resto de la vida del proceso. Cero cambio de comportamiento, solo elimina el trabajo redundante que generaba el choque.

**Captura en vivo del incidente real:** `py-spy dump` durante un colgado real mostró el hilo principal atascado exactamente en `_sync_guardian_aps (shomer_inframonitor.py:174) ← list_devices (shomer_inframonitor.py:949)` — confirmando la teoría con evidencia directa, no especulación.

## BB.4 Hallazgo 2 — el poller de Inframonitor competía contra sí mismo

`record_status_event()` (en `shomer_status_events.py`) abría su **propia conexión nueva** de escritura cada vez que se llamaba — pero el poller de Inframonitor (`_poll_once()`) la llama **dentro** de su propio `with get_db() as conn:` que ya tiene una transacción de escritura abierta y sin comitear (acumula cambios de todos los dispositivos del ciclo antes de comitear al final). Resultado: el propio poller esperaba su propio lock hasta el `busy_timeout` (10s) por cada equipo que cambiaba de estado en el mismo ciclo de 30s — auto-contención, no un choque externo.

**Fix:** `record_status_event()` ahora acepta un parámetro opcional `conn=` — si se pasa, reutiliza esa transacción en vez de abrir una segunda. El único call site con riesgo real (`shomer_inframonitor.py`) ahora pasa su `conn` existente. Los otros 3 call sites (en `shomer_guardian_nodes.py`, el poller principal de Guardian) no tenían este problema — usan Redis para su propio estado, no abren una transacción SQLite abierta alrededor de la llamada.

## BB.5 Hallazgo 3 — el watchdog convertía una espera normal en un apagón

`/usr/local/bin/shomer-health-check.sh` usaba `curl --max-time 5` — pero `get_db()` usa `timeout=10` (el tiempo que SQLite espera legítimamente por un lock antes de fallar). Cualquier escritura que tardara entre 5 y 10 segundos en resolverse sola (situación normal bajo carga, no una falla real) era interpretada por el watchdog como "el servicio está muerto" → `SIGKILL` + reinicio — el disparador que convertía cada choque de lock en un apagón completo en vez de una demora de unos segundos.

**Fix:** `--max-time` subido a 12s (por encima del `busy_timeout` real) + un reintento de 3s antes de declarar el servicio caído. Aplicado en `.205`, Hotel Ópera, shomer245 y shomer243 — cada uno tenía su propia copia del script (no viaja con `deploy.sh`, vive en `/usr/local/bin/` fuera del repo, hubo que tocar cada servidor a mano).

## BB.6 Hallazgo 4 — autobloqueo Hunter, la ruta más sensible

`execute_hunter_block()` (disparada por cada alerta de Suricata que cumple la política de autobloqueo) hacía el `INSERT OR REPLACE INTO blocked_ips` de forma síncrona y directa en el hilo de Guardian, sin `to_thread()`. Durante una ráfaga real de alertas (el momento donde más importa que el panel siga respondiendo) cada autobloqueo podía competir por el lock hasta 10s, bloqueando todo el servidor. Envuelto en `asyncio.to_thread()`; probado real contra el MikroTik de Ópera (bloqueo + desbloqueo de la IP reservada de prueba `198.51.100.77`, nunca una IP operativa del hotel).

## BB.7 Hallazgo 5 — bug de esquema preexistente en shomer245/shomer243 (no causado por los fixes de hoy)

Al desplegar los fixes anteriores a los mini PCs de lab, ambos quedaron en loop de reinicio — pero por una causa **distinta y preexistente**, no por nada de lo hecho hoy: `/health` devolvía `503` real (`no such column: last_heartbeat`) porque la tabla `infra_nodes` se creó alguna vez con el esquema viejo (columna `last_seen`) y `shomer-monitor.service` —el servicio que crea la tabla con el esquema nuevo— **nunca había corrido** en ninguno de los dos equipos. El watchdog (con cualquier timeout) reiniciaba correctamente algo que de verdad estaba roto, sin poder arreglarlo solo.

**Fix inmediato:** migración aplicada vía el conector propio de la app (`app.backend.db.connect()`, no SQL crudo por CLI) — `ALTER TABLE infra_nodes ADD COLUMN last_heartbeat` + backfill desde `last_seen`.

**Fix permanente:** nueva función `ensure_infra_nodes_heartbeat_column()` en `shomer_guardian_nodes.py`, con guard de una sola vez, llamada desde `lifespan()` en `main.py` (no desde `/health` — eso fue justo la causa del incidente original de §AT.1). Cualquier servidor nuevo o viejo con este esquema desactualizado se autorepara al arrancar Guardian, sin depender de que alguien instale `shomer-monitor.service` a mano.

## BB.8 Despliegue y verificación

Todo desplegado vía el mecanismo oficial (`tools/deploy.sh`, con `SHOMER_DEPLOY_AUTHORIZED=1` para Ópera) — no copias manuales sueltas, excepto el watchdog (`/usr/local/bin/`, fuera del repo, no sincronizado por `deploy.sh`) y la migración de esquema (aplicada una vez por servidor, luego cubierta por el fix permanente de código).

| Fix | `.205` | Ópera | shomer245 | shomer243 |
|---|---|---|---|---|
| 5 guards `_init_tables()` | ✅ | ✅ | ✅ | ✅ |
| `record_status_event(conn=)` | ✅ | ✅ | ✅ | ✅ |
| `execute_hunter_block` → `to_thread` | ✅ | ✅ probado real (MikroTik) | ✅ | ✅ |
| Watchdog `max-time 12` + reintento | ✅ | ✅ | ✅ | ✅ |
| Migración `infra_nodes.last_heartbeat` | n/a (esquema ya correcto) | n/a (esquema ya correcto) | ✅ aplicada + permanente | ✅ aplicada + permanente |
| `/health` 200 OK verificado | ✅ | ✅ | ✅ | ✅ |

**Verificación en producción (Ópera):** sin reinicios nuevos en el watchdog durante 1h14min continuas tras el deploy, cubriendo de sobra la ventana de ~2h en la que recurría el patrón histórico de caídas. `/health` estable en ~12ms durante toda la ventana.

## BB.9 Bucles de fondo auditados y confirmados sin el mismo problema

Como parte de la misma revisión se auditaron los otros 4 bucles de fondo que arrancan en `lifespan()` de Guardian — ninguno requirió cambios, ya estaban bien diseñados:

- `_poller_tick()` (Guardian, cada 10s) — ping/SSH/SNMP ya en `asyncio.to_thread()`.
- `_server_health_tick()` — métricas del servidor ya en `to_thread()`.
- `retention_prune_loop()` / `outage_report_loop()` — ya envuelven su trabajo en `to_thread()`.
- El bloqueo SSH al firewall (`_fw_block`) usa `asyncssh`, async nativo, no bloqueante.

## BB.10 Principio para evitar que esto se repita

Cualquier función nueva que cree/migre tablas debe llevar el guard de una sola vez desde el primer commit (no agregarlo después de que cause un incidente). Cualquier escritura SQLite dentro de una ruta `async def` con tráfico real (no solo acciones puntuales de un técnico) debe envolverse en `asyncio.to_thread()` desde el diseño, no como corrección posterior. El watchdog nunca debe tener un timeout menor al `busy_timeout` real de la conexión que está verificando.

## BB.11 Anexo Sesión 60 (21 jun 2026) — B2 Ópera tenía contraseña incompatible, reinicializado

Durante la verificación del backup de Zeus de las 05:00 (corrió bien, local OK), se descubrió que el repo B2 `hotel-opera` daba `"ciphertext verification failed"` al intentar leerlo — la contraseña configurada como fallback automático (`/home/usb_admin/.restic-local-pass`, sin cambios desde el 21 de mayo) no coincidía con la que cifró ese repo en algún momento anterior. Esto significa que el sync nocturno a B2 (5:30am) venía fallando silenciosamente — el backup **local** de Zeus nunca estuvo en riesgo, pero la copia en la nube no se estaba actualizando.

**Diagnóstico:** descartada caché corrupta de restic (no es la causa). Sin acceso para recuperar la contraseña original ni evidencia de cuál fue.

**Decisión (autorizada explícitamente por Juan Pablo, con confirmación específica del paso irreversible):** borrar el contenido del path `hotel-opera/` en el bucket B2 (797 archivos, datos ilegibles de todas formas) y reinicializar el repo limpio con la contraseña correcta actual.

**Ejecución:** vía API nativa de B2 (`b2_authorize_account` → `b2_list_file_versions` → `b2_delete_file_version` por cada archivo bajo el prefijo) usando las credenciales ya almacenadas en `system_state` — sin mover ni exponer contraseñas entre servidores. `restic init` reinicializó el repo limpio (`4f1d0eb0ac`). Sync inmediato de verificación: ambos snapshots reales de Zeus (19 y 20 jun) subidos correctamente, con `tree` hash y `original` snapshot ID intactos — los mismos campos que usa la Capa 1 del Drill rediseñado (§BA.6).

**No relacionado:** el aviso de Telegram que el propio scheduler de Protector intenta mandar al grupo sigue fallando (`bot was kicked from the group chat`) — mismo problema preexistente de §AU.6, no causado por este fix.

---

# Parte BC — Sesión 61 (24 jun 2026) — Causa raíz real del flapping de Inframonitor (ping 1 paquete)

## BC.1 Contexto

Tras §AU (Sesión 58 — fix del pool de hilos del poller), Juan Pablo seguía viendo flapping falso en Ópera y concluyó que "el bot no sirve" — iba a escribir un documento para rediseñarlo desde cero. Antes de invertir en eso, se confirmó con datos reales que el problema seguía activo: 10+ equipos (`192.168.0.146, .111, .133, .240, .58, .136, .143, .1, .118, .129, .152, .168, .187, .212, .216`) con **30-36 transiciones offline↔online en 24h** (cada ~40-48 min), contenido únicamente por el debounce del bot (`_INFRA_OFFLINE_CONFIRM=2`) — no por una corrección real. El fix de §AU.2 (pool de hilos) era real y necesario, pero no era la única causa.

## BC.2 Causa raíz — `_ping()` con 1 solo paquete ICMP

`_ping()` en `app/api/shomer_inframonitor.py` mandaba **un solo** paquete (`ping -c 1 -W 2`). Cualquier pérdida transitoria de ese único paquete — normal en WiFi, PoE, switches reales bajo carga momentánea — se registraba como `offline` (caída total), sin distinguir "no respondió nada" de "perdió un paquete aislado". Con 50+ equipos monitoreados cada 30s, la probabilidad de que *alguno* pierda su único paquete en cualquier ciclo dado es alta — de ahí el patrón de flapping constante y repartido entre muchos equipos distintos, sin relación con fallas reales de hardware (confirmado: switches sanos con 0 errores SNMP flapeaban igual que los dañados `.168`/`.216`).

## BC.3 Fix — 3 paquetes + estado `degraded`

**Archivo:** `app/api/shomer_inframonitor.py::_ping()`

```python
PING_COUNT = int(os.environ.get("INFRA_PING_COUNT", "3"))
PING_LOSS_DEGRADED_PCT = int(os.environ.get("INFRA_PING_LOSS_DEGRADED_PCT", "60"))

def _ping(ip: str) -> tuple[str, Optional[float], float]:
    # 3 paquetes (igual criterio que Guardian, shomer_guardian_health_checks.py::_ping_metrics)
    # offline solo si se pierden TODOS; degraded si la pérdida sostenida supera el umbral
    ...
```

| Resultado del ping | Antes | Ahora |
|---|---|---|
| 0% pérdida | `online` | `online` |
| Pérdida parcial (1-2 de 3) | `offline` (falso positivo) | `degraded` |
| 100% pérdida | `offline` | `offline` (sin cambio — caída real) |

**Comportamiento de `degraded`:**
- Visible en panel (`inframonitor.html` — dot/badge ámbar, `% pérdida` mostrado) y en NOC
- **No dispara alerta Telegram** — solo los cruces reales hacia/desde `offline` generan aviso (`is_real_outage_edge = status == "offline" or prev_status == "offline"`)
- Nueva columna `loss_pct` en `infra_status`, expuesta en `/infra/status` y `/infra/devices`

**Archivos modificados:** `app/api/shomer_inframonitor.py` (lógica + columna `loss_pct`), `app/templates/inframonitor.html` (UI estado `degraded`). Commit `01873f6`.

## BC.4 Validación

- `.205`: poller reiniciado, sin errores, columna `loss_pct` poblándose correctamente (lab solo tiene 2 equipos activos — no reproduce el escenario de pérdida parcial real).
- **Hotel Ópera** (autorizado por Juan Pablo): `deploy.sh` + reinicio manual de `shomer-inframonitor-poller.service` (recordatorio: `deploy.sh` no reinicia este servicio, hay que hacerlo a mano — ver §AU.2/§AZ.5). Primer ciclo post-deploy: 52/53 equipos `online` con `loss_pct=0.0`, 1 `offline` real — sin falsos positivos en el primer ciclo.
- Pendiente confirmar con el tiempo (ventana ≥1h, dado que el patrón histórico era de transiciones cada ~40-48 min) que el conteo de transiciones bajó de forma sostenida frente al baseline de 30-36/24h por equipo.

## BC.5 Implicación para el rediseño del bot

La queja de Juan Pablo ("el bot no sirve") tenía como causa real el ruido de falsos positivos de Inframonitor — no el diseño del bot en sí (ver `feedback_validar_dolor_real_antes_de_features` en memoria). Si la validación de §BC.4 confirma que el flapping bajó de forma sostenida, vale la pena revisar con él si el documento de rediseño completo del bot sigue siendo necesario, o si el problema raíz ya quedó resuelto aquí.

## BC.6 Pendiente sin relación — switches dañados `.168`/`.216`

Sigue pendiente la revisión física en sitio de estos dos switches (errores SNMP acumulados reales: 95,534 y 50,587/2,860 respectivamente, según §AU.5) — **no** es el bug de flapping corregido en esta sesión, es daño de hardware real (cable, transceiver, o equipo conectado al puerto). Confirmado que switches sanos (`.118`, `.129`, `.133`, 0 errores SNMP) flapeaban igual que estos dos antes del fix de §BC.3 — la correlación temporal del flapping no tenía relación con el daño físico.

---

# Parte BD — Sesión 62 (29–30 jun 2026) — Estabilización Ópera: Fase 3 perfiles, poller, bot y bitácora

## BD.1 Contexto

Tras §BB (apagones Guardian), §BC (ping 3 paquetes + `degraded`) y §AU (debounce Infra), Juan Pablo pidió auditoría integral en Hotel Ópera: el poller seguía siendo cuello de botella, los APs se pingueaban dos veces (Guardian + Infra), `memoria_alertas` no distinguía qué monitor envió cada Telegram, y el histórico `infra_legacy` inflaba `memoria.db` sin aportar valor. Esta sesión cerró esos frentes en producción.

## BD.2 Poller Inframonitor — rendimiento y robustez

| Cambio | Archivo / unidad | Efecto |
|--------|------------------|--------|
| `CPUQuota=100%` | `/etc/systemd/system/shomer-inframonitor-poller.service` | Poller ya no se queda sin CPU a mitad de ciclo |
| Pools auto-escala | `shomer_inframonitor.py` — `_scaled_fast_workers`, `_scaled_snmp_workers` | Hilos fast/SNMP separados según cantidad de equipos |
| Fix `cb_block` + logging blip | `shomer_inframonitor.py` | Menos falsos bloqueos y trazas útiles en journal |
| Confirmación impresoras | Agente `INFRA_OFFLINE_CONFIRM_PRINTER=3` | Debounce extra para POS/impresoras |

**Validación Ópera (30 jun):** poll fast ~22 equipos, ~3,4 s/ciclo, 0% ciclos >30 s (log `infra poll fast: ... devices=22`).

## BD.3 Fase 3 — perfiles `monitor_profile` y APs fuera del ping

Nuevo módulo `app/api/infra_monitor_profiles.py`:

| Perfil | Uso |
|--------|-----|
| `ap_guardian` | AP: **sin ping Infra**; estado desde Guardian/`infra_nodes` |
| `network_gear` | Switch/router con SNMP: frescura SNMP manda sobre ping |
| `printer` | Impresora/POS: ping laxo (2 paquetes) |
| `endpoint_tcp` | Servidor/POS con `tcp_port`: TCP manda |
| `generic` | Ping estándar (3 paquetes) |

- Columna `monitor_profile` en `infra_devices` + backfill al arrancar poller.
- `_sync_guardian_aps()` asigna `ap_guardian` a reflejos de AP.
- `derive_liveness()` por perfil en el poller; ciclo fast excluye `ap_guardian` del ping.
- Espejo de estado AP: `infra_nodes` (no `devices.status` directo en el poller).

## BD.4 Guardian — sync panel y debounce offline

`app/api/shomer_guardian_nodes.py`:

- `_sync_devices_status_from_infra_nodes()` — alinea `devices.status` del panel con `infra_nodes` (fix APs desincronizados en Guardian vs Infra).
- `offline_streak` + `SHOMER_OFFLINE_PERSIST_TICKS` (default 3) — alerta offline Guardian solo tras N ticks consecutivos (complementa §AN fix recuperación huérfana).

## BD.5 Bot — intervalo Infra, SNMP puertos, predictivo e IA

Variables en `/storage/shomer-agent/.env` (Ópera):

```
WATCH_INFRA_INTERVAL_SEC=60
INFRA_SNMP_PORT_ALERTS=1
INFRA_OFFLINE_CONFIRM_PRINTER=3
MEMORIA_SYNC_INFRA_LEGACY=0
```

| Feature | Código | Comportamiento |
|---------|--------|----------------|
| Loop Infra 60 s | `monitor.py` — `_WATCH_INFRA_INTERVAL_SEC` | Menos carga; mínimo 30 s |
| Alertas puerto SNMP | `watch_infra` + `_INFRA_SNMP_PORT_ALERTS` | UP→DOWN en switch/router/server/NAS/controller |
| Sin sync legacy | `memoria_central.py` — `SYNC_INFRA_LEGACY` | No importar `infra_events` antiguos a `memoria_incidentes` |
| Predictivo | `pattern_analysis.py` — `tendencia`, `alert_suffix()` | Sufijo en alertas Guardian si entidad “degradando” |
| Diagnóstico IA | `monitor.py` — `_diagnostico_degradando` + `_emit_guardian` | OpenAI explica AP degradando; monitor `ia_diagnostico` |

Limpieza: 5.467 filas `source='infra_legacy'` purgadas de `memoria.db` (backup previo en sitio).

## BD.6 Etiquetado `memoria_alertas` por monitor

**Problema:** casi todas las alertas se guardaban como `monitor='bot'` porque `_send()` no recibía el nombre del watcher.

**Fix** (`core/monitor.py` + `memoria_central.log_telegram_alert`):

- `_resolve_monitor()` + `ContextVar` `_monitor_ctx`
- `_send` / `_send_critical` aceptan `monitor=` y registran en `memoria_alertas`
- `_emit()` pasa `monitor=origen`
- **53 llamadas** `_send`/`_send_critical` etiquetadas (sub-monitores Infra: `watch_infra_equipment`, `watch_infra_flap`, `watch_infra_printer`, `watch_infra_service`, `watch_infra_snmp`)
- `ia_diagnostico` en `MONITOR_LABELS` (`bot.py`)

**Histórico:** filas antiguas **no se migraron** (234 con `monitor='bot'`). Siguen visibles en `/bitacora` y en el contador de alertas; solo pierden clasificación por monitor. Las nuevas alertas ya llevan etiqueta correcta.

Consulta útil:
```sql
SELECT monitor, COUNT(*) FROM memoria_alertas GROUP BY monitor ORDER BY 2 DESC;
```

## BD.7 Estado Ópera post-deploy

| Métrica | Valor |
|---------|-------|
| Poll fast | ~3,4 s, 22 equipos |
| APs | 28 online / 2 offline (Guardian e Infra alineados) |
| Offline reales pendientes campo | SW-REST-SCALA, POS Bixolon, AP 108, AP REST SCALA, IMP Recepción |

Despliegue: código Guardian/poller vía autorización habitual; agente `docker compose up -d --force-recreate` en `/storage/shomer-agent`.

## BD.8 Pendientes (no bloqueantes)

- Revisión física 5 equipos offline + switches `.168`/`.216`
- Rotar token Telegram si quedó expuesto en sesión
- Medición 7 días debounce OFC-COCINA
- Validar suffix predictivo + `ia_diagnostico` en Telegram en vivo
- Vigilar costo OpenAI primera semana

Detalle operativo del sitio: `SITE.md` §Estabilización Inframonitor + bot.

---

# Sesión 63 — 29–30 jun 2026 (Hotel Ópera) — §BE

## BE.1 Contexto

Sesión operativa en `shomer-hotelopera` tras §BD: retención Protector, falsa alarma Hunter nocturna, cierre de incidentes al desbloquear IP, excepciones laptops HP, mantenimiento APs Guardian, falso positivo papel impresora WF-M5899, y auditoría de equipos offline reales.

## BE.2 Protector / backups `/srv`

| Tema | Detalle |
|------|---------|
| Retención | Local **10 días**, B2 **3 días**, sync B2 **05:30** |
| Incidente | Lock Restic desde 25/jun bloqueaba `prune` → 11 snapshots locales acumulados |
| Fix manual | `restic unlock` + `prune` local y B2 (B2: 11→3 snapshots) |
| TASK-005 logs | Silenciar Telegram si no hay nada que truncar; mostrar nombre de archivo si trunca (`auto_tasks.py`) |
| Logrotate | `/etc/logrotate.d/shomer` — `maxsize 50M` (solo sistema, no en git) |

## BE.3 Hunter — falsa alarma nocturna Suricata

**Problema:** `casador_support_health` marcaba Hunter caído si `eve-alerts.json` no crecía, aunque Suricata procesaba tráfico en `eve.json`.

**Fix** (`app/api/casador_support_health.py`):

- Liveness por actividad en `eve.json` (tráfico), no solo `eve-alerts.json`
- Texto del bot actualizado en `core/monitor.py`

## BE.4 Incidentes — desbloquear IP no cerraba incidente

**Fix** (`app/api/shomer_incidents.py` — `close_incidents_on_unblock()`):

- Al desbloquear IP desde panel, cierra incidente(s) asociados
- `casador_blocking.py` llama cierre en `unblock`
- `incidents.html` pasa `incident_id` al desbloquear

## BE.5 Excepciones Hunter — laptops HP

11 IPs añadidas a `hunter.auto_block_exceptions` en `system_state` (desde `inventory.db`). Documentado en `SITE.md`.

## BE.6 APs en mantenimiento Guardian

`.210` (AP HAB 108) y `.239` (AP REST SCALA) en `node_maintenance:*` = 1, sin expiración (TTL -1). Evita alertas mientras equipos físicos offline.

## BE.7 WF-M5899 — falso positivo papel bajo

**Causa:** solo se leía bandeja 1 (`0/80`); bandeja 2 reporta `-3` (con papel).

**Fix multi-bandeja:**

| Archivo | Cambio |
|---------|--------|
| `shomer_inframonitor.py` | `_summarize_printer_paper` — snmpwalk todas las bandejas |
| `monitor.py` | Usa `paper_ok` / `paper_low` |
| `inframonitor.html`, `noc.html` | UI papel por impresora |
| `drivers/printer.py` | Agente — lectura multi-bandeja |

## BE.8 Revisión offline real (29 jun ~11:44 Bogotá)

Equipos **sin ping/TCP/SNMP** desde Shomer (~12 h estables al cierre de sesión):

| IP | Equipo |
|----|--------|
| `.212` | SW-REST-SCALA |
| `.56` | Bixolon POS |
| `.239` | AP REST SCALA |
| `.210` | AP HAB 108 |

Gateway y demás switches responden OK — **revisión física pendiente**.

## BE.9 Archivos tocados (sync git + deploy)

**App:** `casador_support_health.py`, `shomer_incidents.py`, `casador_blocking.py`, `shomer_inframonitor.py`, `backups.py`, `incidents.html`, `inframonitor.html`, `noc.html`, `backups.html`

**Agente:** `core/monitor.py`, `core/auto_tasks.py`, `core/ui_notify.py`, `drivers/printer.py`

**Solo sitio (no deploy):** `SITE.md`, `CLAUDE.md`, BD `system_state`, `/etc/logrotate.d/shomer`

## BE.10 Despliegue

1. Rsync Ópera → `usb-shomer-205` (`/opt/network_monitor/app/`, agente)
2. `git commit` + `push` en `.205`
3. `bash tools/deploy.sh` → lab `shomer245` + `shomer243`
4. `SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh 100.103.148.119` → Ópera (código; BD/SITE locales intactos)

## BE.11 Pendientes

- Revisión física 4 equipos offline (§BE.8)
- Cerrar incidentes viejos abiertos vía Desbloquear (tras fix §BE.4)
- Histórico `memoria_alertas` con `monitor='bot'` no migrado (§BD.6)

---

# Sesión 64 — 2 jul 2026 (Hotel Ópera) — §BF

## BF.1 Hunter — mensajes legibles para técnicos

Nuevo módulo `app/api/hunter_signature_labels.py` (+ `core/hunter_labels.py` en agente).

Traduce firmas Suricata/ET a español en Telegram, panel Hunter, incidentes y bot `watch_hunter`:

| Firma técnica (ejemplo) | Mensaje humano |
|-------------------------|----------------|
| `ET CINS … Poor Reputation` | IP con mala reputación (lista CINS) |
| `ET DROP Dshield` | IP en lista negra DShield |
| `ET DROP Spamhaus` | IP en lista Spamhaus DROP |
| `ET P2P eMule` | Tráfico P2P sospechoso |

Cada alerta incluye: qué significa, nivel de riesgo, acción para el técnico, regla técnica al final.

**Archivos:** `casador_blocking.py`, `casador_support_hunter_recurrence.py`, `shomer_incidents.py`, `hunter.html`, `incidents.html`, `core/monitor.py`

## BF.2 Documento revisión en sitio

`docs/campo/REVISION-EN-SITIO-OPERA.md` — checklist vivo para Cristian/Ricardo:

- Offline crónicos, flapping, microcorte 13:07
- Investigación blips Shomer (sin fix software)
- Mensaje Telegram listo para copiar
- Tabla historial de visitas

## BF.3 Investigación `host_network_blip` — sin fix (pendiente causa raíz)

**Contexto:** huéspedes y servicios del hotel **no reportaron falla de internet**. Gateway `192.168.0.1` responde bien entre eventos. Shomer a veces pierde visibilidad LAN.

### Dos fenómenos distintos

| Tipo | Cuándo | Guardian | Infra | Telegram masivo |
|------|--------|----------|-------|-----------------|
| **A — Blip Shomer** | Madrugada (ej. 06:32–06:37) | No oleada | Sí, `host_network_blip` | No (supresor OK) |
| **B — Microcorte real** | Mediodía (13:07–13:14) | Sí, muchos APs | Sí, switches/impresoras | Sí |

No confundir A con B. Solo B afectó usuarios potencialmente.

### Evidencia tipo A (blip Shomer — 2 jul)

| Dato | Valor |
|------|-------|
| Blips 7 días | **131** eventos |
| Patrón | Ráfagas de **~3 ciclos** (poll cada 30 s ≈ 90 s) |
| Guardian 06:00–08:00 | **0** eventos masivos |
| Ping normal | **~1,3–3,5 s** (22 equipos) |
| Ping en blip | **~10–11,3 s** — firma de **timeout ICMP total** (`_ping` timeout 9 s + overhead) |
| Transición | 06:31:34 ping OK (1370 ms) → 06:32:11 blip en **37 s** — corte brusco, no degradación lenta |
| Recheck blip | 300 ms — gateway a veces recupera en el recheck (falso positivo de duración sub-segundo) |

### Evidencia hardware Shomer

| Dato | Valor |
|------|-------|
| NIC gestión | `eno1` — link 1000/full, **sin errores RX/TX** |
| RX dropped acumulado | **~12 M** paquetes — investigar tasa (no solo total lifetime) |
| RX missed | 773 (bajo) |
| ARP gateway | `REACHABLE` vía `eno1` |

### Hipótesis ordenadas (sin confirmar)

1. **Cable o puerto del switch** donde está Shomer (`.250`) — más probable para tipo A
2. **Buffer/NIC `eno1`** bajo ráfaga ICMP (22 hosts × 3 paquetes cada 30 s)
3. **Microcortes LAN admin muy breves** que solo el poller Infra captura (< tick Guardian)
4. **Descartada como causa principal:** WAN/MikroTik caído (huéspedes OK, gateway OK entre blips)

### Qué NO hacer hasta confirmar

- No bajar umbrales del supresor de blips
- No silenciar logs `host_network_blip`
- No cambiar `INFRA_FAST_POLL_INTERVAL_SEC` ni timeouts de ping sin evidencia

### Próximos pasos investigación

- [ ] Campo: cable + puerto switch de Shomer (checklist en `REVISION-EN-SITIO-OPERA.md`)
- [ ] USB: registrar `RX dropped` en `eno1` cada 24 h (delta, no acumulado)
- [ ] USB: `mtr 192.168.0.1` 24 h desde Shomer (opcional)
- [ ] Correlacionar si blips coinciden con tareas pesadas en Shomer (backups, scans)

**Estado:** investigación abierta — **sin fix software aplicado**.

## BF.4 VPN MikroTik — mensajes informativos (no alerta de enlace)

Puertos OpenVPN (`ovpn-sistemas`, etc.) usados por USB Ingeniería: Telegram **solo conexiones** desde sesión 66 (`INFRA_VPN_ALERT_DISCONNECT=0`). Puertos físicos `ether*` y switches mantienen alertas de enlace. Ver `monitor.py` `watch_infra_vpn`.

## BF.5 Pendientes sesión 64–66 (cerrar sync)

- [ ] Sync sesiones 64–66 → `.205` / GitHub / deploy estándar (lab online 8 jul)
- [ ] Rotar token Telegram (expuesto en sesión antigua)

---

# Sesión 65 — 8 jul 2026 — §BH — Shomer Pulse en producción Ópera

## BH.1 Entregado (software — producto multi-cliente)

| Mejora | Estado |
|--------|--------|
| Pulse Correlate — oleada LAN, blip Shomer, recuperación oleada | ✅ |
| Pulse EWMA — `infra_pulse`, alerta degradando | ✅ `INFRA_PULSE_ENABLED=1` |
| IA diagnóstico — cooldown 6 h por equipo | ✅ |
| Debounce puertos SNMP — 2 polls | ✅ |
| `watch_infra_pulse` monitor | ✅ |

## BH.2 Pendientes activos post-sesión 65

Ver listado maestro en `SITE.md` §Pendientes activos (8 jul 2026).

---

# Sesión 66 — 8 jul 2026 — §BI — Salud host + VPN + auditoría estado

## BI.1 Entregado (software)

| Mejora | Estado |
|--------|--------|
| `shomer_host_health.py` — blips en SQLite + muestras NIC | ✅ |
| Resumen diario 07:00 — visibilidad blips + RX dropped `eno1` | ✅ |
| API `GET /api/host-health/daily` | ✅ |
| VPN Telegram solo conexiones (`INFRA_VPN_ALERT_DISCONNECT=0`) | ✅ |

## BI.2 Estado Ópera verificado (8 jul ~12:35 COT)

| Métrica | Valor |
|---------|-------|
| Infra activos | 50 online / 2 offline (`.148`, `.243`) |
| Guardian APs | 29 online / 1 offline |
| Offline crónico extra | IMP Recepción `.57` (inactive Infra, offline desde 10 jun) |
| Pulse degradando | IMP SCOCINA `.58` (71 ticks) |
| Blips poller | 3 / 24 h · 56 / 7 días |
| Telegram 3 días | 138 msgs |
| Switch `.168` GE49 | ~95.534 `in_errors` |

## BI.3 Pendientes activos

Ver `SITE.md` y `docs/campo/REVISION-EN-SITIO-OPERA.md` (actualizados 8 jul 2026).

---

# Sesión 67 — 17–18 jul 2026 (Hotel Ópera) — §BJ — Protector

## BJ.1 Auditoría Protector (solo módulo)

| Tema | Hallazgo |
|------|----------|
| Equipo | Zeus PMS `.5` — SMB → Restic local → B2 `hotel-opera` |
| Fallo 17 jul ~05:00 | Restic índice/permiso + lock huérfano; sin snapshot del día |
| Panel | `verified_ready` sin `last_snapshot_id` (falso verde) |
| Auth `/backups/*` | 401 sin JWT — OK |
| Retención viva Ópera | 5 local / 3 B2 (divergente de decisión 30/30 §BA.2) |

## BJ.2 Recuperación (adelante 18 jul)

| Paso | Resultado |
|------|-----------|
| `restic unlock` staging | OK |
| Backup one-shot dumps `*_2026_07_17_*` | Local **`195e55af`** (9 archivos, ~38 s) |
| Sync B2 | **`fb25f703`** (mismos paths) |
| Panel | `last_status=ok`, `last_snapshot_id=195e55af` |
| Patrón schedule | sin cambio: `*_{today}_*` |

**Nota operativa:** `backup_now` tras medianoche Bogotá busca dumps del día nuevo; Zeus genera ~03:00. Si hace falta recuperar el día anterior, override puntual del patrón (no persistir en BD).

## BJ.3 Docs

- `SITE.md` Ópera: sección **Protector** (config viva + último OK) — **no va a git**
- Canvas local: `protector-auditoria.canvas.tsx`

**Sin código de producto en esta sesión** (solo operación + docs). Sync GitHub = este `CLAUDE.md` §BJ.

---

# Sesión 68 — 21 jul 2026 (Hotel Ópera) — §BK — Hunter + Protector + bot

## BK.1 Hunter — la cadena Wazuh ahora respeta `only_external`

**Bug real:** `execute_hunter_block()` (`app/api/casador_blocking.py`) aplicaba `only_external`
**solo** en el camino `blocked_by=auto`. El camino `blocked_by=wazuh` únicamente miraba
`hunter.auto_block_exceptions` → **bloqueaba IPs internas** del sitio que no estuvieran
listadas explícitamente (p. ej. `192.168.0.28` por firma `ET POLICY ... pin= in cleartext`,
sev 1). En Ópera 66/72 bloqueos venían por Wazuh, así que la regla "solo externas" no se
cumplía en la práctica para esa vía.

**Fix:** en el bloque `if blocked_by == "wazuh"`, tras la comprobación de excepciones se añadió:

```python
if policy["only_external"] and not _is_external_ip(ip):
    return {"success": False, "skipped": True,
            "detail": "IP interna del sitio; Hunter solo autobloquea externas (only_external)..."}
```

Ahora una IP interna (en `hunter.subnets`) **no** se autobloquea por Wazuh aunque una regla
POLICY dispare sobre ella. El **bloqueo manual** desde el panel sigue disponible.
Diferencia vs camino `auto`: aquí **no** hay excepción por severidad crítica (1) — en la LAN
del hotel esas alertas eran falsos positivos. Verificado: internas `→ skip`, externas `→ block`.

## BK.2 Protector — permisos del repo Restic

La recuperación del 17 jul (§BJ) se corrió con `sudo` → dejó ~808 archivos `root` en
`/srv/shomer_backups/staging`. Como `shomer-tools` corre **como `usb_admin`**, los backups
programados del 19–21 jul fallaron con `Load(<index/...>) ... permission denied`.
**Fix (21 jul):** `chown -R usb_admin:usb_admin /srv/shomer_backups/staging` → backup Zeus
OK (`d628f1df`, 9 archivos) + sync B2. **Regla:** nunca correr backup/restore Protector con
`sudo`; siempre por el servicio o como `usb_admin`.

## BK.3 Bot — mensaje `watch_groq` corregido

`storage/shomer-agent/core/monitor.py`: la alerta decía siempre "Groq sin conexión" aunque
la causa real fuera **cuota/rate-limit del plan free** (TCP abría, la API rechazaba). Ahora
distingue `limite` / `sobrecargado` / `sin_conexion` y aclara "No es caída del hotel".
(Agente = repo aparte `/storage/shomer-agent`, no entra en el sync de `/opt/network_monitor`.)

## BK.4 Bot — IA/Groq: fin de los "Groq caído" repetidos (auditoría IA+Telegram)

Causa raíz confirmada: **no es caída**, es el **plan free de Groq** (límites RPM/TPM/RPD).
Consumo real 8k–20k tok/día, muy por debajo del tope local 120k → el presupuesto NO era el problema.
Canvas: `ia-telegram-auditoria.canvas.tsx`. Cambios en `/storage/shomer-agent/core`:

- **`watch_groq`** (`monitor.py`): el chequeo cada 5 min usaba un `chat.completions.create` real
  (288 llamadas/día que **gastaban cuota** del free) → ahora `models.list()` (verifica API+credencial
  **sin consumir tokens**, no toca TPM). Además la alerta tiene **tope 1/día** (`_groq_alert_day`);
  antes re-alertaba cada ventana de ≥10 min.
- **`_call_groq`** (`groq_helper.py`): un 429 de una llamada de **fondo** llamaba `maintenance.pause()`
  y **apagaba el bot entero ~90 s** (chat incluido) aunque nadie usara Telegram → ya **no pausa** por
  un 429 aislado. Nuevo parámetro `background=True` (monitores/patrones) devuelve "" y se salta la
  llamada; el chat interactivo conserva su aviso. `explain(background=True)` por defecto.
- **`pattern_analysis.py`**: payload 6000→2500 y `max_tokens` 1200→600 (una sola llamada excedía TPM
  del free → 429). Si Groq no responde (límite), se trata como "sin hallazgos" en vez de anotar
  "respuesta no es JSON válido".

Verificado: `py_compile` OK · contenedor reiniciado · 28 monitores · `models.list` 15 modelos · 0 tracebacks.

## BK.5 Protector — panel "sin snapshots" (caché restic con dueño root)

Síntoma: el panel de backups mostraba **0 snapshots locales** aunque `restic snapshots` sí lista **9**
(21/22/23 jul OK). Diagnóstico: `restic snapshots` tardaba **~44 s** por errores `permission denied`
en `~/.cache/restic/**/snapshots/{19,fb}` → el panel expira y muestra vacío. Causa: el rescate con
`sudo` del 18 jul (§BJ.2) dejó **2 carpetas de caché propiedad de `root`** (snapshots `195e55af` local y
`fb25f703` B2); ese día se corrigió el dueño del **repo** pero **no del caché**.
Fix: `restic unlock` (2 locks huérfanos del restart de `shomer-tools` 05:12) + `sudo chown -R
usb_admin:usb_admin /home/usb_admin/.cache/restic`. Resultado: `restic snapshots` **43.9 s → 0.47 s**.
**Lección:** tras cualquier `sudo restic`, chequear/corregir dueño de repo **y** de `~/.cache/restic`.

---

# Parte BG — Shomer Pulse — capa predictiva Infra

**Nombre producto:** **Shomer Pulse** — **Correlate** (oleadas/blip) ✅ + **EWMA** (latencia predictiva) ✅  
**Objetivo:** detectar deterioro de red **antes** del offline; complementa polling ICMP, `degraded`, `host_network_blip` y `tendencia` en `knowledge.db`.  
**Alcance:** código universal multi-cliente; activación `INFRA_PULSE_ENABLED` / `infra.pulse.enabled`. Sin lógica por sitio.

## BG.1 Contexto vs estado actual

| Capacidad | Hoy | Con Pulse EWMA |
|-----------|-----|----------------|
| Latencia instantánea | `infra_status.latency_ms` cada poll ~30 s | Igual + serie EWMA |
| Degradación | `degraded` si pérdida ICMP ≥ `INFRA_PING_LOSS_DEGRADED_PCT` (60%) | Alerta **degradando** si EWMA sube N polls (equipo aún `online`) |
| Predictivo | `pattern_analysis.tendencia` — caídas semana vs semana (post-incidente) | EWMA en tiempo real (~5 polls ≈ 2,5 min) |
| Correlación oleadas | `batch_id`, `status_events`, `correlate_outage_to_switches()` | Fase 2 Pulse (ver BG.4) — topología `network_links` hoy vacía en Ópera |

## BG.2 Pulse EWMA — diseño acordado (MVP)

**Módulo nuevo:** `app/api/shomer_infra_pulse.py`  
**Tabla nueva:** `infra_pulse` en `network_monitor.db`:

```sql
CREATE TABLE IF NOT EXISTS infra_pulse (
    ip                  TEXT PRIMARY KEY,
    ewma_latency_ms     REAL,
    ewma_loss_pct       REAL,
    baseline_latency_ms REAL,
    degrade_ticks       INTEGER DEFAULT 0,
    pulse_state         TEXT DEFAULT 'stable',  -- stable | degrading | recovered
    last_alert_at       TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);
```

**Estados Pulse:** `stable` → `degrading` (N polls) → `recovered` → `stable`.  
**Regla MVP:** Pulse **no cambia** `infra_status.status` al inicio — solo enriquece alertas y Redis `infra:{ip}:pulse`.

**Fórmula:** `ewma = alpha * sample + (1 - alpha) * prev` (~5 líneas Python).

**Config por sitio (env / `get_config`):**

| Clave | Default | Ópera piloto |
|-------|---------|--------------|
| `INFRA_PULSE_ENABLED` | `0` | `1` |
| `INFRA_PULSE_ALPHA` | `0.25` | `0.25` |
| `INFRA_PULSE_LATENCY_FACTOR` | `1.5` | `1.4` |
| `INFRA_PULSE_PERSIST_TICKS` | `5` | `6` |
| `INFRA_PULSE_ALERT_COOLDOWN_SEC` | `1800` | `1800` |
| `INFRA_PULSE_TIMEOUT_MS` | `9000` | `9000` |

**Enganche:** `shomer_inframonitor.py` — bucle fast poll, post-`_ping`, pre-`pending_rows`.  
**Telegram:** `storage/shomer-agent/core/monitor.py` — alerta suave “⚠️ Pulse — {equipo} degradando” con cooldown; respetar supresor blip; **no** `ia_diagnostico` en cada pulse.  
**Opcional MVP+:** sincronizar `patrones_detectados.tendencia = 'degradando'` para reutilizar `alert_suffix()` en bot.

## BG.3 Checklist implementación Pulse (producto multi-cliente)

- [x] **Fase 2a — Pulse Correlate** — `shomer_pulse_correlate.py` + Redis `infra:poll:context` / `blip_last`
- [x] **Fase 2b** — `/infra/devices` expone `poll_context` + `last_blip` (cualquier sitio)
- [x] **Fase 2c** — Agente `pulse_correlate.py`: oleada LAN (≥`PULSE_WAVE_MIN_DEVICES`), blip informativo, recuperación oleada
- [x] **Fase 2d** — `watch_infra_pulse` monitor; IA diagnóstico con cooldown (`IA_DIAGNOSTICO_COOLDOWN_SEC`, default 6h)
- [x] **Fase 2e** — Debounce puertos SNMP (`INFRA_SNMP_PORT_DEBOUNCE_POLLS`, default 2)
- [x] **Fase 1 — Pulse EWMA** — `shomer_infra_pulse.py`, tabla `infra_pulse`, `INFRA_PULSE_ENABLED=1` Ópera
- [ ] **Fase 3** — Syslog MikroTik
- [ ] **Fase 6** — Panel badge Pulse en UI
- [ ] **Fase 7** — Tuning multi-cliente post-piloto (2–3 días observación)
- [ ] **Opcional** — Topología `network_links` + mensaje “switch padre” (UniFi API o mapa manual; **no** endurecer SNMP `public`)

**Variables estándar (env, default OFF o conservador):**

| Variable | Default | Rol |
|----------|---------|-----|
| `PULSE_WAVE_MIN_DEVICES` | `3` | Mínimo equipos para 1 Telegram oleada |
| `PULSE_BLIP_INFORM_COOLDOWN_SEC` | `3600` | Máx. 1 aviso blip Shomer / hora |
| `IA_DIAGNOSTICO_COOLDOWN_SEC` | `21600` | 1 diagnóstico IA / equipo / 6h |
| `INFRA_SNMP_PORT_DEBOUNCE_POLLS` | `2` | Puertos SNMP: 2 polls antes de alertar |

**Variables EWMA (env):**

| Variable | Default | Ópera piloto |
|----------|---------|--------------|
| `INFRA_PULSE_ENABLED` | `0` | `1` |
| `INFRA_PULSE_ALPHA` | `0.25` | `0.25` |
| `INFRA_PULSE_LATENCY_FACTOR` | `1.5` | `1.4` |
| `INFRA_PULSE_PERSIST_TICKS` | `5` | `6` (~3 min) |
| `INFRA_PULSE_ALERT_COOLDOWN_SEC` | `1800` | `1800` |

- [x] **Fase 1 — Pulse EWMA** — `shomer_infra_pulse.py`, `infra_pulse`, Telegram degradando

**Estado BG:** Pulse Correlate + EWMA ✅ sesión 65 (8 jul 2026)

## BG.4 Roadmap Pulse — fases posteriores (backlog producto)


---

# 📚 Sesiones 69-88 (5 ago - 12 sep 2026)

Archivadas el 13 sep 2026 durante la consolidación a versión final — el resumen
"Estado vivo" al inicio de `CLAUDE.md` y las Partes A-N ya incorporan lo que de
esto sigue vigente. Nada se borró: queda aquí para el detalle de cada
cambio/parche, en orden cronológico (las sesiones 82-88 estaban invertidas en
el original; se reordenaron aquí).

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
- **Aprendizaje acumulado (`agente_skills`) conectado a más lugares:** `/diagnostico` y
  `/criticidad` muestran el historial de soluciones confirmadas de un equipo; el resumen
  matutino agrega "patrones confirmados" (3+ arreglos remotos confirmados = candidato a
  revisión física), excluyendo explícitamente tareas automáticas rutinarias (TASK-*) para no
  confundirlas con equipos que siguen fallando. Versión 1.1.9.
- **Fix en vivo: el resumen matutino se mandó dos veces hoy** por reiniciar el bot justo en la
  ventana 07:00-07:02 — el día del último envío ahora se guarda en disco (`bot_state` en
  `knowledge.db`), sobrevive a reinicios. Mismo fix en el resumen de las 22:00.
- **Auditoría completa de mensajes del día (3:30am-ahora) — 3 hallazgos reales, los 3
  corregidos, versión 1.2.0:**
  1. **Sistema de "pendientes" (tickets) nuevo**, conectando el patrón crónico (opción 3) con
     un ciclo de vida real: se abre un pendiente una sola vez, se recuerda 3x/día (10am/3pm/8pm),
     y el técnico lo cierra o lo pausa (reusa `/silenciar`) — antes un crónico simplemente
     dejaba de avisar para siempre, sin ninguna acción posible. Tabla `chronic_tickets` +
     módulo `core/chronic_tickets.py` + comando `/pendientes`, en shomer-agent.
  2. **Fix: Hunter avisaba doble** cada bloqueo Wazuh (una vez directo, otra vez el bot ~1 min
     después) — ahora el bot recuerda qué ya avisó la vía directa y no repite.
  3. **Fix: hueco real — el aviso directo de "falló el reinicio" (network_monitor) no
     respetaba el patrón crónico**, aunque el bot sí lo hacía. Un AP con 17 ocurrencias desde
     junio (AP PASILLO HAB 701-702) igual interrumpía por este camino aparte. Corregido en
     `app/api/shomer_guardian_nodes.py` (`_es_patron_cronico()`, lee `knowledge.db` de solo
     lectura, mismo umbral que el bot).
- **Auditoría de los 18 `send_telegram_safe()` directos de network_monitor (Sesión 80,
  commit `0d83b4d`): 4 huecos más encontrados y cerrados, 14 revisados y están bien así.**
  - **Opción 1** (auto-reboot exitoso no interrumpe): "REINICIO EN PROGRESO" se mandaba en 2
    caminos de código distintos (poller por lotes y heartbeat individual) apenas se emitía el
    comando de reinicio, sin saber si de verdad funcionó — ahora solo queda en `log_event`,
    igual que ya hacía el bot; el bot avisa solo si sigue caído a los 3 min.
  - **Opción 3** (patrón crónico no interrumpe): "CALIDAD DEGRADADA" y el "falló el reinicio"
    del camino heartbeat (distinto del que ya se arregló, que era el del poller por lotes)
    tampoco revisaban crónico. `_es_patron_cronico()` ahora acepta IP además de nombre
    (resuelve el nombre desde `devices` si hace falta) — antes solo funcionaba si se tenía el
    nombre a mano.
  - **Revisados y correctos, sin tocar:** mantenimiento (global y por nodo, son cambios
    humanos, no ruido automático), salud del servidor (RAM/CPU/WAN, ya con su propio cooldown
    de 1h), reinicio manual (respuesta directa a una acción del técnico, debe avisar siempre),
    reportes de caída masiva (ya con su propio dedup por causa/ventana).

## Sesión 81 (4 sep 2026) — Cerebro unificado: correlación cruzada entre sistemas + aprendizaje activo

- **Pedido explícito de Juan Pablo**, tras revisar el sistema completo: *"el sistema está bien
  pero está suelto, no es un conjunto con cerebro propio"* — cada módulo (Guardian, Hunter,
  Infra, `pattern_analysis`, `chronic_tickets`) decidía y avisaba por su cuenta sin ver el
  cuadro completo. Antes de tocar nada: backup completo (tags `pre-cerebro-20260904` en ambos
  repos + copia en caliente de las 7 bases de datos vivas — `network_monitor.db`, `inventory.db`,
  `knowledge.db`, `memoria.db`, `changelog.db`, `conversations.db`, `telegram_enviados.db`).
- **Hallazgo clave (no había que inventar nada desde cero):** `watch_memoria_sync` (shomer-agent)
  ya unificaba Guardian+Infra+auto_task en una bitácora común (`memoria_incidentes`, en
  `memoria.db`) con la intención explícita, escrita en su propio docstring meses atrás, de que
  *"todo el razonamiento futuro (vigilante, investigación, chat) debe leer de memoria_central"*
  — pero nada lo hacía todavía. `pattern_analysis.py` sí lee de ahí, pero agrupa por ENTIDAD
  individual (un mismo AP repetido), nunca cruza sistemas ni equipos distintos.
- **`core/brain.py` (nuevo, shomer-agent) — el "cerebro":**
  - `memoria_central.py` gana una fuente más: Hunter (`blocked_ips`) ahora también sincroniza a
    `memoria_incidentes` — antes corría aparte y nunca entraba a la bitácora común.
  - Cada `BRAIN_INTERVAL_MIN` (20 min): agrupa eventos nuevos de TODOS los sistemas por
    **proximidad temporal**, sin importar el origen — así detecta, por ejemplo, varios equipos
    caídos juntos por una causa común en vez de tratarlos como incidentes separados.
  - Cruza cada equipo del grupo con su historial real en `agente_skills` (éxitos/fallos de
    remediaciones previas), patrón crónico (`pattern_analysis`) y tickets abiertos
    (`chronic_tickets`) — aprendizaje **activo** como insumo de la recomendación, no solo
    contexto pasivo pegado al chat (que es todo lo que hacía hasta hoy).
  - Le pide a un modelo de razonamiento una causa raíz + recomendación respaldada en esa
    evidencia — los conteos los calcula código, nunca el LLM (mismo principio anti-alucinación
    que ya usaba `pattern_analysis.py`). Fallback automático OpenAI → Groq si el primero falla.
  - No reemplaza ninguna alerta existente — capa adicional, solo manda Telegram si la urgencia
    es media o alta. Comando nuevo `/cerebro` (`/cerebro ahora` fuerza un análisis manual).
  - **Probado extremo a extremo antes de tocar producción:** copia aislada de datos reales (no
    la BD viva), escenario sintético de 2 APs caídos con 2 min de diferencia + 1 bloqueo Hunter
    35 min después — agrupó correctamente los 2 APs en un solo hallazgo, dejó el bloqueo Hunter
    aparte (sin relación temporal), y generó una recomendación citando el historial real (ej.:
    "reinicio remoto funcionó 100% de las veces anteriores"). Probado también el fallback a
    Groq apagando la key de OpenAI a propósito — funcionó igual de bien.
  - **Hallazgo honesto, no oculto:** el proyecto OpenAI de Shomer no tiene habilitado `gpt-4o`
    (403 `model_not_found`, confirmado en la prueba real) — solo `gpt-4o-mini`, el mismo que ya
    usa el chat interactivo. `BRAIN_MODEL` quedó en `gpt-4o-mini` por ahora; para el salto de
    calidad que pidió Juan Pablo ("pagar otra IA") falta solo habilitar `gpt-4o` en
    `platform.openai.com` (Project → Limits/Models) y cambiar una variable en `.env` — sin
    tocar código.
  - Desplegado en Ópera (commit `e868812`, reiniciado y verificado sin errores) + sincronizado
    a los 3 labs vía `fleet_sync.sh`.

## Sesión 82 (5-7 sep 2026) — KB CompTIA completa + auditoría de seguridad + topología LLDP real + Fases 5-8 del cerebro + Guardian: causa raíz del reinicio automático

Sesión larga, varios días. Resumen por bloques (ver `CHANGELOG.md` de shomer-agent v1.20.0 a
v1.29.0 para el detalle línea por línea de cada fix):

- **KB técnica (`conocimiento_general.py`, shomer-agent):** cobertura exhaustiva de las 6
  certificaciones CompTIA pedida por Juan Pablo (436 entradas: 173 reglas + 263 teoría, solo
  temario oficial + contenido escrito por Claude, nunca respuestas de examen real). Auditada dos
  veces a pedido explícito de Juan Pablo (desconfiaba de auditorías "básicas y rápidas"): sample
  audit (18/19 correctas) y luego auditoría completa vía 8 agentes en paralelo (397/436
  correctas, 39 fixes, v1.20.0) + unificación de metodología de troubleshooting a una sola
  versión de 7 pasos (v1.20.1). Primera suite de pruebas automatizadas de shomer-agent (0→31
  pruebas, v1.21.0).
- **Auditoría de seguridad completa** (asumiendo erróneamente que el sistema no estaba expuesto):
  encontrado y corregido un error real de UFW — reglas #7/#8 permitían TCP 80/8443 desde
  "Anywhere" (todo internet), pese a un comentario engañoso de "cualquier LAN". Confirmado por
  logs reales de nginx que Tailscale era el único acceso histórico; eliminadas las reglas,
  probado sin corte desde Ópera y desde un lab remoto por Tailscale.
- **Limpieza de datos muertos:** `backups/` (150MB legacy, ya migrado a `_archivo_obsoleto/` en
  sesión previa) y `logs/` (52MB, 0 archivos modificados desde marzo) eliminados por completo.
  `discover_macs.py` tenía un `"""` suelto desde su primer commit (string sin cerrar) — corregido.
  `_calc_uptime_24h`/`_calc_uptime_24h_batch` trataban cualquier evento de `infra_events` como
  transición binaria online/offline, corrompiendo el cálculo con eventos `degraded`/`pulse_*` —
  filtrado a `event IN ('online','offline')`.
- **Descubrimiento de topología real por LLDP/SNMP** (`shomer_topology.py`) construido desde cero
  tras encontrar que `SnmpSwitchProvider`/`UniFiControllerProvider` eran placeholders no
  funcionales — y `protector.py::sync_to_cloud()` (simulado con `time.sleep()`, sin caller real)
  eliminado por completo. Usa `lldpRemManAddrTable` (IP de gestión real del vecino) como fuente
  principal de resolución, no coincidencia de nombres (que resolvía 0/19 enlaces). Corre solo
  cada 5 min (`inframonitor_poller.py`), 19 enlaces reales descubiertos.
- **Cerebro (shomer-agent) — Fases 5 a 8, todas probadas contra datos reales antes de desplegar:**
  Fase 5 (topología LLDP confirmada como evidencia de switch compartido), Fase 6 (cambios de IP
  por MAC, incidentes Hunter abiertos, hallazgos de auditoría pendientes, errores de puerto —
  bug real corregido en el camino: `get_hunter_incidents` con ventana de 24h no encontraba nada
  porque los incidentes de Hunter quedan abiertos semanas), Fase 7 (estado real del WAN +
  fallas/reboots por nodo), Fase 8 (mantenimiento por-nodo, razón exacta de `classify_health`,
  resultado del último auto-reinicio — ver más abajo).
- **Cierre automático de ruido de Hunter confirmado** (+14 días, solo "Poor Reputation" externo,
  criterio explícitamente aprobado por Juan Pablo vía pregunta directa): bug arquitectónico real
  encontrado y corregido en el camino — la primera versión escribía SQL directo al `.db` de
  network_monitor desde el contenedor de shomer-agent, que lo monta `:ro` a propósito; fallaba en
  silencio (`log.debug` no visible en el nivel real del contenedor). Corregido con un endpoint
  HTTP nuevo (`POST /incidents/close_stale_noise`) en vez de escritura directa.
- **KB conectada al chat interactivo** (antes solo la usaba cerebro y el comando manual
  `/conocimiento` — el chat natural del técnico respondía sin verla). Bug de costo encontrado y
  corregido el mismo día: el fallback genérico a dominio "metodologia" inyectaba ~325 tokens
  hasta en un saludo casual sin ningún match técnico real — nuevo parámetro `strict=True` para
  el chat, cerebro sin cambios.
- **Guardian — causa raíz real de por qué fallan la mayoría de los auto-reinicios:** un AP normal
  (`device_type='access_point'`) solo puede llegar a `offline` (0% respuesta LAN) antes de que
  Guardian intente reiniciarlo por SSH — la clasificación `no-internet` (WAN caída, LAN viva) es
  exclusiva de routers. Sin ruta de red, ningún protocolo remoto puede llegarle — no es bug de
  credenciales. Verificado con evidencia real: AP HAB 103 en mantenimiento por-nodo desde hace
  ~2 meses (`node_maintenance:192.168.0.148`, `offline_streak` en 580k+ ciclos, cortando el flujo
  antes de tocar el contador de fallas — confirmado correcto) y varios AUTO-REBOOT reales
  fallando con "Connection timed out"/"No route to host" contra AP CONTABILIDAD, AP HAB 215-216,
  AP REST MIRADOR, AP OFC-MANTENIMIENTO. Ver §D.3 para la propuesta de recuperación por PoE/SNMP,
  documentada como pendiente (requiere validación en campo, equipos ya en tránsito a Bogotá).
  Dos mejoras construidas y probadas (commit `3ba3ac9`): reinicio preventivo cuando `degraded` se
  sostiene sobre `guardian.degraded_preventive_reboot_ticks` (60 ticks ≈ 10 min por defecto,
  mientras aún hay conectividad parcial) y `is_network_unreachable_error()` para un aviso de
  Telegram distinto ("requiere atención física") cuando el fallo es por falta total de ruta.
- **Reinicio manual probado en vivo contra hardware real** (AP CONTABILIDAD, de madrugada sin
  nadie en oficina): funcionó de principio a fin (~2 min offline→online). Bug real encontrado en
  el camino — el timeout del cliente (`shomer_api.py::reboot_guardian_node`, shomer-agent) era de
  15s pero el servidor prueba hasta 3 métodos SSH en cadena (~30s en el peor caso); subido a 40s.
  Segundo bug encontrado después: esa llamada (y `_try_remediate_ip`) bloqueaba el único hilo de
  eventos del bot de Telegram entero mientras esperaba — ahora envueltas en `asyncio.to_thread`.
- **Corrección propia importante:** subí `BRAIN_MODEL` a `gpt-4o` sin releer primero esta misma
  nota de la Sesión 81 (arriba) que ya documentaba que este proyecto de OpenAI no tiene acceso a
  ese modelo (403). Cerebro estuvo unas horas fallando en silencio a OpenAI y cayendo a Groq sin
  ninguna mejora real. Revertido a `gpt-4o-mini` en Ópera y en los 3 labs (que tenían el mismo
  problema desde antes, sin relación con este cambio).
- **Auditoría dedicada de Guardian (código + lógica) — 10 hallazgos reales, 9 corregidos, 1
  pendiente a propósito** (commit `bf6a7db`): **🔴 sin corregir, a pedido explícito** — la clave
  `SSH_FALLBACK_PASSWORD` en texto plano committeada a git (`start_api_with_fallback.sh`,
  commit `d888b07`) requiere rotación + limpieza de historial git, decisión que le corresponde
  a Juan Pablo, no algo para resolver solo. Los 9 restantes, corregidos y verificados en vivo:
  - Dos endpoints sin autenticación (`/node_maintenance/{ip}`, `/api/server-metrics`) —
    verificado en vivo antes (200 sin login) y después (401) del fix.
  - **Reloj sesgado +5 horas**: `datetime.utcnow().timestamp()` reinterpreta un datetime naive
    como hora LOCAL en vez de UTC — corrompía cada timestamp de reinicio que Guardian escribe
    (el técnico veía "último reinicio: hace -5h", la ventana de "reinició hace poco" de cerebro
    duraba en realidad 29h, el guardián de frescura de 10 min de `monitor.py` quedaba
    completamente inútil). Corregido a `datetime.now(timezone.utc).timestamp()` en los 5 sitios
    reales. Verificado contra los 16 `last_reboot:*` reales en Redis antes de desplegar —
    ninguno estaba dentro de la ventana de cooldown de 5 min, cero riesgo de migración.
  - Fallback SNMP en `_run_ssh_reboot()` nunca se alcanzaba en producción (el paso SSH de
    respaldo retornaba siempre, éxito o fallo) — ahora solo retorna en éxito y cae al SNMP.
  - El heartbeat `guardian:poller:last_ok` (usado por `watch_poller_heartbeat` en shomer-agent
    para detectar "Guardian congelado") se refrescaba solo al final del bucle de reinicios —
    con 2+ reinicios en un mismo ciclo podía vencer su TTL de 40s y disparar una alerta crítica
    falsa. Justo el riesgo que el reinicio preventivo de hoy (arriba) aumentaba. Refrescado
    ahora antes del bucle y entre cada intento.
  - `_clean_redis_for_ip()` duplicada 3 veces con listas de claves divergentes — la copia usada
    al desactivar un equipo dejaba huérfana para siempre la clave `node:{ip}` (sin TTL).
    Unificada a una sola fuente en `shomer_guardian_discovery.py`.
  - `GET /maintenance` devolvía `null` en vez de `false` cuando no había fila — verificado
    corregido en vivo.
  - `get_nodes()` usaba `KEYS` (bloquea todo Redis) en vez de `SCAN`, ya disponible en el mismo
    archivo (`_redis_scan_keys()`).
  - `checks_ms` sumaba la duración individual de cada ping concurrente en vez de medir tiempo
    real de reloj — un log real mostraba "checks=213975ms" dentro de un ciclo de 18s, inútil
    para diagnosticar ciclos lentos.
  - Código muerto eliminado: `_probe_guardian_device()` (cero referencias) y una rama
    inalcanzable en `_gw_ping_triplet()`. `send_telegram_safe()` y las 2 funciones de lectura
    de credenciales SSH/SNMP ahora loguean en vez de tragarse errores en silencio (antes una
    alerta de Telegram podía desaparecer sin ningún rastro, justo cuando más importa).
  - **13 archivos `.bak.UTAH.202605222357`** (~500KB) en `app/templates/`, todos del 22 mayo,
    cero referencias — confirmados huérfanos, quedan como hallazgo para limpieza (no borrados
    en este pase, ver decisión de Juan Pablo).
  - Bonus cross-repo: `bot.py` (shomer-agent) le decía al técnico "Guardian reinicia al llegar
    a 5" con el número fijo en el texto, pero el umbral real configurado
    (`guardian.fail_threshold`) es 3 — ahora lee el valor real en vez de un número fijo.
  - Todo verificado con `pytest` (117/117 network_monitor, 31/31 shomer-agent) + pruebas en vivo
    contra el servicio real antes de desplegar en Ópera y los 3 labs.
- **Auditoría dedicada de Tracker (código + botones + escaneo básico/profundo) — 10
  hallazgos, 9 corregidos y verificados en vivo** (commit `a659384`):
  - **La detección de sistema operativo del escaneo profundo nunca había funcionado** (probado
    en vivo antes y después): combinar `-O` con `-sV`/`-A` en una sola pasada de nmap hace que
    la detección de SO nunca complete dentro del `--host-timeout` — confirmado 3 veces seguidas
    contra un servidor Windows real conocido (IIS, RDP, MSSQL). Separado en dos pasadas de nmap
    (una solo para SO, otra para versión de servicio) — ahora detecta correctamente ("Microsoft
    Windows Server 2012" 93%, "Linux 2.6.32" en el MikroTik) donde antes nunca devolvía nada
    para ningún equipo real. También faltaba `--osscan-guess` (sin él, nmap solo llena el XML
    con coincidencia casi perfecta).
  - Dos endpoints de exportación en el puerto 8001 sin autenticación en ningún lado (a
    diferencia del caso de Guardian, acá no había una segunda validación aguas abajo) —
    corregido, verificado 401 en vivo.
  - Condición de carrera real: el propio sondeo de estado de la UI (cada 5s) podía borrar el
    candado de un escaneo que apenas arrancaba, permitiendo dos `scanner.py` concurrentes sobre
    la misma red — confirmado simulando la carrera exacta, corregido con margen de 10s.
  - La subred configurada del Tracker se ignoraba en el escaneo básico (autodetectaba la red
    real sin importar lo configurado) — corregido y verificado con un escaneo real.
  - Contraseña de override en texto plano expuesta a cualquier usuario autenticado —
    enmascarada igual que el otro campo de credenciales del módulo, verificado en vivo.
  - `pkill`/timer de limpieza con `192.168.` fijo (no funcionaría en ningún cliente con otra
    red), truncamiento silencioso a una sola subred en ambos proxies de escaneo, `DROP TABLE`
    incondicional en cada lectura sondeada cada 5s, PATCH creando activos fantasma, botón de
    "rescanear" apuntando a un proxy que nunca resolvía IP desde MAC — todos corregidos.
  - `inventory_sync.py` eliminado: script huérfano que además creaba una tabla duplicada con
    esquema distinto en la base de datos equivocada.
  - **Pendiente a propósito**: la contraseña SSH en texto plano en git (misma de Guardian, ya
    documentada) — ninguna decisión nueva aquí, sigue esperando a Juan Pablo.
  - 117/117 pruebas + verificación en vivo de cada fix antes de desplegar en Ópera y los 3 labs.
- **Auditoría dedicada de Inframonitor (poller, Pulse EWMA, oleadas de status_events) — 3
  hallazgos reales, corregidos y verificados en vivo** (commits `97a5fab` + `05d60ec`):
  - `_persist_poll_results` nunca devolvía `pulse_events` en su dict de retorno;
    `_poll_fast_once` lo leía de una variable que no existía en su propio scope —
    `NameError` silencioso en **cada ciclo fast** (30s), atrapado por el `except Exception`
    genérico alrededor de `write_poll_context()`. Efecto: `infra:poll:context` nunca se
    escribía en Redis, nunca. Verificado en vivo antes (`redis-cli EXISTS
    infra:poll:context` → `0`, pese al poller corriendo y escribiendo `infra_status`
    normalmente) y después del fix (existe, con `pulse_events` poblado). Esto también
    dejaba muerto el handler `exit_degrading` del bot (nunca le llegaba el evento).
  - Pulse EWMA: un equipo "degradando" que caía del todo a offline se etiquetaba
    `transition=exit_degrading` / `pulse_state=recovered` — quedaba en `infra_events`
    como `pulse_recovered` justo cuando en realidad empeoró (caída real, no
    recuperación). Corregido: una caída total resetea la máquina de estados Pulse sin
    emitir transición. Con el fix de arriba, la primera vez que `exit_degrading` llega
    de verdad a `pulse_events` es un recovery genuino.
  - `compute_outages()` agrupaba oleadas comparando cada evento contra el TS del
    **primer** evento del cluster (`cluster_start` fijo), no contra el último agregado.
    Con `CLUSTER_GAP_SEC=3` y decenas de equipos escribiendo su transición en el mismo
    ciclo (cada fila con su propio `datetime('now')`), una oleada real con pasos de 2s
    pero >3s de punta a punta quedaba partida en varios "incidentes" en vez de uno solo
    — justo el tipo de fragmentación que puede sesgar el análisis pendiente de causa
    raíz de caídas sincronizadas (Sesión 70-72, sigue sin resolver la causa de fondo;
    esto no la resuelve, evita que el propio reporte la oculte partiéndola). Corregido
    a ventana rodante (compara contra el último evento del cluster).
  - Pulse EWMA sigue deshabilitado hoy en Ópera (sin `infra.pulse.enabled`, default
    `INFRA_PULSE_ENABLED=0`) — los 2 primeros bugs eran latentes, no afectaban alertas
    reales todavía, pero se habrían disparado en cuanto se activara. Topología LLDP/SNMP
    (`shomer_topology.py`) no se reauditó a fondo — se reconstruyó por completo hace 2
    días en esta misma sesión (ver más abajo) con verificación extensa contra hardware
    real, no se encontraron hallazgos nuevos. `shomer_audit_network.py` (nmap sobre
    activos Tracker) es funcionalmente de Tracker, no de Inframonitor — no revisado en
    este pase. 3 tests nuevos, 121/121 pruebas. Reinicio de
    `shomer-inframonitor-poller` autorizado y hecho en vivo el mismo día.
- **Auditoría Inframonitor — SEGUNDO PASE, capa panel/botones/NOC (commits `15cb229` +
  `dd87181`).** El primer pase (arriba) se quedó solo en el poller; Juan Pablo lo marcó como
  flojo con razón — no se habían revisado ni los botones de la aplicación ni el NOC. 8
  hallazgos más, todos verificados contra datos reales de Ópera:
  - **El contador "caídas 24h" medía el estado ACTUAL, no el historial** — en el panel y en la
    pantalla NOC. Leía `infra_status` (una fila por IP, `checked_at` reescrito cada 30s, así
    que la condición de 24h se cumplía siempre). Medido al detectarlo: mostraba **1** cuando en
    24h hubo **11 caídas reales sobre 10 equipos**, y la misma pantalla ya listaba 10 equipos
    con badge de caídas por fila. Ahora sale de `infra_events`: header y filas cuadran (10).
  - **La columna "Uptime 24h" se borraba sola a los 30s.** `pollStatus()` repintaba con
    `st.uptime_24h`/`st.outages_today`, campos que `/infra/status` no devuelve (verificado en
    vivo contra los 51 equipos) → `uptimeBadge(undefined)` = "—" para toda la tabla hasta
    recargar la página. Guard + refresco completo cada 5 min.
  - **Nombre/ubicación sin escapar** en la tabla y dentro de 3 `onclick` (Eliminar, Cola,
    Stream): un equipo llamado `POS D'Angelo` rompía esos botones de su fila (JS inválido), y
    un nombre con HTML se inyectaba tal cual. Hoy no hay nombres así en Ópera — era latente.
    Helpers `esc()`/`escAttr()` siguiendo el patrón ya usado en `noc_cliente.html`.
  - **El botón "Cola" no aparecía nunca en producción**: los 6 printer/pos tienen
    `pc_server_ip` vacío y ese campo solo se podía fijar al CREAR el equipo. Ahora editable
    (mismo bug de fondo que ya se había corregido para `device_type` el 3 sep), con
    revalidación de `monitor_profile` cuando cambian `device_type`/`tcp_port`/`snmp_community`.
  - **`checked_at` tenía dos formatos en la misma columna**: los 30 APs en ISO
    (`.isoformat()`, vía `_sync_ap_status_from_guardian`) y los 21 equipos Infra en formato
    SQL. SQLite los compara como texto y la `T` (0x54) ordena por encima del espacio (0x20),
    así que dentro del mismo día un AP siempre parecía más reciente que cualquier umbral.
    Normalizado; verificado 51/51 en un solo formato tras desplegar.
  - **`stream_url` daba una URL que no abre**: ruta fija `rtsp://{ip}:554/stream1`
    (genérica/TP-Link) contra NVR Hikvision reales, que usan `/Streaming/Channels/101` y piden
    credenciales — además de violar la norma B.1 (cero hardcoding de topología cliente). Nueva
    columna `rtsp_path` por equipo, editable desde el panel con las rutas de Hikvision/Dahua/
    genérica como guía; sin ruta configurada responde 400 explicando qué falta en vez de
    entregar una URL que falla en silencio. Probado end-to-end contra el NVR `.111` real y
    revertido al estado original.
  - **`snmp_reboot` eliminada** (decisión de Juan Pablo): inalcanzable — sin botón en la UI,
    `snmp_community_write` vacío en los 51 equipos y no configurable, OID específico de
    TP-Link EAP cuando los APs TP-Link los reinicia Guardian con `_run_snmp_reboot`. Un solo
    camino de reinicio, no dos divergentes.
  - `ago()` estaba definida y sin usar en la plantilla — eliminada.
  - 17 tests nuevos entre los dos pases (`test_infra_pulse.py`, `test_infra_ui_contract.py`),
    138/138. Desplegado en Ópera con reinicio autorizado de `shomer-guardian` y del poller.
  - **Sin revisar todavía en Inframonitor:** `shomer_audit_network.py` (nmap sobre activos, es
    funcionalmente de Tracker) y la plantilla `noc.html` en sí (se revisó el backend del NOC,
    `_infra_devices`, no el JS de la pantalla).
- **Auditoría dedicada de Protector (backend + botones + B2 + drill, con prueba en vivo) — 3
  hallazgos, corregidos y verificados** (commit tras `2ef6cee`):
  - **El tamaño de cada copia nunca se registró.** `_parse_restic_stats` buscaba
    `"Added to the repository:"` (redacción de restic 0.14+) pero el binario de Ópera es
    **0.12.1**, que imprime `"Added to the repo:"` — capturado ejecutando el binario real. La
    regex no matcheaba nunca: `last_size_mb` quedaba NULL en las 9 copias históricas y ni el
    panel ni el aviso de Telegram mostraban el tamaño, que es justo la señal que delata un
    backup encogido porque el origen dejó de escribir. Además `size_mb` pasa a ser el **total
    procesado** en vez del delta añadido: con deduplicación el delta diario es ~0 aunque la
    copia esté sana (medido: 0.001 MB de delta contra 1.26 GB respaldados).
  - **Sin `b2_path` la copia iba a la RAÍZ del bucket**, compartida entre todos los clientes en
    un repo Restic indistinguible — exactamente lo que prohíbe la norma D.1. Ópera se salvaba
    solo porque `base.client_name` está puesto y el slug sale de ahí; una instalación nueva sin
    nombre de cliente (los 3 labs camino a serlo) habría mezclado sus backups con los de otro
    hotel, legibles entre sí con la misma clave de repo. Los 4 sitios que armaban la URL pasan
    ahora por `_b2_repo_url()`, que falla con mensaje accionable; el prune se cancela sin tocar
    el bucket compartido.
  - UI: nombre, IP, ruta, patrón y `last_status` se inyectaban sin escapar. `last_status`
    guarda el texto crudo de la excepción (salida de restic o `mount.cifs`).
  - **Lo que se verificó sano, con datos reales:** el backup del PMS Zeus funciona de verdad
    (9 snapshots, las 9 bases del PMS, el hotel genera las copias 03:00 y Shomer las toma
    05:00); el restore drill corre mensual **desde B2** (no solo local) restaurando y
    comparando el árbol contra el repo local — 1 sep, 1 ago, 1 jul, todos OK; el contrato
    UI↔backend está sano (`has_password` sale del endpoint individual, que es el que usa
    `editEquipo`).
  - **Falso positivo propio, anotado a propósito:** un primer análisis estático marcó "8
    endpoints sin autenticación" (incluido restaurar y guardar credenciales B2). Era un
    artefacto de la regex, que se cortaba en los paréntesis anidados de `Body(default={})`.
    Probado en vivo: los 24 endpoints responden 401 sin sesión, y los proxies del 8000 validan
    admin dentro de `_proxy_backups`. **No había vulnerabilidad.** Queda escrito porque el
    reflejo correcto fue probarlo antes de reportarlo.
  - 9 tests nuevos (`test_protector_audit.py`), 147/147.
- **Auditoría dedicada de Hunter (código + botones + bloqueo/desbloqueo real) — 10 hallazgos +
  1 bonus encontrado probando en vivo, los 11 corregidos y verificados** (commits `799c44e` +
  `8455de4`):
  - **Bonus, encontrado probando el bloqueo real antes de tocar código**: `/firewall/routeros/
    verify` siempre reportaba "falta la regla DROP" (104 IPs "bloqueadas" pero supuestamente sin
    enforcement) — investigado a fondo contra el router real por SSH: RouterOS no evalúa
    correctamente `where ... src-address-list=X` en modo `count-only` (el `print` normal sí
    muestra las reglas con ese mismo filtro). La regla SÍ existía y SÍ bloqueaba — el bug era
    de reporte, no de protección real. Cambiado a filtrar por `comment="Shomer-Hunter"`.
    Efecto colateral: mi propio intento de "arreglarlo" antes de encontrar la causa real creó
    una regla duplicada (inofensiva, redundante) — removida con autorización explícita.
  - Un operador (no admin) podía reescribir la contraseña SSH real del firewall o el token de
    integración Wazuh vía `POST /config/system` (el `GET` ya exigía admin, el `POST` no) —
    corregido y verificado que el admin real sigue pudiendo guardar config.
  - Desbloquear marcaba la IP como desbloqueada en la BD aunque el firewall rechazara el
    comando — quedaba bloqueada de verdad en la red pero invisible para el sistema.
  - `execute_hunter_block()` (compartida por panel, Wazuh y el poller automático) no validaba
    el formato de IP — solo la ruta HTTP manual lo hacía. Riesgo de ejecución de comandos si
    Suricata alguna vez registrara un `src_ip` malformado.
  - `INSERT OR REPLACE` en `blocked_ips` (columna `ip` UNIQUE) borraba el historial completo de
    un reincidente al volver a bloquearlo — nueva tabla `blocked_ips_history` archiva la fila
    cerrada antes de sobrescribir; probado en copia aislada antes de tocar producción.
  - El panel reintentaba auto-bloquear la misma alerta cada 30s sin deduplicar — con la política
    de "3 en 10 min" para severidad alta, 90 segundos de una pestaña abierta bastaban para
    cumplir el umbral con una sola alerta real, no un ataque sostenido.
  - El editor de reglas de Suricata no existía en el HTML pese a que el JS ya lo esperaba —
    abrir "Configuración Hunter" tiraba un error de inmediato. Construida la sección completa.
  - Reglas fantasma (comentarios de encabezado mostrados como reglas con botones rotos),
    recarga de Suricata que existía pero nunca se llamaba tras editar una regla, 6 llamadas de
    log con argumentos invertidos, bloqueo por iptables sin chequeo de duplicados, fallo
    silencioso en sync, doble conteo por un glob de Redis mal armado — todos corregidos.
  - 117/117 pruebas + verificación en vivo (ciclo real de bloqueo/desbloqueo, historial,
    reglas) antes de desplegar en Ópera y los 3 labs.

---
## Sesión 83 (8-9 sep 2026) — Hunter cortaba el internet del hotel + auditoría del bot y del cerebro

### ⚠️ Incidente: Hunter bloqueó los DNS de Google y el hotel se quedó sin internet

**Cómo llegó:** una alerta de Telegram decía "interfaz de red caída —
`enx9c69d33bc55f` DOWN". Eso era el síntoma final de una cadena, no la causa.

**La cadena real, reconstruida con el log del router:**

1. `hunter.auto_block_min_severity` estaba en **3**. En Suricata **menor número =
   más severo**, así que 3 incluye la franja donde caen `ET INFO` y las anomalías
   de protocolo (`SURICATA STREAM/HTTP/TCP/IKEv2`), que no describen ataques.
2. Hunter acumuló **126 IPs bloqueadas**, 20 de ellas legítimas: **`8.8.8.8` y
   `8.8.4.4`** (DNS de Google — causa directa de "no hay internet": sin
   resolución DNS da igual que el enlace funcione), más Google, Akamai,
   Canonical y varias IPs del ISP colombiano. Una de las firmas culpables:
   `ET INFO ... STUN`, que es cómo funciona cualquier videollamada.
3. El proveedor (`admin` desde `172.16.1.99` vía Winbox) entró al MikroTik,
   **deshabilitó la regla de firewall** de Shomer (`filter set *10A
   disabled=yes`, 06:29:21) y **apagó el puerto `ether4`** — el `mirror-target`
   del espejo SPAN — para recuperar el servicio. Eso dejó a Hunter ciego y
   generó la alerta con la que empezó todo.

**Diagnóstico del puerto (importante para la próxima):** la config del espejo
NUNCA se perdió (`switch2 mirror-source=ether3 mirror-target=ether4`). El puerto
estaba `X` = DISABLED con 0 bytes, y `ether3` (la fuente) seguía `R` = RUNNING.
Como en RouterOS ese estado es persistente, sobrevivió al reinicio: fue una
acción deliberada, no un efecto del reboot. Reactivado con
`/interface ethernet enable ether4`; Suricata volvió a procesar tráfico real en
segundos (verificado en `eve.json`, no solo que la interfaz estuviera UP).

**Correcciones (commits `6c151f8` + `cabe937`):**

- **Umbral a 2** (solo critical y high). Spamhaus, Dshield, CINS y los escaneos
  se siguen bloqueando igual.
- **Filtro por firma** (`NUNCA_AUTOBLOQUEAR`): `ET INFO`, `ET POLICY` y las
  anomalías `SURICATA STREAM/HTTP/TCP/IPV4/UDP/IKEV2/TLS` no bloquean nunca,
  venga la severidad que venga — la misma firma puede llegar etiquetada distinto
  según la fuente (Suricata directo vs Wazuh), así que el umbral solo no basta.
  Va en `execute_hunter_block()`, el camino compartido por panel, Wazuh y el
  poller, y en el pre-filtro del poller.
- **`INFRA_CRITICA` nunca se autobloquea, ni con severidad 1**: DNS públicos,
  Google, Microsoft, Apple, Canonical, Akamai, Fastly, Cloudflare. Si una regla
  marca al DNS de Google como amenaza, el error es de la regla. Esto convierte
  el arreglo de "depende de la configuración" a "imposible por construcción".
- **20 IPs liberadas** (126 → 106) con la lógica del sistema: firewall primero,
  BD solo si el router confirma. Verificado en el router real.
- El **bloqueo manual no se tocó**: el técnico sigue pudiendo bloquear lo que
  decida. Los 3 labs nunca tuvieron el problema (usan el default 2 del código).

**`tools/simular_politica_hunter.py`** — responde "¿qué cortaría si lo activo?"
ANTES de activar: pasa la política sobre el tráfico REAL registrado (eve.json +
rotados) con la misma cadena de decisión del autobloqueo, sin tocar el firewall,
y termina en semáforo que falla si alguna IP a bloquear es un servicio esencial.
Con 24 h reales: **22.440 alertas → 0 IPs bloqueadas**, 🟢.

**🔴 PENDIENTE:** la regla de firewall sigue **apagada** por decisión de Juan
Pablo (dry-run de 24-48 h antes de reactivar). Mientras tanto Hunter detecta
pero no corta. Ver `PENDIENTES_LAB.md` para el criterio de validación y el
comando exacto. **Avisarle a Ricardo antes de reactivar.**

### Auditoría del bot y del cerebro (ver `CHANGELOG.md` de shomer-agent v1.31.0)

Misma metodología que los demás módulos; en el bot los "botones" son los
comandos y los callbacks inline. 3 bugs reales, todos de los que no dan error:

- **El botón "🔓 Desbloquear" de las alertas de Hunter nunca funcionó** —
  mandaba `block_unblock_<ip>` y el handler espera `unblock_confirm:<ip>`.
  Por eso, durante el incidente de arriba, el técnico no pudo liberar los DNS
  desde Telegram y hubo que entrar al router.
- **Un cluster con error atascaba el cerebro y repetía el gasto del modelo**:
  el cursor `last_incident_id` avanzaba después del bucle, así que una
  excepción lo dejaba sin mover y el ciclo siguiente repagaba las mismas
  llamadas, en bucle. Ahora `try/except` por cluster y cursor en `finally`.
- **`/monitores` mostraba 37 de los 39 reales** — faltaban `watch_brain` y
  `watch_poller_heartbeat`, y este último es el que detecta "Guardian
  congelado".

Cuatro herramientas nuevas en `shomer-agent/tools/` para los contratos que se
desincronizan solos sin dar error: `auditar_callbacks.py`, `auditar_comandos.py`,
`auditar_monitores.py` y `auditar_endpoints.py` (esta última lee `app.routes` de
la app FastAPI real — un parser por texto daba 8 falsos positivos porque los
routers se componen anidados con prefijo).

---

## Sesión 84 (11 sep 2026) — Menos ruido sin perder información + el internet de los huéspedes

**Contexto que define el diseño** (Juan Pablo): el sistema lo administra un
técnico de soporte que atiende **2-3 hoteles** y va a cada uno **1-2 días por
semana**; el resto lo gestiona en remoto. Necesita información válida,
verificada, en lenguaje natural, sin basura y sin duplicados. Shomer son sus
ojos, oídos, cerebro y voz: el técnico no sabe qué está pasando si Shomer no se
lo dice. Y no puede confundir la caída de un ping con la caída del hotel.

### El diagnóstico, medido

1.009 mensajes en 30 días (**32,5/día**, picos de 92), **58% puramente
informativos**. Dos fuentes concentraban el 66%. Y el mismo mensaje, palabra por
palabra: "AP OFC-MANTENIMIENTO" 42 veces, "Nodo recuperado AP OFC-COCINA" 32,
"todos los sistemas OK" 54, "angy.monroy conectado" 45.

**Dos formas de duplicación**, no una:
- **Vertical**: un bloqueo de Hunter generaba 3 mensajes en 3 minutos (backend
  al bloquear, `watch_hunter` a los 64 s, cerebro a los 3 min) — más un ticket
  que se recordaba 3 veces al día. Un evento falso produjo ~20 mensajes.
- **Temporal**: lo crónico se trataba como noticia. El AP de mantenimiento
  avisaba 42 veces lo mismo; el técnico lo supo la segunda.

**La causa de fondo:** Shomer no tiene el concepto de *incidente*. Tiene eventos
sueltos y cada capa que ve uno avisa por su cuenta; nadie es dueño del hecho ni
lo cierra. Y no distingue novedad / estado que sigue igual / crónico conocido.

### Lo corregido (ver `CHANGELOG.md` de shomer-agent v1.34.0)

- **Pendientes que se cierran solos** cuando su motivo ya no existe.
- **VPN**: 217 mensajes/mes → uno diario, pero **un usuario nunca visto avisa al
  instante**. Sin sembrar datos: ventana de aprendizaje de 14 días por sitio.
- **Latido "todo OK"**: de 3 al día a 1 (no se elimina: su ausencia es la alarma).
- **Duplicación de Hunter eliminada** y **el cerebro solo habla si correlaciona**
  (de 50 conclusiones reales, 11 se enviarían y 39 se guardarían sin interrumpir).
- **El parte diario se vigila a sí mismo.**

### Un patrón que apareció tres veces y conviene recordar

El digest de VPN existía y no agrupaba (14 de 217); el botón "Desbloquear"
existía y no enrutaba a ningún handler; la supresión de duplicados existía desde
la Sesión 80 y su regex **nunca matcheó** el formato real del mensaje. Tres
mecanismos correctos, bien pensados, que **nunca llegaron a ejecutarse** — y
ninguno daba error: el síntoma era "se manda de más" o "el botón no hace nada",
cosas que no aparecen en ningún log. Eso explica por qué el ruido persistía pese
a varios intentos previos de reducirlo. **Cada arreglo queda con un test que
falla si vuelve la versión frágil.**

### `watch_internet_hotel` — el internet de los huéspedes

Que el servidor Shomer navegue **no** prueba que el hotel navegue: Shomer vive
en la LAN de gestión, los huéspedes salen por otras VLAN y por el hotspot, y la
regla de bloqueo actúa sobre `chain=forward`, o sea sobre el tráfico de ellos.
El 8 sep el hotel se quedó sin internet mientras el servidor navegaba perfecto.

Nuevo endpoint `GET /api/wan-hotel` (`shomer_wan_hotel.py`) que mide desde el
gateway: WAN arriba y con IP, pérdida real, y **uso** (sesiones NAT y clientes
de hotspot) comparado contra la medición anterior — un desplome del uso es la
señal más honesta de que la gente se quedó sin servicio aunque todo "responda".
Lo consume el monitor `watch_internet_hotel` del agente. Genérico:
`base.wan_interface` y `base.wan_test_ips`.

### Principios que quedaron fijos

1. **El código decide, el cerebro redacta.** Nunca un modelo decidiendo qué es
   crítico: a un hotel hay que darle un servicio predecible y auditable.
2. **Un hecho, un hilo.** Ninguna capa habla por su cuenta de algo que ya tiene dueño.
3. **Nada se repite sin cambio de estado.**
4. **Lo crónico no es alerta, es trabajo de campo** (va al informe, no a Telegram).
5. **Shomer aprende de los hechos, no de aportes voluntarios** — medido: de 9
   tickets, 7 seguían abiertos, y en 3 meses hubo 6 acciones de técnico. Esperar
   que el técnico documente no funciona.
6. **Nada ad-hoc.** Si algo solo funciona porque alguien sembró datos de un sitio,
   está mal diseñado: en el cliente siguiente no existiría.

### Pendiente de esta línea de trabajo

- **Informe al coordinador por correo** (separa "actuar" de "supervisar"): el
  código de envío ya existe en `incident_escalation.py`, falta configurar SMTP.
- **Fase 2**: perfil por equipo para que las recomendaciones sean de sitio y no
  de manual — *"este AP falló 42 veces, el reinicio no lo resuelve, revisá la
  fuente"* en vez de *"revise el cableado"*. La estructura de aprendizaje ya
  existe (`veces_confirmado`/`veces_refutado` en `conocimiento_general`) y está
  **vacía**: hay que conectarla, no construirla.
- **Medir el efecto real** de Fase 0 y 1 contra la línea base de este mes.

---

## Sesión 85 (11 sep 2026) — Consolidación de flota y el secreto que la consola no veía

### Lo que estaba corriendo fuera de git

Nueve archivos del core llevaban días vivos en Ópera **sin commitear**: los
arreglos de las auditorías de Tracker y Guardian nunca se confirmaron, así que
los tres labs no los tenían y una reinstalación los habría perdido. Lo que
recuperan: cancelar un escaneo durante su ventana de arranque decía "cancelado"
sin matar nada (el PID de `scanner.py` todavía no es visible para `pgrep`, así
que se borraba el candado del escaneo que seguía arrancando); un status file
ilegible dejaba el escaneo marcado como corriendo para siempre; y
`tracker.subnets`, que termina en el argv de un `sudo nmap`, no se validaba como
IP/CIDR. Va también el arreglo de sintaxis de `discover_macs.py`.

Comparar por hash el árbol de Ópera contra un lab, en vez de fiarse de los
commits, fue lo que los sacó a la luz: los labs reconcilian con commits propios,
así que `git diff` entre hashes no dice nada.

### La alarma falsa que sí escondía una falla real

Cualquier script lanzado a mano imprimía **"JWT_SECRET usa valor por defecto —
definir JWT_SECRET en producción"**. Parecía que los cuatro servidores firmaban
sesiones con un literal publicado en el repositorio. No era así: cada sitio
tiene su propio secreto y systemd se lo pasa a los servicios por
`EnvironmentFile`. El aviso salía de **mi propio proceso de consola**, que no
hereda ese entorno — el mismo error de método de otras veces: medir fuera del
entorno real y creerle al resultado.

Pero debajo había una falla de verdad. La clave de cifrado de las credenciales
de Protector se **deriva** de ese valor, así que toda herramienta de
mantenimiento trabajaba con la clave equivocada: `_decrypt_device_password`
fallaba con `ValueError` sobre la contraseña de **SRV Zeus PMS**, el servidor
del PMS, cuyo respaldo de las 05:00 sí corre bien desde el servicio. Un aviso
que el técnico aprende a ignorar tapaba una rotura silenciosa.

Y el instalador la sembraba en **toda instalación nueva**: creaba
`shomer-runtime.env` como `640 root:$SERVICE_USER` pero `/etc/shomer` como
`root:root 750`, de modo que el usuario del servicio no podía entrar al
directorio a leer el archivo que era suyo. Permiso muerto.

`auth_api` resuelve ahora el secreto en orden — entorno, archivo de runtime, y
solo entonces el default — con la ruta configurable vía `SHOMER_RUNTIME_ENV`.
El entorno mantiene la prioridad, así que **el servicio ve exactamente lo mismo
que antes**: no se rota ningún secreto ni hace falta reiniciar producción.
`backups.py` toma el valor ya resuelto en vez de leer el entorno por su cuenta,
para no dejar dos fuentes de verdad. Verificado en vivo: la credencial que
fallaba ahora descifra desde consola.

### Estado de la flota

Ópera y los tres labs con 163/163 pruebas del core y 99/99 del agente, agente
v1.35.0 (`256207e`) en los cuatro, y `/etc/shomer` en `750 root:<usuario del
servicio>` (shomer205 estaba en 755, más abierto de lo debido).

**Internet del hotel, verificado en esta sesión**: WAN arriba, 0% de pérdida a
8.8.8.8 y 1.1.1.1 — las mismas IPs que Hunter había bloqueado —, 1.099 sesiones
NAT y 11 clientes en hotspot.

### Pendiente

El reporte de caídas de POS sigue **sin enviar**: falta la cuenta de correo de
Shomer. Juan Pablo pidió expresamente **no aplicar todavía** la configuración de
puertos que el reporte recomienda.

## Sesión 86 (12 sep 2026) — Que la flota no pueda desincronizarse en silencio + Shomer deja de hablar de sí mismo

### El procedimiento era el error, no el descuido

El agente ya tenía `fleet_sync.sh`, pero el core se sincronizaba **a mano**,
tecleando la lista de archivos en cada rsync. Lo que no se teclea, no viaja: así
se quedaron nueve archivos sin llegar a los labs durante días, vivos en
producción y fuera de git. Un procedimiento que depende de que alguien recuerde
la lista completa va a fallar siempre.

**`tools/fleet_estado.py`** compara el **contenido** archivo por archivo contra
el maestro y separa tres cosas: lo que corre sin commitear, lo que le falta a un
sitio y lo que solo tiene el sitio. Comparar `git log` entre servidores no
sirve — cada uno reconcilia con commits propios, así que los hashes difieren
siempre aunque el contenido sea idéntico; por eso la deriva nunca se vio.

Mientras se escribía cometió el error que ahora vigila: el guion iba dentro de
la línea de comando de `ssh`, el shell **local** expandía el `$(git rev-parse)`
antes de que viajara y cada sitio contestaba con datos del maestro. Salía "todo
al día" sin haber mirado nada. Va por entrada estándar, y hay una prueba que
falla si alguien lo devuelve a un argumento.

**`tools/fleet_sync_core.sh`** propaga el árbol completo, reinicia, comprueba
salud, corre las pruebas y revierte solo si algo falla — sin lista que recordar.
Y **se niega a sincronizar si el maestro tiene código sin commitear**: propagar
un árbol sucio reparte un estado que no existe en ningún historial. En su
primera corrida frenó a quien lo escribió, que es exactamente el punto.

Un temporizador diario lo revisa solo. En una instalación de un solo hotel no
hay flota y la herramienta sale sin hacer nada.

Encontró de paso dos archivos borrados a propósito en Ópera hace semanas que
seguían vivos en los tres labs, porque el rsync manual nunca usó `--delete`.

### Shomer hablaba de Shomer

Con la flota consolidada, se midió el tráfico real: 1.013 mensajes en 30 días.
El bloque identificable más grande **no era del hotel, era del propio Shomer**:

- **55 mensajes** "✅ SHOMER operativo — todos los sistemas OK", tres veces al
  día. No dicen nada, y además ya estaba dicho: el resumen diario publica CPU,
  RAM, disco y servicios con **más** detalle. Duplicación pura. Un técnico con
  2-3 hoteles recibía unos 9 al día, todos iguales.
- **32 mensajes** "SISTEMA REINICIADO", casi todos despliegues nuestros. Que
  Shomer se reinicie no es un hecho del hotel.

El riesgo real del cambio era perder la prueba de vida, así que el latido se
sigue **registrando** y el resumen diario ya lo publica; lo único que traía y no
estaba allí era el estado de la WAN, que bajó al resumen. Y el reinicio ahora
cuenta los arranques de la última hora: uno es un despliegue, varios son un
servicio que no levanta — eso sí se avisa, con el número, que es el dato útil.
Umbral configurable por sitio (`guardian.reinicios_para_avisar`), y
`guardian.heartbeat_telegram` devuelve el latido a quien lo quiera.

**87 mensajes menos al mes sin perder una sola señal real.**

### Lo que se midió y NO se tocó

Las oleadas de Pulse (10 equipos avisando "degradando" en 40 segundos con la
misma latencia, y "estable" tres minutos después: 20 mensajes para un solo
hecho, con el gateway en la lista delatando la causa compartida) son solo el
**6%** del tráfico: agruparlas ahorraría unos 36 mensajes al mes. Está medido y
anotado, pero no se tocó — primero lo grande.

### Estado

189/189 pruebas del core y 99/99 del agente en los cuatro servidores; agente
v1.36.0. `fleet_estado.py` da salida 0 por primera vez: toda la flota con el
mismo código y nada fuera de git.

**Ópera tiene el código pero sigue con el comportamiento anterior**: aplicarlo
exige reiniciar servicios en producción (norma B.3).

## Sesión 87 (12 sep 2026) — La evidencia del internet + un equipo que no contesta no es un equipo lento

### Extender la vigilancia sin depender de que alguien se acuerde

Juan Pablo pidió cinco días más de verificación del internet del hotel (hasta el
**17 sep 2026**). El monitor horario existía, pero **no guardaba nada**: la única
evidencia de que el internet estuvo bien era que no llegaron alertas —
indistinguible de un monitor atascado, que es el fallo que ya apareció tres
veces en este sistema.

Cada lectura queda registrada con el uso real (sesiones y huéspedes), purga a
los 30 días y sin inflarse cuando alguien recarga el panel. El resumen diario
publica cuántas comprobaciones hubo y cuántas salieron limpias. **Cero lecturas
se reporta como "no se midió", nunca como "todo bien"** — y hay una prueba que
falla si alguien lo convierte en un resultado bueno.

### El fallo que Juan Pablo vio en Telegram

Cuatro datáfonos e impresoras POS salieron como *"⚠️ Pulse — degradando —
latencia EWMA 401 ms (normal ~0 ms)"* mientras respondían al ping en **0,3 ms
con 0% de pérdida** (medido a mano en ese momento: 0,221 a 0,578 ms los cuatro).

**La causa:** cuando un equipo no contestaba, se metía el valor del TIMEOUT
—9.000 ms en este sitio— en el promedio de latencia como si fuera una medición.
Esos cuatro POS fallan pings a diario (32 caídas al mes cada uno: los mismos del
reporte de POS), así que su promedio quedaba envenenado de forma permanente. Y
el estado **no tenía salida**: la línea base solo se recalcula cuando el equipo
está estable, y con el promedio envenenado no podía volver a estarlo nunca.

Peor que el ruido: convertía un problema de **respuesta** en uno de **lentitud**,
que es otro problema y manda al técnico a buscar donde no es.

Sin medición ya no se inventa una. La señal no se pierde: que un equipo deje de
contestar lo cuenta el EWMA de pérdida, su canal correcto, y la caída total la
avisa el evento de offline aparte. Verificado en producción: los cuatro pasaron
de 225 ms a **0,3-0,6 ms** y de "degrading" a **stable** en minutos.

### El mismo error de método, otra vez

Al diagnosticar, `pulse_config()` desde la consola decía `enabled: False` — Pulse
apagado. Falso: el servicio recibe `INFRA_PULSE_ENABLED=1` por
`EnvironmentFile`, y un proceso lanzado a mano no hereda ese entorno. Es el
tercer caso del mismo patrón hoy (ver Sesión 85, JWT_SECRET). **Medir fuera del
entorno del servicio y creerle al resultado** es un error recurrente: verificar
siempre contra el proceso real.

### Estado

208/208 pruebas del core y 99/99 del agente en los cuatro servidores; agente
v1.37.0. Flota consistente.

## Sesión 88 (12 sep 2026) — Las cuatro pendientes de la línea de ruido

### Oleadas de degradación: 20 mensajes para un hecho

Diez equipos —dos servidores, cinco switches, una impresora y el **propio
router**— avisaron "degradando" en 40 segundos, todos con 534-538 ms contra su
normal de ~349, y volvieron solos tres minutos después. El delator estaba en la
lista: si sube la latencia del router, sube la de todo lo que pasa por él.

La agrupación de oleadas **ya existía** para equipos caídos
(`format_wave_message`), pero no para los degradados: ahí salía un mensaje por
equipo. Ahora los eventos del ciclo se juntan antes de decidir y, a partir del
umbral del sitio, sale uno solo que dice cuántos son, la medida común y —cuando
el gateway aparece— por dónde empezar. Por debajo del umbral cada equipo
conserva su aviso detallado: **un equipo con problema propio no puede perderse
dentro de una agrupación**.

### Informe al coordinador: construido, esperando credenciales

Separa dos trabajos que compartían canal: el técnico actúa con Telegram, el
coordinador supervisa lo que lleva días sin resolverse. Mandarle las mismas
alertas no lo informa, lo entierra.

Se arma solo con hechos ya registrados y responde a una pregunta: qué sigue
pendiente. **Probarlo con datos reales sacó dos fallos que en teoría no se
veían**: la antigüedad salía vacía porque la columna es `opened_at` y no
`created_at` —justo el dato que hace decidir al coordinador— y los hallazgos del
cerebro aparecían como una lista cortada a la mitad, que hace parecer que el
problema es del primer equipo.

`auditar_monitores.py` cazó que el monitor corría **sin aparecer en
`/monitores`**: habría quedado invisible, y si deja de salir el coordinador no
se entera de nada. De paso salió que el contador del log decía "32 tasks" cuando
corrían 41 — escrito a mano. Una línea así se mira justamente para notar que un
monitor dejó de arrancar; con el número fijo no servía para nada.

Falta solo la cuenta de correo. Configuración por sitio en el `.env`.

### Los datáfonos: el dato estaba y nadie lo veía

Los dos Ingenico figuraban como "ubicación por confirmar". Se sacaron sus MAC de
la tabla ARP del router (`38:EF:E3:7B:4B:5E` y `38:EF:E3:9D:E9:D9`, mismo
fabricante, misma VLAN `LanAdmin`) y se descartaron **4 de los 8 switches**
consultando sus tablas de direcciones. El puerto exacto no se puede sacar en
remoto: los switches candidatos no exponen la MIB de reenvío.

Pero lo importante fue otro: **Shomer ya tenía la MAC de 50 de 51 equipos** —las
recoge el propio sondeo— y el dato no aparecía en ningún lado donde alguien
fuera a mirarlo. Ahora cada pendiente del informe trae su ubicación y, si no
hay, la MAC para identificar el aparato por su etiqueta. "Por confirmar
ubicación" no se presenta como ubicación: mandar al técnico ahí es mandarlo a
ninguna parte.

### La medición, con lo que se puede afirmar hoy

Base: **1.024 mensajes/30 días = 34,1 por día**. El día de hoy no sirve para
comparar —se reinició media docena de veces desplegando—, pero dos señales sí:

- **Seis reinicios de servicio, cero mensajes anunciándolos** (antes, seis).
- **Un solo latido "todo OK"**, el anterior al cambio, contra tres diarios.
- De los 51 mensajes de hoy, **32 fueron del fallo de Pulse** ya corregido. Sin
  ellos el día cierra en 19, bastante por debajo de la base.

Una medición limpia necesita 3-4 días sin despliegues.

### Advertencia de método, tercera vez en el día

Diagnosticando los datáfonos, `snmpwalk` desde la consola decía que cuatro
switches no respondían. Falso: Shomer los consulta sin problema — prueba v2c y
cae a v1, y mi comando solo usaba v2c. Igual que con `JWT_SECRET` y con
`pulse_config`. **Medir fuera del entorno real y creerle al resultado** sigue
siendo el error más caro de esta sesión.



---

# 📚 Parte A.2 / A.3 (estado de laboratorio, mayo 2026)

Archivado 13 sep 2026 -- snapshot puntual de pruebas de mayo 2026, superado por el estado real verificado en "Estado por modulo" al inicio de CLAUDE.md.


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


---

# 📚 Parte E.1 / E.2 (bugs e integracion Hunter, mayo 2026)

Archivado 13 sep 2026 -- resuelto y verificado hace meses, contenido historico de la Sesion 23.

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



---

# 📚 Parte E.4, items P5-P11 (resueltos Hunter, mayo 2026)

Archivado 13 sep 2026 -- todos resueltos o cerrados como decision de diseno.

| P5 | ~~Export CSV histórico bloqueos~~ — ✅ `GET /remedies/history/csv` (descarga directa) | ✅ Sesión 24 |
| P6 | ~~`hunter.firewall_port` en formulario UI~~ — ✅ campo Puerto SSH + Timeout SSH en panel Firewall | ✅ Sesión 24 |
| P7 | ~~`hunter.firewall_timeout` hardcodeado~~ — ✅ `hunter.firewall_timeout` en BD, `_get_firewall_creds()` lo lee, `run_timeout = connect_timeout - 2` | ✅ Sesión 24 |
| P8 | ~~Columna `firewall_blocked`~~ — ✅ migración automática `ALTER TABLE`, INSERT guarda `1` si SSH OK, `0` si solo-BD | ✅ Sesión 24 |
| P9 | **Retry automático al reabrir CB** — ✅ **CERRADO como diseño intencional**: sync manual disponible (`POST /remedies/firewall/sync`, botón en panel). Para hoteles de hasta ~100 hab. el flujo de dos pasos (Reset CB → Sincronizar) es suficiente; muchos clientes Colombia ni firewall tienen. Hacer el reset automático complicaría UX (botón lento) sin beneficio real en ese segmento. | ✅ Cerrado — decisión Juan Pablo |
| P10 | ~~Vista de bloqueos históricos~~ — ✅ `GET /remedies/history`, sección colapsable con tabla + CSV en panel Hunter | ✅ Sesión 24 |
| P11 | **Clave Wazuh con HMAC** — ~~prioridad media~~ → **DESCARTADO**: Wazuh y Shomer corren en el mismo servidor; la llamada va a `http://127.0.0.1:8000` (loopback, nunca sale al exterior). El riesgo real es exposición del puerto 8000 en UFW — ya está cubierto (solo localhost). No aplicar HMAC si no hay justificación arquitectural. | ✅ No aplica (mismo servidor) |


---

# 📚 Parte L (backlog abril-mayo 2026)

Archivado 13 sep 2026 -- casi todo resuelto (ver marcas Sesion 25/26/28/29). Los 3 items PLAN que seguian abiertos se movieron a la nueva Parte L en CLAUDE.md.

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

# 📚 Parte N vieja (agente, hasta Sesion 19, mayo 2026)

Archivado 13 sep 2026 -- reescrita por completo en CLAUDE.md contra el codigo real de hoy: la version vieja no mencionaba el cerebro ni la mayoria de los modulos actuales, y contradecia el resumen inicial en un punto (decia bot compartido con Guardian; desde Sesion 80 cada sitio tiene su propio bot).

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
