# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para Cat_flip (onedir compartido por AppImage y Flatpak)."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), "..", ".."))

datas = [
    (os.path.join(ROOT, "app.py"), "."),
    (os.path.join(ROOT, "operations.py"), "."),
    (os.path.join(ROOT, "cli.py"), "."),
    # Versión del bundle para /version/check (aviso de versión nueva)
    (os.path.join(ROOT, "package.json"), "."),
    (os.path.join(ROOT, "premium"), "premium"),
    (os.path.join(ROOT, "static"), "static"),
    (os.path.join(ROOT, "templates"), "templates"),
    (os.path.join(ROOT, "assets"), "assets"),
]

a = Analysis(
    [os.path.join(os.path.dirname(SPEC), "entry.py")],
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
    [],
    exclude_binaries=True,
    name="CatFlip",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CatFlip",
)
