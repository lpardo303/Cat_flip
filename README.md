# 🐈 Cat_flip - Studio ETL

[![Ko-fi](https://img.shields.io/badge/Ko-fi-%23FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/lpardo303)
[![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsors-f0f2f4?logo=githubsponsors&logoColor=black)](https://github.com/sponsors/lpardo303)

> Plataforma local de transformación de datos para Linux y Windows, construida con Python (Flask + pandas) y una interfaz web moderna.

**Cat_flip** es una alternativa ligera, diáfana y rápida a herramientas ETL pesadas (como Power Query), diseñada para ingenieros de datos y analistas que quieren procesar datos sin escribir código. Permite construir pipelines empresariales mediante una interfaz visual intuitiva, generando código Python/Pandas en tiempo real a medida que se aplican las transformaciones.

## ✨ Características Principales

* 🚀 **25 Operaciones ETL:** Herramientas de limpieza, filtrado, transformación estructural (Pivot/Unpivot), reordenación de columnas (bloque fijo + resto alfabético, o mover a una posición exacta), manejo de texto y cambio de tipo en masa (selección múltiple con catálogo str/int/float/datetime/bool/category), enmascaramiento de PII (Regex Mask), concatenación de columnas, detección de outliers (Z-Score / IQR) y muestreo reproducible (head/tail/random/stratified con semilla fija).
* 🐍 **Generador de Código en Vivo:** Aprende y audita con el visor que muestra el código de Pandas autogenerado en tiempo real.
* 💾 **Recetas Reproducibles:** Guarda tu pipeline como `.catrecipe` y revívelo con un clic sobre cualquier dataset — el ExecutePipelineModal muestra consola y barra de progreso paso a paso, y la receta se aplica sola al llegar al 100% (reproducción atómica: un paso fallido o un Cancelar a mitad no toca tus datos), con deshacer/rehacer paso a paso (`Ctrl+Z` / `Ctrl+Shift+Z`). Un `.catrecipe` arrastrado al grid abre el mismo modal.
* 📥 **Receta desde CSV:** Elige un CSV sucio y Cat_flip **propone** una receta de limpieza (quitar espacios, filas con nulos, cambio de tipo donde todas las celdas casan, duplicados al final — máx. 4 pasos); el modal de preview lista pasos y avisos, y solo «Aplicar» la ejecuta vía el ExecutePipelineModal con dry-run previo.
* 🐍 **Receta como `.py` portátil:** Exporta la receta como script con argumentos de línea de comandos (`python pipeline.py entrada.xlsx salida.xlsx`), pasos numerados con nombre legible y código idéntico al que ejecutó la app (mismo generador, incluido el frame derecho de un `merge`).
* 🔍 **Diff por Paso:** Pregunta «¿Qué cambió este paso?» a cualquier tarjeta de tu pipeline: formas antes/después, columnas altas/bajas, deltas de nulos y únicos por columna, y una muestra de hasta 20 celdas realmente cambiadas (antes tachado, después en verde) — comparación por etiqueta de fila y 100% de solo lectura.
* 💻 **Modo CLI:** La misma receta corre en terminal, sin navegador: `python cli.py run receta.catflip.json --input datos.csv --output limpio.csv` — autodetección de separador/encoding, salidas `.csv`/`.tsv`/`.xlsx`/`.parquet` con escritura atómica y exit codes para CI.
* ⏱️ **Benchmark por paso:** barra proporcional sobre el pipeline con el tiempo de cada operación, chip «N ms» en cada tarjeta y leyenda con el paso más lento y su porcentaje — medido en el servidor, alineado con deshacer/rehacer y con la receta aplicada.
* 🌗 **Tech Labs (interfaz neo-brutalista mínima):** Rediseño completo sobre tokens: triada tipográfica **Plus Jakarta Sans + Space Mono**, grid técnico de fondo con cruces de registro en las esquinas, cabecera con el logo de Cat_flip en caja de acento y **canvas isométrico animado** teñido con el acento vigente (se dibuja estático si el sistema pide `prefers-reduced-motion`). Soporte persistente de modo claro y oscuro, más un modo **Automático** por defecto que sigue `prefers-color-scheme` del sistema y reacciona en vivo sin recargar. El botón de tema abre un panel con la **vista previa real** de cada opción antes de elegirla, agrupado en **Claro / Oscuro / Sistema**.
* 🖌️ **Catálogo de color de énfasis:** Sección «Color de énfasis» dentro del panel de tema — 6 presets + color personalizado (selector nativo) — que recalcula en vivo `--accent`, `--accent-hover`, `--accent-contrast`, `--accent-text` (texto derivado con **≥5.2:1** sobre las superficies del tema), `--accent-subtle` y `--accent-glow`. El acento es **ortogonal** al tema: funciona igual en claro, oscuro, Aurora y Solar, tiñe botones, badges, esquinas de sección, iconos y el fondo animado, y persiste entre sesiones.
* 🎨 **Temas premium Aurora y Solar (Open Core):** Con licencia premium, el selector añade dos paletas fijas — **Aurora** (violeta) y **Solar** (ámbar) — independientes del sistema, dentro del grupo *Claro*. Sin licencia la app es idéntica: el CSS premium ni siquiera se sirve.
* 📅 **Auto-Mapeo de Tipos:** Al cargar un archivo, un motor heurístico analiza cada columna de texto del esquema completo y una barra te ofrece convertirlas con un clic a `datetime`, `int` o `float` cuando ≥90% de los valores lo permiten — cada conversión queda como paso deshacible en la receta.
* 📤 **Exportación en 5 formatos:** CSV, Excel XLSX, **Parquet** (columnar, preserva tipos), **JSON Records** (array de objetos con nulos `null` y fechas ISO, round-trip con `pd.read_json(orient='records')`) y **SQL** (script DDL + INSERT portable a PostgreSQL/SQLite con tipos derivados del dtype real, lotes de 100 filas y escapado de comillas — se ejecuta tal cual).
* 🧪 **Destinos (demo):** Simulador visual de conectores **Snowflake** y **Webhook REST**: configura cuenta/tabla o URL, valida el formulario y verás en consola el paquete que se enviaría — sin que nada salga de tu equipo (cero peticiones de red, badge DEMO permanente).
* 🐘 **Destino real PostgreSQL (Open Core):** Con licencia premium, la sección *Destino real* conecta con tu servidor mediante [psycopg](https://www.psycopg.org/) y exporta el dataset completo a una tabla: **Probar conexión** (`SELECT version()`) y exportación en modos **Reemplazar tabla** (DDL con tipos derivados de los dtypes de pandas) o **Añadir filas**, transaccional, con identificadores comillados y valores parametrizados. El driver es opcional (`pip install -r requirements-connectors.txt`): sin él la app arranca igual y la ruta te dice cómo instalarlo; sin licencia premium la ruta responde 404.
* 🪣 **Destino real S3 (Open Core):** Con licencia premium, la tarjeta **S3** de *Destino real* sube el dataset completo como CSV a `s3://bucket/prefijo/ruta`: **Probar conexión** (`head_bucket`) y exportación en modos **Sobrescribir objeto** o **Fallar si existe**, con prefijo opcional, `endpoint_url` compatible MinIO/R2 y credenciales opcionales (si las dejas vacías manda la cadena por defecto de AWS). Mismo paquete de drivers opcional (`requirements-connectors.txt`, ahora con `boto3`) y mismo gating 404 sin licencia.
* ☁️ **Destino real BigQuery (Open Core):** Con licencia premium, la tarjeta **BigQuery** de *Destino real* carga el dataset completo en `dataset.tabla` de Google BigQuery: **Probar conexión** (`SELECT 1`) y exportación en modos **Reemplazar tabla** (`WRITE_TRUNCATE` + `autodetect`, crea la tabla si no existe) o **Añadir filas** (`WRITE_APPEND`, avisa si la tabla no existe), con proyecto, dataset y tabla validados y clave de cuenta de servicio opcional — si la dejas vacía manda la cadena por defecto del SDK (Application Default Credentials). Mismo paquete opcional (`requirements-connectors.txt`, ahora con `google-cloud-bigquery`, `db-dtypes` y `pyarrow`), misma acción del driver ausente y mismo gating 404 sin licencia; la clave privada nunca se muestra y queda enmascarada en los errores.
* 🛡️ **Validación de esquema:** Define reglas por columna — **no-nulo**, **único**, **regex** y **rango** (mín/máx inclusivo) — y Cat_flip pinta de rojo las celdas que las incumplen con el motivo en el tooltip, con badge de conteo y resumen por columna. Solo marcan: nunca tocan los datos ni entran en la receta, se revalidan solas tras cada operación/deshacer y se limpian al cargar otro archivo.
* 📊 **Perfilado de Datos:** Diagnóstico estadístico instantáneo de tus columnas (nulos, valores únicos, mínimos, máximos) y **heatmap de correlaciones de Pearson** entre columnas numéricas — teal para positivas, rojo para negativas, celdas sin variación como «—» — con refresco automático tras cada operación.
* 💻 **100% Local y Privado:** Sin bases de datos ni envíos a la nube; todo el procesamiento ocurre de forma segura en la memoria RAM de tu equipo.

## 🚀 Instalación y Uso

Asegúrate de tener **Python 3.10+** instalado en tu sistema.

1. **Clona el repositorio:**
   ```bash
   git clone https://github.com/lpardo303/Cat_flip.git
   cd Cat_flip
   ```

2. **Crea y activa un entorno virtual:**

   **Linux / macOS:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Bash/Zsh
   source .venv/bin/activate.fish   # Fish shell
   ```

   **Windows:**
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Instala las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

   *Opcional — conectores reales de Postgres, S3 y BigQuery (función
   premium; sin ellos la app funciona igual):*
   ```bash
   pip install -r requirements-connectors.txt
   ```

4. **Ejecuta la aplicación:**

   **Linux (Bash/Zsh):**
   ```bash
   ./launch.sh
   ```
   **Linux (Fish):**
   ```fish
   ./launch.fish
   ```
   **Windows (doble clic o cmd):**
   ```bat
   launch.bat
   ```
   **Windows (PowerShell):**
   ```powershell
   .\launch.ps1
   ```
   O directamente en cualquier sistema:
   ```bash
   python app.py
   ```

5. **Abre tu navegador:** Visita `http://127.0.0.1:5050`

> **Modo CLI (sin navegador):**
> ```bash
> python cli.py run receta.catflip.json --input datos.csv --output limpio.csv
> ```
> Exit codes: `0` OK · `1` receta/datos (cita el paso) · `2` flags. Ver *Modo CLI* en `manual_de_usuario.md`.

> **Nota Windows — PowerShell:** Si al ejecutar `launch.ps1` aparece un error de política de ejecución, corre este comando una sola vez en PowerShell como administrador:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

## 📦 Paquetes (AppImage y Flatpak)

El core MIT se empaqueta en dos formatos **firmados con GPG** desde [`packaging/`](packaging/):

```bash
packaging/appimage/build.sh   # dist/appimage/CatFlip-<ver>-x86_64.AppImage (+ .asc y SHA256SUMS firmados)
packaging/flatpak/build.sh    # dist/flatpak/repo (ostree firmado) + CatFlip-<ver>.flatpak (+ .asc)
```

Ambos formatos envuelven el mismo binario congelado de PyInstaller. Requisitos, verificación de firmas, instalación y las decisiones técnicas (runtime 26.08, SDK a nivel de sistema) están en **[packaging/README.md](packaging/README.md)**.

## 🧪 Tests

El proyecto usa `pytest` con cobertura. Los fixtures de `tests/conftest.py` resetean el estado global de `app` en cada test, así que los tests son independientes entre sí.

```bash
pip install -r requirements-dev.txt   # pytest + pytest-cov
pytest                                # suite completa
coverage gate (lo que usa CI):
pytest tests/ --cov=app --cov=operations --cov=cli --cov-report=term-missing --cov-fail-under=93
```

Los tests originales siguen siendo unittest y también corren con `python -m unittest discover -s tests`.

El workflow de CI (`.github/workflows/ci.yml`) ejecuta la suite con el gate de cobertura y añade `node --check` sobre los 5 módulos de `static/js/` en cada push/PR a `main`. Un segundo job (**axe**) levanta la app (con `CATFLIP_PREMIUM_KEY` para cubrir también las paletas premium), la abre con Playwright y ejecuta [axe-core](https://github.com/dequelabs/axe-core) (WCAG 2.0 A/AA) en 15 corridas: la página base en modo Automático con el sistema en oscuro (`prefers-color-scheme`, perfil sin localStorage); tema claro/oscuro explícitos sobre 6 superficies — página base, los modales *Receta desde CSV*, conectores demo y *Validación de esquema*, la pestaña Diagnóstico con el heatmap y el panel del selector de tema abierto —; y las 2 paletas premium **Aurora** y **Solar**; además verifica que el cambio en vivo del sistema re-aplica el tema. Si hay violaciones o fallos el job falla y sube `violations.json` como artefacto. Para correrlo localmente (con la app en `127.0.0.1:5050`; para las 15 corridas, levántala con `CATFLIP_PREMIUM_KEY=local python app.py`):

```bash
npm ci && npx playwright install chromium
npm run test:axe
```

## 🛠️ Arquitectura

* **Backend:** `Flask` expone los endpoints REST. `Pandas` funciona como el motor de cálculo en memoria.
* **Frontend:** Vanilla JS, HTML5 y CSS3. Cero dependencias pesadas en el cliente. Interfaz reactiva comunicada vía `fetch()`.

## ☕ Apoya el proyecto

Cat_flip es y seguirá siendo **gratuito y de código abierto (MIT)**: nada de esto se traslada a funciones de pago ni telemetría. Si el proyecto te ahorra tiempo, puedes invitarme un café por [**Ko-fi**](https://ko-fi.com/lpardo303) o apoyar su desarrollo con [**GitHub Sponsors**](https://github.com/sponsors/lpardo303) — los mismos enlaces viven en el footer de la app. El apoyo es voluntario y solo sostiene el ritmo de desarrollo del core.

## 🤝 Contribuir

Las contribuciones son bienvenidas. Lee [CONTRIBUTING.md](CONTRIBUTING.md) para el flujo completo: puesta en marcha, verificación obligatoria antes del PR (suite con gate de cobertura, `node --check` y gate de axe) y convenciones de código, diseño y accesibilidad.

## 📋 Changelog

Los cambios por versión se documentan en [CHANGELOG.md](CHANGELOG.md) (formato Keep a Changelog, versionado semántico).

## 💼 Licencia dual (Open Core)

El core es **MIT** y nunca se degrada: sin licencia la app funciona igual, sin telemetría ni funciones de pago. Para uso empresarial embebido (incrustar Cat_flip en un producto propietario, distribuir binarios sin publicar la fuente o servirlo como SaaS) existe una **licencia comercial** — ver [LICENSE-PREMIUM.txt](LICENSE-PREMIUM.txt) (borrador) y contacta por [Ko-fi](https://ko-fi.com/lpardo303) o [GitHub Sponsors](https://github.com/sponsors/lpardo303).

## ⭐ Premium (Open Core)

Junto al core vive el paquete [`premium/`](premium/), con gating **server-side**: la licencia se activa con la env var `CATFLIP_PREMIUM_KEY` o el fichero `premium.key` (ignorado por git), y sin ella `/premium/status` devuelve la lista vacía y `/premium/themes/<id>.css` responde 404. Hoy contiene los **temas Aurora y Solar** y los **conectores reales de Postgres, S3 y BigQuery** (`/connectors/{postgres,s3,bigquery}/*`, drivers opcionales en `requirements-connectors.txt`); en el roadmap, auto-update. El packaging firmado vive en [`packaging/`](packaging/README.md) — Linux (Flatpak/AppImage) y Windows (`.exe` onefile). Detalles y guía para ampliarlo en [premium/README.md](premium/README.md).

## 📄 Licencia

Este proyecto se distribuye bajo la licencia [MIT](LICENSE). Eres libre de utilizarlo, modificarlo y distribuirlo. El paquete `premium/` y [LICENSE-PREMIUM.txt](LICENSE-PREMIUM.txt) se rigen por la licencia comercial.
