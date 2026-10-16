"""Tests de la operación Join/Merge (op #19) y su frame derecho.

Patrón: helpers locales autocontenidos (upload + upload_right + merge),
casos parametrizados por tipo de cruce y cobertura de los 4 caminos de
error del contrato (400 sin frame derecho / 500 params inválidos).
"""
import io

import pytest

import app as app_module

BASE_CSV = (
    "Region,Producto,Ventas\n"
    "Norte,Teclado,100\n"
    "Sur,Ratón,200\n"
    "Este,Monitor,150\n"
)
# Claves distintas a las de BASE (Norte/Sur/Este): añade Oeste, no tiene Este
RIGHT_CSV = (
    "Region,Meta\n"
    "Norte,120\n"
    "Sur,250\n"
    "Oeste,80\n"
)
# Clave con nombre diferente (para left_on/right_on)
RIGHT_RENAMED_CSV = (
    "Zona,Meta\n"
    "Norte,120\n"
    "Sur,250\n"
    "Oeste,80\n"
)
# Solapa la columna no-clave "Ventas" -> suffixes
RIGHT_OVERLAP_CSV = (
    "Region,Ventas,Meta\n"
    "Norte,999,120\n"
    "Sur,888,250\n"
    "Oeste,777,80\n"
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


def upload_right(client, csv_text=RIGHT_CSV, filename="regions.csv"):
    resp = client.post(
        "/upload_right",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def merge(client, **overrides):
    params = {
        "left_on": "Region",
        "right_on": "Region",
        "how": "left",
        "suffixes": ["_x", "_y"],
    }
    params.update(overrides)
    return client.post(
        "/operation", json={"operation": "merge", "params": params}
    )


def cell(payload, row, col):
    i = payload["data"]["columns"].index(col)
    return payload["data"]["data"][row][i]


# ── happy path ─────────────────────────────────────────────────────────
def test_merge_left_join_same_key_columns(client):
    upload(client)
    upload_right(client)
    resp = merge(client)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["success"] is True
    data = body["data"]
    # 3 filas izquierdas conservadas + columna Meta del frame derecho
    assert data["total_rows"] == 3
    assert data["columns"] == ["Region", "Producto", "Ventas", "Meta"]
    # NaN de Este promociona Meta a float64: df_to_json renderiza 120.0
    assert cell(body, 0, "Meta") == "120.0"    # Norte, coincidencia
    assert cell(body, 2, "Meta") == ""         # Este, sin match -> NaN


@pytest.mark.parametrize(
    "how,expected_rows",
    [
        pytest.param("inner", 2, id="how_inner"),
        pytest.param("left", 3, id="how_left"),
        pytest.param("right", 3, id="how_right"),
        pytest.param("outer", 4, id="how_outer"),
    ],
)
def test_merge_how_types(client, how, expected_rows):
    upload(client)
    upload_right(client)
    resp = merge(client, how=how)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["total_rows"] == expected_rows
    assert len(app_module.history) == 2


def test_merge_different_key_names(client):
    upload(client)
    upload_right(client, RIGHT_RENAMED_CSV, "zonas.csv")
    resp = merge(client, left_on="Region", right_on="Zona")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    # claves con nombre distinto: ambas columnas quedan en el resultado
    assert data["total_rows"] == 3
    assert "Region" in data["columns"] and "Zona" in data["columns"]
    assert "Meta" in data["columns"]


def test_merge_suffixes_rename_overlapping_columns(client):
    upload(client)
    upload_right(client, RIGHT_OVERLAP_CSV)
    resp = merge(client)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    cols = body["data"]["columns"]
    assert "Ventas_x" in cols and "Ventas_y" in cols
    assert "Ventas" not in cols
    assert cell(body, 0, "Ventas_x") == "100"   # valor izquierdo original
    # Ventas_y contiene NaN (fila Este): promoción a float igual que Meta
    assert cell(body, 0, "Ventas_y") == "999.0"  # valor del frame derecho


# ── código generado / script / linaje / undo ───────────────────────────
def test_merge_code_contains_right_load_and_merge(client):
    upload(client)
    upload_right(client)
    body = merge(client).get_json()
    assert "df_right = pd.read_csv('regions.csv'" in body["last_code"]
    assert "df.merge(df_right" in body["last_code"]
    assert "how='left'" in body["last_code"]
    assert len(app_module.code_log) == 2  # carga + merge


def test_export_script_includes_right_frame_load(client):
    upload(client)
    upload_right(client)
    merge(client)
    resp = client.post("/export_script", json={"filename": "pipeline"})
    assert resp.status_code == 200
    script = resp.data.decode("utf-8")
    assert "import pandas as pd" in script
    assert "df_right = pd.read_csv('regions.csv'" in script
    assert "df = df.merge(df_right" in script


def test_lineage_node_includes_right_source(client):
    upload(client)
    upload_right(client)
    merge(client)
    nodes = client.get("/lineage").get_json()["nodes"]
    assert len(nodes) == 2  # dataset + merge
    node = nodes[1]
    assert node["op"] == "merge"
    assert node["params"]["right_name"] == "regions.csv"
    assert node["params"]["how"] == "left"
    assert node["params"]["left_on"] == "Region"
    assert (node["rows"], node["cols"]) == (3, 4)


def test_undo_after_merge_restores_original(client):
    upload(client)
    upload_right(client)
    merge(client)
    resp = client.post("/undo")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["columns"] == ["Region", "Producto", "Ventas"]
    assert data["total_rows"] == 3
    assert len(app_module.op_history) == 0


def test_merge_accumulates_history_and_recipe_state(client):
    upload(client)
    upload_right(client)
    merge(client, how="inner")
    assert len(app_module.history) == 2
    assert len(app_module.op_history) == 1
    assert len(app_module.code_log) == 2


# ── caminos de error ───────────────────────────────────────────────────
def test_merge_without_right_frame_returns_400(client):
    upload(client)
    resp = merge(client)
    assert resp.status_code == 400
    assert "frame derecho" in resp.get_json()["error"]


def test_merge_unknown_left_column_returns_500(client):
    upload(client)
    upload_right(client)
    resp = merge(client, left_on="NoExiste")
    assert resp.status_code == 500
    assert "no existe en el dataset activo" in resp.get_json()["error"]


def test_merge_unknown_right_column_returns_500(client):
    upload(client)
    upload_right(client)
    resp = merge(client, right_on="NoExiste")
    assert resp.status_code == 500
    assert "no existe en el frame derecho" in resp.get_json()["error"]


def test_merge_invalid_how_returns_500(client):
    upload(client)
    upload_right(client)
    resp = merge(client, how="cross_fire")
    assert resp.status_code == 500
    assert "no válido" in resp.get_json()["error"]


def test_merge_missing_key_returns_500(client):
    upload(client)
    upload_right(client)
    resp = merge(client, left_on="")
    assert resp.status_code == 500
    assert "columna de cruce" in resp.get_json()["error"]


def test_op_merge_handler_guard_without_right_frame():
    """Guard del handler: defensa directa si un caller no pasa right_df.

    El endpoint devuelve 400 antes de llegar aquí; esta prueba protege la
    validación interna de op_merge (operations.py al 100%).
    """
    import pandas as pd

    from operations import op_merge

    with pytest.raises(ValueError, match="frame derecho"):
        op_merge(pd.DataFrame({"a": [1]}), {"left_on": "a", "right_on": "a"})


# ── endpoints del frame derecho ────────────────────────────────────────
def test_upload_right_returns_name_and_columns(client):
    resp = upload_right(client)
    body = resp.get_json()
    assert body["success"] is True
    assert body["name"] == "regions.csv"
    assert body["data"]["columns"] == ["Region", "Meta"]
    assert body["data"]["total_rows"] == 3


def test_upload_right_unsupported_format_returns_400(client):
    resp = client.post(
        "/upload_right",
        data={"file": (io.BytesIO(b"cualquier cosa"), "archivo.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "Formato no soportado" in resp.get_json()["error"]
    assert app_module.right_df is None  # estado intacto tras el fallo


def test_right_info_reflects_state(client):
    body = client.get("/right_info").get_json()
    assert body == {"loaded": False}

    upload_right(client)
    info = client.get("/right_info").get_json()
    assert info["loaded"] is True
    assert info["name"] == "regions.csv"
    assert info["columns"] == ["Region", "Meta"]
    assert info["shape"] == [3, 2]


def test_upload_right_replaces_previous_frame(client):
    upload_right(client)
    upload_right(client, "Clave,Valor\nA,1\n", "otro.csv")
    info = client.get("/right_info").get_json()
    assert info["name"] == "otro.csv"
    assert info["columns"] == ["Clave", "Valor"]
