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
- `tests/fixtures/ventas.json` → esquema plano (array de registros) con los
  mismos datos que los demás. `tests/fixtures/anidado.json` → objetos y
  listas dentro de cada registro, para el aplanado.
- `tests/fixtures/hojas.xlsb` → **del corpus de tests de calamine**
  (proyecto MIT, `tests/any_sheets.xlsb`). Ningún conversor local escribe
  XLSB —LibreOffice no exporta el formato y `pyxlsb` solo lee—, así que el
  fixture se versiona tal cual en vez de fabricarlo. Tiene 3 hojas (una
  oculta), texto y números: es el que además ejercita el selector de hoja.
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
    # El motor va explícito: pandas 3 leería .ods con odfpy y .xlsb con
    # pyxlsb, y no empaquetamos ninguna de las dos.
    ".ods": "pd.read_excel('ventas.ods', sheet_name=0, engine='calamine'",
    ".xlsb": "pd.read_excel('hojas.xlsb', sheet_name=0, engine='calamine'",
    ".parquet": "pd.read_parquet('ventas.parquet'",
    ".json": "pd.json_normalize(pd.read_json('ventas.json', orient='records')",
}


# Qué se espera de cada fixture: los cinco formatos que sabemos generar
# llevan los mismos datos; el .xlsb viene de fuera y declara los suyos.
ESPERADOS = {
    ext: {
        "columnas": list(ESPERADO),
        "filas": 3,
        "primera": [ESPERADO[c][0] for c in ESPERADO],
        "hojas": 1,
    }
    for ext in formats.READ_EXTS
}
ESPERADOS[".xlsb"] = {
    # Los encabezados del fixture son números, y calamine los entrega como int
    "columnas": [1, 2],
    "filas": 4,
    "primera": [3, 4.0],
    "hojas": 3,
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
    nombre = "hojas.xlsb" if ext == ".xlsb" else f"ventas{ext}"
    fixture = FIXTURES / nombre
    assert fixture.is_file(), f"falta el fixture {nombre}"
    return fixture.name, fixture.read_bytes()


def _comprobar(df, ext):
    esperado = ESPERADOS[ext]
    assert list(df.columns) == esperado["columnas"]
    assert len(df) == esperado["filas"]
    assert df.iloc[0].tolist() == esperado["primera"]
    if ext != ".xlsb":
        # Los formatos generables comparten datos: se comparan celda a celda
        for columna, valores in ESPERADO.items():
            assert df[columna].tolist() == valores, columna


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
    # La conjunción final va con «o»: «… Parquet o JSON»
    ultimo = formats.LABELS[formats.READ_EXTS[-1]]
    assert formats.read_plain().endswith(f" o {ultimo}")
    assert "<strong>CSV</strong>" in formats.read_html()


# ── Cada formato anunciado se lee de verdad ───────────────────────────
@pytest.mark.parametrize("ext", formats.READ_EXTS)
def test_read_table_lee_cada_formato(ext):
    nombre, contenido = _contenido(ext)
    df, expr, encoding = read_table(_ArchivoConNombre(contenido, nombre))
    _comprobar(df, ext)
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
    assert cuerpo["data"]["columns"] == ESPERADOS[ext]["columnas"]
    assert cuerpo["data"]["total_rows"] == ESPERADOS[ext]["filas"]


@pytest.mark.parametrize("ext", formats.READ_EXTS)
def test_el_codigo_generado_reproduce_la_carga(ext, tmp_path, monkeypatch):
    """El script exportado debe volver a dar el mismo df, sin dependencias extra."""
    nombre, contenido = _contenido(ext)
    _, expr, _ = read_table(_ArchivoConNombre(contenido, nombre))
    (tmp_path / nombre).write_bytes(contenido)
    monkeypatch.chdir(tmp_path)  # la expresión usa el nombre relativo
    # Todos los formatos con motor lo fijan en el código generado, así que
    # aquí no debe aparecer el aviso de pandas sobre el default de .xlsx.
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        reconstruido = eval(expr, {"pd": pd})  # noqa: S307 — expresión propia
    assert [str(w.message) for w in avisos] == []
    _comprobar(reconstruido, ext)


@pytest.mark.parametrize("ext", formats.EXCEL_EXTS)
def test_get_sheets_devuelve_las_hojas_de_los_formatos_con_hojas(ext, client):
    nombre, contenido = _contenido(ext)
    resp = client.post(
        "/get_sheets",
        data={"file": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    hojas = resp.get_json()["sheets"]
    assert len(hojas) == ESPERADOS[ext]["hojas"]
    if ext == ".xlsb":
        # Las hojas ocultas también se listan (el usuario puede elegirlas)
        assert hojas == ["Visible", "Hidden", "VeryHidden"]


@pytest.mark.parametrize("ext", (".parquet", ".csv", ".tsv", ".json"))
def test_get_sheets_no_falla_en_formatos_sin_hojas(ext, client):
    nombre, contenido = _contenido(ext)
    resp = client.post(
        "/get_sheets",
        data={"file": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.get_json()["sheets"] == []


@pytest.mark.parametrize("ext", (".ods", ".xlsb", ".parquet", ".json"))
def test_cli_carga_los_formatos_con_motor_explicito(ext):
    """El CLI comparte read_table, así que cubre los tres motores nuevos."""
    nombre = "hojas.xlsb" if ext == ".xlsb" else f"ventas{ext}"
    df, expr, _ = cli._load_frame(FIXTURES / nombre)
    _comprobar(df, ext)
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


# ── JSON: orientaciones, esquemas anidados y errores ──────────────────
def _subir(client, nombre, contenido):
    if isinstance(contenido, str):
        contenido = contenido.encode("utf-8")
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data",
    )


@pytest.mark.parametrize(
    "nombre,texto,columnas,orient",
    [
        # Array de objetos: la forma habitual
        ("registros.json", '[{"a":1,"b":"x"},{"a":2,"b":"y"}]', ["a", "b"], "records"),
        # {"columna": [valores]}
        ("columnas.json", '{"a":[1,2],"b":["x","y"]}', ["a", "b"], "columns"),
        # {"fila": {...}}: con orient="records" pandas lo leía transpuesto
        ("indice.json", '{"f1":{"a":1,"b":"x"},"f2":{"a":2,"b":"y"}}', ["a", "b"], "index"),
        # Array de filas, sin nombres de columna
        ("valores.json", '[[1,"x"],[2,"y"]]', [0, 1], "values"),
        # NDJSON: un objeto por línea (lo que exportan logs y muchas APIs)
        ("lineas.json", '{"a":1,"b":"x"}\n{"a":2,"b":"y"}', ["a", "b"], "records"),
    ],
)
def test_json_detecta_la_orientacion(nombre, texto, columnas, orient, client):
    resp = _subir(client, nombre, texto)
    assert resp.status_code == 200, resp.get_json()
    cuerpo = resp.get_json()
    assert cuerpo["data"]["columns"] == columnas
    assert cuerpo["data"]["total_rows"] == 2
    # La orientación va explícita también en el código generado
    assert f"orient={orient!r}" in cuerpo["code"], cuerpo["code"]
    assert ("lines=True" in cuerpo["code"]) is (nombre == "lineas.json")


def test_json_anidado_se_aplana_sin_duplicar_filas():
    """Objetos → columnas con punto; las listas quedan como celda, intactas."""
    contenido = (FIXTURES / "anidado.json").read_bytes()
    df, _, _ = read_table(_ArchivoConNombre(contenido, "anidado.json"))
    assert list(df.columns) == [
        "Nombre",
        "Etiquetas",
        "Pedidos",
        "Contacto.Ciudad",
        "Contacto.CodigoPostal",
    ]
    # Aplanar no puede multiplicar filas: 2 registros de entrada → 2 filas
    assert len(df) == 2
    assert df.loc[0, "Contacto.Ciudad"] == "Madrid"
    assert list(df.loc[0, "Etiquetas"]) == ["cliente", "vip"]
    assert [p["total"] for p in df.loc[0, "Pedidos"]] == [120.5, 80.0]


def test_upload_de_json_anidado_no_revienta_con_celdas_de_lista(client):
    """Regresión: `pd.isna` sobre una lista devolvía un array y rompía el grid."""
    contenido = (FIXTURES / "anidado.json").read_bytes()
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(contenido), "anidado.json")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    datos = resp.get_json()["data"]
    assert datos["total_rows"] == 2
    assert "Contacto.Ciudad" in datos["columns"]
    fila = dict(zip(datos["columns"], datos["data"][0]))
    # La lista viaja como texto JSON (lo que el grid y las ops de texto esperan)
    assert json.loads(fila["Etiquetas"]) == ["cliente", "vip"]
    assert json.loads(fila["Pedidos"])[0]["total"] == 120.5


def test_codigo_exportado_reproduce_json_anidado(tmp_path, monkeypatch):
    contenido = (FIXTURES / "anidado.json").read_bytes()
    df, expr, _ = read_table(_ArchivoConNombre(contenido, "anidado.json"))
    (tmp_path / "anidado.json").write_bytes(contenido)
    monkeypatch.chdir(tmp_path)
    reconstruido = eval(expr, {"pd": pd})  # noqa: S307 — expresión propia
    assert list(reconstruido.columns) == list(df.columns)
    assert len(reconstruido) == len(df)
    assert reconstruido["Contacto.Ciudad"].tolist() == df["Contacto.Ciudad"].tolist()


@pytest.mark.parametrize(
    "nombre,texto,mensaje",
    [
        ("roto.json", '{"a": 1,', "JSON inválido"),
        ("escalar.json", "42", "la raíz debe ser"),
        # Un único registro sin array: se explica cómo arreglarlo
        ("registro.json", '{"Nombre": "Ana"}', "envuelve el registro en un array"),
        ("vacio.json", "[]", "no contiene registros"),
        ("mixto.json", '[{"a": 1}, 2]', "mezcla objetos y valores"),
    ],
)
def test_json_invalido_explica_el_problema(nombre, texto, mensaje, client):
    resp = _subir(client, nombre, texto)
    assert resp.status_code == 500
    assert mensaje in resp.get_json()["error"], resp.get_json()["error"]


def test_el_batch_acepta_json(client):
    contenido = (FIXTURES / "ventas.json").read_bytes()
    resp = client.post(
        "/batch_preview",
        data={
            "files": [
                (io.BytesIO(contenido), "a.json"),
                (io.BytesIO(contenido), "b.json"),
            ]
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    assert len(resp.get_json()["files"]) == 2


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
    # Y no anuncia formatos que no se leen
    for fuera in ("XLSM", "XML"):
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
