# -*- coding: utf-8 -*-
"""Conectores reales de Cat_flip (Open Core).

El core MIT nunca toca la red por sí solo: este módulo solo se invoca desde
las rutas ``/connectors/*``, que están gated por licencia premium
(``premium.is_licensed()``). Sin licencia la ruta responde 404 y aquí no se
ejecuta nada.

Driver: **psycopg v3** como dependencia *opcional*
(``requirements-connectors.txt``). Se importa perezosamente dentro de cada
operación, así la app arranca perfectamente sin él y el error que ve el
usuario es accionable.

Reglas de seguridad:

* Los identificadores (esquema, tabla, columnas) pasan por
  :func:`quote_ident` — comillas dobles con las internas duplicadas; una
  entrada del usuario **nunca** se interpola en SQL sin comillar.
* Los valores viajan siempre como parámetros ``%s`` de psycopg.
* La contraseña se pasa como kwarg a ``psycopg.connect`` (nunca en un DSN
  concatenado), no se refleja en las respuestas y se enmascara si apareciera
  en el mensaje de una excepción.
"""

import math
from itertools import islice

import pandas as pd

# Campos obligatorios: (clave del JSON, etiqueta para el mensaje de error)
_REQUIRED_CONN = (
    ("host", "host"),
    ("dbname", "base de datos"),
    ("user", "usuario"),
)
_DEFAULT_PORT = 5432
_MAX_IDENT = 63  # límite de identificador en Postgres
_BATCH = 1000


class ConnectorError(Exception):
    """Error accionable del conector → la ruta responde con su `status` (400)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _load_psycopg():
    """Importa el driver en el momento de usarlo (dependencia opcional)."""
    try:
        import psycopg
    except ImportError as exc:
        raise ConnectorError(
            "Driver «psycopg» no instalado. Ejecuta: "
            "pip install -r requirements-connectors.txt"
        ) from exc
    return psycopg


def _mask(message, password=None):
    """Por si una excepción del driver llegara a reflejar la contraseña."""
    if password:
        return str(message).replace(password, "***")
    return str(message)


def clean_conn_params(payload):
    """Valida y normaliza los parámetros de conexión recibidos del front.

    Devuelve los kwargs exactos que acepta ``psycopg.connect``: la contraseña
    nunca se concatena en un DSN y un campo vacío no viaja (el entorno/`.pgpass`
    del usuario puede estar haciéndose cargo).
    """
    if not isinstance(payload, dict):
        raise ConnectorError("Se espera un objeto JSON con los datos de conexión.")

    params = {}
    for key, label in _REQUIRED_CONN:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConnectorError(f"Falta el campo obligatorio «{label}» ({key}).")
        if "\x00" in value:
            raise ConnectorError(f"El campo «{key}» no puede contener caracteres nulos.")
        params[key] = value.strip()

    port = payload.get("port")
    if port in (None, ""):
        port = _DEFAULT_PORT
    if isinstance(port, str) and port.strip().isdigit():
        port = int(port.strip())
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConnectorError("El puerto debe ser un número entre 1 y 65535.")
    params["port"] = port

    password = payload.get("password")
    if password in (None, ""):
        return params
    if not isinstance(password, str):
        raise ConnectorError("La contraseña debe ser texto.")
    if "\x00" in password:
        raise ConnectorError("La contraseña no puede contener caracteres nulos.")
    params["password"] = password
    return params


def quote_ident(name):
    """Identificador SQL de Postgres entre comillas dobles.

    Duplica las comillas internas y rechaza lo que Postgres no acepta (vacío,
    NUL, más de 63 caracteres) — con esto ninguna entrada del usuario puede
    romper la sentencia ni salir del identificador.
    """
    if not isinstance(name, str) or not name.strip():
        raise ConnectorError("El nombre de tabla o columna no puede estar vacío.")
    if "\x00" in name:
        raise ConnectorError("Los nombres no pueden contener caracteres nulos.")
    if len(name) > _MAX_IDENT:
        raise ConnectorError(
            f"Los nombres de Postgres admiten como máximo {_MAX_IDENT} caracteres."
        )
    return '"' + name.replace('"', '""') + '"'


def qualified_name(table, schema="public"):
    """`schema.table` comillado (el esquema por defecto es `public`)."""
    return f"{quote_ident(schema or 'public')}.{quote_ident(table)}"


def pg_type_for(series):
    """Tipo Postgres para el dtype de pandas de `series` (DDL de replace)."""
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "bigint"
    if pd.api.types.is_float_dtype(dtype):
        return "double precision"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        tz = getattr(dtype, "tz", None)
        return "timestamptz" if tz is not None else "timestamp"
    # object (str, fechas como texto desde CSV), string de pandas 3, categorías…
    return "text"


def _py_value(value):
    """Valor de celda apto para psycopg: nulos reales y scalars de numpy → Python."""
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, float):  # cubre np.float64 (subclase de float)
        return None if math.isnan(value) else value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, (bool, int, str)):
        return value
    item = getattr(value, "item", None)  # np.int64, np.bool_, datetime.date…
    if callable(item):
        try:
            return _py_value(item())
        except Exception:  # pragma: no cover - defensa ante tipos exóticos
            return value
    return value


def row_batches(df, size=_BATCH):
    """Genera lotes de tuplas Python para `executemany` (sin materializar el df)."""
    it = df.itertuples(index=False, name=None)
    while True:
        batch = list(islice(it, size))
        if not batch:
            return
        yield [tuple(_py_value(v) for v in row) for row in batch]


def test_connection(params):
    """`SELECT version()` contra el servidor: valida credenciales y red."""
    psycopg = _load_psycopg()
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                row = cur.fetchone()
                version = str(row[0]) if row else ""
    except Exception as exc:
        raise ConnectorError(
            f"No se pudo conectar a Postgres: {_mask(exc, params.get('password'))}"
        ) from exc
    return {"success": True, "version": version, "driver": f"psycopg {psycopg.__version__}"}


def export_to_postgres(df, params, table, schema="public", mode="replace"):
    """Escribe el DataFrame completo en `schema.table` y devuelve el resumen.

    * `replace` — DROP TABLE IF EXISTS + CREATE con tipos derivados de los
      dtypes de pandas; transacción única, así un fallo no deja la tabla
      a medias.
    * `append` — inserta en la tabla existente (si no existe, el propio
      servidor lo dice y el mensaje se devuelve tal cual al front).

    `psycopg.connect(**params)` como contexto **confirma la transacción al
    salir sin excepción** y la revierte si algo truena.
    """
    if mode not in ("replace", "append"):
        raise ConnectorError("El modo debe ser «replace» o «append».")
    if df is None or df.shape[1] == 0:
        raise ConnectorError("El dataset no tiene columnas que exportar.")

    names = [str(c) for c in df.columns]
    if len(set(names)) != len(names):
        raise ConnectorError(
            "El dataset tiene nombres de columna duplicados; renómbralos antes de exportar."
        )

    psycopg = _load_psycopg()
    target = qualified_name(table, schema)
    col_sql = ", ".join(quote_ident(n) for n in names)
    types = [pg_type_for(df.iloc[:, i]) for i in range(df.shape[1])]
    placeholders = ", ".join(["%s"] * len(names))
    insert_sql = f"INSERT INTO {target} ({col_sql}) VALUES ({placeholders})"

    rows = 0
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                if mode == "replace":
                    cur.execute(f"DROP TABLE IF EXISTS {target};")
                    ddl = ", ".join(
                        f"{quote_ident(n)} {t}" for n, t in zip(names, types)
                    )
                    cur.execute(f"CREATE TABLE {target} ({ddl});")
                for batch in row_batches(df):
                    cur.executemany(insert_sql, batch)
                    rows += len(batch)
    except Exception as exc:
        raise ConnectorError(
            f"No se pudo exportar a Postgres: {_mask(exc, params.get('password'))}"
        ) from exc

    return {
        "success": True,
        "schema": schema or "public",
        "table": table,
        "mode": mode,
        "rows": rows,
        "columns": len(names),
    }
