#!/usr/bin/env bash
#
# Smoke real de los conectores (Postgres y S3) en local.
#
# Es la versión en un solo comando de la sección «Smoke real de conectores»
# de CONTRIBUTING.md: levanta los contenededores, espera a que estén sanos,
# ejecuta los tests reales y **los limpia siempre** (trap EXIT/INT/TERM,
# también si un test falla o Ctrl+C en medio).
#
# Uso:
#   scripts/smoke.sh              # ambos smokes (Postgres y S3)
#   scripts/smoke.sh --pg         # solo Postgres
#   scripts/smoke.sh --s3         # solo S3
#   scripts/smoke.sh --pg --s3    # ambos (idéntico a sin banderas)
#   scripts/smoke.sh --help
#
# Requisitos: podman o docker, y los drivers opcionales instalados
#   pip install -r requirements-connectors.txt
#
# Variables (con su valor por defecto): CATFLIP_PG_PORT (5432),
# CATFLIP_PG_USER (catflip), CATFLIP_PG_PASSWORD (smoke_pg_2026),
# CATFLIP_PG_DB (catflip_smoke), CATFLIP_PG_HOST (127.0.0.1),
# CATFLIP_S3_PORT (4566), CATFLIP_S3_ENDPOINT (http://127.0.0.1:4566),
# CATFLIP_S3_BUCKET (catflip-smoke), CATFLIP_S3_REGION (us-east-1),
# CATFLIP_S3_ACCESS_KEY / CATFLIP_S3_SECRET_KEY (test) y las imágenes
# PG_IMAGE / S3_IMAGE. El script solo añade *_SMOKE=1, que es lo que
# activa los tests: sin esa variable pytest los salta.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# ── Banderas ──────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
Uso: scripts/smoke.sh [--pg] [--s3] [--help]

  (sin banderas)   ambos smokes: Postgres y S3
  --pg             solo el smoke de Postgres
  --s3             solo el smoke de S3
  --pg --s3        ambos (idéntico a sin banderas)
  -h, --help       esta ayuda

Levanta los contenededores, espera a que estén sanos, ejecuta los tests
reales y los limpia siempre (también si algo falla o hay Ctrl+C).
Requiere podman o docker y los drivers opcionales:
  pip install -r requirements-connectors.txt

Variables: CATFLIP_PG_PORT/USER/PASSWORD/DB/HOST, CATFLIP_S3_PORT/
ENDPOINT/BUCKET/REGION/ACCESS_KEY/SECRET_KEY, PG_IMAGE, S3_IMAGE y PYBIN.
EOF
}

run_pg=0
run_s3=0
for arg in "$@"; do
  case "$arg" in
    --pg) run_pg=1 ;;
    --s3) run_s3=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Opción desconocida: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done
if ((run_pg == 0 && run_s3 == 0)); then
  run_pg=1
  run_s3=1
fi

# ── Entorno (los tests ya tienen estos mismos valores por defecto) ────
export CATFLIP_PG_HOST="${CATFLIP_PG_HOST:-127.0.0.1}"
export CATFLIP_PG_PORT="${CATFLIP_PG_PORT:-5432}"
export CATFLIP_PG_USER="${CATFLIP_PG_USER:-catflip}"
export CATFLIP_PG_PASSWORD="${CATFLIP_PG_PASSWORD:-smoke_pg_2026}"
export CATFLIP_PG_DB="${CATFLIP_PG_DB:-catflip_smoke}"
export CATFLIP_S3_PORT="${CATFLIP_S3_PORT:-4566}"
export CATFLIP_S3_ENDPOINT="${CATFLIP_S3_ENDPOINT:-http://127.0.0.1:${CATFLIP_S3_PORT}}"
export CATFLIP_S3_BUCKET="${CATFLIP_S3_BUCKET:-catflip-smoke}"
export CATFLIP_S3_REGION="${CATFLIP_S3_REGION:-us-east-1}"
export CATFLIP_S3_ACCESS_KEY="${CATFLIP_S3_ACCESS_KEY:-test}"
export CATFLIP_S3_SECRET_KEY="${CATFLIP_S3_SECRET_KEY:-test}"

PG_CONTAINER="${PG_CONTAINER:-catflip-pg-test}"
S3_CONTAINER="${S3_CONTAINER:-catflip-s3-test}"
PG_IMAGE="${PG_IMAGE:-postgres:16}"
S3_IMAGE="${S3_IMAGE:-localstack/localstack:4.13.1}"

PYBIN="${PYBIN:-}" # .venv si existe, si no python3 (mismo patrón que packaging/)
if [[ -z "$PYBIN" ]]; then
  if [[ -x .venv/bin/python ]]; then PYBIN=.venv/bin/python; else PYBIN=python3; fi
fi

# ── Motor de contenedores ─────────────────────────────────────────────
if command -v podman >/dev/null 2>&1; then
  ENGINE=podman
elif command -v docker >/dev/null 2>&1; then
  ENGINE=docker
else
  echo "ERROR: hace falta podman o docker para levantar los servidores." >&2
  exit 1
fi

# ── Limpieza siempre (exit, Ctrl+C, error de un test) ─────────────────
started_pg=0
started_s3=0

# shellcheck disable=SC2317  # se invoca vía trap, no desde aquí
cleanup() {
  local status=$?
  set +e
  if ((started_s3)); then
    echo ""
    echo "— Limpiando $S3_CONTAINER —"
    "$ENGINE" rm -f "$S3_CONTAINER" >/dev/null
  fi
  if ((started_pg)); then
    echo "— Limpiando $PG_CONTAINER —"
    "$ENGINE" rm -f "$PG_CONTAINER" >/dev/null
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

# Espera a que algo responda; $1 descripción, resto = comando
wait_for() {
  local desc=$1
  shift
  local i
  for ((i = 1; i <= 90; i++)); do
    if "$@" >/dev/null 2>&1; then
      echo "  $desc listo (${i}s)"
      return 0
    fi
    sleep 1
  done
  echo "ERROR: $desc no respondió en 90 s." >&2
  return 1
}

# El endpoint de S3 responde con curl o, si no lo hay, con python
# shellcheck disable=SC2317  # se pasa como comando a wait_for
s3_ready() {
  if command -v curl >/dev/null 2>&1; then
    curl -sf "$CATFLIP_S3_ENDPOINT/_localstack/health" >/dev/null
  else
    "$PYBIN" - "$CATFLIP_S3_ENDPOINT" <<'EOF'
import sys, urllib.request
urllib.request.urlopen(sys.argv[1] + "/_localstack/health", timeout=2)
EOF
  fi
}

# ── Postgres ──────────────────────────────────────────────────────────
run_pg_smoke() {
  echo ""
  echo "══ Postgres: $PG_IMAGE en ${CATFLIP_PG_HOST}:${CATFLIP_PG_PORT} ══"
  if ! "$PYBIN" -c "import psycopg" 2>/dev/null; then
    echo "ERROR: falta el driver psycopg → pip install -r requirements-connectors.txt" >&2
    return 1
  fi
  "$ENGINE" rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  # Ojo: estas funciones se invocan con `|| status=1`, lo que desactiva
  # `errexit` dentro; cada paso crítico aborta con `return 1` a mano.
  "$ENGINE" run -d --name "$PG_CONTAINER" \
    -e POSTGRES_USER="$CATFLIP_PG_USER" \
    -e POSTGRES_PASSWORD="$CATFLIP_PG_PASSWORD" \
    -e POSTGRES_DB="$CATFLIP_PG_DB" \
    -p "${CATFLIP_PG_PORT}:5432" \
    "$PG_IMAGE" >/dev/null || return 1
  started_pg=1
  wait_for "postgres" "$ENGINE" exec "$PG_CONTAINER" \
    pg_isready -U "$CATFLIP_PG_USER" -d "$CATFLIP_PG_DB" || return 1

  CATFLIP_PG_SMOKE=1 "$PYBIN" -m pytest \
    tests/test_connectors_postgres_live.py -v
}

# ── S3 (LocalStack) ───────────────────────────────────────────────────
run_s3_smoke() {
  echo ""
  echo "══ S3: $S3_IMAGE en $CATFLIP_S3_ENDPOINT ══"
  if ! "$PYBIN" -c "import boto3" 2>/dev/null; then
    echo "ERROR: falta el driver boto3 → pip install -r requirements-connectors.txt" >&2
    return 1
  fi
  "$ENGINE" rm -f "$S3_CONTAINER" >/dev/null 2>&1 || true
  "$ENGINE" run -d --name "$S3_CONTAINER" \
    -p "${CATFLIP_S3_PORT}:4566" \
    "$S3_IMAGE" >/dev/null || return 1
  started_s3=1
  wait_for "localstack" s3_ready || return 1

  CATFLIP_S3_SMOKE=1 "$PYBIN" -m pytest \
    tests/test_connectors_s3_live.py -v
}

status=0
if ((run_pg)); then run_pg_smoke || status=1; fi
if ((run_s3)); then run_s3_smoke || status=1; fi

echo ""
if ((status == 0)); then
  echo "✓ Smokes en verde."
else
  echo "✗ Hay smokes en rojo (mira el fallo de arriba)." >&2
fi
exit "$status"
