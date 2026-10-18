# 🐈 Cat_flip - Manual de Usuario

Bienvenido a **Cat_flip - Studio ETL**, tu plataforma local y ligera para la limpieza, transformación y preparación de datos. Diseñada como una alternativa rápida a herramientas pesadas, Cat_flip te permite construir pipelines de datos visualmente mientras genera código Python por debajo.

Este manual detalla las 20 operaciones de transformación disponibles en la "Caja de Transformaciones" (Panel Izquierdo) de la interfaz.

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
    Modifica la capitalización de toda una columna de texto. Opciones disponibles: minúsculas (`lower`), MAYÚSCULAS (`upper`), Tipo Título (`title`), o Primera letra mayúscula (`capitalize`). *(Nota: Las opciones title y capitalize cubren la operación #24).*
12. **Reemplazar Valores:** 
    Busca una palabra o fragmento de texto específico dentro de una columna y lo sustituye por otro. 
13. **Renombrar Columna:** 
    Cambia el nombre de la cabecera de una columna seleccionada.
14. **Eliminar Columna:** 
    Borra completamente la columna seleccionada de tu dataset.
15. **Cambiar Tipo de Dato:** 
    Fuerza a una columna a interpretarse como un tipo de dato específico: Texto (`str`), Número Entero (`int`), Número Decimal (`float`) o Fecha y Hora (`datetime`).

---

## 🧮 D. Reglas & Operaciones

Lógica condicional, ordenamiento, agregación y cruce de datasets.

16. **Filtrar Filas:** 
    Mantiene solo las filas que cumplen una condición lógica en una columna específica. Operadores: igual a (`==`), diferente de (`!=`), mayor que (`>`), menor que (`<`), contiene texto (`contiene`), no contiene texto (`no contiene`).
17. **Ordenar:** 
    Ordena todo el dataset basándose en los valores de una columna seleccionada, ya sea en orden Ascendente (A-Z, 0-9) o Descendente (Z-A, 9-0).
18. **Group By (Agregación):** 
    Agrupa las filas por los valores únicos de una columna ("agrupar por") y resume otra columna numérica con una función: suma (`sum`), media (`mean`), conteo (`count`), mínimo (`min`), máximo (`max`), mediana (`median`) o valores únicos (`nunique`).
19. **Join / Merge (Cruzar datasets):** 
    Carga un segundo dataset (el "frame derecho") desde el propio modal — con un archivo tuyo o con uno de los demos — y cruza ambos por una columna de clave. Tipos de cruce: `inner` (solo coincidencias), `left` (todas las filas izquierdas), `right` (todas las derechas) y `outer` (unión). Las claves sin coincidir quedan con valores vacíos. Puedes deshacer como cualquier otro paso.
20. **Columna Calculada:** 
    Crea (o sobrescribe) una columna a partir de una expresión pandas, por ejemplo `round(Precio * 1.21, 2)`. Puedes usar nombres de columna, operadores (`+`, `-`, `*`, `/`, `**`, `%`), comparaciones y las funciones permitidas: `abs`, `round`, `len`, `min`, `max`, `sum`, `int`, `float`, `str`, `bool`, `log`, `log10`, `exp`, `sqrt`, `floor`, `ceil`, `sign`, `where(cond, a, b)` y `col('Nombre con espacios')` para referenciar columnas cuyo nombre tiene espacios o símbolos. Un sandbox de seguridad valida la expresión antes de ejecutarla: bloquea acceso a atributos (`.`), imports, lambdas y comprensiones, así que nunca se ejecuta código externo — si la expresión no está permitida, verás un mensaje explicando por qué. Nota: para condiciones por fila usa `where(cond, valor_si_true, valor_si_false)` (el ternario de Python no funciona con columnas).

---

## 🔄 Navegación y Exportación

* **Auto-mapeo de tipos al cargar (heurística de esquema completo):** Cuando cargas un dataset, Cat_flip analiza cada columna de texto y sugiere el tipo óptimo entre los tres que la operación *Cambiar Tipo de Dato* sabe aplicar: **fecha** (formato ISO `2026-01-05` con hora opcional, `31/12/2026`, `31.12.2026` o `Jan 5, 2026`), **entero** (`100`, `-5`) y **decimal** (`19.90`). Si ≥90% de los valores no nulos de una columna se convierte sin coercionar a nulo, aparece una **barra de sugerencia** sobre el Data Grid con una píldora por columna (`Fecha → DATE 100%`, `Cantidad → INT 90%`, `Precio → FLOAT 90%`). Dos acciones:
  - **Aplicar** — convierte todas las columnas sugeridas a su tipo. Cada conversión se registra como un paso de tipo *Cambiar Tipo de Dato* en la receta, así que puedes deshacerla normalmente con **Undo**.
  - **Descartar** — oculta la sugerencia sin tocar los datos.
  Solo se sugiere lo que pandas podría convertir de verdad (≥90% de valores convertibles; la regla de fecha exige además que parseen sin producir `NaT`, y las columnas que pandas ya tipó como numérico/booleano al leer el archivo no se tocan). Por ejemplo, `5 ene 2026` (mes en español) no genera sugerencia porque pandas no lo convertirá — transforma esos valores a ISO (`2026-01-05`) y usa la operación *Cambiar Tipo de Dato* manualmente.
* **Deshacer (Undo):** Revierte la última operación aplicada, restaurando el dataset al paso anterior de tu receta.
* **Estadísticas (Diagnóstico):** En la pestaña central, puedes ver perfiles de cada columna (conteo de nulos, valores únicos, mínimos, máximos). Se actualiza tras cada transformación.
* **Barra de Calidad de Datos (Data Quality Bar):** Micro-barra de 3px visible en la parte inferior de cada cabecera del Data Grid. Muestra visualmente la proporción de datos válidos (no nulos) frente a nulos en cada columna, con color semántico:
  - 🟢 **Verde** — calidad ≥ 90% (columna casi completa)
  - 🟡 **Amarillo** — calidad entre 60% y 89% (atención recomendada)
  - 🔴 **Rojo** — calidad < 60% (columna con muchos nulos)
  
  Al pasar el cursor sobre la cabecera, el tooltip muestra el conteo exacto de nulos y el porcentaje de datos válidos (ej. `Precio — 12 nulos (88.5% válido)`). Las columnas sin ningún nulo no muestran fondo de barra para no distraer visualmente.
* **Nulos visibles en el Data Grid:** Las celdas con un nulo real de pandas (NaN) muestran la etiqueta `null` en cursiva y color tenue, distinguiéndose así de un string vacío legítimo. Eliminar Nulos y la barra de calidad operan sobre exactamente los mismos nulos.
* **Visor de Código:** Revisa el script de Python en tiempo real generado por tus acciones visuales.
* **Exportar datos:** Desde el panel derecho, descarga tus datos limpios en formato CSV o Excel XLSX.
* **Exportar pipeline como script Python (`.py`):** Descarga todo el pipeline acumulado como un archivo Python ejecutable e independiente. El script incluye el código de cada transformación aplicada en orden, listo para ejecutarse con `python nombre_script.py`, integrarse en un flujo de automatización (cron, Airflow) o reproducirse en cualquier entorno con pandas instalado. El botón aparece en el panel derecho, separado de las opciones de exportación de datos, identificado con color violeta.

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
  )

  # sort
  df = df.sort_values(by='Valor', ascending=False)
  ```