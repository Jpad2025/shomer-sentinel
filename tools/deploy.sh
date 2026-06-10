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
        -e "ssh $SSH_OPTS" \
        "$REPO_DIR/app/" \
        "$REMOTE_USER@$ip:$REMOTE_DIR/app/"

    # 2. Sincronizar código agente (sin data/ ni .env)
    rsync -az --delete \
        --exclude='data/' --exclude='.env' \
        --exclude='__pycache__' --exclude='*.pyc' \
        -e "ssh $SSH_OPTS" \
        "$AGENT_DIR/" \
        "$REMOTE_USER@$ip:$AGENT_DIR/"

    # 3. Actualizar TRUSTED_HOSTS y CORS con IP Tailscale del servidor remoto
    ssh $SSH_OPTS -n "$REMOTE_USER@$ip" "
        TS_IP=\$(sudo tailscale ip -4 2>/dev/null || echo '')
        LAN_IP=\$(hostname -I | awk '{print \$1}')
        RUNTIME=/etc/shomer/shomer-runtime.env
        if [[ -n \"\$TS_IP\" && -f \"\$RUNTIME\" ]]; then
            sudo sed -i \"s|SHOMER_TRUSTED_HOSTS=.*|SHOMER_TRUSTED_HOSTS=\${LAN_IP},localhost,127.0.0.1,\${TS_IP}|\" \"\$RUNTIME\"
            sudo sed -i \"s|SHOMER_CORS_ORIGINS=.*|SHOMER_CORS_ORIGINS=https://\${LAN_IP}:8443,https://\${TS_IP}:8443|\" \"\$RUNTIME\"
        fi
    "

    # 4. Reiniciar servicios remotos
    ssh $SSH_OPTS -n \
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
        if _is_production "$ip" && [[ "${SHOMER_DEPLOY_AUTHORIZED:-}" != "1" ]]; then
            warn "Omitiendo PRODUCCIÓN $name ($ip) — requiere SHOMER_DEPLOY_AUTHORIZED=1"
            continue
        fi
        deploy_server "$ip" "$name"
    done < "$SERVERS_FILE"
fi

log "🎉 Deploy completo"
