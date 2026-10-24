"""Tests de la barra de benchmark `GET /benchmark` (roadmap).

Tiempo por paso para detectar cuellos de botella. La propiedad central es
el alineamiento con `op_history` vía la lista paralela `step_ms`:

* una op nueva trunca la cola de rehacer (`step_ms` queda con la misma
  profundidad que `op_history`);
* un undo NO borra el tiempo — `/benchmark` lo rebana con `zip`, así que
  la barra se ajusta y un `/redo` recupera el MISMO ms original;
* aplicar una receta añade un tiempo por paso (callback `on_step`) solo
  si la receta entera tiene éxito (atomicidad intacta).
"""
import io

import pytest

import app as app_module


BASE_CSV = (
    "Nombre,Edad,Ciudad\n"
    "  Ana ,30,Madrid\n"
    "Luis ,25,Barcelona\n"
    "Carla,35,Madrid\n"
)

RECIPE_OK = {
    "version": 1,
    "steps": [
        {"op": "change_case", "params": {"column": "Nombre", "case": "title"}},
        {"op": "trim", "params": {"columns": ["Nombre"]}},
    ],
}

RECIPE_BROKEN = {
    "version": 1,
    "steps": [
        {"op": "trim", "params": {"columns": ["Nombre"]}},
        {"op": "op_fantasma", "params": {}},
    ],
}


def upload(client, csv_text=BASE_CSV, filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def op(client, name, params):
    resp = client.post("/operation", json={"operation": name, "params": params})
    assert resp.status_code == 200, resp.get_json()
    return resp


def get_bench(client):
    return client.get("/benchmark")


# ── Endpoints ───────────────────────────────────────────────────────────
def test_without_data_is_error(client):
    resp = get_bench(client)
    assert resp.status_code == 400
    assert "No hay datos" in resp.get_json()["error"]


def test_without_steps_returns_empty(client):
    upload(client)
    assert get_bench(client).get_json() == {"steps": [], "total_ms": 0}


def test_one_operation_reports_its_ms(client):
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    body = get_bench(client).get_json()
    assert len(body["steps"]) == 1
    assert body["steps"][0]["op"] == "trim"
    assert isinstance(body["steps"][0]["ms"], (int, float))
    assert body["steps"][0]["ms"] >= 0
    assert body["total_ms"] == pytest.approx(body["steps"][0]["ms"], abs=0.01)


def test_steps_align_with_op_history(client):
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    op(client, "drop_nulls", {"columns": ["Ciudad"], "how": "any"})
    op(client, "sort", {"column": "Edad", "ascending": True})
    body = get_bench(client).get_json()
    assert [s["op"] for s in body["steps"]] == ["trim", "drop_nulls", "sort"]
    assert [s["op"] for s in body["steps"]] == [
        s["op"] for s in app_module.op_history
    ]
    assert body["total_ms"] == pytest.approx(
        sum(s["ms"] for s in body["steps"]), abs=0.01
    )


def test_undo_shrinks_and_redo_recovers_the_same_ms(client):
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    op(client, "sort", {"column": "Edad", "ascending": True})
    before = get_bench(client).get_json()["steps"]

    assert client.post("/undo").status_code == 200
    after_undo = get_bench(client).get_json()["steps"]
    assert [s["op"] for s in after_undo] == ["trim"]  # la barra se ajusta

    assert client.post("/redo").status_code == 200
    after_redo = get_bench(client).get_json()["steps"]
    assert after_redo == before  # MISMO ms original, no vuelve a medir


def test_new_operation_after_undo_discards_the_redo_tail(client):
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    op(client, "sort", {"column": "Edad", "ascending": True})
    client.post("/undo")
    # Avance del pipeline: la cola de rehacer (y su ms) queda descartada
    op(client, "drop_duplicates", {"columns": ["Ciudad"]})

    body = get_bench(client).get_json()
    assert [s["op"] for s in body["steps"]] == ["trim", "drop_duplicates"]
    assert len(app_module.step_ms) == len(app_module.op_history) == 2
    assert client.post("/redo").status_code == 400  # sin nada que rehacer


def test_upload_resets_benchmark(client):
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    upload(client, "Nombre,Ciudad\nAna,Madrid\n", "otro.csv")
    assert get_bench(client).get_json() == {"steps": [], "total_ms": 0}
    assert app_module.step_ms == []


def test_apply_recipe_adds_one_ms_per_step(client):
    upload(client)
    resp = client.post("/apply_recipe", json=RECIPE_OK)
    assert resp.status_code == 200, resp.get_json()
    body = get_bench(client).get_json()
    assert [s["op"] for s in body["steps"]] == ["change_case", "trim"]
    assert all(s["ms"] >= 0 for s in body["steps"])
    assert len(app_module.step_ms) == len(app_module.op_history) == 2


def test_failed_recipe_leaves_benchmark_intact(client):
    """Atomicidad: una receta que truena no escribe step_ms."""
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    before = get_bench(client).get_json()

    resp = client.post("/apply_recipe", json=RECIPE_BROKEN)
    assert resp.status_code == 400
    assert "paso 2" in resp.get_json()["error"]
    assert get_bench(client).get_json() == before
    assert len(app_module.step_ms) == 1


def test_benchmark_never_touches_the_pipeline(client):
    upload(client)
    op(client, "trim", {"columns": ["Nombre"]})
    before = {
        "history": len(app_module.history),
        "op_history": len(app_module.op_history),
        "lineage": client.get("/lineage").get_json(),
        "step_ms": list(app_module.step_ms),
    }
    assert get_bench(client).status_code == 200
    assert len(app_module.history) == before["history"]
    assert len(app_module.op_history) == before["op_history"]
    assert client.get("/lineage").get_json() == before["lineage"]
    assert app_module.step_ms == before["step_ms"]
    assert client.post("/undo").status_code == 200
