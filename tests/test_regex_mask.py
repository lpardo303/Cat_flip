"""Tests del op regex_mask (#21): enmascaramiento y extracción de PII.

Cubre los presets (email/teléfono/id), la regex personalizada, ambos
modos (mask/extract), la supervivencia de nulos (regla Bug 4) y todos
los ValueError que el endpoint traduce a 500 sin mutar el estado.
"""
import io

import pytest

import app as app_module

PII_CSV = (
    "Nombre,Contacto,Nota\n"
    "Ana,ana.torres@catflip.dev,SN-001\n"
    "Luis,+34 612 345 678,x\n"
    "Marta,soporte@catflip.dev,4111111111111111\n"
    "Pedro,,\n"
)


def upload(client, csv_text=PII_CSV, filename="pii.csv"):
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


# ── Modo mask (sustituye la coincidencia en la misma columna) ──────────

def test_mask_email_preset(client):
    upload(client)
    resp = op(client, "regex_mask", {"column": "Contacto", "pattern": "email", "mode": "mask"})
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Contacto") == "****"
    assert cell(resp, 2, "Contacto") == "****"
    assert "str.replace" in resp.get_json()["last_code"]


def test_mask_phone_preset(client):
    upload(client)
    resp = op(client, "regex_mask", {"column": "Contacto", "pattern": "phone", "mode": "mask"})
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 1, "Contacto") == "****"
    # El email no contiene suficientes dígitos: queda intacto
    assert cell(resp, 0, "Contacto") == "ana.torres@catflip.dev"


def test_mask_id_preset(client):
    upload(client)
    resp = op(client, "regex_mask", {"column": "Nota", "pattern": "id", "mode": "mask"})
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Nota") == "****"        # SN-001
    assert cell(resp, 2, "Nota") == "****"        # tarjeta de 16 dígitos
    assert cell(resp, 1, "Nota") == "x"           # sin coincidencia


def test_mask_custom_pattern(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Nota", "pattern": "custom", "custom_pattern": r"SN-\d+", "mode": "mask",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Nota") == "****"
    assert cell(resp, 2, "Nota") == "4111111111111111"  # custom solo casó SN-001


def test_mask_custom_fill(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "email", "mode": "mask", "mask": "[OCULTO]",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Contacto") == "[OCULTO]"


def test_mask_empty_fill_erases_match(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "email", "mode": "mask", "mask": "",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 0, "Contacto") == ""


def test_mask_preserves_nulls(client):
    """El email nulo de Pedro sigue siendo nulo tras enmascarar (Bug 4)."""
    upload(client)
    resp = op(client, "regex_mask", {"column": "Contacto", "pattern": "email", "mode": "mask"})
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 3, "Contacto") is None
    assert resp.get_json()["data"]["nulls"]["Contacto"] == 1


# ── Modo extract (primera coincidencia → columna nueva) ────────────────

def test_extract_default_new_column(client):
    upload(client)
    resp = op(client, "regex_mask", {"column": "Contacto", "pattern": "email", "mode": "extract"})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert "Contacto_mask" in data["columns"]
    i_contacto = data["columns"].index("Contacto")
    i_mask = data["columns"].index("Contacto_mask")
    # Columna fuente intacta + primera coincidencia en la nueva
    assert data["data"][0][i_contacto] == "ana.torres@catflip.dev"
    assert data["data"][0][i_mask] == "ana.torres@catflip.dev"
    assert data["data"][1][i_mask] is None  # el teléfono no es email


def test_extract_custom_new_column(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Nota", "pattern": "id", "mode": "extract", "new_column": "ID_Limpio",
    })
    assert resp.status_code == 200, resp.get_json()
    assert "ID_Limpio" in resp.get_json()["data"]["columns"]
    assert cell(resp, 0, "ID_Limpio") == "SN-001"
    assert cell(resp, 0, "Nota") == "SN-001"  # fuente intacta


def test_extract_no_match_is_null(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Nota", "pattern": "email", "mode": "extract", "new_column": "EmailNota",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 1, "EmailNota") is None  # "x" no casó


def test_extract_preserves_nulls(client):
    """La fila de Pedro (nulos reales) produce nulo en la columna extraída."""
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "email", "mode": "extract", "new_column": "Email2",
    })
    assert resp.status_code == 200, resp.get_json()
    assert cell(resp, 3, "Email2") is None


# ── Errores (500 con mensaje, sin mutar el estado) ─────────────────────

def test_unknown_column_is_error(client):
    upload(client)
    resp = op(client, "regex_mask", {"column": "Fantasma", "pattern": "email", "mode": "mask"})
    assert resp.status_code == 500
    assert "no existe" in resp.get_json()["error"]
    assert len(app_module.history) == 1  # solo el upload


def test_invalid_mode_is_error(client):
    upload(client)
    resp = op(client, "regex_mask", {"column": "Contacto", "pattern": "email", "mode": "viral"})
    assert resp.status_code == 500
    assert "Modo no válido" in resp.get_json()["error"]


def test_unknown_pattern_is_error(client):
    upload(client)
    resp = op(client, "regex_mask", {"column": "Contacto", "pattern": "dni", "mode": "mask"})
    assert resp.status_code == 500
    assert "Patrón desconocido" in resp.get_json()["error"]


def test_invalid_regex_is_error(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "custom", "custom_pattern": "[unclosed", "mode": "mask",
    })
    assert resp.status_code == 500
    assert "Regex no válida" in resp.get_json()["error"]


def test_empty_custom_pattern_is_error(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "custom", "custom_pattern": "", "mode": "mask",
    })
    assert resp.status_code == 500
    assert "vacía" in resp.get_json()["error"]


def test_regex_matching_empty_string_is_error(client):
    """Un patrón como 'a*' casaría la cadena vacía: enmascararía todo."""
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "custom", "custom_pattern": "a*", "mode": "mask",
    })
    assert resp.status_code == 500
    assert "cadena vacía" in resp.get_json()["error"]


def test_extract_collision_is_error(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "email", "mode": "extract", "new_column": "Nombre",
    })
    assert resp.status_code == 500
    assert "ya existe" in resp.get_json()["error"]


def test_extract_onto_source_column_is_error(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "email", "mode": "extract", "new_column": "Contacto",
    })
    assert resp.status_code == 500
    assert "original" in resp.get_json()["error"]


def test_oversized_custom_regex_is_error(client):
    upload(client)
    resp = op(client, "regex_mask", {
        "column": "Contacto", "pattern": "custom", "custom_pattern": "a" * 501, "mode": "mask",
    })
    assert resp.status_code == 500
    assert "500" in resp.get_json()["error"]
