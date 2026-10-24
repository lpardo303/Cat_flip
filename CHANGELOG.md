# 📋 Changelog

Cambios notables de Cat_flip, en orden inverso cronológico.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
versionado semántico ([SemVer](https://semver.org/lang/es/)): la versión vive
en `package.json` y las funciones nuevas van a **Sin publicar** hasta el
siguiente corte.

## [Sin publicar]

### Añadido

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
- Gate de axe ampliado a **13 corridas** (paletas Aurora y Solar con el
  servidor licenciado — la CI levanta con `CATFLIP_PREMIUM_KEY`).

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
