# Shomer Sentinel — Sitio: Lab mini PC N100 (shomer245)

## Identificación
- Nombre: Lab Utah — Mini PC 1
- Hostname: `usbadmin4`
- Tailscale: `100.75.182.116`
- LAN: `192.168.1.245/24`

## Shomer — NICs
| Rol | Interfaz |
|-----|----------|
| Gestión | `enp4s0` |
| Espejo Hunter | `enp2s0` (sin cable SPAN habitualmente) |

## Hunter
- Sin firewall dedicado en lab
- `SHOMER_LAB_NO_SPAN=1`
- Suricata: `sudo MIRROR_IFACE=enp2s0 bash /opt/network_monitor/tools/suricata_lab_setup.sh`

## Estado jun 2026
- Código panel sincronizado con .205 / Ópera
- Inventario e infra vacíos — listo para pruebas
- Bot: código deployado; `.env` pendiente
