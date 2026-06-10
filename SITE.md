# Shomer Sentinel — Sitio: Lab Utah principal (USB-SHOMER)

## Identificación
- Nombre: Lab USB Ingeniería — Utah
- Hostname: `USB-SHOMER`
- Tailscale: `100.100.188.87`
- LAN: `192.168.1.205/24`
- Fecha referencia: jun 2026

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

## Bot
- Desarrollo activo en `/storage/shomer-agent/` (no afecta otros servidores)

## No aplicar en clientes
- IPs, credenciales y `SHOMER_LAB_NO_SPAN` de este archivo
