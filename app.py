from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import io
import os
import re
import json
import base64

from operations import OPS, detect_pii_columns, detect_type_suggestions

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

# Frame derecho para el cruce Join/Merge (op #19): fuente independiente del
# pipeline (no participa en undo) más su expresión de carga para el script.
right_df = None
right_name = ""
right_code = ""

def df_to_json(df, max_rows=500):
    """Convierte DataFrame a JSON seguro para el frontend."""
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

def read_table(file):
    """Lee un CSV/XLSX/XLS subido y devuelve (df, expresión pandas, encoding).

    La expresión es el RHS listo para el código generado: en /upload se usa
    como `df = <expr>` y en el cruce como `df_right = <expr>`. El formato lo
    valida el endpoint que llama; aquí se autodetecta el separador del CSV
    (comas vs punto y coma), la codificación (UTF-8 si el decode pasa; si no,
    charset-normalizer) o se lee la hoja de Excel.

    `encoding` es la codificación no-utf8 detectada (ej. 'cp1252') o None.
    El script exportado la incluye para reproducir la misma carga. Fallback:
    latin-1 (nunca lanza UnicodeDecodeError) si la detección no sirve.
    """
    if file.filename.lower().endswith(".csv"):
        # Intentar detectar el separador automáticamente
        content = file.read()
        file.seek(0)
        sep = "," if content.count(b",") > content.count(b";") else ";"
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
        if encoding:
            df = pd.read_csv(io.StringIO(text), sep=sep, encoding=encoding)
            return (
                df,
                f"pd.read_csv('{file.filename}', sep='{sep}', encoding={encoding!r})",
                encoding,
            )
        df = pd.read_csv(io.StringIO(text), sep=sep)
        return df, f"pd.read_csv('{file.filename}', sep='{sep}')", None
    sheet = request.form.get("sheet", 0)
    df = pd.read_excel(file, sheet_name=int(sheet) if str(sheet).isdigit() else sheet)
    return df, f"pd.read_excel('{file.filename}', sheet_name={repr(sheet)})", None


@app.route("/upload", methods=["POST"])
def upload():
    global current_df, history, code_log, op_history, redo_history
    file = request.files["file"]
    filename = file.filename.lower()
    
    try:
        if not filename.endswith((".csv", ".xlsx", ".xls")):
            return jsonify({"error": "Formato no soportado. Usa CSV, XLSX o XLS."}), 400

        current_df, expr, encoding = read_table(file)
        code = f"df = {expr}"
        
        history = [current_df.copy()]
        code_log = [f"import pandas as pd\n\n# Cargar archivo\n{code}"]
        op_history = []
        redo_history = []  # dataset nuevo → la pila de rehacer no aplica
        
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

    if not filename.endswith((".csv", ".xlsx", ".xls")):
        return jsonify({"error": "Formato no soportado. Usa CSV, XLSX o XLS."}), 400

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
    global current_df, history, code_log, op_history, redo_history
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

        df, code = handler(current_df.copy(), handler_params)

        # Guardar en historial
        history.append(df.copy())
        op_history.append({"op": op, "params": history_params})
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

@app.route("/apply_recipe", methods=["POST"])
def apply_recipe():
    """Reproduce una receta `.catflip.json` sobre el dataset actual.

    Atomicidad: TODA la receta se ejecuta sobre copias de trabajo y los
    globals (history/code_log/op_history/current_df) solo se escriben si
    ningún paso falla → imposible dejar estado parcial. Si todo pasa,
    `history` recibe un snapshot por paso: Deshacer revierte paso a paso
    y el linaje muestra cada paso individual, igual que ops manuales.
    """
    global current_df, history, code_log, op_history, redo_history
    if current_df is None:
        return jsonify({"error": "No hay datos cargados. Carga un archivo antes de aplicar la receta."}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "La receta no es JSON válido."}), 400
    if data.get("version") != 1:
        return jsonify({"error": f"Versión de receta no soportada: {data.get('version')!r} (se espera 1)."}), 400
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return jsonify({"error": "La receta no contiene pasos válidos ('steps' ausente o vacío)."}), 400

    # Validación estructural ANTES de ejecutar nada: un paso malformado
    # ni siquiera llega al handler.
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            return jsonify({"error": f"El paso {i} no es un objeto válido."}), 400
        sop = step.get("op")
        if not isinstance(sop, str) or sop not in OPS:
            return jsonify({"error": f"El paso {i} usa una operación desconocida: {sop!r}."}), 400
        if not isinstance(step.get("params", {}), dict):
            return jsonify({"error": f"El paso {i} ({sop}) tiene 'params' que no son un objeto."}), 400

    # Reproducción en copia de trabajo: cero mutación de globals aquí.
    df_work = current_df
    snaps, codes, applied = [], [], []
    for i, step in enumerate(steps, 1):
        sop = step["op"]
        params = step.get("params", {})
        handler = OPS[sop]
        handler_params = params
        if sop == "merge":
            if right_df is None:
                return jsonify({
                    "error": f"El paso {i} (merge): No hay frame derecho cargado. Carga un segundo dataset desde el modal de Join."
                }), 400
            handler_params = {**params, "right_df": right_df, "right_code": right_code}
        try:
            df_work, code = handler(df_work.copy(), handler_params)
        except Exception as e:
            # 400: el problema lo trae la receta del cliente, no el servidor
            return jsonify({"error": f"El paso {i} ({sop}) falló: {e}"}), 400
        snaps.append(df_work.copy())
        codes.append(f"# {sop}\n{code}")
        applied.append({"op": sop, "params": params})

    # Commit único: solo aquí se tocan los globals (ya se validó todo ⇒ no
    # puede quedar estado parcial por un paso a mitad de camino)
    history.extend(snaps)
    op_history.extend(applied)
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


if __name__ == "__main__":
    app.run(debug=False, port=5050, host="127.0.0.1")
