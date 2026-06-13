#!/bin/bash
# deploy-all.sh — Envía código desde Utah (.205) a los demás servidores
#
# Uso:
#   bash tools/deploy-all.sh              → labs .245 y .243
#   bash tools/deploy-all.sh --with-opera → incluye hotel (requiere autorización)
#
# Producción:
#   SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy-all.sh --with-opera

set -e

REPO_DIR="/opt/network_monitor"
cd "$REPO_DIR"

log()  { echo "[deploy-all] $1"; }
warn() { echo "[deploy-all] AVISO: $1"; }

LAB_SERVERS=(
    "100.75.182.116"
    "100.108.17.50"
)

WITH_OPERA=0
[[ "${1:-}" == "--with-opera" ]] && WITH_OPERA=1

log "Desplegando en labs Utah (.245, .243)..."
for ip in "${LAB_SERVERS[@]}"; do
    bash "$REPO_DIR/tools/deploy.sh" "$ip" || warn "Falló $ip"
done

if [[ "$WITH_OPERA" == "1" ]]; then
    if [[ "${SHOMER_DEPLOY_AUTHORIZED:-}" != "1" ]]; then
        warn "Opera omitido — requiere:"
        echo "  SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy-all.sh --with-opera"
        exit 1
    fi
    log "Desplegando en opera (producción)..."
    bash "$REPO_DIR/tools/deploy.sh" "100.103.148.119"
fi

log "Deploy completo"
