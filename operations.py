"""Handlers de operaciones ETL — refactor P2 de la cadena if/elif de `operation()`.

Cada handler recibe `(df, params)` y devuelve `(df, code)` donde `code` es el
fragmento de Pandas autogenerado que se muestra en el visor y se exporta al
script. `OPS` es el registro que consume `app.operation()`: añadir una
operación = añadir una función aquí + una entrada en `OPS` (+ su modal en el
front). El endpoint no cambia de comportamiento: mismos dataframes, mismos
strings de código, mismos errores.
"""
import pandas as pd


# ── Estructural ─────────────────────────────────────────────────────────

def op_unpivot(df, params):
    id_cols = params.get("id_cols", [])
    value_name = params.get("value_name", "Valor")
    var_name = params.get("var_name", "Variable")
    df = df.melt(id_vars=id_cols, var_name=var_name, value_name=value_name)
    code = (f"df = df.melt(\n"
            f"    id_vars={id_cols},\n"
            f"    var_name='{var_name}',\n"
            f"    value_name='{value_name}'\n"
            f")")
    return df, code


def op_pivot(df, params):
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
    return df, code


def op_split_column(df, params):
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
    return df, "\n".join(code_lines)


def op_split_to_rows(df, params):
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
    return df, code


def op_set_header(df, params):
    row_idx = int(params.get("row_index", 0))
    new_cols = df.iloc[row_idx].astype(str).tolist()
    df.columns = new_cols
    df = df.drop(index=row_idx).reset_index(drop=True)
    code = (f"df.columns = df.iloc[{row_idx}].astype(str).tolist()\n"
            f"df = df.drop(index={row_idx}).reset_index(drop=True)")
    return df, code


# ── Limpieza & Filtrado ─────────────────────────────────────────────────

def op_drop_nulls(df, params):
    cols = params.get("columns", None) or None
    how = params.get("how", "any")
    before = len(df)
    df = df.dropna(subset=cols, how=how)
    removed = before - len(df)
    code = f"df = df.dropna(subset={cols}, how='{how}')  # Eliminó {removed} filas"
    return df, code


def op_drop_duplicates(df, params):
    cols = params.get("columns", None) or None
    before = len(df)
    df = df.drop_duplicates(subset=cols)
    removed = before - len(df)
    code = f"df = df.drop_duplicates(subset={cols})  # Eliminó {removed} duplicados"
    return df, code


def op_drop_rows(df, params):
    position = params.get("position", "top")   # "top" | "bottom"
    n = int(params.get("n", 1))
    before = len(df)
    if position == "top":
        df = df.iloc[n:].reset_index(drop=True)
    else:
        df = df.iloc[:-n].reset_index(drop=True)
    removed = before - len(df)
    code = f"df = df.iloc[{':-' + str(n) if position == 'bottom' else str(n) + ':'}].reset_index(drop=True)  # {removed} filas eliminadas desde el {'inicio' if position == 'top' else 'final'}"
    return df, code


def op_trim(df, params):
    cols = params.get("columns", list(df.select_dtypes(include=["object", "str"]).columns))
    for col in cols:
        df[col] = df[col].astype(str).str.strip()
    code = f"for col in {cols}:\n    df[col] = df[col].astype(str).str.strip()"
    return df, code


def op_clean_newlines(df, params):
    cols = params.get("columns") or list(df.select_dtypes(include=["object", "str"]).columns)
    for col in cols:
        df[col] = df[col].astype(str).str.replace(r'\r\n|\r|\n', ' ', regex=True).str.strip()
    code = f"for col in {cols}:\n    df[col] = df[col].astype(str).str.replace(r'\\r\\n|\\r|\\n', ' ', regex=True).str.strip()"
    return df, code


# ── Texto & Tipos ───────────────────────────────────────────────────────

def op_change_case(df, params):
    col = params.get("column")
    case = params.get("case", "lower")
    fn = {"lower": "lower", "upper": "upper", "title": "title", "capitalize": "capitalize"}.get(case, "lower")
    df[col] = getattr(df[col].astype(str).str, fn)()
    code = f"df['{col}'] = df['{col}'].astype(str).str.{fn}()"
    return df, code


def op_replace(df, params):
    col = params.get("column")
    old_val = params.get("old_value", "")
    new_val = params.get("new_value", "")
    df[col] = df[col].astype(str).str.replace(old_val, new_val, regex=False)
    code = f"df['{col}'] = df['{col}'].astype(str).str.replace('{old_val}', '{new_val}', regex=False)"
    return df, code


def op_rename_column(df, params):
    old_name = params.get("old_name")
    new_name = params.get("new_name")
    df = df.rename(columns={old_name: new_name})
    code = f"df = df.rename(columns={{'{old_name}': '{new_name}'}})"
    return df, code


def op_drop_column(df, params):
    col = params.get("column")
    df = df.drop(columns=[col])
    code = f"df = df.drop(columns=['{col}'])"
    return df, code


def op_change_type(df, params):
    col = params.get("column")
    dtype = params.get("dtype", "str")
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
    return df, code


# ── Reglas & Operaciones ────────────────────────────────────────────────

def op_filter(df, params):
    col = params.get("column")
    operator = params.get("operator", "==")
    value = params.get("value", "")
    code = ""

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

    return df, code


def op_sort(df, params):
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
    return df, code


# ── Registro (consumido por app.operation()) ────────────────────────────

OPS = {
    # Estructural
    "unpivot": op_unpivot,
    "pivot": op_pivot,
    "split_column": op_split_column,
    "split_to_rows": op_split_to_rows,
    "set_header": op_set_header,
    # Limpieza & Filtrado
    "drop_nulls": op_drop_nulls,
    "drop_duplicates": op_drop_duplicates,
    "drop_rows": op_drop_rows,
    "trim": op_trim,
    "clean_newlines": op_clean_newlines,
    # Texto & Tipos
    "change_case": op_change_case,
    "replace": op_replace,
    "rename_column": op_rename_column,
    "drop_column": op_drop_column,
    "change_type": op_change_type,
    # Reglas & Operaciones
    "filter": op_filter,
    "sort": op_sort,
}
