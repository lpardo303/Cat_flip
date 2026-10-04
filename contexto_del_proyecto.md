# 🐈 Cat_flip - Studio ETL

## 1. Visión General

**Cat_flip - Studio ETL** es una aplicación web diseñada como una alternativa moderna y ligera a Power Query (especialmente optimizada para entornos Linux y Web). Su objetivo es proporcionar un entorno de trabajo analítico de alta precisión para ingenieros de datos y usuarios de negocio, permitiendo la construcción de pipelines ETL empresariales mediante una interfaz visual intuitiva y reactiva.

El sistema fusiona el rigor utilitario de la manipulación de datos tabulares con un diseño web moderno y fluido (Glassmorphism), generando automáticamente código backend (Python/Pandas) en tiempo real a medida que se aplican las transformaciones.

## 2. Arquitectura de Interfaz (UI/UX)

El sistema de diseño, denominado **Kinetic Query Minimal**, abandona el modo oscuro tradicional en favor de un entorno diáfano y focalizado, soportando tanto modo Claro como Oscuro mediante persistencia.

### 2.1. Estilo Visual

* **Tema:** Soporte Light/Dark persistente, fundamentado en principios de minimalismo y *Glassmorphism* controlado (paneles translúcidos, fondos esmerilados y sombras sutiles).

* **Colores Principales:**

  * **Base/Canvas:** Tonos gris-azulado muy claros para modo claro, o tonos oscuros azulados para el modo oscuro, buscando evitar la fatiga visual.

  * **Primario (Acción/Éxito):** Teal/Cyan (`#267c7c`), utilizado para herramientas activas, tipografía principal y validaciones.

  * **Secundario (Mutación/Alerta):** Naranja vibrante (`#e26d0d`), reservado para advertencias y ejecución de acciones críticas.

* **Tipografía:**

  * `Hanken Grotesk`: Para encabezados, modales y títulos de nodos.

  * `Geist`: Para la interfaz general y legibilidad en herramientas.

  * `JetBrains Mono`: Para la cuadrícula de datos (Data Grid), tipos de datos, código y fórmulas.

### 2.2. Disposición Espacial (Layout Fluido)

La interfaz se divide en un diseño modular de 3 columnas principales, con paneles laterales colapsables para maximizar el área de datos:

1. **Top Ribbon (Header):** Contiene el branding, ruta del archivo activo, métricas rápidas (filas, calidad), barra de pestañas globales (Data Grid, Recipe Steps, Profiling) y botones de ejecución global.

2. **Panel Izquierdo (Caja de Transformaciones):** Menú colapsable con las 25 operaciones ETL estructuradas categóricamente.

3. **Panel Central (Work Area Canvas):** Área principal con pestañas para interactuar con los datos (Grid), ver estadísticas de calidad o revisar el código generado.

4. **Panel Derecho (Pipeline y Exportación):** Menú colapsable que muestra la fuente de datos cargada, el historial de pasos aplicados (Receta) y las opciones de exportación.

## 3. Funcionalidades Core y Motor ETL (Pandas)

Todas las operaciones se ejecutan visualmente en el frontend, enviando los parámetros a un backend basado en Python y Pandas, que procesa el pipeline y devuelve el nuevo estado de los datos junto con el código generado.

### 3.1. Gestión de Archivos y Fuentes de Datos

* **Soporte de Ingesta:** Carga de archivos vía Drag & Drop o selección tradicional. Formatos soportados: `.CSV`, `.XLSX`, `.XLS`.

* **Selección de Hojas (Sheet Selector):** Si se detecta un archivo Excel con múltiples pestañas, el sistema despliega un modal o selector para que el usuario elija la hoja de trabajo a procesar.

### 3.2. Caja de Transformaciones (25 Operaciones)

Las transformaciones (detalladas en el MANUAL.md) se organizan en las siguientes categorías lógicas:

**A. Transformación Estructural** (Pivot, Unpivot, Separar columnas/filas, Definir encabezado).
**B. Limpieza & Filtrado** (Eliminar nulos/duplicados/filas por posición, Trim espacios, Limpiar saltos de línea).
**C. Texto & Tipos** (May/Min, Reemplazar, Renombrar/Eliminar columna, Cambiar tipo de dato).
**D. Reglas & Operaciones** (Filtrar lógico, Ordenar).

### 3.3. Panel de Inspección (Vistas Centrales)

* **Data Grid (Tabla de Datos):** Tabla infinita, optimizada (muestra truncada si es necesario para el rendimiento en UI).

* **Diagnóstico (Estadísticas):** Pantalla de perfilado de columnas en tiempo real. Muestra conteo de nulos, valores únicos, min/max, promedios y distribuciones.

* **Python:** Un visor en vivo que muestra el código generado en Python nativo con Pandas correspondiente a cada transformación aplicada en el pipeline.

### 3.4. Pipeline Receta y Gestión de Estado

* **Historial de Pasos (Recipe):** En el panel derecho, cada acción genera un "Paso" visual (Tarjeta).

* **Control de Flujo:** Botón de **Deshacer (Undo)** o atajo `Ctrl+Z` para revertir el último cambio de estado.

* **Exportación:** Descarga del dataset final limpio en formato `.CSV` o Excel `.XLSX`.

## 4. Dinámica Cliente - Servidor

1. **Carga:** El usuario carga el archivo, que se procesa en el backend (ej. endpoint `/upload`).

2. **Operación:** Cuando se ejecuta una acción, el modal recopila los parámetros y envía un JSON al endpoint `/operation`.

3. **Respuesta:** El backend retorna tres elementos fundamentales:

   * `data`: La muestra truncada de los datos (columnas, shape) para refrescar el *Data Grid*.

   * `code`: El fragmento actualizado del script de Python.

   * `stats` (vía `/stats`): Los perfiles actualizados de integridad y distribución.

4. **Descarga:** Al finalizar, el request `/export` solicita al backend procesar todo el archivo con los pasos en memoria y retorna el blob (CSV o XLSX).