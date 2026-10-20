#!/usr/bin/env python3
"""Cat_flip CLI — ejecuta recetas `.catflip.json` sin navegador.

Uso:
    python cli.py run receta.catflip.json --input datos.csv --output limpio.csv

Exit codes: 0 OK · 1 error de receta/datos · 2 uso incorrecto (argparse).

Reutiliza el motor de /apply_recipe (validate_recipe + apply_recipe_df:
validación estructural de TODA la receta antes de ejecutar y reproducción
sobre copias → cero estado parcial) y read_table (autodetección de
separador CSV y codificación, igual que /upload). El archivo de salida se
escribe al final, vía temporal + os.replace: un paso que falla o un error
de escritura nunca dejan un archivo a medias.
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

from app import apply_recipe_df, read_table, validate_recipe

INPUT_EXTS = (".csv", ".tsv", ".xlsx", ".xls")
OUTPUT_EXTS = (".csv", ".tsv", ".xlsx", ".parquet")


class _NamedFile(io.BytesIO):
    """BytesIO con `.filename`: la interfaz mínima que read_table espera."""

    def __init__(self, content, filename):
        super().__init__(content)
        self.filename = filename


def _load_frame(path, sheet=None):
    """Carga un dataset con la misma autodetección que /upload.

    Devuelve (df, expresión pandas, encoding) tal cual read_table.
    """
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"No existe el archivo: {path}")
    if p.suffix.lower() not in INPUT_EXTS:
        raise ValueError(
            f"Formato de entrada no soportado: {p.suffix or '(sin extensión)'} — usa CSV, TSV, XLSX o XLS."
        )
    return read_table(_NamedFile(p.read_bytes(), p.name), sheet=sheet)


def _write_output(df, path):
    """Escribe el resultado según la extensión, de forma atómica.

    Se escribe a `<archivo>.tmp` en el mismo directorio y se renombra con
    os.replace solo si el escritor termina bien: o el archivo completo o
    nada (nunca uno truncado a medias).
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in OUTPUT_EXTS:
        raise ValueError(
            f"Formato de salida no soportado: {p.suffix or '(sin extensión)'} — usa .csv, .tsv, .xlsx o .parquet."
        )
    if not p.parent.is_dir():
        raise ValueError(f"No existe el directorio de salida: {p.parent}")
    tmp = p.with_name(p.name + ".tmp")
    try:
        if ext == ".xlsx":
            df.to_excel(tmp, index=False, engine="openpyxl")
        elif ext == ".parquet":
            df.to_parquet(tmp, index=False)
        elif ext == ".tsv":
            df.to_csv(tmp, index=False, sep="\t")
        else:
            df.to_csv(tmp, index=False)
        os.replace(tmp, p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return p


def _run(args):
    # 1) Receta en disco
    recipe_path = Path(args.recipe)
    if not recipe_path.is_file():
        print(f"Error: no existe la receta: {args.recipe}", file=sys.stderr)
        return 1
    try:
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"Error: La receta no es JSON válido. ({e})", file=sys.stderr)
        return 1

    # 2) Validación estructural COMPLETA antes de tocar datos
    try:
        steps = validate_recipe(recipe)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # 3) merge necesita frame derecho: se avisa ANTES de cargar nada
    if not args.right:
        for i, step in enumerate(steps, 1):
            if step["op"] == "merge":
                print(
                    f"Error: El paso {i} (merge): hace falta --right <archivo> "
                    "(receta con cruce pero sin frame derecho).",
                    file=sys.stderr,
                )
                return 1

    # 4) Cargas (autodetecta separador + encoding como /upload)
    try:
        df, _expr, encoding = _load_frame(args.input, sheet=args.sheet)
        right_df = right_code = None
        if args.right:
            right_df, right_code, _ = _load_frame(args.right)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # 5) Reproducción atómica: un paso fallido ⇒ exit 1 y CERO escritura
    try:
        df_final, snaps, codes, applied = apply_recipe_df(
            df, steps, right_df=right_df, right_code=right_code
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # 6) Informe en stdout
    print(f"Entrada: {Path(args.input).name} → {df.shape[0]}×{df.shape[1]}")
    if encoding:
        print(f"Codificación detectada: {encoding}")
    prev = df.shape
    for i, (step, snap) in enumerate(zip(applied, snaps), 1):
        print(
            f"[{i}/{len(applied)}] {step['op']} "
            f"{prev[0]}×{prev[1]} → {snap.shape[0]}×{snap.shape[1]}"
        )
        prev = snap.shape

    if args.show_code:
        print("\n" + "\n\n".join(codes))

    if args.output:
        try:
            out = _write_output(df_final, args.output)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(f"Salida: {out} ({df_final.shape[0]}×{df_final.shape[1]})")
    else:
        print(
            f"Receta válida ({len(applied)} pasos, resultado "
            f"{df_final.shape[0]}×{df_final.shape[1]}) — sin --output, nada escrito."
        )
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="Cat_flip CLI — ejecuta recetas .catflip.json sin navegador.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser(
        "run", help="ejecuta una receta sobre un dataset y escribe el resultado"
    )
    run.add_argument("recipe", help="ruta a la receta .catflip.json")
    run.add_argument(
        "--input", "-i", required=True, help="dataset de entrada (.csv .tsv .xlsx .xls)"
    )
    run.add_argument(
        "--output",
        "-o",
        default=None,
        help="archivo de salida (.csv .tsv .xlsx .parquet); sin esta opción solo valida",
    )
    run.add_argument("--right", default=None, help="frame derecho para pasos merge")
    run.add_argument("--sheet", default=None, help="hoja de Excel de entrada (default: 0)")
    run.add_argument(
        "--show-code",
        action="store_true",
        help="imprime el código pandas generado por cada paso",
    )
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return _run(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
