#!/usr/bin/env bash
# Firma detached GPG + SHA256SUMS de un artefacto YA construido y YA probado.
#
# Uso:
#   packaging/sign.sh dist/appimage/CatFlip-1.6.0-x86_64.AppImage
#   packaging/sign.sh dist/flatpak/CatFlip-1.6.0.flatpak
#   SKIP_SIGN=1 packaging/sign.sh <artefacto>       # no firma (CI sin clave)
#   packaging/sign.sh --verificar <artefacto>       # comprueba firma + checksums
#
# `--verificar` existe porque el paso de la CI hacía `gpg --verify
# ./*.AppImage.asc ./*.AppImage`: con un `.asc` viejo en dist/ (residuo de
# otra versión), gpg verifica TODOS los .asc contra el mismo binario y uno
# sale «Firma INCORRECTA» aunque el bueno esté correcto. Aquí se nombra el
# artefacto exacto que se acaba de firmar.
#
# Vive aparte de los build.sh a propósito. Los tres build.sh firmaban al
# final del build y la CI ejecutaba el smoke DESPUÉS: se firmaban (y se
# verificaban) bundles que nadie había arrancado nunca. El orden correcto es
# construir → ejecutar el artefacto real → firmar, que es lo que hace
# scripts/smoke_package.sh entre medias.
#
# Recibe un solo artefacto: si el glob del llamador casa con dos (residuo de
# otra versión), falla en vez de firmar el que elija el shell.
#
# Comprueba que la clave con la que se firma sea la que se DISTRIBUYE
# (`packaging/gpg/catflip-release.asc`), en los dos sentidos: antes de firmar,
# que el `.asc` versionado contenga la huella de `packaging/gpg/FINGERPRINT`;
# y después, que las firmas verifiquen en una jaula de claves vacía con SOLO
# esa clave pública —lo mismo que hace quien descarga el paquete—. Una
# rotación a medias (clave nueva en el secreto y `FINGERPRINT`, `.asc` viejo, o
# al revés) publicaba `.asc` que no verificaban con la clave distribuida.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODO="firmar"
if [ "${1:-}" = "--verificar" ]; then
  MODO="verificar"
  shift
fi
if [ "$#" -ne 1 ]; then
  echo "Uso: packaging/sign.sh [--verificar] <artefacto>  (exactamente uno)" >&2
  exit 2
fi
ART="$1"
if [ ! -f "$ART" ]; then
  echo "::error::No existe el artefacto: $ART" >&2
  exit 1
fi

if [ "$MODO" = "verificar" ]; then
  DIR="$(cd "$(dirname "$ART")" && pwd)"
  NAME="$(basename "$ART")"
  gpg --verify "$ART.asc" "$ART"
  (
    cd "$DIR"
    gpg --verify SHA256SUMS.asc SHA256SUMS
    sha256sum -c SHA256SUMS
  )
  echo "✅ firma y checksums verificados: $NAME"
  exit 0
fi

if [ "${SKIP_SIGN:-0}" = "1" ]; then
  echo "→ firma omitida (SKIP_SIGN=1): $(basename "$ART") queda sin firmar"
  exit 0
fi

FPR="$(tr -d '[:space:]' < "$ROOT/packaging/gpg/FINGERPRINT")"
# gpg y sha256sum viven en Git Bash en Windows (no en el PATH de PowerShell);
# el build no los necesita para nada, así que la comprobación vive aquí.
for tool in gpg sha256sum; do
  if ! command -v "$tool" > /dev/null 2>&1; then
    echo "::error::Falta «$tool». En Windows usa Git Bash (gpg y sha256sum" \
      "viven en /usr/bin) o instala GnuPG con choco install gnupg."
    exit 1
  fi
done

# GnuPG en Git Bash es un binario nativo: no entiende rutas POSIX (/tmp/...,
# /d/...). Por eso, desde aquí y para todo lo que toque gpg, se trabaja con
# rutas RELATIVAS a la raíz del repo (la CI pasa los artefactos así).
cd "$ROOT"
PUB="packaging/gpg/catflip-release.asc"
# La jaula de claves también relativa, por el mismo motivo.
JAULA="build/gnupg-publica"

if [ ! -f "$PUB" ]; then
  echo "::error::Falta la clave pública versionada: $ROOT/$PUB" >&2
  exit 1
fi

# 1) Antes de firmar: la clave que se distribuye tiene que ser esta misma.
#    Falla aquí y no después para no dejar `.asc` de una clave que los
#    usuarios no tienen (y para no tocar el artefacto ya construido).
publicadas="$(gpg --batch --with-colons --import-options show-only \
  --import "$PUB" 2> /dev/null | awk -F: '$1 == "fpr" { print $10 }')"
if ! grep -qx "$FPR" <<< "$publicadas"; then
  echo "::error::La clave pública versionada no es la de FINGERPRINT." \
    "$PUB trae [${publicadas//$'\n'/, }] y FINGERPRINT dice $FPR:" \
    "rotación a medias — los .asc publicados NO verificarían con la clave" \
    "que se distribuye. Actualiza el .asc y la huella en el mismo commit." >&2
  exit 1
fi

NAME="$(basename "$ART")"
DIR="$(cd "$(dirname "$ART")" && pwd)"

echo "→ firma GPG ($FPR) de $NAME"
rm -f "$ART.asc" "$ART.sig"
gpg --batch --yes --armor --local-user "$FPR" --detach-sign "$ART"
(
  cd "$DIR"
  rm -f SHA256SUMS.asc SHA256SUMS.sig
  sha256sum "$NAME" > SHA256SUMS
  gpg --batch --yes --armor --local-user "$FPR" --detach-sign SHA256SUMS
)

# 2) Después de firmar: que verifiquen con LO MISMO que tiene el usuario, es
#    decir en una jaula de claves vacía que solo importa la clave publicada.
#    En la jaula normal verificaría igual aunque el .asc versionado fuera otro,
#    porque ahí está la privada.
rm -rf "$JAULA"
mkdir -p "$JAULA"
chmod 700 "$JAULA"
# shellcheck disable=SC2317,SC2329  # se invoca vía trap
limpiar_jaula() {
  gpgconf --homedir "$JAULA" --kill all 2> /dev/null || true
  rm -rf "$JAULA"
}
trap limpiar_jaula EXIT
ARTDIR="$(dirname "$ART")"
gpg --homedir "$JAULA" --batch --quiet --import "$PUB"
gpg --homedir "$JAULA" --batch --verify "$ART.asc" "$ART"
gpg --homedir "$JAULA" --batch --verify \
  "$ARTDIR/SHA256SUMS.asc" "$ARTDIR/SHA256SUMS"
echo "✅ las firmas verifican con la clave pública versionada"

echo "✅ firmado:"
ls -lh "$ART" "$ART.asc" "$DIR/SHA256SUMS" "$DIR/SHA256SUMS.asc"
