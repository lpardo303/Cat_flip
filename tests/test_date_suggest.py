"""Detección inteligente de fechas con auto-tipado al cargar datasets.

Cubre `operations.detect_date_columns` (detector puro) y el campo
`date_suggestions` que `/upload` añade a su respuesta. El detector solo
sugiere: la conversión la dispara el front vía la op `change_type`.
"""
import io

import pandas as pd

from operations import detect_date_columns


# ── detect_date_columns (unitario, sin servidor) ─────────────────────────

def _df(csv):
    return pd.read_csv(io.StringIO(csv))


def test_detects_iso_dates():
    df = _df("Fecha\n2026-01-05\n2026-01-06\n2026-03-07\n")
    sugg = detect_date_columns(df)
    assert len(sugg) == 1
    assert sugg[0] == {
        "column": "Fecha",
        "sample": "2026-01-05",
        "pct": 100,
        "suggested_dtype": "datetime",
    }


def test_detects_iso_dates_with_time():
    df = _df("ts\n2026-01-05 10:30\n2026-01-06 11:00\n")
    assert [s["column"] for s in detect_date_columns(df)] == ["ts"]


def test_detects_day_first_and_dotted_and_text_dates():
    df = _df(
        "slash,dotted,text\n"
        '31/12/2026,01.02.2026,"Jan 5, 2026"\n'
        '01/01/2027,03.03.2026,"Feb 6, 2026"\n'
    )
    cols = [s["column"] for s in detect_date_columns(df)]
    assert cols == ["slash", "dotted", "text"]


def test_skips_text_months_pd_cannot_convert():
    # "5 ene 2026" casa la forma de fecha pero pd.to_datetime NO lo convierte
    # (dateutil solo entiende meses ingleses) → sugerirlo sería traicionar el
    # cambio de tipado con una columna NaT; el detector lo descarta.
    df = _df("Col\n5 ene 2026\n6 ene 2026\n")
    assert detect_date_columns(df) == []


def test_ignores_ids_names_and_numeric_text():
    df = _df("ID,Nombre,Codigo\nA-100,Alice,X204\nB-101,Bob,X205\n")
    assert detect_date_columns(df) == []


def test_ignores_partially_numeric_strings():
    # "10/20" no es fecha aunque contenga barras; "100" es número-texto
    df = _df("Ratio,Cantidad\n10/20,100\n20/40,200\n")
    assert detect_date_columns(df) == []


def test_ignores_numeric_and_datetime_dtypes():
    df = pd.DataFrame({
        "Entero": [1, 2, 3],
        "Decimal": [1.5, 2.5, 3.5],
        "Cuando": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
    })
    assert detect_date_columns(df) == []


def test_ignores_column_with_fewer_than_two_values():
    assert detect_date_columns(pd.DataFrame({"Fecha": ["2026-01-05"]})) == []
    assert detect_date_columns(pd.DataFrame({"Fecha": [None, None]})) == []


def test_rejects_majority_non_date_text():
    # 50% casan la forma pero 50% no → por debajo del umbral del 90%
    df = _df("Col\n2026-01-05\n2026-01-06\nnada por aquí\notro texto\n")
    assert detect_date_columns(df) == []


def test_nulls_ignored_in_sampling():
    df = _df("Fecha\n2026-01-05\n\n2026-01-06\n\n")
    assert [s["column"] for s in detect_date_columns(df)] == ["Fecha"]


def test_max_cols_caps_suggestions():
    header = "Fecha0,Fecha1,Fecha2\n"
    rows = "".join("2026-01-05,2026-01-06,2026-01-07\n" for _ in range(3))
    df = _df(header + rows)
    assert len(detect_date_columns(df, max_cols=2)) == 2
    assert len(detect_date_columns(df)) == 3


# ── /upload: campo date_suggestions ──────────────────────────────────────

def _upload(client, csv_text, filename="data.csv"):
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )


def test_upload_returns_date_suggestions(client):
    csv_text = "Fecha,Ventas\n2026-01-05,100\n2026-01-06,200\n"
    resp = _upload(client, csv_text)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["date_suggestions"] == [
        {"column": "Fecha", "sample": "2026-01-05",
         "pct": 100, "suggested_dtype": "datetime"}
    ]
    # El contrato de df_to_json no cambia
    assert body["data"]["dtypes"]["Fecha"] == "STR"


def test_upload_without_dates_returns_empty_list(client):
    csv_text = "Nombre,Edad\nAlice,30\nBob,25\n"
    resp = _upload(client, csv_text)
    assert resp.status_code == 200
    assert resp.get_json()["date_suggestions"] == []