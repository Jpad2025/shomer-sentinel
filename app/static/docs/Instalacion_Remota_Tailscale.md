# Instalación Remota Shomer Sentinel 2.0 — Acceso vía Tailscale

**Última actualización:** 10 junio 2026  
**Aplica a:** Instalaciones en campo donde el técnico no está físicamente presente  
**Probado en:** Core i3 / 16 GB RAM / dual NIC / Ubuntu 22.04

**Registro de equipos:** ver `docs/EQUIPOS.md` y `SITE.md` en cada servidor (config del cliente, no copiar entre hoteles).

---

## Resumen del flujo

```
Bogotá (técnico cliente)          Utah (Juan Pablo)
─────────────────────             ─────────────────
Instala Ubuntu 22.04         →    —
Conecta cable ethernet        →    —
Ejecuta 2 comandos Tailscale  →    Ve el equipo en tailscale.com
                              ←    Se conecta vía SSH
                              ←    Transfiere paquete Shomer
                              ←    Ejecuta instalador
                              ←    Completa wizard en navegador
```

---

## Parte 1 — Configuración única (Juan Pablo, una sola vez)

### 1.1 Cuenta Tailscale

1. Ir a **tailscale.com** → registrarse con Google (`juanpacerodiaz@gmail.com`)
2. ✅ Cuenta activa — `juanpacerodiaz@`

### 1.2 Equipos ya conectados (16 mayo 2026)

| Nombre | IP Tailscale | Equipo |
|--------|-------------|--------|
| `usb-shomer` | `100.100.188.87` | Lab `.205` — servidor Shomer principal |
| `jpad` | `100.119.205.86` | PC Utah — Windows (Juan Pablo) |

### 1.3 Llave de autenticación reutilizable

✅ Generada — guardar en lugar seguro, renovar cada 90 días.

Para conectar cualquier equipo nuevo (Bogotá, futuros clientes):
```bash
sudo tailscale up --authkey=tskey-auth-kyZGeYx3Cf11CNTRL-Zd43XEfKRpEEjMSo9gyhoEDcowpZBvks --ssh
```

> ⚠️ Si la llave expira: **tailscale.com/admin/settings/keys** → Generate auth key → Reusable + Pre-authorized + 90 days.

---

## Parte 2 — Instrucciones para la persona en Bogotá

### Lo que necesitas pedirle

Mandarle este mensaje exacto:

---

**Mensaje para el técnico en campo:**

> Hola, necesito que hagas estos pasos en el PC que me vas a dejar configurar:
>
> **1. Instalar Ubuntu 22.04 LTS**
> - Descarga: ubuntu.com → "Download Ubuntu 22.04 LTS"
> - Durante la instalación:
>   - Nombre de usuario: `usb_admin`
>   - Contraseña: *(la que te indique Juan Pablo por WhatsApp)*
>   - ✅ Marcar "Install OpenSSH server" si lo pregunta
> - Conectar el PC al router con **cable ethernet** (no WiFi)
>
> **2. Cuando Ubuntu esté listo, abrir Terminal y pegar esto:**
>
> ```bash
> curl -fsSL https://tailscale.com/install.sh | sh
> sudo tailscale up --authkey=tskey-auth-XXXXXXXX --ssh
> ```
>
> *(Juan Pablo te manda el authkey completo por WhatsApp)*
>
> **3. Cuando termine, mandarme una foto de la pantalla o decirme "listo"**
>
> No necesitas hacer nada más.

---

### Qué NO necesitas pedirle

- La IP del equipo — Tailscale la maneja
- Configuración del router — no hace falta port-forward
- Nada de red — el instalador de Shomer configura todo

---

## Parte 3 — Flujo del día de instalación (una sola terminal)

Una vez el equipo Bogotá aparece en Tailscale, todo se hace secuencialmente desde una sola terminal.

---

### Paso 1 — Generar el paquete en el lab y enviarlo a Bogotá

```bash
ssh usb_admin@usb-shomer

cd /opt/network_monitor
bash tools/make_package.sh

scp /tmp/shomer-$(date +%Y%m%d).tar.gz usb_admin@nombre-bogota:/home/usb_admin/

exit
```

---

### Paso 2 — Instalar en el equipo Bogotá

```bash
ssh usb_admin@nombre-bogota

tmux new -s install

# Ver las NICs del equipo
ip -br link show
# La que tiene IP → gestión   (ej. enp2s0)
# La que está DOWN → espejo   (ej. enp3s0)

cd /home/usb_admin
tar -xzf shomer-*.tar.gz
cd shomer-*/

sudo INSTALL_WAZUH=yes \
     MGMT_IFACE=enp2s0 \
     MIRROR_IFACE=enp3s0 \
     bash tools/install_shomer.sh
```

Tarda ~15 min. Si el SSH se cae: `ssh usb_admin@nombre-bogota` → `tmux attach -t install`

Al terminar ejecutar:
```bash
sudo touch /etc/cloud/cloud-init.disabled

systemctl is-active shomer-guardian shomer-tools nginx shomer-health-watchdog.timer
# Todos deben decir: active
```

---

### Paso 3 — Completar el wizard desde el navegador

Nginx escucha en todas las interfaces incluyendo Tailscale — abrir directamente en el navegador:

```
https://IP-TAILSCALE-BOGOTA:8443/setup/
```

La IP Tailscale del equipo se ve con:
```bash
tailscale status
```

Credenciales iniciales: `admin / 12345`

Completar el wizard en orden:
1. Nombre del sitio + zona horaria → `America/Bogota`
2. IP definitiva de gestión (coordinar con cliente)
3. Telegram → token bot + chat ID técnico
4. Guardian → IPs de los APs
5. Hunter → IP firewall + credenciales SSH
6. Protector → usuario `shomer`, rutas, B2 bucket + slug cliente

---

## Parte 3b — Detalle de cada paso

### 3.1 Verificar que el equipo aparece en Tailscale

```bash
tailscale status
# Debe aparecer algo como:
# 100.x.x.x  usb-admin-bogota  ...  active
```

### 3.2 Conectarse al equipo

```bash
ssh usb_admin@nombre-equipo
# Si pide contraseña → la que se definió durante Ubuntu install
```

**Primera conexión — activar tmux** (protege si cae el SSH):

```bash
tmux new -s shomer
```

> ⚠️ Todo lo que sigue ejecutarlo dentro de tmux. Si el SSH se cae reconectar con:
> `ssh usb_admin@nombre-equipo` → `tmux attach -t shomer`

### 3.3 Identificar las NICs antes de instalar

```bash
ip -br link show
# Ejemplo:
# lo        UNKNOWN
# enp2s0    UP      192.168.1.x    ← NIC de gestión (cable al switch cliente)
# enp3s0    DOWN                   ← NIC espejo SPAN (cable al puerto mirror del switch)
```

Anotar:
- **NIC gestión** (la que tiene IP): `_________`
- **NIC espejo** (la que va al SPAN): `_________`

### 3.4 Generar el paquete desde el lab

```bash
# SSH al lab desde tu PC o directamente en .205:
ssh usb_admin@usb-shomer   # vía Tailscale desde cualquier lugar

cd /opt/network_monitor
bash tools/make_package.sh
# Genera: /tmp/shomer-YYYYMMDD.tar.gz
```

### 3.5 Transferir el paquete al equipo Bogotá

```bash
# Directo de .205 → Bogotá, ambos en Tailscale:
scp /tmp/shomer-YYYYMMDD.tar.gz usb_admin@nombre-equipo-bogota:/home/usb_admin/
```

### 3.6 Ejecutar el instalador

```bash
# En el equipo Bogotá (dentro de tmux):
cd /home/usb_admin
tar -xzf shomer-*.tar.gz
cd shomer-*/

# Instalación estándar — Wazuh siempre incluido (requiere ~15 min):
sudo INSTALL_WAZUH=yes \
     MGMT_IFACE=enp2s0 \
     MIRROR_IFACE=enp3s0 \
     bash tools/install_shomer.sh
```

> El instalador termina mostrando la URL del panel y las credenciales iniciales.

### 3.7 Verificar servicios

```bash
systemctl is-active shomer-guardian shomer-tools nginx shomer-health-watchdog.timer
# Todos deben decir: active
```

### 3.8 IP de fábrica — antes del wizard

El instalador deja el equipo con una IP fija de fábrica en la NIC de gestión:

| Campo | Valor |
|-------|-------|
| **IP gestión** | `192.168.0.205` |
| **Máscara** | `/24` |
| **Gateway** | `192.168.0.1` |
| **Panel** | `http://192.168.0.205:8000/setup/` |

> La persona en Bogotá debe conectar el equipo a un switch o router en la red `192.168.0.x` para que el wizard sea accesible localmente. La IP definitiva del cliente se configura dentro del wizard.

### 3.9 Acceder al wizard desde Utah

Abrir un túnel SSH para acceder al panel sin exponerlo a internet:

```bash
# En tu PC local (Utah):
ssh -L 8000:127.0.0.1:8000 usb_admin@nombre-equipo-bogota
```

Luego abrir en el navegador: **http://localhost:8000/setup/**

O vía HTTPS:
```bash
ssh -L 8443:127.0.0.1:8443 usb_admin@nombre-equipo-bogota
# → https://localhost:8443/setup/
```

Credenciales iniciales: `admin / 12345`

---

## Parte 4 — Configuración en el wizard

Completar en orden:

| Paso | Qué configurar |
|------|----------------|
| Identificación del sitio | Nombre cliente, zona horaria Colombia = `America/Bogota` |
| Red de gestión | IP fija para la NIC de gestión (coordinar con cliente) |
| Telegram | Token bot + chat ID del técnico cliente |
| Guardian | IP de los APs a monitorear |
| Hunter | IP del firewall, credenciales SSH |
| Protector | Usuario servicio `shomer`, rutas backup, B2 bucket + slug cliente |

---

## Parte 5 — Post-instalación

### Deshabilitar cloud-init (evita pausa en boot)

```bash
sudo touch /etc/cloud/cloud-init.disabled
```

### Cambiar contraseña admin

Desde el panel: **Configuración → Usuarios → Cambiar contraseña**

### Configurar el bot Telegram (shomer-agent)

```bash
sudo cp /storage/shomer-agent/.env.example /storage/shomer-agent/.env
sudo nano /storage/shomer-agent/.env
# Completar: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY, SITE_NAME, SHOMER_PASS
sudo systemctl enable --now shomer-agent
```

### Verificación final

```bash
# Estado completo:
systemctl is-active shomer-guardian shomer-tools nginx shomer-health-watchdog.timer shomer-agent

# Panel accesible desde la red del cliente:
curl -k https://IP_GESTION:8443/health
```

---

## Pendientes para la instalación Bogotá (mayo 2026)

| # | Ítem | Estado |
|---|------|--------|
| 1 | Cuenta Tailscale + llave `tskey-auth-...` generada | ✅ LISTO |
| 2 | Lab `.205` conectado a Tailscale (`usb-shomer`) | ✅ LISTO |
| 3 | PC Utah conectada a Tailscale (`jpad`) | ✅ LISTO |
| 4 | Confirmar IPs de la red en Bogotá (gateway, subnet) | ⏳ PENDIENTE |
| 6 | Definir nombre del bot Telegram para ese cliente | ⏳ PENDIENTE |
| 7 | Coordinar con persona en Bogotá: Ubuntu install + Tailscale | ⏳ PENDIENTE |
| 8 | Ejecutar instalación remota y completar wizard | ⏳ PENDIENTE |
| 9 | Prueba Hunter campo: SPAN real, SID 9009001, autobloqueo | ⏳ PENDIENTE |

---

## Hardware mínimo verificado

| Componente | Mínimo | Recomendado | Lab .205 |
|------------|--------|-------------|----------|
| CPU | N95 / N100 | Core i3+ | Intel N100 |
| RAM | 8 GB (sin Wazuh) | **16 GB** | 16 GB |
| Disco | 128 GB SSD | 256 GB SSD | 256 GB NVMe |
| NICs | **2 integradas** | 2 integradas PCIe | 2 integradas |
| NIC espejo emergencia | RTL8153 USB | — | — |

---

## Parte 6 — Soporte remoto con Cursor + Claude

Una vez el equipo cliente está en Tailscale, Claude (vía Cursor) puede conectarse directamente al servidor remoto y resolver fallos igual que lo hace en el lab `.205` — leer archivos, editar código, revisar logs, reiniciar servicios.

### 6.1 Qué puede hacer Claude en el servidor remoto

| Acción | Ejemplo |
|--------|---------|
| Leer logs en tiempo real | `journalctl -u shomer-guardian -f` |
| Editar archivos de configuración | Corregir bugs en `/opt/network_monitor/app/` |
| Reiniciar servicios | `systemctl restart shomer-guardian` |
| Revisar base de datos | `sqlite3 /storage/db/network_monitor.db` |
| Transferir archivos desde el lab | `scp` desde `.205` al equipo cliente |
| Ejecutar el instalador o actualizaciones | `bash tools/install_shomer.sh` |
| Diagnosticar red | `ip`, `ping`, `tcpdump`, `curl` |

### 6.2 Cómo abrir la sesión para que Claude acceda

**Opción A — SSH directo desde Cursor (recomendada)**

Cursor tiene extensión "Remote - SSH". Conectarse así:

1. En Cursor: `Ctrl+Shift+P` → "Remote-SSH: Connect to Host"
2. Ingresar: `usb_admin@nombre-equipo-bogota`
3. Cursor abre una sesión completa en el servidor remoto
4. Claude opera directamente en ese servidor — misma experiencia que el lab

**Opción B — Abrir terminal SSH y compartir sesión**

```bash
# Desde tu PC (Utah):
ssh usb_admin@nombre-equipo-bogota

# Claude opera en esa terminal — pídele lo que necesites
```

### 6.3 Prerequisito — SSH habilitado en Tailscale

El flag `--ssh` al conectar activa SSH a través de Tailscale sin configurar nada más:

```bash
# Ya incluido en el comando de instalación (Parte 2):
sudo tailscale up --authkey=tskey-auth-XXXX --ssh
```

Verificar que funciona:
```bash
# Desde tu PC en Utah:
tailscale ssh usb_admin@nombre-equipo-bogota
```

### 6.4 Agregar la llave SSH del lab al equipo remoto (alternativa)

Si prefieres SSH clásico sin depender de Tailscale SSH:

```bash
# Copiar la llave pública del lab al equipo remoto:
ssh-copy-id -i ~/.ssh/id_rsa.pub usb_admin@nombre-equipo-bogota

# Desde ese momento: sin contraseña, acceso directo
ssh usb_admin@nombre-equipo-bogota
```

### 6.5 Protocolo de soporte remoto

Cuando hay un fallo en un equipo cliente:

```
1. Juan Pablo abre Cursor → Remote-SSH → nombre-equipo-cliente
2. Claude lee los logs y diagnostica
3. Claude propone y ejecuta el fix con aprobación de Juan Pablo
4. Se verifica que los servicios vuelven a active
5. Se documenta el fix en CLAUDE.md si es un bug nuevo
```

> **Regla:** Claude no ejecuta acciones destructivas (borrar DBs, reset fábrica, cambiar credenciales) sin confirmación explícita de Juan Pablo — igual que en el lab.

---

## Referencia rápida comandos Tailscale

```bash
# Ver todos los equipos conectados:
tailscale status

# Conectar equipo nuevo:
sudo tailscale up --authkey=tskey-auth-XXXX --ssh

# SSH directo vía Tailscale:
tailscale ssh usb_admin@nombre-equipo

# Ver IP Tailscale del equipo:
tailscale ip

# Desconectar temporalmente:
sudo tailscale down

# Estado detallado:
tailscale status --json
```

---

## Post-instalación — Suricata en laboratorio (mini PCs Utah)

Tras `install_shomer.sh`, en lab **sin cable SPAN** en la NIC espejo:

```bash
cd /opt/network_monitor
# Mini PCs: gestión enp4s0, espejo enp2s0
sudo MIRROR_IFACE=enp2s0 bash tools/suricata_lab_setup.sh
# Lab .205: espejo enp4s0
sudo MIRROR_IFACE=enp4s0 bash tools/suricata_lab_setup.sh
```

Eso activa ruleset ET, reglas `shomer-local.rules` y `SHOMER_LAB_NO_SPAN=1` (pipeline OK sin tráfico espejo).

**Producción (hotel con SPAN):** no usar `SHOMER_LAB_NO_SPAN`. Ver checklist Hunter en `CLAUDE.md` §AJ.
