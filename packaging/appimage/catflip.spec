# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para Cat_flip (onedir compartido por AppImage y Flatpak)."""
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
    [os.path.join(os.path.dirname(SPEC), "entry.py")],
    # `openbrowser.py` vive junto a `entry.py`, fuera de ROOT: sin este
    # pathex el import del punto de entrada no se resuelve al congelar.
    pathex=[ROOT, os.path.join(ROOT, "packaging", "appimage")],
    binaries=[],
    datas=datas,
    # app.py entra como dato (runpy lo ejecuta) y como hidden import para que
    # el grafo de dependencias (pandas, pyarrow, flask, premium) se analice.
    # `openbrowser` es el ayudante de `entry.py` que abre el navegador.
    # python_calamine: pandas lo importa en diferido (import_optional_dependency)
    # como motor de lectura de .xls y .ods, así que el análisis estático de
    # PyInstaller no lo ve y el bundle fallaba con "Import python-calamine failed".
    # formats: app.py (dato ejecutado con runpy) hace `import formats` al
    # arrancar; mismo caso, sin el hiddenimport el bundle no lo encuentra.
    hiddenimports=["app", "operations", "premium", "openbrowser", "formats", "python_calamine"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib.tests", "numpy.f2py.tests"],
    noarchive=False,
    optimize=0,
)

# Lo que PyInstaller arrastra por «datos del paquete» y no se usa al ejecutar:
#   * pyarrow publica su carpeta `tests/`, con fixtures .parquet y .orc dentro;
#   * copiar `premium` entero se lleva su `__pycache__` y, si quien construye
#     tiene licencia local, también `premium.key` (una licencia viajando dentro
#     del binario que se distribuye).
# Nada de eso hace falta para leer un Excel ni para servir un tema, y el smoke
# lo rechaza (scripts/auditar_bundle.py). Se quita en el origen, no se avisa.
def _sobra(destino):
    partes = destino.replace("\\", "/").split("/")
    return (
        "__pycache__" in partes
        or "tests" in partes
        or destino.endswith(".pyc")
        or partes[-1] == "premium.key"
    )


a.datas = [dato for dato in a.datas if not _sobra(dato[0])]

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
