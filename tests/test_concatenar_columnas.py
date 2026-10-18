"""Tests del op concatenar_columnas (#22): unión de 2+ columnas.

Cubre el orden de unión, delimitador custom (incluido vacío), omisión de
nulos sin delimitadores huérfanos (regla Bug 4), drop_sources, la
sobrescritura de una columna seleccionada y todos los ValueError que el
endpoint traduce a 500 sin mutar el estado.
"""
import io

import pytest

import app as app_module

BASE_CSV = (
    "Nombre,Apellido,Departamento\n"
    "Ana,Torres,Dirección\n"
    "Luis,,Ventas\n"
    ",,Marketing\n"
    ",,\n"
)


def upload(client, csv_text=BASE_CSV, filename="nombres.csv"):
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


def cell(resp, row, col):
    """Celda (row, col) del payload, como la ve la UI."""
    data = resp.get_json()["data"]
    return data["data"][row][data["columns"].index(col)]


# ── Happy path ─────────────────────────────────────────────────────────

def test_concat_two_columns_default_delim(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Apellido"], "new_name": "Completo",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Completo") == "Ana Torres"
    # Nulo intermedio omitido: sin delimitador huérfano
    assert cell(resp, 1, "Completo") == "Luis"
    # Filas cuyas dos columnas seleccionadas son nulas → nulo real
    assert cell(resp, 2, "Completo") is None  # solo Departamento tiene valor
    assert cell(resp, 3, "Completo") is None
    assert resp.get_json()["data"]["nulls"]["Completo"] == 2


def test_concat_three_columns_custom_delim(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Apellido", "Departamento"],
        "delimiter": " - ", "new_name": "Ficha",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Ficha") == "Ana - Torres - Dirección"
    assert cell(resp, 1, "Ficha") == "Luis - Ventas"
    assert cell(resp, 2, "Ficha") == "Marketing"


def test_concat_order_is_params_order(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Apellido", "Nombre"], "delimiter": "|", "new_name": "Invertido",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Invertido") == "Torres|Ana"


def test_concat_empty_delim_joins_directly(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Apellido"], "delimiter": "", "new_name": "Compacto",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Compacto") == "AnaTorres"
    assert cell(resp, 1, "Compacto") == "Luis"


def test_concat_drop_sources(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Apellido"], "new_name": "Completo", "drop_sources": True,
    })
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert "Nombre" not in data["columns"]
    assert "Apellido" not in data["columns"]
    assert "Completo" in data["columns"]
    assert "Departamento" in data["columns"]  # no seleccionada: intacta
    assert cell(resp, 0, "Completo") == "Ana Torres"


def test_concat_overwrites_selected_column(client):
    """new_name igual a una columna seleccionada: sobrescribe en sitio."""
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Apellido"], "new_name": "Nombre",
    })
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert "Nombre" in data["columns"]
    assert cell(resp, 0, "Nombre") == "Ana Torres"
    assert "Apellido" in data["columns"]  # sin drop_sources: originales quedan


def test_concat_generated_code(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Apellido"], "delimiter": " ", "new_name": "Completo",
    })
    assert resp.status_code == 200, resp.get_json()
    code = resp.get_json()["last_code"]
    assert "_partes" in code
    assert "'Nombre', 'Apellido'" in code
    assert "agg" in code
    # El código generado debe ser Python válido con solo pandas
    compile(code, "<generated>", "exec")


# ── Errores (500 con mensaje, sin mutar el estado) ─────────────────────

def test_single_column_is_error(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre"], "new_name": "X",
    })
    assert resp.status_code == 500
    assert "al menos 2" in resp.get_json()["error"]
    assert len(app_module.history) == 1  # solo el upload


def test_no_columns_is_error(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {"new_name": "X"})
    assert resp.status_code == 500
    assert "al menos 2" in resp.get_json()["error"]


def test_duplicated_column_is_error(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Nombre"], "new_name": "X",
    })
    assert resp.status_code == 500
    assert "No repitas" in resp.get_json()["error"]


def test_unknown_column_is_error(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Fantasma"], "new_name": "X",
    })
    assert resp.status_code == 500
    assert "no existe" in resp.get_json()["error"]


def test_empty_new_name_is_error(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Apellido"], "new_name": "  ",
    })
    assert resp.status_code == 500
    assert "nombre" in resp.get_json()["error"].lower()


def test_collision_with_unrelated_column_is_error(client):
    upload(client)
    resp = op(client, "concatenar_columnas", {
        "columns": ["Nombre", "Apellido"], "new_name": "Departamento",
    })
    assert resp.status_code == 500
    assert "ya existe" in resp.get_json()["error"]
    assert len(app_module.history) == 1  # sin estado parcial
