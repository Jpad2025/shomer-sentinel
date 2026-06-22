#!/bin/bash
# =============================================================================
# install_shomer.sh — Instalación completa Shomer Sentinel 2.0
# =============================================================================
# Requisitos:
#   - Ubuntu 22.04 LTS (limpio o con Ubuntu instalado)
#   - Ejecutar como root: sudo bash install_shomer.sh
#   - El script debe estar dentro del paquete Shomer extraído:
#       shomer-YYYYMMDD/
#           tools/install_shomer.sh   ← este archivo
#           app/                      ← código fuente
#           config/                   ← nodos_gl.json etc.
#           ...
#
# Uso básico:
#   sudo bash tools/install_shomer.sh
#
# Variables de entorno opcionales (exportar antes de correr):
#   SERVICE_USER        Usuario del sistema para los servicios  (default: usb_admin)
#   INSTALL_WAZUH       Instalar Wazuh manager/indexer/dashboard (default: no)
#   SKIP_DOCKER         No instalar Docker ni shomer-agent      (default: no)
#   SKIP_FRONTPANEL     No instalar s1panel / pantalla S1       (default: no)
#   MGMT_IFACE          NIC de gestión                         (default: auto-detect)
#   MIRROR_IFACE        NIC espejo para Hunter                  (default: enp4s0)
# =============================================================================

set -euo pipefail

# ─── Colores ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${BLUE}[→]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗] ERROR: $*${NC}" >&2; exit 1; }

# ─── Variables configurables ──────────────────────────────────────────────────
SERVICE_USER="${SERVICE_USER:-usb_admin}"
INSTALL_WAZUH="${INSTALL_WAZUH:-no}"
SKIP_DOCKER="${SKIP_DOCKER:-no}"
SKIP_FRONTPANEL="${SKIP_FRONTPANEL:-no}"
MIRROR_IFACE="${MIRROR_IFACE:-enp4s0}"

INSTALL_DIR="/opt/network_monitor"
STORAGE_DIR="/storage"
LOG_DIR="/var/log/shomer"
CONF_DIR="/etc/shomer"
RESTIC_REPO="/srv/shomer_backups/staging"
RESTIC_PASS_FILE="/home/${SERVICE_USER}/.restic-local-pass"
NGINX_CONF="/etc/nginx/sites-available/network-monitor"
SSL_DIR="/etc/nginx/ssl"

# Directorio raíz del paquete (un nivel arriba del script)
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ─── Checks previos ───────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Shomer Sentinel 2.0 — Instalador          ${NC}"
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo ""

[[ $EUID -ne 0 ]] && die "Ejecutar como root: sudo bash $0"

. /etc/os-release 2>/dev/null || true
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "22.04" ]]; then
    warn "Este script fue probado en Ubuntu 22.04. Continuando de todas formas..."
fi

[[ -d "$PKG_DIR/app" ]] || die "No se encuentra $PKG_DIR/app — asegúrate de correr el script desde el paquete Shomer"

# Verificar internet — instalar ping si no está disponible
command -v ping &>/dev/null || apt-get install -y -qq iputils-ping &>/dev/null
ping -c1 -W3 8.8.8.8 &>/dev/null || curl -s --max-time 5 https://example.com -o /dev/null || die "Sin conexión a internet"

info "Paquete fuente : $PKG_DIR"
info "Usuario servicio: $SERVICE_USER"
info "Wazuh          : $INSTALL_WAZUH"
info "Docker/Agente  : $([ "$SKIP_DOCKER" = "yes" ] && echo "omitido" || echo "sí")"
info "Pantalla S1    : $([ "$SKIP_FRONTPANEL" = "yes" ] && echo "omitida" || echo "auto (Holtek 04d9:fd01)")"
echo ""

# ─── 1. Usuario del sistema ───────────────────────────────────────────────────
info "Creando usuario $SERVICE_USER..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -m -s /bin/bash -G sudo "$SERVICE_USER"
    echo "${SERVICE_USER}:Shomer2026!" | chpasswd
    log "Usuario $SERVICE_USER creado (contraseña: Shomer2026! — cambiar post-instalación)"
else
    log "Usuario $SERVICE_USER ya existe"
fi

# ─── 2. Paquetes apt ──────────────────────────────────────────────────────────
info "Actualizando apt e instalando dependencias..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

apt-get install -y -qq \
    python3.10 python3.10-dev python3.10-venv \
    nginx \
    redis-server \
    restic \
    nmap \
    snmp snmpd snmp-mibs-downloader \
    suricata suricata-update \
    cifs-utils samba-common samba-common-bin \
    libpcap-dev \
    openssl \
    curl wget git \
    rsync \
    sqlite3 \
    jq \
    lsof \
    net-tools \
    ufw \
    fail2ban \
    2>/dev/null

log "Paquetes apt instalados"

# ─── 3. Docker ────────────────────────────────────────────────────────────────
if [[ "$SKIP_DOCKER" != "yes" ]]; then
    info "Instalando Docker..."
    if ! command -v docker &>/dev/null; then
        curl -fsSL https://get.docker.com | bash -s -- --quiet
        usermod -aG docker "$SERVICE_USER"
        systemctl enable docker --quiet
        log "Docker instalado"
    else
        log "Docker ya instalado"
    fi
fi

# ─── 4. Wazuh (opcional) ─────────────────────────────────────────────────────
if [[ "$INSTALL_WAZUH" == "yes" ]]; then
    info "Instalando Wazuh 4.14 (esto toma varios minutos)..."
    curl -sO https://packages.wazuh.com/4.x/wazuh-install.sh
    curl -sO https://packages.wazuh.com/4.x/config.yml
    # Instalación all-in-one para lab/SMB
    bash wazuh-install.sh -a -i 2>/dev/null || warn "Wazuh: revisar instalación manualmente"
    rm -f wazuh-install.sh config.yml
    log "Wazuh instalado"
else
    info "Wazuh omitido (INSTALL_WAZUH=yes para incluirlo)"
fi

# ─── 5. Estructura de directorios ─────────────────────────────────────────────
info "Creando estructura de directorios..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$STORAGE_DIR/db"
mkdir -p "$STORAGE_DIR/shomer-agent"
mkdir -p "$LOG_DIR"
mkdir -p "$CONF_DIR"
mkdir -p "/srv/shomer_backups/staging"
mkdir -p "/srv/shomer_backups/staging_ssh"
mkdir -p "/srv/shomer_restore"
mkdir -p "$SSL_DIR"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$STORAGE_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
chown root:root "$CONF_DIR"
chmod 750 "$CONF_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "/srv/shomer_backups"
chown -R "$SERVICE_USER:$SERVICE_USER" "/srv/shomer_restore"

log "Directorios creados"

# ─── 6. Copiar código ─────────────────────────────────────────────────────────
info "Copiando código Shomer a $INSTALL_DIR..."
rsync -a --delete \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    "$PKG_DIR/" "$INSTALL_DIR/"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
log "Código copiado"

# ─── 6b. Copiar código shomer-agent ──────────────────────────────────────────
if [[ "$SKIP_DOCKER" != "yes" ]] && [[ -d "$PKG_DIR/shomer-agent" ]]; then
    info "Copiando shomer-agent a $STORAGE_DIR/shomer-agent..."
    rsync -a --delete \
        --exclude='.env' \
        --exclude='data/' \
        "$PKG_DIR/shomer-agent/" "$STORAGE_DIR/shomer-agent/"
    mkdir -p "$STORAGE_DIR/shomer-agent/data/backups" \
             "$STORAGE_DIR/shomer-agent/data/downloads"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$STORAGE_DIR/shomer-agent"
    log "Código shomer-agent copiado"

    info "Construyendo imagen Docker del agente (puede tardar 2-3 min)..."
    cd "$STORAGE_DIR/shomer-agent"
    docker compose build --quiet 2>/dev/null \
        && log "Imagen Docker construida" \
        || warn "Docker build falló — revisar manualmente: cd $STORAGE_DIR/shomer-agent && docker compose build"
    cd - > /dev/null
elif [[ "$SKIP_DOCKER" != "yes" ]]; then
    warn "No se encontró $PKG_DIR/shomer-agent — agente no copiado"
fi

# ─── 6c. Inicializar bases de datos ──────────────────────────────────────────
info "Inicializando bases de datos..."

python3 - << 'PYINIT'
import sqlite3, os, json, hashlib

STORAGE = "/storage/db"
os.makedirs(STORAGE, exist_ok=True)

# ── network_monitor.db ────────────────────────────────────────────────────────
conn = sqlite3.connect(f"{STORAGE}/network_monitor.db")

conn.executescript("""
CREATE TABLE IF NOT EXISTS system_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'operator',
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address      TEXT NOT NULL,
    name            TEXT,
    device_type     TEXT,
    ssh_user        TEXT,
    ssh_pass        TEXT,
    snmp_community  TEXT,
    reboot_method   TEXT DEFAULT 'ssh',
    no_reboot       INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS infra_nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address      TEXT UNIQUE NOT NULL,
    name            TEXT,
    device_type     TEXT,
    status          TEXT DEFAULT 'unknown',
    last_seen       TEXT,
    ssh_user        TEXT,
    ssh_pass        TEXT,
    check_interval  INTEGER DEFAULT 10,
    fail_threshold  INTEGER DEFAULT 3,
    reboot_method   TEXT DEFAULT 'ssh',
    snmp_community        TEXT,
    snmp_community_write  TEXT,
    is_router       INTEGER DEFAULT 0,
    no_reboot       INTEGER DEFAULT 0,
    maintenance     INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS discovered_devices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address    TEXT NOT NULL,
    mac_address   TEXT,
    vendor        TEXT,
    hostname      TEXT,
    open_ports    TEXT,
    inferred_type TEXT,
    status        TEXT,
    source        TEXT,
    first_seen    TEXT,
    last_seen     TEXT
);
CREATE TABLE IF NOT EXISTS blocked_ips (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address       TEXT NOT NULL,
    reason           TEXT,
    blocked_by       TEXT,
    firewall_blocked INTEGER DEFAULT 0,
    blocked_at       TEXT DEFAULT (datetime('now')),
    unblocked_at     TEXT
);
CREATE TABLE IF NOT EXISTS backup_devices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT,
    ip_address          TEXT,
    protocol            TEXT,
    port                INTEGER,
    username            TEXT,
    password            TEXT,
    remote_path         TEXT,
    schedule_enabled    INTEGER DEFAULT 0,
    schedule_time       TEXT,
    schedule_b2_enabled INTEGER DEFAULT 0,
    last_snapshot_id    TEXT,
    last_files_count    INTEGER,
    last_size_mb        REAL,
    last_duration_sec   REAL,
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS device_status (
    id            INTEGER NOT NULL,
    device_id     INTEGER NOT NULL,
    status        VARCHAR(7) NOT NULL,
    response_time FLOAT,
    uptime        VARCHAR(50),
    cpu_usage     FLOAT,
    memory_usage  FLOAT,
    last_check    DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(device_id) REFERENCES devices (id)
);
CREATE TABLE IF NOT EXISTS devices_inventory (
    mac_address TEXT PRIMARY KEY,
    ip_address  TEXT,
    hostname    TEXT,
    last_seen   TIMESTAMP,
    promoted    INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS event_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,
    message    TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events_log (
    id         INTEGER NOT NULL,
    device_id  INTEGER NOT NULL,
    event_type VARCHAR(17) NOT NULL,
    description TEXT,
    severity   VARCHAR(8) NOT NULL,
    created_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(device_id) REFERENCES devices (id)
);
CREATE TABLE IF NOT EXISTS failsafe_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS recovery_actions (
    id          INTEGER NOT NULL,
    device_id   INTEGER NOT NULL,
    action_type VARCHAR(13) NOT NULL,
    command     TEXT,
    success     BOOLEAN,
    output      TEXT,
    executed_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(device_id) REFERENCES devices (id)
);
CREATE TABLE IF NOT EXISTS server_metrics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cpu        REAL,
    ram        REAL,
    disk       REAL,
    recorded_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ip          TEXT,
    mac         TEXT,
    hostname    TEXT,
    vendor      TEXT,
    os_family   TEXT,
    cpu         TEXT,
    ram         TEXT,
    disk        TEXT,
    serial      TEXT,
    software    TEXT,
    last_seen   TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
""")

# Valores por defecto system_state (INSERT OR IGNORE — no pisa config existente)
defaults = [
    ("modules.enabled",                 '["guardian","hunter","tracker","protector"]'),
    ("guardian.fail_threshold",         "3"),
    ("guardian.cooldown_sec",           "300"),
    ("guardian.ping_count",             "4"),
    ("guardian.subnets",                "[]"),
    ("guardian.telegram_token",         ""),
    ("guardian.telegram_chat_id",       ""),
    ("hunter.auto_block_enabled",       "false"),
    ("hunter.auto_block_min_severity",  "2"),
    ("hunter.auto_block_only_external", "true"),
    ("hunter.auto_block_exceptions",    "[]"),
    ("hunter.firewall_ip",              ""),
    ("hunter.firewall_user",            ""),
    ("hunter.firewall_pass",            ""),
    ("hunter.firewall_port",            "22"),
    ("hunter.firewall_timeout",         "10"),
    ("hunter.integration_key",          ""),
    ("hunter.interfaces",               "[]"),
    ("hunter.subnets",                  "[]"),
    ("hunter.wazuh_dashboard_url",      ""),
    ("protector.b2_account_id",         ""),
    ("protector.b2_app_key",            ""),
    ("protector.b2_bucket",             ""),
    ("protector.b2_password",           ""),
    ("tracker.subnets",                 "[]"),
]
conn.executemany("INSERT OR IGNORE INTO system_state (key, value) VALUES (?, ?)", defaults)

# Usuario root de fábrica (INSERT OR IGNORE — no pisa si ya existe)
factory_hash = hashlib.sha256("shomer2026".encode()).hexdigest()
conn.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
             ("root", factory_hash, "admin"))

conn.commit()
conn.close()

# ── inventory.db ──────────────────────────────────────────────────────────────
inv = sqlite3.connect(f"{STORAGE}/inventory.db")
inv.executescript("""
CREATE TABLE IF NOT EXISTS assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ip          TEXT,
    mac         TEXT,
    hostname    TEXT,
    vendor      TEXT,
    os_family   TEXT,
    cpu         TEXT,
    ram         TEXT,
    disk        TEXT,
    serial      TEXT,
    software    TEXT,
    last_seen   TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    closed_at   TEXT,
    assets_json TEXT
);
CREATE TABLE IF NOT EXISTS network_credentials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,
    protocol    TEXT,
    username    TEXT,
    password    TEXT,
    port        INTEGER,
    created_at  TEXT DEFAULT (datetime('now'))
);
""")
inv.commit()
inv.close()

print("  Bases de datos inicializadas OK")
PYINIT

chown -R "$SERVICE_USER:$SERVICE_USER" "$STORAGE_DIR/db"
log "Bases de datos inicializadas"

# ─── 7. Entorno virtual Python ────────────────────────────────────────────────
info "Creando virtualenv e instalando dependencias Python..."
sudo -u "$SERVICE_USER" python3.10 -m venv "$INSTALL_DIR/venv"

REQS="$INSTALL_DIR/requirements.txt"
if [[ ! -f "$REQS" ]]; then
    die "No se encuentra $REQS — el paquete debe incluir requirements.txt"
fi

sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet -r "$REQS"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet pyserial 2>/dev/null || true
log "Python deps instalados ($(wc -l < "$REQS") paquetes)"

# ─── 7b. Pantalla frontal AceMagic S1 (s1panel + LED) ────────────────────────
if [[ "$SKIP_FRONTPANEL" != "yes" ]] && lsusb -d 04d9:fd01 &>/dev/null; then
    info "Mini PC AceMagic S1 detectado — instalando pantalla frontal..."
    if ! command -v snap &>/dev/null; then
        apt-get install -y -qq snapd
        systemctl enable --now snapd.socket snapd.seeded.service 2>/dev/null || true
    fi
    HOST_LABEL="$(hostname -s)"
    if bash "$INSTALL_DIR/tools/frontpanel/install_shomer_frontpanel.sh" "$HOST_LABEL"; then
        log "Pantalla frontal S1 configurada ($HOST_LABEL)"
    else
        warn "Pantalla frontal — revisar: bash $INSTALL_DIR/tools/frontpanel/install_shomer_frontpanel.sh"
    fi
elif [[ "$SKIP_FRONTPANEL" == "yes" ]]; then
    info "Pantalla S1 omitida (SKIP_FRONTPANEL=yes)"
else
    info "Sin Holtek 04d9:fd01 — pantalla S1 no instalada (servidor genérico)"
fi

# ─── 8. OUI database (para Tracker) ──────────────────────────────────────────
if [[ ! -f "$STORAGE_DIR/db/oui.txt" ]]; then
    info "Descargando base de datos OUI IEEE..."
    curl -sfL "https://standards-oui.ieee.org/oui/oui.txt" -o "$STORAGE_DIR/db/oui.txt" 2>/dev/null || \
        warn "No se pudo descargar oui.txt — Tracker mostrará fabricante desconocido hasta que esté disponible"
fi

# ─── 9. Restic — inicializar repositorio local ────────────────────────────────
info "Inicializando repositorio Restic local..."
RESTIC_PASS="$(openssl rand -base64 32)"
echo "$RESTIC_PASS" > "$RESTIC_PASS_FILE"
chmod 600 "$RESTIC_PASS_FILE"
chown "$SERVICE_USER:$SERVICE_USER" "$RESTIC_PASS_FILE"

if ! RESTIC_PASSWORD="$RESTIC_PASS" restic -r "$RESTIC_REPO" cat config &>/dev/null; then
    RESTIC_PASSWORD="$RESTIC_PASS" restic -r "$RESTIC_REPO" init --quiet
    log "Repositorio Restic inicializado en $RESTIC_REPO"
else
    log "Repositorio Restic ya existía"
fi

# ─── 10. Certificado SSL auto-firmado ─────────────────────────────────────────
info "Generando certificado SSL auto-firmado..."
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout "$SSL_DIR/shomer-lab.key" \
    -out "$SSL_DIR/shomer-lab.crt" \
    -subj "/C=CO/ST=Bogota/O=USB Ingenieria/CN=shomer.local" \
    2>/dev/null
chmod 600 "$SSL_DIR/shomer-lab.key"
log "Certificado SSL generado (válido 10 años)"

# ─── 11. Nginx ────────────────────────────────────────────────────────────────
info "Configurando nginx..."
cat > "$NGINX_CONF" << 'NGINX'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 301 https://$host:8443$request_uri;
}

server {
    listen 8443 ssl;
    listen [::]:8443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/shomer-lab.crt;
    ssl_certificate_key /etc/nginx/ssl/shomer-lab.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
    expires off;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $http_host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
        proxy_redirect     off;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }
}
NGINX

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/network-monitor
rm -f /etc/nginx/sites-enabled/default
nginx -t -q && log "Nginx configurado"

# ─── 12. Logrotate Suricata ───────────────────────────────────────────────────
cat > /etc/logrotate.d/suricata << 'LR'
/var/log/suricata/*.log
/var/log/suricata/*.json
{
    rotate 7
    daily
    maxsize 500M
    missingok
    compress
    copytruncate
    sharedscripts
    postrotate
        /bin/kill -HUP $(cat /var/run/suricata.pid 2>/dev/null) 2>/dev/null || true
    endscript
}
LR

# ─── 13. JWT Secret y runtime env ────────────────────────────────────────────
info "Generando JWT secret y configuración de runtime..."
JWT_SECRET="$(openssl rand -hex 32)"

cat > "$CONF_DIR/shomer-runtime.env" << ENV
JWT_SECRET=${JWT_SECRET}
SHOMER_JWT_EXPIRE_HOURS=1
SHOMER_BEHIND_PROXY=1
SHOMER_PROXY_TRUSTED_HOSTS=127.0.0.1,::1
ENV

chmod 640 "$CONF_DIR/shomer-runtime.env"
chown root:"$SERVICE_USER" "$CONF_DIR/shomer-runtime.env"
log "JWT secret generado"

# ─── 14. Watchdog script ─────────────────────────────────────────────────────
cat > /usr/local/bin/shomer-health-check.sh << 'WD'
#!/bin/bash
LOG="/var/log/shomer/watchdog.log"
TS=$(date '+%Y-%m-%d %H:%M:%S')

if ! curl -sf --max-time 5 http://localhost:8000/health > /dev/null 2>&1; then
    echo "[$TS] ERROR: 8000 no responde — reiniciando shomer-guardian" >> "$LOG"
    systemctl restart shomer-guardian.service
    sleep 8
    curl -sf --max-time 5 http://localhost:8000/health > /dev/null 2>&1 \
        && echo "[$TS] OK: reiniciado exitosamente" >> "$LOG" \
        || echo "[$TS] CRITICAL: no levantó tras reinicio" >> "$LOG"
fi

if ! curl -sf --max-time 5 http://localhost:8001/login/ok > /dev/null 2>&1; then
    echo "[$TS] WARN: 8001 no responde — reiniciando shomer-tools" >> "$LOG"
    systemctl restart shomer-tools.service
fi
WD
chmod +x /usr/local/bin/shomer-health-check.sh

# ─── 15. Systemd units ───────────────────────────────────────────────────────
info "Instalando unidades systemd..."

cat > /etc/systemd/system/shomer-guardian.service << SVC
[Unit]
Description=SHOMER Core API — Guardian + Hunter, puerto 8000
After=network.target redis-server.service
Wants=redis-server.service

[Service]
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStartPre=/bin/bash -c 'fuser -k 8000/tcp 2>/dev/null || true'
ExecStartPre=/bin/sleep 1
ExecStart=${INSTALL_DIR}/venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
Environment=PYTHONPATH=${INSTALL_DIR}
EnvironmentFile=${CONF_DIR}/shomer-runtime.env
Environment=RESTIC_PASSWORD_FILE=${RESTIC_PASS_FILE}
Restart=always
RestartSec=10
MemoryMax=700M
MemorySwapMax=0
StandardOutput=append:${LOG_DIR}/api.log
StandardError=append:${LOG_DIR}/api.log

[Install]
WantedBy=multi-user.target
SVC

cat > /etc/systemd/system/shomer-tools.service << SVC
[Unit]
Description=SHOMER Tools API — Tracker + Protector, puerto 8001
After=network.target shomer-guardian.service
Wants=shomer-guardian.service

[Service]
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStartPre=/bin/bash -c 'fuser -k 8001/tcp 2>/dev/null || true'
ExecStartPre=/bin/sleep 1
ExecStart=${INSTALL_DIR}/venv/bin/python -m uvicorn app.api.main_tools:app --host 127.0.0.1 --port 8001
Environment=PYTHONPATH=${INSTALL_DIR}
EnvironmentFile=${CONF_DIR}/shomer-runtime.env
Environment=RESTIC_PASSWORD_FILE=${RESTIC_PASS_FILE}
Restart=always
RestartSec=15
MemoryMax=800M
MemorySwapMax=0
StandardOutput=append:${LOG_DIR}/tools_api.log
StandardError=append:${LOG_DIR}/tools_api.log

[Install]
WantedBy=multi-user.target
SVC

cat > /etc/systemd/system/shomer-health-watchdog.service << SVC
[Unit]
Description=Shomer health watchdog
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/shomer-health-check.sh
User=root
SVC

cat > /etc/systemd/system/shomer-health-watchdog.timer << SVC
[Unit]
Description=Shomer watchdog cada 30 segundos

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
AccuracySec=5s
Unit=shomer-health-watchdog.service

[Install]
WantedBy=timers.target
SVC

if [[ "$SKIP_DOCKER" != "yes" ]]; then
cat > /etc/systemd/system/shomer-agent.service << SVC
[Unit]
Description=Shomer Agent — Bot Telegram multi-vendor
After=docker.service shomer-guardian.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=${STORAGE_DIR}/shomer-agent
ExecStartPre=/usr/bin/docker compose build --quiet
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=on-failure
RestartSec=15
User=${SERVICE_USER}

[Install]
WantedBy=multi-user.target
SVC
fi

systemctl daemon-reload
log "Unidades systemd instaladas"

# ─── 16. Habilitar e iniciar servicios ───────────────────────────────────────
info "Habilitando e iniciando servicios..."

systemctl enable --quiet redis-server nginx suricata
systemctl enable --quiet shomer-guardian shomer-tools shomer-health-watchdog.timer

systemctl restart redis-server
systemctl restart nginx
systemctl start shomer-guardian || warn "shomer-guardian no arrancó — revisar: journalctl -u shomer-guardian -n 30"
sleep 3
systemctl start shomer-tools || warn "shomer-tools no arrancó — revisar: journalctl -u shomer-tools -n 30"
systemctl start shomer-health-watchdog.timer

log "Servicios iniciados"

# ─── 17. UFW — firewall con subnet auto-detectada ────────────────────────────
info "Configurando UFW..."

# Detectar interfaz y subnet de gestión
_MGMT_IFACE="${MGMT_IFACE:-$(ip route show default 2>/dev/null | awk '/^default/{print $5; exit}')}"
_MGMT_CIDR=""
_MGMT_SUBNET=""

if [[ -n "$_MGMT_IFACE" ]]; then
    _MGMT_CIDR=$(ip -4 addr show dev "$_MGMT_IFACE" 2>/dev/null | awk '/inet /{print $2; exit}')
fi
if [[ -n "$_MGMT_CIDR" ]]; then
    _MGMT_SUBNET=$(python3 -c "import ipaddress; print(ipaddress.ip_network('$_MGMT_CIDR', strict=False))" 2>/dev/null)
fi

ufw --force reset >/dev/null 2>&1
ufw default deny incoming  >/dev/null
ufw default allow outgoing >/dev/null
ufw default deny routed    >/dev/null

# Tailscale — siempre presente como fallback de acceso remoto
ufw allow from 100.64.0.0/10 to any port 22   comment "SSH Tailscale"     >/dev/null
ufw allow from 100.64.0.0/10 to any port 80   comment "HTTP redirect Tailscale" >/dev/null
ufw allow from 100.64.0.0/10 to any port 8443 comment "Panel HTTPS Tailscale"   >/dev/null

if [[ -n "$_MGMT_SUBNET" ]]; then
    ufw allow from "$_MGMT_SUBNET" to any port 22   comment "SSH gestion LAN"       >/dev/null
    ufw allow from "$_MGMT_SUBNET" to any port 80   comment "HTTP redirect LAN"     >/dev/null
    ufw allow from "$_MGMT_SUBNET" to any port 8443 comment "Panel HTTPS LAN"       >/dev/null
    info "Subnet gestión: $_MGMT_SUBNET (iface: $_MGMT_IFACE)"
else
    warn "No se pudo detectar subnet — solo Tailscale habilitado. Agregar LAN manualmente:"
    warn "  ufw allow from <subnet>/24 to any port 22,80,8443"
fi

# Bloquear puertos internos de API explícitamente
ufw deny 8000/tcp comment "API Guardian — solo loopback" >/dev/null
ufw deny 8001/tcp comment "API Tools — solo loopback"    >/dev/null

# Pantalla S1 — GUI s1panel (HTTP, puerto 8686)
if lsusb -d 04d9:fd01 &>/dev/null; then
    ufw allow from 100.64.0.0/10 to any port 8686 comment "s1panel GUI Tailscale" >/dev/null
    if [[ -n "$_MGMT_SUBNET" ]]; then
        ufw allow from "$_MGMT_SUBNET" to any port 8686 comment "s1panel GUI LAN" >/dev/null
    fi
fi

ufw --force enable >/dev/null 2>&1
log "UFW configurado ($(ufw status | grep -c ALLOW) reglas ALLOW activas)"

# ─── 17b. fail2ban ───────────────────────────────────────────────────────────
info "Configurando fail2ban..."

# Filtro personalizado para intentos fallidos de login al panel
cat > /etc/fail2ban/filter.d/nginx-shomer-login.conf << 'F2B'
[Definition]
failregex = ^<HOST> .* "POST /auth/login HTTP/[0-9\.]+" 401
ignoreregex =
F2B

# Jails: SSH (1h) + login panel (30 min)
cat > /etc/fail2ban/jail.d/shomer.conf << 'F2B'
[sshd]
enabled  = true
bantime  = 3600
maxretry = 5

[nginx-shomer-login]
enabled   = true
port      = http,https,8443
filter    = nginx-shomer-login
logpath   = /var/log/nginx/access.log
bantime   = 1800
maxretry  = 5
findtime  = 120
F2B

systemctl enable --quiet fail2ban
systemctl restart fail2ban
sleep 2
systemctl is-active fail2ban >/dev/null \
    && log "fail2ban activo (SSH 1h ban, panel login 30min ban)" \
    || warn "fail2ban no arrancó — revisar: journalctl -u fail2ban -n 20"

# ─── 18. Verificación rápida ─────────────────────────────────────────────────
echo ""
info "Verificando servicios..."
sleep 5
ALL_OK=true
for svc in shomer-guardian shomer-tools nginx redis-server; do
    STATE=$(systemctl is-active "$svc" 2>/dev/null)
    if [[ "$STATE" == "active" ]]; then
        echo -e "  ${GREEN}✓${NC} $svc"
    else
        echo -e "  ${RED}✗${NC} $svc ($STATE)"
        ALL_OK=false
    fi
done

# Detectar IP de gestión
MGMT_IP=$(ip -4 addr show | grep "inet " | grep -v "127.0.0.1\|172.17" | awk '{print $2}' | cut -d/ -f1 | head -1)

# ─── 19. Resumen final ───────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}   Shomer Sentinel 2.0 — Instalación lista   ${NC}"
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo ""
echo -e "  Panel (HTTPS): ${YELLOW}https://${MGMT_IP}:8443/setup/${NC}"
echo -e "  Panel (HTTP) : ${YELLOW}http://${MGMT_IP}:8000/setup/${NC}"
echo ""
echo "  Credenciales iniciales: root / shomer2026"
echo "  JWT Secret guardado en: $CONF_DIR/shomer-runtime.env"
echo "  Restic password en    : $RESTIC_PASS_FILE"
echo ""
echo "  Próximos pasos:"
echo "  1. Abrir /setup/ en el navegador y configurar el sitio"
echo "  2. Cambiar contraseña admin desde el panel"
echo "  3. Configurar IPs definitivas con:"
echo "     sudo bash $INSTALL_DIR/tools/factory_reset_network.sh"
echo ""

if [[ "$SKIP_FRONTPANEL" != "yes" ]] && lsusb -d 04d9:fd01 &>/dev/null 2>&1; then
    echo "  Pantalla S1 (AceMagic):"
    echo "  • s1panel — logo Shomer + sensores"
    echo "  • shomer-frontpanel — WAN/AP en pantalla"
    echo "  • shomer-led-strip — tira RGB arcoíris"
    echo ""
fi

if [[ "$SKIP_DOCKER" != "yes" ]]; then
    echo "  Bot Telegram (shomer-agent):"
    echo "  1. Copiar /storage/shomer-agent/.env.example → .env y completar tokens"
    echo "  2. sudo systemctl enable --now shomer-agent"
    echo ""
fi

if [[ "$ALL_OK" == "true" ]]; then
    echo -e "${GREEN}  ✓ Todos los servicios activos${NC}"
else
    echo -e "${YELLOW}  ! Algunos servicios no arrancaron — revisar con journalctl${NC}"
fi
echo ""
