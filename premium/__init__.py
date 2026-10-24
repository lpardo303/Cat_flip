"""Paquete premium de Cat_flip (Open Core).

El core es MIT y nunca se degrada: la licencia solo decide qué sirve
`/premium/status` y `/premium/themes/<id>.css`. Sin licencia no se entrega
ni la lista de temas ni un solo byte de CSS premium.

La licencia se activa con una de estas dos señales (cualquiera sirve):

* Env var ``CATFLIP_PREMIUM_KEY`` con un valor no vacío.
* Fichero ``premium.key`` junto a este módulo, con contenido no vacío.

El CSS se lee SOLO tras validar el id contra el manifiesto, así que la
ruta del fichero sale del manifiesto y nunca del usuario (sin traversal).
"""
import os
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_KEY_FILE = _DIR / "premium.key"

# Manifiesto de features premium. `id` es el valor de `data-theme` que el
# front aplica al elegir el tema; `file` es relativo a este paquete.
# `mode` declara la familia del tema (light/dark) para que el selector de
# tema agrupe en el servidor y el front no tenga que adivinarlo.
THEMES = [
    {"id": "aurora", "name": "Aurora", "mode": "light", "file": "themes/aurora.css"},
    {"id": "solar", "name": "Solar", "mode": "light", "file": "themes/solar.css"},
]


def is_licensed() -> bool:
    """True si la instalación tiene licencia premium (env var o fichero)."""
    if os.environ.get("CATFLIP_PREMIUM_KEY", "").strip():
        return True
    try:
        return _KEY_FILE.is_file() and _KEY_FILE.read_text(encoding="utf-8").strip() != ""
    except OSError:
        return False


def theme_manifest():
    """Lista pública de temas: SOLO id, nombre y mode (nunca la ruta interna)."""
    return [{"id": t["id"], "name": t["name"], "mode": t["mode"]} for t in THEMES]


def theme_css(theme_id):
    """CSS del tema `theme_id` o None (sin licencia, id desconocido u error)."""
    if not is_licensed():
        return None
    entry = next((t for t in THEMES if t["id"] == theme_id), None)
    if entry is None:
        return None
    try:
        return (_DIR / entry["file"]).read_text(encoding="utf-8")
    except OSError:
        return None
