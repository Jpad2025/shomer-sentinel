#!/bin/bash
# Fragmento opcional: añadir al final de /usr/local/bin/shomer-health-check.sh
# Comprueba GET /remedies/pipeline/health y escribe en watchdog.log si overall_ok es false.
# Instalación: sudo bash -c 'cat ... >> /usr/local/bin/shomer-health-check.sh' (o fusionar a mano)

LOG="${LOG:-/var/log/shomer/watchdog.log}"
TIMESTAMP=$(date '+%m-%d %H:%M:%S')
PH=$(curl -sf --max-time 8 http://localhost:8000/remedies/pipeline/health 2>/dev/null) || true
if echo "$PH" | grep -q '"overall_ok": false'; then
  echo "[$TIMESTAMP] WARN: pipeline Hunter NO OK — $(echo "$PH" | tr '\n' ' ' | cut -c1-280)" >> "$LOG"
fi
