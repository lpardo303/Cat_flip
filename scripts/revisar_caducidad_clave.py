#!/usr/bin/env python3
"""Falla si la clave de firma publicada caduca pronto (o ya caducó).

Una clave GPG caducada no rompe el build hasta el día que caduca: entonces el
cron semanal se pone en rojo y hay que rotar con prisa, con releases sin
publicar de por medio. Este script lo mira antes: lee la clave pública
versionada (`packaging/gpg/catflip-release.asc`) y avisa `DIAS_AVISO` días antes
de la fecha de caducidad.

Sin fecha de caducidad no dice nada: una clave sin expiración es una decisión,
no un fallo.

Variables de entorno:
    DIAS_AVISO    días de antelación con los que avisar (30 por defecto)
"""
import os
import subprocess
import sys
from datetime import datetime, timezone

RUTA_CLAVE = "packaging/gpg/catflip-release.asc"
RUTA_HUELLA = "packaging/gpg/FINGERPRINT"


def main():
    dias = int(os.environ.get("DIAS_AVISO", "30"))

    if not os.path.exists(RUTA_CLAVE):
        print(f"::error::no existe {RUTA_CLAVE}", file=sys.stderr)
        return 1

    # `--import-options show-only` no toca el keyring: lee el fichero y sale.
    proceso = subprocess.run(
        ["gpg", "--with-colons", "--import-options", "show-only", "--import", RUTA_CLAVE],
        capture_output=True,
        text=True,
    )
    if proceso.returncode != 0:
        print(f"::error::gpg no pudo leer {RUTA_CLAVE}: {proceso.stderr.strip()}",
              file=sys.stderr)
        return 1

    huella = ""
    if os.path.exists(RUTA_HUELLA):
        with open(RUTA_HUELLA, encoding="utf-8") as f:
            huella = f.read().strip().replace(" ", "")

    clave = None
    for linea in proceso.stdout.splitlines():
        campos = linea.split(":")
        if campos[0] == "pub":
            clave = campos
        elif campos[0] == "fpr" and clave is not None and not clave[-1]:
            clave.append(campos[9])  # se guarda al final de la lista
    if clave is None:
        print(f"::error::{RUTA_CLAVE} no contiene ninguna clave pública", file=sys.stderr)
        return 1

    caduca = clave[6].strip()
    nombre = clave[-1] if clave[-1] else huella
    if not caduca:
        print(f"→ la clave {nombre} no caduca: nada que vigilar")
        return 0

    fecha = datetime.fromtimestamp(int(caduca), timezone.utc)
    restante = (fecha - datetime.now(timezone.utc)).days
    print(f"→ la clave {nombre} caduca el {fecha:%Y-%m-%d} (en {restante} días)")

    if restante < 0:
        print(
            f"::error::la clave de firma caducó hace {-restante} días: hay que "
            "rotarla ya (ver «Rotar la clave» en packaging/README.md).",
            file=sys.stderr,
        )
        return 1
    if restante < dias:
        print(
            f"::error::la clave de firma caduca en {restante} días (aviso a los "
            f"{dias}). Rotarla con margen: packaging/README.md, «Rotar la clave».",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
