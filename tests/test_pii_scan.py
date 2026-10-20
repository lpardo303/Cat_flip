"""Tests del escaneo automático de PII al cargar (roadmap "Detección PII").

Cubre el motor puro `detect_pii_columns` (unitario, sin servidor) y el
campo `pii_suggestions` que `/upload` añade a su respuesta. Reglas
verificadas: ≥90% de matches en el sample de texto, nulos fuera del
denominador (Bug 4), números de teléfono no confunden con fechas,
solo columnas STR/object, ≥2 valores no nulos, tope `max_cols`, y
round-trip sugerencia → `regex_mask` mask con undo.
"""
import io

import pandas as pd

from operations import detect_pii_columns

EMAILS = (
    "ana@catflip.dev\nluis@catflip.dev\nmaria@catflip.dev\n"
    "carlos@catflip.dev\nlucia@catflip.dev\njorge@catflip.dev\n"
)

BASE_CSV = "Nombre,Valor\nAlice,1\nBob,2\n"


# ── helpers ────────────────────────────────────────────────────────────
def _df(csv_text):
    return pd.read_csv(io.StringIO(csv_text))


def upload(client, csv_text=BASE_CSV, filename="data.csv"):
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


# ── motor puro: detect_pii_columns ────────────────────────────────────
def test_detects_email_column():
    df = _df("Contacto\n" + EMAILS)
    findings = detect_pii_columns(df)
    assert findings == [
        {"column": "Contacto", "kind": "email", "pct": 100,
         "sample": "ana@catflip.dev"}
    ]


def test_detects_phone_column():
    df = _df(
        "Telefono\n+34 612 345 678\n+34 612 345 679\n+34 612 345 680\n"
        "+34 612 345 681\n+34 612 345 682\n+34 612 345 683\n"
    )
    assert [f["kind"] for f in detect_pii_columns(df)] == ["phone"]


def test_detects_id_and_card_column():
    # `id` cubre SN-001 (prefijo alfanumérico) y tarjetas de 13–19 dígitos
    df = _df("Codigo\nSN-001\nSN-002\nSN-003\nSN-004\nSN-005\nSN-006\n")
    assert [f["kind"] for f in detect_pii_columns(df)] == ["id"]
    # Tarjeta como texto (una columna numérica se descarta a propósito:
    # igual que los detectores de tipo, nunca se sugiere sobre dtype no-texto)
    df_card = pd.DataFrame({
        "Tarjeta": [f"411111111111{i}" for i in range(1, 7)]
    })
    assert [f["kind"] for f in detect_pii_columns(df_card)] == ["id"]


def test_below_threshold_is_not_suggested():
    # 2 de 6 emails = 33% < 90% → nada
    df = _df(
        "Contacto\nana@catflip.dev\nluis@catflip.dev\nsoporte interno\n"
        "nota vieja\nsin datos\nrevisar\n"
    )
    assert detect_pii_columns(df) == []


def test_dates_do_not_false_positive_as_phone():
    # 31/12/2026 y 2026-10-01 casan la forma de teléfono (dígitos + guiones)
    df = _df(
        "Fecha\n31/12/2026\n01/01/2027\n15/03/2026\n2026-10-01\n"
        "2026-10-02\n2026-10-03\n"
    )
    assert detect_pii_columns(df) == []


def test_nulls_are_not_pii():
    # Nulos reales no cuentan en el denominador (regla Bug 4): la columna
    # tiene 3 nulos y 3 emails → 100% de los no nulos casan.
    df = _df("Contacto\nana@catflip.dev\n\nluis@catflip.dev\n\nmaria@catflip.dev\n\n")
    df["Contacto"] = df["Contacto"].astype("string")
    findings = detect_pii_columns(df)
    assert len(findings) == 1
    assert findings[0]["pct"] == 100
    # Columna solo-nulos → sin valores suficientes
    assert detect_pii_columns(pd.DataFrame({"Vacio": [None] * 4})) == []


def test_single_value_column_is_skipped():
    df = _df("Contacto\nana@catflip.dev\n\n\n\n\n")
    assert detect_pii_columns(df) == []


def test_only_string_columns_are_scanned():
    df = pd.DataFrame({
        "Importes": [1111111111111.0, 2222222222222.0, 3333333333333.0,
                     4444444444444.0, 5555555555555.0, 6666666666666.0],
        "Flag": [True, False, True, False, True, False],
        "Fecha": pd.to_datetime(["2026-01-01"] * 6),
    })
    assert detect_pii_columns(df) == []


def test_max_cols_caps_the_findings():
    emails = EMAILS.strip().split("\n")
    csv_text = "Contacto0,Contacto1,Contacto2\n" + "\n".join(
        ",".join([e] * 3) for e in emails
    )
    assert len(detect_pii_columns(_df(csv_text), max_cols=2)) == 2


def test_column_order_is_dataset_order():
    df = _df("A,B\nSN-001,ana@catflip.dev\nSN-002,luis@catflip.dev\n"
             "SN-003,maria@catflip.dev\nSN-004,carlos@catflip.dev\n"
             "SN-005,lucia@catflip.dev\nSN-006,jorge@catflip.dev\n")
    assert [f["column"] for f in detect_pii_columns(df)] == ["A", "B"]


# ── /upload: campo pii_suggestions ────────────────────────────────────
def test_upload_returns_pii_suggestions(client):
    resp = upload(client, "Contacto,Notas\n" + EMAILS)
    body = resp.get_json()
    assert body["pii_suggestions"] == [
        {"column": "Contacto", "kind": "email", "pct": 100,
         "sample": "ana@catflip.dev"}
    ]
    # el dataset NO se toca: la columna original sigue intacta
    assert body["data"]["columns"] == ["Contacto", "Notas"]


def test_upload_without_pii_returns_empty(client):
    assert upload(client).get_json()["pii_suggestions"] == []


# ── round-trip: sugerencia → regex_mask → undo ────────────────────────
def test_suggestion_masks_with_regex_mask_and_undo_restores(client):
    upload(client, "Contacto,Notas\n" + EMAILS)
    sugg = upload(client, "Contacto,Notas\n" + EMAILS).get_json()["pii_suggestions"][0]

    resp = op(client, "regex_mask",
              {"column": sugg["column"], "pattern": sugg["kind"], "mode": "mask"})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    i = data["columns"].index("Contacto")
    assert data["data"][0][i] == "****"
    assert data["data"][5][i] == "****"

    undo = client.post("/undo")
    assert undo.status_code == 200
    assert undo.get_json()["data"]["data"][0][i] == "ana@catflip.dev"
