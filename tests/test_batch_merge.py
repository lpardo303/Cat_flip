"""Tests del Multi-File Batch Merge: consolidación de N archivos.

Cubre `consolidate_batch` (operations.py) como función pura — unión outer
sin pérdidas, bloque fijo, orden `append`/`alpha` y modo plantilla —, los
endpoints `/batch_preview` (solo lectura, matriz de encabezados y
diferencias contra la plantilla) y `/batch_merge` (reset de estado idéntico
a `/upload`), la paridad del código generado (el `code_log` exportable
reproduce la consolidación completa ejecutando el script con los archivos
reales) y todos los 400/500 con su contrato de mensajes.
"""
import io

import pandas as pd
import pytest

import app as app_module
from operations import consolidate_batch, validate_template_columns

A_CSV = "Fecha,Region,Unidades\n2026-01-01,Norte,5\n2026-01-02,Sur,7\n"
B_CSV = "Fecha,Region,Unidades,Extra\n2026-01-03,Este,2,x\n"
# Tercer archivo sin Unidades y sin Extra: sus filas deben quedar vacías ahí
C_CSV = "Fecha,Region\n2026-01-04,Oeste\n"
TPL_CSV = "Region,Unidades,Fecha,Observaciones\n"


def files(*pairs, template=None, **form):
    data = {"files": [(io.BytesIO(txt.encode("utf-8")), name) for name, txt in pairs]}
    if template is not None:
        data["template"] = (io.BytesIO(template[1].encode("utf-8")), template[0])
    data.update(form)  # campos de formulario (first/rest/mode…)
    return data


def preview(client, *pairs, template=None):
    return client.post(
        "/batch_preview",
        data=files(*pairs, template=template),
        content_type="multipart/form-data",
    )


def merge(client, *pairs, template=None, **form):
    data = files(*pairs, template=template)
    data.update(form)
    return client.post(
        "/batch_merge", data=data, content_type="multipart/form-data"
    )


def df_of(response):
    """DataFrame a partir de la respuesta (df_to_json → filas con nan→None)."""
    payload = response.get_json()["data"]
    rows = [[float("nan") if v is None else v for v in r] for r in payload["data"]]
    return pd.DataFrame(rows, columns=payload["columns"])


# ── Función pura: consolidate_batch ────────────────────────────────────
def test_conserve_extra_columns_and_null_fill():
    """Unión outer: la columna extra de un archivo no se pierde y las que
    faltan en otros quedan vacías en sus filas."""
    dfs = [
        pd.read_csv(io.StringIO(A_CSV)),
        pd.read_csv(io.StringIO(B_CSV)),
        pd.read_csv(io.StringIO(C_CSV)),
    ]
    df, order = consolidate_batch(dfs)
    assert order == ["Fecha", "Region", "Unidades", "Extra"]
    assert list(df.columns) == order
    assert len(df) == 4  # 2 + 1 + 1 filas
    # fila de C: sin Unidades/Extra → nulo
    assert pd.isna(df.iloc[3]["Unidades"]) and pd.isna(df.iloc[3]["Extra"])
    # fila de A: sin Extra → nulo
    assert pd.isna(df.iloc[0]["Extra"])


def test_pinned_block_and_append_rest():
    dfs = [pd.read_csv(io.StringIO(A_CSV)), pd.read_csv(io.StringIO(B_CSV))]
    df, order = consolidate_batch(dfs, first=["Unidades", "Fecha"])
    assert order == ["Unidades", "Fecha", "Region", "Extra"]
    assert list(df["Unidades"]) == [5, 7, 2]  # los valores viajan con su fila


def test_alpha_rest_is_case_insensitive():
    dfs = [
        pd.DataFrame({"Zeta": [1], "alpha": [2], "Beta": [3]}),
        pd.DataFrame({"Zeta": [4], "monto": [5]}),
    ]
    _, order = consolidate_batch(dfs, rest="alpha")
    # casefold: alpha, Beta, monto, Zeta (un sort ASCII daría Beta, Zeta…)
    assert order == ["alpha", "Beta", "monto", "Zeta"]


def test_template_exact_order_drops_and_fills():
    dfs = [
        pd.read_csv(io.StringIO(A_CSV)),
        pd.read_csv(io.StringIO(B_CSV)),
    ]
    tpl = ["Observaciones", "Region", "Fecha"]
    df, order = consolidate_batch(dfs, template_columns=tpl)
    assert order == tpl
    assert list(df.columns) == tpl
    # Unidades/Extra no están en la plantilla → descartadas
    assert "Unidades" not in df.columns and "Extra" not in df.columns
    # Observaciones no existe en ningún archivo → columna toda nula creada
    assert df["Observaciones"].isna().all()


@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        ({"dfs": None}, "al menos 2"),
        ({"dfs": "no-lista"}, "al menos 2"),
        ({"rest": "rotate"}, "Orden del resto"),
        ({"first": ["Fantasma"]}, "bloque fijo inexistente"),
        ({"first": ["Fecha", "Fecha"]}, "No repitas"),
        ({"template_columns": []}, "plantilla"),
        ({"template_columns": ["a", "a"]}, "repite columnas"),
        ({"template_columns": ["a", " "]}, "plantilla"),
        ({"template_columns": ["a"], "first": ["Fecha"]}, "bloque fijo"),
    ],
    ids=[
        "empty", "not_a_list", "bad_rest", "first_missing",
        "first_duplicated", "tpl_empty", "tpl_duplicated", "tpl_blank",
        "tpl_plus_first",
    ],
)
def test_consolidate_batch_errors(kwargs, fragment):
    dfs = [pd.read_csv(io.StringIO(A_CSV)), pd.read_csv(io.StringIO(B_CSV))]
    if "dfs" in kwargs:
        dfs = kwargs.pop("dfs")
    with pytest.raises(ValueError) as exc:
        consolidate_batch(dfs, **kwargs)
    assert fragment in str(exc.value)


def test_validate_template_columns_direct_contract():
    with pytest.raises(ValueError):
        validate_template_columns(None)
    with pytest.raises(ValueError):
        validate_template_columns(["a", None])
    validate_template_columns(["a", "b"])  # no lanza


# ── /batch_preview (solo lectura) ──────────────────────────────────────
def test_preview_reports_union_common_and_matrix(client):
    resp = preview(client, ("a.csv", A_CSV), ("b.csv", B_CSV), ("c.csv", C_CSV))
    assert resp.status_code == 200, resp.get_json()
    j = resp.get_json()
    assert j["union"] == ["Fecha", "Region", "Unidades", "Extra"]
    assert j["common"] == ["Fecha", "Region"]
    assert j["total_rows"] == 4
    assert [f["name"] for f in j["files"]] == ["a.csv", "b.csv", "c.csv"]
    assert j["files"][0]["rows"] == 2
    extra = next(c for c in j["columns"] if c["column"] == "Extra")
    assert extra["present"] == ["b.csv"] and extra["missing"] == ["a.csv", "c.csv"]
    # es una previsualización: nada de estado tocado
    assert app_module.current_df is None and app_module.history == []


def test_preview_with_template_reports_differences(client):
    resp = preview(
        client, ("a.csv", A_CSV), ("b.csv", B_CSV),
        template=("tpl.csv", TPL_CSV),
    )
    assert resp.status_code == 200, resp.get_json()
    t = resp.get_json()["template"]
    assert t["columns"] == ["Region", "Unidades", "Fecha", "Observaciones"]
    assert t["dropped"] == ["Extra"]       # fuera del maestro → se descarta
    assert t["missing"] == ["Observaciones"]  # en el maestro, sin datos → vacío


def test_preview_needs_at_least_two_files(client):
    resp = preview(client, ("a.csv", A_CSV))
    assert resp.status_code == 400
    assert "al menos 2" in resp.get_json()["error"]


# ── /batch_merge en modo dinámico ──────────────────────────────────────
def test_merge_dynamic_default_keeps_everything(client):
    resp = merge(client, ("a.csv", A_CSV), ("b.csv", B_CSV), ("c.csv", C_CSV))
    assert resp.status_code == 200, resp.get_json()
    j = resp.get_json()
    assert j["merged"] == {
        "files": ["a.csv", "b.csv", "c.csv"],
        "rows": 4, "columns": 4, "dropped": [],
    }
    assert j["data"]["columns"] == ["Fecha", "Region", "Unidades", "Extra"]
    df = df_of(resp)
    assert len(df) == 4
    # las filas de c.csv quedan vacías en lo que no traían
    assert pd.isna(df.iloc[3]["Unidades"])
    # el dataset activo quedó committeado con reset completo
    assert len(app_module.history) == 1
    assert app_module.op_history == [] and app_module.redo_history == []
    assert app_module.code_log[0].startswith("import pandas as pd")
    # suggestions como en /upload
    assert "type_suggestions" in j and "pii_suggestions" in j


def test_merge_pinned_block_first(client):
    resp = merge(
        client, ("a.csv", A_CSV), ("b.csv", B_CSV), first='["Unidades", "Fecha"]'
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["columns"] == [
        "Unidades", "Fecha", "Region", "Extra"
    ]


def test_merge_rest_alpha(client):
    resp = merge(client, ("a.csv", A_CSV), ("b.csv", B_CSV), rest="alpha")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["columns"] == [
        "Extra", "Fecha", "Region", "Unidades"
    ]


def test_merge_resets_state_after_previous_ops(client):
    client.post("/upload", data={
        "file": (io.BytesIO(A_CSV.encode()), "old.csv")
    }, content_type="multipart/form-data")
    client.post("/operation", json={
        "operation": "trim", "params": {},
    })
    assert len(app_module.history) > 1

    resp = merge(client, ("a.csv", A_CSV), ("b.csv", B_CSV))
    assert resp.status_code == 200, resp.get_json()
    assert len(app_module.history) == 1          # dataset nuevo
    assert app_module.op_history == []           # la receta empieza de cero
    assert app_module.redo_history == []
    assert app_module.step_ms == []
    assert app_module.schema_rules == []


# ── /batch_merge en modo plantilla ─────────────────────────────────────
def test_merge_template_exact_schema(client):
    resp = merge(
        client, ("a.csv", A_CSV), ("b.csv", B_CSV),
        template=("tpl.csv", TPL_CSV), mode="template",
    )
    assert resp.status_code == 200, resp.get_json()
    j = resp.get_json()
    assert j["data"]["columns"] == [
        "Region", "Unidades", "Fecha", "Observaciones"
    ]
    assert j["merged"]["dropped"] == ["Extra"]  # fuera del maestro
    df = df_of(resp)
    assert df["Observaciones"].isna().all()      # sin datos → toda nula


def test_merge_xlsx_file(client):
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(buf, index=False)
    buf.seek(0)
    buf2 = io.BytesIO()
    pd.DataFrame({"a": [3], "b": ["z"]}).to_excel(buf2, index=False)
    buf2.seek(0)
    resp = client.post("/batch_merge", data={
        "files": [(buf, "uno.xlsx"), (buf2, "dos.xlsx")],
        "mode": "dynamic", "rest": "append", "first": "[]",
    }, content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    j = resp.get_json()
    assert j["merged"]["rows"] == 3 and j["merged"]["columns"] == 2


# ── Paridad del código generado ────────────────────────────────────────
def test_generated_code_reproduces_the_merge(client, tmp_path, monkeypatch):
    """El code_log exportable (N lecturas + concat + reindex) reconstruye
    exactamente el df consolidado ejecutado contra los archivos reales."""
    resp = merge(client, ("a.csv", A_CSV), ("b.csv", B_CSV), ("c.csv", C_CSV))
    assert resp.status_code == 200, resp.get_json()
    code = app_module.code_log[-1]
    compile(code, "<generated>", "exec")

    (tmp_path / "a.csv").write_text(A_CSV, encoding="utf-8")
    (tmp_path / "b.csv").write_text(B_CSV, encoding="utf-8")
    (tmp_path / "c.csv").write_text(C_CSV, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    ns = {"pd": pd}
    exec(code, ns)  # noqa: S102 — el script exportado hace exactamente esto
    pd.testing.assert_frame_equal(ns["df"], app_module.current_df)


# ── Errores (400 de contrato, 500 de lectura) ──────────────────────────
@pytest.mark.parametrize(
    "build,fragment",
    [
        (lambda: files(("a.csv", A_CSV)), "al menos 2"),
        (lambda: files(("a.csv", A_CSV), ("b.txt", B_CSV)), "Formato no soportado"),
        (lambda: files(("a.csv", A_CSV), ("b.csv", B_CSV), first='["Fantasma"]'),
         "bloque fijo inexistente"),
        (lambda: files(("a.csv", A_CSV), ("b.csv", B_CSV), rest="rotate"),
         "Orden del resto"),
        (lambda: files(("a.csv", A_CSV), ("b.csv", B_CSV), mode="sideways"),
         "Modo desconocido"),
        (lambda: files(("a.csv", A_CSV), ("b.csv", B_CSV), mode="template"),
         "esquema maestro"),
        (lambda: files(("a.csv", A_CSV), ("b.csv", B_CSV), template=("tpl.csv", TPL_CSV)),
         "modo es Dinámico"),
        (lambda: files(("a.csv", A_CSV), ("b.csv", B_CSV), first="{nope"),
         "lista JSON"),
    ],
    ids=[
        "one_file", "bad_ext", "first_missing", "bad_rest", "bad_mode",
        "template_without_file", "template_in_dynamic", "bad_first_json",
    ],
)
def test_merge_param_errors_are_400(client, build, fragment):
    resp = client.post(
        "/batch_merge", data=build(), content_type="multipart/form-data"
    )
    assert resp.status_code == 400, resp.get_json()
    assert fragment in resp.get_json()["error"]
    assert app_module.current_df is None  # nada de estado parcial


def test_empty_template_is_400(client):
    # pandas mangla las columnas duplicadas al leer (a → a.1), así que ese
    # 400 no es alcanzable por archivo; una plantilla vacía sí es un error
    # de usuario — EmptyDataError es subclase de ValueError → 400.
    resp = merge(
        client, ("a.csv", A_CSV), ("b.csv", B_CSV),
        template=("tpl.csv", ""), mode="template",
    )
    assert resp.status_code == 400
    assert "Plantilla inválida" in resp.get_json()["error"]
    assert app_module.current_df is None


def test_unreadable_file_is_500(client):
    # un archivo vacío lanza EmptyDataError("No columns to parse from file")
    # → 500 con mensaje citando la lectura, nunca un 200 a medias
    resp = merge(client, ("a.csv", A_CSV), ("broken.csv", ""))
    assert resp.status_code == 500
    assert "No se pudieron leer los archivos" in resp.get_json()["error"]
    assert app_module.current_df is None and app_module.history == []
