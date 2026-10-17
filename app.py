from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import io
import os
import json
import base64

from operations import OPS, detect_date_columns

app = Flask(__name__)

# Almacenamiento temporal en memoria
current_df = None
history = []  # Para undo
code_log = []  # Log de código generado
op_history = []  # Pasos estructurados {op, params} para el linaje (F3.3)

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
    """Lee un CSV/XLSX/XLS subido y devuelve (df, expresión pandas).

    La expresión es el RHS listo para el código generado: en /upload se usa
    como `df = <expr>` y en el cruce como `df_right = <expr>`. El formato lo
    valida el endpoint que llama; aquí solo se autodetecta el separador del
    CSV (comas vs punto y coma) o se lee la hoja de Excel.
    """
    if file.filename.lower().endswith(".csv"):
        # Intentar detectar el separador automáticamente
        content = file.read()
        file.seek(0)
        sep = "," if content.count(b",") > content.count(b";") else ";"
        df = pd.read_csv(io.BytesIO(content), sep=sep)
        return df, f"pd.read_csv('{file.filename}', sep='{sep}')"
    sheet = request.form.get("sheet", 0)
    df = pd.read_excel(file, sheet_name=int(sheet) if str(sheet).isdigit() else sheet)
    return df, f"pd.read_excel('{file.filename}', sheet_name={repr(sheet)})"


@app.route("/upload", methods=["POST"])
def upload():
    global current_df, history, code_log, op_history
    file = request.files["file"]
    filename = file.filename.lower()
    
    try:
        if not filename.endswith((".csv", ".xlsx", ".xls")):
            return jsonify({"error": "Formato no soportado. Usa CSV, XLSX o XLS."}), 400

        current_df, expr = read_table(file)
        code = f"df = {expr}"
        
        history = [current_df.copy()]
        code_log = [f"import pandas as pd\n\n# Cargar archivo\n{code}"]
        op_history = []
        
        return jsonify({
            "success": True,
            "data": df_to_json(current_df),
            "sheets": [],
            "code": code_log[-1],
            "date_suggestions": detect_date_columns(current_df)
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
        right_df, right_code = read_table(file)
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
    global current_df, history, code_log, op_history
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
    global current_df, history, code_log, op_history
    if len(history) > 1:
        history.pop()
        current_df = history[-1].copy()
        if len(code_log) > 1:
            code_log.pop()
        if len(op_history) > 0:
            op_history.pop()
        return jsonify({
            "success": True,
            "data": df_to_json(current_df),
            "code": "\n\n".join(code_log)
        })
    return jsonify({"error": "No hay más pasos para deshacer."}), 400

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
