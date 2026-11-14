#!/usr/bin/env python3
"""Avisa de los fallos del cron de packaging y cierra el aviso al recuperarse.

El cron semanal existe para no descubrir en el tag una clave GPG caducada, un
secreto mal rotado o un runtime que desapareció de flathub. Pero un lunes en
rojo no lo mira nadie, y un issue de fallo sin cerrar tampoco dice nada: seis
meses después no se sabe si sigue roto o si se arregló en su momento.

Modos (los dos usan la búsqueda de issues para no duplicar):

* **fallo** (por defecto): abre el issue si no existe, comenta si está abierto
  y reabre el que alguien cerró sin que estuviera arreglado.
* **`--ok`**: si hay un issue abierto del cron, comenta la corrida buena y lo
  cierra. Si no hay nada abierto, no toca nada.

El issue se localiza con `GET /search/issues` (`in:title`, `type:issue`), no
listando los últimos N: con la lista, un repo con más de 100 issues abiertos
dejaría de encontrar el suyo y abriría un duplicado cada lunes.

Lo llama `packaging.yml` solo en corridas programadas: un `workflow_dispatch`
lo lanza alguien que ya está mirando.

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
import urllib.parse
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


def buscar_issue(repo, titulo):
    """El issue del cron por búsqueda, abierto o cerrado.

    La búsqueda es difusa (encuentra por palabras), así que se compara el
    título exacto antes de darlo por bueno. `type:issue` descarta los PRs, que
    si no aparecen con el mismo texto.
    """
    consulta = f'repo:{repo} in:title type:issue "{titulo}"'
    ruta = "/search/issues?per_page=100&q=" + urllib.parse.quote(consulta)
    for issue in api("GET", ruta).get("items", []):
        if issue.get("title") == titulo:
            return issue
    return None


def datos_corrida(repo):
    corrida = os.environ.get("GITHUB_RUN_ID", "").strip()
    sha = os.environ.get("GITHUB_SHA", "").strip()[:7]
    detalle = []
    if corrida:
        detalle.append(f"- Corrida: https://github.com/{repo}/actions/runs/{corrida}")
    if sha:
        detalle.append(f"- Commit: `{sha}`")
    resultados = os.environ.get("RESULTADOS", "").strip()
    if resultados:
        detalle.append(f"- Jobs: {resultados}")
    return detalle


def avisar_fallo(repo):
    previo = buscar_issue(repo, TITULO)
    detalle = datos_corrida(repo)

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
                "Se cerrará solo cuando una corrida programada vuelva a salir bien.",
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
        {"body": "\n".join(["Otra corrida programada en rojo.", "", *detalle])},
    )
    print(f"comentado en el issue #{numero}")
    return 0


def cerrar_aviso(repo):
    previo = buscar_issue(repo, TITULO)
    if previo is None:
        print("no hay issue del cron: no hay nada que cerrar")
        return 0
    if previo["state"] != "open":
        print(f"el issue #{previo['number']} ya estaba cerrado")
        return 0

    numero = previo["number"]
    api(
        "POST",
        f"/repos/{repo}/issues/{numero}/comments",
        {
            "body": "\n".join(
                [
                    "La corrida programada ha vuelto a salir bien; se cierra.",
                    "",
                    *datos_corrida(repo),
                ]
            )
        },
    )
    api("PATCH", f"/repos/{repo}/issues/{numero}", {"state": "closed"})
    print(f"issue #{numero} cerrado")
    return 0


def main():
    if os.environ.get("GH_TOKEN", "").strip() == "":
        print("::error::falta GH_TOKEN", file=sys.stderr)
        return 1
    repo = os.environ["GITHUB_REPOSITORY"]
    if "--ok" in sys.argv[1:]:
        return cerrar_aviso(repo)
    return avisar_fallo(repo)


if __name__ == "__main__":
    sys.exit(main())
