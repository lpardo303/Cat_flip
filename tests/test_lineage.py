"""Tests del endpoint /lineage (F3.3): grafo de linaje del pipeline.

Contrato: `{"nodes": [{id, op, params, rows, cols}], "edges": [[i, i+1], ...]}`.
Nodo 0 = dataset original; cada operación añade un nodo con el shape del
snapshot resultante. El reset de globals en conftest aísla cada test.
"""
import io


BASE_CSV = (
    "Nombre,Edad,Ciudad\n"
    "Alice ,30,Madrid\n"
    "Bob,25,Barcelona\n"
)


def upload(client):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(BASE_CSV.encode("utf-8")), "data.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def test_lineage_sin_datos_devuelve_400(client):
    resp = client.get("/lineage")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_lineage_tras_upload_un_solo_nodo_fuente(client):
    upload(client)
    resp = client.get("/lineage")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["nodes"] == [{"id": 0, "op": "dataset", "params": {}, "rows": 2, "cols": 3}]
    assert payload["edges"] == []


def test_lineage_ops_anaden_nodos_y_undo_quita(client):
    upload(client)
    r1 = client.post("/operation", json={"operation": "trim", "params": {"columns": ["Nombre"]}})
    assert r1.status_code == 200, r1.get_json()
    r2 = client.post(
        "/operation",
        json={"operation": "sort", "params": {"column": "Edad", "ascending": True}},
    )
    assert r2.status_code == 200, r2.get_json()

    payload = client.get("/lineage").get_json()
    assert [n["op"] for n in payload["nodes"]] == ["dataset", "trim", "sort"]
    assert payload["nodes"][1]["params"] == {"columns": ["Nombre"]}
    assert payload["edges"] == [[0, 1], [1, 2]]
    assert all(n["rows"] == 2 and n["cols"] == 3 for n in payload["nodes"])

    undo = client.post("/undo")
    assert undo.status_code == 200
    payload = client.get("/lineage").get_json()
    assert [n["op"] for n in payload["nodes"]] == ["dataset", "trim"]
    assert payload["edges"] == [[0, 1]]
