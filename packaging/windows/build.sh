#!/usr/bin/env bash
# Build del .exe de Windows (PyInstaller onefile), firmado con GPG y con
# SHA256SUMS — el equivalente a packaging/appimage/build.sh.
#
# Uso (Git Bash en Windows, o los jobs de la CI con `shell: bash`):
#   packaging/windows/build.sh                 # congelado + .exe + firma
#   SKIP_FROZEN=1 packaging/windows/build.sh   # reutiliza dist/CatFlip.exe
#   SKIP_SIGN=1 packaging/windows/build.sh     # sin firma (CI: no hay clave)
#
# `SKIP_SIGN=1` construye y deja el .exe en dist/windows/ sin firmar: es lo
# que usan los jobs de CI para probar el artefacto (el smoke va SIEMPRE antes
# de firmar). La firma vive en packaging/sign.sh, común a los tres formatos.
#
# Nota: gpg y sha256sum viven en Git Bash (no en el PATH de PowerShell); este
# script ya no los necesita para construir, pero la CI corre con
# `shell: bash` igualmente (y el smoke usa bash + curl).
# Sale si cualquier paso falla; el binario queda en dist/windows/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VERSION="$(python -c "import json; print(json.load(open('package.json'))['version'])")"
# Python del proyecto: el del entorno (CI); si hay .venv de Linux no aplica aquí.
PYBIN="${PYBIN:-python}"
OUT="$ROOT/dist/windows"
WORK="$ROOT/build/windows"

if ! command -v "$PYBIN" > /dev/null 2>&1; then
  echo "::error::Falta «$PYBIN» (el Python que construye el .exe)."
  exit 1
fi

mkdir -p "$OUT"

# 1) Binario onefile con PyInstaller.
if [ "${SKIP_FROZEN:-0}" != "1" ]; then
  echo "→ PyInstaller onefile ($PYBIN)"
  "$PYBIN" -m PyInstaller --noconfirm --clean \
    --distpath dist --workpath "$WORK" \
    packaging/windows/catflip.spec
fi

if [ ! -f dist/CatFlip.exe ]; then
  echo "::error::No existe dist/CatFlip.exe — el spec de Windows solo" \
    "produjo resultado en Windows (ejecuta este script en Git Bash)."
  exit 1
fi

BINARY="$OUT/CatFlip-${VERSION}-x64.exe"
echo "→ .exe listo para firmar"
rm -f "$BINARY" "$BINARY.asc"
mv dist/CatFlip.exe "$BINARY"

# 2) Firma detached + checksums firmados (packaging/sign.sh, común a los 3)
"$ROOT/packaging/sign.sh" "$BINARY"

echo "✅ .exe listo en $OUT"
