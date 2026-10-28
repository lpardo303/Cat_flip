"""Tests del aviso de versión nueva (`GET /version/check`).

Cuatro propiedades que defender:

1. **Compara contra `package.json` y solo avisa hacia adelante**: una
   release más nueva que la actual → `update_available`; la misma o más
   vieja → nada. La comparación es numérica por componente (1.10 > 1.9).
2. **Best-effort**: sin red, rate limit o tag ilegible → 200 con
   `checked`/`update_available` en False. El aviso jamás rompe la app.
3. **Cacheado**: 1 h si fue OK, 5 min si falló — sin esto, cada carga de
   la página gastaría cuota del rate limit anónimo de api.github.com.
4. **Ningún test toca la red**: `_fetch_release` se sustituye SIEMPRE
   con monkeypatch (y `_RELEASE_CACHE` arranca en frío por test).
"""
import json
import os

import app as app_module


def fake_release(tag, url="https://github.com/lpardo303/Cat_flip/releases/tag/x"):
    """Payload mínimo con la forma de `releases/latest` de GitHub."""
    return {
        "tag_name": tag,
        "html_url": url,
        "published_at": "2026-10-28T00:00:00Z",
    }


def fresh(monkeypatch, release):
    """Cache en frío + fetch falso. Devuelve el contador de llamadas."""
    calls = {"n": 0}

    def fetch(repo):
        calls["n"] += 1
        return release

    monkeypatch.setattr(
        app_module, "_RELEASE_CACHE", {"at": 0.0, "release": None, "failed": False}
    )
    monkeypatch.setattr(app_module, "_fetch_release", fetch)
    return calls


def check(client, query=""):
    resp = client.get("/version/check" + query)
    assert resp.status_code == 200
    return resp.get_json()


# ── Comparación de versiones ────────────────────────────────────────
def test_aviso_si_la_release_es_mas_nueva(client, monkeypatch):
    fresh(monkeypatch, fake_release("v99.0.1"))
    data = check(client)
    assert data["update_available"] is True
    assert data["checked"] is True
    assert data["latest"] == "v99.0.1"
    assert data["html_url"].startswith("https://github.com/")


def test_sin_aviso_si_la_release_es_la_actual(client, monkeypatch):
    current = app_module.app_version()
    fresh(monkeypatch, fake_release("v" + current))
    data = check(client)
    assert data["update_available"] is False
    assert data["checked"] is True
    assert data["current"] == current


def test_sin_aviso_si_la_release_es_mas_vieja(client, monkeypatch):
    fresh(monkeypatch, fake_release("v0.1.0"))
    assert check(client)["update_available"] is False


def test_comparacion_numerica_no_lexicografica():
    """1.10 es más nuevo que 1.9 (una comparación de strings diría lo contrario)."""
    assert app_module.is_newer("v1.10.0", "1.9.0") is True
    assert app_module.is_newer("v1.9.0", "1.10.0") is False
    assert app_module.is_newer("v1.4", "1.4.0") is False   # mismo valor
    assert app_module.is_newer("v1.4.1", "1.4") is True


def test_tag_ilegible_no_anuncia(client, monkeypatch):
    """Un tag que no es versión («nightly») → checked pero sin aviso."""
    fresh(monkeypatch, fake_release("nightly"))
    data = check(client)
    assert data["checked"] is True
    assert data["update_available"] is False


def test_parse_version_acepta_v_y_basura_final():
    assert app_module.parse_version("v1.3.0") == (1, 3, 0)
    assert app_module.parse_version("1.3.0-rc.1") == (1, 3, 0)
    assert app_module.parse_version("") is None
    assert app_module.parse_version(None) is None
    assert app_module.parse_version("release") is None


# ── Best-effort: el fallo no rompe nada ─────────────────────────────
def test_fallo_de_red_responde_200_sin_aviso(client, monkeypatch):
    fresh(monkeypatch, None)  # _fetch_release devuelve None sin red
    data = check(client)
    assert data == {
        "current": app_module.app_version(),
        "latest": None,
        "html_url": None,
        "published_at": None,
        "update_available": False,
        "checked": False,
    }


def test_sin_package_json_no_rompe(client, monkeypatch):
    """Bundle sin package.json (o JSON roto): current=None, sin aviso."""
    monkeypatch.setattr(app_module, "app_version", lambda: None)
    fresh(monkeypatch, fake_release("v99.0.0"))
    data = check(client)
    assert data["current"] is None
    assert data["update_available"] is False
    assert data["checked"] is True


def test_app_version_lee_el_package_json_del_repo():
    with open(
        os.path.join(os.path.dirname(__file__), "..", "package.json"),
        encoding="utf-8",
    ) as f:
        expected = json.load(f)["version"]
    assert app_module.app_version() == expected


def test_app_version_sin_fichero_devuelve_none(tmp_path, monkeypatch):
    """Bundle roto o ausente: no lanza, devuelve None (y no hay aviso)."""
    monkeypatch.setattr(
        app_module, "__file__", str(tmp_path / "no_existe" / "app.py")
    )
    assert app_module.app_version() is None


def test_app_version_con_json_invalido_devuelve_none(tmp_path, monkeypatch):
    """package.json corrupto: mismo contrato — None sin excepción."""
    (tmp_path / "package.json").write_text("{no es json", encoding="utf-8")
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "app.py"))
    assert app_module.app_version() is None


# ── _fetch_release (urlopen se sustituye, tampoco hay red) ──────────
class FakeResp:
    """Respuesta de urlopen con la forma de contexto que usa el código."""

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


def test_fetch_release_parsea_la_respuesta(monkeypatch):
    monkeypatch.setattr(
        app_module.urllib.request,
        "urlopen",
        lambda req, timeout=None: FakeResp(
            json.dumps({"tag_name": "v9.9.9"}).encode("utf-8")
        ),
    )
    assert app_module._fetch_release("x/y")["tag_name"] == "v9.9.9"


def test_fetch_release_error_de_red_es_none(monkeypatch):
    def boom(req, timeout=None):
        raise app_module.urllib.error.URLError("sin red")

    monkeypatch.setattr(app_module.urllib.request, "urlopen", boom)
    assert app_module._fetch_release("x/y") is None


def test_fetch_release_json_que_no_es_objeto_es_none(monkeypatch):
    """Un 200 con cuerpo inesperado (lista) no debe reventar el parseo."""
    monkeypatch.setattr(
        app_module.urllib.request,
        "urlopen",
        lambda req, timeout=None: FakeResp(b"[]"),
    )
    assert app_module._fetch_release("x/y") is None


# ── Versión descartada (?dismissed=) ─────────────────────────────────
def test_dismissed_igual_a_la_release_suprime_el_aviso(client, monkeypatch):
    """El usuario cerró el aviso de v9.9.9: no debe volver a aparecer."""
    fresh(monkeypatch, fake_release("v9.9.9"))
    data = check(client, "?dismissed=v9.9.9")
    assert data["checked"] is True
    assert data["latest"] == "v9.9.9"      # la release sigue ahí
    assert data["update_available"] is False  # …pero ya no avisa


def test_dismissed_mas_viejo_sigue_avisando(client, monkeypatch):
    """Descartó 1.0 y sale 9.9.9: es otra versión, hay que avisar."""
    fresh(monkeypatch, fake_release("v9.9.9"))
    assert check(client, "?dismissed=v1.0.0")["update_available"] is True


def test_dismissed_mas_nuevo_que_la_release_suprime(client, monkeypatch):
    """Rollback (release 9.9.9, ya se descartó la 99): sin aviso."""
    fresh(monkeypatch, fake_release("v9.9.9"))
    assert check(client, "?dismissed=v99.0.0")["update_available"] is False


def test_dismissed_corrupto_no_calla_los_avisos(client, monkeypatch):
    """Un valor ilegible en localStorage no puede suprimir para siempre."""
    fresh(monkeypatch, fake_release("v9.9.9"))
    assert check(client, "?dismissed=nightly")["update_available"] is True
    assert check(client, "?dismissed=")["update_available"] is True


def test_dismissed_no_toca_el_cache(client, monkeypatch):
    """El descarte se calcula por petición: no contamina la caché de GitHub."""
    calls = fresh(monkeypatch, fake_release("v9.9.9"))
    assert check(client, "?dismissed=v9.9.9")["update_available"] is False
    assert check(client)["update_available"] is True   # sin parámetro
    assert calls["n"] == 1                             # un solo fetch


# ── Cache ───────────────────────────────────────────────────────────
def test_cache_reutiliza_el_resultado(client, monkeypatch):
    calls = fresh(monkeypatch, fake_release("v99.0.0"))
    check(client)
    check(client)
    check(client)
    assert calls["n"] == 1


def test_cache_de_ok_caduca_a_la_hora(client, monkeypatch):
    calls = fresh(monkeypatch, fake_release("v99.0.0"))
    check(client)
    assert calls["n"] == 1
    # Envejece el cache más allá del TTL de éxito → nuevo fetch
    app_module._RELEASE_CACHE["at"] -= app_module._RELEASE_TTL_OK + 1
    check(client)
    assert calls["n"] == 2


def test_fallo_cacheado_se_reintenta_mas_pronto(client, monkeypatch):
    """El fallo se cachea (5 min) pero no durante 1 h: reintentar pronto."""
    calls = fresh(monkeypatch, None)
    check(client)
    check(client)  # dentro del TTL de fallo: sin nuevo intento
    assert calls["n"] == 1
    app_module._RELEASE_CACHE["at"] -= app_module._RELEASE_TTL_ERR + 1
    check(client)
    assert calls["n"] == 2


def test_cache_usa_el_repositorio_configurado(client, monkeypatch):
    seen = {}

    def fetch(repo):
        seen["repo"] = repo
        return fake_release("v1.0.0")

    monkeypatch.setattr(
        app_module, "_RELEASE_CACHE", {"at": 0.0, "release": None, "failed": False}
    )
    monkeypatch.setattr(app_module, "_fetch_release", fetch)
    monkeypatch.setattr(app_module, "_RELEASE_REPO", "ejemplo/otro")
    check(client)
    assert seen["repo"] == "ejemplo/otro"


def test_ttls_de_cache():
    """Acuerdos de rate limit: 1 h con éxito, 5 min con fallo (< 60 req/h)."""
    assert app_module._RELEASE_TTL_OK == 3600
    assert app_module._RELEASE_TTL_ERR == 300
    assert app_module._RELEASE_TTL_ERR < app_module._RELEASE_TTL_OK
