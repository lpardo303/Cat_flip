"""Lectura de `.xls` (BIFF): el fixture real y la ruta completa.

Contexto del fallo: la app anunciaba `.xls` en el estado vacío, en el
selector, en el dropzone, en `cli.py` y en los mensajes 400, pero pandas 3
ya no trae motor para BIFF: un `.xls` real acababa en un 500 con
`Import python-calamine failed`. Ningún test lo cubría porque los fixtures
se generaban al vuelo en CSV/XLSX.

Aquí:
- el fixture `tests/fixtures/ventas.xls` es un BIFF de verdad, generado una
  vez con LibreOffice (`soffice --convert-to xls`), no bytes falsos;
- se prueba la ruta completa (`read_table`, `/upload`, `/get_sheets` y el
  CLI) con él, y que el motor no traiga deprecaciones.

La coherencia entre lo anunciado y lo soportado (y la matriz de todos los
formatos) vive en `tests/test_formats.py`, que comprueba el HTML renderizado.
"""
import io
import warnings
from pathlib import Path

import pandas as pd

import cli
from app import read_table

RAIZ = Path(__file__).resolve().parent.parent
FIXTURE_XLS = RAIZ / "tests" / "fixtures" / "ventas.xls"

# Contenido de tests/fixtures/ventas.xls (3 filas, acentos y decimales)
ESPERADO = {
    "Nombre": ["Ana López", "Luis Pérez", "Marta Ruiz"],
    "Edad": [30, 41, 25],
    "Ciudad": ["Madrid", "Bogotá", "Lima"],
    "Salario": [2500.5, 3200.0, 1800.75],
}


class _ArchivoConNombre(io.BytesIO):
    """BytesIO con `.filename`, la interfaz mínima que espera read_table."""

    def __init__(self, contenido, filename):
        super().__init__(contenido)
        self.filename = filename


def _comprobar(df):
    assert list(df.columns) == list(ESPERADO)
    assert df["Nombre"].tolist() == ESPERADO["Nombre"]
    assert df["Edad"].tolist() == ESPERADO["Edad"]
    assert df["Salario"].tolist() == ESPERADO["Salario"]


# ── El fixture es lo que dice ser ─────────────────────────────────────
def test_fixture_es_un_biff_de_verdad():
    contenido = FIXTURE_XLS.read_bytes()
    # Firma OLE2 de los .xls (BIFF8): un .xlsx empezaría por "PK".
    assert contenido.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert not contenido.startswith(b"PK")


def test_motor_de_xls_instalado_sin_deprecaciones():
    """pandas 3 deprecó `xlrd`: el motor debe ser calamine y no avisar."""
    from pandas.io.excel._util import get_default_engine

    assert get_default_engine("xls", mode="reader") == "calamine"
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        pd.read_excel(FIXTURE_XLS)
    assert [str(w.message) for w in avisos] == [], "pandas avisó al leer .xls"


# ── Ruta real: read_table, /upload, /get_sheets y CLI ─────────────────
def test_read_table_lee_xls():
    df, expr, encoding = read_table(
        _ArchivoConNombre(FIXTURE_XLS.read_bytes(), "ventas.xls")
    )
    _comprobar(df)
    assert expr.startswith("pd.read_excel('ventas.xls'")
    assert encoding is None


def test_upload_acepta_xls(client):
    contenido = FIXTURE_XLS.read_bytes()
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(contenido), "ventas.xls")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    cuerpo = resp.get_json()
    assert cuerpo["success"] is True
    assert cuerpo["data"]["columns"] == list(ESPERADO)
    assert cuerpo["data"]["total_rows"] == 3
    assert "read_excel('ventas.xls'" in cuerpo["code"]


def test_get_sheets_acepta_xls(client):
    contenido = FIXTURE_XLS.read_bytes()
    resp = client.post(
        "/get_sheets",
        data={"file": (io.BytesIO(contenido), "ventas.xls")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["sheets"] == ["ventas_origen"]


def test_cli_carga_xls():
    df, expr, _ = cli._load_frame(FIXTURE_XLS)
    _comprobar(df)
    assert expr.startswith("pd.read_excel('ventas.xls'")
