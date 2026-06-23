# Shomer Sentinel — Sitio: Lab Utah principal (USB-SHOMER)

## Identificación
- Nombre: Lab USB Ingeniería — Utah
- Hostname: `USB-SHOMER`
- Tailscale: `100.100.188.87`
- LAN: `192.168.1.205/24`
- Fecha referencia: jun 2026

## Acceso panel
- LAN: `https://192.168.1.205:8443`
- Tailscale: `https://100.100.188.87:8443`

## Red
- Subnet: `192.168.1.0/24`
- Gateway: `192.168.1.1` (típico lab)

## Shomer — NICs
| Rol | Interfaz |
|-----|----------|
| Gestión | `enp2s0` |
| Espejo Hunter | `enp4s0` |

## Hunter
- Firewall lab: OpenWrt `192.168.1.206` (iptables)
- Subnets internas: `192.168.1.0/24`
- **Lab sin SPAN:** `SHOMER_LAB_NO_SPAN=1` en `/etc/shomer/shomer-runtime.env`
- Suricata: `sudo MIRROR_IFACE=enp4s0 bash /opt/network_monitor/tools/suricata_lab_setup.sh`
- **Seguro autobloqueo:** panel → botón **Seguro ON/OFF** o Telegram `/seguro on|off` (ver `docs/EQUIPOS.md`)

## Deploy código (16 jun 2026)
- **Todos lab:** `bash tools/deploy.sh` (243+245+205)
- **Un equipo:** `bash tools/deploy.sh 100.100.188.87`
- **.205 local:** restart servicios si no rsync a sí mismo (`shomer-guardian`, `shomer-tools`, `shomer-agent`)

## Tracker / Guardian / Infra
- Hardware físico conectado (APs `.210`, `.253`, `.254`, Kali `.203`, etc.)
- Ver inventario real en panel — no usar IPs de este archivo en otros sitios

## Historial incidentes y retención (jun 2026)
- **Estado del Sistema** → tabla *Incidentes de red (48 h)* + export CSV
- Retención configurable (días) — poda automática horaria de `status_events`, `infra_events`, `event_log`
- Defaults: historial 90 d / logs BD 30 d / poda agresiva si disco ≥ 85 %
- Código: `app/api/shomer_status_events.py`
- **Último deploy código:** 16 jun 2026 (245/243 vía deploy.sh; .205 restart local)

## Modo mantenimiento Guardian
- Panel **Guardian** → botón 🔧, o bot Telegram `/modo on|off` (`/mantenimiento`)
- Al activar/desactivar → **Telegram** al chat del técnico (fix 13 jun 2026)
- Pausa reboots automáticos; monitoreo sigue activo
- **Antes de deploy/reinicio de servicios:** activar mantenimiento en producción

## Bot
- Desarrollo activo en `/storage/shomer-agent/` (no afecta otros servidores)

## Pantalla frontal AceMagic S1 (jun 2026)

Hardware: LCD Holtek `04d9:fd01` (320×170 portrait) + tira RGB CH340 `/dev/ttyUSB0`.

| Item | Valor |
|------|--------|
| Etiqueta en pantalla | `shomer205` |
| GUI s1panel (HTTP, **no HTTPS**) | LAN: `http://192.168.1.205:8686` · Tailscale: `http://100.100.188.87:8686` |
| Panel Shomer | `https://192.168.1.205:8443` |
| UFW | `8686/tcp` desde `192.168.1.0/24`, `10.0.0.0/24` (WiFi lab), `100.64.0.0/10` (Tailscale) |

**Servicios systemd**

| Servicio | Función |
|----------|---------|
| `snap.s1panel.s1panel` | Pantalla + sensores (hora, CPU, temp) |
| `shomer-frontpanel` | Logo + WAN/AP cada 30 s (Redis + BD) |
| `shomer-led-strip` | Arcoíris vía `/dev/ttyUSB0` |

**Tira RGB:** ❌ **hardware dañado** (jun 2026) — conexiones OK; CH340 responde; LCD OK. Servicio `shomer-led-strip` activo por uniformidad con 245/243.

**Mensaje "Disconnection…"** en la pantalla = s1panel caído (sin heartbeat). Recuperar:

```bash
sudo snap restart s1panel
# o
sudo systemctl restart shomer-frontpanel
```

**Reinstalar tema Shomer**

```bash
cd /opt/network_monitor
sudo bash tools/frontpanel/install_shomer_frontpanel.sh shomer205
```

**Verificación**

```bash
systemctl is-active shomer-frontpanel shomer-led-strip
snap services s1panel
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8686/
```

Documentación técnica: `tools/frontpanel/README.md`

## No aplicar en clientes
- IPs, credenciales y `SHOMER_LAB_NO_SPAN` de este archivo
