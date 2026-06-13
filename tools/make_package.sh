#!/bin/bash
# =============================================================================
# make_package.sh — Genera el paquete de instalación Shomer Sentinel 2.0
# =============================================================================
# Uso: bash tools/make_package.sh
# Genera: /tmp/shomer-YYYYMMDD.tar.gz  (~30-50 MB)
#
# El técnico recibe ese .tar.gz, lo extrae y corre:
#   tar -xzf shomer-YYYYMMDD.tar.gz
#   cd shomer-YYYYMMDD
#   sudo bash tools/install_shomer.sh
# =============================================================================

set -euo pipefail

FECHA=$(date +%Y%m%d)
PKG_NAME="shomer-${FECHA}"
OUT="/tmp/${PKG_NAME}.tar.gz"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Generando paquete Shomer Sentinel 2.0 ==="
echo "Fuente : $SRC"
echo "Destino: $OUT"
echo ""

# Actualizar requirements.txt desde el venv activo
if [[ -d "$SRC/venv" ]]; then
    echo "→ Actualizando requirements.txt..."
    "$SRC/venv/bin/pip" freeze > "$SRC/requirements.txt"
    echo "  $(wc -l < "$SRC/requirements.txt") paquetes"
fi

AGENT_SRC="/storage/shomer-agent"

echo "→ Empaquetando panel + agente..."

# Carpeta temporal para armar el paquete completo
TMP_DIR="/tmp/${PKG_NAME}_build"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR/${PKG_NAME}"

# Copiar panel Shomer
cp -a "$SRC/." "$TMP_DIR/${PKG_NAME}/"
rm -rf "$TMP_DIR/${PKG_NAME}/venv" \
       "$TMP_DIR/${PKG_NAME}/.git" \
       "$TMP_DIR/${PKG_NAME}/tools/make_package.sh"
find "$TMP_DIR/${PKG_NAME}" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$TMP_DIR/${PKG_NAME}" -name "*.pyc" -delete 2>/dev/null || true

# Copiar agente si existe
if [[ -d "$AGENT_SRC" ]]; then
    echo "→ Incluyendo shomer-agent..."
    mkdir -p "$TMP_DIR/${PKG_NAME}/shomer-agent"
    cp -a "$AGENT_SRC/." "$TMP_DIR/${PKG_NAME}/shomer-agent/"
    rm -f "$TMP_DIR/${PKG_NAME}/shomer-agent/.env"
    rm -rf "$TMP_DIR/${PKG_NAME}/shomer-agent/data"
    echo "  shomer-agent incluido"
else
    echo "  ⚠ No se encontró $AGENT_SRC — agente no incluido"
fi

tar -czf "$OUT" -C "$TMP_DIR" "${PKG_NAME}"
rm -rf "$TMP_DIR"

SIZE=$(du -sh "$OUT" | cut -f1)
echo ""
echo "=== Paquete listo ==="
echo "Archivo : $OUT"
echo "Tamaño  : $SIZE"
echo ""
echo "Envío por SCP al nuevo servidor:"
echo "  scp $OUT usuario@IP_DESTINO:/tmp/"
echo ""
echo "Instalación en el servidor destino:"
echo "  cd /tmp && tar -xzf ${PKG_NAME}.tar.gz"
echo "  cd ${PKG_NAME}"
echo "  sudo bash tools/install_shomer.sh"
echo ""
echo "Para instalación remota Bogotá:"
echo "  ssh usuario@IP_BOGOTA 'mkdir -p /tmp/shomer_install'"
echo "  scp $OUT usuario@IP_BOGOTA:/tmp/"
echo "  ssh usuario@IP_BOGOTA 'cd /tmp && tar -xzf ${PKG_NAME}.tar.gz && cd ${PKG_NAME} && sudo bash tools/install_shomer.sh'"
