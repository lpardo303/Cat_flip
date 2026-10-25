#!/usr/bin/env bash
# Build del Flatpak de Cat_flip: repo ostree firmado con GPG + bundle .flatpak.
#
# Uso:
#   packaging/flatpak/build.sh                 # congelado + flatpak + firma
#   SKIP_FROZEN=1 packaging/flatpak/build.sh   # reutiliza dist/CatFlip ya construido
#
# Requiere: org.flatpak.Builder y org.freedesktop.Sdk//25.08 en flathub (user).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

FPR="$(tr -d '[:space:]' < "$ROOT/packaging/gpg/FINGERPRINT")"
VERSION="$(python3 -c "import json; print(json.load(open('package.json'))['version'])")"
# Python del proyecto: .venv si existe (local); si no, el del entorno (CI).
PYBIN=".venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="python3"
MANIFEST="$ROOT/packaging/flatpak/io.github.lpardo303.CatFlip.yml"
OUT="$ROOT/dist/flatpak"
BUILD="$ROOT/build/flatpak"
APP_ID="io.github.lpardo303.CatFlip"

# 1) Binario onedir con PyInstaller (el mismo que usa el AppImage).
if [ "${SKIP_FROZEN:-0}" != "1" ]; then
  echo "→ PyInstaller onedir ($PYBIN)"
  "$PYBIN" -m PyInstaller --noconfirm --clean \
    --distpath dist --workpath build/pyinstaller \
    packaging/appimage/catflip.spec
fi

# 2) flatpak-builder dentro de su app aislada (misma keyring de usuario).
# Builder: por defecto la app aislada org.flatpak.Builder (necesita el SDK a
# nivel de sistema); en CI se puede usar un flatpak-builder del host con
# FLATPAK_BUILDER_CMD="flatpak-builder".
if [ -n "${FLATPAK_BUILDER_CMD:-}" ]; then
  read -r -a FB <<< "$FLATPAK_BUILDER_CMD"
else
  FB=(flatpak run --filesystem="$ROOT" --command=flatpak-builder org.flatpak.Builder)
fi

echo "→ flatpak-builder (repo firmado con $FPR)"
mkdir -p "$OUT" "$BUILD"
rm -rf "$OUT/repo"
"${FB[@]}" \
  --force-clean \
  --repo="$OUT/repo" \
  --gpg-sign="$FPR" \
  "$BUILD/dir" "$MANIFEST"

# 3) Rama real que exportó el builder (no asumir «master»).
BRANCH="$(find "$OUT/repo/refs" -type f -printf '%f\n' | head -1)"
[ -n "$BRANCH" ] || { echo "✗ el repo no tiene refs"; exit 1; }
echo "→ rama: $BRANCH"

# 4) Bundle + checksums firmados
BUNDLE="$OUT/CatFlip-$VERSION.flatpak"
echo "→ bundle"
rm -f "$BUNDLE" "$BUNDLE.asc" "$BUNDLE.sig"
flatpak build-bundle "$OUT/repo" "$BUNDLE" "$APP_ID" "$BRANCH"

echo "→ firma GPG ($FPR)"
gpg --batch --yes --armor --local-user "$FPR" --detach-sign "$BUNDLE"
(
  cd "$OUT"
  rm -f SHA256SUMS.asc SHA256SUMS.sig
  sha256sum "$(basename "$BUNDLE")" > SHA256SUMS
  gpg --batch --yes --armor --local-user "$FPR" --detach-sign SHA256SUMS
)

echo "✅ Flatpak listo:"
ls -lh "$BUNDLE" "$BUNDLE.asc" "$OUT/SHA256SUMS" "$OUT/SHA256SUMS.asc"
