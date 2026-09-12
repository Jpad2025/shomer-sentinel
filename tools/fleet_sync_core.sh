#!/usr/bin/env bash
# fleet_sync_core.sh — propaga el código del core desde el maestro (Ópera) a
# toda la flota, reinicia los servicios, verifica que arrancaron y revierte
# solo si no.
#
# Por qué existe (12 sep 2026): el agente ya tenía fleet_sync.sh, pero el core
# se sincronizaba A MANO, tecleando la lista de archivos en cada rsync. Lo que
# no se teclea, no viaja: así se quedaron nueve archivos sin llegar a los labs
# durante días, y otros tantos vivos en producción sin commitear. Un
# procedimiento que depende de que alguien recuerde la lista completa va a
# fallar siempre; este script no tiene lista que recordar.
#
# Uso:
#   ./tools/fleet_sync_core.sh                 # toda la flota
#   ./tools/fleet_sync_core.sh shomer245       # solo ese host
#   PERMITIR_SUCIO=1 ./tools/fleet_sync_core.sh   # solo para emergencias
#
# Guardia: si el maestro tiene código sin commitear, NO sincroniza. Ese es el
# punto: propagar un árbol sucio reparte un estado que no existe en ningún
# historial y que nadie puede reproducir después.
#
# Seguridad (mismo criterio que fleet_sync.sh del agente):
#   - Sin --delete: nunca borra algo que el maestro no tenga.
#   - Los cambios sin commitear del remoto se guardan con `git stash` antes de
#     sobrescribir. Nunca se descartan en silencio.
#   - .env, SITE.md, bases de datos, venv y logs quedan excluidos siempre: son
#     de cada instalación y jamás se copian entre hoteles.
#   - Tras reiniciar se comprueba la salud de los dos servicios; si no
#     responden, se revierte con `git reset --hard` al commit anterior.
set -uo pipefail

REPO_DIR="/opt/network_monitor"
SERVICIOS=(shomer-guardian shomer-tools shomer-inframonitor-poller)
LOG_FILE="$REPO_DIR/tools/fleet_sync_core.log"
HOSTS_FILE=""
for c in "${SHOMER_FLEET_HOSTS:-}" /etc/shomer/fleet_hosts.txt \
         /storage/shomer-agent/tools/fleet_hosts.txt; do
  [ -n "$c" ] && [ -f "$c" ] && { HOSTS_FILE="$c"; break; }
done

if [ "$#" -gt 0 ]; then
  hosts=("$@")
elif [ -n "$HOSTS_FILE" ]; then
  mapfile -t hosts < <(grep -vE '^\s*(#|$)' "$HOSTS_FILE")
else
  echo "Sin lista de flota: definir SHOMER_FLEET_HOSTS o crear /etc/shomer/fleet_hosts.txt" >&2
  exit 1
fi
[ "${#hosts[@]}" -eq 0 ] && { echo "Sin hosts que sincronizar (revisar $HOSTS_FILE)." >&2; exit 1; }

# ── Guardia: el maestro no puede tener código sin commitear ──────────────────
sucio=$(cd "$REPO_DIR" && git status --porcelain | grep -vE '\.(db|log|pyc)$|\.env|SITE\.md|servers\.txt' || true)
if [ -n "$sucio" ] && [ "${PERMITIR_SUCIO:-0}" != "1" ]; then
  echo "NO se sincroniza: el maestro tiene código sin commitear." >&2
  echo "$sucio" | sed 's/^/  /' >&2
  echo "" >&2
  echo "Commitearlo primero (con rutas explícitas, nunca 'git add -A')." >&2
  echo "Para una emergencia real: PERMITIR_SUCIO=1 $0" >&2
  exit 2
fi

RSYNC_EXCLUDES=(
  --exclude='.env' --exclude='.env.bak*' --exclude='SITE.md'
  --exclude='tools/servers.txt' --exclude='tools/fleet_sync*.log'
  --exclude='*.db' --exclude='*.db-*' --exclude='*.sqlite*'
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo'
  --exclude='*.log' --exclude='logs/' --exclude='.pytest_cache/'
  --exclude='venv/' --exclude='.venv/'
)

local_head=$(cd "$REPO_DIR" && git rev-parse --short HEAD)
run_ts=$(date '+%Y-%m-%d %H:%M:%S %Z')
echo "== fleet_sync_core — $run_ts — maestro $local_head =="
printf '%-12s | %-22s | %-8s | %-10s | %-10s | %s\n' \
  "HOST" "STASH" "RSYNC" "SERVICIOS" "PRUEBAS" "COMMIT"
printf '%s\n' "-----------------------------------------------------------------------------------------"

for h in "${hosts[@]}"; do
  prev_head=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$h" \
    "cd '$REPO_DIR' 2>/dev/null && git rev-parse HEAD" 2>/dev/null)
  if [ -z "$prev_head" ]; then
    printf '%-12s | %-22s | %-8s | %-10s | %-10s | %s\n' "$h" "SIN_CONEXION" "-" "-" "-" "-"
    echo "$run_ts | $h | SIN_CONEXION" >> "$LOG_FILE"
    continue
  fi
  prev_short=${prev_head:0:7}

  stash_v=$(ssh -o ConnectTimeout=10 "$h" "
    cd '$REPO_DIR'
    if [ -n \"\$(git status --porcelain)\" ]; then
      ts=\$(date +%Y%m%d_%H%M%S)
      git stash push -u -m \"fleet_sync_core auto-stash \$ts\" >/dev/null 2>&1 \
        && echo \"guardado:\$ts\" || echo FALLO_STASH
    else
      echo ninguno
    fi
  " 2>/dev/null)
  stash_v="${stash_v:-ninguno}"

  if rsync -az "${RSYNC_EXCLUDES[@]}" -e "ssh -o ConnectTimeout=15" \
      "$REPO_DIR/" "$h:$REPO_DIR/" >/tmp/fleet_core_rsync_"$h".log 2>&1; then
    rsync_v="ok"
  else
    printf '%-12s | %-22s | %-8s | %-10s | %-10s | %s\n' "$h" "$stash_v" "FALLO" "-" "-" "-"
    echo "$run_ts | $h | $prev_short -> RSYNC_FALLO" >> "$LOG_FILE"
    continue
  fi

  ssh -o ConnectTimeout=10 "$h" "sudo systemctl restart ${SERVICIOS[*]}" >/dev/null 2>&1
  sleep 8
  salud=$(ssh -o ConnectTimeout=15 "$h" "
    c=\$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8000/health)
    t=\$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8001/health)
    [ \"\$c\" = 200 ] && [ \"\$t\" = 200 ] && echo ok || echo \"core=\$c tools=\$t\"
  " 2>/dev/null)
  salud="${salud:-sin_respuesta}"

  if [ "$salud" != "ok" ]; then
    ssh -o ConnectTimeout=10 "$h" "
      cd '$REPO_DIR' && git reset --hard '$prev_head' >/dev/null 2>&1
      sudo systemctl restart ${SERVICIOS[*]} >/dev/null 2>&1
    " >/dev/null 2>&1
    printf '%-12s | %-22s | %-8s | %-10s | %-10s | %s\n' \
      "$h" "$stash_v" "$rsync_v" "ROLLBACK" "-" "revertido:$prev_short"
    echo "$run_ts | $h | $prev_short -> ROLLBACK ($salud)" >> "$LOG_FILE"
    continue
  fi

  pruebas=$(ssh -o ConnectTimeout=10 "$h" \
    "cd '$REPO_DIR' && venv/bin/python -m pytest tests/ -q 2>&1 | tail -1" 2>/dev/null)
  if grep -q "failed\|error" <<<"$pruebas"; then
    pruebas_v="FALLAN"
  else
    pruebas_v=$(grep -oE '^[0-9]+ passed' <<<"$pruebas" | head -1)
    pruebas_v="${pruebas_v:-?}"
  fi

  new_head=$(ssh -o ConnectTimeout=10 "$h" "cd '$REPO_DIR' && git rev-parse --short HEAD" 2>/dev/null)
  printf '%-12s | %-22s | %-8s | %-10s | %-10s | %s\n' \
    "$h" "$stash_v" "$rsync_v" "$salud" "$pruebas_v" "$new_head"
  echo "$run_ts | $h | $prev_short -> $new_head | stash=$stash_v | salud=$salud | pruebas=$pruebas_v" >> "$LOG_FILE"
done

echo ""
echo "Log completo: $LOG_FILE"
echo "Verificar que no quedó nada fuera de sitio:  tools/fleet_estado.py"
echo "Si algún host quedó con STASH=guardado:*, revisar con:"
echo "  ssh <host> 'cd $REPO_DIR && git stash list'"
