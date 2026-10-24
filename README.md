# 🐈 Cat_flip - Studio ETL

> Plataforma local de transformación de datos para Linux y Windows, construida con Python (Flask + pandas) y una interfaz web moderna.

**Cat_flip** es una alternativa ligera, diáfana y rápida a herramientas ETL pesadas (como Power Query), diseñada para ingenieros de datos y analistas que quieren procesar datos sin escribir código. Permite construir pipelines empresariales mediante una interfaz visual intuitiva, generando código Python/Pandas en tiempo real a medida que se aplican las transformaciones.

## ✨ Características Principales

* 🚀 **24 Operaciones ETL:** Herramientas de limpieza, filtrado, transformación estructural (Pivot/Unpivot), manejo de texto, enmascaramiento de PII (Regex Mask), concatenación de columnas, detección de outliers (Z-Score / IQR) y muestreo reproducible (head/tail/random/stratified con semilla fija).
* 🐍 **Generador de Código en Vivo:** Aprende y audita con el visor que muestra el código de Pandas autogenerado en tiempo real.
* 💾 **Recetas Reproducibles:** Guarda tu pipeline como `.catrecipe` y revívelo con un clic sobre cualquier dataset — el ExecutePipelineModal muestra consola y barra de progreso paso a paso, y la receta se aplica sola al llegar al 100% (reproducción atómica: un paso fallido o un Cancelar a mitad no toca tus datos), con deshacer/rehacer paso a paso (`Ctrl+Z` / `Ctrl+Shift+Z`). Un `.catrecipe` arrastrado al grid abre el mismo modal.
* 📥 **Receta desde CSV:** Elige un CSV sucio y Cat_flip **propone** una receta de limpieza (quitar espacios, filas con nulos, cambio de tipo donde todas las celdas casan, duplicados al final — máx. 4 pasos); el modal de preview lista pasos y avisos, y solo «Aplicar» la ejecuta vía el ExecutePipelineModal con dry-run previo.
* 🐍 **Receta como `.py` portátil:** Exporta la receta como script con argumentos de línea de comandos (`python pipeline.py entrada.xlsx salida.xlsx`), pasos numerados con nombre legible y código idéntico al que ejecutó la app (mismo generador, incluido el frame derecho de un `merge`).
* 🔍 **Diff por Paso:** Pregunta «¿Qué cambió este paso?» a cualquier tarjeta de tu pipeline: formas antes/después, columnas altas/bajas, deltas de nulos y únicos por columna, y una muestra de hasta 20 celdas realmente cambiadas (antes tachado, después en verde) — comparación por etiqueta de fila y 100% de solo lectura.
* 💻 **Modo CLI:** La misma receta corre en terminal, sin navegador: `python cli.py run receta.catflip.json --input datos.csv --output limpio.csv` — autodetección de separador/encoding, salidas `.csv`/`.tsv`/`.xlsx`/`.parquet` con escritura atómica y exit codes para CI.
* 🌗 **Kinetic Query Minimal:** Interfaz fluida y minimalista (Glassmorphism) con soporte persistente para modo claro y oscuro.
* 📅 **Auto-Mapeo de Tipos:** Al cargar un archivo, un motor heurístico analiza cada columna de texto del esquema completo y una barra te ofrece convertirlas con un clic a `datetime`, `int` o `float` cuando ≥90% de los valores lo permiten — cada conversión queda como paso deshacible en la receta.
* 📤 **Exportación en 5 formatos:** CSV, Excel XLSX, **Parquet** (columnar, preserva tipos), **JSON Records** (array de objetos con nulos `null` y fechas ISO, round-trip con `pd.read_json(orient='records')`) y **SQL** (script DDL + INSERT portable a PostgreSQL/SQLite con tipos derivados del dtype real, lotes de 100 filas y escapado de comillas — se ejecuta tal cual).
* 🧪 **Destinos (demo):** Simulador visual de conectores **BigQuery**, **Snowflake** y **Webhook REST**: configura proyecto/tabla o URL, valida el formulario y verás en consola el paquete que se enviaría — sin que nada salga de tu equipo (cero peticiones de red, badge DEMO permanente).
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

## 🧪 Tests

El proyecto usa `pytest` con cobertura. Los fixtures de `tests/conftest.py` resetean el estado global de `app` en cada test, así que los tests son independientes entre sí.

```bash
pip install -r requirements-dev.txt   # pytest + pytest-cov
pytest                                # suite completa
coverage gate (lo que usa CI):
pytest tests/ --cov=app --cov=operations --cov=cli --cov-report=term-missing --cov-fail-under=93
```

Los tests originales siguen siendo unittest y también corren con `python -m unittest discover -s tests`.

El workflow de CI (`.github/workflows/ci.yml`) ejecuta la suite con el gate de cobertura y añade `node --check` sobre los 5 módulos de `static/js/` en cada push/PR a `main`. Un segundo job (**axe**) levanta la app, la abre con Playwright y ejecuta [axe-core](https://github.com/dequelabs/axe-core) (WCAG 2.0 A/AA) sobre 4 superficies — página base y los modales *Receta desde CSV*, conectores demo y *Validación de esquema* — en tema claro y oscuro; si hay violaciones el job falla y sube `violations.json` como artefacto. Para correrlo localmente (con la app en `127.0.0.1:5050`):

```bash
npm ci && npx playwright install chromium
npm run test:axe
```

## 🛠️ Arquitectura

* **Backend:** `Flask` expone los endpoints REST. `Pandas` funciona como el motor de cálculo en memoria.
* **Frontend:** Vanilla JS, HTML5 y CSS3. Cero dependencias pesadas en el cliente. Interfaz reactiva comunicada vía `fetch()`.

## 📄 Licencia

Este proyecto se distribuye bajo la licencia [MIT](LICENSE). Eres libre de utilizarlo, modificarlo y distribuirlo.
