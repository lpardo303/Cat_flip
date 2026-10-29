# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para el .exe onefile de Windows.

Mismos datos que el spec de AppImage/Flatpak (`packaging/appimage/`
comparte `entry.py`), pero en un único fichero ejecutable: en Windows no
hay AppDir ni runtime, el usuario descarga `CatFlip-<ver>-x64.exe` y
ejecuta. La salida es `dist/CatFlip.exe`, que `build.sh` renombra a
`dist/windows/CatFlip-<ver>-x64.exe` antes de firmar.
"""
import os

import certifi

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), "..", ".."))

datas = [
    (os.path.join(ROOT, "app.py"), "."),
    (os.path.join(ROOT, "operations.py"), "."),
    (os.path.join(ROOT, "cli.py"), "."),
    # Versión del bundle para /version/check (aviso de versión nueva)
    (os.path.join(ROOT, "package.json"), "."),
    # Almacén de CAs: PyInstaller no empaqueta ninguno y sin él el aviso
    # de versión (HTTPS a api.github.com) falla en los bundles congelados.
    # `entry.py` fija SSL_CERT_FILE a esta ruta al arrancar.
    (certifi.where(), "certifi"),
    (os.path.join(ROOT, "premium"), "premium"),
    (os.path.join(ROOT, "static"), "static"),
    (os.path.join(ROOT, "templates"), "templates"),
    (os.path.join(ROOT, "assets"), "assets"),
]

a = Analysis(
    [os.path.join(ROOT, "packaging", "appimage", "entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    # app.py entra como dato (runpy lo ejecuta) y como hidden import para que
    # el grafo de dependencias (pandas, pyarrow, flask, premium) se analice.
    hiddenimports=["app", "operations", "premium"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib.tests", "numpy.f2py.tests"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    name="CatFlip",
)
