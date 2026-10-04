# 🐈 Cat_flip - Studio ETL

> Plataforma local de transformación de datos para Linux, construida con Python (Flask + pandas) y una interfaz web moderna.

**Cat_flip** es una alternativa ligera, diáfana y rápida a herramientas ETL pesadas (como Power Query), diseñada para ingenieros de datos y analistas. Permite construir pipelines empresariales mediante una interfaz visual intuitiva, generando código backend en tiempo real a medida que se aplican las transformaciones.

## ✨ Características Principales

* 🚀 **25 Operaciones ETL:** Herramientas de limpieza, filtrado, transformación estructural (Pivot/Unpivot) y manejo de texto.
* 🐍 **Generador de Código en Vivo:** Aprende y audita con el visor que muestra el código de Pandas autogenerado en tiempo real.
* 🌗 **Kinetic Query Minimal:** Interfaz fluida y minimalista (Glassmorphism) con soporte persistente para modo claro y oscuro.
* 📊 **Perfilado de Datos:** Diagnóstico estadístico instantáneo de tus columnas (nulos, valores únicos, mínimos, máximos).
* 💻 **100% Local y Privado:** Sin bases de datos ni envíos a la nube; todo el procesamiento ocurre de forma segura en la memoria RAM de tu equipo.

## 🚀 Instalación y Uso

Asegúrate de tener Python 3.10+ instalado en tu sistema.

1. **Clona el repositorio:**
   ```bash
   git clone https://github.com/TU_USUARIO/Cat_flip.git
   cd Cat_flip
   ```

2. **Crea y activa un entorno virtual:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # En Bash/Zsh
   # o bien: source .venv/bin/activate.fish  # En Fish shell
   ```

3. **Instala las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Ejecuta la aplicación:**
   ```bash
   python app.py
   # O usa los scripts lanzadores incluidos: ./launch.sh o ./launch.fish
   ```

5. **Abre tu navegador:** Visita `http://127.0.0.1:5050`

## 🛠️️ Arquitectura

* **Backend:** `Flask` expone los endpoints REST. `Pandas` funciona como el motor de cálculo en memoria.
* **Frontend:** Vanilla JS, HTML5 y CSS3. Cero dependencias pesadas en el cliente. Interfaz reactiva comunicada vía `fetch()`.

## 📄 Licencia

Este proyecto se distribuye bajo la licencia MIT. Eres libre de utilizarlo, modificarlo y distribuirlo.