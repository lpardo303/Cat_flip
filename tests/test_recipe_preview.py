"""Tests del dry-run de receta `POST /recipe_preview` (F3.5).

El endpoint alimenta la consola del ExecutePipelineModal: devuelve un log
por paso (op, params, shape in→out, ms) sin tocar ningún global. Las dos
propiedades que hay que defender aquí son:

1. **Paridad de mensajes** con `/apply_recipe` (comparten `validate_recipe`
   y `apply_recipe_df`, así que un fallo dice exactamente lo mismo).
2. **Cero mutación**: el preview no puede dejar estado parcial, porque el
   front solo llama a `/apply_recipe` cuando la barra llega al 100%.
"""
import io
import json as jsonlib

import pytest

import app as app_module


BASE_CSV = (
    "Nombre,Edad,Ciudad\n"
    "  Ana ,30,Madrid\n"
    "Luis ,25,Barcelona\n"
    "Carla,35,Madrid\n"
)

RECIPE_OK = {
    "version": 1,
    "steps": [
        {"op": "change_case", "params": {"column": "Nombre", "case": "title"}},
        {"op": "trim", "params": {"columns": ["Nombre"]}},
        {"op": "drop_duplicates", "params": {"columns": ["Ciudad"]}},
    ],
}


def upload(client, csv_text=BASE_CSV, filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def preview(client, recipe):
    return client.post("/recipe_preview", json=recipe)


def apply_recipe(client, recipe):
    return client.post("/apply_recipe", json=recipe)


# ── Happy path ─────────────────────────────────────────────────────────
def test_preview_without_data_is_error(client):
    resp = preview(client, RECIPE_OK)
    assert resp.status_code == 400
    assert "No hay datos cargados" in resp.get_json()["error"]


def test_preview_returns_one_log_per_step(client):
    upload(client)
    resp = preview(client, RECIPE_OK)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()

    assert body["success"] is True
    assert body["steps"] == 3
    assert len(body["logs"]) == 3

    for i, (log, step) in enumerate(zip(body["logs"], RECIPE_OK["steps"]), 1):
        assert log["i"] == i
        assert log["n"] == 3
        assert log["op"] == step["op"]
        assert log["params"] == step["params"]
        assert isinstance(log["ms"], (int, float))
        assert log["ms"] >= 0


def test_preview_shapes_chain_from_step_to_step(client):
    """La salida de cada log es la entrada del siguiente (y arranca en el dataset)."""
    upload(client)
    body = preview(client, RECIPE_OK).get_json()

    assert body["input_shape"] == [3, 3]
    prev = body["input_shape"]
    for log in body["logs"]:
        assert [log["rows_in"], log["cols_in"]] == prev
        prev = [log["rows_out"], log["cols_out"]]
    assert body["output_shape"] == prev


def test_preview_shape_is_real(client):
    """drop_duplicates sobre Ciudad (Madrid, Barcelona, Madrid) → 2 filas."""
    upload(client)
    body = preview(client, RECIPE_OK).get_json()
    assert body["output_shape"] == [2, 3]


def test_preview_total_ms_matches_sum_of_steps(client):
    upload(client)
    body = preview(client, RECIPE_OK).get_json()
    assert body["total_ms"] == pytest.approx(
        sum(log["ms"] for log in body["logs"]), abs=0.01
    )


# ── La propiedad central: no muta ──────────────────────────────────────
def test_preview_never_mutates_state(client):
    upload(client)
    op_resp = client.post(
        "/operation", json={"operation": "trim", "params": {"columns": ["Ciudad"]}}
    )
    assert op_resp.status_code == 200

    before = {
        "history": len(app_module.history),
        "op_history": len(app_module.op_history),
        "code_log": len(app_module.code_log),
        "lineage": client.get("/lineage").get_json(),
        "columns": client.get("/stats").get_json()["columns"],
    }

    resp = preview(client, RECIPE_OK)
    assert resp.status_code == 200

    assert len(app_module.history) == before["history"]
    assert len(app_module.op_history) == before["op_history"]
    assert len(app_module.code_log) == before["code_log"]
    assert client.get("/lineage").get_json() == before["lineage"]
    assert client.get("/stats").get_json()["columns"] == before["columns"]
    # Undo no se ve afectado: sigue habiendo exactamente el mismo paso
    assert client.post("/undo").status_code == 200


def test_preview_then_apply_gives_same_shape(client):
    """Paridad: el dry-run y la aplicación real terminan en el mismo shape."""
    upload(client)
    preview_shape = preview(client, RECIPE_OK).get_json()["output_shape"]

    resp = apply_recipe(client, RECIPE_OK)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["applied"] == 3

    final = client.get("/lineage").get_json()["nodes"][-1]
    assert [final["rows"], final["cols"]] == preview_shape


def test_preview_leaves_undo_and_redo_usable(client):
    upload(client)
    assert preview(client, RECIPE_OK).status_code == 200
    # Ningún paso aplicado → no hay nada que deshacer
    undo = client.post("/undo")
    assert undo.status_code == 400
    # …y la receta sigue pudiéndose aplicar después del dry-run
    assert apply_recipe(client, RECIPE_OK).status_code == 200


# ── Paridad de mensajes con /apply_recipe ──────────────────────────────
def test_preview_non_json_body_is_error(client):
    upload(client)
    resp = client.post("/recipe_preview", data="{rota", content_type="application/json")
    assert resp.status_code == 400
    assert "JSON válido" in resp.get_json()["error"]


@pytest.mark.parametrize("bad_recipe,fragmento", [
    ({"version": 2, "steps": [{"op": "trim", "params": {}}]}, "Versión"),
    ({"steps": [{"op": "trim", "params": {}}]}, "Versión"),
    ({"version": 1}, "pasos"),
    ({"version": 1, "steps": []}, "pasos"),
    ({"version": 1, "steps": ["no-objeto"]}, "paso 1"),
    ({"version": 1, "steps": [{"op": "op_fantasma", "params": {}}]}, "desconocida"),
    ({"version": 1, "steps": [{"op": "trim", "params": ["lista"]}]}, "params"),
])
def test_preview_malformed_recipe_matches_apply_message(client, bad_recipe, fragmento):
    """Mismo texto que /apply_recipe: los dos comparten el validador."""
    upload(client)
    preview_resp = preview(client, bad_recipe)
    apply_resp = apply_recipe(client, bad_recipe)

    assert preview_resp.status_code == 400
    assert apply_resp.status_code == 400
    assert preview_resp.get_json()["error"] == apply_resp.get_json()["error"]
    assert fragmento in preview_resp.get_json()["error"]

    # …y sin estado parcial de parte del preview tampoco
    assert len(app_module.history) == 1
    assert len(app_module.op_history) == 0


def test_preview_failing_step_matches_apply_message(client):
    """Fallo a mitad de receta: mismo mensaje y cero estado parcial."""
    upload(client)
    recipe = {
        "version": 1,
        "steps": [
            {"op": "change_case", "params": {"column": "Nombre", "case": "upper"}},
            {"op": "regex_mask", "params": {"column": "Fantasma", "pattern": "email", "mode": "mask"}},
        ],
    }
    preview_resp = preview(client, recipe)
    apply_resp = apply_recipe(client, recipe)

    assert preview_resp.status_code == 400
    error = preview_resp.get_json()["error"]
    assert "El paso 2" in error and "regex_mask" in error
    assert error == apply_resp.get_json()["error"]

    # El paso 1 no corrió ni siquiera en la copia de trabajo del preview
    assert len(app_module.history) == 1
    assert len(app_module.op_history) == 0
    assert len(app_module.code_log) == 1
    assert client.get("/stats").status_code == 200


def test_preview_merge_without_right_frame_matches_apply_message(client):
    upload(client)
    recipe = {"version": 1, "steps": [
        {"op": "merge", "params": {"left_on": "Nombre", "right_on": "Nombre",
                                   "how": "left", "suffixes": ["_x", "_y"]}},
    ]}
    preview_resp = preview(client, recipe)
    apply_resp = apply_recipe(client, recipe)

    assert preview_resp.status_code == 400
    error = preview_resp.get_json()["error"]
    assert "El paso 1 (merge)" in error
    assert error == apply_resp.get_json()["error"]
    assert len(app_module.history) == 1


# ── Regresión del motor compartido (CLI) ───────────────────────────────
def test_engine_without_callback_is_unchanged(client):
    """Sin `on_step`, el motor devuelve exactamente lo de siempre."""
    upload(client)
    steps = app_module.validate_recipe(RECIPE_OK)

    plain = app_module.apply_recipe_df(app_module.current_df, steps)
    df_final, snaps, codes, applied = plain

    assert list(df_final.shape) == [2, 3]
    assert len(snaps) == len(codes) == len(applied) == 3
    assert applied == [{"op": s["op"], "params": s["params"]} for s in steps]
    assert codes[0].startswith("# change_case")


def test_engine_callback_receives_serializable_params(client):
    """`params` llega serializable (nunca arrastra el DataFrame derecho)."""
    upload(client)
    steps = app_module.validate_recipe(RECIPE_OK)
    seen = []

    app_module.apply_recipe_df(
        app_module.current_df, steps,
        on_step=lambda i, op, params, s_in, s_out, ms: seen.append(
            (i, op, params, tuple(s_in), tuple(s_out), ms)
        ),
    )

    assert len(seen) == 3
    assert seen[0][0] == 1 and seen[0][1] == "change_case"
    assert seen[0][2] == {"column": "Nombre", "case": "title"}
    # Los shapes también son tuplas de enteros, no numpy
    assert all(isinstance(v, int) for v in seen[0][3])
    assert jsonlib.dumps(seen[0][2])  # parámetros JSON-serializables
