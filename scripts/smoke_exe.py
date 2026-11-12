#!/usr/bin/env python3
"""Smoke de un binario congelado ya arrancado: ¿lee de verdad los fixtures?

El `.exe` de Windows era el único artefacto sin verificar: se compilaba a mano
y nadie comprobaba que el paquete incluyera lo que el venv da por hecho. Los
`hiddenimports` (`formats`, `python_calamine`) y los `datas` (plantillas,
`static`) son exactamente lo que un entorno de desarrollo no necesita y un
bundle sí: si falta, el binario arranca y luego devuelve 500 al subir un
`.xls`, o sirve una página sin los formatos.

Este script no construye nada ni sabe de sistemas operativos: se apunta a una
URL ya levantada y comprueba, con los fixtures reales del repo, que el paquete
lee cada formato. Sirve igual para `dist/CatFlip` en Linux que para
`dist/windows/CatFlip-<ver>-x64.exe` en el runner de Windows.

Uso:
    python scripts/smoke_exe.py [--base-url http://127.0.0.1:5050]

Sale 1 con el error exacto si algo falla.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))  # `formats` vive en la raíz del repo

import formats  # noqa: E402 — después de ajustar sys.path

# En Windows, con stdout redirigido el codec es cp1252 y un «✅» lanza
# UnicodeEncodeError justo cuando el smoke acaba de pasar. UTF-8 explícito:
# los emoji son parte de la salida legible y el log de la CI los muestra bien.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")

FIXTURES = RAIZ / "tests" / "fixtures"

# Formato → (columnas esperadas, filas). Los nombres salen de los fixtures
# reales, así que un cambio de motor que altere el contrato de lectura se ve
# aquí, en el artefacto, no solo en los tests.
CASOS = [
    ("ventas.xls", ["Nombre", "Edad", "Ciudad", "Salario"], 3),
    ("ventas.ods", ["Nombre", "Edad", "Ciudad", "Salario"], 3),
    ("hojas.xlsb", [1, 2], 4),
    ("ventas.parquet", ["Nombre", "Edad", "Ciudad", "Salario"], 3),
    ("ventas.json", ["Nombre", "Edad", "Ciudad", "Salario"], 3),
    (
        "contrato.xlsx",
        ["Nombre", "Edad", "Salario", "Activo", "Fecha", "Ciudad", "Vacio", "Nota"],
        3,
    ),
]


def _multipart(nombre, contenido):
    limite = uuid.uuid4().hex
    cuerpo = (
        f"--{limite}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{nombre}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + contenido + f"\r\n--{limite}--\r\n".encode()
    return cuerpo, f"multipart/form-data; boundary={limite}"


def _post(base, ruta, nombre, contenido):
    cuerpo, tipo = _multipart(nombre, contenido)
    peticion = urllib.request.Request(
        f"{base}{ruta}", data=cuerpo, method="POST",
        headers={"Content-Type": tipo},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=180) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detalle = error.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"✘ {ruta} con {nombre}: HTTP {error.code} → {detalle}")


def _get(base, ruta):
    with urllib.request.urlopen(f"{base}{ruta}", timeout=30) as respuesta:
        return respuesta.read().decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5050")
    base = parser.parse_args().base_url.rstrip("/")

    # 1) La página debe anunciar los formatos: formats.py + Jinja en el bundle.
    html = _get(base, "/")
    if formats.read_accept() not in html:
        raise SystemExit(
            f"✘ la página no anuncia {formats.read_accept()}: el bundle no "
            "trajo formats.py o la plantilla quedó vieja"
        )
    if "window.CATFLIP_FORMATS" not in html:
        raise SystemExit("✘ la página no inyecta window.CATFLIP_FORMATS")
    print(f"✅ página con los {len(formats.READ_EXTS)} formatos")

    # 2) Cada fixture real tiene que leerse con el binario.
    for nombre, columnas, filas in CASOS:
        ruta = FIXTURES / nombre
        datos = _post(base, "/upload", ruta.name, ruta.read_bytes())
        if not datos.get("success"):
            raise SystemExit(f"✘ {nombre}: respuesta sin success → {datos}")
        obtenidas = datos["data"]["columns"]
        if obtenidas != columnas:
            raise SystemExit(f"✘ {nombre}: columnas {obtenidas} ≠ {columnas}")
        if datos["data"]["total_rows"] != filas:
            raise SystemExit(
                f"✘ {nombre}: {datos['data']['total_rows']} filas ≠ {filas}"
            )
        print(f"✅ {nombre} → {len(columnas)} columnas × {filas} filas")

    # 3) El selector de hoja también vive en el paquete (y descarta la de gráfico)
    hojas = _post(
        base, "/get_sheets", "contrato.xlsx", (FIXTURES / "contrato.xlsx").read_bytes()
    )
    if hojas.get("sheets") != ["ventas", "combinadas", "Oculta"]:
        raise SystemExit(f"✘ /get_sheets devolvió {hojas.get('sheets')}")
    print("✅ /get_sheets lista las 3 hojas de trabajo y descarta la de gráfico")

    print(f"\n{2 + len(CASOS)} comprobaciones OK contra {base}")


if __name__ == "__main__":
    main()
