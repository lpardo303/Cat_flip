# 📦 Packaging firmado de Cat_flip (AppImage + Flatpak + .exe Windows)

Builds **locales y reproducibles** del core MIT en tres formatos, todos
firmados con GPG y con `SHA256SUMS` firmados. Nada se publica desde aquí: los
artefactos quedan en `dist/` (ignorado por git).

| Formato | Script | Artefactos |
|---|---|---|
| AppImage | `packaging/appimage/build.sh` | `dist/appimage/CatFlip-<ver>-x86_64.AppImage` + `.asc` + `SHA256SUMS` + `SHA256SUMS.asc` |
| Flatpak | `packaging/flatpak/build.sh` | `dist/flatpak/repo/` (ostree firmado) + `dist/flatpak/CatFlip-<ver>.flatpak` + `.asc` + `SHA256SUMS(.asc)` |
| .exe Windows | `packaging/windows/build.sh` (Git Bash) | `dist/windows/CatFlip-<ver>-x64.exe` (onefile) + `.asc` + `SHA256SUMS(.asc)` |

Los dos formatos envuelven **el mismo binario** `dist/CatFlip/` que genera
PyInstaller desde `packaging/appimage/catflip.spec` (`entry.py` ejecuta
`app.py` con los recursos en su sitio), así que AppImage y Flatpak corren
exactamente el mismo código.

## Prerrequisitos

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder          # builder aislado
flatpak install --system -y flathub \
  org.freedesktop.Platform//26.08 org.freedesktop.Sdk//26.08   # ver «Decisiones»
```

`appimagetool` se descarga solo en el primer build y se verifica contra el
hash de `packaging/appimage/pins.env` antes de usarse (si no coincide, el
build para).

## La clave de firma

- Firma con la clave dedicada **Cat_flip Release**
  (`lpardo303@users.noreply.github.com`), huella en
  `packaging/gpg/FINGERPRINT`:

  ```
  E3DC 6786 64E1 2570 15B3  645C DE7C B5CA 87D2 DD91
  ```

- La **pública** está versionada en `packaging/gpg/catflip-release.asc` — es
  la que reparten los usuarios para verificar. La **privada vive solo en
  `~/.gnupg`** y nunca se commitea (sin passphrase para poder firmar en
  scripts; si prefieres passphrase, créala con
  `gpg --s2k-mode 3 --passphrase` y firma con el agente).
- Rotación: `gpg --quick-generate-key ...` nueva → actualizar
  `FINGERPRINT` y `catflip-release.asc` en el mismo commit, y recomunicar
  la pública. **`packaging/sign.sh` lo verifica**: antes de firmar exige que
  el `.asc` versionado contenga la huella de `FINGERPRINT` (si no, falla sin
  llegar a firmar), y después comprueba las dos firmas en una jaula de claves
  vacía con **solo** esa clave pública — exactamente lo que hace quien
descarga el paquete. Una rotación a medias ya no puede publicar `.asc` que no
  verifiquen con la clave que se distribuye.

## Build

```bash
packaging/appimage/build.sh                  # congelado + AppImage + firma
packaging/flatpak/build.sh                   # congelado + flatpak + firma
packaging/windows/build.sh                   # Git Bash: congelado + .exe + firma
SKIP_FROZEN=1 packaging/appimage/build.sh    # reutiliza dist/CatFlip ya construido
SKIP_FROZEN=1 packaging/flatpak/build.sh
SKIP_SIGN=1 packaging/appimage/build.sh      # sin firmar (CI: no hay clave)
```

Los tres `build.sh` construyen **y llaman a `packaging/sign.sh`**, que es el
único sitio donde vive la firma (detached `.asc` + `SHA256SUMS` firmado):
antes ese bloque estaba copiado en los tres. Con `SKIP_SIGN=1` construyen sin
tocar la clave. La secuencia completa de un release —y la que sigue la CI—
es:

```bash
SKIP_SIGN=1 packaging/appimage/build.sh        # 1. construir
scripts/smoke_package.sh appimage              # 2. ejecutar el artefacto REAL
packaging/sign.sh dist/appimage/*.AppImage     # 3. firmar
packaging/sign.sh --verificar dist/appimage/*.AppImage   # 4. comprobar
```

**Windows**: el build se hace en **Git Bash**, no en PowerShell — `gpg` y
`sha256sum` viven en `/usr/bin` de Git for Windows y no están en el PATH de
PowerShell (así lo lleva la CI: jobs `windows` y `windows-exe`, ambos con
`shell: bash`). El spec
`packaging/windows/catflip.spec` produce un **onefile** `dist/CatFlip.exe`
que el script renombra y firma; reutiliza `packaging/appimage/entry.py`.
Local solo funciona en un host Windows (en Linux el artefacto no lleva
`.exe` y el script lo rechaza).

**Una excepción al «smoke antes de firmar»**: el repo ostree que va dentro
del `.flatpak` se firma al construirlo (`flatpak build-export --gpg-sign`) y
`flatpak install` la exige, así que ahí la clave entra antes del build. Lo
que se firma después del smoke en los tres formatos es el `.asc` detached y
los `SHA256SUMS`, que es lo que el usuario verifica con `gpg --verify`.

El primer build tarda ~1 min (PyInstaller) + ~2,5 min (flatpak-builder).
Los pines de herramientas viven en `packaging/appimage/pins.env`.

## Verificar y instalar

```bash
# AppImage
gpg --verify dist/appimage/CatFlip-1.0.0-x86_64.AppImage.asc \
             dist/appimage/CatFlip-1.0.0-x86_64.AppImage
(cd dist/appimage && gpg --verify SHA256SUMS.asc SHA256SUMS && sha256sum -c SHA256SUMS)
chmod +x dist/appimage/CatFlip-1.0.0-x86_64.AppImage && ./dist/appimage/CatFlip-1.0.0-x86_64.AppImage

# Flatpak — repo local con verificación GPG obligatoria
flatpak remote-add --user --gpg-import=packaging/gpg/catflip-release.asc \
  catflip-local "file://$PWD/dist/flatpak/repo"
flatpak install --user -y catflip-local io.github.lpardo303.CatFlip
flatpak run io.github.lpardo303.CatFlip

# O directamente desde el bundle (firma en el .asc)
gpg --verify dist/flatpak/CatFlip-1.0.0.flatpak.asc dist/flatpak/CatFlip-1.0.0.flatpak
flatpak install --user --bundle dist/flatpak/CatFlip-1.0.0.flatpak
```

Al arrancar cualquiera de los tres formatos, el binario levanta el
servidor y **abre la URL en tu navegador por defecto** en cuanto el
puerto responde (hasta 30 s de espera). Lo hace `openbrowser.py`, junto
a `entry.py`, y vale igual dentro del sandbox del Flatpak: el `xdg-open`
del runtime `26.08` resuelve por el portal OpenURI, así que **no hace
falta ningún `finish-arg` extra** — solo el `--share=network` que ya
tiene el manifiesto, para que el navegador del host llegue a
`127.0.0.1:5050`. `CATFLIP_NO_BROWSER=1` lo desactiva (servidores,
sesiones remotas, lanzadores propios); en CI y sin sesión gráfica no se
intenta y el servidor arranca igual.

Comprobado en este repo: el repo con `gpg-verify=1` **rechaza** un
`summary.idx` alterado (`BAD signature ... key ID DE7CB5CA87D2DD91`) e
instala el original; nota que `summary.idx.sig` es un contenedor ostree
(`ostree.gpgsigs`), así que se verifica con `flatpak`, no con `gpg` suelto —
los `.asc` del AppImage y del bundle sí son OpenPGP puro y `gpg --verify`
los valida.

## Decisiones técnicas (no tocar sin leer)

- **Runtime `26.08`, no `25.08`**: el binario se enlaza contra el glibc del
  host (2.44). FDO 25.08 trae glibc 2.42 y el binario muere con
  `GLIBC_2.44 not found`; FDO 26.08 lleva 2.44 y arranca.
- **SDK a nivel de sistema**: `org.flatpak.Builder` resuelve el SDK con
  `flatpak info …` ejecutado *en el host*, donde no ve la instalación de
  usuario (el `XDG_DATA_HOME` del sandbox se le cuela). Con el SDK solo en
  `--user` el build falla con `org.freedesktop.Sdk/x86_64/26.08 not
  installed`; por eso el prerrequisito es `flatpak install --system`.
- **Sin Python en el runtime**: FDO no incluye Python de aplicación; la app
  trae su intérprete congelado (por eso el mismo onedir sirve para ambos
  formatos y no hace falta pip dentro del sandbox).
- **App id `io.github.lpardo303.CatFlip`**: ya cumple la convención de
  Flathub por si se publica allí (metainfo y desktop incluidos).

## CI (GitHub Actions)

`.github/workflows/packaging.yml` construye, prueba y firma los tres paquetes
en cada tag `v*`, bajo demanda con `workflow_dispatch` y **cada lunes a las
04:15 UTC** (`schedule`):

La corrida semanal existe porque el camino firmado solo se ejercitaba al
publicar. Hace lo mismo que un tag **menos publicar**: importa la clave GPG,
construye con `flatpak-builder` y el runtime 26.08, pasa los tres smokes, firma
y verifica. El job `release` no se ejecuta (está atado a `refs/tags/`) y los
artifacts no se suben (`if: github.event_name != 'schedule'`), así que no
distribuye nada: si la clave caduca, el secreto se rota mal o flathub retira el
runtime, se ve en el lunes siguiente y no en el tag. GitHub desactiva los
workflows programados tras 60 días sin actividad en el repo; si el cron deja de
aparecer, hay que reactivarlo en la pestaña Actions.

- **En cada PR**, el job `linux-bundles` de `ci.yml` construye el AppImage y el
  Flatpak **sin firmar** en un solo runner y les pasa el mismo
  `scripts/smoke_package.sh` con `--version-check-una-llamada`: una sola petición a `/version/check` que
  exige `checked:true` (el tag mantiene el backoff de 305 s por intento). Ante
  `checked:false` se consulta `/rate_limit` —no consume cuota— para no fallar
  por un límite ajeno al bundle; con cuota disponible, `checked:false` es la
  regresión de CAs. El binario congelado se construye una vez y el Flatpak lo
  reutiliza con `SKIP_FROZEN=1`; antes estos dos bundles solo se probaban en
  el tag, así que una regresión de empaquetado llegaba a `main`. El job se
  salta solo si el diff no toca nada que acabe en el bundle
  (`scripts/toca_bundle.sh` mediante el job `cambios`), y responde «construir»
  ante cualquier duda.
- **Los tres jobs del tag siguen el mismo orden**: construir → `scripts/smoke_package.sh
  <formato>` → `packaging/sign.sh <artefacto>` → `packaging/sign.sh --verificar
  <artefacto>` → subida de artifacts. El smoke es **el mismo** para AppImage,
  Flatpak y `.exe` (delega en `scripts/smoke_lecturas.py` y
  `scripts/smoke_version_check.sh`): arranca el artefacto real, lee los
  fixtures versionados —CSV/TSV/XLSX/XLS/XLSB/ODS/Parquet/JSON—, comprueba
  `/get_sheets`, `/premium/status` y `/version/check`. Antes cada job tenía su
  copia del smoke y solo el `.exe` comprobaba lecturas; el AppImage y el
  Flatpak se conformaban con que `/` respondiera.
- **appimage** / **flatpak**: pip, `build.sh` con `SKIP_SIGN=1` (AppImage) o
  con la firma ostree interna (Flatpak, que `flatpak install` exige), smoke,
  firma detached y verificación. El job de flatpak instala `flatpak-builder`
  con apt y el runtime 26.08 en `--user`, y usa
  `FLATPAK_BUILDER_CMD=flatpak-builder` (sin el sandbox de
  `org.flatpak.Builder` no existe el problema de la instalación de sistema).
- **windows** (`windows-latest`, todo en `shell: bash`): primer paso de
  comprobación de las herramientas de Git Bash, pip, `build.sh` con
  `SKIP_SIGN=1`, el mismo smoke que los otros dos y firma posterior.
- **release** (solo en tag): crea la release si no existe y adjunta los
  artefactos con `gh release upload` (AppImage, flatpak y `.exe`, con los
  `SHA256SUMS.*` renombrados por formato).
- **verificar-release** (solo en tag, después de `release`): el último tramo
  que nadie comprobaba. Todo lo anterior verifica sobre `dist/`, así que un
  asset subido truncado o un renombrado roto dejaba una release mal publicada
  con la CI en verde. Este job **descarga los assets publicados** y ejecuta
  `scripts/verificar_release.sh release`: juego exacto de 12 assets, las 3
  firmas y los 3 `SHA256SUMS.*.asc` en una jaula vacía que solo importa
  `packaging/gpg/catflip-release.asc` (exigiendo además la huella de
  `FINGERPRINT`), y `sha256sum -c` de cada `SHA256SUMS.*`. Después arranca el
  `.AppImage` **descargado** con el smoke completo. Si falla, la release existe
  pero queda probado que sus assets están mal: el rojo es la señal.
- **Firma ostree del Flatpak**: el smoke del job `flatpak` usa
  `--exigir-firma-ostree`, que importa el bundle a un repo temporal con una
  jaula que solo tiene la pública versionada y exige `Good signature`. Sin
  eso, un bundle **sin** firma interna se instala igual y el smoke pasaría: se
  probó que `flatpak install --gpg-file=<otra clave>` también lo instala, así
  que `--gpg-file` no restringe, solo añade claves. Los jobs de PR construyen
  sin firma y por eso no llevan el flag.

### Secreto obligatorio

La clave privada vive **solo** como secreto del repo **`GPG_SIGNING_KEY`**
nunca en el código ni en el chat. Exportarla en local y añadirla en
Settings → Secrets and variables → Actions:

```bash
gpg --armor --export-secret-keys "$(tr -d '[:space:]' < packaging/gpg/FINGERPRINT)" > /tmp/catflip-signing.key
```

Sin el secreto, los jobs fallan al inicio con
`::error::Falta el secreto GPG_SIGNING_KEY` — a propósito: no se publica nada
sin firmar. Si la huella del secreto no coincide con `packaging/gpg/FINGERPRINT`,
falla el paso de firma (`gpg --local-user`).

### Compatibilidad

El binario se enlaza contra el glibc del runner (`ubuntu-latest`), igual que en
local contra el del host (2.44). Bajar el suelo de compatibilidad (p. ej.
Ubuntu 22.04) exigiría construir en un contenedor antiguo.

## Límites de esta iteración

- **No publicado**: ni Flathub ni AppImageHub (la release de GitHub en tags
  sí se publica sola).
- El `.exe` de Windows se **construye y firma en la CI** (no hay build
  local posible fuera de un host Windows); el auto-update sigue en el
  roadmap Open Core (`premium/README.md`).
