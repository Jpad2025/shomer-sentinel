# Instalación Ubuntu 22.04 desde USB — Particiones para SSD 256 GB

**Para quién es este documento:** Juan Pablo, Andrés, Laura  
**Cuándo usarlo:** Instalación nueva en equipo de cliente o pruebas — SSD de 256 GB  
**Versión:** mayo 2026

---

## Contexto

El appliance Shomer Sentinel corre sobre Ubuntu 22.04 LTS. El disco se divide en particiones separadas para que logs, datos y backups no llenen el sistema operativo y causen caídas inesperadas.

El modelo de referencia del lab usa un SSD de 500 GB. Esta guía adapta las particiones para equipos con **SSD de 256 GB** (como el equipo de pruebas en Bogotá). El esquema de 500 GB **no se modifica** — esta es una variante de campo.

---

## Requisitos antes de empezar

| Qué | Detalle |
|-----|---------|
| USB booteable | Ubuntu 22.04 LTS — mínimo 8 GB. Herramienta: **Rufus** (Windows) o **balenaEtcher** (Mac/Linux) |
| ISO oficial | ubuntu.com → Download → Ubuntu 22.04.x LTS Server o Desktop |
| Modo arranque | UEFI (el script de Shomer asume GPT + EFI) |
| Conexión a internet | El instalador necesita conexión por cable ethernet — no WiFi |
| Tiempo estimado | 20–30 minutos solo la instalación del SO |

---

## Crear la USB booteable

### Desde Windows (Rufus)
1. Descargar Rufus: rufus.ie
2. Insertar USB → abrir Rufus
3. Dispositivo: tu USB
4. Seleccionar imagen ISO: el archivo `ubuntu-22.04.x-live-server-amd64.iso`
5. Esquema de partición: **GPT**
6. Sistema de destino: **UEFI**
7. Clic en INICIAR → Aceptar el aviso (borra la USB)
8. Esperar ~5 minutos → listo

### Desde Mac (Terminal)
```bash
# Identificar la USB (busca el disco que apareció al insertar)
diskutil list

# Desmontar (reemplazar diskX con tu disco, ej. disk2)
diskutil unmountDisk /dev/diskX

# Escribir imagen (reemplazar diskX y la ruta del ISO)
sudo dd if=~/Downloads/ubuntu-22.04.x-live-server-amd64.iso of=/dev/rdiskX bs=1m status=progress
```

---

## Arrancar desde USB

1. Conectar la USB al equipo nuevo
2. Encender el equipo y entrar a la BIOS/UEFI — la tecla varía por marca:
   - **Intel NUC / mini PC chino:** `F2` o `DEL` al encender
   - **Beelink / N100:** `F7` para menú de arranque, o `DEL` para BIOS
3. En el menú de arranque: seleccionar la USB (aparece como "UEFI: [nombre de la USB]")
4. En el menú de Ubuntu: seleccionar **Install Ubuntu Server**

---

## Particionado manual — SSD 256 GB

⚠️ **IMPORTANTE:** Usar siempre particionado **MANUAL** (no el automático). El automático de Ubuntu no crea la estructura que necesita Shomer.

### Esquema de particiones para 256 GB

Cuando el instalador pregunte sobre el disco, elegir **Custom storage layout** (diseño personalizado).

| # | Punto de montaje | Tamaño | Tipo de sistema |
|---|-----------------|--------|-----------------|
| 1 | `/boot/efi` | **1 GB** | FAT32 (partición EFI) |
| 2 | `/boot` | **1 GB** | ext4 |
| 3 | `/` (raíz) | **20 GB** | ext4 |
| 4 | `/var` | **20 GB** | ext4 — logs del sistema, Suricata, journal |
| 5 | `/opt` | **20 GB** | ext4 — código Shomer + entorno Python |
| 6 | `/home` | **10 GB** | ext4 — usuario usb_admin |
| 7 | `/srv` | **133 GB** | ext4 — **backups Restic, staging, restore** |
| 8 | `/tmp` | **4 GB** | ext4 |
| 9 | `swap` | **4 GB** | swap |
| 10 | `/storage` | **25 GB** | ext4 — bases de datos Shomer |

**Total: ~238 GB** (el SSD de 256 GB reporta ~238 GB reales tras formatear)

---

### Paso a paso en el instalador de Ubuntu

**1. Seleccionar el disco**

El instalador muestra el disco disponible (ej. `/dev/sda` o `/dev/nvme0n1`). Hacer clic sobre él.

**2. Elegir "Custom storage layout"**

No seleccionar "Use entire disk" — eso crea una sola partición y no sirve para Shomer.

**3. Crear cada partición**

Por cada partición de la tabla anterior:
- Clic en el espacio libre (free space)
- Clic en **Add GPT Partition**
- Ingresar el tamaño en GB
- Seleccionar el formato (ext4, FAT32, swap)
- Ingresar el punto de montaje

**Partición 1 — EFI** (obligatoria para UEFI):
```
Tamaño: 1 GB
Formato: FAT32
Montar como: /boot/efi
```

**Partición 2 — boot**:
```
Tamaño: 1 GB
Formato: ext4
Montar como: /boot
```

**Partición 3 — raíz**:
```
Tamaño: 20 GB
Formato: ext4
Montar como: /
```

**Partición 4 — var**:
```
Tamaño: 20 GB
Formato: ext4
Montar como: /var
```

**Partición 5 — opt**:
```
Tamaño: 20 GB
Formato: ext4
Montar como: /opt
```

**Partición 6 — home**:
```
Tamaño: 10 GB
Formato: ext4
Montar como: /home
```

**Partición 7 — srv** (backups — la más grande):
```
Tamaño: 133 GB  (o "el espacio restante menos 33 GB")
Formato: ext4
Montar como: /srv
```

**Partición 8 — tmp**:
```
Tamaño: 4 GB
Formato: ext4
Montar como: /tmp
```

**Partición 9 — swap**:
```
Tamaño: 4 GB
Formato: swap
(sin punto de montaje)
```

**Partición 10 — storage** (bases de datos):
```
Tamaño: 25 GB
Formato: ext4
Montar como: /storage
```

**4. Confirmar y formatear**

El instalador muestra un resumen antes de borrar el disco. Verificar que los puntos de montaje coinciden con la tabla. Confirmar → el instalador formatea y continúa.

---

## Configuración del sistema durante la instalación

### Usuario del sistema
```
Nombre completo: USB Admin
Nombre de usuario: usb_admin
Contraseña: Shomer2026!
Nombre del servidor: shomer-bogota  (o el nombre del cliente)
```
⚠️ Anotar la contraseña — se necesita para el primer login y para el script de instalación.

### OpenSSH
Cuando el instalador pregunte "Install OpenSSH server":
- ✅ **Marcar SÍ** — es obligatorio para acceso remoto y para Tailscale

### Paquetes adicionales del instalador
No instalar nada adicional en este paso. El script `install_shomer.sh` instala todo lo necesario.

---

## Después de instalar Ubuntu — antes de correr el instalador Shomer

### 1. Verificar que el equipo arrancó correctamente

```bash
# Ver las particiones creadas — debe coincidir con la tabla
lsblk

# Ver IP asignada por DHCP (para conectarse por SSH)
ip addr show
```

### 2. Conectar a Tailscale (para que Juan Pablo pueda tomar control remoto)

```bash
# Instalar Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Conectar con la llave de autenticación que manda Juan Pablo por WhatsApp
sudo tailscale up --authkey=tskey-auth-XXXX --ssh
```

Cuando terminen esos dos comandos, Juan Pablo puede conectarse desde Utah sin necesitar la IP local del equipo.

### 3. Verificar las particiones desde el servidor

```bash
df -h
```

Resultado esperado (aproximado):
```
Filesystem       Size  Used  Use%  Mounted on
/dev/nvme0n1p3    20G  2.0G   10%  /
/dev/nvme0n1p4    20G  200M    1%  /var
/dev/nvme0n1p5    20G  200M    1%  /opt
/dev/nvme0n1p6    10G  100M    1%  /home
/dev/nvme0n1p7   133G   20M    1%  /srv
/dev/nvme0n1p8   4.0G   10M    1%  /tmp
/dev/nvme0n1p10   25G   20M    1%  /storage
```

Si alguna partición no aparece o tiene un tamaño muy diferente: avisar antes de continuar.

---

## Diferencias respecto al esquema de 500 GB (referencia)

| Partición | 500 GB (lab .205) | 256 GB (campo) | Observación |
|-----------|-------------------|----------------|-------------|
| `/` | 25 GB | 20 GB | Suficiente — SO + código base |
| `/var` | 35 GB | 20 GB | Logrotate activo — Suricata no llena esto |
| `/opt` | 55 GB | 20 GB | venv + código = ~1.5 GB real |
| `/home` | 25 GB | 10 GB | Solo usuario usb_admin |
| `/srv` | 280 GB | 133 GB | **Backups Restic** — suficiente para hotel típico; escalar si el cliente tiene muchos equipos grandes |
| `/tmp` | 8 GB | 4 GB | Sin impacto |
| `/storage` | 43 GB | 25 GB | DBs Shomer — crecimiento lento |

**Regla práctica para campo:**
- El cliente tiene backups de **menos de 10 equipos** → 133 GB en `/srv` es suficiente
- El cliente tiene backups de **10 a 20 equipos** → considerar SSD de 500 GB o separar el B2 sync para no saturar
- B2 (nube) **no ocupa espacio local** después del sync — el instalador de Shomer puede configurarse para sincronizar inmediatamente y liberar local

---

## Si el instalador de Ubuntu no deja particionado manual

En algunos sistemas el instalador de Ubuntu Server puede no mostrar "Custom storage layout" si hay particiones previas en el disco. Solución:

```bash
# Desde la terminal de rescate del instalador (Ctrl+Alt+F2):
wipefs -a /dev/nvme0n1    # o /dev/sda si es SATA
# Volver al instalador (Ctrl+Alt+F1) y reiniciar el paso de disco
```

O desde una LiveUSB de Ubuntu Desktop:
```bash
sudo fdisk /dev/nvme0n1
# Comando d → eliminar todas las particiones
# Comando w → guardar y salir
```

---

## Continuar con la instalación de Shomer

Una vez Ubuntu está instalado y Tailscale conectado, seguir la guía:

📄 `Instalacion_Remota_Tailscale.md` → Parte 3 en adelante

O si la instalación es presencial:
📄 `SOPORTE_TECNICO.md` → Parte 1, Paso 1 en adelante

---

*USB Ingeniería SAS — guía de campo para instalación en SSD 256 GB.*  
*Variante del esquema estándar de 500 GB — no modifica el script `install_shomer.sh`.*  
*Versión mayo 2026.*
