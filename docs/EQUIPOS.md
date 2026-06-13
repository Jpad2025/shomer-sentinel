# Shomer Sentinel — Equipos registrados

Documento maestro: qué tiene cada appliance y qué configuración es **específica del sitio** (no copiar entre clientes).

**Última actualización:** 13 jun 2026 (Sesión 55 — Telegram mantenimiento global)

> **REGLA CRÍTICA:** Deploy o cambios remotos en **producción** (Ópera) **solo con autorización de Juan Pablo**. Deploy = **solo código** de la aplicación; **nunca** BD, `SITE.md`, credenciales ni config del sitio. Ver **`docs/REGLAS_DEPLOY.md`**.

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
| **Bot Telegram** | `/storage/shomer-agent/` — desarrollo activo aquí |
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
| **`auto_block_enabled`** | **`false`** — preventivo; bloqueo manual/Wazuh |
| **Tracker** | **76** activos; credencial AD `administrador` / dominio `HOTELOPERA` |
| **Inframonitor** | **23** equipos (switches, POS, impresoras, cámaras…) |
| **Guardian** | **30** APs `192.168.0.x` — estado vivo en Redis; BD puede mostrar `unknown` |
| **Bot** | Agente Docker activo; anti-spam Hunter desplegado 11/jun (`watch_active_threats`, `watch_network_audit`) |
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
| **Tracker / Infra** | Vacío — listo para pruebas |
| **Wazuh** | No instalado (opcional en lab) |
| **Bot** | Código sincronizado; `.env` pendiente si se usa |
| **Historial incidentes** | Deploy 13/jun — mismo código que `.205` |

### 4. shomer243 — Mini PC lab (N95)

Igual que shomer245 salvo IP `192.168.1.243` y hostname `usbadmin3`.

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
# Deploy solo mini PCs (no Ópera):
bash tools/deploy.sh 100.75.182.116
bash tools/deploy.sh 100.108.17.50

# Ópera (producción — requiere autorización):
SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh 100.103.148.119

# Todos (Ópera solo si SHOMER_DEPLOY_AUTHORIZED=1):
SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh

# SSH
ssh -i ~/.ssh/id_rsa_shomer usb_admin@100.103.148.119      # Ópera
ssh -i ~/.ssh/id_ed25519_shomer usb_admin@100.75.182.116   # .245
```
