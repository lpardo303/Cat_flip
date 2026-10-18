"""Auto-mapear tipos: heurística de esquema completo al cargar datasets.

Cubre `operations.detect_type_suggestions` (motor puro) y el campo
`type_suggestions` que `/upload` añade a su respuesta. El motor solo
sugiere: la conversión la dispara el front vía la op `change_type`.

Nota de fixtures: `read_csv` ya tipa como int64/float64/bool las columnas
numéricas o booleanas puras, así que las columnas candidatas a INT/FLOAT
se construyen directamente como object (patrón aprendido en el Bug 4).
"""
import io

import pandas as pd

from operations import detect_type_suggestions


# ── detect_type_suggestions (unitario, sin servidor) ───────────────────

def _df(csv):
    return pd.read_csv(io.StringIO(csv))


def _only(df, dtype=None):
    """Sugerencias del motor, opcionalmente filtradas por dtype."""
    return [s for s in detect_type_suggestions(df)
            if dtype is None or s["suggested_dtype"] == dtype]


# Fechas (regla más específica: se prueba antes que lo numérico)

def test_detects_iso_dates():
    df = _df("Fecha\n2026-01-05\n2026-01-06\n2026-03-07\n")
    sugg = _only(df, "datetime")
    assert len(sugg) == 1
    assert sugg[0] == {
        "column": "Fecha",
        "sample": "2026-01-05",
        "pct": 100,
        "suggested_dtype": "datetime",
    }


def test_detects_iso_dates_with_time():
    df = _df("ts\n2026-01-05 10:30\n2026-01-06 11:00\n")
    assert [s["column"] for s in _only(df, "datetime")] == ["ts"]


def test_detects_day_first_and_dotted_and_text_dates():
    df = _df(
        "slash,dotted,text\n"
        '31/12/2026,01.02.2026,"Jan 5, 2026"\n'
        '01/01/2027,03.03.2026,"Feb 6, 2026"\n'
    )
    cols = [s["column"] for s in _only(df, "datetime")]
    assert cols == ["slash", "dotted", "text"]


def test_detects_iso_dates_with_day_above_twelve():
    # Regresión: dayfirst=True hacía que pandas infiriera "%Y-%d-%m" para
    # columnas ISO y las fechas con día > 12 cayeran a NaT (o se interpretaran
    # volteadas). ISO-dominante ahora parsea con dayfirst=False.
    df = _df("Fecha\n2026-01-13\n2026-01-14\n2026-02-20\n")
    sugg = _only(df, "datetime")
    assert [s["column"] for s in sugg] == ["Fecha"]
    assert sugg[0]["pct"] == 100
    # y la conversión que aplica el usuario no produce NaT ni fechas volteadas
    from operations import OPS
    out, _ = OPS["change_type"](df.copy(), {"column": "Fecha", "dtype": "datetime"})
    assert out["Fecha"].dt.day.tolist() == [13, 14, 20]
    assert not out["Fecha"].isna().any()


def test_skips_text_months_pd_cannot_convert():
    # "5 ene 2026" casa la forma de fecha pero pd.to_datetime NO lo convierte
    # (dateutil solo entiende meses ingleses) → sugerirlo sería traicionar el
    # cambio de tipado con una columna NaT; el motor lo descarta entero
    # (tampoco es numérico, así que no hay sugerencia de ningún tipo).
    df = _df("Col\n5 ene 2026\n6 ene 2026\n")
    assert detect_type_suggestions(df) == []


def test_ignores_ids_names_and_numeric_text():
    df = _df("ID,Nombre,Codigo\nA-100,Alice,X204\nB-101,Bob,X205\n")
    assert detect_type_suggestions(df) == []


def test_ignores_partially_numeric_strings():
    # "10/20" no es fecha ni número aunque contenga barras. Cantidad ya la
    # tipa read_csv como int64 (no es candidata): nada que sugerir.
    df = _df("Ratio,Cantidad\n10/20,100\n20/40,200\n")
    assert detect_type_suggestions(df) == []


def test_ignores_numeric_and_datetime_dtypes():
    df = pd.DataFrame({
        "Entero": [1, 2, 3],
        "Decimal": [1.5, 2.5, 3.5],
        "Flag": [True, False, True],
        "Cuando": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
    })
    assert detect_type_suggestions(df) == []


def test_bool_text_typed_by_pandas_is_not_suggested():
    # read_csv ya convierte TRUE/FALSE a dtype bool → no es columna de texto
    assert detect_type_suggestions(_df("Flag\nTRUE\nFALSE\n")) == []


def test_ignores_column_with_fewer_than_two_values():
    assert _only(pd.DataFrame({"Fecha": ["2026-01-05"]}), "datetime") == []
    assert _only(pd.DataFrame({"Fecha": [None, None]}), "datetime") == []


def test_rejects_majority_non_date_text():
    # 50% casan la forma pero 50% no → por debajo del umbral del 90%
    df = _df("Col\n2026-01-05\n2026-01-06\nnada por aquí\notro texto\n")
    assert detect_type_suggestions(df) == []


def test_nulls_ignored_in_sampling():
    df = _df("Fecha\n2026-01-05\n\n2026-01-06\n\n")
    assert [s["column"] for s in _only(df, "datetime")] == ["Fecha"]


def test_max_cols_caps_suggestions():
    header = "Fecha0,Fecha1,Fecha2\n"
    rows = "".join("2026-01-05,2026-01-06,2026-01-07\n" for _ in range(3))
    df = _df(header + rows)
    assert len(detect_type_suggestions(df, max_cols=2)) == 2
    assert len(detect_type_suggestions(df)) == 3


# Números-texto: INT / FLOAT (columnas object que pandas no pudo tipar)

def test_detects_int_text():
    df = pd.DataFrame({"Cantidad": ["100", "200", "300"]})
    assert _only(df) == [
        {"column": "Cantidad", "sample": "100", "pct": 100,
         "suggested_dtype": "int"}
    ]


def test_detects_float_text():
    df = pd.DataFrame({"Precio": ["19.90", "25.50", "7.25"]})
    assert _only(df) == [
        {"column": "Precio", "sample": "19.90", "pct": 100,
         "suggested_dtype": "float"}
    ]


def test_mixed_integral_and_decimal_is_float():
    df = pd.DataFrame({"Monto": ["1", "2.5", "3"]})
    assert [s["suggested_dtype"] for s in _only(df)] == ["float"]


def test_negative_numbers_are_int():
    df = pd.DataFrame({"Delta": ["-5", "-10", "3"]})
    assert [s["suggested_dtype"] for s in _only(df)] == ["int"]


def test_int_suggestion_ignores_nulls():
    df = pd.DataFrame({"Cantidad": ["100", None, "200"]})
    assert [s["suggested_dtype"] for s in _only(df)] == ["int"]
    assert _only(df)[0]["pct"] == 100


def test_numeric_below_threshold_not_suggested():
    # 25% convertible → muy lejos del 90%
    df = pd.DataFrame({"Mixta": ["100", "abc", "def", "ghi"]})
    assert detect_type_suggestions(df) == []


def test_numeric_at_threshold_with_missing_marker_is_suggested():
    # Caso real: guion de "sin dato" en una columna casi toda numérica
    df = pd.DataFrame({"Cantidad": ["100", "200", "300", "400", "500",
                                    "600", "700", "800", "900", "-"]})
    sugg = detect_type_suggestions(df)
    assert sugg == [
        {"column": "Cantidad", "sample": "100", "pct": 90,
         "suggested_dtype": "int"}
    ]
    # y la conversión que aplicaría el usuario funciona de verdad
    from operations import OPS
    out, code = OPS["change_type"](df.copy(), {"column": "Cantidad", "dtype": "int"})
    assert str(out["Cantidad"].dtype) == "Int64"
    assert out["Cantidad"].iloc[-1] is pd.NA or pd.isna(out["Cantidad"].iloc[-1])
    assert "Int64" in code


def test_datetime_wins_over_numeric_for_date_like_text():
    # Columna fecha textual: la sugerencia es datetime, nunca int/float
    df = pd.DataFrame({"Fecha": ["2026-01-05", "2026-01-06"]})
    assert [s["suggested_dtype"] for s in detect_type_suggestions(df)] == ["datetime"]


# ── /upload: campo type_suggestions ────────────────────────────────────

def _upload(client, csv_text, filename="data.csv"):
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )


def test_upload_returns_type_suggestions(client):
    # Fecha textual (object) + Entero/Decimal con guion de "sin dato" (object):
    # el CSV real es donde read_csv no puede tipar y el motor sí puede.
    csv_text = (
        "Fecha,Cantidad,Precio,Region\n"
        "2026-01-05,100,19.90,Norte\n"
        "2026-01-06,200,25.50,Sur\n"
        "2026-01-07,300,7.25,Norte\n"
        "2026-01-08,400,31.00,Sur\n"
        "2026-01-09,500,12.35,Norte\n"
        "2026-01-10,600,44.10,Sur\n"
        "2026-01-11,700,9.99,Norte\n"
        "2026-01-12,800,15.05,Sur\n"
        "2026-01-13,900,22.80,Norte\n"
        "2026-01-14,-,-,Sur\n"
    )
    resp = _upload(client, csv_text)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["type_suggestions"] == [
        {"column": "Fecha", "sample": "2026-01-05",
         "pct": 100, "suggested_dtype": "datetime"},
        {"column": "Cantidad", "sample": "100",
         "pct": 90, "suggested_dtype": "int"},
        {"column": "Precio", "sample": "19.90",
         "pct": 90, "suggested_dtype": "float"},
    ]
    # El contrato de df_to_json no cambia
    assert body["data"]["dtypes"]["Fecha"] == "STR"


def test_upload_without_suggestions_returns_empty_list(client):
    csv_text = "Nombre,Edad\nAlice,30\nBob,25\n"
    resp = _upload(client, csv_text)
    assert resp.status_code == 200
    assert resp.get_json()["type_suggestions"] == []
