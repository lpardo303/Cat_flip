"""Tests del diff entre dos estados `POST /step_diff` (roadmap diff de paso).

El endpoint compara los snapshots `history[index]` (antes) y
`history[index + 1]` (después) — los mismos que usa el undo — y devuelve un
resumen (formas, columnas, deltas por columna) más una muestra de celdas
realmente cambiadas. Propiedades clave:

1. **Alineación por etiqueta de índice**: filtrados/limpiezas conservan el
   índice original, así que una fila que solo se movió de posición NO cuenta
   como cambio.
2. **Solo lectura**: el diff no puede tocar ningún global.
3. **Paridad de mensajes**: errores en el mismo estilo que el resto de la app
   (400 citando el paso).
"""
import io

import pandas as pd
import pytest

import app as app_module
from app import diff_snapshots


BASE_CSV = (
    "Nombre,Edad,Ciudad\n"
    "  Ana ,30,Madrid\n"
    "Luis ,25,Barcelona\n"
    "Carla,35,Madrid\n"
)


def upload(client, csv_text=BASE_CSV, filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def post_op(client, operation, params):
    resp = client.post("/operation", json={"operation": operation, "params": params})
    assert resp.status_code == 200, resp.get_json()
    return resp


def step_diff(client, index=0):
    return client.post("/step_diff", json={"index": index})


# ── Errores de validación ─────────────────────────────────────────────
def test_step_diff_without_data_is_error(client):
    resp = step_diff(client, 0)
    assert resp.status_code == 400
    assert "No hay datos cargados" in resp.get_json()["error"]


@pytest.mark.parametrize("body", [
    {},                                # sin index
    {"index": "0"},                    # string
    {"index": 0.5},                    # float
    {"index": True},                   # bool (subclase de int en Python)
    {"index": None},
])
def test_step_diff_requires_integer_index(client, body):
    upload(client)
    post_op(client, "trim", {"columns": ["Nombre"]})
    resp = client.post("/step_diff", json=body)
    assert resp.status_code == 400
    assert "índice del paso" in resp.get_json()["error"]


def test_step_diff_index_out_of_range_is_error(client):
    upload(client)
    post_op(client, "trim", {"columns": ["Nombre"]})
    for bad in (-1, 1, 99):
        resp = step_diff(client, bad)
        assert resp.status_code == 400, bad
        assert "no existe en el historial" in resp.get_json()["error"]


def test_step_diff_without_steps_is_error(client):
    upload(client)  # historial: solo el upload → op_history vacío
    resp = step_diff(client, 0)
    assert resp.status_code == 400


def test_step_diff_non_json_body_is_error(client):
    upload(client)
    post_op(client, "trim", {"columns": ["Nombre"]})
    resp = client.post("/step_diff", data="{rota", content_type="application/json")
    assert resp.status_code == 400


# ── Happy path: cambios de celda con alineación por índice ────────────
def test_step_diff_trim_reports_changed_cells(client):
    upload(client)
    post_op(client, "trim", {"columns": ["Nombre"]})
    body = step_diff(client, 0).get_json()

    assert body["success"] is True
    assert body["index"] == 0
    assert body["op"] == "trim"
    assert body["params"] == {"columns": ["Nombre"]}
    assert body["before_shape"] == [3, 3]
    assert body["after_shape"] == [3, 3]
    assert body["aligned"] is True
    assert body["rows_added"] == 0 and body["rows_removed"] == 0

    # Solo la columna Nombre cambió: 2 celdas con espacios ("  Ana ", "Luis ")
    nombre = next(c for c in body["columns"] if c["column"] == "Nombre")
    assert nombre["changed"] == 2
    assert body["changed_cells"] == 2
    assert body["columns_unchanged"] == 2  # Edad y Ciudad intactas

    assert len(body["sample"]) == 2
    assert body["sample_truncated"] is False
    first = body["sample"][0]
    assert first["column"] == "Nombre"
    assert first["before"] == "  Ana "
    assert first["after"] == "Ana"


def test_step_diff_reorder_only_is_not_a_value_change(client):
    """Ordenar mueve filas de sitio: alineadas por índice, 0 celdas cambiadas."""
    upload(client)
    post_op(client, "sort", {"column": "Edad", "ascending": True})
    body = step_diff(client, 0).get_json()

    assert body["changed_cells"] == 0
    assert body["sample"] == []
    assert body["reordered"] is True
    assert body["rows_added"] == 0 and body["rows_removed"] == 0
    assert body["columns"] == []
    assert body["columns_unchanged"] == 3


# ── Filas y columnas añadidas/quitadas ────────────────────────────────
def test_step_diff_counts_removed_rows(client):
    upload(client)
    post_op(client, "filter", {"column": "Ciudad", "operator": "==", "value": "Madrid"})
    body = step_diff(client, 0).get_json()

    assert body["before_shape"] == [3, 3]
    assert body["after_shape"] == [2, 3]
    assert body["rows_removed"] == 1
    assert body["rows_added"] == 0
    # Las filas supervivientes no cambiaron sus valores
    assert body["changed_cells"] == 0
    assert body["sample"] == []


def test_step_diff_reports_removed_column(client):
    upload(client)
    post_op(client, "drop_column", {"column": "Ciudad"})
    body = step_diff(client, 0).get_json()

    assert body["columns_removed"] == ["Ciudad"]
    assert body["columns_added"] == []
    assert body["after_shape"] == [3, 2]
    assert body["columns_unchanged"] == 2


def test_step_diff_reports_added_column(client):
    upload(client)
    post_op(client, "detectar_outliers", {"columns": ["Edad"]})
    body = step_diff(client, 0).get_json()

    assert body["columns_added"] == ["Edad_outlier"]
    assert body["columns_removed"] == []
    assert body["after_shape"] == [3, 4]
    # La columna añadida no es "cambio de celda" de columnas comunes
    assert body["changed_cells"] == 0


# ── Deltas de metadatos por columna ───────────────────────────────────
def test_step_diff_dtype_change_is_reported(client):
    upload(client)
    post_op(client, "change_type", {"column": "Edad", "dtype": "str"})
    body = step_diff(client, 0).get_json()

    edad = next(c for c in body["columns"] if c["column"] == "Edad")
    assert edad["dtype_before"] == "int64"
    # pandas 3 tipa astype(str) como `str`; versiones previas como `object`
    assert edad["dtype_after"] in ("object", "str")
    # El valor "30" → 30 es un cambio de celda observable
    assert edad["changed"] == 3


def test_step_diff_null_delta_is_reported(client):
    """drop_nulls: nulos de Ciudad 1 → 0 y una fila fuera."""
    csv = "Nombre,Ciudad\nAna,Madrid\nLuis,\nCarla,Barcelona\n"
    upload(client, csv)
    post_op(client, "drop_nulls", {"columns": ["Ciudad"]})
    body = step_diff(client, 0).get_json()

    ciudad = next(c for c in body["columns"] if c["column"] == "Ciudad")
    assert ciudad["nulls_before"] == 1
    assert ciudad["nulls_after"] == 0
    assert body["rows_removed"] == 1


def test_step_diff_value_to_null_counts_as_change(client):
    """Valor → nulo real cuenta como cambio; nulo vs nulo NO cuenta."""
    csv = "Nombre,Ciudad\nAna,Madrid\nLuis,Dogville\nCarla,\n"
    upload(client, csv)
    # Madrid → "" → nulo real (Bug 4); la fila 2 ya era nula y no cambia
    post_op(client, "replace", {"column": "Ciudad", "old_value": "Madrid", "new_value": ""})
    body = step_diff(client, 0).get_json()

    ciudad = next(c for c in body["columns"] if c["column"] == "Ciudad")
    assert ciudad["changed"] == 1  # solo Madrid → nulo; nulo → nulo no cuenta
    assert body["sample"][0]["before"] == "Madrid"
    assert body["sample"][0]["after"] is None


# ── Límites y robustez ────────────────────────────────────────────────
def test_step_diff_sample_is_capped(client):
    rows = "".join(f"  persona{i} ,{20 + i},Madrid\n" for i in range(30))
    upload(client, "Nombre,Edad,Ciudad\n" + rows)
    post_op(client, "trim", {"columns": ["Nombre"]})
    body = step_diff(client, 0).get_json()

    assert body["changed_cells"] == 30
    assert len(body["sample"]) == 20
    assert body["sample_truncated"] is True


def test_step_diff_is_read_only(client):
    upload(client)
    post_op(client, "trim", {"columns": ["Nombre"]})
    snap = {
        "history": len(app_module.history),
        "op_history": len(app_module.op_history),
        "code_log": len(app_module.code_log),
        "redo": len(app_module.redo_history),
        "shape": app_module.current_df.shape,
        "data": app_module.current_df.copy(),
    }
    resp = step_diff(client, 0)
    assert resp.status_code == 200
    assert len(app_module.history) == snap["history"]
    assert len(app_module.op_history) == snap["op_history"]
    assert len(app_module.code_log) == snap["code_log"]
    assert len(app_module.redo_history) == snap["redo"]
    assert app_module.current_df.shape == snap["shape"]
    pd.testing.assert_frame_equal(app_module.current_df, snap["data"])


def test_step_diff_after_undo_is_error(client):
    upload(client)
    post_op(client, "trim", {"columns": ["Nombre"]})
    assert client.post("/undo").status_code == 200
    resp = step_diff(client, 0)
    assert resp.status_code == 400


def test_step_diff_works_for_every_step_of_a_recipe(client):
    """La receta multipaso deja un snapshot por paso: cada índice es válido."""
    upload(client)
    recipe = {
        "version": 1,
        "steps": [
            {"op": "trim", "params": {"columns": ["Nombre"]}},
            {"op": "change_case", "params": {"column": "Nombre", "case": "title"}},
            {"op": "drop_column", "params": {"column": "Ciudad"}},
        ],
    }
    assert client.post("/apply_recipe", json=recipe).status_code == 200

    ops = [step_diff(client, i).get_json() for i in range(3)]
    assert [d["op"] for d in ops] == ["trim", "change_case", "drop_column"]
    assert all(d["success"] for d in ops)
    assert ops[0]["after_shape"] == ops[1]["before_shape"] == [3, 3]
    assert ops[2]["after_shape"] == [3, 2]
    assert step_diff(client, 3).status_code == 400


# ── Unidad: diff_snapshots con índice no único ────────────────────────
def test_diff_snapshots_without_unique_index_is_summary_only():
    before = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "y", "z"]},
                          index=[0, 0, 1])
    after = pd.DataFrame({"a": [1, 3], "b": ["x", "w"]}, index=[0, 0])
    out = diff_snapshots(before, after)

    assert out["aligned"] is False
    assert out["rows_added"] is None and out["rows_removed"] is None
    assert out["changed_cells"] is None
    assert out["sample"] == [] and out["sample_truncated"] is False
    # El resumen de columnas sigue disponible
    assert {c["column"] for c in out["columns"]} <= {"a", "b"}
    assert out["columns_removed"] == []


def test_diff_snapshots_empty_intersection(client):
    """Ops que reindexan (group_by) → índices sin solape: sin pánico."""
    upload(client)
    post_op(client, "group_by", {"by": ["Ciudad"], "column": "Edad", "func": "sum"})
    body = step_diff(client, 0).get_json()

    # Único por lado, pero etiquetas 0..n que pueden solapar: sale resumen
    assert body["aligned"] is True
    assert body["after_shape"] == [2, 2]
    assert body["columns_removed"] == ["Nombre"]
