from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import io
import os
import json
import base64

app = Flask(__name__)

# Almacenamiento temporal en memoria
current_df = None
history = []  # Para undo
code_log = []  # Log de código generado

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

    return {
        "columns": list(df.columns),
        "dtypes": {col: classify_dtype(df[col]) for col in df.columns},
        "data": preview.fillna("").astype(str).values.tolist(),
        "shape": [len(df), len(df.columns)],
        "truncated": len(df) > max_rows
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    global current_df, history, code_log
    file = request.files["file"]
    filename = file.filename.lower()
    
    try:
        if filename.endswith(".csv"):
            # Intentar detectar el separador automáticamente
            content = file.read()
            file.seek(0)
            sep = "," if content.count(b",") > content.count(b";") else ";"
            current_df = pd.read_csv(io.BytesIO(content), sep=sep)
            code = f"df = pd.read_csv('{file.filename}', sep='{sep}')"
        elif filename.endswith((".xlsx", ".xls")):
            sheet = request.form.get("sheet", 0)
            current_df = pd.read_excel(file, sheet_name=int(sheet) if str(sheet).isdigit() else sheet)
            code = f"df = pd.read_excel('{file.filename}', sheet_name={repr(sheet)})"
        else:
            return jsonify({"error": "Formato no soportado. Usa CSV, XLSX o XLS."}), 400
        
        history = [current_df.copy()]
        code_log = [f"import pandas as pd\n\n# Cargar archivo\n{code}"]
        
        return jsonify({
            "success": True,
            "data": df_to_json(current_df),
            "sheets": [],
            "code": code_log[-1]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    global current_df, history, code_log
    if current_df is None:
        return jsonify({"error": "No hay datos cargados."}), 400
    
    data = request.json
    op = data.get("operation")
    params = data.get("params", {})
    
    try:
        df = current_df.copy()
        code = ""

        # ── UNPIVOT (melt) ──────────────────────────────────────────────
        if op == "unpivot":
            id_cols = params.get("id_cols", [])
            value_name = params.get("value_name", "Valor")
            var_name = params.get("var_name", "Variable")
            df = df.melt(id_vars=id_cols, var_name=var_name, value_name=value_name)
            code = (f"df = df.melt(\n"
                    f"    id_vars={id_cols},\n"
                    f"    var_name='{var_name}',\n"
                    f"    value_name='{value_name}'\n"
                    f")")

        # ── PIVOT ────────────────────────────────────────────────────────
        elif op == "pivot":
            index = params.get("index")
            columns = params.get("columns")
            values = params.get("values")
            df = df.pivot_table(index=index, columns=columns, values=values, aggfunc="sum").reset_index()
            df.columns = [str(c) for c in df.columns]
            code = (f"df = df.pivot_table(\n"
                    f"    index='{index}',\n"
                    f"    columns='{columns}',\n"
                    f"    values='{values}',\n"
                    f"    aggfunc='sum'\n"
                    f").reset_index()")

        # ── SEPARAR COLUMNA ──────────────────────────────────────────────
        elif op == "split_column":
            col = params.get("column")
            delimiter = params.get("delimiter", ",")
            col_prefix = params.get("col_prefix", col)
            max_split = params.get("max_split", 1)
            max_split = None if int(max_split) == 0 else int(max_split)
            split_df = df[col].str.split(delimiter, n=max_split, expand=True)
            # Generar nombres dinámicamente para TODOS los fragmentos obtenidos
            new_col_names = [f"{col_prefix}_{i+1}" for i in range(split_df.shape[1])]
            for i, name in enumerate(new_col_names):
                df[name] = split_df[i]
            code_lines = [f"split_df = df['{col}'].str.split('{delimiter}', n={max_split}, expand=True)"]
            for i, name in enumerate(new_col_names):
                code_lines.append(f"df['{name}'] = split_df[{i}]")
            code = "\n".join(code_lines)

        # ── ELIMINAR FILAS VACÍAS ────────────────────────────────────────
        elif op == "drop_nulls":
            cols = params.get("columns", None) or None
            how = params.get("how", "any")
            before = len(df)
            df = df.dropna(subset=cols, how=how)
            removed = before - len(df)
            code = f"df = df.dropna(subset={cols}, how='{how}')  # Eliminó {removed} filas"

        # ── ELIMINAR DUPLICADOS ──────────────────────────────────────────
        elif op == "drop_duplicates":
            cols = params.get("columns", None) or None
            before = len(df)
            df = df.drop_duplicates(subset=cols)
            removed = before - len(df)
            code = f"df = df.drop_duplicates(subset={cols})  # Eliminó {removed} duplicados"

        # ── RENOMBRAR COLUMNA ────────────────────────────────────────────
        elif op == "rename_column":
            old_name = params.get("old_name")
            new_name = params.get("new_name")
            df = df.rename(columns={old_name: new_name})
            code = f"df = df.rename(columns={{'{old_name}': '{new_name}'}})"

        # ── ELIMINAR COLUMNA ─────────────────────────────────────────────
        elif op == "drop_column":
            col = params.get("column")
            df = df.drop(columns=[col])
            code = f"df = df.drop(columns=['{col}'])"

        # ── FILTRAR ──────────────────────────────────────────────────────
        elif op == "filter":
            col = params.get("column")
            operator = params.get("operator", "==")
            value = params.get("value", "")
            
            if operator == "==":
                df = df[df[col].astype(str) == str(value)]
                code = f"df = df[df['{col}'].astype(str) == '{value}']"
            elif operator == "!=":
                df = df[df[col].astype(str) != str(value)]
                code = f"df = df[df['{col}'].astype(str) != '{value}']"
            elif operator == "contiene":
                df = df[df[col].astype(str).str.contains(str(value), na=False)]
                code = f"df = df[df['{col}'].astype(str).str.contains('{value}', na=False)]"
            elif operator == "no contiene":
                df = df[~df[col].astype(str).str.contains(str(value), na=False)]
                code = f"df = df[~df['{col}'].astype(str).str.contains('{value}', na=False)]"
            elif operator == ">":
                df = df[pd.to_numeric(df[col], errors='coerce') > float(value)]
                code = f"df = df[pd.to_numeric(df['{col}'], errors='coerce') > {value}]"
            elif operator == "<":
                df = df[pd.to_numeric(df[col], errors='coerce') < float(value)]
                code = f"df = df[pd.to_numeric(df['{col}'], errors='coerce') < {value}]"

        # ── LIMPIAR ESPACIOS ─────────────────────────────────────────────
        elif op == "trim":
            cols = params.get("columns", list(df.select_dtypes(include=["object", "str"]).columns))
            for col in cols:
                df[col] = df[col].astype(str).str.strip()
            code = f"for col in {cols}:\n    df[col] = df[col].astype(str).str.strip()"

        # ── CAMBIAR MAYÚSCULAS/MINÚSCULAS ────────────────────────────────
        elif op == "change_case":
            col = params.get("column")
            case = params.get("case", "lower")
            fn = {"lower": "lower", "upper": "upper", "title": "title", "capitalize": "capitalize"}.get(case, "lower")
            df[col] = getattr(df[col].astype(str).str, fn)()
            code = f"df['{col}'] = df['{col}'].astype(str).str.{fn}()"

        # ── LIMPIAR SALTOS DE LÍNEA ──────────────────────────────────────
        elif op == "clean_newlines":
            cols = params.get("columns") or list(df.select_dtypes(include=["object", "str"]).columns)
            for col in cols:
                df[col] = df[col].astype(str).str.replace(r'\r\n|\r|\n', ' ', regex=True).str.strip()
            code = f"for col in {cols}:\n    df[col] = df[col].astype(str).str.replace(r'\\r\\n|\\r|\\n', ' ', regex=True).str.strip()"

        # ── REEMPLAZAR VALORES ───────────────────────────────────────────
        elif op == "replace":
            col = params.get("column")
            old_val = params.get("old_value", "")
            new_val = params.get("new_value", "")
            df[col] = df[col].astype(str).str.replace(old_val, new_val, regex=False)
            code = f"df['{col}'] = df['{col}'].astype(str).str.replace('{old_val}', '{new_val}', regex=False)"

        # ── CAMBIAR TIPO DE DATO ─────────────────────────────────────────
        elif op == "change_type":
            col = params.get("column")
            dtype = params.get("dtype", "str")
            type_map = {"str": str, "int": "Int64", "float": float, "datetime": None}
            if dtype == "datetime":
                df[col] = pd.to_datetime(df[col], errors="coerce")
                code = f"df['{col}'] = pd.to_datetime(df['{col}'], errors='coerce')"
            elif dtype == "int":
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                code = f"df['{col}'] = pd.to_numeric(df['{col}'], errors='coerce').astype('Int64')"
            elif dtype == "float":
                df[col] = pd.to_numeric(df[col], errors="coerce")
                code = f"df['{col}'] = pd.to_numeric(df['{col}'], errors='coerce')"
            else:
                df[col] = df[col].astype(str)
                code = f"df['{col}'] = df['{col}'].astype(str)"

        # ── ORDENAR ──────────────────────────────────────────────────────
        elif op == "sort":
            col = params.get("column")
            ascending = params.get("ascending", True)
            try:
                df = df.sort_values(by=col, ascending=ascending)
                code = f"df = df.sort_values(by='{col}', ascending={ascending})"
            except TypeError:
                # Columna con tipos mixtos (ej. columna "Valor" tras un unpivot):
                # se ordena por su representación textual para no romper el pipeline.
                df = df.sort_values(by=col, ascending=ascending, key=lambda s: s.astype(str))
                code = (f"df = df.sort_values(by='{col}', ascending={ascending}, "
                        f"key=lambda s: s.astype(str))  # tipos mixtos -> orden textual")

        # ── SEPARAR POR FILAS ────────────────────────────────────────────
        elif op == "split_to_rows":
            col = params.get("column")
            delimiter = params.get("delimiter", ",")
            strip = params.get("strip", True)
            before = len(df)
            df[col] = df[col].astype(str).str.split(delimiter)
            df = df.explode(col).reset_index(drop=True)
            if strip:
                df[col] = df[col].str.strip()
            after = len(df)
            code = (f"df['{col}'] = df['{col}'].astype(str).str.split('{delimiter}')\n"
                    f"df = df.explode('{col}').reset_index(drop=True)\n"
                    f"df['{col}'] = df['{col}'].str.strip()  # generó {after - before} filas nuevas")

        # ── ELIMINAR FILAS POR POSICIÓN ──────────────────────────────────
        elif op == "drop_rows":
            position = params.get("position", "top")   # "top" | "bottom"
            n = int(params.get("n", 1))
            before = len(df)
            if position == "top":
                df = df.iloc[n:].reset_index(drop=True)
            else:
                df = df.iloc[:-n].reset_index(drop=True)
            removed = before - len(df)
            code = f"df = df.iloc[{':-' + str(n) if position == 'bottom' else str(n) + ':'}].reset_index(drop=True)  # {removed} filas eliminadas desde el {'inicio' if position == 'top' else 'final'}"

        # ── DEFINIR FILA COMO ENCABEZADO ─────────────────────────────────
        elif op == "set_header":
            row_idx = int(params.get("row_index", 0))
            new_cols = df.iloc[row_idx].astype(str).tolist()
            df.columns = new_cols
            df = df.drop(index=row_idx).reset_index(drop=True)
            code = (f"df.columns = df.iloc[{row_idx}].astype(str).tolist()\n"
                    f"df = df.drop(index={row_idx}).reset_index(drop=True)")

        else:
            return jsonify({"error": f"Operación '{op}' no reconocida."}), 400

        # Guardar en historial
        history.append(df.copy())
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
    global current_df, history, code_log
    if len(history) > 1:
        history.pop()
        current_df = history[-1].copy()
        if len(code_log) > 1:
            code_log.pop()
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

        stats[col] = col_stats

    return jsonify({"columns": current_df.columns.tolist(), "stats": stats})

if __name__ == "__main__":
    app.run(debug=False, port=5050, host="127.0.0.1")
