"""Tests del modo CLI (`cli.py run`).

Cubre el camino feliz CSV→CSV, TSV/pipe autodetectado, cp1252, xlsx con
--sheet, salidas xlsx/parquet, validación sin --output, y los errores por
exit code: receta inexistente/no-JSON/malformada, op desconocida, paso
fallido (cita el paso y NO escribe nada), merge sin --right, input
inexistente y extensión de salida no soportada. La atomicidad es la misma
que /apply_recipe: el motor es compartido.
"""
import json

import pandas as pd
import pytest

import cli

BASE_CSV = (
    "Nombre,Edad,Ciudad\n"
    "  Ana ,30,Madrid\n"
    "Luis ,25,Barcelona\n"
    "Carla,35,Madrid\n"
)

RECIPE_STEPS = [
    {"op": "change_case", "params": {"column": "Nombre", "case": "upper"}},
    {"op": "trim", "params": {"columns": ["Nombre", "Ciudad"]}},
]

# Receta mínima para inputs con solo columna Nombre/Edad (TSV, pipes, Excel)
RECIPE_NOMBRE = [
    {"op": "change_case", "params": {"column": "Nombre", "case": "upper"}},
    {"op": "trim", "params": {"columns": ["Nombre"]}},
]


def write_recipe(tmp_path, steps=RECIPE_STEPS, name="receta.catflip.json", raw=None):
    p = tmp_path / name
    if raw is not None:
        p.write_text(raw, encoding="utf-8")
    else:
        p.write_text(
            json.dumps({"version": 1, "app": "catflip", "steps": steps}),
            encoding="utf-8",
        )
    return p


def write_input(tmp_path, text=BASE_CSV, name="datos.csv", encoding="utf-8"):
    p = tmp_path / name
    p.write_bytes(text.encode(encoding))
    return p


def run(*argv):
    """main() con argv explícito; devuelve el exit code."""
    return cli.main(["run", *map(str, argv)])


# ── Camino feliz ───────────────────────────────────────────────────────
def test_run_csv_to_csv_writes_result(tmp_path, capsys):
    recipe = write_recipe(tmp_path)
    inp = write_input(tmp_path)
    out = tmp_path / "limpio.csv"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "ANA" in text and "LUIS" in text
    assert "  Ana " not in text  # change_case + trim aplicados
    stdout = capsys.readouterr().out
    assert f"{len(RECIPE_STEPS)}" in stdout
    assert "Salida:" in str(out) or str(out) in stdout
    # Informe por paso con shapes
    assert "[1/2] change_case" in stdout and "[2/2] trim" in stdout


def test_run_without_output_validates_only(tmp_path, capsys):
    recipe = write_recipe(tmp_path)
    inp = write_input(tmp_path)

    code = run(recipe, "--input", inp)

    assert code == 0
    assert not (tmp_path / "limpio.csv").exists()
    assert "nada escrito" in capsys.readouterr().out


def test_run_show_code_prints_generated_pandas(tmp_path, capsys):
    recipe = write_recipe(tmp_path)
    inp = write_input(tmp_path)

    code = run(recipe, "--input", inp, "--show-code")

    assert code == 0
    out = capsys.readouterr().out
    assert "# change_case" in out and "# trim" in out


def test_run_round_trip_matches_recipe_engine(tmp_path):
    """Mismo resultado que apply_recipe_df directo (motor compartido)."""
    from app import apply_recipe_df, validate_recipe

    recipe = write_recipe(tmp_path)
    inp = write_input(tmp_path)
    out = tmp_path / "limpio.csv"
    assert run(recipe, "--input", inp, "--output", out) == 0

    df = pd.read_csv(inp, skipinitialspace=False)
    df_final, *_ = apply_recipe_df(df, validate_recipe(json.loads(recipe.read_text())))
    pd.testing.assert_frame_equal(pd.read_csv(out), df_final)


# ── Autodetección de entrada ───────────────────────────────────────────
def test_run_tsv_input_autodetects_tab(tmp_path):
    recipe = write_recipe(tmp_path, steps=RECIPE_NOMBRE)
    inp = write_input(tmp_path, "Nombre\tEdad\n  Ana \t30\n", name="datos.tsv")
    out = tmp_path / "limpio.csv"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 0
    df = pd.read_csv(out)
    assert list(df.columns) == ["Nombre", "Edad"]
    assert df["Nombre"][0] == "ANA"


def test_run_pipe_delimiter_input(tmp_path):
    recipe = write_recipe(tmp_path, steps=RECIPE_NOMBRE)
    inp = write_input(tmp_path, "Nombre|Edad\n Ana |30\n", name="datos.csv")
    out = tmp_path / "limpio.csv"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 0
    assert list(pd.read_csv(out).columns) == ["Nombre", "Edad"]


def test_run_cp1252_input_without_mojibake(tmp_path, capsys):
    recipe = write_recipe(tmp_path, steps=[{"op": "trim", "params": {"columns": ["Nombre"]}}])
    inp = write_input(
        tmp_path, "Nombre,Ciudad\nJosé Márquez,Jaén\n", name="datos.csv", encoding="cp1252"
    )
    out = tmp_path / "limpio.csv"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 0
    assert "José Márquez" in out.read_text(encoding="utf-8")
    assert "Codificación detectada: cp1252" in capsys.readouterr().out


# ── Excel ──────────────────────────────────────────────────────────────
def test_run_xlsx_input_with_sheet_and_xlsx_output(tmp_path):
    src = tmp_path / "libro.xlsx"
    with pd.ExcelWriter(src, engine="openpyxl") as xw:
        pd.DataFrame({"Nombre": ["ignorado"]}).to_excel(xw, sheet_name="Hoja1", index=False)
        pd.DataFrame({"Nombre": ["  Ana "], "Edad": [30]}).to_excel(
            xw, sheet_name="Hoja2", index=False
        )
    recipe = write_recipe(tmp_path, steps=RECIPE_NOMBRE)
    out = tmp_path / "limpio.xlsx"

    code = run(recipe, "--input", src, "--sheet", "Hoja2", "--output", out)

    assert code == 0
    df = pd.read_excel(out)
    assert list(df.columns) == ["Nombre", "Edad"]
    assert df["Nombre"][0] == "ANA"


def test_run_xlsx_sheet0_default_is_first(tmp_path):
    src = tmp_path / "libro.xlsx"
    with pd.ExcelWriter(src, engine="openpyxl") as xw:
        pd.DataFrame({"Nombre": ["  Ana "]}).to_excel(xw, sheet_name="Hoja1", index=False)
        pd.DataFrame({"Nombre": ["Otra"]}).to_excel(xw, sheet_name="Hoja2", index=False)
    recipe = write_recipe(tmp_path, steps=RECIPE_NOMBRE)
    out = tmp_path / "limpio.xlsx"

    code = run(recipe, "--input", src, "--output", out)

    assert code == 0
    assert pd.read_excel(out)["Nombre"][0] == "ANA"


# ── Salidas ────────────────────────────────────────────────────────────
def test_run_parquet_output_is_readable(tmp_path):
    recipe = write_recipe(tmp_path)
    inp = write_input(tmp_path)
    out = tmp_path / "limpio.parquet"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 0
    raw = out.read_bytes()
    assert raw[:4] == b"PAR1" and raw[-4:] == b"PAR1"
    assert pd.read_parquet(out)["Nombre"][0] == "ANA"


def test_run_tsv_output(tmp_path):
    recipe = write_recipe(tmp_path)
    inp = write_input(tmp_path)
    out = tmp_path / "limpio.tsv"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 0
    assert pd.read_csv(out, sep="\t")["Nombre"][0] == "ANA"


def test_run_unsupported_output_extension_exit_1(tmp_path, capsys):
    recipe = write_recipe(tmp_path)
    inp = write_input(tmp_path)
    out = tmp_path / "limpio.json"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 1
    assert not out.exists()
    assert "no soportado" in capsys.readouterr().err


def test_run_missing_output_directory_exit_1(tmp_path, capsys):
    recipe = write_recipe(tmp_path)
    inp = write_input(tmp_path)

    code = run(recipe, "--input", inp, "--output", tmp_path / "no_existe" / "x.csv")

    assert code == 1
    assert "directorio" in capsys.readouterr().err


# ── Errores: receta ────────────────────────────────────────────────────
def test_run_recipe_file_missing_exit_1(tmp_path, capsys):
    inp = write_input(tmp_path)
    code = run(tmp_path / "fantasma.json", "--input", inp)
    assert code == 1
    assert "no existe la receta" in capsys.readouterr().err


def test_run_recipe_not_json_exit_1(tmp_path, capsys):
    recipe = write_recipe(tmp_path, raw="{rota")
    inp = write_input(tmp_path)
    code = run(recipe, "--input", inp)
    assert code == 1
    assert "JSON válido" in capsys.readouterr().err


def test_run_recipe_version_unsupported_exit_1(tmp_path, capsys):
    p = tmp_path / "r.catflip.json"
    p.write_text(json.dumps({"version": 2, "steps": RECIPE_STEPS}), encoding="utf-8")
    inp = write_input(tmp_path)
    code = run(p, "--input", inp)
    assert code == 1
    assert "Versión" in capsys.readouterr().err


def test_run_recipe_unknown_op_exit_1(tmp_path, capsys):
    recipe = write_recipe(tmp_path, steps=[{"op": "op_fantasma", "params": {}}])
    inp = write_input(tmp_path)
    code = run(recipe, "--input", inp)
    assert code == 1
    assert "desconocida" in capsys.readouterr().err


def test_run_failing_step_cites_step_and_writes_nothing(tmp_path, capsys):
    """Paso 2 roto → exit 1 citando el paso y CERO archivo de salida."""
    recipe = write_recipe(
        tmp_path,
        steps=[
            {"op": "change_case", "params": {"column": "Nombre", "case": "upper"}},
            {"op": "regex_mask", "params": {"column": "Fantasma", "pattern": "email", "mode": "mask"}},
        ],
    )
    inp = write_input(tmp_path)
    out = tmp_path / "limpio.csv"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 1
    err = capsys.readouterr().err
    assert "El paso 2" in err and "regex_mask" in err
    assert not out.exists()
    assert not list(tmp_path.glob("*.tmp"))  # ni temporal huérfano


# ── Errores: datos ─────────────────────────────────────────────────────
def test_run_input_missing_exit_1(tmp_path, capsys):
    recipe = write_recipe(tmp_path)
    code = run(recipe, "--input", tmp_path / "no.csv")
    assert code == 1
    assert "No existe el archivo" in capsys.readouterr().err


def test_run_input_unsupported_format_exit_1(tmp_path, capsys):
    recipe = write_recipe(tmp_path)
    bad = tmp_path / "datos.json"
    bad.write_text("[]", encoding="utf-8")
    code = run(recipe, "--input", bad)
    assert code == 1
    assert "entrada no soportado" in capsys.readouterr().err


# ── Merge ──────────────────────────────────────────────────────────────
def merge_recipe():
    return [
        {
            "op": "merge",
            "params": {"left_on": "Nombre", "right_on": "Nombre", "how": "left", "suffixes": ["_x", "_y"]},
        }
    ]


def test_run_merge_without_right_exit_1(tmp_path, capsys):
    recipe = write_recipe(tmp_path, steps=merge_recipe())
    inp = write_input(tmp_path)
    out = tmp_path / "limpio.csv"

    code = run(recipe, "--input", inp, "--output", out)

    assert code == 1
    err = capsys.readouterr().err
    assert "El paso 1 (merge)" in err and "--right" in err
    assert not out.exists()


def test_run_merge_with_right_applies(tmp_path):
    recipe = write_recipe(tmp_path, steps=merge_recipe())
    inp = write_input(tmp_path)
    right = tmp_path / "der.csv"
    right.write_text("Nombre,Departamento\nAna,Finanzas\n", encoding="utf-8")
    out = tmp_path / "limpio.csv"

    code = run(recipe, "--input", inp, "--right", right, "--output", out)

    assert code == 0
    df = pd.read_csv(out)
    assert "Departamento" in df.columns
    assert df["Nombre"][0].strip() == "Ana"  # merge no muta el nombre


def test_run_merge_without_right_never_reads_input(tmp_path, capsys):
    """La comprobación de --right es ANTES de cargar: input no hace falta."""
    recipe = write_recipe(tmp_path, steps=merge_recipe())
    code = run(recipe, "--input", tmp_path / "no_existe.csv")
    assert code == 1
    assert "--right" in capsys.readouterr().err


# ── Uso ────────────────────────────────────────────────────────────────
def test_run_requires_input_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "receta.json"])
    assert exc.value.code == 2
    assert "--input" in capsys.readouterr().err


def test_unknown_subcommand_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["frobnicate"])
    assert exc.value.code == 2
