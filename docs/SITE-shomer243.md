# Shomer Sentinel — Sitio: Lab mini PC N95 (shomer243)

## Identificación
- Nombre: Lab Utah — Mini PC 2
- Hostname: `usbadmin3`
- Tailscale: `100.108.17.50`
- LAN: `192.168.1.243/24`

## Acceso panel
- LAN: `https://192.168.1.243:8443`
- Tailscale: `https://100.108.17.50:8443`

## Shomer — NICs
| Rol | Interfaz |
|-----|----------|
| Gestión | `enp4s0` |
| Espejo Hunter | `enp2s0` (sin cable SPAN habitualmente) |

## Hunter
- Sin firewall dedicado en lab
- `SHOMER_LAB_NO_SPAN=1`
- Suricata: `sudo MIRROR_IFACE=enp2s0 bash /opt/network_monitor/tools/suricata_lab_setup.sh`
- Seguro autobloqueo: panel **Seguro ON/OFF** o Telegram `/seguro` (mismo código que Ópera; en lab suele estar OFF)

## Deploy
- **Último:** 16 jun 2026 — `bash tools/deploy.sh 100.108.17.50`
- **Todos lab:** `bash tools/deploy.sh` desde `.205`

## Pantalla frontal AceMagic S1 (jun 2026)

Hardware: LCD Holtek `04d9:fd01` (320×170 portrait) + tira RGB CH340 `/dev/ttyUSB0`.

| Item | Valor |
|------|--------|
| Etiqueta en pantalla | `shomer243` |
| GUI s1panel (HTTP, **no HTTPS**) | LAN: `http://192.168.1.243:8686` · Tailscale: `http://100.108.17.50:8686` |
| UFW | `8686/tcp` desde `192.168.1.0/24` y `100.64.0.0/10` (Tailscale) — reglas `s1panel GUI LAN` / `Tailscale` |

**Servicios systemd**

| Servicio | Función |
|----------|---------|
| `snap.s1panel.s1panel` | Pantalla + sensores (hora, CPU, temp) |
| `shomer-frontpanel` | Logo + WAN/AP cada 30 s (Redis + BD) |
| `shomer-led-strip` | Arcoíris vía `/dev/ttyUSB0` |

**Tira RGB:** ✅ operativa (jun 2026)

**Mensaje "Disconnection…"** en la pantalla = s1panel caído (sin heartbeat). Recuperar:

```bash
sudo snap stop s1panel
sudo fuser -k 8686/tcp 2>/dev/null; sudo pkill -9 -f 's1panel/main.js' 2>/dev/null
sudo snap start s1panel
sudo systemctl restart shomer-frontpanel shomer-led-strip
```

**Reinstalar tema Shomer**

```bash
cd /opt/network_monitor
sudo bash tools/frontpanel/install_shomer_frontpanel.sh shomer243
```

**Verificación**

```bash
systemctl is-active shomer-frontpanel shomer-led-strip
snap services s1panel
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8686/
lsusb | grep -i holtek    # 04d9:fd01
```

**Modo pantalla** (`system_state`): `frontpanel.mode` = `status` · `logo` · `rotate` (default `status`).

Documentación técnica: `tools/frontpanel/README.md`

## Estado jun 2026
- Código panel sincronizado con .205 / Ópera vía `deploy.sh`
- Inventario e infra vacíos — listo para pruebas
- Bot: código deployado; `.env` pendiente
