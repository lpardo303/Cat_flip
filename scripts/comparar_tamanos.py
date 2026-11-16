#!/usr/bin/env python3
"""Compara el peso de la release con la anterior y avisa si creció de más.

El presupuesto de `scripts/auditar_bundle.py` es un tope ABSOLUTO por formato:
mientras quepa, el paquete puede engordar 20 MiB sin que nadie lo mire. Este
script pone la otra mitad: cuánto ha crecido respecto a la release anterior, con
un umbral relativo. Un salto grande suele ser un `datas` de más, una dependencia
nueva o una dependencia que dejó de limpiarse.

Un crecimiento legítimo (una dependencia nueva de verdad) se acepta subiendo
`CRECIMIENTO_PCT` en el mismo commit que lo explica, igual que `PRESUPUESTO`.

Variables de entorno:
    GH_TOKEN             token con lectura de releases
    GITHUB_REPOSITORY    dueño/repo
    TAG                  release a comparar (por defecto `GITHUB_REF_NAME`)
    CRECIMIENTO_PCT      umbral de crecimiento por formato (por defecto 15)
"""
import json
import os
import sys
import urllib.request

API = "https://api.github.com"
SUFIJOS = (".AppImage", ".flatpak", ".exe")

for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")


def api(ruta):
    peticion = urllib.request.Request(
        API + ruta,
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "cat-flip-tamanos",
        },
    )
    with urllib.request.urlopen(peticion, timeout=30) as respuesta:
        return json.load(respuesta)


def por_sufijo(release):
    """{sufijo: (nombre, bytes)} de los paquetes de una release."""
    paquetes = {}
    for asset in release.get("assets", []):
        # `SHA256SUMS.flatpak` también acaba en `.flatpak`: sin este filtro
        # pisaba al bundle de verdad y la tabla salía con 0,0 MiB.
        if asset["name"].startswith("SHA256SUMS"):
            continue
        for sufijo in SUFIJOS:
            if asset["name"].endswith(sufijo):
                paquetes[sufijo] = (asset["name"], asset["size"])
    return paquetes


def mib(n):
    return f"{n / (1024 * 1024):.1f}".replace(".", ",")


def main():
    if os.environ.get("GH_TOKEN", "").strip() == "":
        print("::error::falta GH_TOKEN", file=sys.stderr)
        return 1
    repo = os.environ["GITHUB_REPOSITORY"]
    tag = os.environ.get("TAG", "").strip() or os.environ.get("GITHUB_REF_NAME", "").strip()
    if tag == "":
        print("::error::falta TAG (o GITHUB_REF_NAME)", file=sys.stderr)
        return 1
    umbral = float(os.environ.get("CRECIMIENTO_PCT", "15"))

    releases = api(f"/repos/{repo}/releases?per_page=100")
    actual = next((r for r in releases if r.get("tag_name") == tag), None)
    if actual is None:
        print(f"::error::no encuentro la release {tag}", file=sys.stderr)
        return 1

    anteriores = [
        r for r in releases
        if not r.get("draft") and r.get("tag_name") != tag and not r.get("prerelease")
    ]
    if not anteriores:
        print("→ no hay release publicada anterior: no hay con qué comparar")
        return 0
    anterior = anteriores[0]

    nuevos = por_sufijo(actual)
    viejos = por_sufijo(anterior)
    filas = []
    fallo = 0
    for sufijo in SUFIJOS:
        if sufijo not in nuevos or sufijo not in viejos:
            continue
        nombre, nuevo = nuevos[sufijo]
        _, viejo = viejos[sufijo]
        pct = 100 * (nuevo - viejo) / viejo if viejo else 0.0
        marca = ""
        if pct > umbral:
            marca = f"  ⚠ supera {umbral:.0f} %"
            fallo = 1
        filas.append(f"| {sufijo.lstrip('.')} | {mib(viejo)} MiB | {mib(nuevo)} MiB | {pct:+.1f} %{marca} |")

    print(f"→ peso frente a {anterior['tag_name']} (umbral {umbral:.0f} %):")
    tabla = "\n".join(
        [
            f"| Formato | {anterior['tag_name']} | {tag} | Crecimiento |",
            "| --- | --- | --- | --- |",
            *filas,
        ]
    )
    print(tabla)

    resumen = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(f"### Peso frente a {anterior['tag_name']}\n\n{tabla}\n\n")

    if fallo:
        print(
            f"::error::algún paquete ha crecido más de {umbral:.0f} % respecto a "
            f"{anterior['tag_name']}. Si es legítimo (una dependencia nueva), sube "
            "CRECIMIENTO_PCT en scripts/comparar_tamanos.py en el mismo commit.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
