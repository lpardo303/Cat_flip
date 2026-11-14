#!/usr/bin/env python3
"""Avisa de un fallo del cron de packaging abriendo o actualizando un issue.

El cron semanal existe para no descubrir en el tag una clave GPG caducada, un
secreto mal rotado o un runtime que desapareció de flathub. Pero un lunes en
rojo no lo mira nadie: el fallo quedaba en Actions hasta que alguien entraba.
Este script convierte ese rojo en un issue.

Reglas para no llenar la lista de issues:

* si no existe, lo abre;
* si existe y está abierto, **comenta** la corrida nueva en vez de abrir otro;
* si existe cerrado, lo reabre y comenta (alguien lo dio por resuelto y no lo
  estaba).

Lo llama el job `avisar-fallo` de `packaging.yml` solo en corridas
programadas: un `workflow_dispatch` lo lanza alguien que ya está mirando.

Variables de entorno:
    GH_TOKEN             token con permiso de issues (github.token en Actions)
    GITHUB_REPOSITORY    dueño/repo
    GITHUB_RUN_ID        id de la corrida (opcional: sin él no hay enlace)
    GITHUB_SHA           commit de la corrida (opcional)
    RESULTADOS           resumen de jobs, p. ej. "appimage=failure, …"
"""
import json
import os
import sys
import urllib.request

TITULO = "Fallo en el cron semanal de packaging"
API = "https://api.github.com"

# En Windows/CI con stdout redirigido y locales raros, un acento no debe tumbar
# el aviso: aquí perder un carácter es mejor que no avisar.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")


def api(metodo, ruta, payload=None):
    cabeceras = {
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cat-flip-cron-aviso",
    }
    datos = None
    if payload is not None:
        datos = json.dumps(payload).encode()
        cabeceras["Content-Type"] = "application/json"
    peticion = urllib.request.Request(
        API + ruta, data=datos, method=metodo, headers=cabeceras
    )
    with urllib.request.urlopen(peticion, timeout=30) as respuesta:
        if respuesta.status == 204:
            return None
        return json.load(respuesta)


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    corrida = os.environ.get("GITHUB_RUN_ID", "").strip()
    sha = os.environ.get("GITHUB_SHA", "").strip()[:7]
    resultados = os.environ.get("RESULTADOS", "").strip()

    detalle = []
    if corrida:
        detalle.append(f"- Corrida: https://github.com/{repo}/actions/runs/{corrida}")
    if sha:
        detalle.append(f"- Commit: `{sha}`")
    if resultados:
        detalle.append(f"- Jobs: {resultados}")

    # `state=all` para reabrir el anterior en vez de crear otro cada lunes.
    issues = api("GET", f"/repos/{repo}/issues?state=all&per_page=100")
    previo = next(
        (
            i
            for i in issues
            if "pull_request" not in i and i["title"] == TITULO
        ),
        None,
    )

    if previo is None:
        cuerpo = "\n".join(
            [
                "La corrida programada del cron de packaging ha fallado.",
                "",
                *detalle,
                "",
                "El cron existe para no descubrir en el tag una rotura de la firma,",
                "del secreto o del runtime. El log del job en rojo dice cuál fue;",
                "`packaging/sign.sh` distingue la clave mal rotada del `.asc`",
                "desfasado, y `scripts/auditar_bundle.py` el paquete que engordó.",
                "",
                "_Abierto automáticamente por el workflow «packaging»._",
            ]
        )
        api("POST", f"/repos/{repo}/issues", {"title": TITULO, "body": cuerpo})
        print(f"issue abierto: {TITULO}")
        return 0

    numero = previo["number"]
    if previo["state"] != "open":
        api("PATCH", f"/repos/{repo}/issues/{numero}", {"state": "open"})
        print(f"issue #{numero} reabierto")

    api(
        "POST",
        f"/repos/{repo}/issues/{numero}/comments",
        {
            "body": "\n".join(
                ["Otra corrida programada en rojo.", "", *detalle]
            )
        },
    )
    print(f"comentado en el issue #{numero}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
