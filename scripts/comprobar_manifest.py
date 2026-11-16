#!/usr/bin/env python3
"""Comprueba que el manifiesto de una release diga la verdad.

`verificar_release.sh` ya verifica la firma de `manifest.json`; esto mira el
contenido contra los ficheros descargados: que cada `sha256` y cada tamaño
coincidan, que la lista sea exactamente lo que hay en el directorio (menos el
propio manifiesto y su firma), que el tag y la versión sean los del paquete y
que la huella sea la versionada en `packaging/gpg/FINGERPRINT`.

Un manifiesto que miente es peor que no tenerlo: es la lista que alguien usa
para decidir si lo descargado es lo publicado.

Uso:
    scripts/comprobar_manifest.py <directorio-con-los-assets>
"""
import hashlib
import json
import os
import sys

ESTRUCTURA = {"manifest.json", "manifest.json.asc"}


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        print("Uso: scripts/comprobar_manifest.py <directorio>", file=sys.stderr)
        return 2
    directorio = sys.argv[1]

    with open(os.path.join(directorio, "manifest.json"), encoding="utf-8") as f:
        manifiesto = json.load(f)
    with open("package.json", encoding="utf-8") as f:
        version = json.load(f)["version"]
    with open("packaging/gpg/FINGERPRINT", encoding="utf-8") as f:
        huella = f.read().strip().replace(" ", "")

    errores = []

    if manifiesto.get("version") != version:
        errores.append(
            f"el manifiesto dice versión {manifiesto.get('version')}, package.json {version}"
        )
    if manifiesto.get("tag") != f"v{version}":
        errores.append(f"el manifiesto dice tag {manifiesto.get('tag')}, esperado v{version}")
    if (manifiesto.get("clave") or "").upper() != huella.upper():
        errores.append(
            f"el manifiesto dice clave {manifiesto.get('clave')}, versionada {huella}"
        )

    listados = {}
    for asset in manifiesto.get("assets", []):
        nombre = asset.get("nombre", "")
        if not nombre or nombre in listados:
            errores.append(f"asset repetido o sin nombre en el manifiesto: {nombre!r}")
            continue
        listados[nombre] = asset

    en_disco = {
        nombre for nombre in os.listdir(directorio) if nombre not in ESTRUCTURA
    }
    for nombre in sorted(en_disco - set(listados)):
        errores.append(f"{nombre} está en la release y no en el manifiesto")
    for nombre in sorted(set(listados) - en_disco):
        errores.append(f"{nombre} está en el manifiesto y no en la release")

    for nombre in sorted(en_disco & set(listados)):
        ruta = os.path.join(directorio, nombre)
        asset = listados[nombre]
        if asset.get("bytes") != os.path.getsize(ruta):
            errores.append(
                f"{nombre}: el manifiesto dice {asset.get('bytes')} bytes, hay "
                f"{os.path.getsize(ruta)}"
            )
        real = sha256(ruta)
        if (asset.get("sha256") or "").lower() != real:
            errores.append(f"{nombre}: sha256 del manifiesto {asset.get('sha256')} ≠ {real}")

    # El propio verificador y la clave pública tienen que ir anunciados: son lo
    # que permite a quien descarga repetir esta comprobación sin este repo.
    for obligatorio in ("verificar_release.sh", "catflip-release.asc"):
        if obligatorio not in listados:
            errores.append(f"el manifiesto no lista {obligatorio}")

    if errores:
        for error in errores:
            print(f"::error::manifest.json: {error}", file=sys.stderr)
        return 1

    print(f"→ manifest.json: {len(listados)} assets, tag v{version}, hashes y clave coinciden")
    return 0


if __name__ == "__main__":
    sys.exit(main())
