"""Tests del Undo/Redo real: pila `redo_history` (backend) y endpoint /redo.

Cubre: /redo sin nada que rehacer (400), round-trip undo→redo que restaura
columnas, paridad byte a byte de script/receta/linaje tras undo→redo, pilas
LIFO con 2 pasos, undo después de redo, pila vaciada por op nueva, upload y
apply_recipe, y los flags can_undo/can_redo que el front usa para los botones.
"""
import io

import pytest

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


def redo(client):
    return client.post("/redo")


# ── caminos de error ──────────────────────────────────────────────────
def test_redo_without_data_returns_400(client):
    resp = redo(client)
    assert resp.status_code == 400
    assert "rehacer" in resp.get_json()["error"]


def test_redo_without_undo_returns_400(client):
    upload(client)
    op(client, "trim", {"column": "Nombre"})
    resp = redo(client)
    assert resp.status_code == 400
    assert "rehacer" in resp.get_json()["error"]


# ── round-trip ────────────────────────────────────────────────────────
def test_undo_redo_restores_column_state(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})

    undo_resp = client.post("/undo")
    assert undo_resp.status_code == 200
    assert "Ciudad" in undo_resp.get_json()["data"]["columns"]

    redo_resp = redo(client)
    assert redo_resp.status_code == 200
    assert "Ciudad" not in redo_resp.get_json()["data"]["columns"]


def test_undo_redo_payload_is_byte_identical(client):
    """El estado tras undo→redo == estado previo al undo (data + code)."""
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    before = op(client, "trim", {"column": "Nombre"}).get_json()
    assert client.post("/undo").status_code == 200

    after = redo(client).get_json()
    assert after["success"] is True
    assert after["data"] == before["data"]
    assert after["code"] == before["code"]


def test_export_script_identical_after_undo_redo(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    op(client, "trim", {"column": "Nombre"})
    script_before = client.post("/export_script", json={"filename": "p"}).data

    assert client.post("/undo").status_code == 200
    assert redo(client).status_code == 200
    assert client.post("/export_script", json={"filename": "p"}).data == script_before


def test_export_recipe_identical_after_undo_redo(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    recipe_before = client.post("/export_recipe", json={}).get_json()

    assert client.post("/undo").status_code == 200
    assert redo(client).status_code == 200
    assert client.post("/export_recipe", json={}).get_json() == recipe_before


def test_lineage_identical_after_undo_redo(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    op(client, "trim", {"column": "Nombre"})
    lineage_before = client.get("/lineage").get_json()

    assert client.post("/undo").status_code == 200
    assert redo(client).status_code == 200
    assert client.get("/lineage").get_json() == lineage_before


# ── pilas LIFO y flujo mixto ──────────────────────────────────────────
def test_double_undo_double_redo_restores_original(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    op(client, "drop_column", {"column": "Edad"})
    original = client.get("/lineage").get_json()

    assert client.post("/undo").status_code == 200
    assert client.post("/undo").status_code == 200
    assert redo(client).status_code == 200
    assert redo(client).status_code == 200
    assert client.get("/lineage").get_json() == original


def test_undo_after_redo_works(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    assert client.post("/undo").status_code == 200
    assert redo(client).status_code == 200

    resp = client.post("/undo")
    assert resp.status_code == 200
    assert "Ciudad" in resp.get_json()["data"]["columns"]
    # y la rama de rehacer sigue viva tras ese undo
    assert redo(client).status_code == 200


def test_redo_exhausted_returns_400(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    assert client.post("/undo").status_code == 200
    assert redo(client).status_code == 200
    resp = redo(client)
    assert resp.status_code == 400
    assert "rehacer" in resp.get_json()["error"]


# ── invalidación de la pila de rehacer ────────────────────────────────
def test_new_operation_clears_redo_stack(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    assert client.post("/undo").status_code == 200

    assert op(client, "trim", {"column": "Nombre"}).status_code == 200
    resp = redo(client)
    assert resp.status_code == 400
    assert "rehacer" in resp.get_json()["error"]


def test_upload_clears_redo_stack(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    assert client.post("/undo").status_code == 200

    upload(client)
    resp = redo(client)
    assert resp.status_code == 400
    assert "rehacer" in resp.get_json()["error"]


def test_apply_recipe_clears_redo_stack(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    assert client.post("/undo").status_code == 200

    recipe = {"version": 1, "app": "catflip",
              "steps": [{"op": "trim", "params": {"column": "Nombre"}}]}
    resp = client.post("/apply_recipe", json=recipe)
    assert resp.status_code == 200, resp.get_json()
    assert redo(client).status_code == 400


# ── flags can_undo / can_redo (contrato del front) ────────────────────
def test_undo_response_flags(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    payload = client.post("/undo").get_json()
    assert payload["can_undo"] is False  # quedamos en el snapshot base
    assert payload["can_redo"] is True


def test_redo_response_flags(client):
    upload(client)
    op(client, "drop_column", {"column": "Ciudad"})
    assert client.post("/undo").status_code == 200

    payload = redo(client).get_json()
    assert payload["can_undo"] is True
    assert payload["can_redo"] is False  # pila vacía tras el único paso
