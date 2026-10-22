"""Tests de los formatos de exportación JSON Records y SQL (F3.4 ampliación).

`POST /export` gana dos ramas: `json` (array de objetos, round-trip con
`pd.read_json(orient='records')`) y `sql` (script DDL + INSERT portable
entre Postgres y SQLite). Las propiedades que hay que defender:

1. **Fidelidad de tipos**: nulos → `null`/`NULL`, booleanos, fechas ISO y
   dtype SQL derivado del dtype real de pandas.
2. **Escapado**: comillas simples en strings (`O'Connor` → `'O''Connor'`)
   e identificados de tabla/columna sanitizados.
3. **Ejecutabilidad**: el script corre tal cual en SQLite en memoria.
4. **Cero mutación**: exportar jamás toca el pipeline.
"""
import io
import json as jsonlib
import sqlite3

import pandas as pd
import pytest

import app as app_module


BASE_CSV = (
    "Nombre,Edad,Salario,Activo,Fecha\n"
    "  Ana ,30,2500.5,True,2026-01-05\n"
    "Luis ,25,1800.0,False,2026-02-10\n"
    "O'Connor,35,,True,2026-03-15\n"
    "Carla,30,3100.25,False,2026-04-20\n"
)


def upload(client, csv_text=BASE_CSV, filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def export(client, fmt, filename="resultado"):
    return client.post("/export", json={"format": fmt, "filename": filename})


@pytest.fixture()
def loaded(client):
    """Dataset cargado con la columna Fecha ya convertida a datetime."""
    upload(client)
    resp = client.post(
        "/operation",
        json={"operation": "change_type",
              "params": {"column": "Fecha", "dtype": "datetime"}},
    )
    assert resp.status_code == 200, resp.get_json()
    return client


# ── Validación y compatibilidad ────────────────────────────────────────
@pytest.mark.parametrize("fmt", ["json", "sql"])
def test_export_without_data_is_error(client, fmt):
    resp = export(client, fmt)
    assert resp.status_code == 400
    assert "No hay datos" in resp.get_json()["error"]


def test_export_unknown_format_keeps_csv_fallback(client):
    """Compat histórica: formato desconocido sigue cayendo a CSV."""
    upload(client)
    resp = export(client, "formato_fantasma")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert resp.headers["Content-Disposition"].endswith(".csv")


# ── JSON Records ───────────────────────────────────────────────────────
def test_export_json_is_records_array(loaded):
    resp = export(loaded, "json")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    assert resp.headers["Content-Disposition"].endswith(".json")

    rows = jsonlib.loads(resp.get_data(as_text=True))
    assert isinstance(rows, list) and len(rows) == 4
    assert list(rows[0].keys()) == ["Nombre", "Edad", "Salario", "Activo", "Fecha"]
    # Los datos salen tal cual (sin trim): el export refleja el estado actual
    assert rows[0]["Nombre"] == "  Ana "
    assert rows[0]["Edad"] == 30
    assert rows[0]["Activo"] is True
    assert rows[2]["Salario"] is None  # nulo real → null


def test_export_json_roundtrips_with_pandas(loaded):
    """pd.read_json(orient='records') recupera columnas y valores."""
    text = export(loaded, "json").get_data(as_text=True)
    back = pd.read_json(io.StringIO(text), orient="records")
    df = app_module.current_df

    assert list(back.columns) == list(df.columns)
    assert len(back) == len(df)
    assert list(back["Edad"]) == [int(v) for v in df["Edad"]]
    assert int(back["Salario"].isna().sum()) == int(df["Salario"].isna().sum())
    assert list(back["Activo"]) == [bool(v) for v in df["Activo"]]


def test_export_json_dates_are_iso(loaded):
    rows = jsonlib.loads(export(loaded, "json").get_data(as_text=True))
    assert rows[0]["Fecha"].startswith("2026-01-05T")


def test_export_json_keeps_non_ascii(client):
    """force_ascii=False: 'ñ' llega como ñ, sin \\u00f1 ni mojibake."""
    upload(client, csv_text="Nombre\nAna Muñiz\n")
    text = export(client, "json").get_data(as_text=True)
    assert "Muñiz" in text
    assert "\\u00f1" not in text


# ── SQL (DDL + INSERT) ────────────────────────────────────────────────
def test_export_sql_ddl_types_from_dtypes(loaded):
    script = export(loaded, "sql").get_data(as_text=True)

    assert 'CREATE TABLE "resultado" (' in script
    assert '"Nombre" TEXT,' in script
    assert '"Edad" BIGINT,' in script
    assert '"Salario" DOUBLE PRECISION,' in script
    assert '"Activo" BOOLEAN,' in script
    assert '"Fecha" TIMESTAMP' in script  # última columna: sin coma
    assert "Cat_flip" in script.splitlines()[1]  # cabecera con crédito
    assert script.rstrip().endswith(";")


def test_export_sql_escapes_quotes_and_nulls(loaded):
    script = export(loaded, "sql").get_data(as_text=True)
    assert "'O''Connor'" in script          # comilla simple duplicada
    assert "NULL" in script                 # Salario nulo de O'Connor
    assert "TRUE" in script and "FALSE" in script


def test_export_sql_batches_inserts(client):
    """Lotes de 100 filas: 250 filas → 3 statements INSERT."""
    big = "Nombre\n" + "\n".join(f"Fila {i}" for i in range(250))
    upload(client, csv_text=big)
    script = export(client, "sql").get_data(as_text=True)
    assert script.count("INSERT INTO") == 3
    assert script.count("INSERT INTO") == -(-250 // 100)


def test_export_sql_table_name_is_sanitized(client):
    upload(client)
    script = export(client, "sql", filename="Mi Tabla #1!").get_data(as_text=True)
    assert 'CREATE TABLE "mi_tabla_1" (' in script
    assert 'INSERT INTO "mi_tabla_1"' in script
    assert '"Mi Tabla' not in script


def test_export_sql_empty_df_only_creates_table(client):
    upload(client)
    # filter sin coincidencias → 0 filas (mismo dataset, vacío)
    resp = client.post(
        "/operation",
        json={"operation": "filter",
              "params": {"column": "Edad", "operator": "==", "value": "999"}},
    )
    assert resp.status_code == 200, resp.get_json()

    script = export(client, "sql").get_data(as_text=True)
    assert "CREATE TABLE" in script
    assert "INSERT INTO" not in script
    assert "0 fila(s)" in script


def test_export_sql_executes_in_sqlite(loaded):
    """El script corre tal cual en SQLite y los datos vuelven idénticos."""
    script = export(loaded, "sql").get_data(as_text=True)
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(script)
        df = app_module.current_df

        n = con.execute('SELECT COUNT(*) FROM "resultado"').fetchone()[0]
        assert n == len(df)

        # Edad asc → Luis (25): texto, entero, decimal y booleano intactos
        row = con.execute(
            'SELECT "Nombre", "Edad", "Salario", "Activo" FROM "resultado"'
            ' ORDER BY "Edad" LIMIT 1'
        ).fetchone()
        assert row == ("Luis ", 25, 1800.0, 0)

        # La comilla escapada se lee como texto original y su nulo es NULL
        nombre = con.execute(
            'SELECT "Salario" FROM "resultado" WHERE "Nombre" = \'O\'\'Connor\''
        ).fetchone()
        assert nombre == (None,)
    finally:
        con.close()


# ── Cero mutación ──────────────────────────────────────────────────────
@pytest.mark.parametrize("fmt", ["json", "sql"])
def test_export_never_mutates_state(client, fmt):
    upload(client)
    client.post(
        "/operation",
        json={"operation": "trim", "params": {"columns": ["Nombre"]}},
    )
    before = {
        "history": len(app_module.history),
        "op_history": len(app_module.op_history),
        "code_log": len(app_module.code_log),
        "lineage": client.get("/lineage").get_json(),
    }

    assert export(client, fmt).status_code == 200

    assert len(app_module.history) == before["history"]
    assert len(app_module.op_history) == before["op_history"]
    assert len(app_module.code_log) == before["code_log"]
    assert client.get("/lineage").get_json() == before["lineage"]
    assert client.post("/undo").status_code == 200
