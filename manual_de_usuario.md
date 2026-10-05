# 🐈 Cat_flip - Manual de Usuario

Bienvenido a **Cat_flip - Studio ETL**, tu plataforma local y ligera para la limpieza, transformación y preparación de datos. Diseñada como una alternativa rápida a herramientas pesadas, Cat_flip te permite construir pipelines de datos visualmente mientras genera código Python por debajo.

Este manual detalla las 25 operaciones de transformación disponibles en la "Caja de Transformaciones" (Panel Izquierdo) de la interfaz.

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
   Limpia espacios en blanco accidentales al principio o al final del texto dentro de las celdas (ej. `"  texto "` se convierte en `"texto"`).
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
    Borra completamente una o varias columnas seleccionadas de tu dataset.
15. **Cambiar Tipo de Dato:** 
    Fuerza a una columna a interpretarse como un tipo de dato específico: Texto (`str`), Número Entero (`int`), Número Decimal (`float`) o Fecha y Hora (`datetime`).

---

## 🧮 D. Reglas & Operaciones

Lógica condicional y ordenamiento.

16. **Filtrar Filas:** 
    Mantiene solo las filas que cumplen una condición lógica en una columna específica. Operadores: igual a (`==`), diferente de (`!=`), mayor que (`>`), menor que (`<`), contiene texto (`contiene`), no contiene texto (`no contiene`).
17. **Ordenar:** 
    Ordena todo el dataset basándose en los valores de una columna seleccionada, ya sea en orden Ascendente (A-Z, 0-9) o Descendente (Z-A, 9-0).

---

## 🔄 Navegación y Exportación

* **Deshacer (Undo):** Revierte la última operación aplicada, restaurando el dataset al paso anterior de tu receta.
* **Estadísticas (Diagnóstico):** En la pestaña central, puedes ver perfiles de cada columna (conteo de nulos, valores únicos, mínimos, máximos). Se actualiza tras cada transformación.
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