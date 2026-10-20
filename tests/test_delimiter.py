"""Tests de auto-detección de delimitador (roadmap delimitador ampliado).

Antes `read_table()` solo probaba `,` y `;` (conteo de bytes) → TSV y pipes
parseaban mal (una sola columna con basura). Ahora: `csv.Sniffer` con lista
blanca `,;\\t|` (respeta las comillas), fallback de consistencia por línea
(≥60% de líneas con el mismo conteo) y conteo total como último recurso
(generaliza la regla histórica conteo(',') vs conteo(';')).

Cubre `_detect_delimiter` puro (unitario) y su uso en `/upload` y
`/upload_right`: columnas correctas con tab/pipe, regresión coma y
punto-y-coma, comillas, columna única → default, y la expresión de código
con `sep='\\t'` escapado en el script exportado.
"""
import io

from app import _detect_delimiter


# ── _detect_delimiter (puro, sin servidor) ─────────────────────────────
def test_detects_comma_and_semicolon():
    assert _detect_delimiter("a,b,c\n1,2,3\n4,5,6\n") == ","
    assert _detect_delimiter("a;b;c\n1;2;3\n4;5;6\n") == ";"


def test_detects_tab_and_pipe():
    assert _detect_delimiter("a\tb\tc\n1\t2\t3\n4\t5\t6\n") == "\t"
    assert _detect_delimiter("a|b|c\n1|2|3\n4|5|6\n") == "|"


def test_quoted_delimiters_do_not_count():
    # Sniffer respeta las comillas: un ';' dentro de "..." no cuenta
    assert _detect_delimiter('Nombre,Nota\nAna,"lo; que sea"\nBob,otra\n') == ","
    # ...ni una coma dentro de comillas en un fichero con punto-y-coma
    assert _detect_delimiter('a;b\n"x,1";y\n"z,2";w\n') == ";"


def test_single_column_defaults_to_comma():
    assert _detect_delimiter("Nombre\nAna\nBob\n") == ","
    assert _detect_delimiter("a,b,c\n") == ","  # una línea: Sniffer no decide
    # Sniffer falla (sin candidatos) y hay <2 líneas no vacías → default
    assert _detect_delimiter("\n\nuna sola linea sin separadores\n") == ","


def test_fallback_consistency_when_sniffer_fails():
    # Sniffer falla en estas filas irregulares (verificado: csv.Error):
    # consistencia por línea 2/3 → ';' (la regla histórica de conteos
    # globales también diría ';' aquí — sin regresión)
    assert _detect_delimiter("a;b;c\nd;e\nf;g;h\n") == ";"
    # tab irregular: el tab sigue siendo el más consistente/constante
    assert _detect_delimiter("a\tb\tc\nx\ty\n1\t2\t3\t4\n") == "\t"


def test_fallback_total_count_last_resort():
    # Sin ningún candidato consistente → máximo conteo total (regla
    # histórica generalizada a 4 candidatos)
    assert _detect_delimiter("a,b,c\nd,e\nf,g,h,i\n") == ","
    assert _detect_delimiter("sin separadores\notra linea\n") == ","


def test_semicolon_file_with_more_commas_than_semicolons():
    # Sniffer gana aquí: ';' es consistente aunque los totales de ',' sean
    # mayores (celdas con comas sin comillas dentro de filas con ';')
    assert _detect_delimiter("a;b;c\n1,2;3,4;5,6\n7,8;9,10;11,12\n") == ";"


# ── /upload: columnas correctas con los 4 separadores ──────────────────
def upload(client, raw, filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(raw), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def op(client, operation, params=None):
    return client.post(
        "/operation", json={"operation": operation, "params": params or {}}
    )


TSV = "Nombre\tCiudad\tEdad\nAna\tSevilla\t30\nLuis\tCórdoba\t25\n"
PIPE = "Region|Producto|Unidades\nNorte|Teclado|12\nSur|Ratón|30\n"


def test_tsv_upload_splits_columns(client):
    body = upload(client, TSV.encode("utf-8")).get_json()
    assert body["data"]["columns"] == ["Nombre", "Ciudad", "Edad"]
    assert body["data"]["data"][0] == ["Ana", "Sevilla", "30"]


def test_pipe_upload_splits_columns(client):
    body = upload(client, PIPE.encode("utf-8")).get_json()
    assert body["data"]["columns"] == ["Region", "Producto", "Unidades"]
    assert body["data"]["data"][1] == ["Sur", "Ratón", "30"]


def test_comma_and_semicolon_still_work(client):
    body = upload(client, b"Nombre,Edad\nAna,30\n").get_json()
    assert body["data"]["columns"] == ["Nombre", "Edad"]
    body = upload(client, b"Nombre;Edad\nAna;30\n").get_json()
    assert body["data"]["columns"] == ["Nombre", "Edad"]


def test_generated_code_escapes_tab_separator(client):
    body = upload(client, TSV.encode("utf-8")).get_json()
    assert "sep='\\t'" in body["code"]
    script = client.post("/export_script", json={"filename": "p"}).data.decode("utf-8")
    assert "sep='\\t'" in script


def test_pipe_separator_in_generated_code(client):
    body = upload(client, PIPE.encode("utf-8")).get_json()
    assert "sep='|'" in body["code"]


def test_upload_right_tsv(client):
    resp = client.post(
        "/upload_right",
        data={"file": (io.BytesIO(TSV.encode("utf-8")), "derecho.tsv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["columns"] == ["Nombre", "Ciudad", "Edad"]


def test_pipeline_works_after_tsv_upload(client):
    upload(client, TSV.encode("utf-8"))
    resp = op(client, "trim", {"column": "Nombre"})
    assert resp.status_code == 200, resp.get_json()


def test_tsv_extension_accepted(client):
    # Extensión .tsv ahora soportada (antes → 400 "Formato no soportado")
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(TSV.encode("utf-8")), "datos.tsv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["columns"] == ["Nombre", "Ciudad", "Edad"]


def test_unsupported_format_message_lists_tsv(client):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"\x00"), "data.bin")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "TSV" in resp.get_json()["error"]
