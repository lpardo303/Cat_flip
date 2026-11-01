"""Tests del op reorder_columns (#25): reordenación de columnas.

Cubre el modo ``block`` (bloque inicial fijo al principio conservando su
orden actual relativo + resto alfabético case-insensitive con empates
estables), el modo ``move`` (destino exacto: start/end/before/after),
la ejecución del código generado (paridad con ``exec``) y todos los
ValueError que el endpoint traduce a 500 sin mutar el estado.
"""
import io

import pandas as pd

import app as app_module

# Mezcla de mayúsculas/minúsculas a propósito: el orden alfabético debe
# ignorar mayúsculas (casefold) — con sort ASCII 'Zeta' pasaría antes
# que 'alpha'.
BASE_CSV = (
    "Zeta,alpha,Beta,monto\n"
    "z1,a1,b1,10\n"
    "z2,a2,b2,20\n"
    "z3,a3,b3,30\n"
)


def upload(client, csv_text=BASE_CSV, filename="reorder.csv"):
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


def columns(resp):
    return resp.get_json()["data"]["columns"]


def cell(resp, row, col):
    data = resp.get_json()["data"]
    return data["data"][row][data["columns"].index(col)]


# ── Modo block ─────────────────────────────────────────────────────────
def test_block_pins_first_and_sorts_rest(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "block", "first": ["monto"]})
    assert resp.status_code == 200, resp.get_json()
    # bloque (solo monto) + resto alfabético case-insensitive
    assert columns(resp) == ["monto", "alpha", "Beta", "Zeta"]


def test_block_keeps_current_relative_order(client):
    """Dentro del bloque manda el orden ACTUAL del dataset, no el de `first`."""
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "block", "first": ["monto", "Zeta"]})
    assert resp.status_code == 200, resp.get_json()
    # orden actual: Zeta … monto → el bloque sale como [Zeta, monto]
    assert columns(resp) == ["Zeta", "monto", "alpha", "Beta"]


def test_block_empty_sorts_everything_case_insensitive(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "block", "first": []})
    assert resp.status_code == 200, resp.get_json()
    # casefold: alpha, Beta, monto, Zeta (un sort ASCII daría Beta, Zeta, alpha, monto)
    assert columns(resp) == ["alpha", "Beta", "monto", "Zeta"]


def test_block_stable_on_casefold_ties(client):
    """'id' e 'ID' empatan en casefold: se conserva el orden original."""
    upload(client, csv_text="id,ID,x\n1,2,3\n", filename="ties.csv")
    resp = op(client, "reorder_columns", {"mode": "block", "first": ["x"]})
    assert resp.status_code == 200, resp.get_json()
    assert columns(resp) == ["x", "id", "ID"]


def test_block_preserves_values(client):
    """Los datos viajan con su columna: mismo orden de filas, ceros reordenados."""
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "block", "first": ["monto"]})
    assert resp.status_code == 200, resp.get_json()
    assert columns(resp) == ["monto", "alpha", "Beta", "Zeta"]
    data = resp.get_json()["data"]["data"]
    assert data[0] == ["10", "a1", "b1", "z1"]


def test_block_generated_code_executes_identically(client):
    """El código generado lista el orden final: paridad exacta con exec."""
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "block", "first": ["monto"]})
    assert resp.status_code == 200, resp.get_json()
    code = resp.get_json()["last_code"]
    compile(code, "<generated>", "exec")
    assert code.rstrip().splitlines()[-1] == "df = df[['monto', 'alpha', 'Beta', 'Zeta']]"

    ns = {"df": pd.read_csv(io.StringIO(BASE_CSV))}
    exec(code, ns)  # noqa: S102 — el script exportado hace exactamente esto
    assert list(ns["df"].columns) == columns(resp)
    assert ns["df"]["monto"].tolist() == [10, 20, 30]


# ── Modo move ──────────────────────────────────────────────────────────
def test_move_to_start(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "monto", "position": "start"})
    assert resp.status_code == 200, resp.get_json()
    assert columns(resp) == ["monto", "Zeta", "alpha", "Beta"]
    # los valores siguen a su columna
    assert cell(resp, 0, "monto") == "10"
    assert cell(resp, 0, "Zeta") == "z1"


def test_move_to_end(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "Zeta", "position": "end"})
    assert resp.status_code == 200, resp.get_json()
    assert columns(resp) == ["alpha", "Beta", "monto", "Zeta"]


def test_move_before_reference(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "monto", "before": "alpha"})
    assert resp.status_code == 200, resp.get_json()
    assert columns(resp) == ["Zeta", "monto", "alpha", "Beta"]


def test_move_after_reference(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "alpha", "after": "monto"})
    assert resp.status_code == 200, resp.get_json()
    assert columns(resp) == ["Zeta", "Beta", "monto", "alpha"]


def test_move_first_column_after_last(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "Zeta", "after": "monto"})
    assert resp.status_code == 200, resp.get_json()
    assert columns(resp) == ["alpha", "Beta", "monto", "Zeta"]


def test_move_generated_code_executes_identically(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "monto", "before": "alpha"})
    assert resp.status_code == 200, resp.get_json()
    code = resp.get_json()["last_code"]
    compile(code, "<generated>", "exec")

    ns = {"df": pd.read_csv(io.StringIO(BASE_CSV))}
    exec(code, ns)  # noqa: S102
    assert list(ns["df"].columns) == columns(resp) == ["Zeta", "monto", "alpha", "Beta"]


# ── Errores (500 con mensaje, sin mutar el estado) ─────────────────────
def test_unknown_mode_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "rotate"})
    assert resp.status_code == 500
    assert "Modo de reordenación desconocido" in resp.get_json()["error"]
    assert len(app_module.history) == 1  # solo el upload


def test_block_first_not_list_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "block", "first": "monto"})
    assert resp.status_code == 500
    assert "lista" in resp.get_json()["error"]


def test_block_duplicated_entry_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "block", "first": ["Zeta", "Zeta"]})
    assert resp.status_code == 500
    assert "No repitas" in resp.get_json()["error"]


def test_block_unknown_column_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "block", "first": ["Fantasma"]})
    assert resp.status_code == 500
    assert "no existe" in resp.get_json()["error"]


def test_move_unknown_column_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "Fantasma", "position": "start"})
    assert resp.status_code == 500
    assert "no existe" in resp.get_json()["error"]
    assert len(app_module.history) == 1  # sin estado parcial


def test_move_without_target_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "monto"})
    assert resp.status_code == 500
    assert "exactamente un destino" in resp.get_json()["error"]


def test_move_with_two_targets_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {
        "mode": "move", "column": "monto", "position": "start", "after": "alpha",
    })
    assert resp.status_code == 500
    assert "exactamente un destino" in resp.get_json()["error"]


def test_move_bad_position_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "monto", "position": "middle"})
    assert resp.status_code == 500
    assert "'start' o 'end'" in resp.get_json()["error"]


def test_move_unknown_reference_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "monto", "before": "Fantasma"})
    assert resp.status_code == 500
    assert "referencia" in resp.get_json()["error"]


def test_move_reference_is_itself_is_error(client):
    upload(client)
    resp = op(client, "reorder_columns", {"mode": "move", "column": "monto", "after": "monto"})
    assert resp.status_code == 500
    assert "no puede servir de referencia" in resp.get_json()["error"]
