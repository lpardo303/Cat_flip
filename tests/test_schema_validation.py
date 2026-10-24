"""Tests de la validación de esquema — reglas rango/regex/no-nulo/único.

Dos niveles, igual que el resto del backend:

1. **Núcleo puro** (`validate_rules` + `validate_schema` en operations.py):
   qué celda marca cada regla, sin tocar el DataFrame.
2. **Endpoints** (`POST /schema_rules`, `GET /schema_validate`): mensajes
   de error, ausencia de estado parcial y el reset al subir un archivo
   nuevo. Ninguno de los dos altera el pipeline (history/code_log/
   op_history).
"""
import io

import pandas as pd
import pytest

import app as app_module
from operations import validate_rules, validate_schema


BASE_CSV = (
    "Nombre,Edad,Ciudad\n"
    "  Ana ,30,Madrid\n"
    "Luis ,25,\n"
    "Ana ,30,Madrid\n"
    "Carla,35,Sevilla\n"
)


def upload(client, csv_text=BASE_CSV, filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def set_rules(client, rules):
    return client.post("/schema_rules", json={"rules": rules})


def get_validate(client):
    return client.get("/schema_validate")


@pytest.fixture()
def df():
    """df de 4 filas: 1 nulo en Ciudad, Madrid duplicado (filas 0 y 2)."""
    return pd.read_csv(io.StringIO(BASE_CSV))


def violations_at(result, column, rule):
    """Posiciones (base 0) de una columna/regla concretas del resultado."""
    return [v["row"] for v in result["violations"]
            if v["column"] == column and v["rule"] == rule]


# ── validate_rules: validación de la lista completa ─────────────────────
def test_validate_rules_normalizes_entries(df):
    rules = validate_rules(df, [
        {"column": "Ciudad", "rule": "not_null"},
        {"column": "Nombre", "rule": "regex", "pattern": r"[A-Za-z ]+"},
        {"column": "Edad", "rule": "range", "min": 0, "max": 120, "ignorada": True},
        {"column": "Edad", "rule": "unique"},
    ])
    assert rules == [
        {"column": "Ciudad", "rule": "not_null"},
        {"column": "Nombre", "rule": "regex", "pattern": r"[A-Za-z ]+"},
        {"column": "Edad", "rule": "range", "min": 0.0, "max": 120.0},
        {"column": "Edad", "rule": "unique"},
    ]


def test_validate_rules_empty_list_is_valid(df):
    assert validate_rules(df, []) == []


@pytest.mark.parametrize("bad,fragmento", [
    ({"not": "a list"}, "lista"),
    (["no-objeto"], "regla 1"),
    ([{"column": "Fantasma", "rule": "not_null"}], "regla 1"),
    ([{"column": "Edad", "rule": "not_null"},
      {"column": "Edad", "rule": "op_fantasma"}], "regla 2"),
    ([{"column": "Nombre", "rule": "regex"}], "patrón"),
    ([{"column": "Nombre", "rule": "regex", "pattern": ""}], "patrón"),
    ([{"column": "Nombre", "rule": "regex", "pattern": "["}], "inválida"),
    ([{"column": "Nombre", "rule": "regex", "pattern": "a" * 501}], "500"),
    ([{"column": "Nombre", "rule": "regex", "pattern": r"\s*"}], "vacía"),
    ([{"column": "Edad", "rule": "range"}], "mínimo y/o máximo"),
    ([{"column": "Edad", "rule": "range", "min": 10, "max": 5}], "mínimo"),
    ([{"column": "Edad", "rule": "range", "min": "diez"}], "numérico"),
    ([{"column": "Nombre", "rule": "range", "min": 1}], "numérica"),
])
def test_validate_rules_rejects_bad_rules(df, bad, fragmento):
    """Cada regla mala se cita por su posición y con mensaje descriptivo."""
    with pytest.raises(ValueError) as exc:
        validate_rules(df, bad)
    assert fragmento in str(exc.value)


def test_validate_rules_rejects_bool_column_for_range(df):
    df["Activo"] = [True, False, True, False]
    with pytest.raises(ValueError) as exc:
        validate_rules(df, [{"column": "Activo", "rule": "range", "min": 0}])
    assert "numérica" in str(exc.value)


# ── validate_schema: qué celda marca cada regla ─────────────────────────
def test_not_null_marks_only_null_cells(df):
    result = validate_schema(df, [{"column": "Ciudad", "rule": "not_null"}])
    assert result["total"] == 1
    assert violations_at(result, "Ciudad", "not_null") == [1]


def test_unique_marks_every_occurrence_but_not_nulls(df):
    # Madrid en filas 0 y 2; el nulo de la fila 1 no cuenta.
    result = validate_schema(df, [{"column": "Ciudad", "rule": "unique"}])
    assert violations_at(result, "Ciudad", "unique") == [0, 2]
    assert result["total"] == 2


def test_regex_fullmatch_marks_non_matching_non_null_cells(df):
    result = validate_schema(df, [
        {"column": "Nombre", "rule": "regex", "pattern": r"[A-Za-z ]+"},
    ])
    # Todas casan el fullmatch (los espacios sobrantes también), 0 fallos.
    assert result["total"] == 0

    result = validate_schema(df, [
        {"column": "Nombre", "rule": "regex", "pattern": r"[A-Z][a-z]+"},
    ])
    # "  Ana ", "Luis " y "Ana " llevan espacios → no casan el fullmatch.
    assert violations_at(result, "Nombre", "regex") == [0, 1, 2]


def test_regex_ignores_null_cells(df):
    result = validate_schema(df, [
        {"column": "Ciudad", "rule": "regex", "pattern": r"Madrid"},
    ])
    # Sevilla (fila 3) no casa; el nulo de la fila 1 se salta: lo marcaría
    # not_null, no la regex.
    assert violations_at(result, "Ciudad", "regex") == [3]


def test_range_bounds_are_inclusive(df):
    ok = validate_schema(df, [
        {"column": "Edad", "rule": "range", "min": 25, "max": 35},
    ])
    assert ok["total"] == 0  # 25 y 35 están DENTRO del rango

    bad = validate_schema(df, [
        {"column": "Edad", "rule": "range", "min": 26, "max": 34},
    ])
    assert violations_at(bad, "Edad", "range") == [1, 3]  # 25 y 35


def test_range_ignores_nulls_and_skips_non_convertible(df):
    df["Peso"] = [70.0, None, "n/d", 59.0]
    result = validate_schema(df, [
        {"column": "Peso", "rule": "range", "min": 60, "max": 80},
    ])
    # Nulo (1) y no convertible (2) se saltan; 59.0 (3) sí viola.
    assert violations_at(result, "Peso", "range") == [3]


def test_one_cell_can_accumulate_several_violations(df):
    result = validate_schema(df, [
        {"column": "Edad", "rule": "not_null"},
        {"column": "Edad", "rule": "range", "min": 31},
        {"column": "Edad", "rule": "unique"},
    ])
    # Edad = 30, 25, 30, 35: sin nulos; rango <31 marca 0, 1 y 2; el 30
    # duplicado marca las filas 0 y 2 (25 y 35 son únicos).
    assert violations_at(result, "Edad", "not_null") == []
    assert violations_at(result, "Edad", "range") == [0, 1, 2]
    assert violations_at(result, "Edad", "unique") == [0, 2]
    assert result["total"] == 5


def test_validate_schema_does_not_mutate_df(df):
    before = df.copy()
    validate_schema(df, [
        {"column": "Nombre", "rule": "not_null"},
        {"column": "Ciudad", "rule": "unique"},
        {"column": "Edad", "rule": "range", "min": 0},
    ])
    pd.testing.assert_frame_equal(df, before)


def test_violations_are_capped_but_total_and_counts_are_exact(df):
    big = pd.DataFrame({"x": list(range(100))})
    rules = [{"column": "x", "rule": "range", "min": 50}]
    result = validate_schema(big, rules, max_violations=10)
    assert len(result["violations"]) == 10
    assert result["total"] == 50  # el real, sin recortar
    assert result["counts"] == [{"column": "x", "rule": "range", "count": 50}]


def test_counts_summary_matches_violations(df):
    result = validate_schema(df, [
        {"column": "Ciudad", "rule": "not_null"},
        {"column": "Ciudad", "rule": "unique"},
        {"column": "Edad", "rule": "range", "min": 31},
    ])
    assert result["counts"] == [
        {"column": "Ciudad", "rule": "not_null", "count": 1},
        {"column": "Ciudad", "rule": "unique", "count": 2},
        {"column": "Edad", "rule": "range", "count": 3},
    ]


def test_validate_schema_rejects_unknown_rule_kind(df):
    with pytest.raises(ValueError) as exc:
        validate_schema(df, [{"column": "Edad", "rule": "op_fantasma"}])
    assert "desconocido" in str(exc.value)


# ── POST /schema_rules ──────────────────────────────────────────────────
def test_set_rules_without_data_is_error(client):
    resp = set_rules(client, [{"column": "Ciudad", "rule": "not_null"}])
    assert resp.status_code == 400
    assert "No hay datos cargados" in resp.get_json()["error"]


def test_set_rules_happy_path_returns_rules_and_violations(client):
    upload(client)
    resp = set_rules(client, [{"column": "Ciudad", "rule": "not_null"}])
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["success"] is True
    assert body["rules"] == [{"column": "Ciudad", "rule": "not_null"}]
    assert body["total"] == 1
    assert body["violations"] == [{"row": 1, "column": "Ciudad", "rule": "not_null"}]
    assert app_module.schema_rules == body["rules"]


def test_set_rules_with_broken_body_is_error(client):
    upload(client)
    resp = client.post("/schema_rules", data="{rota", content_type="application/json")
    assert resp.status_code == 400
    assert "JSON válido" in resp.get_json()["error"]


def test_set_rules_with_non_list_is_error(client):
    upload(client)
    resp = client.post("/schema_rules", json={"rules": {"column": "Ciudad"}})
    assert resp.status_code == 400
    assert "lista" in resp.get_json()["error"]


def test_bad_rule_rejected_without_touching_stored_rules(client):
    upload(client)
    assert set_rules(client, [{"column": "Ciudad", "rule": "not_null"}]).status_code == 200

    resp = set_rules(client, [
        {"column": "Ciudad", "rule": "not_null"},
        {"column": "Fantasma", "rule": "unique"},
    ])
    assert resp.status_code == 400
    assert "regla 2" in resp.get_json()["error"]
    # Sin estado parcial: la lista anterior sigue vigente.
    assert app_module.schema_rules == [{"column": "Ciudad", "rule": "not_null"}]


def test_empty_list_clears_rules(client):
    upload(client)
    set_rules(client, [{"column": "Ciudad", "rule": "not_null"}])
    body = set_rules(client, []).get_json()
    assert body["rules"] == []
    assert body["total"] == 0
    assert app_module.schema_rules == []


# ── GET /schema_validate ────────────────────────────────────────────────
def test_validate_without_data_is_error(client):
    resp = get_validate(client)
    assert resp.status_code == 400
    assert "No hay datos" in resp.get_json()["error"]


def test_validate_without_rules_returns_empty(client):
    upload(client)
    body = get_validate(client).get_json()
    assert body == {"rules": [], "violations": [], "total": 0, "counts": []}


def test_validate_recovers_saved_rules(client):
    upload(client)
    set_rules(client, [{"column": "Ciudad", "rule": "not_null"}])
    body = get_validate(client).get_json()
    assert body["rules"] == [{"column": "Ciudad", "rule": "not_null"}]
    assert body["total"] == 1


def test_rules_survive_an_operation_and_revalidate_against_new_df(client):
    """Las reglas persisten; las violaciones se recalculan tras la op."""
    upload(client)
    set_rules(client, [{"column": "Ciudad", "rule": "not_null"}])
    resp = client.post(
        "/operation",
        json={"operation": "drop_nulls", "params": {"columns": ["Ciudad"], "how": "any"}},
    )
    assert resp.status_code == 200, resp.get_json()
    body = get_validate(client).get_json()
    assert body["rules"] == [{"column": "Ciudad", "rule": "not_null"}]
    assert body["total"] == 0  # la op arregló el nulo → sin violaciones


def test_violation_rows_are_positions_not_index_labels(client):
    """`row` es la posición del grid, no la etiqueta del índice.

    drop_nulls conserva las etiquetas originales: el DataFrame queda con
    índice [0, 2, 3] y Madrid pasa a ocupar las POSICIONES 0 y 1 — así que
    las violaciones deben venir como 0 y 1, nunca como 0 y 2.
    """
    upload(client)
    client.post("/operation", json={
        "operation": "drop_nulls",
        "params": {"columns": ["Ciudad"], "how": "any"},
    })
    assert app_module.current_df.index.tolist() == [0, 2, 3]  # etiquetas rotas
    set_rules(client, [{"column": "Ciudad", "rule": "unique"}])
    body = get_validate(client).get_json()
    assert body["violations"] == [
        {"row": 0, "column": "Ciudad", "rule": "unique"},
        {"row": 1, "column": "Ciudad", "rule": "unique"},
    ]


def test_upload_resets_rules(client):
    upload(client)
    set_rules(client, [{"column": "Ciudad", "rule": "not_null"}])
    upload(client, "Nombre,Ciudad\nAna,Madrid\n", "otro.csv")
    body = get_validate(client).get_json()
    assert body["rules"] == []
    assert body["total"] == 0
    assert app_module.schema_rules == []


def test_validation_endpoints_never_touch_the_pipeline(client):
    """SOLO LEE: ni history, ni code_log, ni op_history, ni undo."""
    upload(client)
    client.post(
        "/operation",
        json={"operation": "trim", "params": {"columns": ["Nombre"]}},
    )
    before = {
        "history": len(app_module.history),
        "code_log": len(app_module.code_log),
        "op_history": len(app_module.op_history),
        "lineage": client.get("/lineage").get_json(),
    }
    set_rules(client, [{"column": "Ciudad", "rule": "not_null"}])
    get_validate(client)
    assert len(app_module.history) == before["history"]
    assert len(app_module.code_log) == before["code_log"]
    assert len(app_module.op_history) == before["op_history"]
    assert client.get("/lineage").get_json() == before["lineage"]
    assert client.post("/undo").status_code == 200  # el undo sigue intacto
