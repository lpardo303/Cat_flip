#!/usr/bin/env python3
"""Borra los borradores de release que quedaron abandonados.

Desde que la release nace en borrador (ver `packaging/README.md`), un tag cuya
verificación falla deja un borrador que no ve nadie: no está publicado, no
aparece en la página de releases para quien descarga, y el tag queda creado sin
release. En la práctica nadie los borra a mano, y se acumulan.

Este script lo hace desde el cron semanal: lista las releases, se queda con las
que son borrador y tienen más de `DIAS_BORRADOR` días (7 por defecto), dice qué
hay antes de borrar y las elimina. Un borrador no tiene descargas ni
consumidores: sus assets se reconstruyen desde el tag, así que borrarlo no
pierde nada que no esté en el repo.

`--dry-run` lista sin borrar (para probarlo a mano).

Variables de entorno:
    GH_TOKEN             token con permiso de contents
    GITHUB_REPOSITORY    dueño/repo
    DIAS_BORRADOR        días de gracia antes de borrar (por defecto 7)
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"

for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")


def api(metodo, ruta):
    peticion = urllib.request.Request(
        API + ruta,
        method=metodo,
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "cat-flip-borradores",
        },
    )
    with urllib.request.urlopen(peticion, timeout=30) as respuesta:
        if respuesta.status == 204:
            return None
        return json.load(respuesta)


def edad_dias(instante):
    """Días completos desde `created_at` (`YYYY-MM-DDTHH:MM:SSZ`)."""
    cuando = datetime.fromisoformat(instante.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - cuando).days


def main():
    if os.environ.get("GH_TOKEN", "").strip() == "":
        print("::error::falta GH_TOKEN", file=sys.stderr)
        return 1
    repo = os.environ["GITHUB_REPOSITORY"]
    dias = int(os.environ.get("DIAS_BORRADOR", "7"))
    dry_run = "--dry-run" in sys.argv[1:]

    releases = api("GET", f"/repos/{repo}/releases?per_page=100")
    borradores = [r for r in releases if r.get("draft")]
    viejos = [r for r in borradores if edad_dias(r["created_at"]) >= dias]

    print(f"→ {len(releases)} releases, {len(borradores)} en borrador, "
          f"{len(viejos)} con {dias} días o más")

    for r in viejos:
        edad = edad_dias(r["created_at"])
        print(f"  · {r.get('tag_name') or r.get('name') or r['id']}: "
              f"{edad} días, {len(r.get('assets', []))} assets")
        if dry_run:
            print("    (dry-run: no se borra)")
            continue
        api("DELETE", f"/repos/{repo}/releases/{r['id']}")
        print("    borrado")

    if not viejos:
        print("no hay borradores abandonados: nada que hacer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
