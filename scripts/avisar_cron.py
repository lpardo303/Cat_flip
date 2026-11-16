#!/usr/bin/env python3
"""Avisa de los fallos de packaging y cierra el aviso al recuperarse.

Dos orígenes, el mismo mecanismo:

* **cron semanal** (`--ok` para cerrar): la corrida programada existe para no
  descubrir en el tag una clave GPG caducada, un secreto mal rotado o un
  runtime que desapareció de flathub. Pero un lunes en rojo no lo mira nadie, y
  un issue de fallo sin cerrar tampoco dice nada: seis meses después no se sabe
  si sigue roto o si se arregló en su momento.
* **tag** (`--tag`, con `GITHUB_REF_NAME`): un tag que falla deja el tag creado
  y la release sin publicar —o en borrador, que nadie ve— y lo único que queda
  es un run en Actions. Mismo trato: issue con título propio (el tag dentro),
  para que dos tags distintos no se pisen el aviso.

Modos (los dos usan la búsqueda de issues para no duplicar):

* **fallo** (por defecto): abre el issue si no existe, comenta si está abierto
  y reabre el que alguien cerró sin que estuviera arreglado.
* **`--ok`**: si hay un issue abierto de ese origen, comenta la corrida buena y
  lo cierra. Si no hay nada abierto, no toca nada.

El issue se localiza con `GET /search/issues` (`in:title`, `type:issue`), no
listando los últimos N: con la lista, un repo con más de 100 issues abiertos
dejaría de encontrar el suyo y abriría un duplicado cada lunes.

Variables de entorno:
    GH_TOKEN             token con permiso de issues (github.token en Actions)
    GITHUB_REPOSITORY    dueño/repo
    GITHUB_REF_NAME      tag, obligatorio con `--tag`
    GITHUB_RUN_ID        id de la corrida (opcional: sin él no hay enlace)
    GITHUB_SHA           commit de la corrida (opcional)
    RESULTADOS           resumen de jobs, p. ej. "appimage=failure, …"
"""
import json
import os
import sys
import urllib.parse
import urllib.request

TITULO_CRON = "Fallo en el cron semanal de packaging"
TITULO_TAG = "Fallo al publicar el tag {tag}"
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
    """El issue de ese origen por búsqueda, abierto o cerrado.

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


def texto_apertura(tag):
    if tag:
        return [
            f"La publicación del tag `{tag}` no ha terminado: el tag existe, pero",
            "su release no está publicada (o se quedó en borrador, que no la ve",
            "nadie). El log del job en rojo dice qué falló.",
            "",
            "Con el flujo en borrador, un fallo de verificación deja la release",
            "sin publicar a propósito; `scripts/verificar_release.sh` y el smoke",
            "del AppImage descargado son los que deciden.",
        ]
    return [
        "La corrida programada del cron de packaging ha fallado.",
        "",
        "El cron existe para no descubrir en el tag una rotura de la firma,",
        "del secreto o del runtime. El log del job en rojo dice cuál fue;",
        "`packaging/sign.sh` distingue la clave mal rotada del `.asc`",
        "desfasado, y `scripts/auditar_bundle.py` el paquete que engordó.",
    ]


def texto_cierre(tag):
    if tag:
        return f"El tag `{tag}` ya ha publicado su release; se cierra."
    return "La corrida programada ha vuelto a salir bien; se cierra."


def texto_se_cierra(tag):
    if tag:
        return "Se cerrará solo cuando ese tag vuelva a salir bien."
    return "Se cerrará solo cuando una corrida programada vuelva a salir bien."


def avisar_fallo(repo, titulo, tag):
    previo = buscar_issue(repo, titulo)
    detalle = datos_corrida(repo)

    if previo is None:
        cuerpo = "\n".join(
            [
                *texto_apertura(tag),
                "",
                *detalle,
                "",
                texto_se_cierra(tag),
                "",
                "_Abierto automáticamente por el workflow «packaging»._",
            ]
        )
        api("POST", f"/repos/{repo}/issues", {"title": titulo, "body": cuerpo})
        print(f"issue abierto: {titulo}")
        return 0

    numero = previo["number"]
    if previo["state"] != "open":
        api("PATCH", f"/repos/{repo}/issues/{numero}", {"state": "open"})
        print(f"issue #{numero} reabierto")

    api(
        "POST",
        f"/repos/{repo}/issues/{numero}/comments",
        {"body": "\n".join(["Otra corrida en rojo.", "", *detalle])},
    )
    print(f"comentado en el issue #{numero}")
    return 0


def cerrar_aviso(repo, titulo, tag):
    previo = buscar_issue(repo, titulo)
    if previo is None:
        print("no hay issue de packaging: no hay nada que cerrar")
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
                    texto_cierre(tag),
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

    args = sys.argv[1:]
    tag = ""
    if "--tag" in args:
        tag = os.environ.get("GITHUB_REF_NAME", "").strip()
        if tag == "":
            print("::error::--tag necesita GITHUB_REF_NAME", file=sys.stderr)
            return 1

    titulo = TITULO_TAG.format(tag=tag) if tag else TITULO_CRON
    if "--ok" in args:
        return cerrar_aviso(repo, titulo, tag)
    return avisar_fallo(repo, titulo, tag)


if __name__ == "__main__":
    sys.exit(main())
