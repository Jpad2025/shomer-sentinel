# Shomer Sentinel — Equipos registrados

Documento maestro: qué tiene cada appliance y qué configuración es **específica del sitio** (no copiar entre clientes).

**Última actualización:** 23 jun 2026 (Sesión 61 — auditoría EN VIVO de los 4 servidores vía SSH directo, no desde notas de sesiones pasadas).

> **REGLA CRÍTICA:** Deploy o cambios remotos en **producción** (Ópera) **solo con autorización de Juan Pablo**. Deploy = **solo código** de la aplicación; **nunca** BD, `SITE.md`, credenciales ni config del sitio. Ver **`docs/REGLAS_DEPLOY.md`**.

> **REGLA DE VERIFICACIÓN (nueva, 23 jun 2026 — causa de fondo de errores recientes):** Las tablas "Por equipo" de abajo describen el estado la última vez que alguien lo comprobó **en vivo por SSH**, no un estado permanente. Antes de afirmarle a Juan Pablo que algo "falta", "está pendiente" o "necesita instalarse" en cualquier servidor, **volver a comprobar primero** — este documento puede estar desactualizado. Verificación rápida (servicios + si el contenedor del bot existe/corre):
> ```bash
> ssh -i ~/.ssh/id_rsa_shomer     usb_admin@100.103.148.119 "systemctl is-active shomer-guardian shomer-tools nginx; sudo docker ps -a --filter name=shomer-agent --format '{{.Status}}'"  # Ópera
> ssh -i ~/.ssh/id_ed25519_shomer usb_admin@100.75.182.116  "systemctl is-active shomer-guardian shomer-tools nginx; sudo docker ps -a --filter name=shomer-agent --format '{{.Status}}'"  # 245
> ssh -i ~/.ssh/id_ed25519_shomer usb_admin@100.108.17.50   "systemctl is-active shomer-guardian shomer-tools nginx; sudo docker ps -a --filter name=shomer-agent --format '{{.Status}}'"  # 243
> ```
> **Cómo se detectó la falla:** este archivo decía "Bot — Código sync 16/jun; `.env` pendiente si se usa" para los mini PCs. Eso ya era falso desde el 10 jun (el `.env` estaba configurado). Se repitió como hecho actual el 23 jun sin verificar primero — corregido en esta sesión con SSH directo.

---

## Seguro Hunter — autobloqueo (16 jun 2026)

**Dos formas de encender/apagar** (mismo interruptor en BD `hunter.auto_block_enabled`):

| # | Canal | Acción |
|---|--------|--------|
| **1** | **Panel** | Botón **Seguro ON/OFF** (header) **o** Config → checkbox *Habilitado* → Guardar |
| **2** | **Telegram** | `/seguro on` · `/seguro off` · `/seguro` (estado) |

**Desactivar si pasa algo:** cualquiera de las dos vías arriba + `/liberar` o `/desbloquear IP` para una IP puntual. Al cambiar estado → mensaje guía al chat técnico.

**Telegram sonidos:** solo **con sonido** (normal) o **silencioso** por mensaje — no hay tonos distintos por tipo desde el bot; el técnico elige un sonido por chat en la app.

---

## Deploy código — dos modos (16 jun 2026)

| Modo | Comando |
|------|---------|
| **Todos lab** (243+245+205; sin Ópera) | `cd /opt/network_monitor && bash tools/deploy.sh` |
| **Un equipo** | `bash tools/deploy.sh 100.75.182.116` (245) · `100.108.17.50` (243) · `100.100.188.87` (205) |
| **Incluir Ópera** | `SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh` |

Copia: `app/` + agente (sin `.env`/`data/`). **Nunca** BD ni `SITE.md`.

---

## Resumen rápido

| Equipo | Hostname | Tailscale | LAN | Rol | `SITE.md` |
|--------|----------|-----------|-----|-----|-----------|
| Lab principal | `USB-SHOMER` | `100.100.188.87` | `192.168.1.205` | Desarrollo + hardware físico | `/opt/network_monitor/SITE.md` |
| Hotel Ópera | `shomer-hotelopera` | `100.103.148.119` | `192.168.0.250` | **Producción** Bogotá | `/opt/network_monitor/SITE.md` (en el servidor) |
| Mini PC 1 | `usbadmin4` | `100.75.182.116` | `192.168.1.245` | Lab Utah N100 | `/opt/network_monitor/SITE.md` |
| Mini PC 2 | `usbadmin3` | `100.108.17.50` | `192.168.1.243` | Lab Utah N95 | `/opt/network_monitor/SITE.md` |

Registro deploy: `tools/servers.txt`

---

## Por equipo — qué requiere cada uno

### 1. USB-SHOMER — Lab principal (`.205`)

| Área | Configuración |
|------|----------------|
| **NIC gestión** | `enp2s0` → `192.168.1.205/24` |
| **NIC espejo Hunter** | `enp4s0` — SPAN del lab cuando hay cable; **sin SPAN es normal** |
| **Suricata** | Interfaz `enp4s0`; symlink `shomer-local.rules`; ruleset ET en `/var/lib/suricata/rules/` |
| **Pipeline lab** | `SHOMER_LAB_NO_SPAN=1` en `/etc/shomer/shomer-runtime.env` |
| **Hunter firewall** | OpenWrt `192.168.1.206` (lab) |
| **Hunter subnets** | `192.168.1.0/24` |
| **Tracker** | ~7 activos lab; credenciales lab |
| **Inframonitor** | ~2 equipos prueba |
| **Guardian** | 3 APs (`.210`, `.253`, `.254`) |
| **Pantalla S1** | Ver sección en `/opt/network_monitor/SITE.md` — etiqueta `shomer205`, GUI `http://192.168.1.205:8686`, LED ❌ hardware |
| **Bot Telegram** | `/storage/shomer-agent/` — contenedor **corriendo** (`docker ps` ✅, "Up 2 days" verificado 23/jun), aunque sin hardware físico conectado ahora |
| **Último deploy** | 23 jun 2026 — commits locales (origen del código; no rsync a sí mismo) |
| **Historial incidentes** | `status_events` + retención — ver `/system-status` (jun 2026) |
| **Mantenimiento global** | Telegram al activar/desactivar (panel o bot) — `shomer_guardian_events.py` |
| **NO copiar a clientes** | IPs lab, `SHOMER_LAB_NO_SPAN`, credenciales `.206` |

### 2. shomer-hotelopera — Producción (Hotel Ópera)

| Área | Configuración |
|------|----------------|
| **NIC gestión** | `eno1` → `192.168.0.250/24` (red admin hotel `192.168.0.0/24`, gateway `192.168.0.1`) |
| **Panel LAN** | `https://192.168.0.250:8443` |
| **Panel Tailscale** | `https://100.103.148.119:8443` |
| **NIC espejo Hunter** | `enx9c69d33bc55f` (USB) — **SPAN activo**, EVE con tráfico real |
| **Suricata** | Symlink ET `/etc/suricata/rules/suricata.rules` → `/var/lib/...`; `shomer-local` mínimo (ICMP test desactivado) |
| **Pipeline** | **Sin** `SHOMER_LAB_NO_SPAN` — EVE quieto = alerta real |
| **Hunter firewall** | MikroTik RouterOS `192.168.0.1` (`hunter.firewall_type=routeros`) |
| **Regla DROP MikroTik** | Obligatoria en `forward` para `shomer-blocked` — aplicada manual 10/jun; verificar en panel Hunter → *Verificar regla DROP* |
| **`routeros_auto_drop_enabled`** | **`false`** — no aplicar DROP automático desde panel (solo manual en producción) |
| **IP bloqueada activa** | `190.60.195.10` (`firewall_blocked=1`) |
| **Hunter subnets** | 5 VLANs hotel (admin, huéspedes, eventos, WiFi admin, telefonía) — ver `SITE.md` |
| **`auto_block_enabled`** | **`true`** — Seguro Hunter activo; excepciones WAN/operadores en `hunter.auto_block_exceptions` (19/jun) |
| **Excepciones Hunter** | `190.60.195.10` (WAN), `190.13.110.0/23` (Movistar), IPs operador CO IKEv2 — ver `SITE.md` Ópera |
| **Tracker** | **76** activos; credencial AD `administrador` / dominio `HOTELOPERA` |
| **Inframonitor** | **23** equipos (switches, POS, impresoras, cámaras…) |
| **Guardian** | **30** APs `192.168.0.x` — estado vivo en Redis; BD puede mostrar `unknown` |
| **Bot** | Contenedor **corriendo** (verificado 23/jun: "Up 3h", reiniciado automáticamente por `deploy.sh` justo después de sincronizar código nuevo); `/seguro` autobloqueo; anti-spam Hunter desplegado 11/jun. **Sigue fuera del grupo de Telegram del hotel — decisión permanente de Juan Pablo (ruido/credibilidad con socios), no se debe re-agregar.** El bot sí envía a `AGENT_DEVELOPER_CHAT_ID` desde el fix del 23/jun (antes solo intentaba el grupo y se perdía todo) |
| **Historial incidentes** | Deploy 13/jun — `status_events`, oleadas en `/system-status`, retención BD automática |
| **Incidente 12/jun** | ~22:53 Bogotá — ~52 equipos offline ~38 s (microcorte red admin probable); pre-deploy solo Telegram/`infra_events` |
| **Mantenimiento global** | Panel Guardian o bot `/modo` — **Telegram al activar/desactivar** (fix 13/jun). Activar **antes de deploy** en producción |
| **Runtime / acceso** | `/etc/shomer/shomer-runtime.env`; panel `:8443`; 443→8443 redirect nginx |
| **Cuidado deploy** | No `deploy.sh` masivo sin ventana; no tocar BD ni `SITE.md` desde lab (excepto actualización documentada del sitio) |

### 3. shomer245 — Mini PC lab (N100)

| Área | Configuración |
|------|----------------|
| **NIC gestión** | `enp4s0` → `192.168.1.245/24` |
| **NIC espejo** | `enp2s0` — sin cable SPAN habitualmente (**DOWN**) |
| **Suricata** | `tools/suricata_lab_setup.sh` con `MIRROR_IFACE=enp2s0` |
| **Pipeline lab** | `SHOMER_LAB_NO_SPAN=1` |
| **Hunter firewall** | Vacío (sin firewall lab dedicado) |
| **Pantalla S1** | Ver `docs/SITE-shomer245.md` (copia en servidor: `/opt/network_monitor/SITE.md`) — GUI `http://192.168.1.245:8686`, LED ✅ |
| **Tracker / Infra** | Vacío — listo para pruebas |
| **Wazuh** | No instalado (opcional en lab) |
| **Bot** | Código sincronizado 23/jun (igual que .205/Ópera, mismos bytes verificados). **`.env` SÍ está configurado** (3450 bytes, desde 10/jun — token, chat ID, Groq/OpenAI reales) — esto NO está "pendiente", quedó documentado mal antes. Imagen Docker construida (`shomer-agent:latest`, 391MB, hace 13 días) pero **el contenedor nunca se ha creado/iniciado** (`docker ps -a` no muestra ni siquiera uno detenido) — falta solo `cd /storage/shomer-agent && sudo docker compose up -d`, no hay que "instalar" nada más |
| **Último deploy** | 23 jun 2026 — `deploy.sh 100.75.182.116` (verificado por tamaño/fecha de archivo idéntico a `.205`) |
| **Historial incidentes** | Deploy 16/jun — Seguro Hunter panel+Telegram |

### 4. shomer243 — Mini PC lab (N95)

Igual que shomer245 salvo IP `192.168.1.243`, hostname `usbadmin3`, etiqueta pantalla `shomer243`, GUI `http://192.168.1.243:8686`. **Último deploy:** 23 jun 2026 — `deploy.sh 100.108.17.50` (verificado). **Bot:** mismo estado que shomer245 — `.env` configurado desde 10/jun, imagen construida, contenedor sin iniciar. Detalle: `docs/SITE-shomer243.md` → `/opt/network_monitor/SITE.md` en el servidor.

---

## Código vs datos (regla de oro)

| Tipo | Sincronizar con `deploy.sh` | Copiar entre sitios |
|------|----------------------------|---------------------|
| Código `app/` | ✅ Sí | ✅ Lab → mini PCs |
| Agente `/storage/shomer-agent/` (sin `.env`) | ✅ Sí | Con cuidado |
| BD `network_monitor.db` / `inventory.db` | ❌ Nunca rsync | ❌ Cada hotel |
| `SITE.md`, subnets, credenciales | ❌ Manual por sitio | ❌ |
| `SHOMER_LAB_NO_SPAN` | Solo lab | ❌ Nunca en Ópera |
| `suricata.yaml` (interfaz) | Script `suricata_lab_setup.sh` | Por NIC de cada chasis |

---

## Suricata — checklist por sitio nuevo

```bash
# En el servidor (ajustar MIRROR_IFACE):
cd /opt/network_monitor
sudo MIRROR_IFACE=enp2s0 bash tools/suricata_lab_setup.sh   # mini PCs
sudo MIRROR_IFACE=enp4s0 bash tools/suricata_lab_setup.sh   # .205

# Verificar:
sudo suricata -T -c /etc/suricata/suricata.yaml -v 2>&1 | grep 'successfully loaded'
systemctl is-active suricata
```

**Producción con SPAN:** no usar `SHOMER_LAB_NO_SPAN`. Verificar conteo de reglas ET (no solo 1 regla) — §AJ en `CLAUDE.md`.

---

## Bot Telegram (separado del panel)

- Ruta: `/storage/shomer-agent/`
- Desarrollo habitual: **solo `.205`**
- No tumba el panel ni Ópera si se reinicia el container
- Cada sitio: su `.env` (token, chat ID, Groq/OpenAI)
- Deploy copia código; **no** copia `.env` ni `data/`

---

## Comandos útiles

```bash
# Desde lab .205 — origen del código en /opt/network_monitor

# Solo mini PCs (recomendado día a día):
bash tools/deploy.sh 100.75.182.116   # shomer245
bash tools/deploy.sh 100.108.17.50    # shomer243
bash tools/deploy.sh 100.100.188.87   # .205 (reinicia servicios + agente local)

# Todos los servidores de lab (243 + 245 + 205); Ópera se OMITE sin autorización:
bash tools/deploy.sh

# Ópera (producción — requiere autorización JP):
SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh 100.103.148.119

# Lab + Ópera en un solo comando (solo con autorización):
SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh
```

**Qué copia `deploy.sh`:** `app/` + agente (`/storage/shomer-agent/` sin `.env`/`data/`) + units frontpanel. **Nunca** BD ni `SITE.md`.

**Hunter — Seguro autobloqueo:** panel → botón **Seguro ON/OFF** (header) o Config → checkbox *Habilitado*; Telegram → `/seguro on|off`. Al cambiar estado llega guía al chat técnico.

```bash
# SSH
ssh -i ~/.ssh/id_rsa_shomer usb_admin@100.103.148.119      # Ópera
ssh -i ~/.ssh/id_ed25519_shomer usb_admin@100.75.182.116   # .245
```
