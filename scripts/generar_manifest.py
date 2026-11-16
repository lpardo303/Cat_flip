#!/usr/bin/env python3
"""Escribe `manifest.json`: qué se publica, con qué hash y con qué clave.

Los checksums ya viajan (`SHA256SUMS.*`), pero están repartidos en tres ficheros
por formato y no dicen nada del conjunto: ni qué versión, ni de qué commit, ni
con qué clave se firmó. El manifiesto es la lista completa y verificable, y va
firmado con la misma clave que los paquetes.

Determinista a propósito: `commit`/`generado` salen del commit (no del reloj), así
que un rerun del mismo tag produce exactamente el mismo `manifest.json` y la
comparación de assets del job `release` sigue significando algo.

Uso:
    scripts/generar_manifest.py --salida manifest.json fichero [fichero...]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def git(*args):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", default="manifest.json")
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""))
    parser.add_argument("ficheros", nargs="+")
    args = parser.parse_args()

    with open("package.json", encoding="utf-8") as f:
        version = json.load(f)["version"]
    with open("packaging/gpg/FINGERPRINT", encoding="utf-8") as f:
        huella = f.read().strip().replace(" ", "")

    commit = git("rev-parse", "HEAD")
    generado = git("log", "-1", "--format=%cI", commit)

    assets = []
    for ruta in args.ficheros:
        nombre = os.path.basename(ruta)
        if nombre in ("manifest.json", "manifest.json.asc"):
            print(f"::error::{nombre} no puede ir dentro del manifiesto", file=sys.stderr)
            return 1
        assets.append(
            {"nombre": nombre, "bytes": os.path.getsize(ruta), "sha256": sha256(ruta)}
        )
    assets.sort(key=lambda a: a["nombre"])

    tag = args.tag or f"v{version}"
    if tag != f"v{version}":
        print(f"::error::tag {tag} ≠ package.json {version}", file=sys.stderr)
        return 1

    manifiesto = {
        "tag": tag,
        "version": version,
        "commit": commit,
        "generado": generado,
        "clave": huella,
        "assets": assets,
    }
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(manifiesto, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"→ {args.salida}: {len(assets)} assets, tag {tag}, commit {commit[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
