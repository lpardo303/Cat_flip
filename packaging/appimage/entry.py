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
else:
    base = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base)
# Rutas relativas (premium.key, exports) resuelven igual en cualquier sitio.
os.chdir(base)
runpy.run_path(os.path.join(base, "app.py"), run_name="__main__")
