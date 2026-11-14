#!/usr/bin/env bash
# ¿Puede este diff cambiar algo que acabe DENTRO del bundle?
#
# Uso:
#   scripts/toca_bundle.sh <sha-base> [sha-final]
#
# Imprime `true` o `false` y sale 0. Lo usa el job `cambios` de ci.yml para
# saltarse `linux-bundles` (~5 min de runner) en PRs de solo documentación.
#
# Criterio CONSERVADOR: solo responde `false` si TODOS los ficheros cambiados
# son documentación, tests o metadatos que no viajan en el paquete. Ante la
# duda —base desconocida, diff vacío, git que falla— responde `true`:
# construir de más cuesta minutos; saltarse una regresión cuesta una release.
#
# Qué NO se puede saltar aunque parezca inofensivo:
#   - `tests/fixtures/`: son la ENTRADA del smoke; si cambia su forma, el
#     bundle puede dejar de leerlos y hay que verlo.
#   - `requirements*.txt`, `.spec`, `entry.py`, `templates/`, `static/`…: van
#     congelados por PyInstaller (o los usa al arrancar).
#   - Un módulo nuevo en la raíz (`mi_modulo.py`) importado por app.py: lo
#     recoge PyInstaller por import, así que también cuenta.
set -euo pipefail

BASE="${1:?Uso: scripts/toca_bundle.sh <sha-base> [sha-final]}"
FINAL="${2:-HEAD}"

decidir() {
  printf '%s\n' "$1"
  exit 0
}

# SHA cero (rama nueva en un push) o base que no está en el clon: sin base no
# hay diff en el que confiar.
if [ -z "$BASE" ] || [[ "$BASE" =~ ^0+$ ]]; then
  decidir true
fi
if ! git cat-file -e "$BASE^{commit}" 2> /dev/null; then
  decidir true
fi

# Tres puntos: los cambios que introduce el head respecto al punto de
# bifurcación, no el ruido de lo que haya avanzado la base.
if ! CAMBIOS="$(git diff --name-only "$BASE...$FINAL" 2> /dev/null)"; then
  decidir true
fi

# Un diff vacío en un PR no es lo normal: si pasa, se construye.
if [ -z "$CAMBIOS" ]; then
  decidir true
fi

while IFS= read -r fichero; do
  [ -n "$fichero" ] || continue
  case "$fichero" in
    tests/fixtures/*) decidir true ;;
  esac
  case "$fichero" in
    tests/* | docs/* | context/* | .github/ISSUE_TEMPLATE/*) continue ;;
    LICENSE | .gitignore | .cloud-attachments/*) continue ;;
    *.md | screenshot-*.png) continue ;;
  esac
  decidir true
done <<< "$CAMBIOS"

decidir false
