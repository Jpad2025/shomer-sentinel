#!/bin/bash
# deploy.sh — Actualiza servidores Shomer desde .205
#
# REGLA CRÍTICA (docs/REGLAS_DEPLOY.md):
#   - PRODUCCIÓN (Hotel Ópera): solo con autorización explícita de Juan Pablo.
#   - Deploy = SOLO código app/ (+ agente sin .env/data). NUNCA BD, SITE.md,
#     credenciales ni config de sitio del cliente.
#
# Uso: ./tools/deploy.sh [ip_tailscale]
#      Sin argumento: actualiza servidores en servers.txt EXCEPTO producción
#      Con IP:        actualiza solo ese servidor
# Producción autorizada: SHOMER_DEPLOY_AUTHORIZED=1 ./tools/deploy.sh 100.103.148.119

set -e

# IPs de producción — deploy requiere SHOMER_DEPLOY_AUTHORIZED=1
PRODUCTION_IPS=("100.103.148.119")

REPO_DIR="/opt/network_monitor"
SERVERS_FILE="$REPO_DIR/tools/servers.txt"
REMOTE_USER="usb_admin"
REMOTE_DIR="/opt/network_monitor"
AGENT_DIR="/storage/shomer-agent"
SSH_KEY="$HOME/.ssh/id_ed25519_shomer"
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }
err()  { echo -e "${RED}[deploy]${NC} $1"; }

_is_production() {
    local ip=$1
    for p in "${PRODUCTION_IPS[@]}"; do
        [[ "$ip" == "$p" ]] && return 0
    done
    return 1
}

deploy_server() {
    local ip=$1
    local name=$2
    local key="$SSH_KEY"

    if [[ "$ip" == "100.103.148.119" ]]; then
        key="$HOME/.ssh/id_rsa_shomer"
    fi
    local opts="-i $key -o StrictHostKeyChecking=no -o ConnectTimeout=10"

    if _is_production "$ip" && [[ "${SHOMER_DEPLOY_AUTHORIZED:-}" != "1" ]]; then
        err "BLOQUEADO: $name ($ip) es PRODUCCIÓN."
        err "Requiere autorización de Juan Pablo:"
        err "  SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh $ip"
        err "Ver docs/REGLAS_DEPLOY.md — no incluir config de sitio, solo código app/"
        return 1
    fi

    log "→ Desplegando en $name ($ip)..."

    # 1. Sincronizar código app/
    rsync -az --delete \
        --exclude='*.db' --exclude='*.db-*' \
        --exclude='.env' --exclude='*.env' \
        --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='venv/' --exclude='*.log' \
        -e "ssh $opts" \
        "$REPO_DIR/app/" \
        "$REMOTE_USER@$ip:$REMOTE_DIR/app/"

    # 2. Sincronizar pantalla frontal S1 (tools + units systemd)
    rsync -az \
        --exclude='__pycache__' --exclude='*.pyc' \
        -e "ssh $opts" \
        "$REPO_DIR/tools/frontpanel/" \
        "$REMOTE_USER@$ip:$REMOTE_DIR/tools/frontpanel/"
    rsync -az \
        -e "ssh $opts" \
        "$REPO_DIR/etc/shomer-frontpanel.service" \
        "$REPO_DIR/etc/shomer-led-strip.service" \
        "$REMOTE_USER@$ip:$REMOTE_DIR/etc/"

    # 3. Sincronizar código agente (sin data/ ni .env)
    rsync -az --delete \
        --exclude='data/' --exclude='.env' \
        --exclude='__pycache__' --exclude='*.pyc' \
        -e "ssh $opts" \
        "$AGENT_DIR/" \
        "$REMOTE_USER@$ip:$AGENT_DIR/"

    # 4. Actualizar TRUSTED_HOSTS y CORS con IP Tailscale del servidor remoto
    ssh $opts -n "$REMOTE_USER@$ip" "
        TS_IP=\$(sudo tailscale ip -4 2>/dev/null || echo '')
        LAN_IP=\$(hostname -I | awk '{print \$1}')
        RUNTIME=/etc/shomer/shomer-runtime.env
        if [[ -n \"\$TS_IP\" && -f \"\$RUNTIME\" ]]; then
            sudo sed -i \"s|SHOMER_TRUSTED_HOSTS=.*|SHOMER_TRUSTED_HOSTS=\${LAN_IP},localhost,127.0.0.1,\${TS_IP}|\" \"\$RUNTIME\"
            sudo sed -i \"s|SHOMER_CORS_ORIGINS=.*|SHOMER_CORS_ORIGINS=https://\${LAN_IP}:8443,https://\${TS_IP}:8443|\" \"\$RUNTIME\"
        fi
    "

    # 5. Mini PC AceMagic S1 — pyserial + servicios frontpanel
    ssh $opts -n "$REMOTE_USER@$ip" "
        if lsusb -d 04d9:fd01 &>/dev/null; then
            if [[ -x $REMOTE_DIR/venv/bin/pip ]]; then
                sudo $REMOTE_DIR/venv/bin/pip install -q pyserial 2>/dev/null || true
            fi
            sudo ufw allow from 100.64.0.0/10 to any port 8686 comment 's1panel GUI Tailscale' 2>/dev/null || true
            LAN_SUB=\$(ip -4 route show dev \$(ip -4 route show default | awk '{print \$5}' | head -1) 2>/dev/null | awk '/proto kernel/ {print \$1; exit}')
            if [[ -n \"\$LAN_SUB\" ]]; then
                sudo ufw allow from \"\$LAN_SUB\" to any port 8686 comment 's1panel GUI LAN' 2>/dev/null || true
            else
                sudo ufw allow from 192.168.1.0/24 to any port 8686 comment 's1panel GUI LAN' 2>/dev/null || true
            fi
            NEED=0
            sudo test -f /root/snap/s1panel/current/themes/shomer/shomer.json || NEED=1
            systemctl is-enabled shomer-led-strip &>/dev/null || NEED=1
            if [[ \"\$NEED\" -eq 1 ]]; then
                echo 'Instalando / actualizando tema Shomer s1panel...'
                sudo bash $REMOTE_DIR/tools/frontpanel/install_shomer_frontpanel.sh $name
            else
                sudo cp $REMOTE_DIR/etc/shomer-frontpanel.service /etc/systemd/system/
                sudo cp $REMOTE_DIR/etc/shomer-led-strip.service /etc/systemd/system/
                sudo systemctl daemon-reload
                sudo systemctl enable shomer-frontpanel shomer-led-strip 2>/dev/null || true
                sudo systemctl restart shomer-frontpanel shomer-led-strip 2>/dev/null || true
            fi
        fi
    "

    # 6. Reiniciar servicios remotos
    ssh $opts -n \
        "$REMOTE_USER@$ip" \
        "sudo systemctl restart shomer-guardian shomer-tools && \
         sudo docker compose -f $AGENT_DIR/docker-compose.yml restart 2>/dev/null; \
         echo 'Servicios reiniciados'"

    log "✅ $name actualizado"
}

# Argumento opcional: IP específica
TARGET_IP="${1:-}"

if [[ -n "$TARGET_IP" ]]; then
    TARGET_NAME="$TARGET_IP"
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
        ip=$(echo "$line" | awk '{print $1}')
        if [[ "$ip" == "$TARGET_IP" ]]; then
            TARGET_NAME=$(echo "$line" | awk '{print $2}')
            break
        fi
    done < "$SERVERS_FILE"
    deploy_server "$TARGET_IP" "$TARGET_NAME"
else
    # Leer servers.txt y desplegar a todos
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
        ip=$(echo "$line" | awk '{print $1}')
        name=$(echo "$line" | awk '{print $2}')
        if _is_production "$ip" && [[ "${SHOMER_DEPLOY_AUTHORIZED:-}" != "1" ]]; then
            warn "Omitiendo PRODUCCIÓN $name ($ip) — requiere SHOMER_DEPLOY_AUTHORIZED=1"
            continue
        fi
        deploy_server "$ip" "$name"
    done < "$SERVERS_FILE"
fi

log "🎉 Deploy completo"
