#!/usr/bin/env python3
"""Presupuesto de tamaño y lista de contenidos de un bundle ya construido.

Dos cosas que nadie miraba: cuánto pesa el paquete y qué viaja dentro. Un
`datas` de más en el `.spec` (o un `--add-data` copiado de otro proyecto) mete
tests, fixtures o un entorno virtual dentro del binario y el smoke no se
enteraba: el paquete arrancaba igual, solo pesaba más.

Qué hace:

1. Compara el tamaño del fichero que se distribuye con el presupuesto del
   formato y **falla si lo pasa**. El presupuesto no es un número mágico: está
   medido y en el repo, así que subirlo es una decisión consciente.
2. Enumera lo que lleva dentro y **falla si aparece algo que no debería**:
   tests, `.git`, logs, `.env`, `__pycache__` o un venv.
3. Imprime el reparto por grupos (peso y porcentaje) para que el tamaño esté
   justificado en el log y no solo medido: si el AppImage pesa 110 MiB, se ve
   que pandas/numpy se llevan la mitad y que el resto es Qt/CPython.

Uso:
    scripts/auditar_bundle.py appimage|flatpak --tamano <bytes> --dir <carpeta>
    scripts/auditar_bundle.py windows --tamano <bytes> --exe <onefile.exe>

El `.exe` es un onefile de PyInstaller: sus contenidos se leen del archivo con
`PyInstaller.archive.readers` (el job que lo construye ya tiene PyInstaller).
"""
import argparse
import os
import re
import sys
from pathlib import Path

MiB = 1024 * 1024

# Presupuesto por formato, en MiB. Medido el 2026-11-14:
#   release v1.6.0 (lo que se publica):  AppImage 110,0 | flatpak 66,2 | .exe 64,0
#   build local de esa misma versión:    AppImage 131,6 | flatpak 99,0
# El tope queda ~10 % por encima del mayor de los dos para no fallar por cómo
# comprime la herramienta de turno (que cambia el tamaño del fichero, no su
# contenido), pero un `datas` de más —fixtures, tests, un venv— sí lo pasa.
# Si el crecimiento es legítimo, se sube aquí en el mismo commit que lo explica.
PRESUPUESTO = {"appimage": 145, "flatpak": 110, "windows": 72}

# (patrón, motivo). Se aplican al camino relativo dentro del bundle.
PROHIBIDOS = [
    (re.compile(r"(^|/)\.git(/|$)"), ".git"),
    (re.compile(r"(^|/)\.env(\.[^/]*)?$"), ".env"),
    (re.compile(r"(^|/)logs?(/|$)"), "logs"),
    (re.compile(r"\.log$"), "logs"),
    (re.compile(r"(^|/)tests?(/|$)"), "tests"),
    (re.compile(r"(^|/)test_[^/]*\.py$"), "tests"),
    (re.compile(r"(^|/)[^/]*_test\.py$"), "tests"),
    (re.compile(r"(^|/)conftest\.py$"), "tests"),
    (re.compile(r"(^|/)\.venv(/|$)"), "entorno virtual"),
    (re.compile(r"(^|/)venv(/|$)"), "entorno virtual"),
    (re.compile(r"(^|/)__pycache__(/|$)"), "__pycache__"),
    (re.compile(r"\.pyc$"), "__pycache__"),
]


# Rutas que se parecen a lo prohibido pero son datos legítimos.
# `botocore/data/logs/` son los esquemas del servicio CloudWatch Logs (sin
# ellos el conector S3/GCP se rompe), no un directorio de logs.
EXENCIONES = (re.compile(r"(^|/)data/logs/"),)


def _mib(n):
    return f"{n / MiB:.1f}".replace(".", ",")


def _entradas_dir(raiz):
    """[(camino relativo, bytes)] de todo lo que hay bajo `raiz`."""
    raiz = Path(raiz)
    entradas = []
    for base, _dirs, ficheros in os.walk(raiz):
        for nombre in ficheros:
            ruta = Path(base) / nombre
            try:
                tamano = ruta.stat().st_size
            except OSError:
                continue
            entradas.append((ruta.relative_to(raiz).as_posix(), tamano))
    return entradas


def _entradas_exe(ruta):
    """[(nombre, bytes)] del archivo de un onefile de PyInstaller."""
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except ImportError:
        raise SystemExit(
            "✘ para auditar el .exe hace falta PyInstaller "
            "(lo tiene el job que lo construye)"
        )
    lector = CArchiveReader(str(ruta))
    entradas = []
    for nombre, datos in lector.toc.items():
        # toc: (posición, comprimido, sin comprimir, tipo, ...)
        tamano = max(datos[1] or 0, datos[2] or 0) if len(datos) > 2 else 0
        entradas.append((str(nombre), tamano))
    return entradas


def _grupo(camino):
    """Agrupa por módulo/carpeta grande: `_internal/pandas`, `certifi`…"""
    partes = camino.split("/")
    if "_internal" in partes:
        i = partes.index("_internal")
        if len(partes) > i + 1:
            return "/".join(partes[i : i + 2])
        return partes[i]
    if len(partes) > 1:
        return "/".join(partes[:2])
    return partes[0]


def revisar_contenidos(formato, entradas):
    hallazgos = []
    for camino, _tamano in entradas:
        if any(exencion.search(camino) for exencion in EXENCIONES):
            continue
        for patron, motivo in PROHIBIDOS:
            if patron.search(camino):
                hallazgos.append((motivo, camino))
                break
    if not hallazgos:
        print(
            f"✅ contenidos del {formato}: {len(entradas)} entradas, "
            "nada prohibido (tests, .git, logs, .env)"
        )
        return 0

    print(
        f"::error::el {formato} lleva dentro {len(hallazgos)} fichero(s) que no "
        "deberían distribuirse. Revisa el `datas`/`--add-data` del .spec.",
        file=sys.stderr,
    )
    for motivo, camino in hallazgos[:10]:
        print(f"  {motivo:16} {camino}", file=sys.stderr)
    if len(hallazgos) > 10:
        print(f"  … y {len(hallazgos) - 10} más", file=sys.stderr)
    return 1


def reparto(entradas, tope=6):
    """Los grupos que se llevan el peso, para justificar el tamaño."""
    suma = {}
    for camino, tamano in entradas:
        grupo = _grupo(camino)
        suma[grupo] = suma.get(grupo, 0) + tamano
    total = sum(suma.values()) or 1
    mayores = sorted(suma.items(), key=lambda par: par[1], reverse=True)[:tope]
    return [(g, b, 100 * b / total) for g, b in mayores]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formato", choices=sorted(PRESUPUESTO))
    parser.add_argument("--tamano", type=int, required=True, help="bytes del fichero distribuido")
    parser.add_argument("--dir", help="carpeta con el contenido del bundle")
    parser.add_argument("--exe", help="onefile de PyInstaller (.exe)")
    args = parser.parse_args()

    if args.formato == "windows" and not args.exe:
        raise SystemExit("✘ el formato windows necesita --exe")
    if args.formato != "windows" and not args.dir:
        raise SystemExit(f"✘ el formato {args.formato} necesita --dir")

    entradas = _entradas_exe(args.exe) if args.exe else _entradas_dir(args.dir)
    if not entradas:
        raise SystemExit(f"✘ no se encontró contenido en {args.dir or args.exe}")

    tope = PRESUPUESTO[args.formato]
    peso = _mib(args.tamano)
    uso = 100 * args.tamano / (tope * MiB)
    print(f"→ presupuesto {args.formato}: {peso} MiB de {tope} MiB ({uso:.0f} %)")
    print("  reparto (sin comprimir):")
    for grupo, bytes_grupo, pct in reparto(entradas):
        print(f"    {grupo:34} {_mib(bytes_grupo):>7} MiB ({pct:.0f} %)")

    fallo = revisar_contenidos(args.formato, entradas)

    if args.tamano > tope * MiB:
        print(
            f"::error::el {args.formato} pesa {peso} MiB y el presupuesto es "
            f"{tope} MiB. Mira el reparto de arriba: si el peso es legítimo, "
            "sube PRESUPUESTO en scripts/auditar_bundle.py explicando por qué.",
            file=sys.stderr,
        )
        return 1
    return fallo


if __name__ == "__main__":
    sys.exit(main())
