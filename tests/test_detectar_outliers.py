"""Tests del op detectar_outliers (#23): marcado de anomalías numéricas.

Cubre Z-Score (ddof=0, default 2.5) e IQR (k default 1.5), umbral
custom, multicolumna, flag nulo donde el valor es nulo, columnas con
dispersión 0 (todo False sin dividir entre cero), ejecución del código
generado y todos los ValueError que el endpoint traduce a 500 sin mutar
el estado.
"""
import io

import pandas as pd
import pytest

import app as app_module

# Valor: [10,11,12,10,11,12,10,11,100] + 1 nulo.
# z(100) ≈ 2.83 → flag con umbral 2.5; el resto < 0.4.
# IQR k=1.5: Q1=10, Q3=11, upper=12.5 → solo 100 sale.
# Otro: [1..10] → sin flags con ninguno de los dos métodos.
BASE_CSV = (
    "Grupo,Valor,Otro\n"
    "g1,10,1\n"
    "g1,11,2\n"
    "g1,12,3\n"
    "g1,10,4\n"
    "g1,11,5\n"
    "g1,12,6\n"
    "g1,10,7\n"
    "g1,11,8\n"
    "g1,100,9\n"
    "g1,,10\n"
)

CONST_CSV = "C\n5\n5\n5\n5\n"


def upload(client, csv_text=BASE_CSV, filename="outliers.csv"):
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


def flags(resp, col):
    """Flags (True/False/None) de {col}_outlier.

    El payload serializa celdas como string ('True'/'False') y nulos como
    JSON null; el helper invierte esa conversión a valores Python.
    """
    data = resp.get_json()["data"]
    i = data["columns"].index(f"{col}_outlier")
    return [None if row[i] is None else row[i] == "True" for row in data["data"]]


# ── Happy path ─────────────────────────────────────────────────────────

def test_zscore_default_flags_only_extreme(client):
    upload(client)
    resp = op(client, "detectar_outliers", {"columns": ["Valor"]})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["dtypes"]["Valor_outlier"] == "BOOL"
    f = flags(resp, "Valor")
    assert f[:8] == [False] * 8
    assert f[8] is True           # 100 → |z| ≈ 2.83 > 2.5
    assert f[9] is None           # valor nulo → flag nulo
    assert data["nulls"]["Valor_outlier"] == 1


def test_iqr_flags_only_extreme(client):
    upload(client)
    resp = op(client, "detectar_outliers", {
        "columns": ["Valor"], "method": "iqr",
    })
    assert resp.status_code == 200, resp.get_json()
    f = flags(resp, "Valor")
    assert f[:8] == [False] * 8
    assert f[8] is True           # 100 > Q3 + 1.5·IQR = 12.5
    assert f[9] is None


def test_custom_threshold_changes_flags(client):
    """Umbral 3.0 > z(100)≈2.83 → ningún flag. El umbral sí aplica."""
    upload(client)
    resp = op(client, "detectar_outliers", {
        "columns": ["Valor"], "method": "zscore", "threshold": 3,
    })
    assert resp.status_code == 200, resp.get_json()
    assert flags(resp, "Valor") == [False] * 9 + [None]


def test_multicolumn_two_flag_columns(client):
    upload(client)
    resp = op(client, "detectar_outliers", {
        "columns": ["Valor", "Otro"],
    })
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert "Valor_outlier" in data["columns"]
    assert "Otro_outlier" in data["columns"]
    assert flags(resp, "Valor")[8] is True
    assert flags(resp, "Otro") == [False] * 10  # [1..10] sin anomalías


def test_constant_column_all_false(client):
    """Dispersión 0 → todo False, sin división por cero ni error."""
    upload(client, csv_text=CONST_CSV, filename="const.csv")
    resp = op(client, "detectar_outliers", {"columns": ["C"]})
    assert resp.status_code == 200, resp.get_json()
    assert flags(resp, "C") == [False] * 4


def test_generated_code_executes_identically(client):
    """El código generado reproduce exactamente la marca de la op."""
    upload(client)
    resp = op(client, "detectar_outliers", {"columns": ["Valor"]})
    assert resp.status_code == 200, resp.get_json()
    code = resp.get_json()["last_code"]
    assert "Valor_outlier" in code and "ddof=0" in code and "# " in code
    compile(code, "<generated>", "exec")

    local = pd.read_csv(io.StringIO(BASE_CSV))
    exec(code, {"df": local, "float": float})
    expected = flags(resp, "Valor")
    got = [None if pd.isna(v) else bool(v) for v in local["Valor_outlier"]]
    assert got == expected


# ── Errores (500 con mensaje, sin mutar el estado) ─────────────────────

def test_no_columns_is_error(client):
    upload(client)
    resp = op(client, "detectar_outliers", {"columns": []})
    assert resp.status_code == 500
    assert "al menos una" in resp.get_json()["error"]
    assert len(app_module.history) == 1  # solo el upload


def test_non_numeric_column_is_error(client):
    upload(client)
    resp = op(client, "detectar_outliers", {"columns": ["Valor", "Grupo"]})
    assert resp.status_code == 500
    assert "no son numéricas" in resp.get_json()["error"]
    assert "Grupo" in resp.get_json()["error"]


def test_unknown_column_is_error(client):
    upload(client)
    resp = op(client, "detectar_outliers", {"columns": ["Fantasma"]})
    assert resp.status_code == 500
    assert "no existe" in resp.get_json()["error"]


def test_bad_method_is_error(client):
    upload(client)
    resp = op(client, "detectar_outliers", {"columns": ["Valor"], "method": "manhattan"})
    assert resp.status_code == 500
    assert "Método no válido" in resp.get_json()["error"]


def test_non_numeric_threshold_is_error(client):
    upload(client)
    resp = op(client, "detectar_outliers", {
        "columns": ["Valor"], "threshold": "alta",
    })
    assert resp.status_code == 500
    assert "Umbral no numérico" in resp.get_json()["error"]


def test_zero_threshold_is_error(client):
    upload(client)
    resp = op(client, "detectar_outliers", {"columns": ["Valor"], "threshold": 0})
    assert resp.status_code == 500
    assert "mayor que cero" in resp.get_json()["error"]
    assert len(app_module.history) == 1  # sin estado parcial


def test_flag_column_collision_is_error(client):
    upload(client)
    first = op(client, "detectar_outliers", {"columns": ["Valor"]})
    assert first.status_code == 200, first.get_json()
    second = op(client, "detectar_outliers", {"columns": ["Valor"]})
    assert second.status_code == 500
    assert "ya existe" in second.get_json()["error"]
    assert len(app_module.history) == 2  # upload + 1 op: sin parcial
