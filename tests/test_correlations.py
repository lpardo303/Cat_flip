"""Tests del perfilado de correlaciones `GET /correlations` (roadmap).

Alimenta el heatmap del tab Diagnóstico: matriz de Pearson de las columnas
numéricas. Tres propiedades a defender:

1. **Solo lectura** — igual que `/stats`, no toca el pipeline.
2. **JSON válido siempre** — una columna constante da `NaN` en pandas; la
   respuesta lo convierte en `null` (nunca un `NaN` suelto, que rompería
   el `response.json()` del navegador).
3. **Selección numérica** — excluye texto y booleanos (pandas trata bool
   como numérico en `.corr()`).
"""
import io

import pytest

import app as app_module


BASE_CSV = "A,B,Texto\n1,4,x\n2,3,y\n3,2,x\n4,1,y\n"


def upload(client, csv_text=BASE_CSV, filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def get_corr(client):
    return client.get("/correlations")


# ── Endpoints ───────────────────────────────────────────────────────────
def test_without_data_is_error(client):
    resp = get_corr(client)
    assert resp.status_code == 400
    assert "No hay datos" in resp.get_json()["error"]


def test_perfect_negative_correlation(client):
    """A = 1..4, B = 4..1 → r = -1 exacto, diagonal a 1."""
    upload(client)
    body = get_corr(client).get_json()
    assert body["columns"] == ["A", "B"]
    assert body["matrix"] == [[1.0, -1.0], [-1.0, 1.0]]


def test_perfect_positive_correlation(client):
    upload(client, "A,B\n1,10\n2,20\n3,30\n")
    body = get_corr(client).get_json()
    assert body["matrix"][0][1] == pytest.approx(1.0)


def test_excludes_text_and_bool_columns(client):
    upload(client, "Num1,Num2,Flag,Texto\n1,2,true,x\n2,4,false,y\n3,6,true,z\n")
    body = get_corr(client).get_json()
    assert body["columns"] == ["Num1", "Num2"]
    assert len(body["matrix"]) == 2


def test_single_numeric_column_returns_empty_matrix(client):
    upload(client, "Num,Texto\n1,x\n2,y\n")
    body = get_corr(client).get_json()
    assert body["columns"] == ["Num"]
    assert body["matrix"] == []  # el front muestra su aviso con esto


def test_no_numeric_columns(client):
    upload(client, "Texto,Otro\nx,a\ny,b\n")
    resp = get_corr(client)
    assert resp.status_code == 200
    assert resp.get_json() == {"columns": [], "matrix": []}


def test_constant_column_is_null_not_nan(client):
    """Columna constante → NaN en pandas → null en JSON (parse válido)."""
    upload(client, "K,B\n5,1\n5,2\n5,3\n5,4\n")
    resp = get_corr(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["matrix"][0][0] is None  # K vs K
    assert body["matrix"][1][0] is None  # K vs B
    # El JSON textual no contiene un NaN suelto
    assert "NaN" not in resp.get_data(as_text=True)


def test_nulls_use_pairwise_complete_rows(client):
    """Borrado por pares: la fila toda nula no contamina el cálculo."""
    upload(client, "A,B\n1,1\n2,2\n,\n")
    body = get_corr(client).get_json()
    # Solo las 2 filas con ambos valores → correlación perfecta 1.0
    assert body["matrix"][0][1] == pytest.approx(1.0)


def test_values_are_rounded_to_4_decimals(client):
    upload(client, "A,B\n1,2\n2,3\n3,5\n4,8\n5,13\n")
    v = get_corr(client).get_json()["matrix"][0][1]
    assert v == round(v, 4)


def test_matrix_is_symmetric_with_unit_diagonal(client):
    upload(client, "X,Y,Z\n1,5,2\n2,4,3\n3,7,1\n4,6,5\n5,9,4\n")
    m = get_corr(client).get_json()["matrix"]
    for i in range(3):
        assert m[i][i] == pytest.approx(1.0)
        for j in range(3):
            assert m[i][j] == pytest.approx(m[j][i])


def test_matches_pandas_corr(client):
    """Paridad: la respuesta es `df.corr()` sobre las numéricas, redondeado."""
    upload(client, "A,B,C\n1,9,2\n2,7,5\n3,8,1\n4,6,9\n5,4,3\n6,5,7\n")
    body = get_corr(client).get_json()
    assert body["columns"] == ["A", "B", "C"]
    expected = app_module.current_df[["A", "B", "C"]].corr().round(4)
    for i in range(3):
        for j in range(3):
            assert body["matrix"][i][j] == pytest.approx(float(expected.iloc[i, j]))


def test_never_touches_the_pipeline(client):
    """SOLO LEE: ni history, ni op_history, ni linaje, ni undo."""
    upload(client)
    client.post(
        "/operation",
        json={"operation": "sort", "params": {"column": "A", "ascending": True}},
    )
    before = {
        "history": len(app_module.history),
        "op_history": len(app_module.op_history),
        "lineage": client.get("/lineage").get_json(),
    }
    assert get_corr(client).status_code == 200
    assert len(app_module.history) == before["history"]
    assert len(app_module.op_history) == before["op_history"]
    assert client.get("/lineage").get_json() == before["lineage"]
    assert client.post("/undo").status_code == 200
