"""Tests de exportación de receta como script Python `POST /recipe_export` (F3.4).

El script debe ser una TRADUCCIÓN exacta de lo que la app ejecutó:
reutiliza el mismo generador de código que /operation y /apply_recipe,
valida con mensajes en paridad (validate_recipe), y NUNCA escribe estado.
La prueba definitiva es `test_export_is_executable_and_matches_app_result`:
el script corre con pandas y termina en el mismo dataset que la app.
"""
import io
import runpy
import sys

import pandas as pd
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


def upload_right(client, csv_text="Nombre,Departamento\nAna,Ops\n", filename="der.csv"):
    resp = client.post(
        "/upload_right",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def apply_op(client, op, params):
    resp = client.post("/operation", json={"operation": op, "params": params})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def export(client, filename="pipeline_catflip"):
    return client.post("/recipe_export", json={"filename": filename})


# ── Validación (paridad con /apply_recipe) ─────────────────────────────
def test_export_without_data_is_error(client):
    resp = export(client)
    assert resp.status_code == 400
    assert "No hay datos cargados" in resp.get_json()["error"]


def test_export_without_steps_is_error(client):
    upload(client)
    resp = export(client)
    assert resp.status_code == 400
    assert "No hay pasos" in resp.get_json()["error"]


def test_export_malformed_op_history_matches_apply_message(client):
    """op_history corrupto (op fantasma) → mismo texto que /apply_recipe."""
    upload(client)
    app_module.op_history.append({"op": "op_fantasma", "params": {}})

    export_resp = export(client)
    apply_resp = client.post(
        "/apply_recipe",
        json={"version": 1, "steps": [{"op": "op_fantasma", "params": {}}]},
    )
    assert export_resp.status_code == 400
    assert apply_resp.status_code == 400
    assert export_resp.get_json()["error"] == apply_resp.get_json()["error"]
    assert "desconocida" in export_resp.get_json()["error"]


def test_export_merge_without_right_frame_is_error(client):
    """Receta con merge pero sin frame derecho → 400 citando el paso."""
    upload(client)
    app_module.op_history.append({
        "op": "merge",
        "params": {"left_on": "Nombre", "right_on": "Nombre",
                   "how": "left", "suffixes": ["_x", "_y"]},
    })
    resp = export(client)
    assert resp.status_code == 400
    assert "El paso 1 (merge)" in resp.get_json()["error"]


# ── Contenido del script ───────────────────────────────────────────────
def test_export_script_header_and_relative_load(client):
    """Cabecera autocontenida + carga por nombre RELATIVO (portabilidad)."""
    upload(client, filename="empleados.csv")
    apply_op(client, "trim", {"columns": ["Nombre"]})
    script = export(client).get_data(as_text=True)

    assert "import pandas as pd" in script
    assert "sys.argv" in script
    assert "entrada =" in script and "salida =" in script
    # La entrada NO lleva ruta absoluta: lee de argv[1] (portabilidad)
    assert "pd.read_csv(entrada" in script
    assert "sep=','" in script  # el separador detectado se conserva
    assert "empleados.csv" not in script  # el nombre grabado no se hardcodea
    assert "/home/" not in script
    # Termina guardando el resultado por la ruta pedida como argv[2]
    assert "df.to_excel(salida, index=False)" in script


def test_export_code_parity_with_manual_ops(client):
    """Cada fragmento de code_log (pasos manuales) está BYTE A BYTE en el script."""
    upload(client)
    apply_op(client, "change_case", {"column": "Nombre", "case": "upper"})
    apply_op(client, "drop_duplicates", {"columns": ["Ciudad"]})
    script = export(client).get_data(as_text=True)

    # code_log = [carga] + pasos; la carga se regenera con basename, el
    # resto debe coincidir exactamente (mismo generador, sin indentar)
    for frag in app_module.code_log[1:]:
        op_code = frag.split("\n", 1)[1]
        assert op_code in script


def test_export_code_parity_with_apply_recipe(client):
    """La receta aplicada con /apply_recipe produce los mismos fragmentos."""
    upload(client)
    recipe = {"version": 1, "steps": [
        {"op": "change_case", "params": {"column": "Nombre", "case": "title"}},
        {"op": "trim", "params": {"columns": ["Nombre"]}},
    ]}
    assert client.post("/apply_recipe", json=recipe).status_code == 200
    script = export(client).get_data(as_text=True)

    for frag in app_module.code_log[1:]:
        assert frag.split("\n", 1)[1] in script
    # Cabeceras numeradas con el label legible de cada op
    assert "# 1. Cambio de mayúsculas/minúsculas (change_case)" in script
    assert "# 2. Quitar espacios (trim)" in script


def test_export_merge_with_right_frame_includes_load(client):
    """El paso merge exporta también la carga del frame derecho (df_right)."""
    upload(client)
    upload_right(client)
    apply_op(client, "merge", {
        "left_on": "Nombre", "right_on": "Nombre",
        "how": "left", "suffixes": ["_x", "_y"],
    })
    resp = export(client)
    assert resp.status_code == 200, resp.get_json()
    script = resp.get_data(as_text=True)

    assert "df_right = pd.read_csv('der.csv'" in script
    assert "df = df.merge(df_right" in script
    assert "# 1. Cruce Join/Merge (merge)" in script


def test_export_op_labels_cover_the_whole_registry():
    """_OP_LABELS cubre el registro OPS completo (sin huecos ni sobras)."""
    assert set(app_module._OP_LABELS) == set(OPS)


def test_export_non_ascii_is_readable_utf8(client):
    """Acentos y ñ salen intactos (buffer UTF-8, sin mojibake)."""
    upload(client)
    apply_op(client, "change_case", {"column": "Nombre", "case": "upper"})
    script = export(client).get_data(as_text=True)
    assert "mayúsculas" in script


# ── Filename y mimetype ────────────────────────────────────────────────
def test_export_default_filename_is_pipeline_py(client):
    upload(client)
    apply_op(client, "trim", {"columns": ["Nombre"]})
    resp = client.post("/recipe_export", json={})
    assert resp.status_code == 200
    assert resp.mimetype == "text/x-python"
    assert resp.headers["Content-Disposition"].endswith("pipeline_catflip.py")


@pytest.mark.parametrize("malicious", ["../../etc/passwd", "..\\..\\evil", "a/b/c"])
def test_export_filename_is_sanitized(client, malicious):
    """El filename del cliente no escapa: el download_name es basename puro."""
    upload(client)
    apply_op(client, "trim", {"columns": ["Nombre"]})
    resp = client.post("/recipe_export", json={"filename": malicious})
    assert resp.status_code == 200
    name = resp.headers["Content-Disposition"]
    assert ".." not in name
    assert "/" not in name.split("filename=")[1]
    assert "\\" not in name


# ── Cero mutación ──────────────────────────────────────────────────────
def test_export_never_mutates_state(client):
    upload(client)
    apply_op(client, "trim", {"columns": ["Nombre"]})
    before = {
        "history": len(app_module.history),
        "op_history": len(app_module.op_history),
        "code_log": len(app_module.code_log),
        "lineage": client.get("/lineage").get_json(),
        "columns": client.get("/stats").get_json()["columns"],
    }

    assert export(client).status_code == 200

    assert len(app_module.history) == before["history"]
    assert len(app_module.op_history) == before["op_history"]
    assert len(app_module.code_log) == before["code_log"]
    assert client.get("/lineage").get_json() == before["lineage"]
    assert client.get("/stats").get_json()["columns"] == before["columns"]
    # Undo sigue intacto: el export no consumió ni añadió pasos
    assert client.post("/undo").status_code == 200


# ── El guion realmente corre y reproduce el resultado ──────────────────
def test_export_is_executable_and_matches_app_result(client, tmp_path):
    """Ejecuta el .py generado con pandas y compara contra el df de la app."""
    upload(client)
    apply_op(client, "change_case", {"column": "Nombre", "case": "upper"})
    apply_op(client, "drop_duplicates", {"columns": ["Ciudad"]})
    script = export(client).get_data(as_text=True)

    csv_path = tmp_path / "data.csv"
    csv_path.write_text(BASE_CSV, encoding="utf-8")
    out_path = tmp_path / "salida.xlsx"
    script_path = tmp_path / "pipeline.py"
    script_path.write_text(script, encoding="utf-8")

    old_argv = sys.argv
    sys.argv = ["pipeline.py", str(csv_path), str(out_path)]
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    finally:
        sys.argv = old_argv

    assert out_path.exists()
    result = pd.read_excel(out_path)
    expected = app_module.current_df
    # Mismo shape, mismas columnas y mismos valores que la app
    assert list(result.shape) == list(expected.shape)
    assert list(result.columns) == list(expected.columns)
    for col in expected.columns:
        assert list(result[col].astype(str)) == list(expected[col].astype(str))
