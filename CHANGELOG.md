# 📋 Changelog

Cambios notables de Cat_flip, en orden inverso cronológico.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
versionado semántico ([SemVer](https://semver.org/lang/es/)): la versión vive
en `package.json` y las funciones nuevas van a **Sin publicar** hasta el
siguiente corte.

## [Sin publicar]

### Añadido

- **Conector real de Google BigQuery (Open Core — tercer conector real)**:
  la sección *Destino real* gana la tarjeta **BigQuery**, que carga el
  dataset completo en `dataset.tabla` de Google BigQuery como job de carga
  (`load_table_from_dataframe` + `job.result()`): **Probar conexión**
  (`SELECT 1`) y exportación en modos *Reemplazar tabla* (`WRITE_TRUNCATE`
  con `autodetect` y `CREATE_IF_NEEDED`, así la tabla se crea si no existe)
  o *Añadir filas* (`WRITE_APPEND`, con `get_table` previo para avisar si la
  tabla no existe). Backend en `connectors.py`
  (`clean_bq_params` con identificador de dataset/tabla validado
  `^[A-Za-z_][A-Za-z0-9_]{0,1023}$`, clave de cuenta de servicio opcional
  con sus campos mínimos y `_bq_mask` para la clave privada) + rutas
  `POST /connectors/bigquery/{test,export}` con el mismo gating server-side
  (404 sin licencia; `/premium/status` ahora anuncia
  `connectors: ["postgres", "s3", "bigquery"]`). Sin clave, manda la
  cadena por defecto del SDK (Application Default Credentials). El destino
  viaja como identificador del job, nunca concatenado en SQL. Front: la
  tarjeta BigQuery deja la sección *Destinos (demo)* — que queda con
  Snowflake y Webhook — y pasa a *Destino real* con `real: true`, campos
  proyecto/dataset/tabla/clave JSON/ubicación/modo y envío por
  `bqPayload`/`sendBigQuery`. Drivers **opcionales**:
  `google-cloud-bigquery`, `db-dtypes` y `pyarrow` en
  `requirements-connectors.txt`; sin ellos la app funciona igual y la ruta
  explica cómo instalarlos. 30 tests nuevos con el SDK falso inyectado en
  `sys.modules` (sin red ni credenciales reales) — `connectors.py` al 100 %.

## [1.2.0] — 2026-10-27

### Añadido

- **Conector real de PostgreSQL (Open Core — primer conector real)**: nueva
  sección *Destino real* en el panel derecho (solo con licencia) con modal
  de conexión — **Probar conexión** (`SELECT version()`) y **Exportar a
  tabla** en modos *Reemplazar tabla* (DROP + CREATE con tipos derivados de
  los dtypes de pandas) o *Añadir filas*, en una única transacción. Backend
  en `connectors.py` + rutas `POST /connectors/postgres/{test,export}` con
  gating server-side (404 sin licencia; `/premium/status` pasa a anunciar
  `connectors: ["postgres"]` para que el front ni siquiera pinte la
  sección). Identificadores comillados con `quote_ident`, valores siempre
  parametrizados y contraseña nunca reflejada en respuestas ni errores.
  Driver **opcional**: `pip install -r requirements-connectors.txt`
  (`psycopg` v3); sin él la app funciona igual y la ruta explica cómo
  instalarlo. 40 tests nuevos (`connectors.py` al 100 % de cobertura) y
  `--cov=connectors` añadido al gate de la CI.

- **Conector real de Amazon S3 (Open Core — segundo conector real)**: la
  sección *Destino real* gana la tarjeta **S3**, que sube el dataset
  completo como **CSV** (UTF-8, sin índice) a `s3://bucket/<prefijo>/<ruta>`:
  **Probar conexión** (`head_bucket`) y exportación en modos *Sobrescribir
  objeto* o *Fallar si existe*. Backend en `connectors.py`
  (`clean_s3_params` con bucket validado como DNS, `s3_object_key` sin path
  traversal y `_s3_mask` para credenciales) + rutas
  `POST /connectors/s3/{test,export}` con el mismo gating server-side
  (404 sin licencia; `/premium/status` ahora anuncia
  `connectors: ["postgres", "s3"]`). `endpoint_url` opcional compatible
  MinIO/R2 y credenciales opcionales — vacías no viajan y manda la cadena
  por defecto de AWS (env, perfil o instancia). Driver **opcional**:
  `boto3` en `requirements-connectors.txt`; sin él la app funciona igual y
  la ruta explica cómo instalarlo. 27 tests nuevos con el SDK falso
  inyectado en `sys.modules` (sin red ni credenciales reales).

### Arreglados

- **Nulos de solo espacios normalizados al cargar** (Bug 4 al cargar): una
  celda `"   "` sobrevivía al `/upload` y contaba como dato válido, así que
  `/stats` subreportaba nulos y la barra de calidad salía ~1 punto inflada.
  `read_table()` aplica ahora `normalize_read_nulls()` en los tres caminos
  de carga (upload, frame derecho y CLI) y la expresión de carga encadena
  `.replace(r'(?i)^\s*(?:nan|none|null)?\s*$', float('nan'), regex=True)`,
  de modo que el código del panel Python y el script exportado reproducen
  exactamente el df en memoria.

- **Tintes de la pastilla % Calidad derivados de los tokens**: las variantes
  `.q-green/.q-amber/.q-red` de `.metric-quality` llevaban `rgba()`
  hardcodeados de la paleta anterior, así que su relleno y borde no seguían
  al tema (claro/oscuro/Aurora/Solar) ni al re-tuneo de
  `--green/--yellow/--red`. Ahora se derivan con
  `color-mix(in srgb, var(--token) …, transparent)` con los mismos
  porcentajes de antes. Gate de axe en verde: 15 corridas, 0 violaciones.

## [1.1.0] — 2026-10-25

### Añadido

- **Packaging firmado (AppImage + Flatpak)**: carpeta `packaging/` con builds
  locales reproducibles del core MIT. `packaging/appimage/build.sh` produce
  `dist/appimage/CatFlip-<ver>-x86_64.AppImage` y
  `packaging/flatpak/build.sh` un repo ostree + bundle
  `dist/flatpak/CatFlip-<ver>.flatpak`, ambos con firma GPG detached y
  `SHA256SUMS` firmados. Comparten el mismo binario onedir de PyInstaller
  (`packaging/appimage/catflip.spec` + `entry.py`), el Flatpak usa el app id
  `io.github.lpardo303.CatFlip` sobre FDO 26.08 y una clave de firma dedicada
  (pública versionada en `packaging/gpg/`, privada solo en `~/.gnupg`).
  Verificado: AppImage y flatpak arrancan y sirven `/` 200, la instalación
  desde un remote con `gpg-verify=1` funciona y un `summary.idx` alterado se
  rechaza con `BAD signature`. Guía completa en `packaging/README.md`.
- **CI de packaging**: `.github/workflows/packaging.yml` construye y firma el
  AppImage y el Flatpak en tags `v*` (y `workflow_dispatch`), verifica las
  firmas con `gpg --verify` + `sha256sum -c`, sube artifacts y adjunta los
  artefactos a la release con `gh`. Requiere el secreto `GPG_SIGNING_KEY`
  (clave privada armored; sin él los jobs fallan de forma explícita). Los
  scripts ganan `FLATPAK_BUILDER_CMD` (flatpak-builder del host en CI) y
  detección de Python cuando no hay `.venv`.

- **Nuevo front «Tech Labs»**: rediseño completo de la interfaz (tokens,
  componentes, grid y cabecera) con la triada **Plus Jakarta Sans /
  Space Mono**, grid técnico de fondo con cruces de registro, logo de
  Cat_flip en caja de acento, botones y badges con sombra sólida y un
  **canvas isométrico animado** teñido con el acento vigente (se dibuja
  estático bajo `prefers-reduced-motion`). La lógica ETL, los modales y
  el comportamiento de los temas no cambian.
- **Catálogo de color de énfasis**: 6 presets + color personalizado
  dentro del panel de tema, como **capa ortogonal** a Claro/Oscuro/
  Sistema y a los premium (Aurora/Solar). `setAccent()` recalcula
  `--accent`, `--accent-hover`, `--accent-contrast`, `--accent-text`
  (derivado con ≥5.2:1 sobre las superficies del tema), `--accent-subtle`
  y `--accent-glow`, y repinta el canvas; persiste entre sesiones
  (`catflip-accent`). El gate de axe verifica el panel con los 6
  swatches y el marcado.

### Cambiado

- **Teal estructural retirado**: cabeceras del data grid, títulos del
  diagnóstico, schema, linaje, badges del ribbon, chips de tipo y toasts
  `info` pasan a los neutros del prototipo (con `--border-strong` donde
  hacía falta jerarquía) y a tokens de acento en los puntos de énfasis.
  El teal queda **solo como color de datos**: heatmap de correlaciones
  positivas, barras de distribución y peso del benchmark. Los badges
  `INT`/`FLOAT` ahora son neutros con borde fuerte (riesgo de colisión
  con `DATE` si se pintaran con el acento naranja).
- **Vistas limpias al iniciar**: `loadStats`, `loadCorrelations`,
  `loadSchema` y `loadLineage` no consultan al servidor cuando la sesión
  del cliente no tiene dataset, así una carga fresca no pinta datos de
  sesiones anteriores (antes la pestaña Datos estaba vacía pero
  Diagnóstico/Schema/Linaje mostraban el último dataset del backend).
- **Footer en inglés**: «Invítame un café» → «Buy me a coffee».
- **El gate de axe cambia de tema como el usuario**: en vez de un
  `setAttribute('data-theme')` directo (que pintaba el CSS nuevo pero
  dejaba `--accent-text`, un token derivado por JS, calculado contra la
  superficie del tema anterior) ahora hace `themeMode + applyTheme()`,
  igual que `setThemeMode()`. Así se mide el estado real de la app y no
  uno que solo existe en el test.
- **Toasts con fondo opaco** (`--bg-input` + borde de color): antes su
  fondo translúcido se mezclaba con el scrim del modal y hundía el
  contraste del texto por debajo de AA.
- **El gate de axe mide en reposo**: espera a que terminen las
  transiciones/animaciones finitas de cada superficie antes de evaluar,
  así el contraste se comprueba sobre los colores finales y no sobre
  fotogramas interpolados del cambio de tema.
- **`<input type="color">` fuera del `role="menu"`**: el selector
  personalizado vive en `<body>` y lo abre desde el panel un
  `menuitemradio` (un `menu` solo admite `menuitem*`), lo que deja
  `aria-required-children` limpio en axe.

- **Open Core — paquete `premium/`** con gating server-side (env var
  `CATFLIP_PREMIUM_KEY` o fichero `premium.key`): endpoints
  `/premium/status` y `/premium/themes/<id>.css` (lista vacía y 404 sin
  licencia, id validado contra el manifiesto) y los primeros features
  premium — **temas Aurora y Solar**: el botón de tema amplía su ciclo a
  Claro → Oscuro → Automático → Aurora → Solar, con CSS servido solo
  desde el servidor.
- **Licencia dual**: `LICENSE-PREMIUM.txt` (borrador de licencia
  comercial para uso empresarial embebido) y nota al pie de `LICENSE`;
  el texto MIT queda intacto.
- Gate de axe ampliado a **15 corridas** (paletas Aurora y Solar con el
  servidor licenciado — la CI levanta con `CATFLIP_PREMIUM_KEY` — y el
  panel del selector de tema abierto en claro y oscuro; antes 13).
- **Selector de tema con vista previa**: el botón de tema deja de ciclar y
  abre un panel con una opción por tema — cada una con una mini-vista
  previa real de su paleta (fondo, superficie, texto y acento) — agrupado
  en **Claro / Oscuro / Sistema**. El grupo de cada tema premium lo decide
  el servidor con el nuevo campo `mode` de `/premium/status`. Accesibilidad:
  `aria-haspopup`/`aria-expanded` en el botón, `menuitemradio` con
  `aria-checked` en el activo, flechas/Home/End para recorrer, Escape para
  cerrar y devolver el foco, clic-fuera para descartar. La etiqueta del
  botón pasa a mostrar el tema vigente en lugar del siguiente.

## [1.0.0] - 2026-10-23

Primera versión completa: ETL local con recetas reproducibles, CLI,
diagnóstico y CI de accesibilidad.

### Añadido

- **24 operaciones ETL**: estructural (pivot/unpivot, merge, group by,
  filtrado, orden), texto (trim, change case, concat, regex mask), tipos
  (cambio de tipo, detección inteligente de fechas, auto-mapeo ≥90%),
  limpieza (nulos, duplicados, outliers Z-Score/IQR, sampling con
  semilla), columna calculada con sandbox `eval`, PII (escaneo +
  enmascaramiento) y validación de esquema (no-nulo, único, regex, rango).
- **Recetas reproducibles**: guardar/cargar `.catrecipe`, receta como
  script `.py` portable con argumentos, pipeline completo `.py`, receta
  JSON, propuesta automática *Receta desde CSV* y **ExecutePipelineModal**
  con dry-run, barra de progreso y aplicación atómica al 100%.
- **Recorrido del pipeline**: deshacer/rehacer paso a paso
  (`Ctrl+Z`/`Ctrl+Shift+Z`), **diff por paso** con muestra de celdas
  cambiadas, **benchmark por paso** (tiempo en servidor con el cuello de
  botella resaltado) y grafo de linaje.
- **Diagnóstico**: perfilado por columna, heatmap de correlaciones de
  Pearson con `color-mix()` sobre tokens, barra de calidad de datos y
  avisos al cargar (fechas, PII, encoding y separador autodetectados).
- **Exportación**: CSV, Excel XLSX, Parquet, JSON Records y SQL
  DDL + INSERT portables; destinos *demo* (BigQuery, Snowflake, Webhook)
  simulados sin ninguna petición de red.
- **Modo CLI**: `python cli.py run receta.json --input datos.csv
  --output limpio.csv` con autodetección de archivo y exit codes para CI.
- **UI**: diseño *Kinetic Query Minimal* con paneles colapsables, data
  grid virtualizado (5.000 filas), modo claro/oscuro persistente y **modo
  Automático por `prefers-color-scheme`** con reacción en vivo, y footer
  de apoyo (Ko-fi / GitHub Sponsors).
- **Calidad**: CI con gate de cobertura (93%), `node --check` de los
  módulos JS y **gate de axe** (WCAG 2.0 A/AA, 11 corridas) que falla el
  job ante cualquier violación o fallo de sus asserts.
- **Docs**: manual de usuario, README, esta guía de contribuciones
  (`CONTRIBUTING.md`) y changelog.

### Cambios

- El tema por defecto ahora es **Automático** (sigue el sistema); la
  elección manual de claro/oscuro sigue persistiéndose entre sesiones y
  los valores guardados por versiones anteriores se respetan.

### Arreglados

- `applyRecipeResult` reemplazaba la lista de pasos en vez de
  concatenarla: con una receta aplicada sobre un pipeline no vacío, las
  tarjetas y los índices del diff quedaban desfasados del linaje.
- `askFilename()` usaba `prompt()`, inexistente en las webviews del
  escritorio — sustituido por el diálogo nativo de archivo.
- Auto-mapeo de fechas: `dayfirst` mal inferido para días ISO > 12.

[Sin publicar]: https://github.com/lpardo303/Cat_flip/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/lpardo303/Cat_flip/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/lpardo303/Cat_flip/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/lpardo303/Cat_flip/releases/tag/v1.0.0
