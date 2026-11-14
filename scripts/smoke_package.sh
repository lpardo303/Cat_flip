#!/usr/bin/env bash
# Smoke de un paquete YA construido, idéntico para los tres formatos.
#
# Uso:
#   scripts/smoke_package.sh appimage|flatpak|windows [--version-check-una-llamada]
#                                                [--exigir-firma-ostree]
#
# --version-check-una-llamada hace el paso 5 con UNA sola petición, sin el
# backoff de 305 s por intento que usa el tag. Lo usan los jobs de PR: así una
# regresión de CAs en el bundle (sin almacén de CAs no hay HTTPS con
# api.github.com) se ve en el PR y no al publicar, sin pagar el backoff.
#
# --exigir-firma-ostree exige que el bundle lleve su firma ostree interna
# válida con la clave publicada. Sin el flag, un bundle SIN firmar se instala
# igual y el smoke pasa: `flatpak install --gpg-file` no sirve como guardia
# porque AÑADE la clave a las ya confiables en vez de restringirlas (probado:
# con otra clave en --gpg-file el bundle se instala igual). Solo lo usan los
# jobs que firman (tag y cron); los de PR construyen sin firma y romperían.
#
# Antes había tres pasos de workflow con ~50 líneas cada uno que se habían
# ido copiando: solo el .exe comprobaba que el paquete LEYERA un archivo, y el
# AppImage y el Flatpak se conformaban con que `/` respondiera. Un bundle sin
# `python_calamine` arrancaba, servía `/` y fallaba al subir un `.xls`. Aquí
# hay una sola implementación y los tres pasan exactamente lo mismo:
#
#   1. exige UN bundle en dist/<formato>/ (0 = build incompleto, >1 = residuo
#      de otra versión) y, en un tag, que la versión sea la del tag;
#   2. lo arranca por el camino del usuario final (AppRun extraído del
#      AppImage, `flatpak install` + `flatpak run`, o el .exe directo);
#   3. espera a que `/` responda;
#   4. scripts/smoke_lecturas.py: los 8 formatos de entrada, /get_sheets,
#      /premium/status y el anuncio de formatos en la página;
#   5. scripts/smoke_version_check.sh: /version/check (el único HTTPS del
#      bundle, con su backoff) y que el current EMPAQUETADO sea el del build;
#   6. limpia SIEMPRE (trap): mata la app, desinstala el flatpak y borra el
#      directorio temporal del AppImage, también si un check falla.
#
# Se ejecuta ANTES de firmar (packaging/sign.sh): firmar y verificar un
# artefacto que nunca se ha ejecutado produce .asc válidos de un paquete roto.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FORMATO="${1:-}"
shift || true
MODO_VERSION=""
for arg in "$@"; do
  case "$arg" in
    --version-check-una-llamada) MODO_VERSION="--una-llamada" ;;
    --exigir-firma-ostree) EXIGIR_FIRMA_OSTREE=1 ;;
    *)
      echo "Opción desconocida: $arg" >&2
      echo "Uso: scripts/smoke_package.sh appimage|flatpak|windows" \
        "[--version-check-una-llamada] [--exigir-firma-ostree]" >&2
      exit 2
      ;;
  esac
done

if [ -n "${EXIGIR_FIRMA_OSTREE:-}" ] && [ "$FORMATO" != "flatpak" ]; then
  echo "::error::--exigir-firma-ostree solo aplica al Flatpak (formato: ${FORMATO:-ninguno})" >&2
  exit 2
fi

case "$FORMATO" in
  appimage)
    PATRON="dist/appimage/CatFlip-*.AppImage"
    ETIQUETA="AppImage"
    ;;
  flatpak)
    PATRON="dist/flatpak/CatFlip-*.flatpak"
    ETIQUETA="Flatpak"
    ;;
  windows)
    PATRON="dist/windows/CatFlip-*.exe"
    ETIQUETA=".exe"
    ;;
  *)
    echo "Uso: scripts/smoke_package.sh appimage|flatpak|windows" >&2
    exit 2
    ;;
esac

APP_ID="io.github.lpardo303.CatFlip"
BASE_URL="http://127.0.0.1:5050"
OSTREE_TMP=""

# Firma ostree interna del bundle: se importa a un repo temporal con una jaula
# de claves que SOLO tiene la pública versionada y se exige «Good signature».
# `flatpak install` no vale como comprobación (un bundle sin firmar se instala),
# y `flatpak build-import-bundle` tampoco verifica. Para que ostree encuentre la
# clave, el homedir necesita además `trustedkeys.gpg`: con solo `pubring.kbx`
# responde «public key not found». Se acepta ÚNICAMENTE el éxito literal, así
# que una firma ausente, de otra clave o rota falla igual.
# shellcheck disable=SC2317,SC2329  # se invoca desde la rama flatpak
verificar_firma_ostree() {
  local bundle="$1" ref commit salida esperado
  if ! command -v ostree > /dev/null 2>&1; then
    echo "::error::--exigir-firma-ostree necesita ostree (viene con flatpak)" >&2
    return 1
  fi
  OSTREE_TMP="$(mktemp -d)"
  mkdir -p "$OSTREE_TMP/gpg" "$OSTREE_TMP/repo"
  chmod 700 "$OSTREE_TMP/gpg"
  gpg --homedir "$OSTREE_TMP/gpg" --batch --quiet \
    --import packaging/gpg/catflip-release.asc 2> /dev/null
  gpg --homedir "$OSTREE_TMP/gpg" --export \
    > "$OSTREE_TMP/gpg/trustedkeys.gpg" 2> /dev/null
  ostree init --repo="$OSTREE_TMP/repo" --mode=archive > /dev/null 2>&1
  flatpak build-import-bundle "$OSTREE_TMP/repo" "$bundle" > /dev/null 2>&1 || {
    echo "::error::no se pudo importar $bundle para comprobar su firma" >&2
    return 1
  }
  ref="$(ostree --repo="$OSTREE_TMP/repo" refs | head -1)"
  if [ -z "$ref" ]; then
    echo "::error::$bundle no declara ninguna ref: no se puede comprobar su firma" >&2
    return 1
  fi
  commit="$(ostree --repo="$OSTREE_TMP/repo" rev-parse "$ref")"
  salida="$(ostree --repo="$OSTREE_TMP/repo" show \
    --gpg-homedir="$OSTREE_TMP/gpg" "$commit" 2>&1)"
  esperado="$(tr -d '[:space:]' < packaging/gpg/FINGERPRINT)"
  if ! grep -q "Good signature" <<< "$salida"; then
    echo "::error::$bundle no lleva una firma ostree válida con la clave" \
      "publicada ($esperado): el bundle no se puede verificar." >&2
    grep -iE "signature|firma|not found|key ID" <<< "$salida" | sed 's/^/  /' >&2
    return 1
  fi
  echo "  firma ostree interna: $(grep -i "Good signature" <<< "$salida" | sed 's/^ *//')"
}


# Python del proyecto: .venv si existe (local); si no, el del entorno (CI).
# En Windows `python3` puede no existir y sí `python`.
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

# En un tag, la release, el bundle y package.json deben llevar la MISMA
# versión: los binarios se nombran con ella y el asset de la release también.
if [[ "${GITHUB_REF:-}" == refs/tags/* && "v$VERSION" != "${GITHUB_REF_NAME:-}" ]]; then
  echo "::error::tag ${GITHUB_REF_NAME} ≠ package.json $VERSION" >&2
  exit 1
fi

# El glob debe casar EXACTAMENTE con 1 bundle: 0 = build incompleto y >1 =
# residuo de otra versión (un `head -1` se comió el bundle 1.0.0 antiguo en
# local en vez del 1.5.0). Error claro, no elegir el primero a ciegas.
mapfile -t BUNDLES < <(compgen -G "$PATRON" || true)
if [ "${#BUNDLES[@]}" -ne 1 ]; then
  echo "::error::Se esperaba exactamente 1 $ETIQUETA en $(dirname "$PATRON");" \
    "hay ${#BUNDLES[@]} (${BUNDLES[*]:-ninguno})" >&2
  exit 1
fi
BUNDLE="${BUNDLES[0]}"

LOG="$(mktemp)"
SCRATCH=""
APP_PID=""
# Si nunca se llegó a arrancar (p. ej. el guard del puerto), no hay log que
# volcar y el «— log del paquete —» vacío despista.
ARRANCADO=0

cleanup() {
  local estado=$?
  trap - EXIT INT TERM
  set +e
  if [ -n "$APP_PID" ]; then
    kill "$APP_PID" 2> /dev/null
  fi
  if [ "$FORMATO" = "flatpak" ]; then
    # `flatpak run` deja el bwrap colgando si solo se mata al cliente: se
    # mata por app-id y se espera a que desaparezca antes de desinstalar.
    flatpak kill "$APP_ID" 2> /dev/null
    for _ in 1 2 3 4 5; do
      flatpak ps 2> /dev/null | grep -q "$APP_ID" || break
      sleep 1
    done
    flatpak --user uninstall -y --delete-data "$APP_ID" 2> /dev/null
  fi
  # En Windows el onefile deja un hijo: matar el PID de bash no basta.
  if [ "$FORMATO" = "windows" ] && command -v taskkill > /dev/null 2>&1; then
    taskkill //F //IM CatFlip.exe > /dev/null 2>&1
  fi
  if [ -n "$SCRATCH" ]; then
    rm -rf "$SCRATCH"
  fi
  if [ -n "$OSTREE_TMP" ]; then
    rm -rf "$OSTREE_TMP"
  fi
  if [ "$estado" -ne 0 ] && [ "$ARRANCADO" = "1" ]; then
    echo "" >&2
    echo "— log del paquete ($ETIQUETA) —" >&2
    tail -60 "$LOG" >&2
  fi
  rm -f "$LOG"
  exit "$estado"
}
trap cleanup EXIT INT TERM

# Si ya hay algo en el puerto, el smoke mediría el proceso equivocado: un
# AppImage que no muere del todo, un `python app.py` olvidado o un job
# anterior en el mismo runner. Falso verde por diseño, así que se corta.
if curl -sf -o /dev/null --max-time 2 "$BASE_URL/"; then
  echo "::error::Ya hay algo escuchando en $BASE_URL: el smoke probaría ese" \
    "proceso en vez de $BUNDLE. Libéralo (ss -ltnp | grep 5050) y repite." >&2
  exit 1
fi

echo "→ arrancando $BUNDLE (package.json $VERSION, ref ${GITHUB_REF_NAME:-local})"
ARRANCADO=1
case "$FORMATO" in
  appimage)
    # FUSE no siempre está en el runner: se extrae y se lanza AppRun, que es
    # además el squashfs real que se distribuye. La extracción va a un
    # directorio FUERA de dist/ (dentro viajaba al artefacto del job).
    chmod +x "$BUNDLE"
    SCRATCH="$(mktemp -d)"
    (cd "$SCRATCH" && "$ROOT/$BUNDLE" --appimage-extract > /dev/null)
    (cd "$SCRATCH/squashfs-root" && exec ./AppRun > "$LOG" 2>&1) &
    APP_PID=$!
    ;;
  flatpak)
    # --user: la misma instalación donde el job ya puso el runtime.
    # --reinstall: si una corrida anterior dejó la app instalada, `install` a
    # secas falla con «ya está instalada» y el smoke parecería roto.
    # El bundle lleva su firma ostree interna; lo que se difiere hasta después
    # del smoke es la firma detached y los checksums.
    if [ -n "${EXIGIR_FIRMA_OSTREE:-}" ]; then
      verificar_firma_ostree "$BUNDLE"
    fi
    flatpak install --user -y --reinstall "$BUNDLE"
    flatpak run "$APP_ID" > "$LOG" 2>&1 &
    APP_PID=$!
    ;;
  windows)
    CATFLIP_NO_BROWSER=1 "$BUNDLE" > "$LOG" 2>&1 &
    APP_PID=$!
    ;;
esac

# onefile (y el arranque en frío de un runner) tardan: 90 intentos de 1 s.
listo=0
for _ in $(seq 1 90); do
  if curl -sf -o /dev/null "$BASE_URL/"; then
    listo=1
    break
  fi
  sleep 1
done
if [ "$listo" != "1" ]; then
  echo "::error::/ no responde en 90 s" >&2
  exit 1
fi

"$PYBIN" scripts/smoke_lecturas.py --base-url "$BASE_URL"

# Sin modo, el tag paga el backoff completo; con modo, una sola llamada.
bash scripts/smoke_version_check.sh $MODO_VERSION \
  "$BASE_URL/version/check" "$LOG" "$VERSION"

echo "✓ $ETIQUETA E2E: /, lecturas y /version/check con current=$VERSION"
