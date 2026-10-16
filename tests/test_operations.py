"""Tests de la API de Cat_flip: operaciones, rutas y caminos de error.

Patrón: parametrizar una operación por caso (pytest + conftest que
resetea los globals de `app` en cada test → aislamiento real).
"""
import io

import pandas as pd
import pytest

import app as app_module

BASE_CSV = (
    "Nombre,Edad,Ciudad,Ventas\n"
    "Alice,30,Madrid,100\n"
    "Bob,25,Barcelona,200\n"
    "Charlie,35,Madrid,150\n"
)


# ── helpers ────────────────────────────────────────────────────────────

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


def check(resp, expected):
    """Verifica contrato + checks específicos del caso."""
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["last_code"], "toda operación debe generar código"
    data = payload["data"]

    if "rows" in expected:
        assert data["total_rows"] == expected["rows"]
    for col in expected.get("cols_in", []):
        assert col in data["columns"], f"falta columna {col!r}"
    for col in expected.get("cols_out", []):
        assert col not in data["columns"], f"sobra columna {col!r}"
    for col, dtype in expected.get("dtypes", {}).items():
        assert data["dtypes"][col] == dtype
    for row_idx, col, value in expected.get("cells", []):
        i = data["columns"].index(col)
        assert data["data"][row_idx][i] == value
    if "code" in expected:
        assert expected["code"] in payload["last_code"]
    # historial: 1 estado tras upload + 1 por operación
    assert len(app_module.history) == 2
    return payload


# ── 17 operaciones (happy path por operación) ─────────────────────────

OP_CASES = [
    pytest.param(
        "unpivot",
        {"id_cols": ["Nombre"], "var_name": "Variable", "value_name": "Valor"},
        "Nombre,2024,2025\nA,1,2\nB,3,4\n",
        {"rows": 4, "cols_in": ["Variable", "Valor"], "code": "melt"},
        id="unpivot",
    ),
    pytest.param(
        "pivot",
        {"index": "Nombre", "columns": "Ciudad", "values": "Ventas"},
        "Nombre,Ciudad,Ventas\nAlice,Madrid,100\nBob,Barcelona,200\n",
        {"cols_in": ["Madrid", "Barcelona"], "code": "pivot_table"},
        id="pivot",
    ),
    pytest.param(
        "split_column",
        {"column": "Nombre Completo", "delimiter": " ",
         "col_prefix": "nombre", "max_split": 1},
        "Nombre Completo,Ciudad\nAna Lopez,Madrid\nLuis Ruiz,Sevilla\n",
        {"cols_in": ["nombre_1", "nombre_2"], "rows": 2},
        id="split_column",
    ),
    pytest.param(
        "drop_nulls",
        {"columns": ["B"], "how": "any"},
        "A,B\n1,\n2,x\n3,y\n",
        {"rows": 2, "code": "dropna"},
        id="drop_nulls",
    ),
    pytest.param(
        "drop_duplicates",
        {"columns": ["A", "B"]},
        "A,B\n1,x\n1,x\n2,y\n",
        {"rows": 2, "code": "drop_duplicates"},
        id="drop_duplicates",
    ),
    pytest.param(
        "rename_column",
        {"old_name": "Edad", "new_name": "Years"},
        BASE_CSV,
        {"cols_in": ["Years"], "cols_out": ["Edad"]},
        id="rename_column",
    ),
    pytest.param(
        "drop_column",
        {"column": "Ciudad"},
        BASE_CSV,
        {"cols_out": ["Ciudad"]},
        id="drop_column",
    ),
    pytest.param(
        "filter",
        {"column": "Ciudad", "operator": "!=", "value": "Madrid"},
        BASE_CSV,
        {"rows": 1, "code": "!="},
        id="filter_not_equal",
    ),
    pytest.param(
        "filter",
        {"column": "Ciudad", "operator": "contiene", "value": "rid"},
        BASE_CSV,
        {"rows": 2, "code": "contains"},
        id="filter_contains",
    ),
    pytest.param(
        "filter",
        {"column": "Ciudad", "operator": "no contiene", "value": "rid"},
        BASE_CSV,
        {"rows": 1},
        id="filter_not_contains",
    ),
    pytest.param(
        "filter",
        {"column": "Ventas", "operator": ">", "value": "120"},
        BASE_CSV,
        {"rows": 2},
        id="filter_gt",
    ),
    pytest.param(
        "filter",
        {"column": "Ventas", "operator": "<", "value": "150"},
        BASE_CSV,
        {"rows": 1},
        id="filter_lt",
    ),
    pytest.param(
        "trim",
        {"columns": ["Nombre"]},
        "Nombre\n Alice \nBob  \n",
        {"cells": [(0, "Nombre", "Alice"), (1, "Nombre", "Bob")], "code": "strip"},
        id="trim",
    ),
    pytest.param(
        "change_case",
        {"column": "Nombre", "case": "upper"},
        "Nombre\nana LOPEZ\n",
        {"cells": [(0, "Nombre", "ANA LOPEZ")], "code": "upper"},
        id="change_case_upper",
    ),
    pytest.param(
        "change_case",
        {"column": "Nombre", "case": "lower"},
        "Nombre\nana LOPEZ\n",
        {"cells": [(0, "Nombre", "ana lopez")], "code": "lower"},
        id="change_case_lower",
    ),
    pytest.param(
        "change_case",
        {"column": "Nombre", "case": "title"},
        "Nombre\nana LOPEZ\n",
        {"cells": [(0, "Nombre", "Ana Lopez")], "code": "title"},
        id="change_case_title",
    ),
    pytest.param(
        "change_case",
        {"column": "Nombre", "case": "capitalize"},
        "Nombre\nana LOPEZ\n",
        {"cells": [(0, "Nombre", "Ana lopez")], "code": "capitalize"},
        id="change_case_capitalize",
    ),
    pytest.param(
        "clean_newlines",
        {"columns": ["A"]},
        'A,B\n"foo\nbar",x\n',
        {"cells": [(0, "A", "foo bar")], "code": "replace"},
        id="clean_newlines",
    ),
    pytest.param(
        "replace",
        {"column": "Ciudad", "old_value": "Madrid", "new_value": "Lisboa"},
        BASE_CSV,
        {"cells": [(0, "Ciudad", "Lisboa")], "code": "regex=False"},
        id="replace",
    ),
    pytest.param(
        "change_type",
        {"column": "Edad", "dtype": "int"},
        BASE_CSV,
        {"dtypes": {"Edad": "INT"}, "code": "Int64"},
        id="change_type_int",
    ),
    pytest.param(
        "change_type",
        {"column": "Valor", "dtype": "float"},
        "Valor\n1.5\n2.5\n",
        {"dtypes": {"Valor": "FLOAT"}},
        id="change_type_float",
    ),
    pytest.param(
        "change_type",
        {"column": "Nombre", "dtype": "str"},
        BASE_CSV,
        {"dtypes": {"Nombre": "STR"}},
        id="change_type_str",
    ),
    pytest.param(
        "change_type",
        {"column": "Fecha", "dtype": "datetime"},
        "Fecha\n2026-01-05\n2026-01-06\n",
        {"dtypes": {"Fecha": "DATE"}, "code": "to_datetime"},
        id="change_type_datetime",
    ),
    pytest.param(
        "sort",
        {"column": "Ventas", "ascending": True},
        BASE_CSV,
        {"cells": [(0, "Ventas", "100"), (2, "Ventas", "200")],
         "code": "sort_values"},
        id="sort_ascending",
    ),
    pytest.param(
        "sort",
        {"column": "Ventas", "ascending": False},
        BASE_CSV,
        {"cells": [(0, "Ventas", "200"), (2, "Ventas", "100")]},
        id="sort_descending",
    ),
    pytest.param(
        "split_to_rows",
        {"column": "Tags", "delimiter": ",", "strip": True},
        'Tags\n"a, b,c"\n',
        {"rows": 3, "code": "explode"},
        id="split_to_rows",
    ),
    pytest.param(
        "drop_rows",
        {"position": "top", "n": 1},
        BASE_CSV,
        {"rows": 2, "cells": [(0, "Nombre", "Bob")]},
        id="drop_rows_top",
    ),
    pytest.param(
        "drop_rows",
        {"position": "bottom", "n": 1},
        BASE_CSV,
        {"rows": 2, "cells": [(0, "Nombre", "Alice")]},
        id="drop_rows_bottom",
    ),
    pytest.param(
        "set_header",
        {"row_index": 0},
        "Col1,Col2\nNombre,Valor\nA,1\n",
        {"rows": 1, "cols_in": ["Nombre", "Valor"], "cols_out": ["Col1"]},
        id="set_header",
    ),
]


@pytest.mark.parametrize("op_name,params,csv_text,expected", OP_CASES)
def test_operation_scenario_returns_expected(client, op_name, params, csv_text, expected):
    upload(client, csv_text)
    resp = op(client, op_name, params)
    check(resp, expected)


def test_sort_mixed_types_falls_back_to_textual_order(client):
    """Rama TypeError de sort: columnas con tipos mixtos no rompen el pipeline."""
    # unpivot con dtypes distintos → columna object con int y str
    upload(client, "A,B,C\nx,10,p\ny,20,q\n")
    client.post(
        "/operation",
        json={"operation": "unpivot", "params": {"id_cols": ["A"]}},
    )
    resp = op(client, "sort", {"column": "Valor", "ascending": True})
    assert resp.status_code == 200, resp.get_json()
    assert "tipos mixtos" in resp.get_json()["last_code"]


def test_two_operations_accumulate_code_and_history(client):
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    payload = op(client, "sort", {"column": "Ventas", "ascending": True})
    assert resp_ok(payload)
    body = payload.get_json()
    assert "# trim" in body["code"] and "# sort" in body["code"]
    assert len(app_module.history) == 3  # upload + 2 ops
    assert len(app_module.code_log) == 3


def resp_ok(resp):
    assert resp.status_code == 200, resp.get_json()
    return True


# ── rutas ──────────────────────────────────────────────────────────────

def test_index_renders_template(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type


def test_upload_semicolon_csv_autodetects_separator(client):
    resp = upload(client, "a;b\n1;2\n3;4\n")
    data = resp.get_json()["data"]
    assert data["columns"] == ["a", "b"]
    assert "sep=';'" in resp.get_json()["code"]


def test_upload_xlsx_accepts_sheets(client):
    buf = io.BytesIO()
    pd.DataFrame({"Nombre": ["Ana"], "Ventas": [10]}).to_excel(buf, index=False)
    buf.seek(0)
    resp = client.post(
        "/upload",
        data={"file": (buf, "libro.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert resp.get_json()["data"]["columns"] == ["Nombre", "Ventas"]


def test_get_sheets_returns_sheet_names(client):
    buf = io.BytesIO()
    pd.DataFrame({"a": [1]}).to_excel(buf, index=False)
    buf.seek(0)
    resp = client.post(
        "/get_sheets",
        data={"file": (buf, "libro.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    sheets = resp.get_json()["sheets"]
    assert isinstance(sheets, list) and len(sheets) >= 1


def test_export_xlsx_downloads_file(client):
    upload(client)
    resp = client.post("/export", json={"format": "xlsx", "filename": "salida"})
    assert resp.status_code == 200
    assert "spreadsheet" in resp.content_type
    assert len(resp.data) > 0


def test_undo_after_one_operation_reverts_state(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    resp = client.post("/undo")
    assert resp.status_code == 200
    assert "Ciudad" in resp.get_json()["data"]["columns"]


# ── df_to_json (vía /upload) ──────────────────────────────────────────

def test_df_to_json_classifies_bool_column(client):
    resp = upload(client, "Flag\nTrue\nFalse\n")
    assert resp.get_json()["data"]["dtypes"]["Flag"] == "BOOL"


def test_df_to_json_truncates_large_datasets(client):
    csv_text = "n\n" + "".join(f"{i}\n" for i in range(600))
    resp = upload(client, csv_text)
    data = resp.get_json()["data"]
    assert data["total_rows"] == 600
    assert data["truncated"] is True
    assert len(data["data"]) == 500


# ── caminos de error ─────────────────────────────────────────────────

def test_operation_without_data_returns_400(client):
    resp = op(client, "trim", {})
    assert resp.status_code == 400
    assert "No hay datos" in resp.get_json()["error"]


def test_operation_unknown_returns_400(client):
    upload(client)
    resp = op(client, "no_existe", {})
    assert resp.status_code == 400
    assert "no reconocida" in resp.get_json()["error"]


def test_operation_invalid_params_returns_500(client):
    upload(client)
    resp = op(client, "filter", {"column": "ColumnaInexistente"})
    assert resp.status_code == 500
    assert "error" in resp.get_json()


def test_undo_exhausted_returns_400(client):
    upload(client)  # history = [df] → no hay nada que deshacer
    resp = client.post("/undo")
    assert resp.status_code == 400
    assert "deshacer" in resp.get_json()["error"]


def test_upload_unsupported_format_returns_400(client):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"cualquier cosa"), "archivo.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "Formato no soportado" in resp.get_json()["error"]


def test_export_without_data_returns_400(client):
    resp = client.post("/export", json={"format": "csv"})
    assert resp.status_code == 400


def test_export_script_without_data_returns_400(client):
    resp = client.post("/export_script", json={"filename": "x"})
    assert resp.status_code == 400
    assert "pipeline" in resp.get_json()["error"]


def test_stats_without_data_returns_400(client):
    resp = client.get("/stats")
    assert resp.status_code == 400


def test_stats_with_data_returns_metrics(client):
    upload(client, "A,B\n1,\n2,x\n")
    resp = client.get("/stats")
    assert resp.status_code == 200
    stats = resp.get_json()["stats"]
    assert stats["B"]["nulls"] == 1  # celda vacía en B
    assert stats["B"]["unique"] == 1
    assert stats["A"]["min"] == 1.0


def test_stats_duplicates_and_categorical_top(client):
    """F3.2: duplicates global + top-5 valores solo en columnas categóricas."""
    upload(client, "A,B\n1,x\n1,x\n2,y\n")
    data = client.get("/stats").get_json()
    assert data["duplicates"] == 1  # la fila 2 repite a la 1
    assert data["stats"]["B"]["top"] == [["x", 2], ["y", 1]]
    assert "top" not in data["stats"]["A"]  # numérica → sin top


def test_stats_duplicates_zero_and_all_null_column(client):
    upload(client, "A,B\n1,\n2,\n")
    data = client.get("/stats").get_json()
    assert data["duplicates"] == 0
    assert data["stats"]["B"]["top"] == []  # todo nulo → sin valores
    assert "top" not in data["stats"]["A"]


def test_stats_top_limits_five_and_bool(client):
    upload(client, "C,B\na,TRUE\nb,FALSE\na,TRUE\nc,TRUE\na,FALSE\nd,TRUE\ne,TRUE\n")
    data = client.get("/stats").get_json()
    top_c = data["stats"]["C"]["top"]
    assert top_c[0] == ["a", 3]
    assert len(top_c) == 5  # nunca más de 5
    top_b = dict(data["stats"]["B"]["top"])
    # pandas convierte el bool a str canónico: "True"/"False" (no el literal del CSV)
    assert top_b["True"] == 5 and top_b["False"] == 2


# ── Registro de operaciones (refactor P2) ───────────────────────────

def test_registry_expone_las_19_operaciones():
    """El registro define exactamente las ops del contrato UI/API.

    Protege contra borrados accidentales al mover handlers en operations.py.
    """
    from operations import OPS

    expected = {
        "unpivot", "pivot", "split_column", "split_to_rows", "set_header",
        "drop_nulls", "drop_duplicates", "drop_rows", "trim", "clean_newlines",
        "change_case", "replace", "rename_column", "drop_column", "change_type",
        "filter", "sort", "group_by", "merge",
    }
    assert set(OPS) == expected
    assert all(callable(fn) for fn in OPS.values())
