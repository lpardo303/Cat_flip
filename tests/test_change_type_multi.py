"""Tests del cambio de tipo (op 15): selección múltiple + catálogo extendido.

Cubre la forma legada `column` (intacta para recetas/badges/sugerencias),
la nueva forma `columns` (lista, aplicada en un solo paso de receta), las
10 grafías del catálogo con sus alias, la semántica del booleano nullable
(coerce: lo no reconocido → ``<NA>``) y de `category` (normalización de
marcadores de nulo previos, regla Bug 4), la paridad del código generado
con ``exec`` y todos los ValueError que el endpoint traduce a 500 sin
mutar el estado.
"""
import io
import json as jsonlib

import pandas as pd
import pytest

import app as app_module
from operations import OPS

BASE_CSV = (
    "nombre,edad,saldo,fecha,activo\n"
    "Ana,30,10.5,2026-01-05,TRUE\n"
    "Luis,25,20.5,2026-01-06,False\n"
    ",40,,2026-01-07,1\n"
)


def upload(client, csv_text=BASE_CSV, filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def op(client, operation, params=None):
    return client.post(
        "/operation", json={"operation": operation, "params": params or {}}
    )


def export_recipe(client, filename="receta"):
    return client.post("/export_recipe", json={"filename": filename})


def apply_recipe(client, recipe):
    return client.post("/apply_recipe", json=recipe)


# ── Selección múltiple ────────────────────────────────────────────────
def test_multi_applies_dtype_to_every_marked_column(client):
    upload(client)
    resp = op(client, "change_type", {"columns": ["edad", "fecha"], "dtype": "str"})
    assert resp.status_code == 200, resp.get_json()
    dtypes = resp.get_json()["data"]["dtypes"]
    assert dtypes["edad"] == "STR" and dtypes["fecha"] == "STR"
    data = resp.get_json()["data"]
    assert data["data"][0][data["columns"].index("edad")] == "30"
    assert data["data"][0][data["columns"].index("fecha")] == "2026-01-05"


def test_multi_float_on_numeric_columns(client):
    upload(client)
    resp = op(client, "change_type", {"columns": ["edad", "saldo"], "dtype": "float"})
    assert resp.status_code == 200, resp.get_json()
    dtypes = resp.get_json()["data"]["dtypes"]
    assert dtypes["edad"] == "FLOAT" and dtypes["saldo"] == "FLOAT"
    assert str(app_module.current_df["edad"].dtype) == "float64"
    vals = app_module.current_df["saldo"].tolist()
    assert vals[:2] == [10.5, 20.5] and pd.isna(vals[2])


def test_multi_is_a_single_recipe_step(client):
    """Una operación multi = una entrada de history y una de op_history."""
    upload(client)
    resp = op(client, "change_type", {"columns": ["edad", "fecha"], "dtype": "str"})
    assert resp.status_code == 200, resp.get_json()
    assert len(app_module.history) == 2  # upload + 1 op
    assert len(app_module.op_history) == 1  # la receta ve UN paso


def test_multi_code_lists_every_column(client):
    upload(client)
    resp = op(client, "change_type", {"columns": ["edad", "saldo"], "dtype": "float"})
    assert resp.status_code == 200, resp.get_json()
    code = resp.get_json()["last_code"]
    assert "df['edad'] = pd.to_numeric(df['edad']" in code
    assert "df['saldo'] = pd.to_numeric(df['saldo']" in code


# ── Forma legada (column única) ───────────────────────────────────────
def test_legacy_column_param_still_works(client):
    upload(client)
    resp = op(client, "change_type", {"column": "edad", "dtype": "int"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["dtypes"]["edad"] == "INT"


def test_missing_dtype_defaults_to_str(client):
    upload(client)
    resp = op(client, "change_type", {"column": "edad"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["dtypes"]["edad"] == "STR"


# ── Catálogo: alias ───────────────────────────────────────────────────
def test_alias_results_match_canonical():
    """string≡ str, Int64 ≡ int, datetime64 ≡ datetime, boolean ≡ bool."""
    df = pd.read_csv(io.StringIO(BASE_CSV))
    for alias, canonical, column in [
        ("string", "str", "nombre"),
        ("Int64", "int", "edad"),
        ("datetime64", "datetime", "fecha"),
        ("boolean", "bool", "activo"),
    ]:
        out_a, _ = OPS["change_type"](df.copy(), {"column": column, "dtype": alias})
        out_c, _ = OPS["change_type"](df.copy(), {"column": column, "dtype": canonical})
        pd.testing.assert_series_equal(out_a[column], out_c[column])


def test_unknown_dtype_error_lists_the_catalog():
    df = pd.read_csv(io.StringIO(BASE_CSV))
    try:
        OPS["change_type"](df, {"column": "edad", "dtype": "banana"})
    except ValueError as e:
        msg = str(e)
        assert "banana" in msg and "desconocido" in msg
        # el catálogo completo aparece en el mensaje
        for spelling in ("Int64", "bool", "boolean", "category",
                         "datetime", "datetime64", "float", "int",
                         "str", "string"):
            assert spelling in msg
    else:
        raise AssertionError("dtype desconocido debía lanzar ValueError")


# ── Booleano nullable (coerce) ─────────────────────────────────────────
def test_bool_maps_recognized_forms_and_coerces_the_rest():
    df = pd.DataFrame({"v": [
        "TRUE", "t", "yes", "y", "1", "1.0",
        "FALSE", "f", "no", "n", "0", "0.0",
        "banana", "", None,
    ]})
    out, _ = OPS["change_type"](df, {"column": "v", "dtype": "bool"})
    assert str(out["v"].dtype) == "boolean"
    assert list(out["v"]) == (
        [True] * 6 + [False] * 6 + [pd.NA, pd.NA, pd.NA]
    )


def test_bool_coerces_unknown_numeric_values():
    df = pd.DataFrame({"n": [1, 0, 2]})
    out, _ = OPS["change_type"](df, {"column": "n", "dtype": "bool"})
    assert str(out["n"].dtype) == "boolean"
    assert list(out["n"]) == [True, False, pd.NA]


def test_bool_via_endpoint_gets_bool_badge(client):
    upload(client, csv_text="flag\nTRUE\nFalse\n1\n", filename="flag.csv")
    resp = op(client, "change_type", {"columns": ["flag"], "dtype": "bool"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["dtypes"]["flag"] == "BOOL"


def test_bool_generated_code_executes_identically():
    df = pd.read_csv(io.StringIO(BASE_CSV))
    out, code = OPS["change_type"](df.copy(), {"columns": ["activo"], "dtype": "bool"})
    compile(code, "<generated>", "exec")
    ns = {"df": df.copy(), "pd": pd}
    exec(code, ns)  # noqa: S102 — el script exportado hace exactamente esto
    pd.testing.assert_frame_equal(ns["df"], out)


# ── Categoría ──────────────────────────────────────────────────────────
def test_category_keeps_values(client):
    upload(client)
    resp = op(client, "change_type", {"columns": ["nombre"], "dtype": "category"})
    assert resp.status_code == 200, resp.get_json()
    cat = app_module.current_df["nombre"]
    assert str(cat.dtype) == "category"
    vals = list(cat)
    assert vals[:2] == ["Ana", "Luis"]
    assert pd.isna(vals[2])


def test_category_normalizes_previous_null_markers():
    """Los marcadores ('nan', 'None', vacíos) no se convierten en categoría."""
    df = pd.DataFrame({"c": ["x", "y", "nan", "None", "", " "]})
    out, _ = OPS["change_type"](df, {"column": "c", "dtype": "category"})
    assert str(out["c"].dtype) == "category"
    assert set(out["c"].dropna().tolist()) == {"x", "y"}
    assert out["c"].isna().sum() == 4


def test_category_on_numeric_column_skips_null_normalization():
    """En columnas no-texto el código es solo astype (sin línea de nulos)."""
    df = pd.DataFrame({"n": [1, 2, 3]})
    out, code = OPS["change_type"](df, {"column": "n", "dtype": "category"})
    assert str(out["n"].dtype) == "category"
    assert code == "df['n'] = df['n'].astype('category')"


def test_category_generated_code_executes_identically():
    df = pd.read_csv(io.StringIO(BASE_CSV))
    out, code = OPS["change_type"](df.copy(), {"columns": ["nombre"], "dtype": "category"})
    compile(code, "<generated>", "exec")
    ns = {"df": df.copy(), "pd": pd}
    exec(code, ns)  # noqa: S102
    pd.testing.assert_frame_equal(ns["df"], out)


# ── Paridad del código multi generado ─────────────────────────────────
def test_multi_float_generated_code_executes_identically(client):
    upload(client)
    resp = op(client, "change_type", {"columns": ["edad", "saldo"], "dtype": "float"})
    assert resp.status_code == 200, resp.get_json()
    code = resp.get_json()["last_code"]
    compile(code, "<generated>", "exec")
    ns = {"df": pd.read_csv(io.StringIO(BASE_CSV)), "pd": pd}
    exec(code, ns)  # noqa: S102
    pd.testing.assert_frame_equal(ns["df"], app_module.current_df)


# ── Errores (500 con mensaje, sin mutar el estado) ────────────────────
@pytest.mark.parametrize(
    "params,fragment",
    [
        ({"column": "edad", "columns": ["edad"], "dtype": "int"},
         "exactamente una columna"),
        ({}, "exactamente una columna"),
        ({"columns": [], "dtype": "int"}, "al menos una columna"),
        ({"columns": "edad", "dtype": "int"}, "al menos una columna"),
        ({"columns": [1, 2], "dtype": "int"}, "nombres de columna"),
        ({"columns": ["edad", "edad"], "dtype": "int"}, "No repitas"),
        ({"columns": ["Fantasma"], "dtype": "int"}, "inexistente"),
        ({"column": "Fantasma", "dtype": "int"}, "inexistente"),
        ({"column": "edad", "dtype": "banana"}, "desconocido"),
    ],
    ids=[
        "both_params", "neither", "empty_list", "not_a_list", "not_strings",
        "duplicated", "unknown_in_list", "unknown_legacy", "unknown_dtype",
    ],
)
def test_errors_are_500_without_state(client, params, fragment):
    upload(client)
    resp = op(client, "change_type", params)
    assert resp.status_code == 500
    assert fragment in resp.get_json()["error"]
    assert len(app_module.history) == 1  # solo el upload, sin estado parcial


# ── Receta round-trip con `columns` ───────────────────────────────────
def test_recipe_round_trip_with_columns(client):
    upload(client)
    resp = op(client, "change_type", {"columns": ["edad", "fecha"], "dtype": "str"})
    assert resp.status_code == 200, resp.get_json()
    expected = app_module.current_df.copy()

    recipe = jsonlib.loads(export_recipe(client).data)
    assert recipe["steps"] == [{
        "op": "change_type",
        "params": {"columns": ["edad", "fecha"], "dtype": "str"},
    }]

    upload(client)  # estado limpio
    resp = apply_recipe(client, recipe)
    assert resp.status_code == 200, resp.get_json()
    pd.testing.assert_frame_equal(app_module.current_df, expected)
