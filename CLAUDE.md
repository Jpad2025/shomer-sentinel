# Shomer Sentinel 2.0 — Manifiesto vivo

Este archivo une **dos cosas** en un solo lugar: (1) **qué hace el sistema hoy**, según instalación real y laboratorio USB; (2) **normas de diseño y referencia técnica** sin perder línea base del producto.

Los manuales de instalación detallados (cableado, modelo por modelo) y las tablas QA fila por fila **no** caben completos aquí; el equipo debe entregarlos en el mismo paquete de instalación donde corresponda. Este archivo concentra arquitectura, normas y estado sintético.

**Última unificación:** 10 jun 2026 (Sesión 51 — Tracker Ópera + **matriz políticas agente autónomo** `POLITICAS_AGENTE.md` en shomer-agent ✅ §AK.8) · Idioma: español técnico claro · Origen código: `/opt/network_monitor/`

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
| Opcionales cliente | `suricata`, stack Wazuh, `redis-server`, `lldpd`, etc. según alcance |
| `shomer-monitor.service` | Script de monitoreo de infraestructura (`monitor.py`). Instalar: `sudo cp /opt/network_monitor/etc/shomer-monitor.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now shomer-monitor`. Requiere Redis en 127.0.0.1:6379 y llave SSH `~/.ssh/id_rsa_shomer`. |

**Comprobación rápida:**  
`systemctl is-active shomer-guardian shomer-tools nginx shomer-health-watchdog.timer`

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
| **Bot Telegram (agente)** | Docker `shomer-agent` activo en `.205`. **31 comandos slash** + 7 callbacks + **15 tools** (function calling). **Chat interactivo:** OpenAI `gpt-4o-mini` (`.205` lab). **Monitores background + `/doc`:** Groq Llama 3.3-70b (gratis). Router `core/llm_router.py` — fallback automático a Groq si OpenAI falla o supera caps. Memoria SQLite + **`token_usage`** (columnas `provider`, `user_id`). Hard caps OpenAI en código (~$0.05–0.15/mes/Shomer). Tope web OpenAI $5/mes (cliente). 20 monitores. Rate-limit 5s/usuario. ✅ Sesión 33 (22/05) tools+tokens · ✅ Sesión 34 (23/05) OpenAI operativo lab `.205`. |
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
- Firewall remoto ejecuta sobre equipo **Linux/OpenWrt** con credencial `hunter.firewall_*` vía SSH (asyncssh). El código se llama `_mikrotik_block` internamente pero usa **iptables** estándar Linux — funciona en OpenWrt; NO usar con RouterOS MikroTik nativo (sintaxis distinta).

**Firma ICMP laboratorio SID 9009001** suele estar bajo **`/etc/suricata/rules/`** en un fichero tipo `shomer-local.rules`; recarga lógica: `POST /remedies/rules/reload`.

**Checklist campo Hunter (resumen contenido habitual del paquete de soporte):**
- NIC gestión vs NIC espejo acordes al hardware (ej. `enp2s0` / `enp4s0` sólo ejemplo).
- **`hunter.auto_block_*`** revalidar tras cambiar la LAN del cliente.
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

Cooldown reboot y anti-ráfagas viven Redis + algunas claves replicadas SQLite tabla `failsafe_state`.

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

| Comando | Técnico | Developer | Acción |
|---------|---------|-----------|--------|
| `/ayuda` | ✅ | ✅ | Lista de comandos disponibles |
| `/salud` | ✅ resumen | ✅ + botones repair | Estado servicios, disco, Guardian, Hunter pipeline |
| `/resumen` | ✅ | ✅ | Resumen IA on-demand del sistema |
| `/equipos` | ✅ | ✅ | Lista equipos con estado |
| `/diagnostico <ip>` | ✅ | ✅ | Ping + estado Guardian + fallos + último reboot |
| `/ping <ip>` | ✅ | ✅ | ICMP ping |
| `/reiniciar <ip>` | ✅ | ✅ | Reboot AP con confirmación |
| `/clientes <ip>` | ✅ | ✅ | Dispositivos conectados |
| `/info <ip>` | ✅ | ✅ | Firmware, uptime, recursos |
| `/alertas` | ✅ | ✅ | Últimas alertas Hunter con botón bloqueo |
| `/desbloquear <ip>` | ✅ | ✅ | Desbloquear IP en Hunter |
| `/bloquear <ip>` | ✅ | ✅ | Bloquear IP manualmente |
| `/mantenimiento` | ✅ | ✅ | Pausar reboots automáticos Guardian |
| `/agregar` | ✅ | ✅ | Registrar equipo en el agente |
| `/eliminar <ip>` | ✅ | ✅ | Quitar equipo |
| `/instalar` | ✅ | ✅ | Guía instalación paso a paso (10 pasos) |
| `/verificar` | ✅ | ✅ | Checklist final de instalación |
| `/monitores` | ✅ | ✅ | Estado de los 20 monitores background |
| `/usuario` | ✅ | ✅ | Comandos para crear usuario de servicio `shomer` |
| `/nuevo` | ✅ | ✅ | Limpiar historial conversación IA |
| `/doc <pregunta>` | ❌ | ✅ | Consulta técnica interna (developer) |
| `/tokens` | ❌ | ✅ | Consumo tokens por proveedor + costo USD estimado |
| `/botstatus` | ❌ | ✅ | Proveedor LLM activo, caps, nodos online |
| Texto libre | ✅ | ✅ | OpenAI (o Groq fallback) con 15 tools — ver §V |

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

## N.8 Reparación guiada — `/salud` (developer)

Botones disponibles cuando hay problemas:
- `🔧 Reiniciar Guardian/Tools/Nginx` → SSH → `sudo systemctl restart`
- `🦁 Reiniciar Suricata` → SSH → `sudo systemctl restart suricata`
- `🗑️ Docker prune` → SSH → `sudo docker image prune -f` (requiere autorización)

SSH usa clave dedicada `/storage/shomer-agent/data/agent_restart_key` generada para el agente. Clave pública en `~/.ssh/authorized_keys` del host.

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
- `/mantenimiento on/off` — activa/desactiva `shomer_maintenance=1` en Redis; pausa reboots automáticos de Guardian durante trabajo en sitio
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
| LAN IP | `192.168.10.206/24` |
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
| shomer-hotelopera (ex-shomerbogota) | 192.168.10.206 | 100.103.148.119 | `https://100.103.148.119:8443` |
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

Esta sección documenta un **bug de arquitectura/instalación que puede repetirse en cualquier Shomer** (de ahí su lugar en CLAUDE.md). Los valores específicos de Hotel Ópera —p. ej. `hunter.subnets` con las VLANs del hotel (Huéspedes `10.1.48.0/22`, Eventos `30.30.0.0/22`, Admin WiFi `192.168.40.0/24`, Teléfonos `192.168.3.0/24`)— **NO van aquí**: viven en `/opt/network_monitor/SITE.md` dentro de `shomer-hotelopera` (ex-`shomerbogota`, renombrado Sesión 50 — ver nota de convención abajo), conforme a la norma §AH.1. CLAUDE.md es manual de desarrollo (aplica a todos los sitios); SITE.md es config de cliente (aplica solo a ese sitio).

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
