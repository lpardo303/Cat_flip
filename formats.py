"""Cat_flip — formatos de entrada en una sola fuente de verdad.

Motivo: la lista de formatos estaba escrita a mano en nueve sitios (los
`accept=` de la plantilla, las validaciones del front, las tuplas del backend
y el CLI). Eso ya causó dos desincronizaciones reales: TSV se leía en todo el
backend pero faltaba en el estado vacío, y `.xls` se anunciaba en seis sitios
sin poder leerse. Ahora todo deriva de aquí.

Sin dependencias: lo importan app.py (también dentro del bundle, vía
`hiddenimports`), cli.py y la plantilla, que recibe el módulo como contexto
Jinja.
"""

# Extensión → nombre visible. El orden de este dict manda en todos los textos.
LABELS = {
    ".csv": "CSV",
    ".tsv": "TSV",
    ".xlsx": "XLSX",
    ".xls": "XLS",
    ".xlsb": "XLSB",
    ".ods": "ODS",
    ".parquet": "Parquet",
}

READ_EXTS = tuple(LABELS)
# Texto plano: separador y codificación se autodetectan al leer
TEXT_EXTS = (".csv", ".tsv")
# Los que tienen hojas → el front ofrece selector de hoja
EXCEL_EXTS = (".xlsx", ".xls", ".xlsb", ".ods")


def _join(items):
    """Une con comas y una «o» final: «a, b o c»."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " o " + items[-1]


def _labels(exts=READ_EXTS):
    return [LABELS[e] for e in exts]


def read_accept(exts=READ_EXTS):
    """Valor de `accept=` para un `<input type="file">`."""
    return ",".join(exts)


def read_plain(exts=READ_EXTS):
    """«CSV, TSV, XLSX, XLS, ODS o Parquet» — mensajes de error y JS."""
    return _join(_labels(exts))


def read_html(exts=READ_EXTS):
    """Como read_plain pero con <strong>, para el estado vacío."""
    return _join(f"<strong>{name}</strong>" for name in _labels(exts))


def read_dots(exts=READ_EXTS):
    """«.CSV · .TSV · …» — el hint de los dropzones."""
    return " · ".join("." + LABELS[e].upper() for e in exts)


def read_js():
    """Payload de window.CATFLIP_FORMATS: el front no repite la lista."""
    return {
        "accept": read_accept(),
        "exts": list(READ_EXTS),
        "sheets": list(EXCEL_EXTS),
        "plain": read_plain(),
    }


def is_readable(filename):
    """¿El nombre de archivo anuncia un formato de entrada soportado?"""
    return (filename or "").lower().endswith(READ_EXTS)


def has_sheets(filename):
    """¿El formato tiene hojas (Excel/ODS) y merece selector?"""
    return (filename or "").lower().endswith(EXCEL_EXTS)
