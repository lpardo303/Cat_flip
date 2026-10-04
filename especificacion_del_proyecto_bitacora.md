# Cat_flip — Especificación del Proyecto

> Plataforma local de transformación de datos para Linux, construida con Python (Flask + pandas) y una interfaz web.

---

## 🤖 Protocolo de Relevo (Trabajo en Grupo de IAs)

> **⚠️ REGLA DE ORO PARA LA IA ACTIVA:** Estás trabajando en equipo con otros modelos (Claude 3.5 Sonnet, Gemini PRO y DeepSeek-V3.1). Compartimos este archivo como nuestra bitácora común. 
> 
> **Al final de tu turno/sesión, antes de despedirte, es OBLIGATORIO que actualices este archivo:**
> 1. Mueve las tareas completadas a la sección correspondiente con un ✅ y la fecha.
> 2. Actualiza la sección `🚨 Siguiente Paso Inmediato` para que el siguiente modelo sepa exactamente dónde retomar la actividad sin perder contexto.

### 🚨 Siguiente Paso Inmediato

> **Contexto del relevo (DeepSeek):** Bugs 1, 2 y 3 resueltos y **validados en vivo** con pandas `3.0.6` (ver `🐛 Bugs conocidos` e `Historial de Cambios`). Antes de tocar el backend, ten en cuenta el **hallazgo clave**: el `TypeError: '<' not supported` **no** venía de `/stats`, sino de la operación `sort` sobre columnas `object` mixtas (columna "Valor" tras un `unpivot`).

- [ ] **Manual de Uso / Documentación (siguiente tarea de más valor):** Crear `MANUAL.md` documentando las 25 operaciones ETL disponibles. El backend ya está estable, es buen momento para documentarlo.
- [ ] **Verificación cruzada / QA (UI):** Repasar el pipeline completo en la interfaz con un dataset real que contenga columnas de tipos mixtos (ej. cargar → `unpivot` → `ordenar`) para confirmar visualmente que `/stats` y `sort` ya no rompen la vista del Data Grid ni el panel de Diagnóstico.
- [ ] **(Opcional) Alinear el doc maestro de diseño** `contexto_del_proyecto.md`: sigue diciendo "17 operaciones" (son **25**) y menciona "Polars/M-code" (el motor real es **pandas**). Conviene corregirlo para no confundir a la próxima IA.

---

## 📁 Estructura del proyecto

```
/home/luisp/Documentos/DEV_Proyects/Cat_flip/
├── app.py                  # Backend Flask (API REST + lógica pandas)
├── templates/
│   └── index.html          # Interfaz web (HTML + CSS + JS vanilla)
├── assets/
│   └── Cat_flip-logo.svg   # Logo del proyecto
├── launch.fish             # Script lanzador para fish shell
├── launch.sh               # Script lanzador para bash/zsh
├── especificacion_del_proyecto_bitacora.md  # Bitácora técnica (este archivo)
├── manual_de_usuario.md    # Manual completo del aplicativo, con un enfoque amigable para el usuario final
└── contexto_del_proyecto.md    # Documento maestro de diseño y arquitectura
```

Entorno virtual: `/home/luisp/Documentos/DEV_Proyects/Cat_flip/.venv/`

---

## 🚀 Cómo ejecutar

```fish
# Fish shell
source ~/Documentos/DEV_Proyects/Cat_flip/.venv/bin/activate.fish && python ~/Documentos/DEV_Proyects/Cat_flip/app.py
```

O simplemente ejecutar el script lanzador:

```fish
# Fish
~/Documentos/DEV_Proyects/Cat_flip/launch.fish

# Bash/Zsh
bash ~/Documentos/DEV_Proyects/Cat_flip/launch.sh
```

Luego abrir: **http://127.0.0.1:5050**

---

## 🧱 Arquitectura

- **Backend:** Flask (`app.py`) expone endpoints REST. El DataFrame activo se guarda en memoria (`current_df`). Cada operación guarda el estado anterior en `history[]` para soportar undo.
- **Frontend:** HTML/CSS/JS vanilla en una sola plantilla (`index.html`). Se comunica con el backend vía `fetch()` (JSON).
- **Sin base de datos:** Todo vive en RAM mientras el servidor corre. El resultado se exporta manualmente.

---

## ✅ Funcionalidades implementadas

| # | Función | Endpoint / Op |
|---|---|---|
| 1 | Cargar CSV (auto-detecta `,` o `;`) | `POST /upload` |
| 2 | Cargar XLSX / XLS (selección de hoja) | `POST /upload` + `POST /get_sheets` |
| 3 | Unpivot (`melt`) | `POST /operation` → `unpivot` |
| 4 | Pivot (`pivot_table`) | `POST /operation` → `pivot` |
| 5 | Separar columna por delimitador (en columnas múltiples) | `POST /operation` → `split_column` |
| 6 | Separar columna por filas (explode) | `POST /operation` → `split_to_rows` |
| 7 | Filtrar filas (`==`, `!=`, `contiene`, `no contiene`, `>`, `<`) | `POST /operation` → `filter` |
| 8 | Eliminar filas con nulos | `POST /operation` → `drop_nulls` |
| 9 | Eliminar duplicados | `POST /operation` → `drop_duplicates` |
| 10 | Renombrar columna | `POST /operation` → `rename_column` |
| 11 | Eliminar columna | `POST /operation` → `drop_column` |
| 12 | Limpiar espacios en celdas (trim) | `POST /operation` → `trim` |
| 13 | Cambiar mayúsculas/minúsculas (`lower`, `upper`, `title`) | `POST /operation` → `change_case` |
| 14 | Reemplazar valores en columna | `POST /operation` → `replace` |
| 15 | Cambiar tipo de dato (`str`, `int`, `float`, `datetime`) | `POST /operation` → `change_type` |
| 16 | Ordenar por columna | `POST /operation` → `sort` |
| 17 | Deshacer (undo) | `POST /undo` |
| 18 | Exportar CSV / XLSX | `POST /export` |
| 19 | Estadísticas por columna (tipo, nulos, únicos, min/max/media) | `GET /stats` |
| 20 | Log de código Python generado | acumulado en `code_log[]` |
| 21 | Limpiar saltos de línea en celdas | `POST /operation` → `clean_newlines` |
| 22 | Eliminar filas por posición (inicio o final) | `POST /operation` → `drop_rows` |
| 23 | Definir fila como encabezado (`set_header`) | `POST /operation` → `set_header` |
| 24 | Formateo de texto — capitalize | `POST /operation` → `change_case` |
| 25 | Exponer max_split en separar columna | `POST /operation` → `split_column` |

---

## 🐛 Bugs conocidos (Por resolver)

- [x] ~~**Bug 1 — `TypeError: '<' not supported`**~~ ✅ `2026-10-04`
  - **Hallazgo clave (corrige el diagnóstico original):** el error **no** provenía de `/stats` (probado en vivo: `/stats` devolvía `HTTP 200` incluso con columnas mixtas). Se originaba en la operación **`sort`** al ordenar una columna de tipo **`object` mixto** (típicamente la columna `Valor` generada por `unpivot`/`melt`). `/stats` sí tenía un riesgo latente al llamar `min`/`max` sobre columnas mixtas.
  - *Fix aplicado:* `/stats` blindado (try/except por columna, normalización a `float`, y fallback de `nunique` a conteo textual) **y** `sort` con fallback a orden textual (`key=lambda s: s.astype(str)`) cuando la columna tiene tipos mixtos.
- [x] ~~**Bug 2 — `Pandas4Warning`: `select_dtypes(include="object")` deprecado**~~ ✅ `2026-10-04`
  - Corregido en **DOS** puntos (no solo `trim`): **línea 185** (`trim`) y **línea 200** (`clean_newlines`). Se cambió a `include=["object", "str"]`, que silencia el warning y es compatible con pandas 2 y 3.
- [x] ~~**Bug 3 — `POST /operation` retorna 500 aleatorio**~~ ✅ `2026-10-04`
  - Confirmado: era **consecuencia del Bug 1**. El 500 se producía al ejecutar `sort` sobre una columna de tipos mixtos. Con el fallback de `sort` ya no ocurre.

---

## 📋 Pendientes de Evolución

### 🎨 Identidad Visual y UI
- [x] ~~Crear la hoja de estilos base para soportar la integración de temas claro / oscuro de forma nativa.~~ ✅ `2026-10-03`
- [ ] **Badges de Tipo de Dato en Cabeceras (`INT`, `STR`, `DATE`):** Etiquetas compactas en los encabezados del Data Grid que muestren el tipo inferido y permitan abrir directamente el modal de cambio de tipo o filtro al hacer clic sobre ellas.
- [ ] **Barra de Calidad de Datos (Data Quality Bar):** Micro-barra de 3px bajo cada cabecera de columna que ilustra la proporción de datos válidos (verde) vs. nulos (amarillo/gris) en tiempo real sin salir de la vista de datos.

### 💡 Nuevas Funcionalidades y Features Propuestas (Roadmap)
- [ ] **Exportar Pipeline como Script Python (`.py` o `.ipynb`):** Botón en el panel derecho de control para descargar todo el `code_log[]` acumulado como un archivo ejecutable independiente o Jupyter Notebook (ideal para automatización con cron, Airflow o reproducción analítica).
- [ ] **Columna Calculada (Custom Column):** Operación ETL que permita al usuario crear nuevas columnas mediante expresiones matemáticas, de texto o lógicas de Pandas (ej. `df['total'] = df['precio'] * df['cantidad']` o concatenaciones).
- [ ] **Detección inteligente y sugerencias:** Detección automática de columnas de fechas almacenadas como texto y recomendación de tipado/normalización al cargar el dataset.

### 📦 Distribución y Monetización (Vibe-Coding Open Source)
- [ ] **Subir a GitHub:** Preparar el repositorio excluyendo `.venv` (crear `.gitignore`).
- [ ] **Estrategia sugerida:** Publicar el núcleo como Open Source bajo licencia MIT para la comunidad local de Linux (Vibe-Coding), y empaquetar una versión instalable premium simplificada (ej: formato Flatpak o AppImage) con extras visuales para monetizar mediante donaciones (Ko-fi/GitHub Sponsors) o licencias de uso personal.

### 📚 Documentación y Buenas Prácticas
- [ ] **Manual de uso:** Crear `MANUAL.md` documentando las 25 funciones finalizadas.
- [ ] **Skills del proyecto:** Crear una carpeta `/skills/` local donde se guarden guías compactas de UI/UX y arquitectura de Pandas para inyectar contexto rápido a los modelos sin consumir tokens leyendo documentación externa.

---

## 🗂️ Convenciones del código

- Toda operación del backend sigue el patrón:
  1. Copia del DataFrame actual (`df = current_df.copy()`)
  2. Transformación
  3. Append a `history[]` y `code_log[]`
  4. Retorna `{ success, data, code, last_code }`
- El frontend define cada operación en el objeto `modalDefs` (título, cuerpo del formulario, función `params()`).
- `currentOp` se guarda en `const op = currentOp` **antes** de cerrar el modal para evitar el bug de `null`.

---

## ✅ Historial de Cambios (Completados)
- `2026-10-04` — **Fix Backend (DeepSeek): Bugs 1, 2 y 3 resueltos.** (1) `/stats` blindado contra columnas de tipos mixtos (`try/except` por columna, normalización de min/max a `float`, fallback de `nunique` a conteo textual). (2) `select_dtypes(include="object")` → `include=["object", "str"]` en `trim` (línea 185) y `clean_newlines` (línea 200), eliminando el `Pandas4Warning`. (3) Operación `sort` con fallback a orden textual en columnas `object` mixtas (causa real del `TypeError: '<' not supported` y del 500 aleatorio). Validado en vivo con Flask + pandas `3.0.6`.
- `2026-10-04` — **Migrar Emojis a Lucide Icons:** Se reemplazaron todos los emojis de la interfaz (botones de operaciones, secciones, pestañas del canvas, pipeline y modales) por SVGs vectoriales en línea estilo Lucide Icons (stroke 1.75 - 2px, adaptables con `currentColor`).
- `2026-10-04` — **Integrar Logo Adaptativo:** Implementado el logo oficial vectorial (`Cat_flip-logo.svg`) en el Top Ribbon y en el empty state, con variables CSS (`--logo-disc` y `--logo-cat`) que adaptan el contraste de la silueta del gato y el disco según el tema claro u oscuro.
- `2026-10-03` — Se integran correcciones en el CSS (tema oscuro): creación de variable `--color-mutation`, `--row-alt`, y hovers de filas dinámicos `--row-hover`.
- `2026-10-03` — Se añade modo de persistencia en localStorage para el tema (Toggle Light/Dark).
- `2026-10-03` — Migración a la arquitectura visual Kinetic Query Minimal (3 columnas) — Frontend refactorizado en su totalidad.
- `2026-10-03` — Resuelto Bug 4: Expansión dinámica para N columnas en frontend y backend en la opción "Separar Columna".
- `2026-09-27` — Mover proyecto al directorio principal `/Cat_flip/` y recrear `.venv`.
- `2026-09-27` — Implementar funcionalidad "Eliminar filas por posición" (`drop_rows`).
- `2026-09-27` — Implementar funcionalidad "Definir fila como encabezado" (`set_header`).
- `2026-09-27` — Corregir Ajuste 5 en "Separar columna" (`max_split` dinámico).
- `2026-09-27` — Agregar Checkbox global de columnas en modales clave de selección múltiple.
