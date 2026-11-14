# 📋 Changelog

Cambios notables de Cat_flip, en orden inverso cronológico.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
versionado semántico ([SemVer](https://semver.org/lang/es/)): la versión vive
en `package.json` y las funciones nuevas van a **Sin publicar** hasta el
siguiente corte.

## [Sin publicar]

### Añadido

- **El job de bundles se salta en PRs que no tocan el paquete.** `linux-bundles`
  cuesta ~5 min, así que un PR de solo documentación no lo paga: el job
  `cambios` ejecuta `scripts/toca_bundle.sh`, que compara el diff con git y
  responde «no construir» únicamente si **todo** lo cambiado es documentación,
  `tests/` (salvo `tests/fixtures/`, que son la entrada del smoke) o
  metadatos. Ante cualquier duda —base desconocida, diff vacío, git que
  falla— responde «construir»: el filtro puede gastar de más, nunca de menos.
- **`windows-exe` usa el smoke compartido.** Su copia del arranque, la espera,
  el `taskkill` y la subida del log dejan paso a
  `scripts/smoke_package.sh windows --sin-version-check`, el mismo script que
  usan los bundles de Linux y el release; ahora los tres se prueban con una
  sola implementación.
- **El AppImage y el Flatpak se construyen y se prueban en cada PR.** Hasta
  ahora los bundles de Linux solo se ejecutaban en el tag: una regresión de
  empaquetado (`formats.py` sin `hiddenimport`, `python_calamine` fuera,
  plantillas viejas) pasaba `main` y aparecía al publicar. El job
  `linux-bundles` los construye sin firmar en un solo runner —el binario
  congelado se hace una vez y el Flatpak lo reutiliza con `SKIP_FROZEN=1`— y
  les pasa el mismo `scripts/smoke_package.sh` del release, con
  `--sin-version-check` (ese check espera en backoff contra api.github.com y
  en PRs solo aporta intermitencia; el tag lo sigue comprobando). El smoke
  compartido ahora también **rechaza arrancar si el puerto 5050 ya está
  ocupado**, porque dos smokes en el mismo job probarían el proceso
  equivocado y darían un falso verde.
- **El release prueba los tres paquetes antes de firmarlos, con el mismo
  smoke.** Cada job de `packaging.yml` firmaba y verificaba el artefacto antes
  de ejecutarlo, y solo el `.exe` comprobaba que el paquete **leyera** un
  archivo: un AppImage o un Flatpak sin `python_calamine` arrancaban, servían
  `/` y fallaban al subir un `.xls`. Ahora los tres siguen el mismo orden
  —construir → `scripts/smoke_package.sh` → `packaging/sign.sh` → verificar—
  con una sola implementación del smoke (3 copias de ~50 líneas menos) y una
  sola de la firma (estaba copiada en los tres `build.sh`). `packaging/sign.sh
  --verificar` comprueba la firma y los checksums del artefacto exacto, que
  evita el falso «Firma INCORRECTA» que daba `gpg --verify *.asc *.bin` con
  residuos de otra versión en `dist/`. El script compartido se llama ahora
  `scripts/smoke_lecturas.py` (antes `smoke_exe.py`) y añade `/premium/status`
  para los tres formatos.
- **CI: el `.exe` de Windows se construye y se prueba en cada PR.** Era el
  único artefacto sin verificar: el job `windows` de `packaging.yml` solo
  corre en tags, así que una regresión de empaquetado (`formats.py`,
  `python_calamine`, plantillas) llegaba a `main` y estallaba al publicar.
  El nuevo job `windows-exe` construye el `.exe` con el spec real —sin
  firmar: la clave GPG es de publicación, vía `SKIP_SIGN=1`—, lo arranca sin
  navegador y le sube los fixtures reales con `scripts/smoke_lecturas.py`: los
  ocho formatos de entrada y el selector de hoja. El mismo script se ejecuta
  ahora en el job de release, que antes solo comprobaba `/` y
  `premium/status` — es decir, que el `.exe` arrancara, no que leyera un
  archivo.
- **Entrada `.ods` y `.parquet`**: la app lee ahora hojas de cálculo
  OpenDocument y columnas Parquet, además de CSV, TSV, XLSX y XLS. `.ods`
  usa `python-calamine` (ya empaquetado para `.xls`): pandas 3 lo leería
  con `odf`/`odfpy`, una dependencia que no viaja en los bundles, así que
  el motor va fijo por extensión — y el script exportado lo incluye
  (`pd.read_excel('x.ods', sheet_name=0, engine='calamine')`) para que se
  reproduzca sin instalar nada más. `.parquet` se lee con `pyarrow` (que
  ya estaba, por la exportación) conservando los tipos, sin selector de
  hoja: `/get_sheets` responde `[]`. Funciona también en el batch merge,
  en el cruce y en el CLI. Tests con fixtures reales —un `.ods` generado
  por LibreOffice desde un `.xlsx` (para que los números sigan siendo
  números) y un `.parquet` de pyarrow—, incluida la reproducción del
  código generado para cada formato.

- **Entrada `.json`**: lee JSON plano y anidado. La orientación se detecta
  —array de registros, `{"col": [valores]}`, `{"fila": {...}}`, array de
  filas y NDJSON de un objeto por línea— porque pandas no siempre respeta el
  `orient` que se le pasa: un objeto indexado se leía transpuesto. La
  orientación detectada va explícita en el código exportado, así que el
  script reproduce la carga. Los objetos anidados se aplanan a columnas con
  punto (`Contacto.Ciudad`) sin multiplicar filas, y las listas se conservan
  como celda. Los errores explican qué pasa: JSON inválido con línea y
  columna, raíz escalar, un registro suelto sin array, JSON vacío y
  codificación que no sea UTF-8. Fixtures de esquema plano y anidado.
- **Entrada `.xlsb` (Excel binario)**: se lee con `calamine`, el mismo
  motor que ya viaja para `.xls`/`.ods` (pandas usaría `pyxlsb`, que no
  se empaqueta), y el script exportado fija `engine='calamine'` por la
  misma razón. Antes de anunciarlo se comprobó contra un fichero real:
  lista las hojas incluida la oculta, conserva números y texto. El fixture
  es un `.xlsb` auténtico del corpus de tests de calamine (proyecto MIT),
  porque ningún conversor local escribe el formato —LibreOffice no lo
  exporta y `pyxlsb` solo lee— así que no se puede generar como el `.ods`.

### Cambiado

- **La lectura de `.xlsx` pasa a `calamine`** (antes `openpyxl`), después de
  medirlo. Los mismos cuadernos leídos por ambos motores dan las mismas
  columnas, dtypes y valores en todo lo probado —fechas con y sin hora,
  booleanos, enteros por encima de 2^53, errores de fórmula, celdas
  combinadas, encabezados vacíos/duplicados/numéricos, acentos, emoji,
  espacios en los extremos, tabuladores y saltos de línea—; la única
  diferencia bruta era una celda con un solo espacio, que la normalización
  de nulos ya convertía en `null`. A cambio: **7× más rápido** (0,8 s frente
  a 6,0 s en 50.000×8, medido también en la app instalada) y lee los
  cuadernos con hoja de gráfico, que hacían fallar a openpyxl 3.1.5 con
  `AttributeError`. Coste asumido: ~25 % más de pico de memoria al leer.
  `excel_engine()` queda como único interruptor y el código exportado fija
  `engine='calamine'`, de modo que el script sigue reproduciendo la carga
  aunque cambie el motor por defecto de pandas. `openpyxl` sigue en las
  dependencias: es quien **escribe** el `.xlsx` (exportación y CLI), y hay un
  test de ida y vuelta entre ambos.
- **La lista de formatos vive en un solo sitio (`formats.py`)**: estaba
  escrita a mano en nueve lugares (tres `accept=` del HTML, dos
  validaciones del front y las tuplas del backend y del CLI), que es lo
  que ya había dejado TSV fuera del estado vacío y `.xls` anunciado sin
  poder leerse. Ahora backend, CLI, plantilla y JS derivan de ese módulo:
  los `accept=` y los textos se renderizan desde Jinja y el front recibe
  `window.CATFLIP_FORMATS` en vez de repetir extensiones. Los tests
  anti-deriva pasan a comprobar el **HTML renderizado** (y que los módulos
  JS no vuelvan a escribir la lista), así que añadir un formato es tocar
  un fichero y no siete.

### Solucionado

- **`.xls` (Excel 97-2003) no se podía leer**: la extensión se anunciaba
  en el selector, el dropzone, el CLI y los mensajes de error, pero
  pandas 3 ya no incluye motor para BIFF y, sin él, subir un `.xls` real
  devolvía 500 con `Import python-calamine failed` — también en
  `/get_sheets`. Ahora `python-calamine` viaja en `requirements.txt` y
  como `hiddenimport` en los dos specs de PyInstaller (pandas lo importa
  en diferido, así que el análisis estático no lo ve y el Flatpak, el
  AppImage y el `.exe` habrían seguido fallando). Además el motor se fija
  explícitamente —`openpyxl` para `.xlsx`, `calamine` para `.xls`— en
  `read_table` y `/get_sheets`, para no depender del motor por defecto de
  pandas, que ya avisa de que va a cambiar. Tests nuevos con un `.xls`
  BIFF real (fixture generado con LibreOffice): `/upload`, `/get_sheets`
  y CLI.
- **Faltaba TSV en el estado vacío**: la bienvenida decía «Carga un
  archivo CSV, XLSX o XLS» mientras el resto de la interfaz, el CLI y los
  mensajes 400 sí admiten `.tsv` (detectando tabulador). Corregido, y con
  tests anti-deriva que leen `templates/index.html` y exigen que el estado
  vacío, el hint del dropzone y el `accept=` nombren exactamente las
  extensiones que acepta el backend.
- **El paquete abre el navegador al arrancar (Flatpak, AppImage y
  `.exe`)**: el binario congelado solo levantaba Flask, así que abrir
  Cat_flip desde el menú daba la sensación de que «no pasaba nada» — la
  URL `127.0.0.1:5050` había que escribirla a mano, porque los
  `launch.sh`/`launch.fish`/`launch.bat` del repo son lanzadores de
  desarrollo y no viajan dentro del paquete. Ahora un hilo espera a que
  el puerto responda (hasta 30 s: Flask importa pandas antes de escuchar)
  y abre la URL con el navegador por defecto: `xdg-open` en Linux —dentro
  del sandbox del Flatpak resuelve por el portal OpenURI, sin permisos
  extra—, `gio open` como alternativa y `flatpak-spawn --host` como
  último recurso. Es un hilo *daemon* que nunca levanta excepciones: si
  no hay navegador, o falla, el servidor arranca igual. Se desactiva con
  `CATFLIP_NO_BROWSER=1` y no se intenta en CI ni sin sesión gráfica, así
  que los smokes del packaging siguen ejecutando el binario a ciegas sin
  cambios en el workflow.

## [1.6.0] — 2026-11-04

### Añadido

- **Multi-File Batch Merge — consolidación de N archivos**: el selector de
  *Fuente de datos* acepta arrastrar **varios** archivos a la vez y añade
  el botón «Fusionar varios archivos…», que abre un modal con la **matriz
  de encabezados por archivo** (coincidencias, faltantes y totales) antes
  de consolidar. Modo *Dinámico*: unión outer de todos los encabezados —
  lo que falte en un archivo queda vacío y **nada se pierde** — con bloque
  estructural fijo opcional y resto por aparición (default) o alfabético;
  modo *Plantilla*: esquema maestro exacto (orden + conjunto), descartando
  lo que sobre y rellenando vacío lo que falte, con el resumen de
  diferencias en el propio modal. Nuevos endpoints `/batch_preview` (solo
  lectura, la matriz) y `/batch_merge` (reset de estado idéntico a
  `/upload`); el código generado (N lecturas + `concat` outer + `reindex`)
  reproduce la consolidación completa en el script exportado. Modal
  añadido a las superficies del gate de axe (17 corridas, 0 violaciones).
- **`change_type` masivo con catálogo extendido (op 15)**: el modal de
  *Tipo dato* acepta selección múltiple de columnas (checkboxes con
  *Seleccionar todas*) y amplía los tipos de destino a las grafías
  pandas — Texto (`str`/`string`), Entero nullable (`int`/`Int64`),
  Decimal (`float`, ahora siempre `float64`), Fecha y hora
  (`datetime`/`datetime64`), Booleano nullable (`bool`/`boolean`) y
  Categoría (`category`) — aplicando el mismo tipo a todas las columnas
  marcadas en **un solo paso** de receta. Los booleanos aceptan
  `true`/`t`/`yes`/`y`/`1` y `false`/`f`/`no`/`n`/`0` sin distinción de
  mayúsculas y lo no reconocido queda nulo (`<NA>`); `category` no
  convierte en categoría los marcadores de nulo previos de las columnas
  de texto (regla Bug 4). El backend valida el catálogo (dtype
  desconocido → 500 con las 10 grafías en el mensaje; antes caía al
  fallback `str` sin avisar) y acepta `column` (forma legada, intacta)
  o `columns` (lista), exactamente uno.
- **Operación Reordenar Columnas (`reorder_columns`, op #25)**: nuevo modal
  con dos modos — *Bloque inicial + resto alfabético* (fija las columnas
  marcadas al principio conservando su orden actual y ordena el resto A→Z
  ignorando mayúsculas, empates estables; sin marcadas = todo el dataset
  alfabético) y *Mover una columna* (al inicio, al final, antes o después
  de otra columna, con exactamente un destino). Botón «Reordenar» en la
  sección *Estructura* del panel e ítem en el menú contextual de columna
  (abre el modo *Mover* con esa columna preseleccionada). El código
  generado lista el orden final explícito, así que receta y script
  exportado reproducen el mismo orden. Registro `OPS` a 25 operaciones.

### Cambiado

- **Data Grid optimizado para datasets anchos**: el grid ventanea también
  en **anchura** — solo pinta las columnas visibles + 3 de búfer por lado
  (colgroup con todos los anchos y `table-layout: fixed`), de modo que un
  archivo de **78 columnas × 515 filas** navega sin tirones: el scroll
  baja de ~185 ms por frame (≈5 fps) a **~33 ms vertical / ~51 ms
  horizontal**, el render en caliente de 283 ms a **33 ms** y el DOM de
  ~40 000 celdas a **~300**. La cabecera y el colgroup solo se repintan
  cuando cambia la ventana (firmas de render), el buscador aplica
  **debounce de 120 ms** y un **`ResizeObserver`** sobre el viewport
  recalcula la ventana al colapsar/expandir paneles o cambiar de pestaña
  (antes `window.resize`, que no se disparaba en esos casos). El coste
  único de calibrar los anchos solo se paga en la primera carga de cada
  esquema; medido en navegador con el fichero real
  («Query Mayo 2026 - I.xlsx», hoja MAYO 2026-I).
- **Carga y scroll sin tirones: calibración muestreada + histeresis de
  columnas**: la calibración ya no renderiza el dataset completo en auto
  layout — muestrea ~128 filas con stride repartidas por todo el dataset
  — lo que baja el primer pintado de **~2089 ms a ~476 ms** y la
  recalibración de web fonts de **~1925 ms a ~530 ms** (cero bloqueos de
  >0.5 s; subida → grid listo: **2695 → 832 ms**). Los anchos difieren
  como máximo en **1 columna / ≤19 px** de los 78 del fichero real (el
  recorte con ellipsis + tooltip ya documentado cubre ese caso).
  Además `updateVirtualCols` aplica **histeresis**: mientras la franja
  visible siga DENTRO de la ventana ya pintada no re-ventanea, así que el
  scroll horizontal reconstruye el tbody **~1 de cada 3 cruces** en vez de
  en cada una: **39 → 7 reconstrucciones / 3 s**, frame medio
  **31 → 19.8 ms** y p95 **51.9 → 35 ms** (medido en navegador con el
  fichero real).
- **La malla matemática animada se muda a la franja de la cabecera**: el
  `#math-grid-bg` vive ahora dentro de `<header>` (`position: absolute;
  z-index: -1`), se redimensiona al rect del ribbon, el ratón se mapea a
  sus coordenadas y la malla queda recortada a la franja (52 px de fila 1
  transparente sobre el glass; la fila 2 sigue opaca); las alfas suben
  (0.22 → 0.34 en oscuro, 0.16 → 0.26 en claro) para que la franja se
  lea como el antiguo fondo a viewport. Se conservan el tinte `--accent`,
  `aria-hidden`, el pintado estático con `prefers-reduced-motion` y el
  repintado por tema/énfasis — verificado en los 4 temas y en
  reduced-motion.

### Arreglado

- **Las celdas «null» ya no asoman por encima de la cabecera sticky del
  grid**: `thead th` era `position: sticky` con `z-index: auto` y un
  `backdrop-filter` que no se veía (el `--base2` es opaco en los 4
  temas); en Chromium el contenido de las filas (el «null» de
  `.cell-null`, con `opacity` que crea capa de composición) pasaba por
  encima de la cabecera al hacer scroll. La cabecera lleva ahora
  `z-index: 10` y se retira el `backdrop-filter` inservicial; reproducido
  y verificado con `elementFromPoint` sobre la franja de la cabecera con
  el fichero real (antes devolvía `SPAN.cell-null`, después el `th`).

## [1.5.1] — 2026-10-31

### Añadido

- **Smoke E2E del AppImage en la CI**: el job de AppImage ejecuta el
  bundle recién construido y falla si `/` no responde, si
  `/version/check` no da `checked:true` (regresión de CAs) o si
  `current` no coincide con `package.json` — antes se construía y
  firmaba sin ejecutarlo nunca. En un tag además se comprueba que el
  tag y `package.json` llevan la misma versión.
- **Smoke E2E del Flatpak en la CI**: el job de Flatpak instala el bundle
  recién construido (después de verificar su firma), lo arranca con
  `flatpak run` y falla si `/` no responde, si `/version/check` no da
  `checked:true` dentro del sandbox (CAs o red del sandbox) o si el
  `current` empaquetado no coincide con la versión del tag — antes se
  construía y firmaba sin instalarlo nunca. Usa el mismo backoff contra
  el rate limit que el `.exe` (305 s por la caché de 300 s, estirada al
  reset) y desinstala el bundle siempre al terminar, también si falla.
- **Validación de workflows en la CI**: job nuevo de `actionlint` (con
  shellcheck en PATH, que amplía la revisión de los `run:` a bash) en
  `ci.yml`, que revisa los tres workflows en cada PR y empuje — hasta
  ahora `actionlint`/`shellcheck` solo corrían a mano en local, así que
  una regresión en el YAML pasaba inadvertida hasta el siguiente dispatch
  de packaging.
- **Shellcheck de `scripts/` en la CI**: el job `actionlint` pasa ahora
  `shellcheck` por los scripts del repo (`scripts/*.sh`: `smoke.sh` y
  `smoke_version_check.sh`) además de por los `run:` de los workflows —
  antes solo se ejecutaban a mano en local. El paso nuevo destapó 2 avisos
  `SC2329` («función nunca invocada») que el shellcheck 0.11.0 del runner
  lanza sobre `cleanup` y `s3_ready`: falsos positivos de invocación
  indirecta (vía `trap` y como comando pasado a `wait_for`), ya cubiertos
  por las directivas `disable=SC2317` existentes — se amplían a
  `SC2317,SC2329`, válidas en 0.10.0 local y en 0.11.0. Para que el
  resultado no dependa de la versión que traiga la imagen del runner, el
  job **fija shellcheck 0.11.0 con checksum** (`sha256sum -c`), igual que
  ya hacía con actionlint, e imprime la versión en el log como constancia.
- **Aviso de versiones fijadas desactualizadas**: workflow programado
  (`tool-versions.yml`, semanal + manual) que lee los pins de actionlint
  y shellcheck **directamente de `ci.yml`** (un solo sitio que actualizar)
  y los compara con la última release de cada proyecto en GitHub; si hay
  una nueva, abre un issue con la versión y el recordatorio de recalcular
  el `sha256sum`, sin duplicar si ya hay uno abierto. Si un pin
  desapareciera, el job falla con `::error::` en lugar de mirar al lado.
- **Dependabot para actions y pip**: `.github/dependabot.yml` habilita
  version updates semanales (lunes 06:00 UTC) para el ecosistema
  `github-actions` (los `use:` de los tres workflows) y `pip`
  (`requirements*.txt` de la raíz), **agrupados**: un PR por ecosistema
  como máximo a la semana en vez de uno por dependencia. Los binarios
  fijados con checksum (actionlint/shellcheck) no son actions y siguen
  siendo cosa del workflow de avisos.
- **Documentación del bloqueo de autoaprobación** (`CONTRIBUTING.md`):
  sección 🔒 nueva con las reglas reales de protección de `main`, por qué
  un PR escrito por el propio mantenedor no puede reunir la review que
  la regla exige (GitHub prohíbe autoaprobar, y el repo tiene una sola
  persona con escritura, mientras los PR de Dependabot sí fluyen) y el
  ritual ya verificado de relajar → mergear → restaurar, con el payload
  canónico de restauración y su verificación campo a campo contra un
  snapshot previo.
- **Ignoras en Dependabot para dependencias rotas** (`.github/dependabot.yml`):
  bloquea `python-dateutil >=3.0.0` (google-cloud-bigquery 3.46.2 exige
  dateutil <3 → ResolutionImpossible en los jobs de smokes) y
  `charset-normalizer >=3.4.5` — desde la pin 3.4.4 verificada — porque
  la regresión de detección no es solo de la 3.5.x: 3.5.2 **y 3.4.9** dan
  «mac_latin2» para el CSV cp1252 de la suite y rompen los 3 tests de
  `tests/test_encoding.py` (verificado en la CI del PR de Dependabot).
  Sin estas reglas, la ronda semanal reabría cada lunes el mismo PR roto.

### Cambiado

- **El backoff de `/version/check` sale del workflow a
  `scripts/smoke_version_check.sh`**: el mismo bloque de ~40 líneas estaba
  triplicado en los tres smokes (AppImage, `.exe` y Flatpak). El script
  recibe la versión esperada como argumento opcional y **los tres la pasan
  ya**: el smoke del `.exe` pasa a exigir que el `current` empaquetado sea
  el del tag (antes solo `checked:true`) y gana su línea `✓` final como los
  otros dos. Idéntico backoff para los tres (base de 305 s, estirada al
  reset, tope de 10 min) y volcado del log del binario al fallar. El paso de
  Windows gana de paso un `trap` que mata el `.exe` en todos los caminos de
  salida, también si el check falla.

- **Los tres smokes exigen exactamente un bundle en `dist/`**: la
  selección era `ls … | head -1`, que con un glob sin match se quedaba
  vacío (fallas después con un error confuso) y con varios matches se
  tragaba en silencio el primero — en local llegó a coger el AppImage
  1.0.0 antiguo en vez del 1.5.0. Ahora cada paso lista el glob con
  `nullglob` y falla de inmediato con `::error::` diciendo cuántos
  bundles hay y cuáles, si no hay exactamente uno.

### Arreglados

- **El smoke del `.exe` ya no lo tumba el rate limit de api.github.com**:
  el reintento de `/version/check` dormía 3 s, pero el servidor cachea  el fallo 300 s (`_RELEASE_TTL_ERR`), así que los tres intentos releían la
  misma caché y jamás volvían a consultar a GitHub — tres `checked:false`
  falsos hundían el job. El backoff arranca ahora en 305 s y crece por
  intento, y si `/rate_limit` reporta la ventana agotada se estira hasta su
  reset (+15 s, máx. 10 min por intento) antes de fallar, distinguiendo
  en el mensaje un rate limit sostenido de un problema real de CAs.
- **El smoke E2E del AppImage también tolera el rate limit**: el reintento
  de `/version/check` dormía 3 s sin volver a consultar a GitHub (la
  caché de 300 s devolvía el mismo fallo). Ahora usa el mismo backoff que
  el `.exe` — espera base de 305 s, estirada al reset del rate limit con
  tope de 10 min — y separa los fallos: `checked:true` con un `current`
  distinto al del tag es error inmediato sin reintentar (el problema está
  en el bundle, no en GitHub), mientras que `checked:false` sí se
  reintenta. El proceso arrancado se mata siempre al salir del paso.

## [1.5.0] — 2026-10-29

### Añadido

- **Documentación de los smokes reales de conectores**
  (`CONTRIBUTING.md`): cómo levantar el `postgres:16` y el LocalStack S3
  en podman y qué variables de entorno activan `pg-smoke` y `s3-smoke`
  en local, con el detalle de credenciales por defecto y de lo que
  comprueba cada smoke.
- **`scripts/smoke.sh`**: los dos smokes en un solo comando — levanta
  los contenededores, espera a que estén sanos, ejecuta los tests
  reales y los **limpia siempre** (también si algo falla o hay Ctrl+C),
  con `--pg` / `--s3` para correr uno solo. Detecta podman o docker y
  usa el `.venv` si existe.

### Arreglados

- **Las columnas booleanas con nulos ya no se exportan como texto a
  Postgres**: una columna con `True`/`False` y huecos llega a pandas como
  `object` (no como `bool`), así que el DDL del modo *replace* creaba la
  columna `text` y los valores se guardaban como `"true"`/`"false"` de
  texto — al releerlos ya no eran booleanos. `pg_type_for` consulta ahora
  el contenido de la serie: genera `boolean` solo si **todo** lo no-nulo
  es bool, y los mixtos con cadenas o las columnas vacías siguen siendo
  `text`. Detectado con el smoke real contra un `postgres:16` de verdad y
  cubierto desde entonces por el job `pg-smoke` de la CI.
- **El build del Flatpak ya no depende del orden de `readdir`**: el
  script elegía la rama del bundle con el primer fichero que encontrara
  bajo `refs/`, y ahí conviven las refs `appstream`/`appstream2`, que se
  llaman como la arquitectura (`x86_64`). Cuando salía esa, `flatpak
  build-bundle` pedía `app/<id>/x86_64/x86_64` y el job fallaba con
  «Refspec not found». Ahora se lee solo la ref de la propia app y de
  forma ordenada.

## [1.4.1] — 2026-10-29

### Arreglados

- **El aviso de versión nueva ya funciona en los bundles congelados**:
  PyInstaller empaquetaba `libssl` pero **ningún almacén de CAs**, así que
  toda llamada HTTPS a `api.github.com` fallaba en silencio
  (`checked:false`) y ni el AppImage ni el `.exe` llegaban a mostrar el
  aviso (en desarrollo, con las CAs del sistema, sí funcionaba). Ambos
  specs empaquetan ahora `certifi` (`cacert.pem`) como dato y `entry.py`
  fija `SSL_CERT_FILE` a esa ruta al arrancar, respetando la variable si
  el usuario ya la ha puesto. El smoke del `.exe` en la CI del packaging
  pasa a comprobar `GET /version/check` con `checked:true` (con reintentos
  por el rate limit anónimo), de modo que una regresión de CAs rompe el
  build en la CI en vez de llegar al usuario.

## [1.4.0] — 2026-10-28

### Añadido

- **Aviso de versión nueva**: la app consulta la última release publicada
  en GitHub contra `package.json` (`GET /version/check`) y, solo si hay
  algo más nuevo, muestra un toast no intrusivo con enlace a la release
  (8 s, desaparece solo). Best-effort: sin red, con rate limit o con un
  tag ilegible responde 200 sin aviso — nunca bloquea la carga ni rompe
  la app. La respuesta queda cacheada 1 h si fue OK y 5 min si falló (no
  agota el rate limit anónimo de api.github.com), la comparación es
  numérica por componente (1.10 > 1.9) y el enlace del toast hereda el
  color del texto (subrayado, contraste AA). El `package.json` viaja ya
  como dato en los specs de AppImage/Flatpak y Windows, así que los
  bundles congelados también saben su versión. 19 tests nuevos.
- **El aviso de versión no vuelve a aparecer tras cerrarlo**: el toast
  gana un botón **×** (con nombre accesible) que recuerda la versión
  descartada en `localStorage` (`catflip-version-dismissed`) y la manda
  como `?dismissed=` a `/version/check`, que suprime el aviso mientras
  la release no supere TAMBIÉN a la descartada — con una release más
  nueva que la descartada se vuelve a avisar, y un valor corrupto en
  `localStorage` no puede callar los avisos para siempre. El
  auto-cierre a los 8 s no descarta nada: solo el × decide. Cálculo por
  petición, no contamina la caché de GitHub. +5 tests (24 en total).

## [1.3.0] — 2026-10-28

### Añadido

- **Packaging firmado de Windows (`.exe`, Open Core)**: carpeta
  `packaging/windows/` con el spec PyInstaller **onefile**
  (`catflip.spec`, reutiliza `entry.py` del AppImage) y
  `build.sh` — en **Git Bash** — que produce
  `dist/windows/CatFlip-<ver>-x64.exe`, firma con GPG la clave de
  `packaging/gpg/` y genera `SHA256SUMS(.asc)` con el mismo patrón que
  AppImage y Flatpak. El workflow `packaging.yml` gana el job **windows**
  (`windows-latest`, `defaults.run.shell: bash` porque `gpg` y `sha256sum`
  existen en Git for Windows y **no** en el PATH de PowerShell): abre con
  la comprobación de ambos binarios, importa `GPG_SIGNING_KEY`, construye,
  hace **smoke real** (el `.exe` arranca en el runner y sirve `/` y
  `/premium/status`) y verifica firmas + checksums. El tramo `release` pasa
  a adjuntar también `CatFlip-<ver>-x64.exe` y `SHA256SUMS.windows(.asc)`.
  Verificado en local: `bash -n`, actionlint 1.7.7 sobre los dos
  workflows y el spec ejecutado con PyInstaller 6.22.3.

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

[Sin publicar]: https://github.com/lpardo303/Cat_flip/compare/v1.6.0...HEAD
[1.6.0]: https://github.com/lpardo303/Cat_flip/compare/v1.5.1...v1.6.0
[1.5.1]: https://github.com/lpardo303/Cat_flip/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/lpardo303/Cat_flip/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/lpardo303/Cat_flip/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/lpardo303/Cat_flip/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/lpardo303/Cat_flip/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/lpardo303/Cat_flip/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/lpardo303/Cat_flip/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/lpardo303/Cat_flip/releases/tag/v1.0.0
