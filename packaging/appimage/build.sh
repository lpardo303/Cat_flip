#!/usr/bin/env bash
# Build del AppImage de Cat_flip, firmado con GPG y con SHA256SUMS.
#
# Uso:
#   packaging/appimage/build.sh                # congelado + AppImage + firma
#   SKIP_FROZEN=1 packaging/appimage/build.sh  # reutiliza dist/CatFlip ya construido
#   SKIP_SIGN=1 packaging/appimage/build.sh    # sin firma (CI: sin clave)
#
# La firma la hace packaging/sign.sh, igual que en Flatpak y Windows. La CI
# construye con SKIP_SIGN=1, ejecuta scripts/smoke_package.sh sobre el
# artefacto REAL y solo después firma.
#
# Sale si cualquier paso falla; el binario resultante queda en dist/appimage/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

source "$ROOT/packaging/appimage/pins.env"
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

# 5) Firma detached + checksums firmados (packaging/sign.sh, común a los 3)
"$ROOT/packaging/sign.sh" "$BINARY"

echo "✅ AppImage listo en $OUT"
