"""Tests del formato Parquet en `POST /export`.

Cubre: mágicos `PAR1` al inicio y al final del buffer descargado, round-trip
`pd.read_parquet` contra el df subido (columnas y valores), 400 sin datos,
extensión `.parquet` en el `Content-Disposition`, compatibilidad del formato
desconocido (sigue cayendo a csv) y export tras aplicar una operación.
"""
import io

import pandas as pd

BASE_CSV = (
    "Nombre,Edad,Ciudad,Ventas\n"
    "Alice,30,Madrid,100\n"
    "Bob,25,Barcelona,200\n"
    "Charlie,35,Madrid,150\n"
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


def export_parquet(client, filename="resultado"):
    return client.post("/export", json={"format": "parquet", "filename": filename})


# ── Happy path ─────────────────────────────────────────────────────────
def test_parquet_downloads_with_magic_bytes(client):
    upload(client)
    resp = export_parquet(client)
    assert resp.status_code == 200
    assert resp.content_type == "application/vnd.apache.parquet"
    # PAR1: firma obligatoria de un parquet válido (inicio y fin del archivo)
    assert resp.data[:4] == b"PAR1", "falta el mágico inicial PAR1"
    assert resp.data[-4:] == b"PAR1", "falta el mágico final PAR1"


def test_parquet_roundtrip_matches_uploaded_df(client):
    upload(client)
    resp = export_parquet(client)
    out = pd.read_parquet(io.BytesIO(resp.data))
    expected = pd.read_csv(io.StringIO(BASE_CSV))
    assert list(out.columns) == list(expected.columns)
    pd.testing.assert_frame_equal(out, expected)


def test_parquet_download_name_has_extension(client):
    upload(client)
    resp = export_parquet(client, filename="limpio")
    disp = resp.headers.get("Content-Disposition", "")
    assert ".parquet" in disp, f"extensión ausente en {disp!r}"
    assert "limpio" in disp, f"filename ausente en {disp!r}"


# ── Errores y compatibilidad ───────────────────────────────────────────
def test_parquet_without_data_returns_400(client):
    resp = export_parquet(client)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_unknown_format_falls_back_to_csv(client):
    """El `else` de /export sigue produciendo csv (comportamiento previo)."""
    upload(client)
    resp = client.post("/export", json={"format": "weird", "filename": "x"})
    assert resp.status_code == 200
    assert "csv" in resp.content_type
    assert b"Nombre,Edad,Ciudad,Ventas" in resp.data


# ── Refleja el df transformado ─────────────────────────────────────────
def test_parquet_after_operation_exports_transformed_df(client):
    upload(client)
    op = client.post(
        "/operation", json={"operation": "drop_column", "params": {"column": "Ciudad"}}
    )
    assert op.status_code == 200, op.get_json()
    resp = export_parquet(client)
    assert resp.status_code == 200
    out = pd.read_parquet(io.BytesIO(resp.data))
    assert "Ciudad" not in out.columns
    assert list(out.columns) == ["Nombre", "Edad", "Ventas"]
    assert len(out) == 3
