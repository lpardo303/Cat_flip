"""Tests del gating Open Core: `/premium/status` y `/premium/themes/<id>.css`.

Dos propiedades que hay que defender:

1. **Sin licencia no hay nada que robar**: la lista de temas sale vacía y
   el CSS responde 404 — el gating vive en el servidor, no en el front.
2. **El id nunca toca el filesystem**: `theme_css` valida contra el
   manifiesto antes de leer, así que una ruta hostil (`../LICENSE`) no
   encuentra fichero.

La licencia se inyecta con `monkeypatch` de la env var `CATFLIP_PREMIUM_KEY`
(borra/restaura sola); el fichero `premium.key` se prueba apuntando
`premium._KEY_FILE` a un `tmp_path` para no tocar el repo.
"""
import app as app_module
import premium


def status(client):
    return client.get("/premium/status")


def theme_css(client, theme_id):
    return client.get(f"/premium/themes/{theme_id}.css")


# ── /premium/status ────────────────────────────────────────────────────
def test_status_sin_licencia_es_lista_vacia(client, monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    resp = status(client)
    assert resp.status_code == 200
    assert resp.get_json() == {"licensed": False, "themes": []}


def test_status_con_licencia_expone_manifiesto(client, monkeypatch):
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    resp = status(client)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["licensed"] is True
    ids = [t["id"] for t in data["themes"]]
    assert ids == ["aurora", "solar"]
    # El manifiesto público NUNCA filtra la ruta interna del fichero
    for t in data["themes"]:
        assert set(t) == {"id", "name"}


# ── /premium/themes/<id>.css ───────────────────────────────────────────
def test_css_sin_licencia_responde_404(client, monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    resp = theme_css(client, "aurora")
    assert resp.status_code == 404


def test_css_con_licencia_sirve_el_tema(client, monkeypatch):
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    for theme_id in ("aurora", "solar"):
        resp = theme_css(client, theme_id)
        assert resp.status_code == 200, theme_id
        assert resp.headers["Content-Type"].startswith("text/css")
        body = resp.get_data(as_text=True)
        assert f'[data-theme="{theme_id}"]' in body


def test_css_id_desconocido_responde_404_tambien_licenciado(client, monkeypatch):
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    assert theme_css(client, "no-existe").status_code == 404


def test_css_id_con_traversal_no_encuentra_ficheros(client, monkeypatch):
    """El id hostil no sale del manifiesto → 404, nunca Lee LICENSE."""
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    resp = theme_css(client, "..%2F..%2FLICENSE")
    assert resp.status_code == 404


# ── premium.is_licensed / premium.theme_css (unidad) ───────────────────
def test_is_licencia_env_var(monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    assert premium.is_licensed() is False
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "  ")
    assert premium.is_licensed() is False  # en blanco no cuenta
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "clave")
    assert premium.is_licensed() is True


def test_is_licencia_fichero_premium_key(tmp_path, monkeypatch):
    key_file = tmp_path / "premium.key"
    monkeypatch.setattr(premium, "_KEY_FILE", key_file)
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    assert premium.is_licensed() is False
    key_file.write_text("", encoding="utf-8")
    assert premium.is_licensed() is False  # vacío no cuenta
    key_file.write_text("clave\n", encoding="utf-8")
    assert premium.is_licensed() is True


def test_theme_css_devuelve_none_sin_licencia(monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    assert premium.theme_css("aurora") is None


def test_theme_manifest_no_expone_rutas():
    for entry in premium.theme_manifest():
        assert "file" not in entry
