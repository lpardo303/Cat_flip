"""Tests del ayudante que abre el navegador desde los bundles congelados.

Lo que se defiende, en el orden en que importa:

1. **Nunca rompe el servidor**: sin navegador, sin sesión gráfica o con un
   `xdg-open` que falla, se devuelve `False` en silencio.
2. **Nunca abre donde no toca**: CI, `CATFLIP_NO_BROWSER` y Linux sin
   `DISPLAY`/`WAYLAND_DISPLAY` no intentan nada (los smokes de
   `packaging.yml` arrancan el binario sin pantalla).
3. **Espera a que el servidor escuche**: abrir la URL antes de que Flask
   acepte conexiones da un «no se puede conectar» en el navegador.
4. **Un módulo de stdlib**: no se importa nada del proyecto, así que este
   test carga el fichero por ruta (no es un paquete) y no necesita red.
"""
import importlib.util
import socket
import sys
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "packaging" / "appimage" / "openbrowser.py"


def _cargar():
    spec = importlib.util.spec_from_file_location("catflip_openbrowser", RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


openbrowser = _cargar()


# --- 2) Dónde no se abre nada ------------------------------------------------

@pytest.mark.parametrize("valor", ["1", "true", "yes", "si", "sí", "TRUE"])
def test_catflip_no_browser_desactiva(valor):
    env = {"CATFLIP_NO_BROWSER": valor, "DISPLAY": ":0"}
    assert openbrowser.debe_abrir(env, plataforma="linux", sandbox=False) is False


@pytest.mark.parametrize("valor", ["", "0", "false", "no", "off"])
def test_valores_falsos_no_desactivan(valor):
    env = {"CATFLIP_NO_BROWSER": valor, "DISPLAY": ":0"}
    assert openbrowser.debe_abrir(env, plataforma="linux", sandbox=False) is True


def test_ci_no_abre_navegador():
    # GitHub Actions define CI=true; allí no hay navegador que abrir.
    env = {"CI": "true", "DISPLAY": ":0"}
    assert openbrowser.debe_abrir(env, plataforma="linux", sandbox=False) is False


def test_linux_sin_sesion_grafica_no_abre():
    assert openbrowser.debe_abrir({}, plataforma="linux", sandbox=False) is False
    assert openbrowser.debe_abrir(
        {"DISPLAY": ""}, plataforma="linux", sandbox=False
    ) is False


@pytest.mark.parametrize("env", [{"DISPLAY": ":0"}, {"WAYLAND_DISPLAY": "wayland-0"}])
def test_linux_con_sesion_grafica_abre(env):
    assert openbrowser.debe_abrir(env, plataforma="linux", sandbox=False) is True


# El manifiesto no pide --socket=x11 ni --socket=wayland (la app no tiene
# GUI propia), así que dentro del sandbox DISPLAY y WAYLAND_DISPLAY llegan
# vacíos: exigirlos desactivaría el arreglo justo en el Flatpak instalado.
def test_flatpak_abre_aunque_display_llegue_vacio():
    assert openbrowser.debe_abrir({}, plataforma="linux", sandbox=True) is True


def test_flatpak_respeta_el_interruptor_y_la_ci():
    assert openbrowser.debe_abrir(
        {"CATFLIP_NO_BROWSER": "1"}, plataforma="linux", sandbox=True
    ) is False
    assert openbrowser.debe_abrir({"CI": "true"}, plataforma="linux", sandbox=True) is False


@pytest.mark.parametrize("plataforma", ["win32", "darwin"])
def test_windows_y_macos_no_exigen_display(plataforma):
    assert openbrowser.debe_abrir({}, plataforma=plataforma) is True


# --- Elección del comando ----------------------------------------------------

def test_prefiere_xdg_open():
    cmd = openbrowser.comando(
        plataforma="linux", existe=lambda n: n in ("xdg-open", "gio", "flatpak-spawn")
    )
    assert cmd == ["xdg-open"]


def test_sin_xdg_open_usa_gio():
    cmd = openbrowser.comando(
        plataforma="linux", existe=lambda n: n in ("gio", "flatpak-spawn")
    )
    assert cmd == ["gio", "open"]


def test_dentro_del_sandbox_usa_flatpak_spawn_como_ultimo_recurso():
    # Un runtime sin xdg-open ni gio no puede abrir el host sin esto.
    cmd = openbrowser.comando(
        plataforma="linux", existe=lambda n: n == "flatpak-spawn", sandbox=True
    )
    assert cmd == ["flatpak-spawn", "--host", "xdg-open"]


def test_flatpak_spawn_fuera_del_sandbox_no_se_usa():
    cmd = openbrowser.comando(
        plataforma="linux", existe=lambda n: n == "flatpak-spawn", sandbox=False
    )
    assert cmd is None


@pytest.mark.parametrize("plataforma", ["win32", "darwin"])
def test_windows_y_macos_delegan_en_webbrowser(plataforma):
    assert openbrowser.comando(plataforma=plataforma, existe=lambda n: True) is None


# --- abrir(): nunca propaga fallos ------------------------------------------

class _Hecho:
    def __init__(self, returncode):
        self.returncode = returncode


def test_abrir_acepta_el_comando_con_rc_cero(monkeypatch):
    llamadas = []

    def ejecutar(argv, **kwargs):
        llamadas.append((argv, kwargs))
        return _Hecho(0)

    monkeypatch.setattr(openbrowser.webbrowser, "open", _no_llamar)
    assert openbrowser.abrir(
        "http://127.0.0.1:5050",
        plataforma="linux",
        existe=lambda n: n == "xdg-open",
        ejecutar=ejecutar,
    ) is True
    assert llamadas[0][0] == ["xdg-open", "http://127.0.0.1:5050"]


def test_abrir_cae_en_webbrowser_si_el_comando_falla(monkeypatch):
    abiertas = []
    monkeypatch.setattr(
        openbrowser.webbrowser, "open", lambda url: abiertas.append(url) or True
    )
    assert openbrowser.abrir(
        "http://127.0.0.1:5050",
        plataforma="linux",
        existe=lambda n: n == "xdg-open",
        ejecutar=lambda argv, **kwargs: _Hecho(4),
    ) is True
    assert abiertas == ["http://127.0.0.1:5050"]


def test_abrir_devuelve_false_sin_ningun_navegador(monkeypatch):
    monkeypatch.setattr(openbrowser.webbrowser, "open", lambda url: False)
    assert openbrowser.abrir(
        "http://127.0.0.1:5050",
        plataforma="linux",
        existe=lambda n: n == "xdg-open",
        ejecutar=lambda argv, **kwargs: _Hecho(1),
    ) is False


def test_abrir_traga_la_excepcion_del_comando(monkeypatch):
    # Un `xdg-open` que revienta (p. ej. sin DBus) no puede tumbar Flask.
    monkeypatch.setattr(openbrowser.webbrowser, "open", lambda url: True)

    def revienta(argv, **kwargs):
        raise OSError("no hay DBus")

    assert openbrowser.abrir(
        "http://127.0.0.1:5050",
        plataforma="linux",
        existe=lambda n: n == "xdg-open",
        ejecutar=revienta,
    ) is True


def _no_llamar(url):  # pragma: no cover - solo falla si se usa
    raise AssertionError("no debería caer al webbrowser")


# --- 3) Espera a que el puerto responda -------------------------------------

def _escucha():
    """Socket TCP escuchando en un puerto libre (el «servidor» del test)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    return srv, srv.getsockname()[1]


def test_lanzar_no_exige_display_dentro_del_sandbox(monkeypatch):
    # El caso real: Flatpak instalado, sin DISPLAY, y el navegador debe abrirse.
    monkeypatch.delenv("CATFLIP_NO_BROWSER", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(openbrowser, "en_flatpak", lambda: True)
    srv, puerto = _escucha()
    abiertas = []
    try:
        hilo = openbrowser.lanzar(
            f"http://127.0.0.1:{puerto}", abridor=lambda url: abiertas.append(url)
        )
        assert hilo is not None
        hilo.join(10)
    finally:
        srv.close()
    assert abiertas == [f"http://127.0.0.1:{puerto}"]


def test_abre_solo_cuando_el_puerto_responde():
    srv, puerto = _escucha()
    abiertas = []
    try:
        assert openbrowser.abrir_cuando_responda(
            f"http://127.0.0.1:{puerto}",
            espera_max=10.0,
            abridor=lambda url: abiertas.append(url) or True,
        ) is True
    finally:
        srv.close()
    assert abiertas == [f"http://127.0.0.1:{puerto}"]


def test_reintenta_hasta_que_el_servidor_escucha():
    # El sondeo real (con Flask importando pandas) es lo que evita que el
    # navegador abra la URL antes de que el puerto acepte conexiones.
    eventos = []

    def listo(url):
        eventos.append(url)
        return len(eventos) >= 3

    assert openbrowser.abrir_cuando_responda(
        "http://127.0.0.1:5050",
        espera_max=10.0,
        intervalo=0.01,
        abridor=lambda url: True,
        listo=listo,
    ) is True
    assert len(eventos) == 3


def test_devuelve_false_si_el_puerto_nunca_responde():
    llamadas = []
    assert openbrowser.abrir_cuando_responda(
        "http://127.0.0.1:1",
        espera_max=0.05,
        intervalo=0.01,
        abridor=lambda url: llamadas.append(url) or True,
    ) is False
    assert llamadas == []


# --- lanzar(): el hilo que usa entry.py -------------------------------------

def test_lanzar_respeta_la_desactivacion(monkeypatch):
    monkeypatch.setenv("CATFLIP_NO_BROWSER", "1")
    assert openbrowser.lanzar() is None


def test_lanzar_usa_un_hilo_daemon(monkeypatch):
    # Daemon: el hilo esperando el puerto no puede retrasar el cierre.
    srv, puerto = _escucha()
    monkeypatch.delenv("CATFLIP_NO_BROWSER", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("CI", raising=False)
    if not sys.platform.startswith("linux"):  # pragma: no cover
        pytest.skip("el sondeo de DISPLAY solo aplica en Linux")
    abiertas = []
    try:
        hilo = openbrowser.lanzar(
            f"http://127.0.0.1:{puerto}", abridor=lambda url: abiertas.append(url)
        )
        assert hilo is not None and hilo.daemon is True
        # Se le da tiempo al hilo antes de cerrar el socket de prueba.
        hilo.join(10)
    finally:
        srv.close()
    assert abiertas == [f"http://127.0.0.1:{puerto}"]
    assert not hilo.is_alive()
