#!/bin/bash
# deploy.sh — Actualiza servidores Shomer desde .205
# Uso: ./tools/deploy.sh [ip_tailscale]
#      Sin argumento: actualiza todos los servidores en servers.txt
#      Con IP:        actualiza solo ese servidor

set -e

REPO_DIR="/opt/network_monitor"
SERVERS_FILE="$REPO_DIR/tools/servers.txt"
REMOTE_USER="usb_admin"
REMOTE_DIR="/opt/network_monitor"
AGENT_DIR="/storage/shomer-agent"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }
err()  { echo -e "${RED}[deploy]${NC} $1"; }

deploy_server() {
    local ip=$1
    local name=$2

    log "→ Desplegando en $name ($ip)..."

    # 1. Sincronizar código app/
    rsync -az --delete \
        --exclude='*.db' --exclude='*.db-*' \
        --exclude='.env' --exclude='*.env' \
        --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='venv/' --exclude='*.log' \
        -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
        "$REPO_DIR/app/" \
        "$REMOTE_USER@$ip:$REMOTE_DIR/app/"

    # 2. Sincronizar código agente (sin data/ ni .env)
    rsync -az --delete \
        --exclude='data/' --exclude='.env' \
        --exclude='__pycache__' --exclude='*.pyc' \
        -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
        "$AGENT_DIR/" \
        "$REMOTE_USER@$ip:$AGENT_DIR/"

    # 3. Reiniciar servicios remotos
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        "$REMOTE_USER@$ip" \
        "sudo systemctl restart shomer-guardian shomer-tools && \
         sudo docker compose -f $AGENT_DIR/docker-compose.yml restart 2>/dev/null; \
         echo 'Servicios reiniciados'"

    log "✅ $name actualizado"
}

# Argumento opcional: IP específica
TARGET_IP="${1:-}"

if [[ -n "$TARGET_IP" ]]; then
    deploy_server "$TARGET_IP" "$TARGET_IP"
else
    # Leer servers.txt y desplegar a todos
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
        ip=$(echo "$line" | awk '{print $1}')
        name=$(echo "$line" | awk '{print $2}')
        deploy_server "$ip" "$name"
    done < "$SERVERS_FILE"
fi

log "🎉 Deploy completo"
