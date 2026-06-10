# Shomer Sentinel — Equipos registrados

Documento maestro: qué tiene cada appliance y qué configuración es **específica del sitio** (no copiar entre clientes).

**Última actualización:** 10 jun 2026

---

## Resumen rápido

| Equipo | Hostname | Tailscale | LAN | Rol | `SITE.md` |
|--------|----------|-----------|-----|-----|-----------|
| Lab principal | `USB-SHOMER` | `100.100.188.87` | `192.168.1.205` | Desarrollo + hardware físico | `/opt/network_monitor/SITE.md` |
| Hotel Ópera | `shomer-hotelopera` | `100.103.148.119` | `192.168.10.206` | **Producción** Bogotá | `/opt/network_monitor/SITE.md` (en el servidor) |
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
| **NO copiar a clientes** | IPs lab, `SHOMER_LAB_NO_SPAN`, credenciales `.206` |

### 2. shomer-hotelopera — Producción (Hotel Ópera)

| Área | Configuración |
|------|----------------|
| **NIC gestión** | `eno1` → `192.168.10.206/24` (red admin hotel) |
| **NIC espejo Hunter** | `enx9c69d33bc55f` (USB) — **SPAN activo**, EVE con tráfico real |
| **Suricata** | Symlink ET `/etc/suricata/rules/suricata.rules` → `/var/lib/...`; `shomer-local` mínimo (ICMP test desactivado) |
| **Pipeline** | **Sin** `SHOMER_LAB_NO_SPAN` — EVE quieto = alerta real |
| **Hunter firewall** | MikroTik RouterOS `192.168.0.1` (`hunter.firewall_type=routeros`) |
| **Hunter subnets** | 5 VLANs hotel (admin, huéspedes, eventos, WiFi admin, telefonía) — ver `SITE.md` |
| **`auto_block_enabled`** | **`false`** — preventivo; bloqueo manual/Wazuh |
| **Tracker** | **76** activos; credencial AD `administrador` / dominio `HOTELOPERA` |
| **Inframonitor** | **23** equipos (switches, POS, impresoras, cámaras…) |
| **Guardian** | **30** APs `192.168.0.x` — estado vivo en Redis; BD puede mostrar `unknown` |
| **Bot** | Agente Docker activo; `.env` propio del sitio |
| **Cuidado deploy** | No `deploy.sh` masivo sin ventana; no tocar BD ni `SITE.md` desde lab |

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

# SSH
ssh -i ~/.ssh/id_rsa_shomer usb_admin@100.103.148.119      # Ópera
ssh -i ~/.ssh/id_ed25519_shomer usb_admin@100.75.182.116   # .245
```
