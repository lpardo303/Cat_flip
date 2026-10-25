# 📋 Changelog

Cambios notables de Cat_flip, en orden inverso cronológico.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
versionado semántico ([SemVer](https://semver.org/lang/es/)): la versión vive
en `package.json` y las funciones nuevas van a **Sin publicar** hasta el
siguiente corte.

## [Sin publicar]

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

[Sin publicar]: https://github.com/lpardo303/Cat_flip/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lpardo303/Cat_flip/releases/tag/v1.0.0
