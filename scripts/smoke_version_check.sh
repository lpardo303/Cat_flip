#!/usr/bin/env bash
# Backoff de /version/check compartido por los tres smokes de
# packaging.yml (AppImage, .exe y Flatpak): el mismo bloque estaba
# triplicado en el workflow.
#
# Uso:
#   scripts/smoke_version_check.sh <url> [log_del_app] [versión_esperada]
#
#   url               p. ej. http://127.0.0.1:5050/version/check
#   log_del_app       log del binario arrancado; se vuelca si el check falla
#   versión_esperada  si se pasa, `current` debe coincidir: fallo duro SIN
#                     reintentar (reintentar solo vuelve a consultar a
#                     GitHub, la versión ya la sabe el propio bundle). Si se
#                     omite, solo se exige checked:true.
#
# Sale con 0 si el check pasa y con 1 si no (imprimiendo ::error::, que la
# CI interpreta como anotación de error).
#
# Por qué backoff y no «3 × sleep 3» (lo que reventó el job de Windows en
# el PR #46 con tres checked:false en 9 s):
#   1. El servidor cachea el fallo de GitHub 300 s (_RELEASE_TTL_ERR de
#      app.py): una espera menor que ese TTL solo relee la caché y NO vuelve
#      a consultar a api.github.com — los reintentos serían el mismo fallo.
#      Por eso la espera arranca en 305 s (TTL + margen).
#   2. La ventana del rate limit anónimo (60/h por IP del runner) puede
#      durar más que ese TTL: si /rate_limit la reporta agotada
#      (remaining=0), la espera se estira hasta su reset (+15 s) sin pasar
#      de SMOKE_MAX_WAIT. /rate_limit NO consume cuota.
# La espera crece ~10 % por intento (305 → 335 → 366). SMOKE_BASE_DELAY y
# SMOKE_MAX_WAIT solo existen para probar este script en local con esperas
# cortas.
#
# Compatible con Git Bash (job de Windows): solo curl/grep/date/head/sleep
# — grep y NO python sobre /tmp, porque en Windows /tmp no es la ruta que
# ve un Python nativo.
set -uo pipefail

URL="${1:?Uso: scripts/smoke_version_check.sh <url> [log_del_app] [versión_esperada]}"
APPLOG="${2:-}"
EXPECT="${3:-}"

BASE="${SMOKE_BASE_DELAY:-305}"
CAP="${SMOKE_MAX_WAIT:-600}"
OK=0

for i in 1 2 3 4; do
  rm -f /tmp/version.json
  curl -sf -o /tmp/version.json "$URL" || true
  cat /tmp/version.json 2>/dev/null || true
  echo
  if grep -Eq '"checked"[[:space:]]*:[[:space:]]*true' /tmp/version.json 2>/dev/null; then
    if [ -n "$EXPECT" ] && \
       ! grep -Eq "\"current\"[[:space:]]*:[[:space:]]*\"$EXPECT\"" /tmp/version.json 2>/dev/null; then
      echo "::error::$URL da current ≠ $EXPECT — el package.json EMPAQUETADO no es el de la release"
      if [ -n "$APPLOG" ]; then cat "$APPLOG" 2>/dev/null || true; fi
      exit 1
    fi
    OK=1
    break
  fi
  if [ "$i" = 4 ]; then break; fi
  WAIT=$(( BASE + (i - 1) * BASE / 10 ))
  # pipefail: sin coincidencia grep sale 1, por eso cada extracción de las
  # cabeceras va con || true dentro del $().
  RL="$(curl -s --max-time 10 https://api.github.com/rate_limit || true)"
  REMAIN="$(grep -oE '"remaining"[[:space:]]*:[[:space:]]*[0-9]+' <<< "$RL" | head -1 | grep -oE '[0-9]+$' || true)"
  RESET="$(grep -oE '"reset"[[:space:]]*:[[:space:]]*[0-9]+' <<< "$RL" | head -1 | grep -oE '[0-9]+$' || true)"
  if [ "$REMAIN" = 0 ] && [ -n "$RESET" ]; then
    TILLRESET=$(( RESET - $(date +%s) + 15 ))
    if [ "$TILLRESET" -gt "$WAIT" ] && [ "$TILLRESET" -le "$CAP" ]; then
      WAIT=$TILLRESET
    fi
  fi
  echo "→ reintento $i/3 tras ${WAIT}s (rate limit remaining=${REMAIN:-desconocido})"
  sleep "$WAIT"
done

if [ "$OK" != 1 ]; then
  echo "::error::$URL sigue en checked:false tras 4 intentos con backoff — rate limit sostenido de api.github.com, sin CAs en el bundle o sin red en el sandbox"
  if [ -n "$APPLOG" ]; then cat "$APPLOG" 2>/dev/null || true; fi
  exit 1
fi
exit 0