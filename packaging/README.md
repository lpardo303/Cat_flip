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

Desde la release 1.6.2 los paquetes llevan además **atestación de build**, que
se comprueba sin tocar la clave GPG y prueba qué workflow y qué commit los
produjo:

```bash
gh attestation verify CatFlip-1.6.2-x86_64.AppImage \
  --repo lpardo303/Cat_flip \
  --signer-workflow lpardo303/Cat_flip/.github/workflows/packaging.yml
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

Las `uses:` de los workflows van **fijadas por SHA de commit** con la versión en
un comentario (`actions/checkout@3d3c42e5… # v7`): una etiqueta mayor es un
puntero que se puede mover y ejecutar código distinto sin cambiar el repo.
Dependabot (`.github/dependabot.yml`) mantiene SHA y comentario al día en un
solo PR semanal; los binarios fijados por `sha256sum` (actionlint, shellcheck)
no son actions y se vigilan con el workflow «Avisos de versiones fijadas».

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
- **El smoke mira el peso y lo que viaja dentro** (`scripts/auditar_bundle.py`,
  antes de arrancar): el fichero distribuido tiene que caber en el presupuesto
  del formato (145 MiB AppImage, 110 flatpak, 72 `.exe`; medido sobre v1.6.0 y
  los builds locales, con ~10 % de margen), y desde entonces también falla si un
  fichero suelto pasa de 60 MiB (`TOPE_FICHERO`) o si se cuelan `.so.debug`,
  `.map`, `.pdb` o `node_modules`. Imprime los cinco ficheros más grandes y, en
  Actions, deja la tabla entera en el resumen del run (`$GITHUB_STEP_SUMMARY`),
  así que se lee en el PR sin abrir logs. Tampoco puede llevar `tests/`, `.git`,
  logs, `.env`, `__pycache__` ni un venv, e imprime el reparto del peso por
  grupos (`_internal/pyarrow`, `.so` de arrow, `numpy.libs`…) para que el
  tamaño quede justificado. Si el crecimiento es legítimo, se sube
  `PRESUPUESTO` en el mismo commit que lo explica. Los `.spec` filtran `tests`,
  `__pycache__`, `*.pyc` y `premium.key` de los `datas`: el primero que
  apareció fue `pyarrow/tests/`, que PyInstaller arrastraba por ser datos del
  paquete.
- **Peso relativo**: `verificar-release` compara cada paquete con el de la
  release publicada anterior (`scripts/comparar_tamanos.py`, umbral 15 %,
  `CRECIMIENTO_PCT` para ajustarlo) y falla si alguno crece de más: el tope
  absoluto deja engordar mientras quepa, este dice cuánto ha engordado.
- **El smoke arranca el bundle con una licencia premium de prueba**
  (`CATFLIP_PREMIUM_KEY=smoke`, misma idea que el job `axe` con `ci`). Sin
  licencia `/premium/status` sale vacío y los ficheros de `premium/themes` no
  se tocan nunca, así que un `datas` olvidado en el `.spec` solo rompía a quien
  paga. Con `--exigir-premium`, `scripts/smoke_lecturas.py` exige
  `licensed: true`, que el manifiesto liste los temas esperados
  (`premium.THEMES`) y que cada `/premium/themes/<id>.css` responda `text/css`
  con contenido; un `datas` ausente da 404 y corta el smoke en PR y en tag.
- **appimage** / **flatpak**: pip, `build.sh` con `SKIP_SIGN=1` (AppImage) o
  con la firma ostree interna (Flatpak, que `flatpak install` exige), smoke,
  firma detached y verificación. El job de flatpak instala `flatpak-builder`
  con apt y el runtime 26.08 en `--user`, y usa
  `FLATPAK_BUILDER_CMD=flatpak-builder` (sin el sandbox de
  `org.flatpak.Builder` no existe el problema de la instalación de sistema).
- **windows** (`windows-latest`, todo en `shell: bash`): primer paso de
  comprobación de las herramientas de Git Bash, pip, `build.sh` con
  `SKIP_SIGN=1`, el mismo smoke que los otros dos y firma posterior.
- **release** (solo en tag): crea la release **en borrador** si no existe y
  adjunta los artefactos con `gh release upload` (AppImage, flatpak y `.exe`,
  con los `SHA256SUMS.*` renombrados por formato). Antes de subir nada comprueba
  con `GET /compare/main...<tag>` que el commit del tag es ancestro de `main`
  (`behind`/`identical`): no se publica lo que no está en `main`. Si la release
  ya existiera **publicada**, el rerun solo sale verde cuando este build produce
  **exactamente los mismos bytes** (comparación `cmp` contra lo descargado); si
  difiere, falla diciendo qué fichero cambia: `--clobber` reescribiría ficheros
  que alguien ya descargó y verificó.
- **avisar-fallo** / **cerrar-aviso** (solo en la corrida programada): el cron
  existe para no descubrir en el tag una clave caducada o un runtime que
  desapareció, pero un lunes en rojo no lo mira nadie. Si la corrida semanal
  falla, `avisar-fallo` ejecuta `scripts/avisar_cron.py`, que abre un issue con
  la corrida, el commit y qué jobs fallaron; si ya hay uno abierto **comenta**
  en vez de duplicar, y si está cerrado lo reabre. Cuando la corrida vuelve a
  salir bien, `cerrar-aviso` comenta la corrida que lo arregló y lo **cierra**.
  Los dos necesitan `issues: write` (el único permiso que piden). El issue se
  localiza con `GET /search/issues` (`in:title`, `type:issue`), no listando los
  últimos 100: así sigue encontrándolo con el repo crecido. Un
  `workflow_dispatch` no dispara ni el aviso ni el cierre: quien lo lanza ya
  está mirando.
- **avisar-fallo-tag** / **cerrar-aviso-tag** (solo en tag): un tag en rojo
  dejaba el tag creado, la release sin publicar y **ningún aviso**; lo único
  que quedaba era un run en Actions. Mismo `scripts/avisar_cron.py` con `--tag`,
  título propio (`Fallo al publicar el tag vX.Y.Z`, para no mezclar dos tags) y
  `needs` con los seis jobs: un fallo al subir assets, al verificar o al
  publicar también cuenta. `cerrar-aviso-tag` exige `success()` de esos seis,
  así que un tag que publicó pero falló al verificar no cierra nada.
- **auditar-dependencias** / **avisar-caducidad** (solo en cron): `pip-audit`
  sobre `requirements.txt` (lo que se empaqueta, no lo que solo se testea) y
  `scripts/revisar_caducidad_clave.py`, que avisa 30 días antes de que caduque
  la clave de `FINGERPRINT`. Las dos cosas se descubrían el día del tag. Si
  alguno falla, entra en el aviso del cron como un job más. Ojo: la clave
  actual no tiene fecha de caducidad, así que hoy esa comprobación es un no-op
  — empieza a vigilar de verdad el día que se rote a una clave con expiración.
- **`concurrency: packaging-${{ github.ref }}`** y permisos mínimos: el workflow
  solo declara `contents: read` y cada job que escribe pide lo suyo
  (`release`, `publicar` y `limpiar-borradores` → `contents: write`; los avisos
  → `issues: write`). Dos tags a la vez no se pelean por el mismo borrador.
- **Reverificación mensual** (`.github/workflows/reverificar-release.yml`, día 1
  a las 05:00 UTC): baja la release `latest` y repite el chequeo del usuario
  —12 assets, firmas, checksums y smoke del AppImage— semanas después de
  publicar. Si falla, abre su propio issue con `scripts/avisar_cron.py` y
  `TITULO_PERSONALIZADO`. Detecta que un asset cambió en el alojamiento o que
  el binario dejó de arrancar. **Probado a mano** contra `v1.6.1` real
  (`workflow_dispatch` → run 44304274291, verde): bajó los 12 assets,
  `⚠ release anterior al manifiesto firmado` y `✅ release 1.6.1: 12 assets`,
  y el AppImage descargado pasó el smoke completo (13 comprobaciones,
  `current=1.6.1`). El smoke tardó 308 s porque el runner llegó con la cuota
  anónima agotada y el backoff esperó 305 s al TTL de la caché de error: es el
  comportamiento diseñado, no un cuelgue.
  **Fallo latente que destapó esa prueba**: el workflow verificaba con el
  `package.json` de `main`, así que en cuanto `main` va por delante de la
  última release (versión subida antes del tag) la comprobación «tag ==
  package.json» habría fallado cada mes sin nada roto. Ahora los scripts siguen
  saliendo de `main` pero la versión se trae del tag (`git fetch --depth=1
  origin refs/tags/$TAG` + `git checkout FETCH_HEAD -- package.json`). Probado
  en el escenario exacto: rama desechable con `package.json` en `1.6.2` y
  release `v1.6.1` → run 44305405945 verde, `→ package.json del tag v1.6.1:
  "version": "1.6.1"` y `✅ release 1.6.1: 12 assets` (rama borrada después).
- **Cuánto tarda el smoke del Flatpak**: medido con la API sobre dos corridas
  idénticas en pasos. En el tag de v1.6.1 (run 43910429952) el smoke tardó
  **17,0 min** y el job **21,6 min**; en el dispatch de verificación
  (43926902589) el mismo paso tardó **19 s** y el job **4,1 min**. La diferencia
  está fuera del workflow (Flathub / red del runner), no en el bundle, así que
  no se optimizó nada: se subió el tope del job de 25 a 40 min, porque con
  21,6 min de máximo medido y 25 de tope una corrida lenta habría matado un tag
  bueno. Si vuelve a acercarse al tope, el siguiente paso es cachear el runtime.
- **limpiar-borradores** (solo en cron): desde que la release nace en borrador,
  un tag que no pasa la verificación deja un borrador invisible que nadie borra
  a mano. `scripts/limpiar_borradores.py` lista las releases, se queda con los
  borradores de 7 días o más y los borra (`DIAS_BORRADOR` para cambiarlo,
  `--dry-run` para listar sin tocar). Un borrador no tiene descargas y sus
  assets se reconstruyen desde el tag.
- **verificar-release** (solo en tag, después de `release`): el último tramo
  que nadie comprobaba. Todo lo anterior verifica sobre `dist/`, así que un
  asset subido truncado o un renombrado roto dejaba una release mal publicada
  con la CI en verde. Este job **descarga los assets publicados** y ejecuta
  `scripts/verificar_release.sh release`: juego exacto de assets (17 desde el
  manifiesto: los 12 de siempre más `manifest.json`, su firma, el verificador,
  el comprobador y la clave pública; las releases anteriores se aceptan con
  sus 12 y un aviso, porque no se reescriben), las 3
  firmas y los 3 `SHA256SUMS.*.asc` en una jaula vacía que solo importa
  `packaging/gpg/catflip-release.asc` (exigiendo además la huella de
  `FINGERPRINT`), y `sha256sum -c` de cada `SHA256SUMS.*`. Después arranca el
  `.AppImage` **descargado** con el smoke completo. Si falla, la release se
  queda en **borrador**: nadie ve paquetes rotos.
  También corre con `workflow_dispatch` y el input `tag` (p. ej. `v1.6.0`),
  para verificar una release ya publicada sin cortar una versión: es la forma
  de probar este job y de reverificar una release antigua. Hace checkout del
  tag y le pasa al script `GITHUB_REF`/`GITHUB_REF_NAME` de ese tag, para que
  la comprobación «tag == package.json» siga valiendo. Los scripts de
  verificación se toman del commit actual (`git checkout "$GITHUB_SHA" --
  scripts packaging/gpg`), no del tag: un tag antiguo puede no traerlos —v1.6.0
  no tiene `scripts/verificar_release.sh`— y el verificador que manda es el de
  hoy. `package.json` y los fixtures sí son los del tag.
- **verificar-release** además instala `flatpak` y comprueba la **firma ostree
  del bundle publicado** (`scripts/smoke_package.sh flatpak
  --solo-firma-ostree`): importa el `.flatpak` descargado a un repo temporal con
  una jaula que solo tiene la clave versionada y exige `Good signature`. Antes
  esa firma solo se miraba en el build, no en el fichero que se descarga.
- **verificar-release-windows**: el `.exe` era el único asset publicado que no se
  ejecutaba nunca. Este job lo descarga de la release y corre el smoke completo
  en `windows-latest`, con `GITHUB_REF`/`GITHUB_REF_NAME` del tag verificado.
- **publicar** (solo en tag, después de las dos verificaciones): quita el
  borrador con `gh release edit --draft=false --latest`. Atado a
  `refs/tags/`, así que una verificación manual nunca publica nada.
- **El manifiesto firmado** (`manifest.json` + `.asc`): los `SHA256SUMS.*`
  están repartidos por formato y no dicen nada del conjunto. El manifiesto es
  una sola lista —tag, versión, commit, huella de la clave, cada asset con su
  `sha256` y su tamaño— firmada con la misma clave que los paquetes, y en la
  release viajan también `verificar_release.sh`, `comprobar_manifest.py` y
  `catflip-release.asc`: con eso cualquiera puede repetir la verificación sin
  clonar el repo. Lo genera el job `release` (`scripts/generar_manifest.py`) y
  lo comprueba `scripts/comprobar_manifest.py`, que exige que las hashes
  coincidan, que la lista sea exactamente lo descargado y que la huella sea la
  versionada. Es determinista (usa la fecha del commit, no el reloj), así que un
  rerun del mismo tag produce el mismo fichero.
- **Atestación de build (provenance)**: cada job de build atestigua el paquete
  final con `actions/attest-build-provenance` (`id-token: write` +
  `attestations: write`; no hay clave que guardar) y `verificar-release` lo
  comprueba con `gh attestation verify --signer-workflow packaging.yml`. La
  firma GPG dice «lo firmé yo»; la atestación dice «salió de este repositorio,
  este workflow y este commit», que es lo que distingue un asset sustituido por
  alguien con la clave de uno legítimo. Las releases anteriores a 1.6.2 no
  tienen atestaciones: para reverificarlas, el dispatch acepta
  `exigir_atestacion: false` (y lo dice en el log).

### El aviso del cron, comprobado

El cambio a release en borrador tocaba este workflow entero, así que el cron se
comprobó en vez de suponerse:

- **Corrida programada real** (run 43868690230, `event: schedule`, `main` en
  `1e38412`, que ya trae el borrador): los tres builds en verde, **`cerrar-aviso`
  en `success`**, y `release` / `verificar-release` / `publicar` en **`skipped`**.
  Un cron no crea ni toca ninguna release, y el cierre del aviso sí se ejecuta.
- **Ni tag ni dispatch disparan los avisos**: en el run del tag `v1.6.1` y en el
  `workflow_dispatch` con `tag=v1.6.0`, `avisar-fallo` y `cerrar-aviso` salen
  los dos en **`skipped`** — sus `if` exigen `event_name == 'schedule'`.
- **El issue funciona en sus tres caminos**: simulando el fallo con
  `scripts/avisar_cron.py` contra el repo real (`RESULTADOS=appimage=failure,
  flatpak=success, windows=success`) se **reabrió** el issue cerrado y comentó
  la corrida; una segunda simulación **comentó sin duplicar** (sigue habiendo un
  solo issue con ese título, gracias a la búsqueda por título exacto); y `--ok`
  con resultados verdes **comentó y cerró**. Otro `--ok` ya no hace nada
  («el issue ya estaba cerrado»).

Lo único que no se ha visto en vivo es `avisar-fallo` ejecutándose con un cron
en rojo: haría falta romper un build en una corrida programada. Su `if` es la
misma estructura que la de `cerrar-aviso` (probado hoy en verde) y el script
tiene los tres caminos ejercitados.

### El camino de fallo, probado de verdad

Que una release que no pasa `verificar-release` **se queda en borrador y nunca
se publica** no es una suposición: se comprobó con un tag desechable, un
`v0.0.0-test` que se borró después junto con su release y su rama.

Cómo se provocó: el build ya compara tag y `package.json` (un tag con otra
versión ni llega a `release`: los tres jobs mueren con `tag X ≠ package.json
Y`), así que el fallo tenía que ser del tramo de la release. En una rama que
no se mergeó, `package.json` a `0.0.0-test` para que el tag casara, y una línea
menos en el `gh release upload` (`SHA256SUMS.windows.asc`), que es justo el
«renombrado roto» contra el que existe el juego exacto de assets.

Resultado del run (43920349002):

| Job | Resultado |
| --- | --- |
| AppImage / Flatpak / `.exe` firmados | success |
| Prepara el borrador con los paquetes | success — release con **`draft: true`**, `published_at: null`, **11 assets** |
| Verifica la release | **failure** — `##[error]faltan assets de la release: SHA256SUMS.windows.asc` |
| Publica la release verificada | **skipped** |

Y lo que importa: `releases/latest` siguió siendo la release anterior durante y
después del experimento, y `GET /releases/tags/v0.0.0-test` daba **404**
mientras era borrador (por eso la verificación baja del listado y no de ese
endpoint). Si la verificación falla, no hay release visible que arreglar: se
borra el borrador o se corta otra versión.
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

## Releases publicadas: no se reescriben

Una release publicada es **inmutable para el proyecto**. `release` falla si el
tag ya está publicado, y los assets no se reemplazan aunque tengan un defecto
conocido: quien ya descargó y verificó un fichero tendría otros bytes con la
misma firma y otro `SHA256SUMS`, y el tag dejaría de corresponder a un build de
su propio código (los filtros del `.spec` viven en `main`, no en el tag).

Por eso el criterio es: el defecto se arregla en la **siguiente** versión y la
release afectada se queda con un aviso en sus notas. Caso real: v1.6.0 lleva 17
ficheros de `pyarrow/tests/` dentro del AppImage (el filtro llegó en el PR #92,
después del tag); las firmas y checksums de ese corte son válidos y no se
tocaron.

Si lo que hay que hacer es **retirar** una release mala (un fallo funcional
serio), el procedimiento es despublicar, no reescribir:

```bash
# Deja de estar visible y de contar como latest; los assets y el tag siguen ahí.
gh release edit vX.Y.Z --draft=true
gh release edit vX.Y.Z.anterior --latest
```

Después se comunica en el issue del aviso (o en las notas de la siguiente) y se
corta una versión corregida, que pasa otra vez por borrador → verificar →
publicar. **No se borra la release**: el tag y sus assets son la evidencia de lo
que se publicó, y `vX.Y.Z` sin release es un estado que nadie entiende.

Sólo un problema de seguridad justificaría tocar una release publicada, y
entonces se hace explícito y completo: reconstruir con el mismo código + el
arreglo, re-firmar (`packaging/sign.sh`), regenerar `SHA256SUMS.*` y sus `.asc`,
subir con `gh release upload --clobber`, y dejar en las notas los SHA-256
anteriores y nuevos más la entrada del CHANGELOG. Nada de reemplazos
silenciosos.

## Límites de esta iteración

- **No publicado**: ni Flathub ni AppImageHub (la release de GitHub en tags
  sí se publica sola).
- El `.exe` de Windows se **construye y firma en la CI** (no hay build
  local posible fuera de un host Windows); el auto-update sigue en el
  roadmap Open Core (`premium/README.md`).
