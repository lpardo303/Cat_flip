"""Handlers de operaciones ETL — refactor P2 de la cadena if/elif de `operation()`.

Cada handler recibe `(df, params)` y devuelve `(df, code)` donde `code` es el
fragmento de Pandas autogenerado que se muestra en el visor y se exporta al
script. `OPS` es el registro que consume `app.operation()`: añadir una
operación = añadir una función aquí + una entrada en `OPS` (+ su modal en el
front). El endpoint no cambia de comportamiento: mismos dataframes, mismos
strings de código, mismos errores.
"""
import ast
import re

import numpy as np
import pandas as pd


# ── Bug 4 — normalización de nulos en operaciones de texto ──────────────
# `astype(str)` convierte el NaN real en el string "nan" y las operaciones
# de texto dejan cadenas vacías ("" o "   "). Ambas variantes vuelven a
# nulo real (np.nan) para que drop_nulls, /stats y la barra de calidad midan
# de verdad. `read_csv` ya trae "nan"/"" del archivo como NaN: cualquier
# string que sobrevive a esta normalización es dato legítimo del usuario.
# El código generado usa float('nan') para que el script exportado no
# dependa de numpy (solo importa pandas).
_NUL_REGEX = r"(?i)^\s*(?:nan|none|null)?\s*$"


def _normalize_nulls(series):
    """Strings vacíos/de solo espacios y variantes 'nan'/'none'/'null' → NaN.

    Solo columnas de texto (object/str); el resto de tipos pasa intacto.
    """
    if pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype):
        return series.replace(_NUL_REGEX, np.nan, regex=True)
    return series


def _null_code(col):
    return (f"df['{col}'] = df['{col}'].replace(r'{_NUL_REGEX}', float('nan'), regex=True)"
            "  # vacíos/'nan' → nulo real (Bug 4)")


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
        df[name] = _normalize_nulls(split_df[i])
    code_lines = [f"split_df = df['{col}'].str.split('{delimiter}', n={max_split}, expand=True)"]
    for i, name in enumerate(new_col_names):
        code_lines.append(f"df['{name}'] = split_df[{i}]")
        code_lines.append(_null_code(name))
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
    df[col] = _normalize_nulls(df[col])
    after = len(df)
    code = (f"df['{col}'] = df['{col}'].astype(str).str.split('{delimiter}')\n"
            f"df = df.explode('{col}').reset_index(drop=True)\n"
            f"df['{col}'] = df['{col}'].str.strip()  # generó {after - before} filas nuevas\n"
            f"{_null_code(col)}")
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
        df[col] = _normalize_nulls(df[col].astype(str).str.strip())
    code = (f"for col in {cols}:\n"
            f"    df[col] = df[col].astype(str).str.strip()\n"
            f"    df[col] = df[col].replace(r'{_NUL_REGEX}', float('nan'), regex=True)"
            "  # vacíos/'nan' → nulo real (Bug 4)")
    return df, code


def op_clean_newlines(df, params):
    cols = params.get("columns") or list(df.select_dtypes(include=["object", "str"]).columns)
    for col in cols:
        df[col] = _normalize_nulls(df[col].astype(str).str.replace(r'\r\n|\r|\n', ' ', regex=True).str.strip())
    code = (f"for col in {cols}:\n"
            f"    df[col] = df[col].astype(str).str.replace(r'\\r\\n|\\r|\\n', ' ', regex=True).str.strip()\n"
            f"    df[col] = df[col].replace(r'{_NUL_REGEX}', float('nan'), regex=True)"
            "  # vacíos/'nan' → nulo real (Bug 4)")
    return df, code


# ── Texto & Tipos ───────────────────────────────────────────────────────

def op_change_case(df, params):
    col = params.get("column")
    case = params.get("case", "lower")
    fn = {"lower": "lower", "upper": "upper", "title": "title", "capitalize": "capitalize"}.get(case, "lower")
    df[col] = _normalize_nulls(getattr(df[col].astype(str).str, fn)())
    code = f"df['{col}'] = df['{col}'].astype(str).str.{fn}()\n{_null_code(col)}"
    return df, code


def op_replace(df, params):
    col = params.get("column")
    old_val = params.get("old_value", "")
    new_val = params.get("new_value", "")
    df[col] = _normalize_nulls(df[col].astype(str).str.replace(old_val, new_val, regex=False))
    code = (f"df['{col}'] = df['{col}'].astype(str).str.replace('{old_val}', '{new_val}', regex=False)\n"
            f"{_null_code(col)}")
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
        df[col] = _normalize_nulls(df[col].astype(str))
        code = f"df['{col}'] = df['{col}'].astype(str)\n{_null_code(col)}"
    return df, code


# ── Texto & Tipos — Regex Mask (PII) ─────────────────────────────────────
# Presets de detección de PII sin grupos de captura: `str.findall` devuelve
# el texto completo del match y `str.replace` sustituye la coincidencia
# entera. `custom` usa la regex del usuario (validada al vuelo).
_MASK_PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"\+?\d(?:[\s().-]?\d){6,14}",  # 7–15 dígitos, separadores opcionales
    "id": r"\b(?:[A-Za-z]{1,4}-?\d{2,12}|\d{13,19})\b",  # SN-001/X204 o tarjeta
}

# Marcadores de nulo que `astype(str)` materializa en texto (Bug 4, ampliada):
# cubre <NA> (pandas StringDtype) y NaT (fechas) además de nan/none/null.
_MASK_NA_REGEX = r"(?i)^\s*(?:nan|none|null|<na>|nat)\s*$"

_MASK_MAX_CUSTOM_LEN = 500


def op_regex_mask(df, params):
    """Enmascara o extrae PII (email, teléfono, identificador) por regex.

    `mode='mask'` sustituye cada coincidencia en la MISMA columna por
    `fill` (por defecto '****'; cadena vacía = borrar la coincidencia).
    `mode='extract'` escribe la PRIMERA coincidencia de cada fila en una
    columna nueva (`new_column` vacío → `{column}_mask`) y deja la fuente
    intacta. Los nulos reales sobreviven en ambos modos (regla Bug 4).

    Errores (ValueError → 500): columna inexistente, modo inválido,
    patrón desconocido, regex que no compila o que case la cadena vacía
    (enmascararía todo), destino de extracción colisionado y custom > 500.
    """
    col = params.get("column")
    if not isinstance(col, str) or col not in df.columns:
        raise ValueError(f"La columna '{col}' no existe en el dataset.")

    mode = str(params.get("mode") or "mask")
    if mode not in ("mask", "extract"):
        raise ValueError(f"Modo no válido: '{mode}'. Usa 'mask' o 'extract'.")

    pattern_key = str(params.get("pattern") or "email")
    if pattern_key == "custom":
        pat = str(params.get("custom_pattern") or "")
        if not pat:
            raise ValueError("La regex personalizada está vacía.")
        if len(pat) > _MASK_MAX_CUSTOM_LEN:
            raise ValueError(
                f"La regex personalizada supera los {_MASK_MAX_CUSTOM_LEN} caracteres."
            )
    elif pattern_key in _MASK_PATTERNS:
        pat = _MASK_PATTERNS[pattern_key]
    else:
        raise ValueError(f"Patrón desconocido: '{pattern_key}'.")

    try:
        compiled = re.compile(pat)
    except re.error as e:
        raise ValueError(f"Regex no válida: {e}") from None
    if compiled.search(""):
        raise ValueError(
            "La regex coincide con la cadena vacía: enmascararía todo el texto."
        )

    fill = "****" if params.get("mask") is None else str(params.get("mask"))
    new_col = str(params.get("new_column") or "").strip()
    if mode == "extract":
        if not new_col:
            new_col = f"{col}_mask"
        if new_col == col:
            raise ValueError("La columna de destino no puede ser la original.")
        if new_col in df.columns:
            raise ValueError(f"La columna '{new_col}' ya existe. Elige otro nombre.")

    # Orden real: normalizar nulos ANTES de buscar/reemplazar (Bug 4).
    src = df[col].astype(str).replace(_MASK_NA_REGEX, np.nan, regex=True)
    if mode == "mask":
        df[col] = src.str.replace(pat, fill, regex=True)
        code = (f"df[{col!r}] = (df[{col!r}].astype(str)\n"
                f"    .replace(r{_MASK_NA_REGEX!r}, float('nan'), regex=True)\n"
                f"    .str.replace({pat!r}, {fill!r}, regex=True))")
    else:
        df[new_col] = src.str.findall(pat).str[0]
        code = (f"df[{new_col!r}] = (df[{col!r}].astype(str)\n"
                f"    .replace(r{_MASK_NA_REGEX!r}, float('nan'), regex=True)\n"
                f"    .str.findall({pat!r}).str[0])")
    return df, code


# ── Texto & Tipos — Concatenar Columnas ──────────────────────────────────
# Cubre también los marcadores <NA>/<na>/NaT que `astype(str)` materializa
# (Bug 4). El `?` final hace que el grupo sea opcional: la cadena vacía y
# los solo-espacios también son nulo, igual que `_NUL_REGEX`.
_CONCAT_NA_REGEX = r"(?i)^\s*(?:nan|none|null|<na>|nat)?\s*$"


def op_concatenar_columnas(df, params):
    """Concatena 2+ columnas en una nueva con delimitador (op #22).

    Los nulos se omiten al unir (sin delimitadores huérfanos por un nulo
    intermedio o lateral); fila toda nula → nulo real. El orden de la
    unión es el orden de `columns`. `new_name` puede sobrescribir una de
    las columnas seleccionadas (estilo Excel); `drop_sources` elimina las
    originales tras calcular la unión.

    Errores (ValueError → 500): menos de 2 columnas, columnas repetidas,
    columnas inexistentes, nombre vacío y colisión con una columna ajena.
    """
    cols = [str(c) for c in (params.get("columns") or [])]
    delim = params.get("delimiter")
    delim = " " if delim is None else str(delim)  # default = modal; "" explícito une sin separador
    new_name = str(params.get("new_name") or "").strip()
    drop_sources = bool(params.get("drop_sources", False))

    if len(cols) < 2:
        raise ValueError("Elige al menos 2 columnas para concatenar.")
    if len(set(cols)) != len(cols):
        raise ValueError("No repitas columnas: cada columna entra una sola vez.")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"La columna {missing!r} no existe en el dataset.")
    if not new_name:
        raise ValueError("La columna nueva necesita un nombre.")
    if new_name in df.columns and new_name not in cols:
        raise ValueError(f"La columna '{new_name}' ya existe. Elige otro nombre.")

    # Orden real: normalizar nulos por columna ANTES de unir (Bug 4); el
    # generador descarta los NaN de cada fila, así nunca quedan
    # delimitadores huérfanos. `x == x` es el test de no-NaN (NaN != NaN).
    parts = df[cols].astype(str).replace(_CONCAT_NA_REGEX, np.nan, regex=True)
    joined = parts.agg(lambda r: delim.join(x for x in r if x == x), axis=1)
    joined = joined.replace(r"^\s*$", np.nan, regex=True)

    if drop_sources and new_name not in cols:
        df = df.drop(columns=cols)
    df[new_name] = joined

    code = (f"_partes = (df[{cols!r}].astype(str)\n"
            f"    .replace(r{_CONCAT_NA_REGEX!r}, float('nan'), regex=True))\n"
            f"df[{new_name!r}] = (_partes.agg(\n"
            f"    lambda r: {delim!r}.join(x for x in r if x == x), axis=1\n"
            f").replace(r'^\\s*$', float('nan'), regex=True))")
    if drop_sources and new_name not in cols:
        code += f"\ndf = df.drop(columns={cols!r})"
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


def op_group_by(df, params):
    by = params.get("by") or []
    if isinstance(by, str):
        by = [by]
    column = params.get("column")
    func = params.get("func", "sum")
    aggs = {column: func}
    df = df.groupby(by, dropna=False, as_index=False).agg(aggs)
    code = f"df = df.groupby({by}, dropna=False).agg({aggs})  # {len(df)} grupo(s)"
    return df, code


def op_merge(df, params):
    """Cruce Join/Merge del frame activo con el frame derecho (op #19).

    `right_df` y `right_code` los inyecta `app.operation()`; el resto de
    params (`left_on`, `right_on`, `how`, `suffixes`) llega serializado desde
    el modal. Misma columna a ambos lados -> `on=[col]`; distintas ->
    `left_on`/`right_on` (ambas claves quedan en el resultado).
    """
    right = params.get("right_df")
    if right is None:
        raise ValueError("No hay frame derecho cargado para el cruce.")
    left_on = params.get("left_on")
    right_on = params.get("right_on")
    how = params.get("how", "left")
    suffixes = tuple(params.get("suffixes") or ("_x", "_y"))

    if how not in ("inner", "left", "right", "outer"):
        raise ValueError(
            f"Tipo de cruce '{how}' no válido. Usa: inner, left, right u outer."
        )
    if not left_on or not right_on:
        raise ValueError("Debes elegir la columna de cruce en ambos frames.")
    if left_on not in df.columns:
        raise ValueError(f"La columna izquierda '{left_on}' no existe en el dataset activo.")
    if right_on not in right.columns:
        raise ValueError(f"La columna derecha '{right_on}' no existe en el frame derecho.")

    if left_on == right_on:
        merged = df.merge(right, how=how, on=[left_on], suffixes=suffixes)
        keys = f"on=['{left_on}']"
    else:
        merged = df.merge(
            right, how=how, left_on=[left_on], right_on=[right_on], suffixes=suffixes
        )
        keys = f"left_on=['{left_on}'], right_on=['{right_on}']"

    right_code = params.get("right_code")
    load_line = f"df_right = {right_code}\n" if right_code else ""
    code = (
        f"{load_line}"
        f"df = df.merge(df_right, how='{how}', {keys}, suffixes={list(suffixes)})\n"
        f"  # {len(df)} → {len(merged)} filas tras cruce {how}"
    )
    return merged, code


# ── Columna Calculada (op #30) — sandbox del eval() ────────────────────
# Diseño en context/propuesta_tecnica_mejoras.md (4.6): validar el AST ANTES
# de ejecutar. Solo pasan operadores, constantes, nombres de columnas y
# llamadas de la lista blanca. Prohibido acceso a atributos (el vector de
# escape clásico `().__class__.__bases__`), subíndices, lambdas, comprensiones
# y f-strings. Se evalúa sin `__builtins__` y con namespace solo de columnas.

_CALC_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Call, ast.IfExp, ast.Constant, ast.Name, ast.Tuple, ast.List,
    ast.keyword, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub, ast.Not,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
)

# Construcciones con mensaje propio (pase 1) antes del blanqueo genérico.
_CALC_BLOCKED = {
    "Attribute": "no se permite el acceso a atributos con '.'",
    "Subscript": "no se permite el acceso por índice [...]",
    "Lambda": "no se permiten funciones lambda",
    "ListComp": "no se permiten comprensiones",
    "SetComp": "no se permiten comprensiones",
    "DictComp": "no se permiten comprensiones",
    "GeneratorExp": "no se permiten comprensiones",
    "JoinedStr": "no se permiten f-strings",
}

_CALC_FUNCS = {
    # "col" se resuelve en op_calculated_column (cierra sobre el df activo):
    # permite referenciar columnas con espacios: col('Nombre Completo').
    "col": None,
    "abs": abs, "round": round, "len": len, "min": min, "max": max,
    "sum": sum, "int": int, "float": float, "str": str, "bool": bool,
    "log": np.log, "log10": np.log10, "exp": np.exp, "sqrt": np.sqrt,
    "floor": np.floor, "ceil": np.ceil, "sign": np.sign, "where": np.where,
}


def _validate_calc_expr(expr, columns):
    """Parsea y valida la expresión en el sandbox. Devuelve el AST o ValueError."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Expresión no válida: {e.msg}") from None

    # Pase 1: construcciones bloqueadas con mensaje descriptivo.
    for node in ast.walk(tree):
        kind = type(node).__name__
        if kind in _CALC_BLOCKED:
            raise ValueError(f"Expresión no permitida: {_CALC_BLOCKED[kind]}.")

    # Pase 2: blanqueo de nodos + reglas de nombres y llamadas.
    allowed = set(_CALC_ALLOWED_NODES)
    known_names = set(columns) | set(_CALC_FUNCS)
    for node in ast.walk(tree):
        if type(node) not in allowed:
            raise ValueError(
                f"Expresión no permitida: construcción '{type(node).__name__}' no soportada."
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _CALC_FUNCS:
                raise ValueError(
                    "Solo se pueden llamar funciones de la lista blanca: "
                    + ", ".join(sorted(_CALC_FUNCS)) + "."
                )
        if isinstance(node, ast.Name) and node.id not in known_names:
            raise ValueError(
                f"'{node.id}' no es una columna del dataset ni una función permitida."
            )
    return tree


def op_calculated_column(df, params):
    """Columna Calculada (op #30): expresión pandas validada y sandboxeada.

    `name` puede sobrescribir una columna existente (estilo Excel). El código
    generado usa repr() del nombre para que el script exportado siga válido
    aunque el nombre contenga comillas.
    """
    name = str(params.get("name") or "").strip()
    expr = str(params.get("expression") or "").strip()
    if not name:
        raise ValueError("La columna calculada necesita un nombre.")
    if not expr:
        raise ValueError("La expresión está vacía.")

    tree = _validate_calc_expr(expr, df.columns)

    def _col(col_name):
        if not isinstance(col_name, str) or col_name not in df.columns:
            raise ValueError(f"La columna '{col_name}' no existe en el dataset.")
        return df[col_name]

    namespace = {**_CALC_FUNCS, "col": _col, **{c: df[c] for c in df.columns}}
    try:
        values = eval(
            compile(tree, "<calculated_column>", "eval"),
            {"__builtins__": {}},
            namespace,
        )
    except ZeroDivisionError:
        raise ValueError("La expresión divide entre cero.") from None
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Error al evaluar la expresión: {e}") from None

    df[name] = values
    code = f"df[{name!r}] = {expr}"
    return df, code


# ── Reglas & Operaciones — Detectar Outliers ───────────────────────────
_OUTLIER_METHODS = ("zscore", "iqr")
_OUTLIER_DEFAULT_THRESHOLD = {"zscore": 2.5, "iqr": 1.5}


def op_detectar_outliers(df, params):
    """Marca anomalías numéricas con Z-Score o IQR (op #23).

    Por cada columna seleccionada crea `{col}_outlier` (BOOL nullable):
    True si el valor cae fuera del umbral — `|x−media|/std(ddof=0) >
    threshold` en 'zscore', fuera de `[Q1−k·IQR, Q3+k·IQR]` en 'iqr'
    (k = threshold). El valor nulo produce flag nulo; columna con
    dispersión 0 → todo False sin dividir entre cero. La op MARCA, no
    elimina filas (filtra después con filter/drop_rows, deshacible).

    Errores (ValueError → 500): sin columnas, inexistentes, repetidas,
    no numéricas (bool cuenta como no numérico), método desconocido,
    threshold no numérico o ≤ 0 y colisión con `{col}_outlier` existente.
    """
    cols = [str(c) for c in (params.get("columns") or [])]
    if not cols:
        raise ValueError("Elige al menos una columna numérica.")
    if len(set(cols)) != len(cols):
        raise ValueError("No repitas columnas: cada columna se analiza una sola vez.")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"La columna {missing!r} no existe en el dataset.")
    non_numeric = [
        c for c in cols
        if not pd.api.types.is_numeric_dtype(df[c].dtype)
        or pd.api.types.is_bool_dtype(df[c].dtype)
    ]
    if non_numeric:
        raise ValueError(f"Las columnas {non_numeric!r} no son numéricas.")
    collisions = [f"{c}_outlier" for c in cols if f"{c}_outlier" in df.columns]
    if collisions:
        raise ValueError(f"La columna {collisions!r} ya existe. Elimínala antes de volver a marcar.")

    method = str(params.get("method") or "zscore")
    if method not in _OUTLIER_METHODS:
        raise ValueError(f"Método no válido: '{method}'. Usa 'zscore' o 'iqr'.")

    raw = params.get("threshold")
    if raw is None or raw == "":
        threshold = _OUTLIER_DEFAULT_THRESHOLD[method]
    else:
        try:
            threshold = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Umbral no numérico: {raw!r}.") from None
    if not threshold > 0:  # cubre también NaN (NaN > 0 → False)
        raise ValueError("El umbral debe ser mayor que cero.")

    code_lines = []
    for col in cols:
        s = df[col]
        if method == "zscore":
            std = s.std(ddof=0)  # población: estable con pocas filas
            if pd.isna(std) or std == 0:
                flag = pd.Series(False, index=s.index)
            else:
                flag = ((s - s.mean()).abs() / std > threshold)
            expr = (f"((df[{col!r}] - df[{col!r}].mean()).abs() "
                    f"/ df[{col!r}].std(ddof=0) > {threshold!r})")
        else:
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            if pd.isna(iqr) or iqr == 0:
                flag = pd.Series(False, index=s.index)
            else:
                flag = (s < q1 - threshold * iqr) | (s > q3 + threshold * iqr)
            expr = (f"((df[{col!r}] < df[{col!r}].quantile(0.25) - {threshold!r} * "
                    f"(df[{col!r}].quantile(0.75) - df[{col!r}].quantile(0.25))) "
                    f"| (df[{col!r}] > df[{col!r}].quantile(0.75) + {threshold!r} * "
                    f"(df[{col!r}].quantile(0.75) - df[{col!r}].quantile(0.25))))")
        n_flags = int(flag.sum())
        out = f"{col}_outlier"
        df[out] = flag.astype("boolean").where(s.notna())
        # El código generado omite la rama de dispersión 0: 0/0 → NaN →
        # la comparación es False, mismo resultado final que la rama.
        code_lines.append(
            f"df[{out!r}] = ({expr}).astype('boolean').where(df[{col!r}].notna())"
            f"  # {n_flags} outlier(s)"
        )
    return df, "\n".join(code_lines)


# ── Sampling (op #24) ──────────────────────────────────────────────────
# Roadmap "Sampling": head, tail, random(n) y stratified(by=col). El seed
# fijo (42) hace el muestreo determinista: la receta .catflip.json y el
# script exportado reproducen exactamente las mismas filas.
_SAMPLING_MODES = ("head", "tail", "random", "stratified")
_SAMPLING_SEED = 42


def op_sampling(df, params):
    """Muestrea filas del dataset (op #24).

    `mode`:
      - 'head' / 'tail': primeras/últimas `n` filas (pandas recorta solo
        si n > filas, consistente con el resto del registro).
      - 'random': `df.sample(n, random_state=42)` — seed fijo para que la
        receta sea reproducible; n se recorta al tamaño disponible.
      - 'stratified': `n` filas POR ESTRATO de la columna `by` (nulos
        incluidos, `dropna=False`), mismo seed; cada estrato recorta a
        `min(n, len(estrato))`.

    Errores (ValueError → 500): mode desconocido, n no entero o < 1,
    'stratified' sin `by` o con columna inexistente.
    """
    mode = str(params.get("mode") or "head")
    if mode not in _SAMPLING_MODES:
        raise ValueError(
            f"Modo de muestreo no válido: '{mode}'. "
            f"Usa 'head', 'tail', 'random' o 'stratified'."
        )
    raw_n = params.get("n", 1)
    try:
        n = int(raw_n)
    except (TypeError, ValueError):
        raise ValueError(f"n debe ser un número entero, no {raw_n!r}.") from None
    if n < 1:
        raise ValueError("n debe ser al menos 1.")

    total = len(df)
    if mode == "head":
        k = min(n, total)
        df = df.head(n).reset_index(drop=True)
        code = f"df = df.head({n})  # primeras {k} de {total} filas"
    elif mode == "tail":
        k = min(n, total)
        df = df.tail(n).reset_index(drop=True)
        code = f"df = df.tail({n})  # últimas {k} de {total} filas"
    elif mode == "random":
        k = min(n, total)
        df = df.sample(n=k, random_state=_SAMPLING_SEED).reset_index(drop=True)
        code = (f"df = df.sample(n={k}, random_state={_SAMPLING_SEED})"
                f"  # {k} de {total} filas, seed fijo { _SAMPLING_SEED } para reproducibilidad")
    else:  # stratified
        by = params.get("by")
        if not by:
            raise ValueError("El modo 'stratified' requiere la columna por la cual estratificar ('by').")
        if by not in df.columns:
            raise ValueError(f"La columna {by!r} no existe en el dataset.")
        sizes = df.groupby(by, dropna=False).size()
        if df.empty:
            return df.copy(), f"# sampling stratified por {by!r}: dataset vacío, nada que muestrear"
        # pd.concat en vez de groupby().apply(): en pandas 3.0 apply excluye
        # la columna de agrupación de los grupos (include_groups eliminado).
        df = pd.concat(
            [
                g.sample(n=min(len(g), n), random_state=_SAMPLING_SEED)
                for _, g in df.groupby(by, dropna=False)
            ]
        ).reset_index(drop=True)
        code = (
            f"df = pd.concat([g.sample(n=min(len(g), {n}), random_state={_SAMPLING_SEED}) "
            f"for _, g in df.groupby({by!r}, dropna=False)]).reset_index(drop=True)"
            f"  # {n} por estrato de {by!r} ({len(sizes)} estrato(s)), "
            f"{len(df)} filas"
        )
    return df, code


# ── Auto-mapeo de tipos al cargar (heurística de esquema completo) ─────
# Roadmap "Auto-Mapear tipos": extiende la detección de fechas a todo el
# esquema. Para cada columna de texto se prueban, en orden, las tres
# conversiones que `change_type` sabe aplicar: fecha, entero y decimal.
# Criterio común: ≥90% del sample (hasta 200 valores no nulos) debe
# convertirse sin coercionar a nulo — nunca se sugiere algo que pandas no
# podría convertir de verdad. NO convierte nada: la conversión la decide el
# usuario (barra de sugerencia → op change_type con el dtype sugerido).
# Los nombres de columna no participan en la decisión: un nombre sugerente
# no garantiza que la conversión sea correcta; los valores sí lo prueban.

# Sin grupo `(?x)`: pandas `.str.match()` exige que `pat.flags` coincida con
# `re.U`, y `VERBOSE` lo rompe (ValueError en pandas ≥2).
_DATE_SHAPE = re.compile(
    r"^\s*(?:"
    r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"  # ISO (+hora opcional)
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"                                # 31/12/2026, 31.12.26
    r"|\d{1,2}\s+[A-Za-z]{3,9}(?:\s+\d{2,4})?"                          # 5 ene 2026
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"                               # Jan 5, 2026
    r")\s*$"
)

# Subforma ISO (año primero): inequívoca, no necesita dayfirst. Ver
# detect_type_suggestions: con dayfirst=True pandas infiere "%Y-%d-%m" para
# una columna ISO y las fechas con día > 12 caen a NaT (o se interpretan
# volteadas) — bug latente desde la detección de fechas original.
_ISO_SHAPE = re.compile(
    r"^\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?\s*$"
)


def _numeric_kind(sample, min_pct):
    """Conversión numérica del sample. Devuelve (dtype, pct) o (None, 0).

    'int' si todos los valores convertidos son integrales, 'float' si algún
    valor tiene parte decimal. Un porcentaje de convertibles por debajo de
    `min_pct` descarta la sugerencia entera.
    """
    parsed = pd.to_numeric(sample, errors="coerce")
    ok = 1 - (int(parsed.isna().sum()) / len(parsed))
    if ok < min_pct:
        return None, 0
    valid = parsed.dropna()
    kind = "int" if (valid % 1 == 0).all() else "float"
    return kind, int(round(ok * 100))


def detect_type_suggestions(df, max_sample=200, min_pct=0.9, max_cols=10):
    """Heurística de esquema completo: tipos sugeridos para texto (auto-mapeo).

    Devuelve, por columna object/string con ≥2 valores no nulos, la
    sugerencia de `change_type` más específica que sus valores permiten
    (primer match gana): datetime (doble filtro: forma de fecha +
    `pd.to_datetime(..., errors='coerce', dayfirst=True)` sin NaT) y, si no,
    int/float vía `pd.to_numeric(..., errors='coerce')`. El prefiltro por
    forma de fecha evita falsos positivos clásicos: IDs, números-texto
    ("100"), partes de teléfono y columnas ya tipadas por pandas no llegan
    nunca al parseo (dtype no-texto se descarta antes). Cada sugerencia:
    {"column", "sample", "pct", "suggested_dtype"}. Máximo `max_cols`.
    """
    suggestions = []
    for col in df.columns:
        if len(suggestions) >= max_cols:
            break
        series = df[col]
        if not (pd.api.types.is_object_dtype(series.dtype)
                or pd.api.types.is_string_dtype(series.dtype)):
            continue
        sample = series.dropna().astype(str).head(max_sample)
        if len(sample) < 2:
            continue

        # 1) Fecha: regla más específica, se prueba primero.
        if sample.str.match(_DATE_SHAPE).mean() >= min_pct:
            # ISO-dominante → dayfirst=False (formato inequívoco); el resto
            # (31/12/2026, 5 ene…) sigue siendo day-first.
            dayfirst = sample.str.match(_ISO_SHAPE).mean() < 0.5
            parsed = pd.to_datetime(sample, errors="coerce", dayfirst=dayfirst)
            ok = 1 - (int(parsed.isna().sum()) / len(parsed))
            if ok >= min_pct:
                suggestions.append({
                    "column": str(col),
                    "sample": str(sample.iloc[0]),
                    "pct": int(round(ok * 100)),
                    "suggested_dtype": "datetime",
                })
                continue

        # 2) Numérico: entero si todo es integral, decimal si hay fracciones.
        kind, pct = _numeric_kind(sample, min_pct)
        if kind:
            suggestions.append({
                "column": str(col),
                "sample": str(sample.iloc[0]),
                "pct": pct,
                "suggested_dtype": kind,
            })
    return suggestions


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
    "regex_mask": op_regex_mask,
    "concatenar_columnas": op_concatenar_columnas,
    # Reglas & Operaciones
    "filter": op_filter,
    "sort": op_sort,
    "group_by": op_group_by,
    "merge": op_merge,
    "calculated_column": op_calculated_column,
    "detectar_outliers": op_detectar_outliers,
    "sampling": op_sampling,
}
