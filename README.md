# 🐈 Cat_flip - Studio ETL

> Plataforma local de transformación de datos para Linux y Windows, construida con Python (Flask + pandas) y una interfaz web moderna.

**Cat_flip** es una alternativa ligera, diáfana y rápida a herramientas ETL pesadas (como Power Query), diseñada para ingenieros de datos y analistas que quieren procesar datos sin escribir código. Permite construir pipelines empresariales mediante una interfaz visual intuitiva, generando código Python/Pandas en tiempo real a medida que se aplican las transformaciones.

## ✨ Características Principales

* 🚀 **21 Operaciones ETL:** Herramientas de limpieza, filtrado, transformación estructural (Pivot/Unpivot), manejo de texto y enmascaramiento de PII (Regex Mask).
* 🐍 **Generador de Código en Vivo:** Aprende y audita con el visor que muestra el código de Pandas autogenerado en tiempo real.
* 🌗 **Kinetic Query Minimal:** Interfaz fluida y minimalista (Glassmorphism) con soporte persistente para modo claro y oscuro.
* 📅 **Auto-Mapeo de Tipos:** Al cargar un archivo, un motor heurístico analiza cada columna de texto del esquema completo y una barra te ofrece convertirlas con un clic a `datetime`, `int` o `float` cuando ≥90% de los valores lo permiten — cada conversión queda como paso deshacible en la receta.
* 📊 **Perfilado de Datos:** Diagnóstico estadístico instantáneo de tus columnas (nulos, valores únicos, mínimos, máximos).
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
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=93
```

Los tests originales siguen siendo unittest y también corren con `python -m unittest discover -s tests`.

El workflow de CI (`.github/workflows/ci.yml`) ejecuta la suite con el gate de cobertura y añade `node --check` sobre los 5 módulos de `static/js/` en cada push/PR a `main`.

## 🛠️ Arquitectura

* **Backend:** `Flask` expone los endpoints REST. `Pandas` funciona como el motor de cálculo en memoria.
* **Frontend:** Vanilla JS, HTML5 y CSS3. Cero dependencias pesadas en el cliente. Interfaz reactiva comunicada vía `fetch()`.

## 📄 Licencia

Este proyecto se distribuye bajo la licencia [MIT](LICENSE). Eres libre de utilizarlo, modificarlo y distribuirlo.
