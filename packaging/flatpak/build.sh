#!/usr/bin/env bash
# Build del Flatpak de Cat_flip: repo ostree firmado con GPG + bundle .flatpak.
#
# Uso:
#   packaging/flatpak/build.sh                 # congelado + flatpak + firma
#   SKIP_FROZEN=1 packaging/flatpak/build.sh   # reutiliza dist/CatFlip ya construido
#   SKIP_SIGN=1 packaging/flatpak/build.sh     # bundle sin firmar
#
# Ojo con la diferencia: el repo ostree DENTRO del bundle se firma durante el
# build (`flatpak build-export --gpg-sign`) y `flatpak install` la exige, así
# que re-firmarla después no es posible sin regenerar el bundle. La firma
# detached (.asc) y los SHA256SUMS, que es lo que el usuario verifica, sí van
# en packaging/sign.sh como en los otros dos formatos — y por eso el smoke
# corre antes de esa firma.
#
# Requiere: org.flatpak.Builder y org.freedesktop.Sdk//25.08 en flathub (user).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

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

# El repo ostree se firma al exportarlo cuando hay clave: sin esa firma el
# bundle no se podría instalar (ver la nota de la cabecera).
FIRMA=()
if [ "${SKIP_SIGN:-0}" != "1" ]; then
  FPR="$(tr -d '[:space:]' < "$ROOT/packaging/gpg/FINGERPRINT")"
  FIRMA=(--gpg-sign="$FPR")
  echo "→ flatpak-builder (repo firmado con $FPR)"
else
  echo "→ flatpak-builder (repo SIN firmar: SKIP_SIGN=1)"
fi
mkdir -p "$OUT" "$BUILD"
rm -rf "$OUT/repo"
"${FB[@]}" \
  --force-clean \
  --repo="$OUT/repo" \
  ${FIRMA[@]+"${FIRMA[@]}"} \
  "$BUILD/dir" "$MANIFEST"

# 3) Rama real que exportó el builder (no asumir «master»).
#    Ojo: `refs/` contiene además las refs `appstream`/`appstream2`, que
#    son ficheros llamados como la arquitectura (`x86_64`): un
#    `find ... | head -1` sobre TODOS los refs depende del orden de
#    readdir y a veces devolvía «x86_64», con lo que el bundle pedía
#    `app/<id>/x86_64/x86_64` y revienta con «Refspec not found»
#    (flake del packaging de v1.5.0). Se lee solo la ref de NUESTRA app
#    (`app/<id>/<arquitectura>/<rama>`) y se ordena para que sea
#    determinista.
BRANCH="$(find "$OUT/repo/refs/heads/app/$APP_ID" \
  -mindepth 2 -maxdepth 2 -type f -printf '%f\n' 2>/dev/null \
  | sort | head -n1 || true)"
[ -n "$BRANCH" ] || { echo "✗ el repo no tiene refs de $APP_ID"; exit 1; }
echo "→ rama: $BRANCH"

# 4) Bundle + checksums firmados
BUNDLE="$OUT/CatFlip-$VERSION.flatpak"
echo "→ bundle"
rm -f "$BUNDLE" "$BUNDLE.asc" "$BUNDLE.sig"
flatpak build-bundle "$OUT/repo" "$BUNDLE" "$APP_ID" "$BRANCH"

# 5) Firma detached + checksums (packaging/sign.sh, común a los 3)
"$ROOT/packaging/sign.sh" "$BUNDLE"

echo "✅ Flatpak listo en $OUT"
