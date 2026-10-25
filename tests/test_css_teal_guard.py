# -*- coding: utf-8 -*-
"""Guardia de diseño: el teal solo puede vivir en dataviz.

Regla del front «Tech Labs / Neobrutalist Minimal» (cierre PR #14):

  - ``static/css/tokens.css`` es el único archivo que define la escala teal.
  - En el resto del CSS, ``var(--teal*)`` solo está permitido en selectores
    dataviz (barras de distribución; heatmap y benchmark consumen los tokens
    desde JS).
  - Ningún hex/rgba de la escala teal fuera de ``tokens.css``.

Si este test falla, un color estructural del front antiguo (teal) volvió al
CSS. Para permitir un nuevo dataviz con teal, añade su selector a
``DATAVIZ_SELECTORS`` de forma deliberada.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS_DIR = ROOT / "static" / "css"
TEMPLATES_DIR = ROOT / "templates"

# Único archivo autorizado a definir la escala teal.
TOKEN_FILES = {"tokens.css"}

# Plantilla de respaldo del front antiguo: teal estructural por diseño.
BACKUP_TEMPLATES = {"index-respaldo.html"}

# Selectores dataviz autorizados a consumir teal (barras de distribución).
DATAVIZ_SELECTORS = {".dist-track", ".dist-fill"}

TEAL_WORD = re.compile(r"teal", re.IGNORECASE)

# Literales de la escala teal de tokens.css + nombres legacy del front viejo.
TEAL_HEX = {
    "#f2faf9", "#cfefef", "#99d4d4", "#66b2b2", "#3f9191", "#1d6262",
    "#175252", "#b8e8e8", "#85cccc", "#57d0d0", "#3db8b8", "#2e9494",
    "#267c7c", "#1e6565", "#237373",
}
TEAL_RGBA = re.compile(
    r"rgba\(\s*(?:29\s*,\s*98\s*,\s*98|61\s*,\s*184\s*,\s*184)", re.IGNORECASE
)

# At-rules que anidan reglas (se recorre su interior) vs. las que se ignoran
# (keyframes, font-face, import: su interior no son selectores de estilo).
NESTED_AT = ("@media", "@supports", "@container", "@layer")


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def iter_rules(text):
    """Aplana el CSS en pares (selector, cuerpo), recursando en @media/etc."""
    text = strip_comments(text)
    pos, n = 0, len(text)
    while True:
        brace = text.find("{", pos)
        if brace == -1:
            return
        raw = text[pos:brace]
        # Declaraciones sueltas (@import ...;) no abren bloque.
        if ";" in raw:
            raw = raw.rsplit(";", 1)[1]
        selector = raw.strip()
        depth, i = 1, brace + 1
        while i < n and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[brace + 1:i - 1]
        if selector.startswith(NESTED_AT):
            for rule in iter_rules(body):
                yield rule
        elif selector and not selector.startswith("@"):
            yield selector, body
        pos = i


def css_sources():
    """(ruta, css) de todos los estilos vivientes: hojas CSS + <style> HTML."""
    for path in sorted(CSS_DIR.glob("*.css")):
        yield path, path.read_text(encoding="utf-8")
    for path in sorted(TEMPLATES_DIR.glob("*.html")):
        if path.name in BACKUP_TEMPLATES:
            continue
        html = path.read_text(encoding="utf-8")
        for block in re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.I | re.S):
            yield path, block


def _live_sources():
    return [(p, c) for p, c in css_sources() if p.name not in TOKEN_FILES]


def test_teal_solo_en_dataviz():
    """Ningún uso de teal fuera de selectores dataviz permitidos."""
    violaciones = []
    for path, css in _live_sources():
        rel = path.relative_to(ROOT)
        for selector, body in iter_rules(css):
            if not TEAL_WORD.search(selector) and not TEAL_WORD.search(body):
                continue
            partes = [s.strip() for s in selector.split(",")]
            if all(p in DATAVIZ_SELECTORS for p in partes):
                continue
            violaciones.append("%s :: %s" % (rel, " ".join(selector.split())[:90]))
    assert not violaciones, (
        "Teal estructural fuera de dataviz (solo se permite en "
        "%s):\n  %s" % (sorted(DATAVIZ_SELECTORS), "\n  ".join(violaciones))
    )


def test_teal_hex_fuera_de_tokens():
    """Ningún literal hex/rgba teal fuera de tokens.css."""
    violaciones = []
    for path, css in _live_sources():
        rel = path.relative_to(ROOT)
        clean = strip_comments(css)
        low = clean.lower()
        for hx in sorted(TEAL_HEX):
            if hx in low:
                violaciones.append("%s :: %s" % (rel, hx))
        if TEAL_RGBA.search(clean):
            violaciones.append("%s :: rgba teal" % rel)
    assert not violaciones, (
        "Literales teal hardcodeados (mueve los colores a tokens.css y usa "
        "los tokens):\n  %s" % "\n  ".join(violaciones)
    )


def test_tokens_define_escala_teal():
    """Defensa de la otra dirección: tokens.css sigue definiendo la escala."""
    tokens = (CSS_DIR / "tokens.css").read_text(encoding="utf-8")
    clean = strip_comments(tokens)
    for nombre in ("--teal-500", "--teal-bg", "--teal-bd"):
        assert re.search(re.escape(nombre) + r"\s*:", clean), (
            "tokens.css perdió la definición de %s" % nombre
        )
