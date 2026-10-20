"""Tests del op sampling (#24): muestreo de filas.

Cubre head/tail (con recorte cuando n > filas), random determinista
(seed 42, misma entrada → mismas filas), stratified (n por estrato,
estratos nulos incluidos, recorte en estratos pequeños), todos los
ValueError que el endpoint traduce a 500 sin mutar el estado, la
ejecución del código generado (paridad código/resultado) y el
round-trip de receta con un paso sampling.
"""
import io

import pandas as pd
import pytest

import app as app_module

# 9 filas: 3 estratos (a×4, b×3, nulo×2), Valor numérico 1..9.
BASE_CSV = (
    "Grupo,Valor\n"
    "a,1\n"
    "a,2\n"
    "a,3\n"
    "a,4\n"
    "b,5\n"
    "b,6\n"
    "b,7\n"
    ",8\n"
    ",9\n"
)


def upload(client, csv_text=BASE_CSV, filename="muestreo.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def sample(client, params):
    return client.post("/operation", json={"operation": "sampling", "params": params})


def valores(resp):
    data = resp.get_json()["data"]
    i = data["columns"].index("Valor")
    return [row[i] for row in data["data"]]


# ── Happy path ─────────────────────────────────────────────────────────
def test_head_returns_first_n_rows(client):
    upload(client)
    resp = sample(client, {"mode": "head", "n": 3})
    assert resp.status_code == 200, resp.get_json()
    assert valores(resp) == ["1", "2", "3"]


def test_tail_returns_last_n_rows(client):
    upload(client)
    resp = sample(client, {"mode": "tail", "n": 2})
    assert resp.status_code == 200, resp.get_json()
    assert valores(resp) == ["8", "9"]


def test_n_larger_than_df_is_clamped(client):
    """n > filas recorta al máximo, igual que head/tail de pandas."""
    upload(client)
    for mode in ("head", "tail", "random"):
        resp = sample(client, {"mode": mode, "n": 100})
        assert resp.status_code == 200, resp.get_json()
        assert len(resp.get_json()["data"]["data"]) == 9


def test_random_is_deterministic(client):
    """El seed fijo hace el muestreo reproducible: 2 ejecuciones = mismas filas."""
    upload(client)
    first = valores(sample(client, {"mode": "random", "n": 4}))
    # El estado mutó; subo de nuevo para repetir desde el mismo df.
    upload(client)
    second = valores(sample(client, {"mode": "random", "n": 4}))
    assert first == second
    assert len(first) == 4


def test_stratified_samples_n_per_group_including_nulls(client):
    upload(client)
    resp = sample(client, {"mode": "stratified", "n": 2, "by": "Grupo"})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    i_g = data["columns"].index("Grupo")
    counts = {}
    for row in data["data"]:
        key = row[i_g] if row[i_g] is not None else "<nulo>"
        counts[key] = counts.get(key, 0) + 1
    # 3 estratos (a, b, nulo) × 2 filas por estrato.
    assert counts == {"a": 2, "b": 2, "<nulo>": 2}


def test_stratified_on_empty_df_is_noop(client):
    """Dataset vacío → stratified no falla y devuelve 0 filas."""
    upload(client, "G,v\n")  # solo cabecera
    resp = sample(client, {"mode": "stratified", "n": 2, "by": "G"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["data"] == []


def test_stratified_clamps_small_groups(client):
    """Estrato con menos de n filas da todas sus filas, sin error."""
    upload(client, "G,v\nx,1\nx,2\ny,3\ny,4\ny,5\n")
    resp = sample(client, {"mode": "stratified", "n": 10, "by": "G"})
    assert resp.status_code == 200, resp.get_json()
    assert len(resp.get_json()["data"]["data"]) == 5


# ── Errores (ValueError → 500) ─────────────────────────────────────────
@pytest.mark.parametrize(
    "params",
    [
        {"mode": "median", "n": 2},          # mode desconocido
        {"mode": "head", "n": 0},            # n < 1
        {"mode": "head", "n": -3},           # n negativo
        {"mode": "head", "n": "abc"},        # n no entero
        {"mode": "stratified", "n": 2},      # sin by
        {"mode": "stratified", "n": 2, "by": "NoExiste"},  # columna inexistente
    ],
)
def test_invalid_params_return_500_without_mutating(client, params):
    upload(client)
    resp = sample(client, params)
    assert resp.status_code == 500
    payload = resp.get_json()
    assert "error" in payload
    # El dataset quedó intacto (9 filas originales).
    assert app_module.current_df is not None
    assert len(app_module.current_df) == 9


# ── Código generado ────────────────────────────────────────────────────
def test_generated_code_reproduces_the_result(client):
    """El fragmento exportado, ejecutado standalone, produce el mismo df."""
    upload(client)
    resp = sample(client, {"mode": "stratified", "n": 1, "by": "Grupo"})
    assert resp.status_code == 200, resp.get_json()
    fragment = resp.get_json()["last_code"]
    assert "random_state=42" in fragment

    df = pd.read_csv(io.StringIO(BASE_CSV))
    ns = {"df": df, "pd": pd}
    exec(fragment, ns)  # noqa: S102 — el script exportado hace exactamente esto
    assert len(ns["df"]) == 3  # 3 estratos × 1
    assert list(ns["df"]["Valor"]) == [int(v) for v in valores(resp)]


def test_random_code_contains_seed(client):
    upload(client)
    resp = sample(client, {"mode": "random", "n": 2})
    assert "random_state=42" in resp.get_json()["last_code"]


# ── Receta (round-trip) ────────────────────────────────────────────────
def test_sampling_survives_recipe_roundtrip(client):
    """Un paso sampling entra en la receta y se reproduce igual (seed fijo)."""
    upload(client)
    resp = sample(client, {"mode": "random", "n": 4})
    assert resp.status_code == 200
    expected = valores(resp)

    recipe = client.post("/export_recipe", json={"filename": "r"})
    assert recipe.status_code == 200
    import json as jsonlib
    steps = jsonlib.loads(recipe.data)["steps"]
    assert steps[-1]["op"] == "sampling"
    assert steps[-1]["params"]["mode"] == "random"

    # Undo del paso y reproducción de la receta completa.
    assert client.post("/undo").status_code == 200
    applied = client.post("/apply_recipe", json=jsonlib.loads(recipe.data))
    assert applied.status_code == 200, applied.get_json()
    assert valores(applied) == expected
