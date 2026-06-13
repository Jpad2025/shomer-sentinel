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

## Tracker / Guardian / Infra
- Hardware físico conectado (APs `.210`, `.253`, `.254`, Kali `.203`, etc.)
- Ver inventario real en panel — no usar IPs de este archivo en otros sitios

## Historial incidentes y retención (jun 2026)
- **Estado del Sistema** → tabla *Incidentes de red (48 h)* + export CSV
- Retención configurable (días) — poda automática horaria de `status_events`, `infra_events`, `event_log`
- Defaults: historial 90 d / logs BD 30 d / poda agresiva si disco ≥ 85 %
- Código: `app/api/shomer_status_events.py`
- **Último deploy código:** 13 jun 2026 (lab local — no rsync a sí mismo)

## Modo mantenimiento Guardian
- Panel **Guardian** → botón 🔧, o bot Telegram `/modo on|off` (`/mantenimiento`)
- Al activar/desactivar → **Telegram** al chat del técnico (fix 13 jun 2026)
- Pausa reboots automáticos; monitoreo sigue activo
- **Antes de deploy/reinicio de servicios:** activar mantenimiento en producción

## Bot
- Desarrollo activo en `/storage/shomer-agent/` (no afecta otros servidores)

## No aplicar en clientes
- IPs, credenciales y `SHOMER_LAB_NO_SPAN` de este archivo
