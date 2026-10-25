# 📦 Packaging firmado de Cat_flip (AppImage + Flatpak)

Builds **locales y reproducibles** del core MIT en dos formatos, ambos firmados
con GPG y con `SHA256SUMS` firmados. Nada se publica desde aquí: los artefactos
quedan en `dist/` (ignorado por git).

| Formato | Script | Artefactos |
|---|---|---|
| AppImage | `packaging/appimage/build.sh` | `dist/appimage/CatFlip-<ver>-x86_64.AppImage` + `.asc` + `SHA256SUMS` + `SHA256SUMS.asc` |
| Flatpak | `packaging/flatpak/build.sh` | `dist/flatpak/repo/` (ostree firmado) + `dist/flatpak/CatFlip-<ver>.flatpak` + `.asc` + `SHA256SUMS(.asc)` |

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
  la pública.

## Build

```bash
packaging/appimage/build.sh                  # congelado + AppImage + firma
packaging/flatpak/build.sh                   # congelado + flatpak + firma
SKIP_FROZEN=1 packaging/appimage/build.sh    # reutiliza dist/CatFlip ya construido
SKIP_FROZEN=1 packaging/flatpak/build.sh
```

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

`.github/workflows/packaging.yml` construye y firma ambos paquetes en cada tag
`v*` y bajo demanda con `workflow_dispatch`:

- **appimage** / **flatpak**: pip + `packaging/*/build.sh` + verificación
  (`gpg --verify` + `sha256sum -c`) y subida de artifacts. El job de flatpak
  instala `flatpak-builder` con apt y el runtime 26.08 en `--user`, y usa
  `FLATPAK_BUILDER_CMD=flatpak-builder` (sin el sandbox de
  `org.flatpak.Builder` no existe el problema de la instalación de sistema).
- **release** (solo en tag): crea la release si no existe y adjunta los
  artefactos con `gh release upload`.

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
- Solo Linux: el `.exe` firmado de Windows y el auto-update siguen en el
  roadmap Open Core (`premium/README.md`).
