#!/usr/bin/env bash
# Build del .exe de Windows (PyInstaller onefile), firmado con GPG y con
# SHA256SUMS — el equivalente a packaging/appimage/build.sh.
#
# Uso (Git Bash en Windows, o el job `windows` de la CI con `shell: bash`):
#   packaging/windows/build.sh                 # congelado + .exe + firma
#   SKIP_FROZEN=1 packaging/windows/build.sh   # reutiliza dist/CatFlip.exe
#
# Nota: gpg y sha256sum viven en Git Bash (no en el PATH de PowerShell);
# por eso este script es bash y la CI corre este job con `shell: bash`.
# Sale si cualquier paso falla; el binario queda en dist/windows/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

FPR="$(tr -d '[:space:]' < "$ROOT/packaging/gpg/FINGERPRINT")"
VERSION="$(python -c "import json; print(json.load(open('package.json'))['version'])")"
# Python del proyecto: el del entorno (CI); si hay .venv de Linux no aplica aquí.
PYBIN="${PYBIN:-python}"
OUT="$ROOT/dist/windows"
WORK="$ROOT/build/windows"

for tool in gpg sha256sum "$PYBIN"; do
  if ! command -v "$tool" > /dev/null 2>&1; then
    echo "::error::Falta «$tool». En Windows usa Git Bash (gpg y sha256sum)" \
      "viven en /usr/bin) o instala GnuPG con choco install gnupg."
    exit 1
  fi
done

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

# 2) Firma detached + checksums firmados (mismo patrón que AppImage/Flatpak).
echo "→ firma GPG ($FPR)"
gpg --batch --yes --armor --local-user "$FPR" --detach-sign "$BINARY"
(
  cd "$OUT"
  rm -f SHA256SUMS.asc SHA256SUMS.sig
  sha256sum "$(basename "$BINARY")" > SHA256SUMS
  gpg --batch --yes --armor --local-user "$FPR" --detach-sign SHA256SUMS
)

echo "✅ .exe listo:"
ls -lh "$BINARY" "$BINARY.asc" "$OUT/SHA256SUMS" "$OUT/SHA256SUMS.asc"
