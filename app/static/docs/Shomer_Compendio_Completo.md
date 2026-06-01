# Shomer Sentinel 2.0 — Compendio Completo del Sistema

**Para quién:** Juan Pablo Cero, Andrés, Laura — equipo USB Ingeniería  
**Qué es esto:** Todo lo que necesitas saber sobre el sistema en un solo documento.  
Desde qué hace cada módulo hasta cómo instalar el sistema operativo desde cero.  
**Última actualización:** mayo 2026

---

# PARTE 1 — QUÉ ES SHOMER SENTINEL

## 1.1 En una sola oración

Shomer Sentinel es un **servidor físico (mini PC) que se instala en la red del cliente** y desde el cual se puede monitorear, proteger e inventariar toda la red — sin depender de herramientas en la nube ni de servicios externos.

## 1.2 El problema que resuelve

Los hoteles, empresas y colegios tienen redes WiFi con decenas o cientos de equipos (routers, APs, PCs, impresoras). Cuando algo falla nadie sabe exactamente qué pasó ni cuándo. Los APs se cuelgan de madrugada y nadie los reinicia hasta que un huésped se queja. Un ataque entra por la red y nadie lo detecta hasta semanas después.

Shomer resuelve eso:
- Vigila que los equipos estén vivos — los reinicia solo si se caen
- Registra todos los dispositivos de la red
- Detecta amenazas de seguridad en tiempo real
- Hace backups automáticos de los equipos del cliente
- Manda alertas por Telegram al técnico

## 1.3 Qué incluye el sistema

| Componente | Qué es |
|-----------|--------|
| **Mini PC** | El hardware físico — se instala en el rack o en el cuarto de comunicaciones del cliente |
| **Panel web** | La interfaz que controla todo — se abre desde cualquier laptop en la misma red |
| **Bot Telegram** | Agente inteligente que manda alertas y permite hacer acciones desde el celular |
| **4 módulos** | Guardian, Tracker, Hunter, Protector — cada uno con función específica |

## 1.4 Diagrama básico de cómo queda instalado

```
                        INTERNET
                            │
                    [ISP / Modem]
                            │
             ┌──────────────────────────┐
             │    MikroTik (OpenWrt)    │  ← Firewall del cliente
             │    WAN ◄── del ISP       │  ← Hunter lo controla por SSH
             │    LAN ──► switch        │
             └──────────┬───────────────┘
                        │
             ┌──────────────────────────┐
             │    Switch principal      │
             │    del cliente           │
             └──┬──────────┬────────────┘
                │          │
          [SHOMER]       [APs, PCs, impresoras...]
          mini PC
          ├── NIC gestión ──► IP fija en la red del cliente
          │                   Panel web accesible desde laptops
          └── NIC espejo  ──► SIN IP — recibe copia del tráfico
                              para que Hunter/Suricata lo analice
```

---

# PARTE 2 — EL HARDWARE

## 2.1 Especificaciones mínimas y recomendadas

| Componente | Mínimo | Recomendado |
|-----------|--------|-------------|
| CPU | Intel N95 / N100 | Intel Core i3 o superior |
| RAM | 8 GB (sin Wazuh) | **16 GB** |
| Disco | 128 GB SSD | **256 GB SSD** o 500 GB |
| Tarjetas de red | **2 NICs integradas** | 2 NICs integradas PCIe |
| SO | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

⚠️ **Las 2 NICs son obligatorias.** Sin dos tarjetas de red, Hunter no puede analizar el tráfico (necesita una NIC dedicada al espejo del switch).

## 2.2 Las dos tarjetas de red y su función

| NIC | Nombre típico | Función | Tiene IP |
|-----|--------------|---------|---------|
| **Gestión** | `enp2s0` | Conecta al switch del cliente — panel web, SSH, Guardian | ✅ IP fija |
| **Espejo** | `enp4s0` | Recibe copia del tráfico del switch (puerto SPAN) — Suricata analiza aquí | ❌ Sin IP |

**Regla de oro:** La NIC espejo **nunca lleva IP**. Si alguien le asigna una IP, puede causar conflictos de red en el cliente.

Los nombres `enp2s0` y `enp4s0` son los del lab. En otro hardware pueden ser diferentes (`eth0/eth1`, `enp3s0/enp5s0`). Se verifican con `ip link show` antes de instalar.

## 2.3 Accesorios entregados con el appliance

- Mini PC con Ubuntu 22.04 y Shomer preinstalado
- Router **MikroTik con OpenWrt** (firewall del cliente) — ya viene configurado
  - OpenWrt instalado
  - Llave SSH del Shomer cargada (Hunter se conecta sin contraseña)
  - Puerto SPAN/TEE activo para espejo de tráfico
  - WireGuard VPN listo para acceso remoto del técnico

---

# PARTE 3 — EL SISTEMA OPERATIVO

## 3.1 Ubuntu 22.04 LTS

El sistema operativo base es **Ubuntu 22.04 LTS** (Long Term Support — soporte hasta 2027). Se eligió porque:
- Es estable y predecible
- Tiene soporte oficial para todos los paquetes que usa Shomer
- Es compatible con Suricata, Docker, Restic y los demás componentes

## 3.2 Usuario del sistema

| Campo | Valor |
|-------|-------|
| Usuario principal | `usb_admin` |
| Contraseña inicial | `Shomer2026!` (cambiar tras primera instalación) |
| Permisos | `sudo` completo |

## 3.3 Estructura de carpetas del sistema

```
/
├── opt/
│   └── network_monitor/        ← TODO EL CÓDIGO DE SHOMER
│       ├── app/                ← Código Python (APIs, templates, lógica)
│       │   ├── api/            ← Endpoints de la API (Guardian, Hunter, Tracker, etc.)
│       │   ├── backend/        ← Lógica de base de datos y helpers
│       │   ├── scripts/        ← Scripts de escaneo, alertas, monitor
│       │   ├── templates/      ← HTML del panel web
│       │   └── static/         ← CSS, JS, imágenes, documentos PDF
│       ├── tools/              ← Scripts de instalación, fábrica, empaquetado
│       ├── tests/              ← Tests automáticos
│       ├── venv/               ← Entorno virtual Python (dependencias)
│       ├── CLAUDE.md           ← Manifiesto de desarrollo (para ingeniería)
│       └── SISTEMA_SHOMER.md   ← Guía técnica del producto
│
├── storage/
│   ├── db/                     ← BASES DE DATOS
│   │   ├── network_monitor.db  ← Guardian, Hunter, configuración del sistema
│   │   └── inventory.db        ← Tracker (inventario de equipos del cliente)
│   └── shomer-agent/           ← Agente Telegram (bot)
│       ├── core/               ← Código del bot
│       ├── drivers/            ← Drivers por marca de equipo
│       ├── data/               ← Datos persistentes del bot
│       └── .env                ← Tokens y credenciales del bot
│
├── srv/
│   ├── shomer_backups/
│   │   └── staging/            ← Repositorio Restic local (backups de clientes)
│   └── shomer_restore/         ← Carpeta temporal de restauraciones
│
├── var/
│   └── log/
│       └── shomer/             ← LOGS DEL SISTEMA
│           ├── api.log         ← Log del servicio principal (puerto 8000)
│           ├── tools_api.log   ← Log de Tracker y Protector (puerto 8001)
│           ├── tracker.log     ← Log del escáner de inventario
│           └── protector.log   ← Log de backups
│
├── etc/
│   └── shomer/
│       ├── shomer-runtime.env  ← Variables de entorno sensibles (JWT secret, etc.)
│       └── wazuh-integration.key ← Clave de integración Wazuh-Shomer
│
├── home/
│   └── usb_admin/
│       ├── .restic-local-pass  ← Contraseña del repositorio Restic local
│       └── .ssh/               ← Llaves SSH del servidor
│
└── etc/
    └── systemd/system/         ← Unidades de servicio de Shomer
        ├── shomer-guardian.service
        ├── shomer-tools.service
        ├── shomer-health-watchdog.service
        └── shomer-agent.service
```

---

# PARTE 4 — SERVICIOS Y PUERTOS

## 4.1 Qué servicios corren en el servidor

| Servicio | Puerto | Para qué sirve |
|---------|--------|----------------|
| `shomer-guardian` | **8000** | Motor principal: panel web, Guardian, Hunter, autenticación |
| `shomer-tools` | **8001** (solo localhost) | Tracker e inventario, Protector backups |
| `nginx` | **80** → redirige a 8443 | Proxy HTTPS del panel — el técnico accede aquí |
| `nginx` | **8443** | Panel HTTPS hacia el navegador |
| `redis-server` | **6379** (localhost) | Memoria de estado en tiempo real para Guardian |
| `suricata` | — | IDS — escucha tráfico en la NIC espejo |
| `shomer-agent` (Docker) | — | Bot Telegram — corre como contenedor Docker |
| `shomer-health-watchdog` | — | Timer que verifica y reinicia servicios caídos cada 30s |

## 4.2 Cómo se comunican entre sí

```
Navegador del técnico
        │
        ▼ HTTPS :8443
     nginx
        │
        ▼ HTTP :8000
shomer-guardian (FastAPI)
        │
        ├── Lee/escribe → /storage/db/network_monitor.db
        ├── Lee estado  → Redis :6379
        ├── Proxifica   → shomer-tools :8001
        │       │
        │       └── Lee/escribe → /storage/db/inventory.db
        │                      → /srv/shomer_backups/ (Restic)
        │
        └── SSH → APs del cliente (Guardian reboot)
                → Firewall OpenWrt (Hunter block)

shomer-agent (Docker)
        │
        ├── Lee APIs → :8000 (Shomer)
        ├── Lee BDs  → /storage/db/ (directo)
        ├── Lee Redis → :6379
        └── Envía → Telegram API (alertas e interacción)
```

## 4.3 Verificar que todo está corriendo

```bash
systemctl is-active shomer-guardian shomer-tools nginx redis-server suricata
# Todos deben responder: active
```

Si alguno no está active:
```bash
# Ver qué pasó
journalctl -u shomer-guardian -n 30
# Reiniciar
sudo systemctl restart shomer-guardian
```

---

# PARTE 5 — LOS 4 MÓDULOS

## 5.1 Guardian — El vigilante de red

**¿Qué hace?**  
Guardian monitorea constantemente los APs, routers y switches del cliente. Cada 10 segundos hace un "ping" a cada equipo. Si detecta que un equipo se cayó o perdió internet, lo reinicia automáticamente.

**¿Por qué es importante?**  
En hoteles, los APs se cuelgan de madrugada. Sin Guardian, nadie lo sabe hasta que los huéspedes se quejan en la mañana. Con Guardian, el equipo se reinicia solo en 2-3 minutos y llega una alerta por Telegram.

**¿Cómo funciona por dentro?**  
Por cada equipo monitorado, hace estas pruebas en orden:
1. **Ping** desde el Shomer al equipo (¿está vivo en la LAN?)
2. **Ping a internet** (8.8.8.8) desde el equipo mismo vía SSH (¿tiene salida a internet?)
3. **DNS** — pregunta a un servidor DNS desde el equipo (¿funciona la resolución?)
4. **HTTP** — hace un request HTTP y verifica el código de respuesta (¿la red funciona?)

**Estados posibles de un equipo:**

| Estado | Color | Qué significa | ¿Reinicia? |
|--------|-------|--------------|-----------|
| Online | 🟢 Verde | Todo bien | No |
| Degraded | 🟡 Amarillo | Calidad baja, funciona parcial | No — solo alerta |
| No-internet | 🟠 Naranja | Vivo en LAN pero sin internet | Sí, tras umbral |
| Offline | 🔴 Rojo | No responde en absoluto | Sí, tras umbral |

**Condiciones para el reboot automático:**
- El equipo lleva caído **3 ciclos consecutivos** (~5 minutos)
- No se reinició en las últimas **6 horas** (cooldown anti-loop)
- El servidor Shomer tiene internet en ese momento
- No hay modo mantenimiento activo

**Equipos compatibles:**

| Marca/Tipo | Método de reboot |
|-----------|-----------------|
| GL.iNet, OpenWrt, Raspberry Pi | SSH |
| TP-Link EAP (EAP225, EAP610) | SNMP v2c |
| Ubiquiti (UniFi, airMAX) | SSH |
| MikroTik | SSH |
| Cisco SG/SF switches | SSH |
| Aruba Instant | SSH |

**Archivos de código relevantes:**
- `app/api/shomer_guardian_nodes.py` — lógica del poller
- `app/api/shomer_guardian_health_checks.py` — las pruebas (ping, SSH, DNS, HTTP, SNMP)

---

## 5.2 Tracker — El inventario de red

**¿Qué hace?**  
Tracker escanea la red del cliente y construye una lista de todos los dispositivos: IP, MAC, fabricante, nombre del equipo, sistema operativo, CPU, RAM, disco, software instalado.

**¿Por qué es importante?**  
El cliente necesita saber qué tiene en su red. Para cumplimiento, para soporte, para saber cuando aparece un equipo desconocido. El técnico puede exportar el inventario a Excel para el cliente.

**Tipos de escaneo:**

| Tipo | Tiempo | Qué obtiene |
|------|--------|------------|
| **Quick Scan** | 2–5 min | IP, MAC, fabricante, nombre básico |
| **Deep Scan** | 5–20 min | Todo lo anterior + OS, CPU, RAM, disco, software (requiere credenciales) |

**Para el deep scan necesita credenciales en cada equipo:**
- **Windows:** usuario con permisos WMI (ver Parte 9.2 de `SOPORTE_TECNICO.md`)
- **Linux/macOS:** usuario SSH con sudo
- **Switches:** SNMP community

**Exports disponibles:**
- Excel global (todos los equipos)
- PDF etiquetas (con código de barras por equipo)

**Snapshot de inventario:**  
Al cerrar un contrato o hacer un inventario formal, se usa `POST /snapshot/close`. Esto archiva el estado actual y limpia la tabla viva. El Excel se exporta el mismo día del cierre.

**Archivos de código relevantes:**
- `app/api/inventory_*.py` — endpoints del inventario
- `app/scripts/tracker/` — motor de escaneo
- `/storage/db/inventory.db` — base de datos del inventario

---

## 5.3 Hunter — El cazador de amenazas

**¿Qué hace?**  
Hunter analiza en tiempo real el tráfico de la red del cliente en busca de ataques, escaneos, malware y comportamientos sospechosos. Cuando detecta algo, puede bloquearlo automáticamente en el firewall.

**¿Por qué es importante?**  
La mayoría de las redes de hoteles y empresas no tienen detección de intrusiones. Un equipo infectado puede estar exfiltrando datos durante semanas sin que nadie lo sepa. Hunter lo detecta en segundos.

**¿Cómo funciona por dentro?**

```
Tráfico de la red
        │
        ▼ (espejo SPAN del switch → NIC espejo del Shomer)
    SURICATA (IDS)
        │ lee reglas de /etc/suricata/rules/
        │ escribe alertas en eve-alerts.json
        ▼
    Shomer Hunter (panel)
        │ muestra alertas al técnico
        │ aplica políticas auto_block
        ▼
    SSH → Firewall OpenWrt
        │ iptables -I FORWARD -s IP_ATACANTE -j DROP
        ▼
    Telegram → "IP X.X.X.X bloqueada por Hunter"
```

**Integración con Wazuh (opcional):**  
Si el cliente tiene Wazuh instalado, el manager Wazuh puede también disparar bloqueos vía el script `wazuh_shomer_block.py → POST /remedies/block`.

**Estados de un bloqueo:**

| Estado | Qué significa |
|--------|--------------|
| `✔ red` | La regla está activa en el firewall (iptables) |
| `solo BD` | Se registró en la base de datos pero no se aplicó en el router |

Si ves `solo BD`: usar el botón **Sincronizar Firewall** en el panel.

**Reglas importantes de operación:**
- La primera semana en un sitio nuevo: **auto-bloqueo apagado**. Observar qué tráfico genera el cliente antes de activar bloqueos automáticos.
- Siempre agregar a excepciones: IP del gateway, IP del propio Shomer, IP de Wazuh.
- Nunca usar IPs operativas del cliente para pruebas — usar `198.51.100.1` (reservada RFC 5737).

**Archivos de código relevantes:**
- `app/api/casador_blocking.py` — lógica de bloqueo/desbloqueo
- `app/api/casador_rules.py` — gestión de reglas Suricata
- `app/api/casador_intel.py` — inteligencia de alertas
- `tools/cazador/wazuh_shomer_block.py` — script de integración Wazuh

---

## 5.4 Protector — Backups automáticos

**¿Qué hace?**  
Protector hace backups automáticos de los equipos del cliente (Windows, Linux, macOS) hacia el disco local del Shomer y opcionalmente hacia la nube (Backblaze B2).

**¿Por qué es importante?**  
Los equipos de los clientes (PCs de recepción, contabilidad, servidores) suelen no tener backups. Cuando se daña un disco o hay un ransomware, pierden todo. Protector resuelve eso sin que el cliente tenga que hacer nada.

**Tecnología:** Usa **Restic** — una herramienta profesional de backups incremental. Solo transfiere los archivos que cambiaron desde el último backup (delta), lo que hace que los backups diarios sean muy rápidos después del primero.

**Protocolo de backup por equipo:**

```
HH:MM (hora programada por equipo)
  1. Shomer se conecta al equipo (SSH para Linux/Mac, SMB para Windows)
  2. Copia los archivos al Shomer → Restic los comprime y deduplica
  3. Si B2 activado: sincroniza solo el delta nuevo a la nube
  4. Telegram: "Backup OK — Hotel Plaza PC Recepción — 2.3 GB — 4 min"
```

**Convención multi-cliente en B2:**  
Cada cliente tiene su propio prefijo (slug) en B2. Esto es obligatorio en campo:

```
bucket-empresa/
  hotel-plaza/      ← Todo lo de Hotel Plaza
  empresa-abc/      ← Todo lo de Empresa ABC
  hotel-real/       ← Todo lo de Hotel Real
```

El slug se define en ingeniería antes de la instalación y no se cambia.

**Restauración desde panel (sin línea de comandos):**
1. Panel → Protector → B2 → ver snapshots en nube
2. Seleccionar snapshot → Restaurar → el Shomer lo descarga de B2
3. Descargar ZIP al PC del técnico directamente desde el navegador

**Archivos de código relevantes:**
- `app/api/backups.py` — endpoints de backups
- `app/backend/protector.py` — lógica Restic + B2
- `/srv/shomer_backups/staging/` — repositorio Restic local

---

# PARTE 6 — EL BOT TELEGRAM (Agente Shomer)

## 6.1 Qué es

El bot es un agente de inteligencia artificial que vive en Telegram. Manda alertas automáticas y permite que el técnico controle el sistema desde el celular.

**Tecnología:** Python + **OpenAI `gpt-4o-mini`** (chat interactivo del técnico) + **Groq Llama 3.3-70b** (monitores background, `/doc`, fallback) + Telegram Bot API. Router: `core/llm_router.py`.

**Corre como:** Contenedor Docker en `/storage/shomer-agent/`

**El bot y Guardian usan el mismo chat de Telegram.** Guardian manda alertas (solo escribe). El bot recibe comandos (lee y escribe).

## 6.2 Comandos principales

| Comando | Para qué |
|---------|---------|
| `/salud` | Estado de servicios, CPU, RAM, disco, redes |
| `/equipos` | Lista de APs con estado actual |
| `/diagnostico 10.10.0.5` | Estado completo de un equipo específico |
| `/alertas` | Últimas alertas Hunter con botón de bloqueo |
| `/reiniciar 10.10.0.5` | Reiniciar un AP — pide confirmación |
| `/mantenimiento` | Activar/desactivar pausa de reboots automáticos |
| `/bloquear 1.2.3.4` | Bloquear IP manualmente |
| `/desbloquear 1.2.3.4` | Liberar IP bloqueada |
| `/historial` | Últimos 10 cambios del sistema |
| `/instalar` | Guía paso a paso para nueva instalación |
| `/verificar` | Checklist automático del estado de la instalación |
| `/usuario` | Comandos para crear usuario de servicio (Linux/Mac/Windows) |
| `/nuevo` | Limpiar historial de conversación con la IA |
| `/monitores` | Estado de los 20 monitores automáticos en background |
| `/resumen` | Resumen del sistema generado por IA |

## 6.3 Lo que hace solo (sin que le pidas)

El bot tiene 20 monitores que corren en segundo plano:

| Monitor | Qué detecta |
|---------|------------|
| `watch_devices` | Caída o recuperación de equipos |
| `watch_hunter` | Nuevas IPs bloqueadas — explica por qué |
| `watch_services` | Guardian/Tools/Nginx caídos |
| `watch_disk` | Disco >80% → alerta; >85% → limpia automático |
| `watch_wan_outage` | WAN del servidor caída |
| `watch_resources` | CPU >80% o RAM >85% |
| `watch_guardian_nodes` | Cambios de estado en nodos Guardian (con botón de reboot) |
| `watch_pipeline` | Pipeline Hunter degradado |
| `watch_backups` | Sin backup en 26 horas |
| `daily_summary` | Resumen diario a las 7:00 AM |
| `preventive_reboot` | Reinicia APs con uptime >30 días (04:00 AM) |
| Y 9 más... | Docker, conectividad, Groq, seguridad, etc. |

## 6.4 Niveles de acceso

| Nivel | Quién | Qué puede hacer |
|-------|-------|----------------|
| **developer** | Juan Pablo (AGENT_DEVELOPER_ID) | Todo — incluyendo backup, restaurar, /doc, /pause |
| **tecnico** | Técnico del cliente (TELEGRAM_CHAT_ID configurado) | Operación diaria — reiniciar, bloquear, desbloquear, ver estado |
| **none** | Cualquier otro | Ignorado silenciosamente |

## 6.5 Variables de entorno necesarias (.env)

```
TELEGRAM_BOT_TOKEN=       # token del BotFather para este cliente
TELEGRAM_CHAT_ID=         # chat ID del técnico del cliente
GROQ_API_KEY=             # console.groq.com — monitores + fallback (gratis)
LLM_PROVIDER_INTERACTIVE= # openai | groq (default groq si vacío)
OPENAI_API_KEY=           # platform.openai.com — solo si interactive=openai
OPENAI_MODEL=gpt-4o-mini
OPENAI_LIMIT_PER_MESSAGE=2000
OPENAI_LIMIT_PER_USER_DAILY=8000
OPENAI_LIMIT_DAILY=12000
AGENT_DEVELOPER_ID=       # Telegram ID de Juan Pablo
AGENT_DEVELOPER_CHAT_ID=  # Chat de Juan Pablo (alertas críticas)
SHOMER_URL=http://127.0.0.1:8000
SHOMER_USER=admin
SHOMER_PASS=              # contraseña del panel
SITE_NAME=Hotel XYZ       # nombre del cliente — aparece en todos los mensajes
```

**OpenAI en campo (opcional):** crear API key en platform.openai.com → Settings → Limits → monthly budget **$5**. Costo real típico con caps de código: **~$0.05–0.15 USD/mes** por Shomer. Sin OpenAI configurado el bot usa Groq gratis.

## 6.6 Comandos de operación del bot

```bash
# Ver estado
sudo docker compose -f /storage/shomer-agent/docker-compose.yml ps

# Ver logs en tiempo real
sudo docker compose -f /storage/shomer-agent/docker-compose.yml logs --tail=30

# Reiniciar
sudo systemctl restart shomer-agent.service

# Reconstruir tras cambios de código
cd /storage/shomer-agent && sudo docker compose down && sudo docker compose build && sudo docker compose up -d
```

---

# PARTE 7 — INSTALACIÓN COMPLETA DESDE CERO

## 7.1 Visión general del proceso

```
1. Preparar USB booteable con Ubuntu 22.04
2. Instalar Ubuntu en el mini PC (particionado manual)
3. Conectar a Tailscale (para acceso remoto)
4. Transferir el paquete Shomer al equipo
5. Ejecutar el instalador automático (install_shomer.sh)
6. Completar el wizard de configuración en el navegador
7. Configurar el bot Telegram
8. Verificar con /verificar en el bot
```

## 7.2 Paso 1 — Preparar la USB booteable

**ISO necesario:** Ubuntu 22.04 LTS Server (`ubuntu-22.04.x-live-server-amd64.iso`)  
Descargar de: ubuntu.com → Download → Ubuntu 22.04 LTS

**Herramienta para grabar:**
- Windows: **Rufus** (rufus.ie) — seleccionar GPT + UEFI
- Mac: Terminal con `dd`
- Linux: `dd` o `balenaEtcher`

Ver guía detallada: `Instalacion_Ubuntu_USB_Particiones.md`

## 7.3 Paso 2 — Instalar Ubuntu (particionado manual)

⚠️ **Siempre usar particionado MANUAL.** El automático no crea la estructura que Shomer necesita.

### Esquema para SSD 256 GB (equipo Bogotá y campo)

| Partición | Tamaño | Formato | Para qué |
|-----------|--------|---------|---------|
| `/boot/efi` | 1 GB | FAT32 | Arranque UEFI |
| `/boot` | 1 GB | ext4 | Kernel y grub |
| `/` | 20 GB | ext4 | Sistema operativo base |
| `/var` | 20 GB | ext4 | Logs, journal |
| `/opt` | 20 GB | ext4 | Código Shomer + Python |
| `/home` | 10 GB | ext4 | Usuario usb_admin |
| `/srv` | 133 GB | ext4 | Backups Restic (la más grande) |
| `/tmp` | 4 GB | ext4 | Temporales |
| `swap` | 4 GB | swap | Memoria de intercambio |
| `/storage` | 25 GB | ext4 | Bases de datos Shomer |

**Configuración del usuario durante la instalación:**
```
Nombre de usuario: usb_admin
Contraseña: Shomer2026!  (cambiar post-instalación)
Nombre del servidor: shomer-[nombrecliente]
✅ Instalar OpenSSH Server: SÍ (obligatorio)
```

## 7.4 Paso 3 — Conectar a Tailscale

Tailscale es la VPN que permite a Juan Pablo conectarse desde Utah al equipo en Bogotá (o donde sea) sin exponer puertos a internet.

```bash
# En el equipo recién instalado (el técnico en Bogotá hace esto):
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=tskey-auth-kyZGeYx3Cf11CNTRL-Zd43XEfKRpEEjMSo9gyhoEDcowpZBvks --ssh
```

Cuando terminen los dos comandos: Juan Pablo ve el equipo en tailscale.com y puede tomar control.

**Equipos ya en Tailscale:**
| Nombre | IP Tailscale | Equipo |
|--------|-------------|--------|
| `usb-shomer` | `100.100.188.87` | Lab .205 — servidor principal |
| `jpad` | `100.119.205.86` | PC Utah de Juan Pablo |

## 7.5 Paso 4 — Transferir el paquete Shomer

Desde el lab `.205` (Juan Pablo lo hace remotamente):

```bash
# Conectarse al lab y generar el paquete
ssh usb_admin@usb-shomer
cd /opt/network_monitor
bash tools/make_package.sh
# Genera: /tmp/shomer-YYYYMMDD.tar.gz

# Enviarlo al equipo nuevo (ambos deben estar en Tailscale)
scp /tmp/shomer-YYYYMMDD.tar.gz usb_admin@[nombre-equipo-bogota]:/home/usb_admin/
```

## 7.6 Paso 5 — Ejecutar el instalador

```bash
# Conectarse al equipo nuevo
ssh usb_admin@[nombre-equipo-bogota]

# Abrir tmux (protege la sesión si cae el SSH)
tmux new -s install

# Ver las NICs del equipo
ip -br link show
# La que tiene IP → NIC de gestión
# La que está DOWN → NIC espejo

# Descomprimir y ejecutar
cd /home/usb_admin
tar -xzf shomer-*.tar.gz
cd shomer-*/

# Instalación completa con Wazuh
sudo INSTALL_WAZUH=yes \
     MGMT_IFACE=enp2s0 \
     MIRROR_IFACE=enp3s0 \
     bash tools/install_shomer.sh
```

El instalador tarda ~15 minutos. Si el SSH se cae: `ssh usb_admin@equipo` → `tmux attach -t install`

**Qué hace el instalador automáticamente:**
- Instala Python 3.10, nginx, Redis, Restic, nmap, Suricata, Docker y dependencias
- Crea la estructura de carpetas (`/storage/db/`, `/srv/shomer_backups/`, etc.)
- Copia el código Shomer a `/opt/network_monitor/`
- Crea el entorno virtual Python con todas las dependencias
- Genera el certificado SSL auto-firmado (válido 10 años)
- Configura nginx (puerto 80 → redirige a 8443)
- Genera el JWT secret automáticamente
- Instala y habilita todos los servicios systemd
- Inicia los servicios

Al terminar muestra:
```
Panel (HTTPS): https://IP-DEL-EQUIPO:8443/setup/
Credenciales iniciales: root / shomer2026
```

## 7.7 Paso 6 — Completar el wizard de configuración

Abrir en el navegador: `https://[IP-del-equipo]:8443/setup/`  
Login: `root` / `shomer2026`

El sistema redirige automáticamente al wizard cuando se usa la contraseña de fábrica.

**Completar en orden:**

| Sección | Qué configurar |
|---------|---------------|
| **Identificación del sitio** | Nombre del cliente (ej. `Hotel Plaza Bogotá`), zona horaria (`America/Bogota`) |
| **Telegram** | Token del bot (lo entrega USB Ingeniería) + Chat ID del técnico |
| **Red de gestión** | IP fija del Shomer en la red del cliente |
| **Guardian** | IPs de los APs a monitorear |
| **Hunter** | IP del firewall OpenWrt, credenciales SSH |
| **Protector** | Usuario de servicio, rutas, B2 bucket + slug del cliente |

## 7.8 Paso 7 — Configurar el bot Telegram

```bash
# Copiar el archivo de variables de entorno
sudo cp /storage/shomer-agent/.env.example /storage/shomer-agent/.env

# Editar con los datos del cliente
sudo nano /storage/shomer-agent/.env
# Completar: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY, SITE_NAME, SHOMER_PASS

# Iniciar el bot
sudo systemctl enable --now shomer-agent
```

## 7.9 Paso 8 — Verificación final

```bash
# Estado de todos los servicios
systemctl is-active shomer-guardian shomer-tools nginx redis-server shomer-agent
# Todos deben decir: active

# Desde Telegram: verificar instalación completa
/verificar
```

El comando `/verificar` en el bot devuelve un reporte con 10 ítems. Cuando todos están en verde, la instalación está completa.

---

# PARTE 8 — ACCESO REMOTO (TAILSCALE Y VPN)

## 8.1 Tailscale — para el equipo USB Ingeniería

**¿Qué es?** Una VPN que conecta todos los equipos de USB Ingeniería y los servidores de clientes en una red privada, sin configurar routers ni abrir puertos.

**¿Para qué sirve?** Juan Pablo puede conectarse desde Utah a cualquier equipo de cliente (Bogotá, donde sea) como si estuviera en la misma habitación. Cursor/Claude Code también puede conectarse y editar código, ver logs, reiniciar servicios.

**Llave de autenticación (para conectar nuevos equipos):**
```bash
sudo tailscale up --authkey=tskey-auth-kyZGeYx3Cf11CNTRL-Zd43XEfKRpEEjMSo9gyhoEDcowpZBvks --ssh
```
⚠️ Esta llave expira cada 90 días. Renovar en: tailscale.com/admin/settings/keys

**Comandos útiles:**
```bash
tailscale status            # Ver todos los equipos conectados
tailscale ip                # Ver mi IP en Tailscale
tailscale ssh usb_admin@nombre-equipo   # SSH directo via Tailscale
```

## 8.2 WireGuard — para el técnico del cliente

WireGuard es la VPN que permite al técnico del cliente conectarse remotamente al servidor de su hotel cuando no está en el sitio.

**Está configurado en el router OpenWrt del cliente.** El técnico recibe un archivo `.conf` que importa en la app WireGuard de su laptop.

**Para agregar un técnico nuevo:** avisar a ingeniería — es una operación de 5 minutos.

**Para producción:** el router OpenWrt debe tener IP pública (o el router del ISP debe hacer port-forward del puerto UDP 51820 hacia el OpenWrt).

---

# PARTE 9 — OPERACIÓN DIARIA

## 9.1 Verificaciones rápidas de rutina

```bash
# Estado de todos los servicios
systemctl is-active shomer-guardian shomer-tools nginx redis-server suricata

# Ver logs recientes (si hay problema)
tail -n 20 /var/log/shomer/api.log

# Uso de disco
df -h

# Desde Telegram: resumen con IA
/resumen
```

## 9.2 Modo mantenimiento — SIEMPRE activar antes de trabajar en el sitio

Si vas a desconectar cables, hacer cambios en el switch o cualquier trabajo que baje equipos:

**Activar:** `/mantenimiento` en el bot → botón activar  
**Desactivar:** lo mismo al terminar

Con mantenimiento activo, Guardian no reinicia nada automáticamente.

## 9.3 Actualizaciones del sistema

Las actualizaciones **no son automáticas**. Cada actualización se coordina con Juan Pablo:
1. Juan Pablo valida en el lab `.205` primero
2. Notifica al técnico la ventana de tiempo (madrugada o fin de semana)
3. Envía el comando exacto por canal seguro
4. El técnico activa modo mantenimiento, ejecuta el comando, verifica con `/verificar`

## 9.4 Qué escalar a ingeniería (no intentar solo)

| Situación |
|-----------|
| El Shomer no arranca después de un reinicio |
| Contraseñas correctas no funcionan en el panel |
| Se perdió acceso SSH |
| Error de base de datos |
| Disco al 100% y el bot no responde |
| Cambiar IP del Shomer en la red del cliente |

---

# PARTE 10 — SEGURIDAD DEL SISTEMA

## 10.1 Configuración de seguridad estándar

| Elemento | Configuración |
|---------|--------------|
| HTTPS | Certificado SSL auto-firmado — 10 años (válido para red privada) |
| JWT Secret | Generado automáticamente durante instalación — en `/etc/shomer/shomer-runtime.env` |
| Puerto 8001 | Solo accesible desde localhost — no expuesto al exterior |
| UFW | Solo puertos 22 (SSH), 80 (redirect), 8443 (panel) desde la red del cliente |
| Contraseñas | Nunca en texto plano en el código — siempre en BD o archivos con permisos restrictivos |

## 10.2 Rotar el JWT Secret (post-instalación)

```bash
# Generar nuevo secret
NEW_SECRET=$(openssl rand -hex 32)

# Reemplazar en el archivo de configuración
sudo sed -i "s/JWT_SECRET=.*/JWT_SECRET=${NEW_SECRET}/" /etc/shomer/shomer-runtime.env

# Reiniciar servicios (esto cierra todas las sesiones activas)
sudo systemctl restart shomer-guardian shomer-tools
```

## 10.3 Cambiar contraseña del admin

Desde el panel: **Configuración → Usuarios → Cambiar contraseña**

O desde línea de comandos:
```bash
sqlite3 /storage/db/network_monitor.db \
  "UPDATE users SET password_hash=lower(hex(randomblob(32))) WHERE username='admin';"
# Luego usar el panel para poner la contraseña correcta
```

---

# PARTE 11 — BASE DE DATOS Y CONFIGURACIÓN

## 11.1 Dónde vive la configuración del sistema

Toda la configuración del sistema vive en la tabla `system_state` de `/storage/db/network_monitor.db`. Es una tabla clave-valor simple:

```sql
-- Ver toda la configuración
sqlite3 /storage/db/network_monitor.db "SELECT key, value FROM system_state ORDER BY key;"

-- Ver solo configuración de Guardian
sqlite3 /storage/db/network_monitor.db "SELECT key, value FROM system_state WHERE key LIKE 'guardian.%';"
```

**Prefijos de configuración:**

| Prefijo | Módulo |
|---------|--------|
| `base.*` | Configuración general del sitio (nombre, timezone, IP, usuario de servicio) |
| `guardian.*` | Guardian (Telegram, intervalos, thresholds de reboot) |
| `hunter.*` | Hunter (firewall IP/credenciales, auto_block, subredes) |
| `tracker.*` | Tracker (rangos de red, credenciales) |
| `protector.*` | Protector (B2, rutas, usuario de servicio) |
| `modules.enabled.*` | Qué módulos están activos |

## 11.2 Configuraciones críticas a verificar en cada instalación nueva

```bash
sqlite3 /storage/db/network_monitor.db "
SELECT key, value FROM system_state
WHERE key IN (
  'base.site_name',
  'base.timezone',
  'base.service_user',
  'guardian.telegram_chat_id',
  'hunter.firewall_ip',
  'hunter.auto_block_exceptions',
  'hunter.subnets',
  'protector.b2_bucket',
  'protector.b2_path'
);"
```

---

# PARTE 12 — TROUBLESHOOTING RÁPIDO

## El panel no carga
```bash
# Verificar servicios
systemctl is-active shomer-guardian nginx
# Si alguno está caído:
sudo systemctl restart shomer-guardian
sudo systemctl restart nginx
# Si el puerto está ocupado (proceso zombie):
sudo lsof -ti:8000 | xargs sudo kill -9
sudo systemctl start shomer-guardian
```

## Un servicio no arranca
```bash
# Ver por qué falló
journalctl -u shomer-guardian -n 50
# Errores comunes:
# "Address already in use" → proceso zombie en el puerto
# "ModuleNotFoundError" → falta dependencia Python
# "PermissionError" → permisos en carpetas de logs o DB
```

## El bot Telegram no responde
```bash
# Ver logs del bot
sudo docker compose -f /storage/shomer-agent/docker-compose.yml logs --tail=50
# Reiniciar
sudo systemctl restart shomer-agent
```

## Guardian no reinicia un AP
- Verificar credenciales SSH (o SNMP para EAPs) en el panel
- Para APs OpenWrt/GL.iNet: la llave SSH del Shomer debe estar en el AP
- Para EAPs TP-Link: SNMP debe estar activo con la IP del Shomer en la lista permitida

## Disco lleno
```bash
# Ver qué está ocupando espacio
df -h
du -sh /var/log/suricata/
du -sh /var/log/shomer/

# Limpiar logs Suricata (truncar sin cerrar el proceso)
sudo truncate -s 0 /var/log/suricata/eve.json
sudo truncate -s 0 /var/log/suricata/fast.log

# Limpiar journal del sistema
sudo journalctl --vacuum-time=7d

# El bot también puede limpiar automáticamente desde /salud → opción de limpieza
```

## Proceso zombie en puerto 8000 o 8001
```bash
sudo systemctl stop shomer-guardian
sudo lsof -ti:8000 | xargs sudo kill -9
sleep 2
sudo systemctl start shomer-guardian
```

---

# PARTE 13 — REFERENCIA RÁPIDA DE ARCHIVOS

| Qué necesitas | Dónde está |
|--------------|-----------|
| **Código principal** | `/opt/network_monitor/app/` |
| **Base de datos principal** | `/storage/db/network_monitor.db` |
| **Base de datos inventario** | `/storage/db/inventory.db` |
| **Logs del sistema** | `/var/log/shomer/api.log` |
| **Logs de Tools** | `/var/log/shomer/tools_api.log` |
| **JWT Secret y variables** | `/etc/shomer/shomer-runtime.env` |
| **Contraseña Restic** | `/home/usb_admin/.restic-local-pass` |
| **Backups locales** | `/srv/shomer_backups/staging/` |
| **Restauraciones** | `/srv/shomer_restore/` |
| **Bot Telegram** | `/storage/shomer-agent/` |
| **Variables del bot** | `/storage/shomer-agent/.env` |
| **Datos del bot** | `/storage/shomer-agent/data/` |
| **Servicios systemd** | `/etc/systemd/system/shomer-*.service` |
| **Nginx config** | `/etc/nginx/sites-available/network-monitor` |
| **Script instalación** | `/opt/network_monitor/tools/install_shomer.sh` |
| **Script fábrica/red** | `/opt/network_monitor/tools/factory_reset_network.sh` |

---

# PARTE 14 — DOCUMENTOS RELACIONADOS

| Documento | Para qué |
|-----------|---------|
| `SOPORTE_TECNICO.md` | Manual operativo para técnico de campo — instalación paso a paso, módulos en detalle, hoja de datos del sitio |
| `Instalacion_Remota_Tailscale.md` | Cómo hacer una instalación remota desde Utah — flujo completo con Tailscale |
| `Instalacion_Ubuntu_USB_Particiones.md` | Crear USB booteable + particionado para SSD 256 GB |
| `Anexo_MikroTik_TFTP_OpenWrt.md` | Detalle de configuración MikroTik/OpenWrt — TFTP, flash, rutas |
| `CLAUDE.md` | Manifiesto de desarrollo interno — historial de sesiones, bugs corregidos, arquitectura detallada |
| `SISTEMA_SHOMER.md` | Guía técnica del producto para ingeniería L2/L3 |

---

# PARTE 15 — HOJA DE DATOS DEL SITIO

Completar antes de cada instalación:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOJA DE DATOS — INSTALACIÓN SHOMER SENTINEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CLIENTE
Nombre / empresa: ________________________________
Nombre del sitio (para alertas): ________________________________
Ciudad / País: ________________________________
Fecha de instalación: ________________________________
Técnico responsable: ________________________________

RED
Subred LAN (ej. 192.168.1.0/24): ________________
Gateway principal: ________________
IP asignada al Shomer: ________________
IP del MikroTik/firewall (LAN): ________________
Zona horaria: ________________
  (America/Bogota, America/Lima, America/Mexico_City, America/New_York)

FIREWALL / HUNTER
IP del firewall que Hunter controla: ________________
Usuario SSH del router: ________________
Puerto SSH (normalmente 22): ________________

APs / ROUTERS A MONITOREAR (Guardian)
Equipo 1: Nombre _______________ IP _______________ Tipo ___________
Equipo 2: Nombre _______________ IP _______________ Tipo ___________
Equipo 3: Nombre _______________ IP _______________ Tipo ___________

BACKUPS (Protector)
¿Backups en nube B2?: Sí / No
Slug B2 del cliente (entrega ingeniería): ________________
Equipo 1: Nombre _______________ IP _______________ OS _____________
Equipo 2: Nombre _______________ IP _______________ OS _____________

TELEGRAM
Chat ID para alertas: ________________
Bot configurado: Sí / No

NOTAS ESPECIALES
________________________________________________________
________________________________________________________
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

*USB Ingeniería SAS — Shomer Sentinel 2.0*  
*Compendio completo del sistema — versión mayo 2026*  
*Para uso interno del equipo: Juan Pablo Cero, Andrés, Laura*
