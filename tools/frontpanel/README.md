# Pantalla frontal AceMagic S1 (mini PC)

LCD USB **Holtek `04d9:fd01`**, resolución **320×170** (RGB565). Tira RGB en `/dev/ttyUSB0`.

## Instalación rápida (lab)

En el mini PC con Ubuntu 22.04 y pantalla conectada:

```bash
cd /opt/network_monitor
sudo bash tools/frontpanel/install_shomer_frontpanel.sh shomer245
```

El argumento opcional es la etiqueta centrada en la barra inferior (p. ej. `shomer245`, `shomer243`).

## Qué hace

1. Genera `logo-portrait.png` 170×280: **USB Ingeniería arriba** + **Shomer** debajo (`logo-usb.png` + `shomer-eyes.png`).
2. Instala **s1panel** desde Snap Store (canal `edge`) si no está presente.
3. Conecta permisos USB/hardware/disco del snap.
4. Crea tema `themes/shomer/shomer.json` (**portrait** — orientación nativa del panel, una pantalla fija).
5. Tira RGB: **shomer-led-strip.service** (arcoíris vía `/dev/ttyUSB0`). s1panel usa theme **6** (ignore) para no competir por el puerto serial.
6. Preserva `canvas`, `device` y `led_config` del config original del snap.

**Nota:** no usar `wallpaper` de pantalla en portrait — s1panel no lo rota; el logo va como widget `image`.

## Instalación automática (`install_shomer.sh`)

En mini PCs AceMagic S1 (`lsusb -d 04d9:fd01`), el instalador ejecuta este script tras crear el venv (paso 7b). Omitir con `SKIP_FRONTPANEL=yes`.

## LED arcoíris (`shomer-led-strip.service`)

s1panel en snap a veces abre `/dev/ttyUSB0` sin encender la tira. Shomer controla el LED desde el host:

```bash
sudo systemctl status shomer-led-strip
journalctl -u shomer-led-strip -n 10 --no-pager
```

Prueba manual:

```bash
sudo /opt/network_monitor/venv/bin/python3 -c "
from tools.frontpanel.led_strip import apply_led
apply_led()
"
```

## GUI de configuración

**Importante:** es **HTTP** (no HTTPS). Si pones `https://` el navegador dará error.

| Equipo | LAN | Tailscale |
|--------|-----|-----------|
| .205 | `http://192.168.1.205:8686` | `http://100.100.188.87:8686` |
| shomer245 | `http://192.168.1.245:8686` | `http://100.75.182.116:8686` |
| shomer243 | `http://192.168.1.243:8686` | `http://100.108.17.50:8686` |

UFW debe permitir **8686/tcp** desde tu subred (regla `s1panel GUI LAN`).

Detener/editar manualmente:

```bash
sudo snap stop s1panel
# archivos en /root/snap/s1panel/current/
sudo snap start s1panel
sudo snap logs s1panel -n=30
```

## Verificación hardware

```bash
lsusb | grep -i holtek          # 04d9:fd01
ls -la /dev/ttyUSB0             # tira RGB
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8686/
sudo snap services s1panel      # active
```

## Estado lab (14 jun 2026)

| Equipo | Tailscale | s1panel | Notas |
|--------|-----------|---------|-------|
| shomer245 | 100.75.182.116 | ✅ activo | Opción 1 + 2 + LED strip |
| shomer243 | 100.108.17.50 | ✅ activo | Opción 1 + 2 + LED strip |
| .205 lab | 100.100.188.87 | ✅ activo | LCD ✅ · **LED tira dañada** (jun 2026) |

## Opción 2 — estado Shomer en pantalla (`shomer-frontpanel.service`)

Servicio que cada **30 s** lee Redis (`shomer:wan_status`, claves `status:*` Guardian), regenera `logo-portrait.png` con:

- Nombre del sitio (`base.site_name` en BD)
- **WAN OK** / **SIN INTERNET** / etc.
- **AP 3/3** (online/total)

Si el PNG cambia → `snap restart s1panel` (s1panel cachea la imagen).

### Modo (`system_state`)

| Clave | Valores | Default |
|-------|---------|---------|
| `frontpanel.mode` | `status` · `logo` · `rotate` | `status` |
| `frontpanel.label` | Etiqueta en barra inferior s1panel | hostname |

- **status** — logos + WAN/AP siempre
- **logo** — solo logos USB + Shomer (como opción 1)
- **rotate** — alterna logo / logo+estado cada 45 s

Ejemplo SQL lab:

```sql
INSERT INTO system_state (key, value) VALUES ('frontpanel.mode', 'status')
  ON CONFLICT(key) DO UPDATE SET value='status';
```

### Servicio

```bash
sudo systemctl status shomer-frontpanel
journalctl -u shomer-frontpanel -n 20 --no-pager
```

## Referencias

- [s1panel snap](https://snapcraft.io/s1panel) (canal edge)
- [AceMagic S1 LED/TFT Linux](https://github.com/tjaworski/AceMagic-S1-LED-TFT-Linux)
