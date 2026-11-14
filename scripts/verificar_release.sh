#!/usr/bin/env bash
# Verifica los assets YA PUBLICADOS de una release, tal como los recibe quien
# descarga.
#
# El camino firmado termina en `gh release upload` y ahí no se comprobaba nada:
# un asset subido truncado, un renombrado del job `release` que se rompe o un
# fichero que no llegó dejan una release que parece buena, y todo lo anterior
# (firmado y verificado sobre `dist/`) sigue verde. Este script trabaja sobre lo
# descargado, no sobre el build.
#
# Qué comprueba:
#   1. el juego EXACTO de 12 assets (3 paquetes, sus `.asc`, los `SHA256SUMS.*`
#      y sus `.asc`): sobra o falta uno → falla, que es como se ve que el
#      renombrado por formato dejó de funcionar;
#   2. las 3 firmas detached y los 3 `SHA256SUMS.*.asc` en una jaula de claves
#      VACÍA que solo importa `packaging/gpg/catflip-release.asc`, exigiendo
#      además que la firma sea de la huella de `FINGERPRINT`. Es exactamente el
#      chequeo de quien descarga: si verifica aquí, verifica en su máquina;
#   3. `sha256sum -c` de cada `SHA256SUMS.*` (un byte cambiado en la subida).
#
# Uso:
#   scripts/verificar_release.sh <directorio-con-los-assets>
#
# En un tag, la versión de `package.json` tiene que ser la del tag: los nombres
# de los assets salen de ella.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "$#" -ne 1 ] || [ ! -d "${1:-}" ]; then
  echo "Uso: scripts/verificar_release.sh <directorio-con-los-assets>" >&2
  exit 2
fi
DIR="$(cd "$1" && pwd)"

PYBIN="${PYBIN:-}"
if [ -z "$PYBIN" ]; then
  if [ -x .venv/bin/python ]; then
    PYBIN=.venv/bin/python
  elif command -v python3 > /dev/null 2>&1; then
    PYBIN=python3
  else
    PYBIN=python
  fi
fi

VERSION="$("$PYBIN" -c "import json; print(json.load(open('package.json'))['version'])")"
if [[ "${GITHUB_REF:-}" == refs/tags/* && "v$VERSION" != "${GITHUB_REF_NAME:-}" ]]; then
  echo "::error::tag ${GITHUB_REF_NAME} ≠ package.json $VERSION" >&2
  exit 1
fi

APPIMAGE="CatFlip-$VERSION-x86_64.AppImage"
FLATPAK="CatFlip-$VERSION.flatpak"
EXE="CatFlip-$VERSION-x64.exe"
ESPERADOS=(
  "$APPIMAGE" "$APPIMAGE.asc" "SHA256SUMS.appimage" "SHA256SUMS.appimage.asc"
  "$FLATPAK" "$FLATPAK.asc" "SHA256SUMS.flatpak" "SHA256SUMS.flatpak.asc"
  "$EXE" "$EXE.asc" "SHA256SUMS.windows" "SHA256SUMS.windows.asc"
)

# 1) Juego exacto: los assets de una release son planos, y el job `release`
#    renombra los SHA256SUMS por formato porque los tres se llaman igual.
faltan=()
sobran=()
for nombre in "${ESPERADOS[@]}"; do
  [ -f "$DIR/$nombre" ] || faltan+=("$nombre")
done
while IFS= read -r ruta; do
  base="${ruta##*/}"
  printf '%s\n' "${ESPERADOS[@]}" | grep -qxF "$base" || sobran+=("$base")
done < <(find "$DIR" -maxdepth 1 -type f)

# Un `[ ... ] && echo` colgado bajo `set -e` cortaría el script cuando el
# primer conjunto está vacío y se perdería el segundo mensaje.
if [ "${#faltan[@]}" -gt 0 ]; then
  echo "::error::faltan assets de la release: ${faltan[*]}" >&2
fi
if [ "${#sobran[@]}" -gt 0 ]; then
  echo "::error::assets inesperados en la release: ${sobran[*]}" >&2
fi
if [ "${#faltan[@]}" -gt 0 ] || [ "${#sobran[@]}" -gt 0 ]; then
  exit 1
fi

# 2) y 3) Firma y checksums con la clave publicada, sin claves del entorno.
#    Jaula RELATIVA: gpg en Git Bash es binario nativo y no entiende /tmp/...
PUB="packaging/gpg/catflip-release.asc"
FPR="$(tr -d '[:space:]' < packaging/gpg/FINGERPRINT)"
JAULA="build/gnupg-release"

# shellcheck disable=SC2317,SC2329  # se invoca vía trap
limpiar_jaula() {
  gpgconf --homedir "$JAULA" --kill all 2> /dev/null || true
  rm -rf "$JAULA"
}
trap limpiar_jaula EXIT

rm -rf "$JAULA"
mkdir -p "$JAULA"
chmod 700 "$JAULA"
gpg --homedir "$JAULA" --batch --quiet --import "$PUB"
if ! gpg --homedir "$JAULA" --batch --with-colons --list-keys 2> /dev/null |
  awk -F: '$1 == "fpr" { print $10 }' | grep -qx "$FPR"; then
  echo "::error::$PUB no contiene la huella de FINGERPRINT ($FPR)" >&2
  exit 1
fi

# Compara el estado de gpg con la huella esperada: una firma de otra clave (o
# un asset sin firma) no vale aunque gpg salga 0 por confianza.
verificar_firma() {
  local formato="$1" fichero="$2" estados
  if ! estados="$(gpg --homedir "$JAULA" --batch --status-fd 1 \
    --verify "$DIR/$fichero.asc" "$DIR/$fichero" 2> /dev/null)"; then
    echo "::error::$formato: la firma de $fichero no verifica con la clave publicada" >&2
    sed -n 's/^\[GNUPG:\] \(ERRSIG\|NO_PUBKEY\|BADSIG\|EXPKEYSIG\).*/  \1/p' \
      <<< "$estados" >&2
    return 1
  fi
  if ! grep -q "^\[GNUPG:\] VALIDSIG $FPR " <<< "$estados"; then
    echo "::error::$formato: $fichero.asc no está firmado por $FPR" >&2
    grep "^\[GNUPG:\] VALIDSIG" <<< "$estados" | sed 's/^/  /' >&2
    return 1
  fi
}

verificar_formato() {
  local formato="$1" fichero="$2" sums="$3"
  verificar_firma "$formato" "$fichero"
  verificar_firma "$formato" "$sums"
  # `sha256sum -c` necesita el CWD del directorio: los SHA256SUMS.* llevan el
  # nombre base del bundle, sin ruta.
  if ! (cd "$DIR" && sha256sum --quiet -c "$sums" > /dev/null 2>&1); then
    echo "::error::$formato: $sums no cuadra con $fichero (subida truncada o fichero cambiado)" >&2
    (cd "$DIR" && sha256sum -c "$sums" 2>&1 | grep -v ": OK$" | sed 's/^/  /') >&2 || true
    return 1
  fi
  echo "✓ $formato: firma de $FPR y checksums correctos"
}

verificar_formato "AppImage" "$APPIMAGE" "SHA256SUMS.appimage"
verificar_formato "Flatpak" "$FLATPAK" "SHA256SUMS.flatpak"
verificar_formato ".exe" "$EXE" "SHA256SUMS.windows"

echo "✅ release $VERSION: 12 assets, firmas y checksums verificados con $FPR"
