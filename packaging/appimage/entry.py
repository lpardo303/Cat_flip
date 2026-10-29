# -*- coding: utf-8 -*-
"""Punto de entrada congelado de Cat_flip para AppImage y Flatpak.

PyInstaller ejecuta esto; el código real (app.py) se inyecta como dato en el
mismo directorio que los recursos (static/, templates/, premium/), de modo que
Flask resuelve sus rutas relativas igual que en desarrollo:

  _internal/
    entry.py      (este archivo, el __main__ congelado)
    app.py        (--add-data app.py:.)
    operations.py, cli.py, premium/, static/, templates/, assets/

`runpy.run_path` con `run_name="__main__"` hace que app.py vea su guard
`if __name__ == "__main__"` como verdadero y arranque el servidor.
"""
import os
import runpy
import sys

if getattr(sys, "frozen", False):
    base = sys._MEIPASS
    # PyInstaller empaqueta libssl pero NINGÚN almacén de CAs: sin esto
    # todo HTTPS (el aviso de versión a api.github.com) falla en silencio
    # en el bundle. `certifi` viaja como dato en ambos specs; solo lo fijamos
    # si el usuario no ha puesto ya su propio SSL_CERT_FILE.
    _ca = os.path.join(base, "certifi", "cacert.pem")
    if os.path.isfile(_ca) and "SSL_CERT_FILE" not in os.environ:
        os.environ["SSL_CERT_FILE"] = _ca
else:
    base = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base)
# Rutas relativas (premium.key, exports) resuelven igual en cualquier sitio.
os.chdir(base)
runpy.run_path(os.path.join(base, "app.py"), run_name="__main__")
