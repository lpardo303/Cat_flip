"""Lectura de `.xlsx` con calamine: contrato y ruta completa.

Contexto: se comparó openpyxl contra calamine leyendo los mismos cuadernos
(típico de 5.000×8, fórmulas con valor cacheado, errores de fórmula y un
archivo de casos borde con enteros >2^53, porcentajes, horas, combinadas,
encabezados raros y una hoja de gráfico). Resultado medido: **paridad** en
columnas, dtypes y valores —la única diferencia bruta era una celda de solo
espacios, que `normalize_read_nulls` ya convierte a nulo—, **7× más rápido**
(0,8 s frente a 6,0 s en 50.000×8) y **lee los cuadernos con hoja de gráfico**
que hacen fallar a openpyxl 3.1.5 con `AttributeError: 'list' object has no
attribute 'find'`. Por eso la lectura se unificó en calamine; openpyxl sigue
siendo la dependencia que **escribe** `.xlsx`.

El fixture `tests/fixtures/contrato.xlsx` es un cuaderno real creado con
openpyxl que fija ese contrato: tipos variados, fecha sin hora y con hora en
la misma columna, booleanos, nulos, una celda de solo espacios, texto con
espacios en los extremos, celdas combinadas, hoja oculta y hoja de gráfico.
"""
import io
import warnings
from pathlib import Path

import pandas as pd
import pytest

import cli
import formats
from app import excel_engine, read_table

RAIZ = Path(__file__).resolve().parent.parent
FIXTURE = RAIZ / "tests" / "fixtures" / "contrato.xlsx"


class _ArchivoConNombre(io.BytesIO):
    """BytesIO con `.filename`, la interfaz mínima que espera read_table."""

    def __init__(self, contenido, filename):
        super().__init__(contenido)
        self.filename = filename


def _fixture(hoja=None):
    return read_table(
        _ArchivoConNombre(FIXTURE.read_bytes(), "contrato.xlsx"), sheet=hoja
    )


# ── El motor y el fixture ─────────────────────────────────────────────
@pytest.mark.parametrize("ext", formats.EXCEL_EXTS)
def test_el_motor_de_lectura_es_calamine_para_todos(ext):
    assert excel_engine(f"datos{ext}") == "calamine"


def test_el_fixture_es_un_xlsx_con_hoja_de_grafico():
    contenido = FIXTURE.read_bytes()
    assert contenido.startswith(b"PK")  # ZIP: es un .xlsx, no un .xls
    # calamine lista las hojas de trabajo y descarta la de gráfico
    xl = pd.ExcelFile(io.BytesIO(contenido), engine="calamine")
    assert xl.sheet_names == ["ventas", "combinadas", "Oculta"]


def test_la_lectura_no_emite_avisos_de_pandas():
    """Sin motor fijado, pandas avisa de que el default de .xlsx va a cambiar."""
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        _fixture()
    assert [str(w.message) for w in avisos] == []


# ── Contrato de lectura ───────────────────────────────────────────────
def test_contrato_de_tipos_y_valores():
    df, expr, encoding = _fixture()
    assert expr.startswith("pd.read_excel('contrato.xlsx', sheet_name=0")
    assert "engine='calamine'" in expr  # el script exportado no cambia de motor
    assert encoding is None

    assert list(df.columns) == [
        "Nombre", "Edad", "Salario", "Activo", "Fecha", "Ciudad", "Vacio", "Nota",
    ]
    # Tipos: los mismos que daba openpyxl (verificados en la comparación)
    assert [str(df[c].dtype) for c in df.columns] == [
        "str", "int64", "float64", "bool", "datetime64[us]", "str", "float64", "str",
    ]
    assert df["Nombre"].tolist() == ["Ana López", "Luis Pérez", "Marta Ruiz"]
    assert df["Edad"].tolist() == [30, 41, 25]
    assert df["Salario"].tolist() == [2500.5, 3200.0, 1800.75]
    assert df["Activo"].tolist() == [True, False, True]
    # Fecha sin hora → medianoche; con hora → se conserva
    assert df["Fecha"].tolist() == [
        pd.Timestamp("2024-01-31"),
        pd.Timestamp("2024-02-29 13:45:12"),
        pd.Timestamp("2025-06-01"),
    ]
    assert df["Ciudad"].tolist() == ["Madrid", "Bogotá", "Lima"]
    assert df["Vacio"].isna().tolist() == [False, True, False]
    # Texto con espacios en los extremos se respeta; solo-espacios es nulo
    assert df["Nota"].tolist()[0] == "  con espacios  "
    assert df["Nota"].isna().tolist() == [False, True, True]


def test_las_celdas_combinadas_no_duplican_el_valor():
    df, _, _ = _fixture(hoja="combinadas")
    assert list(df.columns) == ["Grupo", "Importe"]
    assert df["Grupo"].tolist()[:2] == [1, "bloque"]
    assert pd.isna(df["Grupo"].tolist()[2])  # A4 está fusionada con A3
    assert df["Importe"].tolist() == [10, 20, 30]


# ── Ruta completa: /upload y /get_sheets ──────────────────────────────
def test_upload_del_fixture(client):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(FIXTURE.read_bytes()), "contrato.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    cuerpo = resp.get_json()
    assert cuerpo["data"]["dtypes"] == {
        "Nombre": "STR", "Edad": "INT", "Salario": "FLOAT", "Activo": "BOOL",
        "Fecha": "DATE", "Ciudad": "STR", "Vacio": "FLOAT", "Nota": "STR",
    }
    assert cuerpo["data"]["shape"] == [3, 8]
    assert "engine='calamine'" in cuerpo["code"]


def test_get_sheets_no_ofrece_la_hoja_de_grafico(client):
    resp = client.post(
        "/get_sheets",
        data={"file": (io.BytesIO(FIXTURE.read_bytes()), "contrato.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["sheets"] == ["ventas", "combinadas", "Oculta"]


# ── Escritura (openpyxl) y lectura (calamine) deben coincidir ─────────
def test_lo_que_escribe_openpyxl_lo_lee_calamine(tmp_path):
    """El CLI exporta .xlsx con openpyxl: leerlo con calamine debe dar lo mismo."""
    original = pd.DataFrame({
        "Nombre": ["Ana López", "Luis Pérez", " Marta "],
        "Edad": [30, 41, 25],
        "Salario": [2500.5, 3200.0, float("nan")],
        "Activo": [True, False, True],
        # format="mixed": pandas 3 ya no infiere formatos distintos en una lista
        "Fecha": pd.to_datetime(
            ["2024-01-31", "2024-02-29 13:45:12", "2025-06-01"], format="mixed"
        ),
    })
    destino = tmp_path / "ida_y_vuelta.xlsx"
    cli._write_output(original, destino)

    leido, expr, _ = cli._load_frame(destino)
    assert "engine='calamine'" in expr
    pd.testing.assert_frame_equal(leido, original, check_dtype=False)
    for columna in ("Nombre", "Edad", "Activo", "Fecha"):
        assert str(leido[columna].dtype) == str(original[columna].dtype), columna
