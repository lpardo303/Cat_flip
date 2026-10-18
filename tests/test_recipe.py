"""Tests de Guardar/Cargar Receta JSON (`.catflip.json`).

Cubre el formato exportado (version/app/steps con {op, params}), el
round-trip exportar → reproducir, el undo paso a paso tras aplicar, la
validación de recetas malformadas y — sobre todo — la atomicidad: un
paso que falla a mitad de la receta no deja ningún estado parcial.
"""
import io
import json as jsonlib

import pytest

import app as app_module
from operations import OPS

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


def op(client, operation, params=None):
    return client.post(
        "/operation", json={"operation": operation, "params": params or {}}
    )


def export_recipe(client, filename="receta"):
    return client.post("/export_recipe", json={"filename": filename})


def apply_recipe(client, recipe):
    return client.post("/apply_recipe", json=recipe)


def cell(resp, row, col):
    data = resp.get_json()["data"]
    return data["data"][row][data["columns"].index(col)]


# ── Export ─────────────────────────────────────────────────────────────

def test_export_without_data_is_error(client):
    resp = export_recipe(client)
    assert resp.status_code == 400
    assert "No hay datos" in resp.get_json()["error"]


def test_export_without_steps_is_error(client):
    upload(client)
    resp = export_recipe(client)
    assert resp.status_code == 400
    assert "No hay pasos" in resp.get_json()["error"]


def test_export_happy_format(client):
    upload(client)
    assert op(client, "change_case", {"column": "Nombre", "case": "upper"}).status_code == 200
    assert op(client, "rename_column", {"old_name": "Edad", "new_name": "Years"}).status_code == 200

    resp = export_recipe(client, filename="mi_receta")
    assert resp.status_code == 200
    assert ".catflip.json" in resp.headers.get("Content-Disposition", "")
    assert resp.headers["Content-Type"].startswith("application/json")

    recipe = jsonlib.loads(resp.data)
    assert recipe["version"] == 1
    assert recipe["app"] == "catflip"
    assert [s["op"] for s in recipe["steps"]] == ["change_case", "rename_column"]
    assert recipe["steps"][0]["params"] == {"column": "Nombre", "case": "upper"}
    # Todo debe ser JSON-válido de ida y vuelta sin pérdidas
    assert jsonlib.loads(jsonlib.dumps(recipe)) == recipe


def test_export_filename_normalization(client):
    """Un filename ya extensión se normaliza: no doble `.catflip.json`."""
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    resp = export_recipe(client, filename="mi_receta.catflip.json")
    assert resp.status_code == 200
    cd = resp.headers.get("Content-Disposition", "")
    assert cd.count(".catflip.json") == 1
    assert "mi_receta.catflip.json" in cd


# ── Round-trip: exportar → reproducir ──────────────────────────────────

def build_recipe(client):
    upload(client)
    op(client, "change_case", {"column": "Nombre", "case": "upper"})
    op(client, "trim", {"columns": ["Nombre", "Ciudad"]})
    resp = export_recipe(client)
    assert resp.status_code == 200
    return jsonlib.loads(resp.data)


def test_round_trip_replays_all_steps(client):
    recipe = build_recipe(client)
    upload(client)  # reset total: mismo shape, sin pasos
    assert len(app_module.op_history) == 0

    resp = apply_recipe(client, recipe)
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["applied"] == 2
    assert [s["op"] for s in payload["steps"]] == ["change_case", "trim"]
    # Mismo resultado que aplicación manual: espacios recortados + MAYÚSCULAS
    assert cell(resp, 0, "Nombre") == "ANA"
    assert cell(resp, 1, "Nombre") == "LUIS"
    # Estado completo: upload + 2 pasos → undo paso a paso
    assert len(app_module.history) == 3
    assert len(app_module.op_history) == 2
    assert len(app_module.code_log) == 3
    assert "# change_case" in payload["code"] and "# trim" in payload["code"]


def test_undo_after_apply_reverts_one_step(client):
    recipe = build_recipe(client)
    upload(client)
    apply_recipe(client, recipe)

    resp = client.post("/undo")
    assert resp.status_code == 200, resp.get_json()
    # Se revirtió el trim (paso 2): queda el paso 1 — MAYÚSCULAS con espacios
    assert cell(resp, 0, "Nombre") == "  ANA "
    assert len(app_module.op_history) == 1
    assert len(app_module.history) == 2
    assert "# change_case" in app_module.code_log[-1]
    assert "# trim" not in app_module.code_log[-1]

    resp2 = client.post("/undo")
    assert resp2.status_code == 200
    assert len(app_module.history) == 1  # vuelta al upload puro
    assert len(app_module.op_history) == 0


# ── Apply: validación de receta ────────────────────────────────────────

def test_apply_without_data_is_error(client):
    resp = apply_recipe(client, {"version": 1, "steps": [{"op": "trim", "params": {}}]})
    assert resp.status_code == 400
    assert "No hay datos cargados" in resp.get_json()["error"]


def test_apply_non_json_body_is_error(client):
    upload(client)
    resp = client.post("/apply_recipe", data="{rota", content_type="application/json")
    assert resp.status_code == 400
    assert "JSON válido" in resp.get_json()["error"]


@pytest.mark.parametrize("bad_recipe,fragmento", [
    ({"version": 2, "steps": [{"op": "trim", "params": {}}]}, "Versión"),
    ({"steps": [{"op": "trim", "params": {}}]}, "Versión"),          # sin version
    ({"version": 1}, "pasos"),
    ({"version": 1, "steps": []}, "pasos"),
    ({"version": 1, "steps": "no-lista"}, "pasos"),
    ({"version": 1, "steps": ["no-objeto"]}, "paso 1"),
    ({"version": 1, "steps": [{"op": "op_fantasma", "params": {}}]}, "desconocida"),
    ({"version": 1, "steps": [{"op": "trim", "params": ["lista"]}]}, "params"),
])
def test_apply_malformed_recipe_is_error_without_state(client, bad_recipe, fragmento):
    upload(client)
    resp = apply_recipe(client, bad_recipe)
    assert resp.status_code == 400, resp.get_json()
    assert fragmento in resp.get_json()["error"]
    # Sin estado parcial: solo el upload
    assert len(app_module.history) == 1
    assert len(app_module.op_history) == 0
    assert len(app_module.code_log) == 1


def test_apply_failing_step_mid_recipe_is_atomic(client):
    """Paso 2 inválido → 400 citando el paso, SIN aplicar el paso 1."""
    upload(client)
    recipe = {
        "version": 1,
        "steps": [
            {"op": "change_case", "params": {"column": "Nombre", "case": "upper"}},
            {"op": "regex_mask", "params": {"column": "Fantasma", "pattern": "email", "mode": "mask"}},
        ],
    }
    resp = apply_recipe(client, recipe)
    assert resp.status_code == 400
    error = resp.get_json()["error"]
    assert "El paso 2" in error and "regex_mask" in error
    # El paso 1 NO se aplicó: estado intacto (solo upload)
    assert len(app_module.history) == 1
    assert len(app_module.op_history) == 0
    assert len(app_module.code_log) == 1
    # Los datos siguen originales (el change_case no corrió)
    data = client.get("/stats")  # endpoint vivo confirma el servidor sin estado roto
    assert data.status_code == 200


def test_apply_merge_step_without_right_frame_is_error(client):
    upload(client)
    recipe = {"version": 1, "steps": [
        {"op": "merge", "params": {"left_on": "Nombre", "right_on": "Nombre", "how": "left", "suffixes": ["_x", "_y"]}},
    ]}
    resp = apply_recipe(client, recipe)
    assert resp.status_code == 400
    assert "El paso 1 (merge)" in resp.get_json()["error"]
    assert len(app_module.history) == 1


def test_apply_rejects_unknown_ops_but_known_registry(client):
    """La validación usa el registro real: ops válidas de 23 no se rechazan."""
    upload(client)
    # detectar_outliers es válida en el registro; como paso de receta pasa
    # la validación estructural (luego ejecuta bien sobre Edad numérico)
    recipe = {"version": 1, "steps": [
        {"op": "detectar_outliers", "params": {"columns": ["Edad"]}},
    ]}
    resp = apply_recipe(client, recipe)
    assert resp.status_code == 200, resp.get_json()
    assert "Edad_outlier" in resp.get_json()["data"]["columns"]
    assert "detectar_outliers" in OPS
