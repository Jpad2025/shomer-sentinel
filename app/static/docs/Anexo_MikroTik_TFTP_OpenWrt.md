# Pasos de Instalación — Shomer Sentinel 2.0 (anexo detallado)

> **2026-04-24 — Jerarquía de documentación**
> - **Guía principal de instalación en producción (orden de trabajo, checklist, resumen):** `Instalacion_Shomer_Produccion_Tecnico.md` (mismo directorio `/static/docs/`).
> - **Guía maestra del sistema (arquitectura, código, recuperación desde cero):** `SISTEMA_SHOMER.md` en la raíz del código en el appliance (`/opt/network_monitor/`).
> - **Este archivo** conserva el procedimiento **largo** (p. ej. Fases B/C MikroTik, TFTP, TinyPXE, firmware `rc3`, reglas TEE, tablas de tiempos y fallos). Usar cuando la guía corta remite al “anexo”.

*USB Ingeniería SAS — Documento técnico ampliado para el técnico de campo.*  
*Última actualización de referencia: abril 2026 (anexo); guía prioritaria vigente: `Instalacion_Shomer_Produccion_Tecnico.md`.*

---

## 0. Hoja de datos del cliente — llenar ANTES de salir del taller

> Imprimir esta hoja y llenarla con el cliente o el responsable de IT antes de la visita.
> Sin estos datos no se puede completar la instalación.

**Datos del cliente:**

| Campo | Valor |
|-------|-------|
| Nombre del cliente | |
| Dirección de instalación | |
| Contacto en sitio | |
| Teléfono de contacto | |
| Fecha de instalación | |
| Técnico asignado | |

**Red del cliente:**

| Campo | Valor | Ejemplo |
|-------|-------|---------|
| Subnet del cliente | | `192.168.10.0/24` |
| Gateway / Router principal | | `192.168.10.1` |
| Servidor DNS del cliente | | `8.8.8.8` |
| IP asignada al Shomer (enp2s0) | | `192.168.10.63` |
| IP asignada a enp4s0 (Suricata) | | `192.168.10.64` |
| IP asignada al MikroTik | | `192.168.10.206` |
| Rango IPs de los GL.iNet | | `192.168.10.210` a `.220` |
| ¿Hay múltiples subredes? | Sí / No | |
| Subnet adicional (si aplica) | | `10.10.1.0/24` |

**WiFi del cliente (solo si Modo B — internet por WiFi):**

| Campo | Valor |
|-------|-------|
| SSID WiFi | |
| Contraseña WiFi | |
| Banda (2.4 / 5 GHz) | |

**Equipos a respaldar (Protector):**

| Nombre equipo | IP | Tipo | Usuario | Ruta fuente |
|---------------|----|------|---------|-------------|
| | | Win/Linux | | |
| | | Win/Linux | | |
| | | Win/Linux | | |

**Telegram (alertas Guardian):**

| Campo | Valor |
|-------|-------|
| Token del bot | |
| Chat ID del grupo | |

**Credenciales GL.iNet (un renglón por AP):**

| Nombre / Ubicación | IP | Password SSH |
|--------------------|----|-------------|
| | | |
| | | |
| | | |
| | | |
| | | |
| | | |

> ⚠️ Esta hoja es confidencial. No enviar por correo sin cifrar. Archivar en carpeta segura de USB Ingeniería.

---

## 1. Requisitos previos antes de llegar al cliente

- IP disponible para el Shomer en la red del cliente
- Subnet del cliente (ej: 192.168.10.0/24)
- Gateway del cliente (ej: 192.168.10.1)
- Rango de IPs de los APs WiFi
- Laptop Windows con los siguientes programas instalados:
  - **Winbox** — para configurar MikroTik
  - **Netinstall** — para recuperación de emergencia
  - **PuTTY** — para SSH
  - **TinyPXE Server** — para TFTP boot (https://erwan.labalec.fr/tinypxeserver/)
- Archivos de firmware en carpeta local (ej: `C:\flashmikro\`):
  - `routeros-mmips-6.49.19.npk` — RouterOS para downgrade/recuperación
  - `openwrt-23.05.0-rc3-ramips-mt7621-mikrotik_routerboard-760igs-initramfs-kernel.bin` — initramfs TFTP
  - `openwrt-23.05.5-ramips-mt7621-mikrotik_routerboard-760igs-squashfs-sysupgrade.bin` — firmware permanente

> ⚠️ NO usar Tftpd64 — no es confiable para este proceso. Usar TinyPXE Server.

---

## 2. Hardware del Shomer

| Componente | Detalle |
|------------|---------|
| Mini PC | Intel N100, 16GB RAM, NVMe 500GB |
| OS | Ubuntu 22.04.5 LTS |
| NIC1 (enp2s0) | Gestión + Guardian — conectar a red del cliente |
| NIC2 (enp4s0) | Suricata/Mirror — recibe tráfico copiado del MikroTik |
| Panel web | `http://[IP-enp2s0]:8000` |

---

## 3. Hardware del MikroTik hEX S

| Componente | Detalle |
|------------|---------|
| Modelo | RB760iGS (hEX S) |
| Firmware | OpenWrt 23.05.5 (NO RouterOS — no soporta port mirroring) |
| Puerto 1 (WAN/PoE-in) | Uplink a internet del cliente |
| Puertos 2-5 (LAN) | Red interna del cliente — conectar switch |
| IP LAN | Asignada por el técnico según red del cliente |
| IP WAN | DHCP del router del cliente o estática según instalación |
| SSH | `root@[IP-MikroTik]` puerto 22 |

---

## 3b. Topología física

```
Internet
    │
    ▼
[Router del cliente]
    │
    ▼
[Switch principal]
    │           │                    │
    ▼           ▼                    ▼
[MikroTik   [GL.iNet x6]    [Equipos del cliente]
 hEX S]      APs WiFi        PCs, impresoras, etc.
    │              │
    │ TEE mirror   │ SSH (Guardian monitor)
    │              │
    ▼              ▼
[SHOMER — Mini PC]
 enp4s0 ← tráfico espejado (Suricata)
 enp2s0 → panel web :8000 → red del cliente
```

**Conexiones físicas:**

| Cable | Desde | Hacia | Función |
|-------|-------|-------|---------|
| 1 | Router cliente | Puerto 1 MikroTik (WAN) | Internet al firewall |
| 2 | Puerto 2-5 MikroTik (LAN) | Switch principal | Red interna |
| 3 | Switch principal | enp2s0 Shomer | Gestión + panel |
| 4 | Switch principal | enp4s0 Shomer | Mirror → Suricata |
| 5 | Switch principal | Puerto LAN GL.iNet | Uplink GL.iNet |

> ⚠️ El mirror de tráfico sale del MikroTik vía TEE (iptables) hacia enp4s0. No requiere puerto SPAN físico en el switch.

---

## Fase A — Preparación y configuración del Shomer

### A.1 — Preparación en el taller (antes de salir a campo)

El Shomer sale del taller con IP de fábrica `192.168.0.205/24`.
Si se acaba de usar en otra instalación, resetear primero:

```bash
sudo bash /opt/network_monitor/tools/factory_reset_network.sh
```

Confirmar IP de fábrica:
```bash
ip addr show enp2s0 | grep inet
# Debe mostrar: inet 192.168.0.205/24
```

> ✅ El Shomer está listo para despachar cuando responde en `192.168.0.205`.

---

### A.2 — Setup wizard en campo (laptop directo al Shomer)

Antes de conectar el Shomer a la red del cliente:

1. Conectar laptop directo a **enp2s0** del Shomer con cable ethernet
2. Asignar IP estática en la laptop: `192.168.0.100/24`
3. Abrir navegador → `http://192.168.0.205:8000/setup`
4. **Paso 1 — Detección de red:**
   - Clic **Escanear red**
   - El wizard detecta subnet y gateway actuales
   - **Editar manualmente** los campos con datos del cliente:
     - **Subnet del cliente:** ej. `192.168.10.0/24`
     - **Gateway del cliente:** ej. `192.168.10.1`
   - Seleccionar una IP disponible para el Shomer en el grid (ej. `192.168.10.63`)
5. **Paso 2 — Internet:**
   - **Modo A** (lo normal): "El cliente provee internet" — el cable del switch da internet
   - **Modo B** (sin cable libre): "Via WiFi" — ingresar SSID y contraseña del cliente
6. **Paso 3 — Resumen:**
   - Verificar todos los datos
   - Clic **Aplicar configuración**
   - El panel muestra la nueva URL: `http://192.168.10.63:8000`
7. Desconectar la laptop del Shomer
8. Conectar **enp2s0** del Shomer al switch del cliente
9. Abrir `http://192.168.10.63:8000` desde cualquier equipo de la red del cliente

> ⚠️ Una vez aplicada la configuración, el Shomer ya no responde en `192.168.0.205`.
> Conectar el cable al switch del cliente ANTES de abrir la nueva URL.

---

### A.2b — Configuración manual vía Netplan (cuando el wizard no es accesible)

Usar este método si:
- El Shomer no responde en `192.168.0.205` (la IP de fábrica fue cambiada)
- El wizard no carga en el navegador
- Se necesita cambiar la IP sin acceso al panel

**Paso 1 — Conectar al Shomer por SSH o teclado directo:**
```bash
ssh usb_admin@[IP-actual-del-Shomer]
# o conectar monitor + teclado directamente al Mini PC
```

**Paso 2 — Editar el netplan:**
```bash
sudo nano /etc/netplan/01-network-config.yaml
```

**Paso 3 — Plantilla (ajustar valores del cliente):**
```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    enp2s0:
      dhcp4: false
      addresses: [192.168.10.63/24]      # ← IP del Shomer en red del cliente
      routes:
        - to: default
          via: 192.168.10.1              # ← Gateway del cliente
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]
    enp4s0:
      dhcp4: false
      addresses: [192.168.10.64/24]      # ← IP de Suricata/mirror
```

**Paso 4 — Aplicar:**
```bash
sudo netplan apply
```

**Paso 5 — Verificar:**
```bash
ip addr show enp2s0 | grep inet
# Debe mostrar la nueva IP del cliente
ping 8.8.8.8 -c 3
# Debe responder
```

---

### A.3 — Persistencia de Suricata (sysctl) — CRÍTICO

> **Hacer esto en cada instalación nueva.**
> Sin este paso, Suricata deja de recibir el tráfico del mirror cada vez que el Shomer reinicia.

**El problema:** Linux activa `rp_filter` por defecto. Descarta paquetes del mirror TEE porque no tienen ruta de retorno.

```bash
# Crear configuración persistente
sudo tee /etc/sysctl.d/99-shomer-suricata.conf << 'EOF'
net.ipv4.conf.enp4s0.rp_filter=0
net.ipv4.conf.all.rp_filter=0
EOF

# Aplicar sin reiniciar
sudo sysctl --system

# Verificar:
sysctl net.ipv4.conf.enp4s0.rp_filter
# Debe mostrar: net.ipv4.conf.enp4s0.rp_filter = 0
```

**Verificar que Suricata recibe tráfico:**
```bash
sudo tcpdump -i enp4s0 -n -c 20
# Debe mostrar paquetes de la red del cliente
```

---

### A.4 — Primer login y cambio de contraseña

**URL del panel:** `http://[IP-Shomer]:8000`

**Credenciales de fábrica:** consultar con USB Ingeniería — nunca documentar aquí.

> ⚠️ Cambiar la contraseña en cada instalación nueva.

**Si el panel no carga — verificar servicios:**
```bash
sudo systemctl status shomer-guardian.service   # Core 8000 (Guardian + Hunter)
sudo systemctl status shomer-tools.service        # Tools 8001 (Tracker + Protector) — producción

# Si alguno está caído:
sudo systemctl stop shomer-guardian.service
sudo lsof -ti:8000 | xargs sudo kill -9 2>/dev/null
sleep 2
sudo systemctl start shomer-guardian.service
```

---

## Fase B — Instalación OpenWrt en MikroTik hEX S

> ⚠️ El MikroTik hEX S (RB760iGS) con chip MT7621 NO soporta port mirroring en RouterOS.
> Se debe instalar OpenWrt para habilitar el mirror de tráfico hacia Suricata (enp4s0).

### B.1 — Downgrade RouterOS a 6.49.19

El TFTP boot requiere RouterOS 6.x. Si el equipo viene con RouterOS 7.x, hacer downgrade primero.

1. Conectar laptop al MikroTik (IP de fábrica: `192.168.88.1`)
2. Abrir Winbox → conectar con usuario `admin`, sin contraseña
3. Files → Upload → subir `routeros-mmips-6.49.19.npk`
4. System → Packages → Downgrade → confirmar reinicio
5. Esperar ~2 minutos
6. Verificar en terminal Winbox:
   ```
   /system resource print
   ```
   Debe mostrar `version: 6.49.19`

> ✅ Si el MikroTik ya tiene RouterOS 6.x (ej: recién restaurado con Netinstall), saltar este paso.

### B.2 — Configurar TinyPXE Server

7. Asignar IP estática en la laptop: `192.168.88.10/24`, Gateway: `192.168.88.1`
8. Abrir TinyPXE Server como administrador
9. Configurar:
   - Option 54 (DHCP Server): `192.168.88.10`
   - Next-Server: `192.168.88.10`
   - Filename: clic en `(...)` → seleccionar `initramfs-kernel.bin`
   - Activar ProxyDhcp ✓
   - Desactivar BINL ✗
   - Dejar HTTPd activado ✓
10. Clic **Online**

> ⚠️ CRÍTICO — versión del initramfs: Solo `openwrt-23.05.0-rc3-...` es netbootable en el hEX S.
> rc1, rc2, rc4 y la versión final 23.05.x NO funcionan en este modelo.

### B.3 — Boot TFTP (cargar OpenWrt en RAM)

11. Conectar cable: laptop → Puerto 1 (WAN/PoE-in) del MikroTik
12. Desconectar la alimentación del MikroTik
13. Presionar y mantener el botón Reset (parte trasera del equipo)
14. Conectar la alimentación sin soltar Reset
15. Esperar ~25 segundos hasta escuchar el beep
16. Soltar el botón Reset
17. Verificar en TinyPXE — debe aparecer en el log:
    ```
    TFTPd:DoReadFile: openwrt-rc3-...-initramfs-kernel.bin
    DHCPd:ACK sent, IP:192.168.88.xx
    ```
18. Esperar 1-2 minutos que OpenWrt cargue en RAM
19. Mover el cable al Puerto 2 del MikroTik
20. Verificar que la laptop recibe IP `192.168.1.x` por DHCP
21. Abrir navegador → `http://192.168.1.1`
22. Login: usuario `root`, password vacío

> ✅ Si aparece el panel LuCI de OpenWrt — el boot en RAM fue exitoso.

### B.4 — Flash sysupgrade (instalación permanente)

23. En panel OpenWrt → System → Backup/Flash Firmware
24. Sección Flash new firmware image → clic **Flash image...**
25. Seleccionar `openwrt-23.05.5-...-squashfs-sysupgrade.bin`
26. Desmarcar **Keep settings** (instalación limpia)
27. Clic Upload → confirmar con **Continue**
28. Esperar 3-5 minutos — el equipo pita y reinicia
29. Conectar cable a Puerto 2-5, abrir `http://192.168.1.1`
30. Login: usuario `root`, password vacío

> ✅ Si aparece LuCI de OpenWrt — instalación permanente exitosa.

---

## Fase C — Configuración del Firewall (MikroTik OpenWrt)

### C.1 — Configuración inicial

Conectar a `http://192.168.1.1` → System → Administration:
- Establecer contraseña root segura (guardar en BD del Shomer, nunca en documentos)
- SSH Access → enabled → Allow password authentication → Save

### C.2 — Asignar IP del cliente

Network → Interfaces → LAN → Edit:
- IPv4 address: IP del MikroTik en la red del cliente (ej: `192.168.10.206`)
- IPv4 netmask: `255.255.255.0`
- Guardar y aplicar

> ⚠️ Al cambiar la IP perderás acceso desde `192.168.1.1`. Reconectar desde la nueva IP.

### C.3 — Deshabilitar DHCP

Network → Interfaces → LAN → Edit → sección DHCP Server:
- Desactivar / Ignore interface
- Guardar y aplicar

> El MikroTik NO debe dar IPs — eso lo hace el router del cliente.

### C.4 — Instalar módulos TEE para mirror de tráfico

Conectar via SSH:
```bash
ssh root@[IP-MikroTik]
```

> ⚠️ El MikroTik necesita internet para instalar paquetes. Ver sección C.4a si no tiene internet directo.

Instalar módulos:
```bash
opkg update
opkg install iptables-mod-tee kmod-ipt-tee
opkg install iptables-zz-legacy
opkg install kmod-nft-nat kmod-nf-nat iptables-mod-conntrack-extra
```

Cargar módulo TEE en memoria:
```bash
modprobe xt_TEE
```

Verificar:
```bash
lsmod | grep tee
opkg list-installed | grep tee
```

### C.4a — Dar internet al MikroTik via GL.iNet (si no hay cable WAN disponible)

Si el cliente no tiene cable ethernet disponible para el WAN del MikroTik:

31. En panel GL.iNet → Red → Internet → verificar que GL.iNet tiene internet por WiFi (Repetidor)
32. En GL.iNet → Red → Internet → habilitar el puerto WAN/LAN1 como LAN adicional
33. Conectar cable: Puerto LAN del GL.iNet → Puerto 1 WAN del MikroTik
34. En el MikroTik forzar DHCP en la WAN:
    ```bash
    udhcpc -i br-wan -n
    ```
35. Si GL.iNet y MikroTik están en la misma subred, asignar IP estática:
    ```bash
    uci set network.wan.proto='static'
    uci set network.wan.ipaddr='[IP-libre-en-subred-GLiNet]'
    uci set network.wan.netmask='255.255.255.0'
    uci set network.wan.gateway='[IP-GLiNet]'
    uci set network.wan.dns='8.8.8.8'
    uci commit network
    /etc/init.d/network restart
    ```
36. Agregar ruta default si no se asignó automáticamente:
    ```bash
    ip route add default via [IP-GLiNet]
    ```
37. Verificar internet:
    ```bash
    ping -c 3 8.8.8.8
    ```

> Una vez instalados los paquetes, desconectar el GL.iNet del WAN del MikroTik y reconectar el uplink real del cliente.

### C.5 — Configurar NAT y forwarding WAN → LAN

Necesario para que el tráfico externo fluya y el TEE lo capture:

```bash
echo 1 > /proc/sys/net/ipv4/ip_forward

nft add table ip nat
nft add chain ip nat postrouting { type nat hook postrouting priority 100 \; }
nft add rule ip nat postrouting oifname "br-wan" masquerade

nft add table ip filter
nft add chain ip filter forward { type filter hook forward priority 0 \; policy accept \; }
```

> ⚠️ OpenWrt 23.05.5 usa nftables — NO usar iptables-legacy para NAT. Usar `nft` directamente.

### C.6 — Configurar mirror de tráfico TEE hacia Suricata

Reemplazar `[IP-enp4s0]` con la IP de monitoreo del Shomer:

```bash
iptables -t mangle -A PREROUTING -j TEE --gateway [IP-enp4s0]
iptables -t mangle -A POSTROUTING -j TEE --gateway [IP-enp4s0]
```

Verificar que las reglas cuentan paquetes:
```bash
iptables -t mangle -L -n -v
```

### C.7 — Hacer mirror y NAT persistentes al reinicio

```bash
cat >> /etc/rc.local << 'EOF'
modprobe xt_TEE
echo 1 > /proc/sys/net/ipv4/ip_forward
nft add table ip nat 2>/dev/null
nft add chain ip nat postrouting { type nat hook postrouting priority 100 \; } 2>/dev/null
nft add rule ip nat postrouting oifname "br-wan" masquerade 2>/dev/null
iptables -t mangle -A PREROUTING -j TEE --gateway [IP-enp4s0]
iptables -t mangle -A POSTROUTING -j TEE --gateway [IP-enp4s0]
EOF
```

**Verificar persistencia — reiniciar el MikroTik y confirmar:**
```bash
reboot
# Esperar 2 minutos, reconectar SSH
iptables -t mangle -L -n -v
# Deben aparecer las reglas TEE contando paquetes
```

### C.8 — Verificar mirror desde el Shomer

En el Shomer via SSH:
```bash
sudo tcpdump -i enp4s0 -n -c 20
# Debe mostrar tráfico de la red del cliente
```

### C.9 — Registrar firewall en panel Hunter

```bash
sqlite3 /storage/db/network_monitor.db "
INSERT OR REPLACE INTO system_state (key, value) VALUES ('hunter.firewall_ip', '[IP-MikroTik]');
INSERT OR REPLACE INTO system_state (key, value) VALUES ('hunter.firewall_user', 'root');
INSERT OR REPLACE INTO system_state (key, value) VALUES ('hunter.firewall_pass', '[password]');
"
```

Verificar bloqueo real:
```bash
curl -s -X POST http://localhost:8000/remedies/block \
  -H "Content-Type: application/json" \
  -d '{"ip": "1.2.3.4", "reason": "test"}' | python3 -m json.tool
# Debe responder: "firewall_ok": true
```

Desbloquear:
```bash
curl -s -X POST http://localhost:8000/remedies/unblock \
  -H "Content-Type: application/json" \
  -d '{"ip": "1.2.3.4"}' | python3 -m json.tool
```

---

## Fase D — Configuración GL.iNet AX6000

El GL.iNet AX6000 viene con OpenWrt preinstalado. Solo actualizar a la versión más reciente.

38. Conectar laptop al puerto LAN del GL.iNet
39. Abrir navegador → `http://192.168.8.1`
40. Ir a System → Upgrade → Online Upgrade
41. Si hay actualización: clic **Download and Install**
42. Esperar reinicio (~3 minutos)
43. Verificar SSH habilitado: System → Advanced Settings → SSH → habilitado en LAN
44. Probar SSH desde el Shomer:
    ```bash
    ssh root@[IP-GL.iNet]
    ```
45. Agregar a Guardian via panel web Shomer → Escanear Red → promover el GL.iNet como nodo monitoreado

---

## Fase E — Configuración del panel Shomer

Con todo el hardware instalado y conectado, configurar cada módulo desde el panel web.

### E.1 — Guardian (monitoreo de routers GL.iNet)

`http://[IP-Shomer]:8000` → sección Guardian

1. Clic **Escanear Red** — el sistema descubre dispositivos en la red
2. En "Dispositivos Descubiertos", identificar cada GL.iNet
3. Clic **Agregar** en cada GL.iNet → pasan a "Nodos monitoreados"
4. Abrir **⚙ Configuración de Red — Guardian**:
   - **Credenciales SSH de routers:** agregar cada GL.iNet con IP, usuario `root` y contraseña
   - **Umbral de fallos:** `2`
   - **Cooldown entre reboots:** `360` segundos
   - **Token Telegram:** pegar token del bot
   - **Chat ID Telegram:** pegar ID del grupo
   - Clic **Guardar parámetros**
5. Clic **Probar Telegram** — verificar que llega el mensaje de prueba
6. Verificar que los nodos aparecen en verde (online)

> ✅ Guardian monitoreará los GL.iNet cada 10 segundos y reiniciará automáticamente si fallan 2 veces seguidas.

### E.2 — Tracker (inventario de activos)

`http://[IP-Shomer]:8000/tracker`

1. Clic **① Credenciales** → ingresar:
   - Usuario SSH: `shomer` (o el usuario de los equipos Linux del cliente)
   - Contraseña SSH
   - Comunidad SNMP: `public`
   - Clic **Guardar credenciales**
2. Clic **② Escanear Red** — ping sweep rápido (~30 seg)
3. Clic **③ Escaneo Profundo** — nmap + WMI/SSH/SNMP (~5 min)
4. Revisar activos: clic en cada fila → editar nombre, ubicación, usuario asignado → **Guardar cambios**
5. Clic **④ Excel Global** → descargar inventario completo para el cliente

> ⚠️ Para escanear equipos Linux, crear usuario `shomer` con sudo en cada equipo primero:
> ```bash
> sudo useradd -m -s /bin/bash shomer
> echo "shomer:[PASSWORD-CLIENTE]" | sudo chpasswd
> sudo usermod -aG sudo shomer
> ```

### E.3 — Hunter (seguridad)

`http://[IP-Shomer]:8000/security`

1. Abrir **⚙ Configuración de Red — Hunter**
2. **Subredes a vigilar:** agregar la subnet del cliente (ej. `192.168.10.0/24`)
3. **Firewall — MikroTik:** ingresar IP, usuario `root` y password → Guardar
4. **Reglas Personalizadas — Suricata:** clic **↻ Actualizar** para verificar que carga
5. Verificar que Suricata recibe tráfico:
   ```bash
   sudo tcpdump -i enp4s0 -n -c 10
   ```

> ✅ Si aparecen alertas en la tabla de Hunter, el sistema está operativo end-to-end.

### E.4 — Protector (backups)

`http://[IP-Shomer]:8000/backups`

1. Clic **+ Agregar Equipo** por cada equipo a respaldar:
   - Nombre, IP, Tipo (Windows/Linux), Usuario, Contraseña, Ruta fuente
   - Clic **Test conexión** → debe responder OK
   - Clic **Guardar**
2. Clic **Backup Ahora** en cada equipo → verificar que completa sin errores
3. Verificar en **Snapshots** que aparece el snapshot nuevo

> El cron corre automáticamente a las 2:00 AM — no requiere configuración adicional.

**Backblaze B2 (si contratado):**
1. Abrir **⚙ Configuración — Backblaze B2**
2. Ingresar Bucket, Account ID, Application Key, Password B2 → Guardar
3. Clic **Sincronizar a B2** para el backup inicial

### E.5 — Verificación final de servicios

```bash
sudo systemctl is-active shomer-guardian.service   # Core API puerto 8000
sudo systemctl is-active shomer-tools.service      # Tools API puerto 8001 (inventario + backups)
sudo systemctl is-active suricata                  # IDS
sudo systemctl is-active redis                     # Cache Guardian

# Logs si hay errores (Core 8000 y Tools 8001):
sudo tail -f /var/log/shomer/api.log
sudo tail -f /var/log/shomer/tools_api.log
```

---

## Fase F — Configuración de Telegram paso a paso

### F.1 — Crear el bot

1. Abrir Telegram → buscar `@BotFather`
2. Enviar: `/newbot`
3. Ingresar nombre: `Shomer [NombreCliente] Bot`
4. Ingresar username (debe terminar en `bot`): `shomer_[cliente]_bot`
5. Copiar el **token** que devuelve BotFather

### F.2 — Crear el grupo de alertas

1. Crear grupo: `Alertas Shomer — [NombreCliente]`
2. Agregar el bot al grupo
3. Enviar cualquier mensaje en el grupo

### F.3 — Obtener el Chat ID

```bash
curl -s "https://api.telegram.org/bot[TOKEN]/getUpdates" \
  | python3 -m json.tool | grep chat_id
# Devuelve: "id": -1001234567890
# El número negativo es el chat_id del grupo
```

### F.4 — Configurar en el panel

1. Guardian → ⚙ Configuración → **Guardian — Parámetros**
2. Pegar Token y Chat ID → Guardar parámetros
3. Clic **Probar Telegram** → verificar que llega el mensaje

---

## Fase G — Instalación con múltiples subredes (hoteles con VLANs)

Ejemplo típico de hotel:
- `192.168.10.0/24` — staff y administración
- `10.10.1.0/24` — huéspedes WiFi

**En el panel:**

- **Guardian:** ⚙ Configuración → Subredes → agregar ambas
- **Tracker:** ⚙ Configuración → Subredes → agregar ambas → Escaneo Profundo escaneará todo
- **Hunter:** ⚙ Configuración → Subredes a vigilar → agregar ambas

**Verificar rutas en el Shomer:**
```bash
ip route
# Deben aparecer todas las subredes del cliente
```

Si falta alguna ruta, agregarla permanentemente en el netplan:
```yaml
# Bajo enp2s0 en /etc/netplan/01-network-config.yaml:
routes:
  - to: default
    via: 192.168.10.1
  - to: 10.10.1.0/24
    via: 192.168.10.1
```

---

## 7. Flujo de mitigación Hunter

| Severidad | Acción |
|-----------|--------|
| Critical / High | Auto-bloqueo automático al cargar la tabla |
| Medium / Low | Técnico decide manualmente — Bloquear / Ignorar |

- Suricata detecta amenaza en tráfico recibido por enp4s0 (mirror del MikroTik)
- Hunter muestra la alerta en el panel
- Al bloquear: Shomer → SSH → MikroTik OpenWrt → iptables DROP
- Credenciales SSH del firewall en `system_state` BD (nunca hardcodeadas)

---

## 8. Restauración de emergencia — MikroTik a RouterOS

Si el MikroTik queda en estado desconocido o no responde:

**Señales de modo de recuperación:**

| Estado LEDs | Significado |
|-------------|-------------|
| Power + SFP estáticos, Puerto 1 parpadeando + beep especial | Modo TFTP recovery |
| Todos los LEDs estáticos, no responde | Boot incompleto — hacer reset |

**Método — Netinstall (Windows):**

46. Laptop con IP `192.168.88.10/24`
47. Abrir Netinstall → configurar IP del servidor: `192.168.88.10`
48. Seleccionar archivo `routeros-mmips-6.49.19.npk`
49. Cable laptop → Puerto 1 del MikroTik
50. Apagar MikroTik → presionar y mantener Reset → encender → esperar ~15s que aparezca en Netinstall → soltar Reset
51. Clic Install → esperar ~2 minutos
52. MikroTik reinicia con RouterOS limpio: IP `192.168.88.1`, usuario `admin`, sin contraseña

> ⚠️ Tras restaurar con Netinstall, repetir el proceso completo desde Fase B.

---

## 9. Problemas conocidos y soluciones

| # | Problema | Causa | Solución |
|---|----------|-------|----------|
| 1 | TinyPXE no recibe petición del MikroTik | BINL activado o IP mal configurada | Desactivar BINL, activar ProxyDhcp, verificar laptop en `192.168.88.10/24` |
| 2 | initramfs no bootea por TFTP | Versión incorrecta del archivo | Usar exactamente rc3 — otras versiones no funcionan en el hEX S |
| 3 | OpenWrt carga en RAM pero no flashea | sysupgrade.bin incorrecto | Verificar que sea `squashfs-sysupgrade.bin` de 23.05.5 |
| 4 | No se puede ingresar tras flash | OpenWrt queda sin contraseña | Usuario `root`, password vacío |
| 5 | `iptables: not found` en OpenWrt | iptables no instalado por defecto | `opkg install iptables-zz-legacy` |
| 6 | Mirror no persiste tras reboot | No se guardó en rc.local | Ejecutar el bloque `cat >> /etc/rc.local` de la sección C.7 |
| 7 | MikroTik no tiene internet para opkg | Sin cable WAN | Conectar GL.iNet como bridge — ver sección C.4a |
| 8 | Netinstall no detecta el MikroTik | Reset soltado antes de tiempo | Mantener Reset hasta que aparezca en Netinstall (~15s) |
| 9 | No entra por PuTTY tras configurar SSH | SSH no habilitado correctamente | Panel OpenWrt → System → Administration → SSH Access → enabled + Allow password auth |
| 10 | MASQUERADE falla con iptables en OpenWrt 23.05.5 | OpenWrt usa nftables por defecto | Usar `nft` directamente — ver sección C.5 |
| 11 | TEE cuenta paquetes pero Suricata no los recibe | Reverse path filtering activo en el Shomer | `sudo sysctl -w net.ipv4.conf.enp4s0.rp_filter=0` (hacer permanente — sección A.3) |
| 12 | GL.iNet no entrega DHCP al MikroTik WAN | Misma subred en WAN y LAN del MikroTik | Asignar IP estática al WAN del MikroTik — ver sección C.4a |
| 13 | Shomer no responde en IP de fábrica | Instalación anterior cambió la IP | Conectar monitor + teclado y usar netplan manual — ver sección A.2b |
| 14 | Wizard `/setup` no detecta la subnet correcta | Sistema detecta WiFi en lugar de cable | Editar manualmente los campos Subnet y Gateway en el paso 1 del wizard |

---

## H. Tiempos estimados de instalación

| Fase | Descripción | Tiempo |
|------|-------------|--------|
| 0 | Hoja de datos + preparación en taller | 15 min |
| A | Setup wizard del Shomer | 10-15 min |
| B | Flash OpenWrt en MikroTik | 20-30 min |
| C | Configuración MikroTik (NAT + TEE + rc.local) | 20-25 min |
| D | Configuración GL.iNet ×1 | 5 min |
| D×N | Configuración GL.iNet adicionales | 3-4 min c/u |
| E.1 | Guardian — nodos + Telegram | 15 min |
| E.2 | Tracker — escaneo profundo + activos | 20-30 min |
| E.3 | Hunter — firewall + verificar bloqueo | 10 min |
| E.4 | Protector — equipos + backup inicial | 15-20 min |
| F | Telegram | 10 min |
| Final | Verificación + reboot MikroTik + checklist | 15-20 min |
| **Total** | **Instalación completa (6 GL.iNet)** | **~3-4 horas** |

> **Instalación en dos visitas** (recomendado para clientes grandes):
> - **Visita 1:** Fases A, B, C, D — hardware y red (~2 horas)
> - **Visita 2:** Fase E, F, G — panel y configuración de módulos (~2 horas)

---

## 10. Checklist final antes de entregar al cliente

- ☐ Panel Shomer accesible desde `http://[IP-Shomer]:8000`
- ☐ Guardian monitoreando routers GL.iNet (todos en verde)
- ☐ Reboot manual probado en al menos 1 GL.iNet desde el panel
- ☐ Tracker con inventario inicial levantado
- ☐ Hunter conectado al MikroTik — bloqueo/desbloqueo funcional probado
- ☐ Suricata recibiendo tráfico mirror desde MikroTik (verificar alertas en Hunter)
- ☐ Protector con equipos configurados y backup inicial exitoso
- ☐ Token Telegram configurado — mensaje de prueba recibido
- ☐ DHCP del MikroTik deshabilitado
- ☐ Mirror persistente verificado (reiniciar MikroTik y confirmar que sigue activo)
- ☐ NAT/forwarding persistente verificado (reiniciar MikroTik y confirmar)
- ☐ sysctl rp_filter=0 persistente verificado (reiniciar Shomer y confirmar tcpdump)
- ☐ Credenciales SSH del firewall guardadas en panel Hunter
- ☐ Contraseña del panel cambiada desde credenciales de fábrica
- ☐ Foto de topología física tomada
- ☐ IPs del cliente documentadas en hoja de datos
- ☐ Documento de entrega firmado con el cliente

---

## I. Documento de entrega al cliente

> Imprimir y firmar con el responsable del cliente al finalizar la instalación.

---

**Constancia de instalación — Shomer Sentinel 2.0**

**Cliente:** _____________________________ **Fecha:** _____________

**Instalado por:** ________________________ **USB Ingeniería SAS**

---

**Acceso al sistema:**

| Dato | Valor |
|------|-------|
| URL del panel | `http://________________:8000` |
| Usuario | `admin` |
| Contraseña | (entregada por separado) |

---

**IPs instaladas:**

| Equipo | IP |
|--------|----|
| Shomer (panel web) | |
| Firewall MikroTik | |
| GL.iNet AP-01 | |
| GL.iNet AP-02 | |
| GL.iNet AP-03 | |
| GL.iNet AP-04 | |
| GL.iNet AP-05 | |
| GL.iNet AP-06 | |

---

**Módulos activos:**

| Módulo | Estado |
|--------|--------|
| Guardian — Monitoreo 7x24 | ☐ Activo |
| Tracker — Inventario | ☐ Activo |
| Hunter — Seguridad | ☐ Activo |
| Protector — Backups | ☐ Activo |
| Alertas Telegram | ☐ Configurado |
| Backup en nube B2 | ☐ Activo / ☐ No contratado |

---

**Cómo interpretar una alerta de Telegram:**

```
🔴 [OFFLINE] GL.iNet-Lobby (192.168.10.210)
   Fallos: 2 | Reinicio automático ejecutado
   — Shomer Sentinel
```

- **🔴 OFFLINE:** un router dejó de responder y fue reiniciado automáticamente
- **Si el router no volvió en 5 min:** llamar al número de soporte

---

**Soporte técnico:**

- **USB Ingeniería SAS** — soporte técnico presencial 1 día/semana
- Teléfono: ___________________________
- Email: ___________________________
- Horario soporte remoto: Lun-Vie 9am-6pm (Mountain Time)

---

**Firmas:**

| Técnico USB Ingeniería | Responsable del cliente |
|-----------------------|------------------------|
| Nombre: _____________ | Nombre: _____________ |
| Firma: ______________ | Firma: ______________ |
| Fecha: ______________ | Fecha: ______________ |

---

## J. Acceso remoto de soporte — USB Ingeniería

### J.1 — Si el cliente tiene puerto 22 abierto al exterior

```bash
ssh usb_admin@[IP-pública-del-cliente]
```

### J.2 — Si NO hay acceso SSH externo (lo más común)

Túnel reverso desde el Shomer hacia el servidor de USB Ingeniería.

Crear servicio persistente `/etc/systemd/system/shomer-tunnel.service`:
```ini
[Unit]
Description=Túnel reverso SSH — soporte USB Ingeniería
After=network.target

[Service]
ExecStart=/usr/bin/ssh -fN -R 2222:localhost:22 -o ServerAliveInterval=60 soporte@[servidor-usb]
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable shomer-tunnel.service
sudo systemctl start shomer-tunnel.service
```

Desde USB Ingeniería:
```bash
ssh -p 2222 usb_admin@localhost
```

### J.3 — Exportar configuración del cliente (respaldo post-instalación)

```bash
sqlite3 /storage/db/network_monitor.db \
  "SELECT key, value FROM system_state;" \
  > /storage/reports/config_$(hostname)_$(date +%Y%m%d).txt
```

---

## K. Política de severidad y bloqueo automático (vida real)

> Objetivo: **mitigación en tiempo real** sin que el técnico revise el panel cada día, **sin bloquear tráfico legítimo** por ruido (falsos positivos).

### K.1 — Qué significa “acotado por nivel/regla”

| Capa | Qué hace | Ajuste típico |
|------|----------|----------------|
| **Suricata** | Etiqueta cada alerta con **severity 1–4** en el JSON (`eve-alerts.json`). | Reglas ET ruidosas: **suprimir**, **desactivar SID**, o reglas **pass** para redes de confianza. |
| **Wazuh (`local_rules.xml`)** | **Escala** eventos Suricata a **niveles 1–12+** (reglas 100100, etc.). | Solo **nivel alto** (p. ej. ≥ 12) debe disparar la **integración** que llama a `POST /remedies/block`. |
| **Integración** (`custom-shomer-block`) | Ejecuta bloqueo **solo** si cumple el filtro de Wazuh. | Revisar en `ossec.conf` que el `<level>` coincida con la política acordada. |
| **Panel Hunter + API** | Muestra alertas y aplica política de auto-bloqueo configurable (`hunter.auto_block_*`). | Default recomendado: habilitado, severidad mínima `2` (Critical/High), solo externas, con lista de excepciones. |

### K.2 — Calibración por cliente (primera semana)

1. **Definir `hunter.subnets`** en el panel (qué es “interno” vs “externo” / badge EXT).
2. Tras 48–72 h, anotar **SIDs** que solo generan ruido (mismo hotel, mismo patrón).
3. Añadir **supresión** o regla local en Suricata / desactivar firma en el set ET si aplica.
4. Ajustar en Hunter → **Auto-bloqueo en Producción**:
   - `auto_block_enabled`: ON
   - `auto_block_min_severity`: `2` (Critical/High)
   - `auto_block_only_external`: ON
   - `auto_block_exceptions`: IPs/CIDR de confianza
5. **Revisar** Telegram: si llegan demasiados bloqueos automáticos, **subir** el umbral Wazuh o **restringir** reglas que escalan a nivel 12.

### K.3 — No prometer

- Ningún IDS garantiza **cero** falsos positivos sin tunear.
- Red “callada” de noche puede no generar eventos en EVE: no es siempre fallo (ver sección L).

---

## L. Salud del pipeline Hunter (Suricata / Wazuh / logs EVE)

> El cliente puede creer que “está protegido” si el panel abre; **si el espejo SPAN cae** o Suricata no escribe, **no hay** detección útil.

### L.1 — Endpoint de diagnóstico

```bash
curl -s http://localhost:8000/remedies/pipeline/health | python3 -m json.tool
```

Respuesta útil:

- **`overall_ok: true`** — servicios y log coherentes con tráfico reciente.
- **`issues`** — fallos críticos (Suricata inactivo, log EVE ausente, **sin eventos recientes** más allá del umbral).
- **`warnings`** — p. ej. `wazuh-manager` inactivo (bloqueo automático por integración no funcionará).
- **`checks.last_event_age_sec`** — antigüedad del último evento parseado en el log.
- Umbral configurable: variable de entorno **`HUNTER_PIPELINE_STALE_SEC`** (por defecto **10800 s = 3 h**). En hoteles con poco tráfico nocturno puede subirse a 12–24 h.

### L.2 — Registro en watchdog (opcional)

Fragmento listo en el servidor:

`/opt/network_monitor/tools/pipeline_health_watchdog_snippet.sh`

Añadir su contenido al final de `/usr/local/bin/shomer-health-check.sh`. En esta instalación, el script se ejecuta por **systemd timer** `shomer-health-watchdog.timer` (cada 30 s). Las incidencias quedan en **`/var/log/shomer/watchdog.log`**.

**Telegram** para pipeline: no está cableado por defecto; se puede enlazar a un script externo que lea el JSON y llame al bot si `overall_ok` es false (misma lógica que Guardian).

### L.3 — Comprobación manual del espejo (campo)

```bash
sudo timeout 5 tcpdump -i enp4s0 -c 20 -n 2>/dev/null | head
```

Si **no** hay paquetes en horario laboral, revisar SPAN en switch, cable TEE en MikroTik y IP de `enp4s0`.

---

## M. Checklist de entrega al cliente (firma técnico / cliente)

> Marcar en sitio. Deja claro **qué está cubierto** y **qué no** (sin SOC 24×7).

| # | Ítem | OK | Observación |
|---|------|----|---------------|
| 1 | IPs y subredes documentadas en hoja de datos (sección 0) | ☐ | |
| 2 | Guardian: nodos monitoreados y Telegram de prueba enviado | ☐ | |
| 3 | Hunter: `hunter.subnets` y firewall (IP/usuario) configurados en panel | ☐ | |
| 4 | Suricata + Wazuh activos; `eve-alerts.json` generándose | ☐ | |
| 5 | `GET /remedies/pipeline/health` → `overall_ok: true` (o acción correctiva anotada) | ☐ | |
| 6 | Auto-bloqueo configurado y documentado: enabled / severidad / solo externas / excepciones | ☐ | |
| 7 | Política de bloqueo automático explicada (nivel/regla, no solo “medium” en panel) | ☐ | |
| 8 | Procedimiento si un cliente queda sin servicio: desbloquear IP / contacto soporte | ☐ | |
| 9 | Protector (si contratado): backup de prueba OK | ☐ | N/A |
| 10 | Tracker (si contratado): credenciales y alcance de escaneo acordados | ☐ | N/A |
| 11 | Técnico y cliente firman conformidad de alcance y limitaciones | ☐ | |

**Limitaciones reconocidas (marcar si se explicó al cliente):**

- [ ] Mitigación automática depende de **reglas** y **umbrales**; requiere tuning inicial por entorno.
- [ ] El panel Hunter **visualiza** alertas; el **bloqueo en tiempo real** vía Wazuh requiere servicios y reglas activas.
- [ ] No se garantiza **cero** falsos positivos sin revisión periódica (mínimo **semanal** las primeras semanas).

| Firma técnico USB | Firma cliente |
|-------------------|---------------|
|  |  |

---

## Notas finales para el técnico

- **Nunca hardcodear IPs** — todas las IPs se configuran desde el panel y se guardan en BD
- **TinyPXE > Tftpd64** para TFTP boot en Windows
- **Solo rc3** del initramfs funciona para netboot en el hEX S (RB760iGS)
- **OpenWrt 23.05.5 usa nftables** — usar `nft` para NAT, `iptables` solo para TEE/mangle
- **sysctl rp_filter=0** debe ser persistente en el Shomer — hacerlo en cada instalación
- **Documentar siempre** las IPs asignadas en la hoja de datos del cliente
- **Tomar foto** de la topología física antes de terminar
- **Guardar copia** del manifiesto `CLAUDE.md` actualizado tras cada sesión

---

*Documento generado por USB Ingeniería SAS — Shomer Sentinel 2.0*
*Última actualización: 6 de Abril 2026*
