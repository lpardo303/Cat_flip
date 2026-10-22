# 🐈 Cat_flip - Manual de Usuario

Bienvenido a **Cat_flip - Studio ETL**, tu plataforma local y ligera para la limpieza, transformación y preparación de datos. Diseñada como una alternativa rápida a herramientas pesadas, Cat_flip te permite construir pipelines de datos visualmente mientras genera código Python por debajo.

Este manual detalla las 24 operaciones de transformación disponibles en la "Caja de Transformaciones" (Panel Izquierdo) de la interfaz.

---

## 🏗️ A. Transformación Estructural

Estas herramientas modifican la forma y arquitectura de tu tabla de datos (Data Grid).

1. **Pivot (Dinamizar):** 
   Transforma filas en columnas. Selecciona una columna de índices (las filas que se mantendrán), una columna de columnas (cuyos valores únicos se convertirán en nuevas cabeceras) y una columna de valores (los datos que llenarán la intersección, aplicando una función de agregación si hay duplicados).
2. **Unpivot (Anular Dinamización / Melt):** 
   Pasa columnas a filas. Ideal para tablas anchas. Selecciona las columnas "identificadoras" (que se mantienen fijas) y las columnas a "des-dinamizar". Crea dos nuevas columnas: una con los nombres originales de las columnas y otra con sus respectivos valores.
3. **Separar Columna:** 
   Divide una o varias columnas en múltiples partes basándose en un carácter delimitador (ej. una coma `,`, un guion `-`). Puedes definir un límite máximo de separaciones (`max_split`).
4. **Separar Filas (Explode):** 
   Si una celda contiene múltiples valores separados por un delimitador (ej. `A, B, C`), esta función crea una fila independiente para cada valor, duplicando el resto de la información de la fila original.
5. **Definir Encabezado:** 
   Promueve una fila específica de tus datos para que se convierta en el nombre de las columnas. Se ingresa la posición numérica de la fila (0 para la primera fila). Útil para archivos donde los títulos no están en la primera fila.

---

## 🧹 B. Limpieza & Filtrado

Funciones esenciales para sanear tus datos y remover información basura.

6. **Eliminar Nulos:** 
   Borra filas que contienen celdas vacías (NaN). Puedes elegir si eliminar la fila cuando *cualquier* celda seleccionada es nula (ANY) o solo cuando *todas* las celdas seleccionadas son nulas (ALL).
7. **Eliminar Duplicados:** 
   Remueve filas idénticas basándose en las columnas que elijas como "clave". Retiene únicamente la primera aparición de la fila.
8. **Eliminar Filas (Por posición):** 
   Recorta un número específico de filas directamente desde el principio (Top) o el final (Bottom) de tu dataset.
9. **Trim Espacios:** 
   Limpia espacios en blanco accidentales al principio o al final del texto dentro de las celdas (ej. `"  texto "` se convierte en `"texto"`). Además, las operaciones de texto (Trim, Limpiar Saltos, May/Min, Reemplazar, Separar Filas/Columnas y Cambiar Tipo a texto) convierten las cadenas vacías, los espacios sobrantes y los strings `"nan"`/`"none"`/`"null"` en **nulos reales** de pandas, de modo que *Eliminar Nulos*, las estadísticas y la barra de calidad reflejan el vacío verdadero.
10. **Limpiar Saltos de Línea:** 
    Normaliza el texto de las celdas eliminando saltos de línea invisibles (`\n`, `\r`, `\r\n`) que suelen causar problemas al exportar a CSV.

---

## 🔡 C. Texto & Tipos

Operaciones de formato de cadenas y estructura de datos.

11. **May/Min (Cambiar Mayúsculas/Minúsculas):** 
    Modifica la capitalización de toda una columna de texto. Opciones disponibles: minúsculas (`lower`), MAYÚSCULAS (`upper`), Tipo Título (`title`), o Primera letra mayúscula (`capitalize`). *(Nota: Las opciones title y capitalize cubren la operación "Title Case" del listado original del proyecto).*
12. **Reemplazar Valores:** 
    Busca una palabra o fragmento de texto específico dentro de una columna y lo sustituye por otro. 
13. **Renombrar Columna:** 
    Cambia el nombre de la cabecera de una columna seleccionada.
14. **Eliminar Columna:** 
    Borra completamente la columna seleccionada de tu dataset.
15. **Cambiar Tipo de Dato:** 
    Fuerza a una columna a interpretarse como un tipo de dato específico: Texto (`str`), Número Entero (`int`), Número Decimal (`float`) o Fecha y Hora (`datetime`).
16. **Enmascarar / Extraer PII (Regex Mask):** 
    Detecta datos personales (emails, teléfonos, identificadores tipo `SN-001`/`X204` o números de tarjeta de 13–19 dígitos) — o cualquier regex personalizada — dentro de una columna y actúa en dos modos: **Enmascarar** sustituye cada coincidencia en la misma columna por un relleno (por defecto `****`; vacío = borrar la coincidencia) y **Extraer a columna nueva** copia la primera coincidencia de cada fila a una columna nueva (`Email_mask` por defecto) dejando la fuente intacta. Los nulos reales se conservan en ambos modos. El patrón solo se aplica sobre la columna elegida; puedes deshacer el paso como cualquier otro.
17. **Concatenar Columnas:** 
    Une 2 o más columnas en una sola columna nueva con el delimitador que elijas (por defecto un espacio; vacío = unir sin separador), en el orden en que las marques. Los nulos se **omiten** al unir: no quedan delimitadores sueltos (`Ana` + nulo + `Torres` con espacio → `Ana Torres`, no `Ana  Torres`) y una fila cuyas columnas elegidas son todas nulas produce un nulo real. Puedes eliminar las columnas originales tras la unión (checkbox) o sobrescribir una de las seleccionadas escribiendo su nombre como destino.

---

## 🧮 D. Reglas & Operaciones

Lógica condicional, ordenamiento, agregación y cruce de datasets.

18. **Filtrar Filas:** 
    Mantiene solo las filas que cumplen una condición lógica en una columna específica. Operadores: igual a (`==`), diferente de (`!=`), mayor que (`>`), menor que (`<`), contiene texto (`contiene`), no contiene texto (`no contiene`).
19. **Ordenar:** 
    Ordena todo el dataset basándose en los valores de una columna seleccionada, ya sea en orden Ascendente (A-Z, 0-9) o Descendente (Z-A, 9-0).
20. **Group By (Agregación):** 
    Agrupa las filas por los valores únicos de una columna ("agrupar por") y resume otra columna numérica con una función: suma (`sum`), media (`mean`), conteo (`count`), mínimo (`min`), máximo (`max`), mediana (`median`) o valores únicos (`nunique`).
21. **Join / Merge (Cruzar datasets):** 
    Carga un segundo dataset (el "frame derecho") desde el propio modal — con un archivo tuyo o con uno de los demos — y cruza ambos por una columna de clave. Tipos de cruce: `inner` (solo coincidencias), `left` (todas las filas izquierdas), `right` (todas las derechas) y `outer` (unión). Las claves sin coincidir quedan con valores vacíos. Puedes deshacer como cualquier otro paso.
22. **Columna Calculada:** 
    Crea (o sobrescribe) una columna a partir de una expresión pandas, por ejemplo `round(Precio * 1.21, 2)`. Puedes usar nombres de columna, operadores (`+`, `-`, `*`, `/`, `**`, `%`), comparaciones y las funciones permitidas: `abs`, `round`, `len`, `min`, `max`, `sum`, `int`, `float`, `str`, `bool`, `log`, `log10`, `exp`, `sqrt`, `floor`, `ceil`, `sign`, `where(cond, a, b)` y `col('Nombre con espacios')` para referenciar columnas cuyo nombre tiene espacios o símbolos. Un sandbox de seguridad valida la expresión antes de ejecutarla: bloquea acceso a atributos (`.`), imports, lambdas y comprensiones, así que nunca se ejecuta código externo — si la expresión no está permitida, verás un mensaje explicando por qué. Nota: para condiciones por fila usa `where(cond, valor_si_true, valor_si_false)` (el ternario de Python no funciona con columnas).
23. **Detectar Outliers:** 
    Analiza columnas numéricas (INT/FLOAT) y crea por cada una una columna de marca `columna_outlier` (TRUE/FALSE) con dos métodos: **Z-Score** marca si `|x − media| / desviación > umbral` (por defecto 2.5, desviación de población) e **IQR** marca si el valor cae fuera de `Q1 − k·IQR … Q3 + k·IQR` (k por defecto 1.5). Los valores nulos producen marca nula y las columnas constantes quedan todas en FALSE. La operación **solo marca, no elimina filas**: filtra después con *Filtrar filas* (por ejemplo `columna_outlier == TRUE`) o *Eliminar filas*. Nota: con pocos datos (menos de ~8 filas) el Z-Score es poco significativo; en columnas muy asimétricas prefiere IQR.
24. **Muestreo (Sampling):** 
    Reduce el dataset a una muestra, con cuatro modos: **head** (primeras N filas), **tail** (últimas N filas), **random** (N filas aleatorias) y **stratified** (N filas *por cada valor* de una columna, por ejemplo 3 empleados de cada Departamento — los nulos cuentan como un estrato más y un estrato con menos de N filas se toma completo). Si N supera el número de filas disponible se recorta al máximo. El modo aleatorio usa una **semilla fija (42)**: la receta `.catflip.json` y el script exportado reproducen exactamente las mismas filas, así que tus resultados son auditables y repetibles. El botón **Muestreo** (icono de flechas cruzadas) está en el panel izquierdo, sección *Limpieza & Filtrado*, junto a *Eliminar filas*.

---

## 🔄 Navegación y Exportación

* **Auto-mapeo de tipos al cargar (heurística de esquema completo):** Cuando cargas un dataset, Cat_flip analiza cada columna de texto y sugiere el tipo óptimo entre los tres que la operación *Cambiar Tipo de Dato* sabe aplicar: **fecha** (formato ISO `2026-01-05` con hora opcional, `31/12/2026`, `31.12.2026` o `Jan 5, 2026`), **entero** (`100`, `-5`) y **decimal** (`19.90`). Si ≥90% de los valores no nulos de una columna se convierte sin coercionar a nulo, aparece una **barra de sugerencia** sobre el Data Grid con una píldora por columna (`Fecha → DATE 100%`, `Cantidad → INT 90%`, `Precio → FLOAT 90%`). Dos acciones:
  - **Aplicar** — convierte todas las columnas sugeridas a su tipo. Cada conversión se registra como un paso de tipo *Cambiar Tipo de Dato* en la receta, así que puedes deshacerla normalmente con **Undo**.
  - **Descartar** — oculta la sugerencia sin tocar los datos.
  Solo se sugiere lo que pandas podría convertir de verdad (≥90% de valores convertibles; la regla de fecha exige además que parseen sin producir `NaT`, y las columnas que pandas ya tipó como numérico/booleano al leer el archivo no se tocan). Por ejemplo, `5 ene 2026` (mes en español) no genera sugerencia porque pandas no lo convertirá — transforma esos valores a ISO (`2026-01-05`) y usa la operación *Cambiar Tipo de Dato* manualmente.
* **Codificación autodetectada al cargar:** Si tu CSV no está en UTF-8 (por ejemplo, guardado en latin-1 o cp1252 desde Excel en español), Cat_flip detecta la codificación, la carga correctamente y lo anuncia con un aviso (`Codificación detectada: cp1252`). El código generado y el script exportado incluyen `encoding='cp1252'` para que la carga se reproduzca igual fuera de la app. Codificaciones europeas del grupo windows-125x se interpretan como cp1252 (acentos españoles correctos); si prefieres control total, guarda tus archivos en UTF-8.
* **Data Grid virtualizado (rendimiento):** El Data Grid renderiza en pantalla solo las filas visibles + un búfer de 10 por lado, así que datasets de **5.000 filas** (el tope del preview) navegan con scroll fluido — el grid usa una fracción de los nodos DOM de antes. El scroll se conserva al aplicar operaciones y al deshacer; el aviso "mostrando primeras filas" indica cuando el dataset completo es mayor que el preview.
* **Separador autodetectado al cargar:** Los archivos de texto aceptan coma (`,`), punto y coma (`;`), tabulador (`\t`, formato TSV) y barra vertical (`|`) — la detección usa el sniffer de la librería estándar de Python, así que respeta las comillas (un `;` dentro de `"..."` no cuenta) y el script exportado incluye el `sep` correcto. Extensión `.tsv` admitida además de `.csv`. Si tu archivo es de una sola columna, se asume separador coma por defecto.
* **Detección de PII al cargar:** Al subir un archivo, Cat_flip analiza las columnas de texto y, si ≥90% de sus valores no nulos casan un patrón de datos personales (email, teléfono, identificador/tarjeta), aparece una **barra naranja** con una píldora por columna (`Email → EMAIL 100%`) sobre el Data Grid — **no toca tus datos** hasta que decidas. Dos acciones:
  - **Enmascarar** — aplica la operación *Enmascarar PII* sobre cada columna señalada (relleno `****`): un paso de receta por columna, visible en el pipeline y reversible con **Deshacer**.
  - **Descartar** — oculta la sugerencia sin tocar los datos.
  Los patrones son los mismos que usa *Enmascarar PII*: el escaneo marca exactamente lo que se enmascararía. Nota: las columnas que pandas tipó como numéricas al leer el archivo no se analizan (un número solo no es PII — si tu tarjeta vino como número, conviértela a texto con *Tipo dato* antes de enmascarar).
* **Deshacer / Rehacer (Undo / Redo):** *Deshacer* revierte la última operación aplicada, restaurando el dataset al paso anterior de tu receta. *Rehacer* vuelve a aplicar el paso que acabas de deshacer (hasta donde llegaste).  Atajos de teclado: `Ctrl+Z` deshace, `Ctrl+Shift+Z` (o `Ctrl+Y`) rehace. La pila de rehacer se vacía en cuanto aplicas una operación nueva, cargas otro archivo o aplicas una receta — solo puedes rehacer lo último que deshiciste.
* **Diff por paso (¿Qué cambió?):** Cada tarjeta de paso del panel derecho muestra un icono de comparación al pasar el cursor. Al hacer clic abre un modal con el resumen de ese paso: forma antes→después, filas/columnas añadidas o quitadas, los deltas de tipo/nulos/únicos por columna y una **muestra de hasta 20 celdas realmente cambiadas** con su valor antes (tachado) y después. La comparación se hace **por etiqueta de fila** (las operaciones de filtrado conservan el índice original), así que un paso que solo reordena filas no cuenta como cambio de valores — verás «reordenadas» en su lugar. El diff es de **solo lectura**: consultarlos nunca modifica tu dataset. Nota: si un paso reindexa por completo (p. ej. *Group By*), las filas dejan de ser comparables y el modal muestra solo el resumen de columnas.
* **Estadísticas (Diagnóstico):** En la pestaña central, puedes ver perfiles de cada columna (conteo de nulos, valores únicos, mínimos, máximos). Se actualiza tras cada transformación.
* **Barra de Calidad de Datos (Data Quality Bar):** Micro-barra de 3px visible en la parte inferior de cada cabecera del Data Grid. Muestra visualmente la proporción de datos válidos (no nulos) frente a nulos en cada columna, con color semántico:
  - 🟢 **Verde** — calidad ≥ 90% (columna casi completa)
  - 🟡 **Amarillo** — calidad entre 60% y 89% (atención recomendada)
  - 🔴 **Rojo** — calidad < 60% (columna con muchos nulos)
  
  Al pasar el cursor sobre la cabecera, el tooltip muestra el conteo exacto de nulos y el porcentaje de datos válidos (ej. `Precio — 12 nulos (88.5% válido)`). Las columnas sin ningún nulo no muestran fondo de barra para no distraer visualmente.
* **Nulos visibles en el Data Grid:** Las celdas con un nulo real de pandas (NaN) muestran la etiqueta `null` en cursiva y color tenue, distinguiéndose así de un string vacío legítimo. Eliminar Nulos y la barra de calidad operan sobre exactamente los mismos nulos.
* **Visor de Código:** Revisa el script de Python en tiempo real generado por tus acciones visuales.
* **Exportar datos:** Desde el panel derecho, descarga tus datos limpios en **CSV, Excel XLSX, Parquet, JSON o SQL**:
  - **Parquet** — formato columnar de Apache: comprime y preserva los tipos (fechas, nulos, booleanos) sin conversiones, y se lee 5-10× más rápido que CSV en pipelines posteriores (pandas `read_parquet`).
  - **JSON** — *JSON Records*: un array de objetos (una fila = un objeto), nulos como `null` y fechas en ISO legible; se recupera con `pd.read_json(orient='records')` sin flags extra. Acentos y ñ salen intactos (sin `\u00f1`).
  - **SQL** — script **DDL + INSERT** portable (PostgreSQL y SQLite): `CREATE TABLE` con tipos derivados del tipo real de cada columna (TEXT, BIGINT, DOUBLE PRECISION, BOOLEAN, TIMESTAMP), `INSERT` multi-fila en lotes de 100 filas, comillas escapadas (`O'Connor` → `'O''Connor'`), nulos e infinidades como `NULL` y el nombre de la tabla tomado de tu nombre de archivo (normalizado a minúsculas y sin símbolos). El script se ejecuta tal cual (`psql`, `sqlite3` o `executescript`).
  Los botones **JSON** y **SQL** están junto a CSV/Excel y se habilitan al cargar un archivo.
* **Exportar / Cargar Receta (`.catrecipe`):** El botón **Exportar receta .catrecipe** (panel derecho) descarga todos los pasos de tu pipeline como un archivo portable con el formato `{version: 1, app: "catflip", steps: [{op, params}]}` — no guarda código Python, sino los parámetros estructurados, así que el código se regenera al reproducir. **Cargar receta** selecciona ese archivo (también acepta `.json` y `.catflip.json`) y abre el **ExecutePipelineModal**: en lugar de aplicarse en silencio, la ejecución ocurre ante tus ojos. Además, arrastrar un `.catrecipe` directamente sobre el Data Grid abre el mismo modal — no intenta subirlo como dataset. El modal muestra una consola tipo terminal (`$ catflip run …`), una **barra de progreso 0-100%** y los logs reales de la reproducción paso a paso (operación, parámetros, filas×columnas antes→después y milisegundos), más la forma de entrada y salida del dataset. La app primero ejecuta la receta en modo *dry-run* sobre una copia (el dataset **no** se toca) y solo **la aplica de verdad cuando la barra llega al 100%**. Puedes **Cancelar** (o pulsar `Escape`) a mitad de animación: el modal se cierra sin aplicar nada — jamás queda estado parcial. La reproducción sigue siendo **atómica**: si algún paso falla (columna ausente, op desconocida, receta de otra versión) la consola muestra el mensaje exacto que cita el paso (`✘ El paso 1 usa una operación desconocida: 'op_fantasma'.`), el estado pasa a *Sin cambios* y **no se aplica nada**. Si todo pasa, la receta entra como pasos normales: cada paso queda en la receta, en el Linaje y se deshace individualmente con **Deshacer paso**. Nota: la receta se aplica sobre el dataset cargado — sus columnas deben existir (o poder crearse) en el archivo actual; un paso `merge` necesita el frame derecho cargado en la sesión.
* **Receta desde CSV… (propuesta automática):** El botón **Receta desde CSV…** (panel derecho) analiza un `.csv`/`.tsv` que elijas y **propone** una receta de limpieza — nunca la aplica sola. La heurística es determinista y prudente: (1) *Quitar espacios* si alguna celda tiene espacios sobrantes; (2) *Eliminar filas con nulos* si hay celdas vacías; (3) *Cambio de tipo* a entero o decimal **solo si todas las celdas no vacías** de la columna casan el patrón (nunca propone fechas); (4) *Quitar duplicados* **siempre al final**. Máximo 4 pasos. Un modal lista los pasos propuestos (con la op y sus parámetros) y los avisos correspondientes (p. ej. «2 fila(s) duplicada(s) → se eliminarán»); la analítica se hace sobre las primeras 5.000 filas y se avisa si el archivo es mayor. Solo al pulsar **Aplicar receta** pasa por el **ExecutePipelineModal** (dry-run + barra de progreso + aplicar al 100%), así que puedes cancelar sin consecuencias y cada paso queda deshacible. Útil para «limpiar rápido» un CSV nuevo antes de decidir a mano.
* **Exportar receta como script Python (`.py`):** El botón **Exportar receta .py** descarga la receta del pipeline como un script Python autocontenido y **portable**: la carga lee de `sys.argv[1]` (entrada, por defecto un nombre relativo — nunca rutas absolutas de tu máquina) y el resultado se guarda en `sys.argv[2]` (`python pipeline_catflip.py datos.xlsx limpio.xlsx`). Cada paso va numerado con su nombre legible (`# 1. Cambio de mayúsculas/minúsculas (change_case)`) y el código de cada paso es **exactamente** el que ejecutó la app (mismo generador que la ventana *Visor de Código*), incluida la carga del frame derecho en pasos `merge`. La validación es la misma que al aplicar la receta: un `op_history` corrupto devuelve el mismo mensaje de error que *Cargar receta*, y un `merge` sin frame derecho avisa citando el paso. Nota: el script generado fija la semilla de *Muestreo* y demás ops deterministas, así que reproducirlo fuera de Cat_flip da el mismo dataset.
* **Exportar pipeline como script Python (`.py` — pipeline completo):** Descarga todo el pipeline acumulado (incluida la carga original) como un archivo Python ejecutable e independiente. El script incluye el código de cada transformación aplicada en orden, listo para ejecutarse con `python nombre_script.py`, integrarse en un flujo de automatización (cron, Airflow) o reproducirse en cualquier entorno con pandas instalado. El botón aparece en el panel derecho, separado de las opciones de exportación de datos, identificado con color violeta. Diferencia con *Exportar receta .py*: este usa el `code_log` completo (carga incluida con el nombre original del archivo), mientras que *Exportar receta .py* genera un script portátil con argumentos de línea de comandos.

  **Ejemplo de script generado:**
  ```python
  # ============================================================
  # Script generado por Cat_flip — Studio ETL
  # https://github.com/lpardo303/Cat_flip
  # ============================================================

  import pandas as pd

  # Cargar archivo
  df = pd.read_csv('ventas.csv', sep=',')

  # unpivot
  df = df.melt(
      id_vars=['Region', 'Producto'],
      var_name='Mes',
      value_name='Valor'
  )  # sort
  df = df.sort_values(by='Valor', ascending=False)
  ```

---

## 💻 E. Modo CLI — ejecutar recetas sin navegador

Las recetas `.catflip.json` también se ejecutan desde la terminal, sin abrir la app — misma reproducción atómica que el botón *Cargar receta* (validación completa de la receta antes de ejecutar; si un paso falla sale con código 1 citando el paso y **no se escribe nada**):

```bash
python cli.py run receta.catflip.json --input datos.csv --output limpio.csv
```

**Flags:**

* `--input` / `-i` *(obligatorio)* — dataset de entrada: `.csv`, `.tsv`, `.xlsx` o `.xls`. La autodetección de separador (`,` `;` `\t` `|`) y de codificación (UTF-8, cp1252…) es la misma que en la app.
* `--output` / `-o` — archivo de salida por extensión: `.csv`, `.tsv`, `.xlsx` o `.parquet`. Sin esta flag solo valida la receta (modo verificación, ideal para CI). La escritura es atómica (temporal + rename): o el archivo completo o nada.
* `--right` — frame derecho para recetas con paso `merge`; sin él, el CLI avisa citando el paso antes de cargar nada.
* `--sheet` — hoja de un `.xlsx` de entrada (nombre o posición; default 0).
* `--show-code` — imprime el código pandas generado por cada paso.

**Códigos de salida:** `0` éxito · `1` error de receta o de datos (mensaje citando el paso exacto en stderr) · `2` uso incorrecto de la flag.

**Ejemplo con informe:**

```text
$ python cli.py run receta.catflip.json -i datos.csv -o limpio.csv
Entrada: datos.csv → 100×6
[1/2] change_case 100×6 → 100×6
[2/2] trim 100×6 → 100×6
Salida: limpio.csv (100×6)
```
