"""Los formatos de entrada, desde una sola fuente (`formats.py`).

Contexto: la lista vivía escrita a mano en nueve sitios (tres `accept=`, dos
validaciones del front, cuatro tuplas del backend y el CLI). Eso ya produjo
dos desincronizaciones reales: TSV se leía en todo el backend pero no
aparecía en el estado vacío, y `.xls` se anunciaba en seis sitios sin poder
leerse. Ahora todo deriva de `formats.py` y estos tests lo vigilan por los
dos lados: **cada extensión anunciada carga de verdad**, y **ningún sitio
vuelve a escribir la lista a mano**.

Fixtures reales, no bytes falsos:
- `tests/fixtures/ventas.xls`  → BIFF8 generado con LibreOffice.
- `tests/fixtures/ventas.ods`  → LibreOffice desde un `.xlsx`, para que los
  tipos numéricos sobrevivan a la conversión (un CSV de entrada los dejaría
  como texto y el test no probaría nada).
- `tests/fixtures/ventas.parquet` → pyarrow desde el mismo DataFrame.
CSV/TSV/XLSX se generan al vuelo: son texto y binarios que pandas reescribe
en cada ejecución, y versionarlos no aportaría nada.
"""
import io
import json
import re
import warnings
from pathlib import Path

import pandas as pd
import pytest

import cli
import formats
from app import read_table

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures"

# Mismo contenido en todos los formatos (acentos y decimales incluidos)
ESPERADO = {
    "Nombre": ["Ana López", "Luis Pérez", "Marta Ruiz"],
    "Edad": [30, 41, 25],
    "Ciudad": ["Madrid", "Bogotá", "Lima"],
    "Salario": [2500.5, 3200.0, 1800.75],
}

# Prefijo esperado de la expresión pandas que se guarda en el código generado
EXPR_ESPERADA = {
    ".csv": "pd.read_csv('ventas.csv'",
    ".tsv": "pd.read_csv('ventas.tsv'",
    ".xlsx": "pd.read_excel('ventas.xlsx'",
    ".xls": "pd.read_excel('ventas.xls'",
    # El motor va explícito: pandas 3 leería .ods con odfpy, que no empaquetamos
    ".ods": "pd.read_excel('ventas.ods', sheet_name=0, engine='calamine'",
    ".parquet": "pd.read_parquet('ventas.parquet'",
}


class _ArchivoConNombre(io.BytesIO):
    """BytesIO con `.filename`, la interfaz mínima que espera read_table."""

    def __init__(self, contenido, filename):
        super().__init__(contenido)
        self.filename = filename


def _contenido(ext):
    """(nombre, bytes) de un archivo válido y con ESPERADO dentro."""
    if ext in formats.TEXT_EXTS:
        sep = "\t" if ext == ".tsv" else ","
        texto = sep.join(ESPERADO) + "\n"
        texto += "".join(
            sep.join(str(ESPERADO[c][i]) for c in ESPERADO) + "\n" for i in range(3)
        )
        return f"ventas{ext}", texto.encode("utf-8")
    if ext == ".xlsx":
        buffer = io.BytesIO()
        pd.DataFrame(ESPERADO).to_excel(buffer, index=False, engine="openpyxl")
        return "ventas.xlsx", buffer.getvalue()
    fixture = FIXTURES / f"ventas{ext}"
    assert fixture.is_file(), f"falta el fixture {fixture.name}"
    return fixture.name, fixture.read_bytes()


def _comprobar(df):
    assert list(df.columns) == list(ESPERADO)
    assert df["Nombre"].tolist() == ESPERADO["Nombre"]
    assert df["Edad"].tolist() == ESPERADO["Edad"]
    assert df["Ciudad"].tolist() == ESPERADO["Ciudad"]
    assert df["Salario"].tolist() == ESPERADO["Salario"]


# ── Una sola fuente de verdad ──────────────────────────────────────────
def test_el_cli_usa_la_misma_lista_que_el_backend():
    assert cli.INPUT_EXTS == formats.READ_EXTS


def test_las_extensiones_de_texto_y_excel_son_subconjuntos():
    assert set(formats.TEXT_EXTS) <= set(formats.READ_EXTS)
    assert set(formats.EXCEL_EXTS) <= set(formats.READ_EXTS)
    assert set(formats.TEXT_EXTS).isdisjoint(formats.EXCEL_EXTS)


def test_los_textos_derivados_nombran_todos_los_formatos():
    assert formats.read_accept() == ",".join(formats.READ_EXTS)
    for texto in (formats.read_plain(), formats.read_html(), formats.read_dots()):
        for etiqueta in formats.LABELS.values():
            assert etiqueta.lower() in texto.lower(), f"{etiqueta} falta en {texto!r}"
    # La conjunción final va con «o»: «… ODS o Parquet»
    assert formats.read_plain().endswith(" o Parquet")
    assert "<strong>CSV</strong>" in formats.read_html()


# ── Cada formato anunciado se lee de verdad ───────────────────────────
@pytest.mark.parametrize("ext", formats.READ_EXTS)
def test_read_table_lee_cada_formato(ext):
    nombre, contenido = _contenido(ext)
    df, expr, encoding = read_table(_ArchivoConNombre(contenido, nombre))
    _comprobar(df)
    assert expr.startswith(EXPR_ESPERADA[ext]), expr
    assert encoding is None


@pytest.mark.parametrize("ext", formats.READ_EXTS)
def test_upload_acepta_cada_formato(ext, client):
    nombre, contenido = _contenido(ext)
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, f"{ext}: {resp.get_json()}"
    cuerpo = resp.get_json()
    assert cuerpo["data"]["columns"] == list(ESPERADO)
    assert cuerpo["data"]["total_rows"] == 3


@pytest.mark.parametrize("ext", formats.READ_EXTS)
def test_el_codigo_generado_reproduce_la_carga(ext, tmp_path, monkeypatch):
    """El script exportado debe volver a dar el mismo df, sin dependencias extra."""
    nombre, contenido = _contenido(ext)
    _, expr, _ = read_table(_ArchivoConNombre(contenido, nombre))
    (tmp_path / nombre).write_bytes(contenido)
    monkeypatch.chdir(tmp_path)  # la expresión usa el nombre relativo
    with warnings.catch_warnings():
        # El código exportado para .xlsx no fija motor (comportamiento
        # histórico) y pandas avisa de que el default cambiará: decisión
        # aparte, fuera de este cambio.
        warnings.filterwarnings("ignore", message=".*default engine.*")
        reconstruido = eval(expr, {"pd": pd})  # noqa: S307 — expresión propia
    _comprobar(reconstruido)


@pytest.mark.parametrize("ext", formats.EXCEL_EXTS)
def test_get_sheets_devuelve_las_hojas_de_los_formatos_con_hojas(ext, client):
    nombre, contenido = _contenido(ext)
    resp = client.post(
        "/get_sheets",
        data={"file": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    assert len(resp.get_json()["sheets"]) == 1


@pytest.mark.parametrize("ext", (".parquet", ".csv", ".tsv"))
def test_get_sheets_no_falla_en_formatos_sin_hojas(ext, client):
    nombre, contenido = _contenido(ext)
    resp = client.post(
        "/get_sheets",
        data={"file": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.get_json()["sheets"] == []


def test_cli_carga_ods_y_parquet():
    for ext in (".ods", ".parquet"):
        df, expr, _ = cli._load_frame(FIXTURES / f"ventas{ext}")
        _comprobar(df)
        assert expr.startswith(EXPR_ESPERADA[ext])


def test_un_formato_no_soportado_se_rechaza_nombrando_todos_los_formatos(client):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"a,b\n1,2\n"), "datos.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == (
        f"Formato no soportado. Usa {formats.read_plain()}."
    )


def test_el_cruce_rechaza_los_formatos_no_soportados(client):
    resp = client.post(
        "/upload_right",
        data={"file": (io.BytesIO(b"a,b\n1,2\n"), "datos.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "Parquet" in resp.get_json()["error"]


def test_el_batch_usa_los_mismos_formatos(client):
    """La consolidación no tiene lista propia: lee con read_table."""
    _, contenido = _contenido(".ods")
    resp = client.post(
        "/batch_preview",
        data={
            "files": [
                (io.BytesIO(contenido), "a.ods"),
                (io.BytesIO(contenido), "b.ods"),
            ]
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    assert len(resp.get_json()["files"]) == 2


def test_el_batch_rechaza_un_formato_no_soportado(client):
    _, contenido = _contenido(".csv")
    resp = client.post(
        "/batch_preview",
        data={
            "files": [
                (io.BytesIO(contenido), "a.csv"),
                (io.BytesIO(b"a,b\n1,2\n"), "b.txt"),
            ]
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "Parquet" in resp.get_json()["error"]


# ── Anti-deriva: el front dice lo mismo que el backend ────────────────
def _html_renderizado(client):
    """La plantilla tal cual la ve el navegador (con el contexto Jinja)."""
    resp = client.get("/")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


@pytest.mark.parametrize(
    "id_input", ("file-input", "batch-file-input", "bm-template-file")
)
def test_los_inputs_file_ofrecen_exactamente_los_formatos_del_backend(id_input, client):
    html = _html_renderizado(client)
    match = re.search(rf'id="{id_input}"[^>]*accept="([^"]+)"', html)
    assert match, f"no se encontró el accept de #{id_input}"
    assert match.group(1) == formats.read_accept()


def test_el_estado_vacio_nombra_todos_los_formatos_y_solo_esos(client):
    html = _html_renderizado(client)
    vacio = re.search(r"<h2>Cat_flip Studio ETL</h2>\s*<p>(.*?)</p>", html, re.S)
    assert vacio, "no se encontró el texto del estado vacío"
    texto = re.sub(r"<[^>]+>", "", vacio.group(1))
    assert formats.read_plain() in texto, texto
    # Y no anuncia formatos que no se leen: XLSB/JSON siguen fuera de alcance
    for fuera in ("XLSB", "JSON", "ODS2"):
        assert fuera not in texto


def test_los_hints_de_los_dropzones_salen_de_formats(client):
    html = _html_renderizado(client)
    hints = re.findall(r'class="ds-dropzone-hint">(.*?)</span>', html, re.S)
    hints += re.findall(r'font-size:0\.68rem">(.*?)</p>', html, re.S)
    assert len(hints) == 2, f"se esperaban 2 hints de dropzone, hay {len(hints)}"
    for hint in hints:
        assert formats.read_dots() in hint, hint


def test_el_front_recibe_la_lista_del_backend(client):
    html = _html_renderizado(client)
    match = re.search(r"window\.CATFLIP_FORMATS = (\{.*?\});</script>", html, re.S)
    assert match, "no se inyectó window.CATFLIP_FORMATS"
    assert json.loads(match.group(1)) == formats.read_js()


@pytest.mark.parametrize("modulo", ("api.js", "modals.js"))
def test_los_modulos_js_no_repiten_la_lista(modulo):
    fuente = (RAIZ / "static" / "js" / modulo).read_text(encoding="utf-8")
    assert "CATFLIP_FORMATS" in fuente, f"{modulo} no consumes la lista del backend"
    # `.catrecipe`/`.catflip.json` son recetas, no datasets: no cuentan.
    escritas_a_mano = [
        ext
        for ext in re.findall(r"endsWith\('\.(\w+)'\)", fuente)
        if ext != "catrecipe"
    ]
    if modulo == "modals.js":
        # Única excepción deliberada: «Receta desde CSV» solo tiene sentido
        # para texto delimitado (ahí el separador se adivina).
        assert escritas_a_mano == ["csv", "tsv"], escritas_a_mano
    else:
        assert escritas_a_mano == [], escritas_a_mano
