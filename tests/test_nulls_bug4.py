"""Bug 4 — nulos reales: normalización en ops de texto + etiqueta en el grid.

Problema original: `astype(str)` de las ops de texto convertía el NaN real
en el string "nan" y dejaba cadenas vacías ("" / "   "), de modo que
`drop_nulls` no eliminaba filas y el usuario no veía los nulos.

Contrato nuevo:
* Backend: trim, clean_newlines, change_case, replace, split_column,
  split_to_rows y change_type(str) devuelven strings vacíos/solo espacios y
  variantes 'nan'/'none'/'null' como NaN real.
* `df_to_json` envía JSON null en esas celdas (antes `fillna("")`).
* El código generado incluye la línea de normalización con `float('nan')`
  (el script exportado solo importa pandas).
"""
import io

import numpy as np
import pandas as pd

import app as app_module
from operations import OPS


def _df(csv):
    return pd.read_csv(io.StringIO(csv))


def _upload(client, csv_text, filename="data.csv"):
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )


def _post_op(client, op, params):
    return client.post("/operation", json={"operation": op, "params": params})


# ── Backend: las ops de texto no destruyen los nulos ────────────────────

def test_trim_keeps_real_nulls():
    df = pd.DataFrame({"Nombre": ["Alice", " ", np.nan]})
    out, code = OPS["trim"](df, {"columns": ["Nombre"]})
    assert out["Nombre"].isna().sum() == 2
    assert "float('nan')" in code
    # La fila con datos legítimos sobrevive intacta
    assert out["Nombre"].iloc[0] == "Alice"


def test_clean_newlines_keeps_real_nulls():
    df = pd.DataFrame({"Nota": ["hola", "", np.nan]})
    out, code = OPS["clean_newlines"](df, {"columns": ["Nota"]})
    assert out["Nota"].isna().sum() == 2
    assert "float('nan')" in code


def test_change_case_keeps_real_nulls():
    df = pd.DataFrame({"Nombre": ["Alice", np.nan]})
    out, code = OPS["change_case"](df, {"column": "Nombre", "case": "upper"})
    assert out["Nombre"].isna().sum() == 1
    assert out["Nombre"].iloc[0] == "ALICE"


def test_replace_keeps_real_nulls():
    df = pd.DataFrame({"Ciudad": ["Madrid", np.nan]})
    out, _ = OPS["replace"](df, {"column": "Ciudad", "old_value": "Madrid", "new_value": "MD"})
    assert out["Ciudad"].isna().sum() == 1
    assert out["Ciudad"].iloc[0] == "MD"


def test_change_type_str_keeps_real_nulls():
    # Regresión exacta del bug: astype(str) convertía NaN → "nan"
    df = pd.DataFrame({"Valor": [1, 2, np.nan]})
    out, code = OPS["change_type"](df, {"column": "Valor", "dtype": "str"})
    assert out["Valor"].isna().sum() == 1
    assert "nan" not in out["Valor"].dropna().tolist()
    assert "float('nan')" in code


def test_split_to_rows_keeps_real_nulls():
    df = pd.DataFrame({"Etiquetas": ["a,b", np.nan]})
    out, _ = OPS["split_to_rows"](df, {"column": "Etiquetas", "delimiter": ",", "strip": True})
    assert out["Etiquetas"].isna().sum() == 1


def test_split_column_keeps_real_nulls_in_fragments():
    df = _df("Par\nA-\n")
    out, code = OPS["split_column"](df, {"column": "Par", "delimiter": "-", "col_prefix": "p"})
    # El segundo fragmento queda vacío → nulo real, no string ""
    assert out["p_2"].isna().sum() == 1
    assert "float('nan')" in code


def test_legit_strings_survive_normalization():
    # Un string que NO es variante de nulo debe sobrevivir aunque parezca raro
    df = _df("Texto\nnanido\nnúmero\n")
    out, _ = OPS["trim"](df, {"columns": ["Texto"]})
    assert out["Texto"].isna().sum() == 0
    assert list(out["Texto"]) == ["nanido", "número"]


def test_null_variants_are_normalized():
    df = pd.DataFrame({"T": ["none", "NULL", " nan ", "ok"]})
    out, _ = OPS["trim"](df, {"columns": ["T"]})
    assert out["T"].isna().sum() == 3
    assert out["T"].iloc[3] == "ok"


# ── Flujo end-to-end: trim + drop_nulls ahora sí elimina filas ───────────

def test_drop_nulls_after_trim_removes_rows(client):
    csv_text = "Nombre,Ciudad\nAlice,Madrid\n ,Barcelona\nBob, \n"
    assert _upload(client, csv_text).status_code == 200
    assert _post_op(client, "trim", {}).status_code == 200
    resp = _post_op(client, "drop_nulls", {"columns": ["Nombre", "Ciudad"], "how": "any"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["shape"][0] == 1
    assert data["data"] == [["Alice", "Madrid"]]


# ── df_to_json: JSON null en celdas nulas ───────────────────────────────

def test_df_to_json_sends_null_for_missing_cells():
    # Edad es float porque lleva un NaN → str(25.0) == '25.0' (contrato existente)
    df = _df("Nombre,Edad\nAlice,\n,25\n")
    payload = app_module.df_to_json(df)
    assert payload["data"] == [["Alice", None], [None, "25.0"]]
    # Los strings vacíos legítios (post-normalización ya no existirían, pero
    # un string no nulo cualquiera conserva su representación textual)
    df2 = pd.DataFrame({"T": ["x", np.nan]})
    assert app_module.df_to_json(df2)["data"] == [["x"], [None]]


def test_upload_sends_null_cells(client):
    # El CSV lleva una fila con el campo Nombre vacío → NaN real
    csv_text = "Nombre,Edad\nAlice,30\n,25\n"
    body = _upload(client, csv_text).get_json()
    assert body["data"]["data"] == [["Alice", "30"], [None, "25"]]
    assert body["data"]["nulls"]["Nombre"] == 1


def test_operation_response_sends_null_cells(client):
    csv_text = "Nombre\nAlice\nBob\n"
    _upload(client, csv_text)
    _post_op(client, "change_type", {"column": "Nombre", "dtype": "str"})
    body = _post_op(client, "replace", {"column": "Nombre", "old_value": "Bob", "new_value": ""}).get_json()
    # "Bob" → "" → nulo real → JSON null
    assert body["data"]["data"] == [["Alice"], [None]]


# ── Carga: Bug 4 también al cargar (QA visual 2026-10-26) ──────────────
# Antes de este fix `_normalize_nulls` solo corría dentro de las ops de
# texto: una celda de solo espacios ("   ") sobrevivía al /upload, contaba
# como dato válido y la barra de calidad salía inflada (~1 punto en el
# dataset del QA).

def test_upload_solo_espacios_cuenta_como_nulo(client):
    r = _upload(client, "a,b\n1,   \n2,x\n")

    assert r.status_code == 200
    assert app_module.current_df["b"].isna().sum() == 1
    assert r.get_json()["data"]["nulls"]["b"] == 1
    assert client.get("/stats").get_json()["stats"]["b"]["nulls"] == 1


def test_upload_codigo_de_carga_reproduce_el_df(client, monkeypatch):
    """Paridad: ejecutar el código de carga devuelve el MISMO df en memoria.

    El script exportado (receta/`.py`) arranca por esa línea, así que si
    aquí no cuadra, el usuario que ejecute el guion vería otros nulos.
    """
    csv_text = "a,b\n1,   \n2,nan\n3,None\n4,x\n"
    r = _upload(client, csv_text, filename="espacios.csv")
    code = r.get_json()["code"]

    assert "float('nan')" in code  # la normalización viaja en el código

    real_read_csv = pd.read_csv

    def _from_memory(*args, **kwargs):
        # El código llama a pd.read_csv('espacios.csv', ...): se redirige al
        # CSV en memoria para no depender de un fichero en disco.
        kwargs.pop("encoding", None)
        return real_read_csv(io.StringIO(csv_text), **kwargs)

    monkeypatch.setattr(pd, "read_csv", _from_memory)
    ns = {}
    exec(code, ns)
    pd.testing.assert_frame_equal(ns["df"], app_module.current_df)


def test_upload_right_normaliza_solo_espacios(client):
    # 2 columnas a propósito: en un CSV de una sola columna pandas se come
    # la línea de solo espacios como línea en blanco (skip_blank_lines) y la
    # celda ni llegaría al df — el caso real es una celda dentro de una fila
    # con datos, como en el dataset del QA.
    r = client.post(
        "/upload_right",
        data={"file": (io.BytesIO(b"id,col\n1,   \n2,ok\n"), "der.csv")},
        content_type="multipart/form-data",
    )

    assert r.status_code == 200
    assert app_module.right_df["col"].isna().sum() == 1
    assert "float('nan')" in app_module.right_code
