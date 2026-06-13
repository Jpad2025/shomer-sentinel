#!/bin/bash
# sync-from-opera.sh — Trae cambios de código desde opera (producción) hacia Utah (.205)
#
# Uso: bash tools/sync-from-opera.sh
#
# Trae SOLO código (app/ + agente). NUNCA BD, SITE.md, .env ni config del hotel.
# Después: git diff → commit en .205 → deploy-all

set -e

OPERA_IP="100.103.148.119"
OPERA_NAME="shomer-hotelopera"
REPO_DIR="/opt/network_monitor"
AGENT_DIR="/storage/shomer-agent"
REMOTE_USER="usb_admin"
REMOTE_DIR="/opt/network_monitor"
SSH_KEY="$HOME/.ssh/id_rsa_shomer"
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15"

log()  { echo "[sync-from-opera] $1"; }
warn() { echo "[sync-from-opera] AVISO: $1"; }

log "Conectando a $OPERA_NAME ($OPERA_IP)..."

rsync -avz --no-group --no-owner \
    --exclude="*.db" --exclude="*.db-*" \
    --exclude=".env" --exclude="*.env" \
    --exclude="SITE.md" \
    --exclude="__pycache__" --exclude="*.pyc" \
    --exclude="venv/" --exclude="*.log" \
    -e "ssh $SSH_OPTS" \
    "$REMOTE_USER@$OPERA_IP:$REMOTE_DIR/app/" \
    "$REPO_DIR/app/"

rsync -avz --no-group --no-owner \
    --exclude="data/" --exclude=".env" \
    --exclude="__pycache__" --exclude="*.pyc" \
    -e "ssh $SSH_OPTS" \
    "$REMOTE_USER@$OPERA_IP:$AGENT_DIR/" \
    "$AGENT_DIR/"

log "OK — Código traído desde opera hacia Utah"
warn "Siguiente paso:"
echo "  cd /opt/network_monitor && git diff"
echo "  git add -A && git commit -m \"fix: cambio desde opera\""
echo "  bash tools/deploy-all.sh"
