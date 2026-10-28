from flask import Flask, render_template, request, jsonify, send_file, has_request_context
import pandas as pd
import csv
import io
import os
import re
import json
import base64
import time
import urllib.error
import urllib.request
from functools import wraps

# Open Core: gating de features premium (la licencia decide qué sirve
# /premium/status y /premium/themes/<id>.css — sin ella, 404/lista vacía)
import premium as premium_pkg

# Conectores reales (Open Core): lógica pura + driver opcional
# (psycopg / boto3 / google-cloud-bigquery)
from connectors import (
    ConnectorError,
    clean_bq_params,
    clean_conn_params,
    clean_s3_params,
    export_to_bigquery,
    export_to_postgres,
    export_to_s3,
    test_bq_connection,
    test_connection,
    test_s3_connection,
)

from operations import (
    OPS,
    NUL_REGEX,
    detect_pii_columns,
    detect_type_suggestions,
    normalize_read_nulls,
    validate_rules,
    validate_schema,
)

app = Flask(__name__)

# Almacenamiento temporal en memoria
current_df = None
history = []  # Para undo
code_log = []  # Log de código generado
op_history = []  # Pasos estructurados {op, params} para el linaje (F3.3)
# Pila de rehacer: cada entrada es (snapshot_df, code_frag, op_step) popeados
# por /undo. Se vacía en cualquier avance del pipeline (op nueva, upload,
# receta) — semántica estándar de redo: solo se rehace lo último deshecho.
redo_history = []
# Reglas de validación de esquema — SOLO anotan: no transforman el df y no
# entran en la receta ni en el script. Se limpian al cargar un archivo
# nuevo; las violaciones se recalculan on-demand contra el df vigente.
schema_rules = []
# Tiempo por paso (barra de benchmark del roadmap): paralelo a
# `op_history` — se trunca en cada avance y se rebana con zip al leer, así
# un undo deja el valor disponible para que /redo lo recupere idéntico y
# una op nueva descarta la cola de rehacer. Nunca entra en la receta ni
# en el linaje.
step_ms = []

# Frame derecho para el cruce Join/Merge (op #19): fuente independiente del
# pipeline (no participa en undo) más su expresión de carga para el script.
right_df = None
right_name = ""
right_code = ""

def df_to_json(df, max_rows=5000):
    """Convierte DataFrame a JSON seguro para el frontend.

    `max_rows=5000` (antes 500): el grid virtualiza el render (F3.6), así
    que el preview puede ampliarse sin coste de DOM. `truncated` marca si
    el dataset tiene MÁS filas que este tope.
    """
    preview = df.head(max_rows)

    # Clasificar cada columna en una categoría semántica para los badges del UI
    def classify_dtype(series):
        dt = series.dtype
        if pd.api.types.is_bool_dtype(dt):
            return "BOOL"
        if pd.api.types.is_datetime64_any_dtype(dt):
            return "DATE"
        if pd.api.types.is_integer_dtype(dt):
            return "INT"
        if pd.api.types.is_float_dtype(dt):
            return "FLOAT"
        return "STR"

    # Filas con nulos reales como JSON null (Bug 4): el front los pinta con
    # la etiqueta "null" tenue. Antes fillna("") los ocultaba como celda
    # vacía indistinguible de un string vacío legítimo.
    rows = [[None if pd.isna(v) else str(v) for v in row]
            for row in preview.itertuples(index=False, name=None)]

    return {
        "columns": list(df.columns),
        "dtypes": {col: classify_dtype(df[col]) for col in df.columns},
        "nulls": {col: int(df[col].isna().sum()) for col in df.columns},
        "total_rows": len(df),
        "data": rows,
        "shape": [len(df), len(df.columns)],
        "truncated": len(df) > max_rows
    }

@app.route("/")
def index():
    return render_template("index.html")

# Separadores candidatos de CSV. El orden es el desempate de la regla de
# consistencia ("," gana a ";" — conserva el comportamiento histórico).
_DELIM_CANDIDATES = ",;\t|"


def _detect_delimiter(text):
    """Detecta el separador de un CSV: coma, punto y coma, tab o pipe.

    1) `csv.Sniffer` con lista blanca de candidatos: respeta las comillas
       (un ';' o ',' dentro de "..." no cuenta como separador).
    2) Fallback si el Sniffer no puede decidir (pocas líneas, filas
       irregulares): regla de consistencia — candidato con conteo >0 y el
       MISMO número de apariciones en ≥60% de las líneas no vacías; gana la
       mejor consistencia (desempate por orden: ',' antes que ';').
    3) Último recurso: máximo conteo total (generaliza la regla histórica
       conteo(',') vs conteo(';')). Sin apariciones → ',' (default).
    """
    sample = text[:65536]
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIM_CANDIDATES).delimiter
    except csv.Error:
        pass
    lines = [ln for ln in sample.splitlines() if ln.strip()]
    if len(lines) < 2:
        return ","
    scores = {}
    for cand in _DELIM_CANDIDATES:
        counts = [ln.count(cand) for ln in lines]
        top = max(counts)
        scores[cand] = (sum(1 for c in counts if c == top) / len(lines)
                        if top else 0.0)
    qualified = [c for c in _DELIM_CANDIDATES if scores[c] >= 0.6]
    if qualified:
        # max() con empate se queda con el primero → orden ',':\t|
        return max(qualified, key=lambda c: scores[c])
    totals = {c: sum(ln.count(c) for ln in lines) for c in _DELIM_CANDIDATES}
    best_c, best_n = max(totals.items(), key=lambda kv: kv[1])
    return best_c if best_n else ","


# Cola que encadena la expresión de carga con la normalización de nulos
# (Bug 4 al cargar): el código generado y el script exportado deben
# reproducir el MISMO df que quedó en memoria, celda de solo espacios incluida.
_NULLS_TAIL = (
    f".replace(r'{NUL_REGEX}', float('nan'), regex=True)"
    "  # vacíos/solo-espacios → nulo real (Bug 4)"
)


def read_table(file, sheet=None):
    """Lee un CSV/XLSX/XLS subido y devuelve (df, expresión pandas, encoding).

    La expresión es el RHS listo para el código generado: en /upload se usa
    como `df = <expr>` y en el cruce como `df_right = <expr>`. El formato lo
    valida el endpoint que llama; aquí se autodetecta el separador del CSV
    (`,`, `;`, `\t`, `|` vía _detect_delimiter), la codificación (UTF-8 si el
    decode pasa; si no, charset-normalizer) o se lee la hoja de Excel.

    `encoding` es la codificación no-utf8 detectada (ej. 'cp1252') o None.
    El script exportado la incluye para reproducir la misma carga. Fallback:
    latin-1 (nunca lanza UnicodeDecodeError) si la detección no sirve.

    `sheet`: hoja de Excel. None (default) = comportamiento histórico:
    se lee `request.form['sheet']` si hay contexto Flask; sin contexto
    (modo CLI, cli.py) → hoja 0. El CLI puede pasarla explícita (--sheet).
    """
    if file.filename.lower().endswith((".csv", ".tsv")):
        content = file.read()
        file.seek(0)
        encoding = None
        try:
            # utf-8 estricto: si el decode pasa, no se toca nada (caso normal)
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            # CSV en latin-1/cp1252: sin esto, pandas lanza UnicodeDecodeError
            # y el upload entero devolvía 500 con texto mojibake o error críptico.
            from charset_normalizer import detect
            detected = detect(content) or {}
            encoding = (detected.get("encoding") or "latin-1")
            # charset-normalizer confunde las familias windows-125x entre sí
            # (empate real: el byte 0xF1 es 'ñ' en cp1252 y 'ń' en cp1250).
            # Este público escribe en español → se normaliza la familia 125x
            # a cp1252, el mapeo correcto para acentos españoles; el resto de
            # familias (shift_jis, koi8-r…) se respeta tal cual.
            if re.fullmatch(r"(?:windows|cp|ibm)?-?125[0-9]", encoding.lower().replace("_", "-")):
                encoding = "cp1252"
            try:
                text = content.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                encoding = "latin-1"  # decode total: latin-1 mapea todo byte
                text = content.decode("latin-1")
        sep = _detect_delimiter(text)
        if encoding:
            df = normalize_read_nulls(
                pd.read_csv(io.StringIO(text), sep=sep, encoding=encoding)
            )
            return (
                df,
                f"pd.read_csv('{file.filename}', sep={sep!r}, encoding={encoding!r})"
                + _NULLS_TAIL,
                encoding,
            )
        df = normalize_read_nulls(pd.read_csv(io.StringIO(text), sep=sep))
        return df, f"pd.read_csv('{file.filename}', sep={sep!r})" + _NULLS_TAIL, None
    if sheet is None:
        sheet = request.form.get("sheet", 0) if has_request_context() else 0
    df = normalize_read_nulls(
        pd.read_excel(file, sheet_name=int(sheet) if str(sheet).isdigit() else sheet)
    )
    return df, f"pd.read_excel('{file.filename}', sheet_name={repr(sheet)})" + _NULLS_TAIL, None


@app.route("/upload", methods=["POST"])
def upload():
    global current_df, history, code_log, op_history, redo_history, schema_rules, step_ms
    file = request.files["file"]
    filename = file.filename.lower()
    
    try:
        if not filename.endswith((".csv", ".tsv", ".xlsx", ".xls")):
            return jsonify({"error": "Formato no soportado. Usa CSV, TSV, XLSX o XLS."}), 400

        current_df, expr, encoding = read_table(file)
        code = f"df = {expr}"
        
        history = [current_df.copy()]
        code_log = [f"import pandas as pd\n\n# Cargar archivo\n{code}"]
        op_history = []
        redo_history = []  # dataset nuevo → la pila de rehacer no aplica
        schema_rules = []  # las reglas del dataset anterior no aplican
        step_ms = []  # benchmark vacío con el dataset nuevo
        
        return jsonify({
            "success": True,
            "data": df_to_json(current_df),
            "sheets": [],
            "code": code_log[-1],
            "type_suggestions": detect_type_suggestions(current_df),
            "pii_suggestions": detect_pii_columns(current_df),
            # Codificación no-utf8 detectada (ej. cp1252); null en el caso
            # normal → el front solo avisa cuando hubo una.
            "detected_encoding": encoding
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/upload_right", methods=["POST"])
def upload_right():
    """Carga el frame derecho para el cruce Join/Merge (op #19)."""
    global right_df, right_name, right_code
    file = request.files["file"]
    filename = file.filename.lower()

    if not filename.endswith((".csv", ".tsv", ".xlsx", ".xls")):
        return jsonify({"error": "Formato no soportado. Usa CSV, TSV, XLSX o XLS."}), 400

    try:
        right_df, right_code, _ = read_table(file)
        right_name = file.filename
        return jsonify({
            "success": True,
            "name": right_name,
            "data": df_to_json(right_df),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/right_info", methods=["GET"])
def right_info():
    """Estado del frame derecho: pre-pobla el select del modal de Join."""
    if right_df is None:
        return jsonify({"loaded": False})
    return jsonify({
        "loaded": True,
        "name": right_name,
        "columns": list(right_df.columns),
        "shape": [int(right_df.shape[0]), int(right_df.shape[1])],
    })


@app.route("/get_sheets", methods=["POST"])
def get_sheets():
    file = request.files["file"]
    try:
        xl = pd.ExcelFile(file)
        return jsonify({"sheets": xl.sheet_names})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/operation", methods=["POST"])
def operation():
    global current_df, history, code_log, op_history, redo_history, step_ms
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400
    
    data = request.json
    op = data.get("operation")
    params = data.get("params", {})
    
    try:
        # Dispatch por registro (refactor P2): los handlers viven en operations.py
        handler = OPS.get(op)
        if handler is None:
            return jsonify({"error": f"Operación '{op}' no reconocida."}), 400

        # Join/Merge (op #19): inyecta el frame derecho al handler. El
        # DataFrame nunca entra en op_history (rompería la serialización de
        # /lineage); el historial solo guarda el nombre de la fuente.
        handler_params = params
        history_params = params
        if op == "merge":
            if right_df is None:
                return jsonify({"error": "No hay frame derecho cargado. Carga un segundo dataset desde el modal de Join."}), 400
            handler_params = {**(params or {}), "right_df": right_df, "right_code": right_code}
            history_params = {**(params or {}), "right_name": right_name}

        _t0 = time.perf_counter()
        df, code = handler(current_df.copy(), handler_params)
        ms = round((time.perf_counter() - _t0) * 1000, 1)

        # Guardar en historial
        history.append(df.copy())
        op_history.append({"op": op, "params": history_params})
        del step_ms[len(op_history) - 1:]  # descarta la cola de rehacer
        step_ms.append(ms)
        current_df = df
        code_log.append(f"# {op}\n{code}")
        # Avance del pipeline → rama de rehacer descartada (semántica estándar)
        redo_history = []
        
        return jsonify({
            "success": True,
            "data": df_to_json(current_df),
            "code": "\n\n".join(code_log),
            "last_code": code
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/undo", methods=["POST"])
def undo():
    """Revierte el último paso y lo guarda en `redo_history` para /redo.

    Los tres registros (snapshot, fragmento de código, paso estructurado)
    se desapilan juntos: /redo los re-appendea idénticos, así que script,
    receta y linaje vuelven byte a byte al estado previo.
    """
    global current_df, history, code_log, op_history, redo_history
    if len(history) > 1:
        snap = history.pop()
        code_frag = None
        op_step = None
        if len(code_log) > 1:
            code_frag = code_log.pop()
        if len(op_history) > 0:
            op_step = op_history.pop()
        redo_history.append((snap, code_frag, op_step))
        current_df = history[-1].copy()
        return jsonify({
            "success": True,
            "data": df_to_json(current_df),
            "code": "\n\n".join(code_log),
            "can_undo": len(history) > 1,
            "can_redo": True,
        })
    return jsonify({"error": "No hay más pasos para deshacer."}), 400

@app.route("/redo", methods=["POST"])
def redo():
    """Re-aplica el último paso deshecho (LIFO sobre `redo_history`)."""
    global current_df, history, code_log, op_history, redo_history
    if not redo_history:
        return jsonify({"error": "No hay pasos para rehacer."}), 400

    snap, code_frag, op_step = redo_history.pop()
    history.append(snap)
    if code_frag is not None:
        code_log.append(code_frag)
    if op_step is not None:
        op_history.append(op_step)
    current_df = history[-1].copy()
    return jsonify({
        "success": True,
        "data": df_to_json(current_df),
        "code": "\n\n".join(code_log),
        "can_undo": True,
        "can_redo": len(redo_history) > 0,
    })

@app.route("/export_recipe", methods=["POST"])
def export_recipe():
    """Serializa la receta (op_history) a `.catflip.json` descargable.

    Fuente de verdad: `op_history` ({op, params} serializables — los
    DataFrames nunca entran, ver comentario en operation()). Los
    fragments de código se regeneran al reproducir, no se guardan.
    """
    global current_df, op_history
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400
    if not op_history:
        return jsonify({"error": "No hay pasos en la receta para exportar."}), 400

    data = request.get_json(silent=True) or {}
    filename = str(data.get("filename") or "receta_catflip")
    filename = filename.removesuffix(".catflip.json").removesuffix(".json") or "receta_catflip"

    recipe = {
        "version": 1,
        "app": "catflip",
        "steps": [{"op": s["op"], "params": s["params"]} for s in op_history],
    }
    buf = io.BytesIO(json.dumps(recipe, ensure_ascii=False, indent=2).encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"{filename}.catflip.json",
    )

def validate_recipe(data):
    """Valida la estructura de una receta `.catflip.json` y devuelve `steps`.

    Compartida por el endpoint /apply_recipe y el modo CLI (cli.py):
    mensaje idéntico en ambos (los tests de recipe actúan de red de
    paridad). Lanza ValueError en el primer problema — nada se ejecuta
    antes de que toda la receta valide.
    """
    if not isinstance(data, dict):
        raise ValueError("La receta no es JSON válido.")
    if data.get("version") != 1:
        raise ValueError(
            f"Versión de receta no soportada: {data.get('version')!r} (se espera 1)."
        )
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("La receta no contiene pasos válidos ('steps' ausente o vacío).")

    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ValueError(f"El paso {i} no es un objeto válido.")
        sop = step.get("op")
        if not isinstance(sop, str) or sop not in OPS:
            raise ValueError(f"El paso {i} usa una operación desconocida: {sop!r}.")
        if not isinstance(step.get("params", {}), dict):
            raise ValueError(f"El paso {i} ({sop}) tiene 'params' que no son un objeto.")
    return steps


def apply_recipe_df(df, steps, right_df=None, right_code=None, on_step=None):
    """Reproduce `steps` sobre `df` y devuelve (df_final, snaps, codes, applied).

    Ejecuta SOLO sobre copias de trabajo: si un paso falla lanza
    ValueError citando el paso y no devuelve nada parcial (el caller
    decide si hay globals que escribir — en el endpoint, nada se toca;
    en el CLI, no se escribe el archivo de salida).

    `on_step` (opcional, F3.5) se invoca tras cada paso con
    `(i, op, params, shape_in, shape_out, ms)` para alimentar la consola
    del ExecutePipelineModal. Dos reglas:
      * `params` es el de la receta (serializable), nunca `handler_params`,
        que en `merge` arrastra el DataFrame derecho;
      * el tiempo solo se mide si hay callback: el CLI pasa `None` y sigue
        costando exactamente lo que costaba; `/apply_recipe` pasa el suyo
        para alimentar la barra de benchmark.
    """
    df_work = df
    snaps, codes, applied = [], [], []
    for i, step in enumerate(steps, 1):
        sop = step["op"]
        params = step.get("params", {})
        handler = OPS[sop]
        handler_params = params
        if sop == "merge":
            if right_df is None:
                raise ValueError(
                    f"El paso {i} (merge): No hay frame derecho cargado. Carga un segundo dataset desde el modal de Join."
                )
            handler_params = {**params, "right_df": right_df, "right_code": right_code}
        shape_in = df_work.shape
        started = time.perf_counter() if on_step is not None else None
        try:
            df_work, code = handler(df_work.copy(), handler_params)
        except Exception as e:
            # 400 en endpoint / exit 1 en CLI: el problema lo trae la receta
            raise ValueError(f"El paso {i} ({sop}) falló: {e}") from e
        if on_step is not None:
            on_step(
                i, sop, params, shape_in, df_work.shape,
                round((time.perf_counter() - started) * 1000, 1),
            )
        snaps.append(df_work.copy())
        codes.append(f"# {sop}\n{code}")
        applied.append({"op": sop, "params": params})
    return df_work, snaps, codes, applied


# ── F3.4: exportar la receta como script Python reproducible ────────────

# Nombre legible de cada op para el comentario de cabecera del script.
# Claves exactas del registro OPS (operations.py); el fallback en el
# generador es el nombre crudo de la op para que una op futura sin etiqueta
# no rompa la exportación.
_OP_LABELS = {
    "unpivot": "Unpivot",
    "pivot": "Pivot",
    "split_column": "Separar en columnas",
    "split_to_rows": "Separar por filas",
    "set_header": "Fijar cabecera",
    "drop_nulls": "Eliminar filas con nulos",
    "drop_duplicates": "Quitar duplicados",
    "drop_rows": "Eliminar filas",
    "trim": "Quitar espacios",
    "clean_newlines": "Limpiar saltos de línea",
    "change_case": "Cambio de mayúsculas/minúsculas",
    "replace": "Reemplazar valores",
    "rename_column": "Renombrar columna",
    "drop_column": "Eliminar columna",
    "change_type": "Cambio de tipo",
    "regex_mask": "Enmascarar / extraer PII",
    "concatenar_columnas": "Concatenar columnas",
    "filter": "Filtrar filas",
    "sort": "Ordenar",
    "group_by": "Agrupar",
    "merge": "Cruce Join/Merge",
    "calculated_column": "Columna calculada",
    "detectar_outliers": "Detectar outliers",
    "sampling": "Muestreo",
}


def _load_line_with_argv(load_line):
    """Reescribe la carga para leer de `entrada` (argv[1]) en vez del nombre grabado.

    Conserva el resto de argumentos detectados (sep, encoding, sheet_name):
    solo se sustituye el primer parámetro (la ruta) por la variable `entrada`
    del guion, que es lo que hace el script portable entre máquinas.
    """
    return re.sub(
        r"^(df = )pd\.(read_csv|read_excel)\(\s*(?:'[^']*'|\"[^\"]*\")",
        r"\1pd.\2(entrada",
        load_line,
    )


def receta_a_codigo(steps, load_code="df = pd.read_csv(entrada)"):
    """Traduce `steps` (ya validados) a un script pandas autocontenido.

    Reutiliza el MISMO generador de código que /operation y /apply_recipe
    (llama a cada handler de OPS encadenando sobre una copia que arranca
    en el snapshot original), así que cada paso ve el mismo df que vio al
    ejecutarse y lo que sale aquí es exactamente lo que la app ejecutó —
    si un paso genera código, ese código está en el script. Un paso que
    truene al regenerar (p.ej. merge sin frame derecho o params que ya no
    aplican) lanza ValueError citando el paso, con el mismo estilo que
    apply_recipe_df.

    El script NUNCA lleva rutas absolutas: la carga usa un nombre de
    archivo relativo (basename) para que sea portable entre máquinas.
    """
    header = (
        "# ============================================================\n"
        "# Pipeline generado por Cat_flip — Studio ETL\n"
        "# Reproduce la receta exacta que ejecutaste en la app.\n"
        "# Requiere: pandas (+ openpyxl para leer .xlsx)\n"
        "# Uso: python pipeline_catflip.py datos_entrada.xlsx salida_resultante.xlsx\n"
        "# ============================================================\n\n"
        "import sys\n\n"
        "import pandas as pd\n\n"
        "# Argumentos: [entrada] [salida] — valores por defecto solo para pruebas\n"
        "entrada = sys.argv[1] if len(sys.argv) > 1 else 'datos_entrada.xlsx'\n"
        "salida = sys.argv[2] if len(sys.argv) > 2 else 'salida_resultante.xlsx'\n\n"
        "# Cargar archivo (nombre relativo: el script es portable entre máquinas)\n"
        f"{load_code}\n"
    )
    # Cuerpo: un bloque por paso, con el fragmento de código REAL del
    # handler. La cadena arranca en el snapshot del upload (history[0]):
    # ops con comentarios dependientes del estado (drop_duplicates cuenta
    # los duplicados que quitó) solo son paridad exacta si cada paso ve el
    # mismo df que vio al ejecutarse por primera vez.
    df_work = history[0].copy() if history else current_df.copy()
    body = []
    for i, step in enumerate(steps, 1):
        sop = step["op"]
        params = step.get("params", {})
        handler = OPS[sop]
        handler_params = params
        if sop == "merge":
            if right_df is None:
                raise ValueError(
                    f"El paso {i} (merge): No hay frame derecho cargado. Carga un segundo dataset desde el modal de Join."
                )
            handler_params = {**params, "right_df": right_df, "right_code": right_code}
        try:
            df_work, op_code = handler(df_work.copy(), handler_params)
        except Exception as e:
            # 400 citando el paso, mismo estilo que apply_recipe_df
            raise ValueError(f"El paso {i} ({sop}) falló: {e}") from e
        label = _OP_LABELS.get(sop, sop)
        # Sin indentar: cada línea debe ser BYTE A BYTE el mismo código que
        # ejecutó la app (code_log), así la paridad es comprobable en tests
        body.append(f"# {i}. {label} ({sop})\n{op_code}")

    footer = "\n# Guardar resultado\ndf.to_excel(salida, index=False)\nprint(f'Listo: {salida} — {df.shape[0]} filas × {df.shape[1]} columnas')\n"
    return header + "\n\n".join(body) + "\n\n" + footer


@app.route("/recipe_export", methods=["POST"])
def recipe_export():
    """Exporta la receta del pipeline como script Python (F3.4).

    Misma validación estructural que /apply_recipe (validate_recipe →
    mensajes idénticos), pero sin ejecutar nada sobre los datos: solo
    regenera el código de cada op con el MISMO generador que la app.
    /recipe_preview sigue siendo el gate de reproducibilidad; aquí lo que
    se descarga es la traducción a pandas para ejecutar fuera de Cat_flip.
    """
    global current_df
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400
    if not op_history:
        return jsonify({"error": "No hay pasos en la receta para exportar."}), 400

    # La receta sale de op_history (la fuente de verdad del pipeline)
    payload = {
        "version": 1,
        "steps": [{"op": s["op"], "params": s.get("params", {})} for s in op_history],
    }
    try:
        steps = validate_recipe(payload)
        # La carga del guion sale del code_log del upload (mismo detector de
        # sep/encoding/sheet) reescrita para leer de argv[1]
        load_line = "df = pd.read_csv(entrada)"
        if code_log:
            for line in code_log[0].splitlines():
                if line.startswith("df = "):
                    load_line = _load_line_with_argv(line)
                    break
        script = receta_a_codigo(steps, load_code=load_line)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    data = request.get_json(silent=True) or {}
    # download_name viene del cliente → sin separadores de ruta (basename
    # tras normalizar '\\'; vacío → nombre por defecto)
    filename = os.path.basename(
        str(data.get("filename") or "pipeline_catflip").replace("\\", "/")
    ) or "pipeline_catflip"
    buf = io.BytesIO(script.encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        mimetype="text/x-python",
        as_attachment=True,
        download_name=f"{filename}.py",
    )


@app.route("/recipe_preview", methods=["POST"])
def recipe_preview():
    """Dry-run de una receta: ejecuta en copia y devuelve un log por paso.

    Alimenta la consola del ExecutePipelineModal (F3.5). Repite la misma
    validación y los mismos mensajes de error que /apply_recipe porque
    comparte `validate_recipe` y `apply_recipe_df`, pero NUNCA escribe los
    globals: no puede dejar estado parcial. El front solo llama a
    /apply_recipe cuando la barra de progreso llega al 100%.
    """
    global current_df
    if current_df is None:
        return jsonify({"error": "No hay datos cargados. Carga un archivo antes de aplicar la receta."}), 400

    # Misma validación estructural que /apply_recipe → mismo mensaje
    try:
        steps = validate_recipe(request.get_json(silent=True))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    in_rows, in_cols = current_df.shape
    logs = []

    def collect(i, op, params, shape_in, shape_out, ms):
        logs.append({
            "i": i,
            "n": len(steps),
            "op": op,
            "params": params,
            "rows_in": int(shape_in[0]),
            "cols_in": int(shape_in[1]),
            "rows_out": int(shape_out[0]),
            "cols_out": int(shape_out[1]),
            "ms": ms,
        })

    # Mismo ValueError del motor ("El paso N (op) falló: …") → 400
    try:
        df_work, *_ = apply_recipe_df(current_df, steps, right_df, right_code, on_step=collect)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "success": True,
        "steps": len(logs),
        "input_shape": [int(in_rows), int(in_cols)],
        "output_shape": [int(df_work.shape[0]), int(df_work.shape[1])],
        "total_ms": round(sum(l["ms"] for l in logs), 1),
        "logs": logs,
    })


@app.route("/apply_recipe", methods=["POST"])
def apply_recipe():
    """Reproduce una receta `.catflip.json` sobre el dataset actual.

    Atomicidad: TODA la receta se ejecuta sobre copias de trabajo y los
    globals (history/code_log/op_history/current_df) solo se escriben si
    ningún paso falla → imposible dejar estado parcial. Si todo pasa,
    `history` recibe un snapshot por paso: Deshacer revierte paso a paso
    y el linaje muestra cada paso individual, igual que ops manuales.
    """
    global current_df, history, code_log, op_history, redo_history, step_ms
    if current_df is None:
        return jsonify({"error": "No hay datos cargados. Carga un archivo antes de aplicar la receta."}), 400

    # Validación estructural ANTES de ejecutar nada: un paso malformado
    # ni siquiera llega al motor. Errores → 400 (lo trae la receta del
    # cliente, no el servidor).
    # on_step alimenta el benchmark; si la receta truena, `mss` se tira a
    # la basura con todo lo demás (step_ms solo se toca en el commit)
    mss = []

    def _bench(i, op, params, shape_in, shape_out, ms):
        mss.append(ms)

    try:
        steps = validate_recipe(request.get_json(silent=True))
        df_work, snaps, codes, applied = apply_recipe_df(
            current_df, steps, right_df, right_code, on_step=_bench
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Commit único: solo aquí se tocan los globals (ya se validó todo ⇒ no
    # puede quedar estado parcial por un paso a mitad de camino)
    history.extend(snaps)
    op_history.extend(applied)
    del step_ms[len(op_history) - len(applied):]  # descarta la cola de rehacer
    step_ms.extend(mss)
    code_log.extend(codes)
    current_df = df_work
    redo_history = []  # avance del pipeline → rama de rehacer descartada

    return jsonify({
        "success": True,
        "applied": len(applied),
        "steps": applied,
        "data": df_to_json(current_df),
        "code": "\n\n".join(code_log),
        "last_code": codes[-1],
    })

@app.route("/export", methods=["POST"])
def export():
    global current_df
    if current_df is None:
        return jsonify({"error": "No hay datos."}), 400
    
    data = request.json
    fmt = data.get("format", "xlsx")
    filename = data.get("filename", "resultado")
    
    buf = io.BytesIO()
    if fmt == "xlsx":
        current_df.to_excel(buf, index=False, engine="openpyxl")
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    elif fmt == "parquet":
        # pyarrow escribe el buffer directamente; el mágico PAR1 al inicio y
        # al final garantiza un archivo legible por pandas.read_parquet.
        current_df.to_parquet(buf, index=False)
        mimetype = "application/vnd.apache.parquet"
        ext = "parquet"
    elif fmt == "json":
        # JSON Records: array de objetos (una fila = un objeto). Nulos →
        # null y fechas en ISO legible (date_format="iso"; el default de
        # pandas es epoch ms). force_ascii=False conserva ñ/acentos.
        # Round-trip: pd.read_json(orient="records").
        json_text = current_df.to_json(orient="records", date_format="iso", force_ascii=False)
        buf.write(json_text.encode("utf-8"))
        mimetype = "application/json"
        ext = "json"
    elif fmt == "sql":
        # DDL + INSERT: script portable (Postgres/SQLite) generado del
        # dtype real de cada columna — ver df_to_sql_script().
        script = df_to_sql_script(current_df, _sql_ident(filename))
        buf.write(script.encode("utf-8"))
        mimetype = "text/sql"
        ext = "sql"
    else:
        current_df.to_csv(buf, index=False)
        mimetype = "text/csv"
        ext = "csv"
    
    buf.seek(0)
    return send_file(
        buf,
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"{filename}.{ext}"
    )


# ── Export SQL: DDL + INSERT (F3.4 ampliación) ────────────────────────

def _sql_ident(name):
    """Normaliza un nombre a identificador SQL seguro (letras/dígitos/_).

    El nombre del archivo lo pide el usuario (prompt del front) — no puede
    entrar crudo en el DDL. Minúsculas, sin espacios ni símbolos; vacío →
    'tabla'.
    """
    ident = re.sub(r"\W+", "_", str(name).strip()).strip("_").lower()
    return ident or "tabla"


def _sql_type(series):
    """Mapea el dtype de pandas al tipo SQL más cercano (DDL portable)."""
    dt = series.dtype
    if pd.api.types.is_bool_dtype(dt):
        return "BOOLEAN"
    if pd.api.types.is_datetime64_any_dtype(dt):
        return "TIMESTAMP"
    if pd.api.types.is_integer_dtype(dt):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dt):
        return "DOUBLE PRECISION"
    return "TEXT"


def _sql_literal(v):
    """Celda → literal SQL: NULL, TRUE/FALSE, número o texto con '' escapado.

    Escalares numpy → Python (mismo truco que `_diff_value`), fechas a ISO
    con comillas, infinidades → NULL (no son literales SQL estándar) y
    cualquier cosa no escalar → texto entre comillas con su representación.
    """
    try:
        if pd.isna(v):
            return "NULL"
    except (TypeError, ValueError):
        pass  # valores no escalares → str() abajo
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return "NULL"  # nan ya sale arriba; inf/-inf no son SQL estándar
    if isinstance(v, (int, float)):
        return str(v)
    s = v.isoformat(sep=" ") if hasattr(v, "isoformat") else str(v)
    return "'" + s.replace("'", "''") + "'"


def df_to_sql_script(df, table, batch=100):
    """Genera un script DDL + INSERT del DataFrame (F3.4, formato sql).

    Portátil entre Postgres y SQLite: identificadores entrecomillados con
    `"` (y escapados), tipos derivados del dtype real (TEXT/BIGINT/
    DOUBLE PRECISION/BOOLEAN/TIMESTAMP) y `INSERT` multi-fila en lotes de
    `batch` filas. Nulos e infinidades → NULL. Un df de 0 filas genera solo
    el CREATE TABLE. Solo LEE el DataFrame.
    """
    cols = list(df.columns)
    dquote = '"'
    quoted = [dquote + str(c).replace(dquote, dquote * 2) + dquote for c in cols]
    col_list = ", ".join(quoted)

    lines = [
        "-- ============================================================",
        "-- Script generado por Cat_flip — Studio ETL (DDL + INSERT)",
        f"-- Tabla: {table} · {len(df)} fila(s) × {len(cols)} columna(s)",
        "-- Compatible con PostgreSQL y SQLite",
        "-- ============================================================",
        "",
        f'CREATE TABLE "{table}" (',
    ]
    for i, c in enumerate(cols):
        comma = "," if i < len(cols) - 1 else ""
        lines.append(f"    {quoted[i]} {_sql_type(df[c])}{comma}")
    lines.append(");")

    if len(df):
        values_blocks = []
        for start in range(0, len(df), batch):
            chunk = df.iloc[start:start + batch]
            rows = []
            for row in chunk.itertuples(index=False, name=None):
                rows.append("(" + ", ".join(_sql_literal(v) for v in row) + ")")
            values_blocks.append(
                f"INSERT INTO \"{table}\" ({col_list}) VALUES\n" + ",\n".join(rows) + ";"
            )
        lines.append("")
        lines.extend(values_blocks)

    return "\n".join(lines) + "\n"

@app.route("/export_script", methods=["POST"])
def export_script():
    global code_log
    if not code_log:
        return jsonify({"error": "No hay pasos en el pipeline para exportar."}), 400

    data = request.json
    filename = data.get("filename", "pipeline_catflip")

    # Encabezado del script generado
    header = (
        "# ============================================================\n"
        "# Script generado por Cat_flip — Studio ETL\n"
        "# https://github.com/lpardo303/Cat_flip\n"
        "# ============================================================\n\n"
    )
    script_content = header + "\n\n".join(code_log)

    buf = io.BytesIO(script_content.encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        mimetype="text/x-python",
        as_attachment=True,
        download_name=f"{filename}.py"
    )


@app.route("/stats", methods=["GET"])
def stats():
    global current_df
    if current_df is None:
        return jsonify({"error": "No hay datos."}), 400
    
    stats = {}
    for col in current_df.columns:
        series = current_df[col]
        col_stats = {"dtype": str(series.dtype)}

        # Nulos: nunca debería fallar, pero se protege igual.
        try:
            col_stats["nulls"] = int(series.isna().sum())
        except Exception:
            col_stats["nulls"] = None

        # Únicos: en columnas de tipos mixtos/no hasheables se cuenta como texto.
        try:
            col_stats["unique"] = int(series.nunique())
        except TypeError:
            try:
                col_stats["unique"] = int(series.astype(str).nunique())
            except Exception:
                col_stats["unique"] = None

        # Métricas numéricas solo para columnas realmente numéricas.
        # Se normalizan a float y se captura cualquier error por tipos mixtos
        # (evita el TypeError: '<' not supported en columnas object).
        if pd.api.types.is_numeric_dtype(series):
            try:
                if series.isna().all():
                    col_stats["min"] = col_stats["max"] = col_stats["mean"] = None
                else:
                    col_stats["min"] = float(series.min())
                    col_stats["max"] = float(series.max())
                    col_stats["mean"] = round(float(series.mean()), 2)
            except (TypeError, ValueError):
                col_stats["min"] = col_stats["max"] = col_stats["mean"] = None

        # Top-5 valores para columnas categóricas (F3.2 Diagnostics):
        # texto/objeto + bool (pandas trata bool como numérico) + columnas
        # todas nulas (para que el front las muestre vacías, no ausentes).
        if (
            not pd.api.types.is_numeric_dtype(series)
            or pd.api.types.is_bool_dtype(series)
            or (not series.notna().any())
        ):
            try:
                vc = series.dropna().astype(str).value_counts().head(5)
                col_stats["top"] = [[str(v), int(c)] for v, c in vc.items()]
            except Exception:
                col_stats["top"] = []

        stats[col] = col_stats

    # Filas duplicadas exactas (F3.2 — KPI "Duplicados Excluidos")
    try:
        duplicates = int(current_df.duplicated().sum())
    except Exception:
        duplicates = None

    return jsonify({"columns": current_df.columns.tolist(), "stats": stats, "duplicates": duplicates})


@app.route("/lineage", methods=["GET"])
def lineage():
    """Grafo de linaje del pipeline (F3.3): cadena de pasos con su shape.

    Nodo 0 = dataset original (snapshot `history[0]`); nodo i = operación
    `op_history[i-1]` con el shape del snapshot `history[i]`. Los shapes
    salen gratis del historial de undo, así que no se guarda estado extra.
    """
    global current_df
    if current_df is None:
        return jsonify({"error": "No hay datos."}), 400

    nodes = []
    # Nodo fuente: snapshot original
    src_rows, src_cols = (list(history[0].shape) if history else list(current_df.shape))
    nodes.append({"id": 0, "op": "dataset", "params": {}, "rows": int(src_rows), "cols": int(src_cols)})

    # Nodos de operaciones (zip defensivo por si history y op_history difieren)
    for i, step in enumerate(op_history):
        snap_idx = i + 1
        if snap_idx < len(history):
            rows, cols = history[snap_idx].shape
        else:
            rows, cols = current_df.shape
        nodes.append({
            "id": snap_idx,
            "op": step.get("op", "?"),
            "params": step.get("params", {}) or {},
            "rows": int(rows),
            "cols": int(cols),
        })

    edges = [[i, i + 1] for i in range(len(nodes) - 1)]
    return jsonify({"nodes": nodes, "edges": edges})


# ── Diff entre dos estados del pipeline (roadmap "¿Qué cambió este paso?") ─


def _diff_value(v):
    """Celda o etiqueta → valor JSON seguro (null para nulos, str para el resto).

    Mismo criterio visible que `df_to_json` (el grid muestra strings), con
    los escalares numpy convertidos a Python para que `jsonify` no truene.
    """
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass  # valores no escalares (listas, arrays) → str() abajo
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass
    if isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def diff_snapshots(before, after, max_sample=20):
    """Resume qué cambió entre dos snapshots consecutivos de `history[]`.

    Alineación por etiqueta de índice: las operaciones de filtrado/limpieza
    conservan el índice original del upload, así que comparar por posición
    inventaría cambios en filas que solo se movieron de sitio. Con índice no
    único en alguno de los dos frames no hay alineación honesta posible →
    `aligned: false` y solo resumen de columnas (sin diff fila a fila).

    Devuelve: formas, filas/columnas añadidas y quitadas, deltas por columna
    (tipo, nulos, únicos, celdas cambiadas) y hasta `max_sample` celdas
    realmente cambiadas con su valor antes/después. Solo LEE los frames.
    """
    b_rows, b_cols = before.shape
    a_rows, a_cols = after.shape

    b_colset, a_colset = set(before.columns), set(after.columns)
    common_cols = [c for c in before.columns if c in a_colset]
    columns_added = [str(c) for c in after.columns if c not in b_colset]
    columns_removed = [str(c) for c in before.columns if c not in a_colset]

    aligned = bool(before.index.is_unique and after.index.is_unique)
    rows_added = rows_removed = None
    reordered = False
    columns = []
    columns_unchanged = 0
    changed_cells = None
    sample = []
    sample_truncated = False

    if aligned:
        common_idx = before.index.intersection(after.index)
        rows_removed = int(len(before.index.difference(after.index)))
        rows_added = int(len(after.index.difference(before.index)))
        # Mismo conjunto de filas pero en otro orden → solo reordenamiento
        reordered = (rows_added == 0 and rows_removed == 0
                     and not before.index.equals(after.index))
        b_part = before.loc[common_idx, common_cols]
        a_part = after.loc[common_idx, common_cols]
        changed_cells = 0

    for col in common_cols:
        b_s, a_s = before[col], after[col]
        entry = {
            "column": str(col),
            "dtype_before": str(b_s.dtype),
            "dtype_after": str(a_s.dtype),
            "nulls_before": int(b_s.isna().sum()),
            "nulls_after": int(a_s.isna().sum()),
            "unique_before": _nunique_safe(b_s),
            "unique_after": _nunique_safe(a_s),
            "changed": None,
        }
        if aligned:
            bc, ac = b_part[col], a_part[col]
            try:
                same = bc.eq(ac).fillna(False) | (bc.isna() & ac.isna())
            except (TypeError, ValueError):
                # Tipos incompatibles para == (p.ej. datetime vs str):
                # se comparan sus representaciones textuales.
                same = (bc.astype(str).eq(ac.astype(str)).fillna(False)
                        | (bc.isna() & ac.isna()))
            n = int((~same).sum())
            entry["changed"] = n
            changed_cells += n
            if n and len(sample) < max_sample:
                labels = (~same)[~same].index[: max_sample - len(sample)]
                for lab in labels:
                    sample.append({
                        "row": _diff_value(lab),
                        "column": str(col),
                        "before": _diff_value(bc.loc[lab]),
                        "after": _diff_value(ac.loc[lab]),
                    })
        differs = (entry["dtype_before"] != entry["dtype_after"]
                   or entry["nulls_before"] != entry["nulls_after"]
                   or entry["unique_before"] != entry["unique_after"]
                   or (entry["changed"] or 0) > 0)
        if differs:
            columns.append(entry)
        else:
            columns_unchanged += 1

    if changed_cells is not None:
        sample_truncated = changed_cells > len(sample)

    return {
        "before_shape": [int(b_rows), int(b_cols)],
        "after_shape": [int(a_rows), int(a_cols)],
        "aligned": aligned,
        "reordered": reordered,
        "rows_added": rows_added,
        "rows_removed": rows_removed,
        "columns_added": columns_added,
        "columns_removed": columns_removed,
        "columns": columns,
        "columns_unchanged": columns_unchanged,
        "changed_cells": changed_cells,
        "sample": sample,
        "sample_truncated": sample_truncated,
    }


def _nunique_safe(series):
    """Únicos con el mismo fallback anti-tipos-mixtos que /stats."""
    try:
        return int(series.nunique())
    except TypeError:
        try:
            return int(series.astype(str).nunique())
        except Exception:
            return None


@app.route("/step_diff", methods=["POST"])
def step_diff():
    """Diff entre el estado antes y después de un paso del pipeline.

    `index` (base 0) es la posición del paso en `op_history` — la misma que
    muestran las tarjetas del panel derecho. Compara `history[index]`
    (antes) con `history[index + 1]` (después): esos snapshots ya existen
    para el undo, así que no se guarda estado extra. SOLO LEE — consultar
    el diff jamás altera el pipeline.
    """
    global current_df
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400

    data = request.get_json(silent=True) or {}
    index = data.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        return jsonify({"error": "Se requiere el índice del paso (entero)."}), 400
    if index < 0 or index >= len(op_history) or index + 1 >= len(history):
        return jsonify({"error": f"El paso {index + 1} no existe en el historial."}), 400

    step = op_history[index]
    result = diff_snapshots(history[index], history[index + 1])
    result.update({
        "success": True,
        "index": index,
        "op": step.get("op", "?"),
        "params": step.get("params", {}) or {},
    })
    return jsonify(result)


@app.route("/schema_rules", methods=["POST"])
def schema_rules_post():
    """Guarda la lista completa de reglas de validación de esquema.

    Valida TODA la lista antes de tocar `schema_rules` (fail-fast, sin
    estado parcial — patrón /apply_recipe): una regla mala → 400 citando
    «regla N» y la lista vigente queda intacta. Lista vacía = limpiar.
    Devuelve las reglas normalizadas y las violaciones ya calculadas.
    """
    global schema_rules, current_df
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400

    data = request.get_json(silent=True)
    if data is None or not isinstance(data.get("rules"), list):
        return jsonify({
            "error": "Se requiere JSON válido con la clave 'rules' (lista de reglas)."
        }), 400

    try:
        clean = validate_rules(current_df, data["rules"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    schema_rules = clean
    result = validate_schema(current_df, schema_rules)
    return jsonify({"success": True, "rules": schema_rules, **result})


@app.route("/schema_validate", methods=["GET"])
def schema_validate():
    """Violaciones actuales, recalculadas contra el df vigente.

    SOLO LEE — consultar la validación jamás altera el pipeline. Las
    reglas sobreviven a operaciones/undo/recarga; solo un upload nuevo las
    limpia (se recalculan contra el estado actual del dataset).
    """
    if current_df is None:
        return jsonify({"error": "No hay datos."}), 400
    result = validate_schema(current_df, schema_rules)
    return jsonify({"rules": schema_rules, **result})


@app.route("/correlations", methods=["GET"])
def correlations():
    """Matriz de correlación de Pearson de las columnas numéricas (roadmap).

    Alimenta el heatmap del tab Diagnóstico. SOLO LEE, como /stats.
    Excluye booleanos (pandas los trata como numéricos en `.corr()`),
    redondea a 4 decimales y convierte los NaN (columna constante o par sin
    variación) en `null` — nunca un NaN suelto, que rompería el
    `response.json()` del navegador. Con menos de 2 columnas numéricas
    devuelve `matrix` vacía y el front muestra su aviso.
    """
    global current_df
    if current_df is None:
        return jsonify({"error": "No hay datos."}), 400

    numeric = [
        c for c in current_df.columns
        if pd.api.types.is_numeric_dtype(current_df[c])
        and not pd.api.types.is_bool_dtype(current_df[c])
    ]
    if len(numeric) < 2:
        return jsonify({"columns": [str(c) for c in numeric], "matrix": []})

    # `.corr()` usa borrado por pares: cada par se calcula sobre las filas
    # donde ambos valores no son nulos (misma semántica que pandas).
    corr = current_df[numeric].corr()
    matrix = [
        [None if pd.isna(v) else round(float(v), 4) for v in row]
        for row in corr.to_numpy()
    ]
    return jsonify({"columns": [str(c) for c in numeric], "matrix": matrix})


@app.route("/benchmark", methods=["GET"])
def benchmark():
    """Tiempo por paso para la barra de benchmark (roadmap). SOLO LEE.

    `step_ms` es paralelo a `op_history` y se rebana con `zip`: un undo
    (que vacía `op_history` sin tocar `step_ms`) muestra solo los pasos
    vivos y un `/redo` recupera el MISMO tiempo medido originalmente.
    """
    global current_df
    if current_df is None:
        return jsonify({"error": "No hay datos."}), 400
    steps = [
        {"op": s.get("op", "?"), "ms": m}
        for s, m in zip(op_history, step_ms)
    ]
    return jsonify({
        "steps": steps,
        "total_ms": round(sum(st["ms"] for st in steps), 2),
    })


# ── OPEN CORE / PREMIUM ───────────────────────────────────────────────
@app.route("/premium/status", methods=["GET"])
def premium_status():
    """Licencia premium, manifiesto de temas y conectores disponibles
    (Open Core).

    Sin licencia devuelve listas vacías: el front no puede ni conocer los
    ids de los temas ni saber qué conectores existen (Postgres, S3), y el CSS
    se niega aparte en /premium/themes/<id>.css. SOLO LEE.
    """
    if premium_pkg.is_licensed():
        return jsonify({
            "licensed": True,
            "themes": premium_pkg.theme_manifest(),
            "connectors": ["postgres", "s3", "bigquery"],
        })
    return jsonify({"licensed": False, "themes": [], "connectors": []})


@app.route("/premium/themes/<theme_id>.css", methods=["GET"])
def premium_theme_css(theme_id):
    """CSS de un tema premium — 404 sin licencia o con id desconocido.

    `premium.theme_css` valida el id contra el manifiesto antes de leer
    el fichero (la ruta sale del manifiesto, nunca del usuario).
    """
    css = premium_pkg.theme_css(theme_id)
    if css is None:
        return jsonify({"error": "No encontrado."}), 404
    return css, 200, {"Content-Type": "text/css; charset=utf-8"}


# ── AVISO DE VERSIÓN NUEVA ────────────────────────────────────────
# El servidor compara la ÚLTIMA release publicada en GitHub con
# `package.json` y el front pinta un toast con enlace solo si hay algo
# más nuevo. Best-effort: sin red, con rate limit o con un tag ilegible
# se responde 200 sin aviso — jamás bloquea ni rompe la app. SOLO LEE.
# El resultado queda cacheado (1 h si fue OK, 5 min si falló) para no
# agotar el rate limit anónimo de api.github.com (60 req/h por IP).
_RELEASE_TTL_OK = 3600
_RELEASE_TTL_ERR = 300
_RELEASE_REPO = os.environ.get("CATFLIP_GITHUB_REPO", "lpardo303/Cat_flip")
_RELEASE_CACHE = {"at": 0.0, "release": None, "failed": False}


def app_version():
    """Versión actual desde `package.json` (None si no se puede leer).

    Los builds congelados lo incluyen como dato en ambos specs, y en
    desarrollo y en el bundle comparten patrón: el fichero vive junto a
    `app.py`, así que basta la ruta relativa a `__file__`.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "package.json")
    try:
        with open(path, encoding="utf-8") as f:
            version = json.load(f).get("version")
    except (OSError, ValueError):
        return None
    return version if isinstance(version, str) and version else None


def parse_version(tag):
    """«v1.4.0» → (1, 4, 0); cualquier tag no numérico → None."""
    if not isinstance(tag, str):
        return None
    m = re.match(r"^v?(\d+(?:\.\d+)*)", tag.strip())
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def is_newer(latest_tag, current_version):
    """True SOLO si `latest_tag` es estrictamente más nueva.

    Comparación numérica por componente (1.10 > 1.9 — nada lexicográfico)
    con relleno de longitudes distintas («1.4» == «1.4.0»). Si cualquiera
    de las dos no se puede interpretar, no se anuncia nada: ante la duda
    el usuario no ve un aviso falso.
    """
    a, b = parse_version(latest_tag), parse_version(current_version)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def _fetch_release(repo):
    """Última release de GitHub o None — CUALQUIER fallo es None.

    Best-effort a propósito: sin red, timeout, 403 por rate limit o JSON
    inesperado significan simplemente «esta vez no hay aviso».
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"CatFlip/{app_version() or 'dev'}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _cached_release():
    """Release con caché: 1 h si fue OK, 5 min si falló (reintentar pronto)."""
    now = time.time()
    ttl = _RELEASE_TTL_ERR if _RELEASE_CACHE["failed"] else _RELEASE_TTL_OK
    if _RELEASE_CACHE["at"] and now - _RELEASE_CACHE["at"] < ttl:
        return _RELEASE_CACHE["release"]
    release = _fetch_release(_RELEASE_REPO)
    _RELEASE_CACHE.update(at=now, release=release, failed=release is None)
    return release


@app.route("/version/check", methods=["GET"])
def version_check():
    """Aviso de versión nueva: última release de GitHub vs `package.json`.

    `update_available` solo es True si la release es interpretably más
    nueva; `checked=False` significa que GitHub no se pudo consultar (sin
    red, rate limit…). El front, en cualquier otro caso, no pinta nada.
    """
    current = app_version()
    release = _cached_release()
    latest = release.get("tag_name") if release else None
    return jsonify({
        "current": current,
        "latest": latest,
        "html_url": release.get("html_url") if release else None,
        "published_at": release.get("published_at") if release else None,
        "update_available": bool(
            release and current and is_newer(latest, current)
        ),
        "checked": release is not None,
    })


# ── CONECTORES REALES (Open Core) ───────────────────────────────
# Gating: sin licencia la ruta no existe (404), igual que el CSS premium.
# La lógica pura (validación, quoting de identificadores, dtypes y driver
# opcional) vive en `connectors.py`; aquí solo se monta la respuesta.

def premium_required(view):
    """Decorador de gating: exige `premium.is_licensed()` o devuelve 404."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not premium_pkg.is_licensed():
            return jsonify({
                "error": "Conector premium: esta instalación no tiene licencia."
            }), 404
        return view(*args, **kwargs)
    return wrapper


@app.route("/connectors/postgres/test", methods=["POST"])
@premium_required
def connectors_postgres_test():
    """Prueba de conexión (`SELECT version()`) — no toca el dataset."""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(test_connection(clean_conn_params(data)))
    except ConnectorError as e:
        return jsonify({"error": str(e)}), e.status


@app.route("/connectors/postgres/export", methods=["POST"])
@premium_required
def connectors_postgres_export():
    """Escribe `current_df` (el dataset completo, no el preview) en la tabla."""
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400
    data = request.get_json(silent=True) or {}
    try:
        params = clean_conn_params(data)
        table = data.get("table")
        if not isinstance(table, str) or not table.strip():
            raise ConnectorError("Falta el campo obligatorio «tabla» (table).")
        schema = data.get("schema") or "public"
        if not isinstance(schema, str) or not schema.strip():
            raise ConnectorError("El esquema debe ser texto (por defecto «public»).")
        mode = data.get("mode") or "replace"
        result = export_to_postgres(
            current_df, params, table.strip(), schema=schema.strip(), mode=mode
        )
    except ConnectorError as e:
        return jsonify({"error": str(e)}), e.status
    return jsonify(result)


@app.route("/connectors/s3/test", methods=["POST"])
@premium_required
def connectors_s3_test():
    """Prueba de acceso (`head_bucket`) — no toca el dataset."""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(test_s3_connection(clean_s3_params(data)))
    except ConnectorError as e:
        return jsonify({"error": str(e)}), e.status


@app.route("/connectors/s3/export", methods=["POST"])
@premium_required
def connectors_s3_export():
    """Sube `current_df` (el dataset completo) como CSV al objeto del bucket."""
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400
    data = request.get_json(silent=True) or {}
    try:
        params = clean_s3_params(data)
        result = export_to_s3(
            current_df, params, data.get("key"), mode=data.get("mode") or "overwrite"
        )
    except ConnectorError as e:
        return jsonify({"error": str(e)}), e.status
    return jsonify(result)


@app.route("/connectors/bigquery/test", methods=["POST"])
@premium_required
def connectors_bigquery_test():
    """Prueba de conexión (`SELECT 1`) — no toca el dataset."""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(test_bq_connection(clean_bq_params(data)))
    except ConnectorError as e:
        return jsonify({"error": str(e)}), e.status


@app.route("/connectors/bigquery/export", methods=["POST"])
@premium_required
def connectors_bigquery_export():
    """Carga `current_df` (el dataset completo) en `<dataset>.<tabla>`."""
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400
    data = request.get_json(silent=True) or {}
    try:
        params = clean_bq_params(data)
        table = data.get("table")
        if not isinstance(table, str) or not table.strip():
            raise ConnectorError("Falta el campo obligatorio «tabla» (table).")
        result = export_to_bigquery(
            current_df, params, table.strip(), mode=data.get("mode") or "replace"
        )
    except ConnectorError as e:
        return jsonify({"error": str(e)}), e.status
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=False, port=5050, host="127.0.0.1")
