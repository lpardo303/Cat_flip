"""Tests de la operación group_by (op #18 — Group By + Agregación).

Contrato: params `{by: str|list, column, func}` → `df.groupby(by,
dropna=False, as_index=False).agg({column: func})`. `by` como string se
normaliza a lista. Función inválida propaga el error de pandas como 500
(consistente con el resto de operaciones).
"""
import io

import pytest


BASE_CSV = (
    "Region,Producto,Unidades\n"
    "Norte,Teclado,10\n"
    "Sur,Ratón,5\n"
    "Norte,Ratón,7\n"
    "Norte,Teclado,3\n"
    "Sur,Monitor,2\n"
)


def upload(client, csv_text=BASE_CSV):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), "data.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def group_by(client, **params):
    return client.post("/operation", json={"operation": "group_by", "params": params})


def test_group_by_sum_agrupa_y_suma(client):
    upload(client)
    resp = group_by(client, by="Region", column="Unidades", func="sum")
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    data = payload["data"]

    # 5 filas → 3 regiones: Norte 20, Sur 7
    assert data["total_rows"] == 2
    assert data["columns"] == ["Region", "Unidades"]
    i_region = data["columns"].index("Region")
    i_uni = data["columns"].index("Unidades")
    sums = {row[i_region]: row[i_uni] for row in data["data"]}
    assert sums == {"Norte": "20", "Sur": "7"}

    # Código autogenerado con groupby y el recuento de grupos
    assert "groupby" in payload["last_code"]
    assert "2 grupo(s)" in payload["last_code"]


@pytest.mark.parametrize(
    "func, expected_norte",
    [
        ("mean", 6.67),      # (10+7+3)/3 → redondeado abajo en el aserto
        ("count", 3),
        ("min", 3),
        ("max", 10),
        ("median", 7),
        ("nunique", 3),
    ],
    ids=["mean", "count", "min", "max", "median", "nunique"],
)
def test_group_by_funcs_parametrizadas(client, func, expected_norte):
    upload(client)
    resp = group_by(client, by="Region", column="Unidades", func=func)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    i_region = data["columns"].index("Region")
    i_uni = data["columns"].index("Unidades")
    values = {row[i_region]: float(row[i_uni]) for row in data["data"]}
    assert values["Norte"] == pytest.approx(expected_norte, abs=0.01)


def test_group_by_acepta_by_como_string_y_como_lista(client):
    upload(client)
    r1 = group_by(client, by="Region", column="Unidades", func="sum")
    assert r1.status_code == 200
    upload(client)  # reset del pipeline
    r2 = group_by(client, by=["Region"], column="Unidades", func="sum")
    assert r2.status_code == 200
    d1, d2 = r1.get_json()["data"], r2.get_json()["data"]
    assert d1["total_rows"] == d2["total_rows"] == 2
    assert d1["data"] == d2["data"]


def test_group_by_func_invalida_devuelve_500(client):
    upload(client)
    resp = group_by(client, by="Region", column="Unidades", func="median_de_masas")
    assert resp.status_code == 500
    assert "error" in resp.get_json()
