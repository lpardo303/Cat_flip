# -*- coding: utf-8 -*-
"""Abre la URL del servidor en el navegador por defecto del usuario.

Lo llaman los tres bundles (Flatpak, AppImage y `.exe`) desde `entry.py`.
Hasta 1.6.0 el binario congelado solo levantaba Flask: el usuario abría
Cat_flip desde el menú, veía que «no pasaba nada» y tenía que escribir
`127.0.0.1:5050` a mano — algo que los lanzadores de desarrollo
(`launch.sh`, `launch.fish`, `launch.bat`, `launch.ps1`) sí hacían, pero que
no viaja dentro del paquete instalado.

Tres decisiones que importan:

1. **Hilo aparte.** `app.run()` es bloqueante, así que la espera y la
   apertura van en un hilo *daemon*: la primera petición al navegador se
   hace cuando el puerto ya responde, y el hilo nunca retrasa ni impide el
   cierre del servidor.
2. **Nunca rompe la app.** Sin navegador, sin sesión gráfica o con un
   `xdg-open` que falla, esto devuelve `False` en silencio: el servidor
   sigue funcionando y la URL está en la consola.
3. **Silencioso donde no toca.** En CI (`CI`) y sin `DISPLAY`/
   `WAYLAND_DISPLAY` no se intenta nada, así los smokes de
   `.github/workflows/packaging.yml` — que arrancan el binario sin
   pantalla — no cambian de comportamiento. `CATFLIP_NO_BROWSER=1` lo
   desactiva a mano (servidores, sesiones remotas, lanzadores propios).
   La única excepción es el sandbox del Flatpak: el manifiesto no pide
   sockets gráficos, así que `DISPLAY` llega **vacío** aunque haya
   escritorio; ahí el portal OpenURI no necesita esa variable.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

URL = "http://127.0.0.1:5050"
# Flask importa pandas y pyarrow antes de escuchar: en frío puede tardar
# varios segundos. 30 s cubre un disco lento sin dejar el hilo colgado.
ESPERA_MAX = 30.0
INTERVALO = 0.25

# Valores de entorno que significan «no»; el resto (incluido «1») es «sí».
_FALSOS = ("", "0", "false", "no", "off")


def _activo(valor):
    """Lee un booleano de entorno: `CATFLIP_NO_BROWSER=false` no desactiva."""
    return valor is not None and valor.strip().lower() not in _FALSOS


def en_flatpak():
    """¿Corre dentro de un sandbox de Flatpak? (`/.flatpak-info` lo crea él)"""
    return os.path.exists("/.flatpak-info")


def debe_abrir(environ=None, plataforma=None, sandbox=None):
    """¿Tiene sentido intentar abrir un navegador en este entorno?

    `environ`, `plataforma` y `sandbox` se inyectan en los tests; en
    producción salen de `os.environ`, `sys.platform` y `en_flatpak()`.
    """
    env = os.environ if environ is None else environ
    plat = sys.platform if plataforma is None else plataforma
    sandbox = en_flatpak() if sandbox is None else sandbox
    if _activo(env.get("CATFLIP_NO_BROWSER")):
        return False
    # Un runner de CI no tiene navegador: gastar el intento solo ensucia
    # el log del smoke (y en Windows podría abrir un diálogo de error).
    if _activo(env.get("CI")):
        return False
    # Linux sin sesión gráfica (servidor, contenedor, ssh sin -X): no hay
    # navegador al que abrir. En macOS y Windows no hay este concepto.
    if plat.startswith("linux"):
        # El Flatpak es la excepción: el manifiesto no pide --socket=x11 ni
        # --socket=wayland (la app no tiene GUI propia), así que dentro del
        # sandbox DISPLAY y WAYLAND_DISPLAY llegan VACÍOS aunque haya
        # escritorio. El xdg-open del runtime resuelve por el portal
        # OpenURI y la sesión gráfica la pone el host, no el sandbox.
        if sandbox:
            return True
        return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
    return True


def comando(plataforma=None, existe=None, sandbox=None):
    """Comando que abre una URL con el navegador por defecto, o `None`.

    `existe` (por defecto `shutil.which`) y `sandbox` (por defecto
    `en_flatpak()`) se inyectan en los tests.
    """
    plat = sys.platform if plataforma is None else plataforma
    if not plat.startswith("linux"):
        # macOS y Windows: `webbrowser` ya usa `open`/`startfile`.
        return None
    existe = shutil.which if existe is None else existe
    sandbox = en_flatpak() if sandbox is None else sandbox
    # Dentro del sandbox el xdg-open del runtime es el camino bueno:
    # resuelve por el portal OpenURI y no pide permisos extra (comprobado
    # con el bundle 1.6.0: abre el navegador del host). `flatpak-spawn
    # --host` queda de último recurso para runtimes sin xdg-open.
    if existe("xdg-open"):
        return ["xdg-open"]
    if existe("gio"):
        return ["gio", "open"]
    if sandbox and existe("flatpak-spawn"):
        return ["flatpak-spawn", "--host", "xdg-open"]
    return None


def abrir(url=URL, plataforma=None, existe=None, sandbox=None, ejecutar=None):
    """Abre `url` y devuelve si algún mecanismo lo aceptó.

    `ejecutar` (por defecto `subprocess.run` con timeout) se inyecta en los
    tests. Cualquier fallo cae al `webbrowser` de la stdlib y, si tampoco,
    devuelve `False` — nunca propaga la excepción al servidor.
    """
    ejecutar = subprocess.run if ejecutar is None else ejecutar
    cmd = comando(plataforma=plataforma, existe=existe, sandbox=sandbox)
    if cmd is not None:
        try:
            hecho = ejecutar(
                [*cmd, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
            if hecho.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        return bool(webbrowser.open(url))
    except Exception:  # el navegador jamás tumba la app
        return False


def _puerto_responde(url):
    """¿Hay algo escuchando en el host/puerto de `url`?"""
    partes = urllib.parse.urlsplit(url)
    host = partes.hostname or "127.0.0.1"
    puerto = partes.port or (443 if partes.scheme == "https" else 80)
    try:
        with socket.create_connection((host, puerto), timeout=1.0):
            return True
    except OSError:
        return False


def abrir_cuando_responda(
    url=URL,
    espera_max=ESPERA_MAX,
    intervalo=INTERVALO,
    abridor=None,
    listo=None,
):
    """Espera a que el servidor escuche y abre `url` una sola vez.

    `abridor` y `listo` se inyectan en los tests (por defecto `abrir` y el
    sondeo del puerto). Devuelve `False` si el puerto no respondió a tiempo
    o si el navegador no se pudo abrir.
    """
    abridor = abrir if abridor is None else abridor
    listo = _puerto_responde if listo is None else listo
    limite = time.monotonic() + espera_max
    while True:
        if listo(url):
            return bool(abridor(url))
        if time.monotonic() >= limite:
            return False
        time.sleep(intervalo)


def lanzar(url=URL, **kwargs):
    """Arranca el hilo que abre el navegador; `None` si no corresponde.

    Se llama antes de `app.run()`: el hilo espera a que el puerto responda
    y muere con el proceso (daemon).
    """
    if not debe_abrir():
        return None
    hilo = threading.Thread(
        target=abrir_cuando_responda,
        args=(url,),
        kwargs=kwargs,
        name="catflip-navegador",
        daemon=True,
    )
    hilo.start()
    return hilo
