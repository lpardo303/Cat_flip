#!/usr/bin/env bash
# Build del AppImage de Cat_flip, firmado con GPG y con SHA256SUMS.
#
# Uso:
#   packaging/appimage/build.sh              # congelado + AppImage + firma
#   SKIP_FROZEN=1 packaging/appimage/build.sh  # reutiliza dist/CatFlip ya construido
#
# Sale si cualquier paso falla; el binario resultante queda en dist/appimage/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

source "$ROOT/packaging/appimage/pins.env"
FPR="$(tr -d '[:space:]' < "$ROOT/packaging/gpg/FINGERPRINT")"
VERSION="$(python3 -c "import json; print(json.load(open('package.json'))['version'])")"
# Python del proyecto: .venv si existe (local); si no, el del entorno (CI).
PYBIN=".venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="python3"
OUT="$ROOT/dist/appimage"
TOOLS="$ROOT/packaging/appimage/tools"
WORK="$ROOT/build/appimage"
APPDIR="$WORK/AppDir"
BINARY="$OUT/CatFlip-${VERSION}-x86_64.AppImage"

# 1) appimagetool: descarga pina y verifica el hash antes de usarlo.
mkdir -p "$TOOLS" "$OUT"
if [ ! -f "$TOOLS/appimagetool.AppImage" ]; then
  echo "→ descargando appimagetool"
  curl -fsSL -o "$TOOLS/appimagetool.AppImage" "$APPIMAGETOOL_URL"
fi
# El run del repo no conserva el bit de ejecución: asegurarlo siempre.
chmod +x "$TOOLS/appimagetool.AppImage"
echo "$APPIMAGETOOL_SHA256  $TOOLS/appimagetool.AppImage" | sha256sum -c -

# 2) Binario onedir con PyInstaller (el mismo que usa el Flatpak).
if [ "${SKIP_FROZEN:-0}" != "1" ]; then
  echo "→ PyInstaller onedir ($PYBIN)"
  "$PYBIN" -m PyInstaller --noconfirm --clean \
    --distpath dist --workpath build/pyinstaller \
    packaging/appimage/catflip.spec
fi

# 3) AppDir
echo "→ AppDir"
rm -rf "$APPDIR"
mkdir -p \
  "$APPDIR/usr/bin/CatFlip" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a dist/CatFlip/. "$APPDIR/usr/bin/CatFlip/"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/CatFlip/CatFlip" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cp "$ROOT/packaging/appimage/catflip.desktop" "$APPDIR/catflip.desktop"
cp "$ROOT/packaging/appimage/catflip.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/packaging/appimage/catflip-icon-512.png" "$APPDIR/catflip.png"
cp "$ROOT/packaging/appimage/catflip-icon-512.png" "$APPDIR/usr/share/icons/hicolor/512x512/apps/catflip.png"
cp "$ROOT/packaging/appimage/catflip-icon-256.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/catflip.png"

# 4) appimagetool (sin FUSE: --appimage-extract-and-run)
echo "→ appimagetool"
rm -f "$BINARY" "$BINARY.asc" "$BINARY.sig"
ARCH=x86_64 "$TOOLS/appimagetool.AppImage" --appimage-extract-and-run \
  "$APPDIR" "$BINARY"

# 5) Firma detached + checksums firmados
echo "→ firma GPG ($FPR)"
gpg --batch --yes --armor --local-user "$FPR" --detach-sign "$BINARY"
(
  cd "$OUT"
  rm -f SHA256SUMS.asc SHA256SUMS.sig
  sha256sum "$(basename "$BINARY")" > SHA256SUMS
  gpg --batch --yes --armor --local-user "$FPR" --detach-sign SHA256SUMS
)

echo "✅ AppImage listo:"
ls -lh "$BINARY" "$BINARY.asc" "$OUT/SHA256SUMS" "$OUT/SHA256SUMS.asc"
