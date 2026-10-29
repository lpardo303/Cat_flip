# -*- coding: utf-8 -*-
"""Conectores reales de Cat_flip (Open Core).

El core MIT nunca toca la red por sí solo: este módulo solo se invoca desde
las rutas ``/connectors/*``, que están gated por licencia premium
(``premium.is_licensed()``). Sin licencia la ruta responde 404 y aquí no se
ejecuta nada.

Drivers: **psycopg v3**, **boto3** y **google-cloud-bigquery** como
dependencias *opcionales* (``requirements-connectors.txt``). Se importan
perezosamente dentro de cada operación, así la app arranca perfectamente
sin ellos y el error que ve el usuario es accionable.

Reglas de seguridad:

* Los identificadores (esquema, tabla, columnas) pasan por
  :func:`quote_ident` — comillas dobles con las internas duplicadas; una
  entrada del usuario **nunca** se interpola en SQL sin comillar.
* Los valores viajan siempre como parámetros ``%s`` de psycopg.
* La contraseña se pasa como kwarg a ``psycopg.connect`` (nunca en un DSN
  concatenado), no se refleja en las respuestas y se enmascara si apareciera
  en el mensaje de una excepción.
"""

import io
import math
import re
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
    # object con solo bools y nulos: pandas tipa [True, None] como object (no
    # como bool), así que sin esta rama la columna saldría como text y los
    # valores se guardarían como «true»/«false» de texto. `infer_dtype` con
    # skipna=True solo dice «boolean» si TODO lo no-nulo es bool: un mixto con
    # cadenas o una columna vacía siguen siendo text.
    if pd.api.types.is_object_dtype(dtype) and pd.api.types.infer_dtype(
        series, skipna=True
    ) == "boolean":
        return "boolean"
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



# ── S3 ──────────────────────────────────────────────────────────────────
# Mismo patrón que Postgres: driver opcional perezoso, parámetros limpios,
# secretos nunca concatenados ni reflejados y claves de objeto sin path
# traversal. El dataset viaja como CSV (UTF-8, sin índice) con `put_object`,
# que en S3 es una operación atómica por objeto.

_REQUIRED_S3 = (("bucket", "bucket"), ("region", "región"))
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")
_MAX_KEY = 1024
_S3_CLIENT_KEYS = ("endpoint_url", "aws_access_key_id", "aws_secret_access_key")


def _load_boto3():
    """Importa el driver de AWS en el momento de usarlo (opcional)."""
    try:
        import boto3
    except ImportError as exc:
        raise ConnectorError(
            "Driver «boto3» no instalado. Ejecuta: "
            "pip install -r requirements-connectors.txt"
        ) from exc
    return boto3


def _s3_mask(message, params):
    """Enmascara las credenciales por si el SDK las reflejara en un error."""
    text = str(message)
    for key in ("aws_secret_access_key", "aws_access_key_id"):
        secret = params.get(key)
        if secret:
            text = text.replace(secret, "***")
    return text


def clean_s3_params(payload):
    """Valida y normaliza los parámetros S3 recibidos del front.

    Obligatorios: `bucket` y `region`. Opcionales: `endpoint_url`
    (compatible MinIO/R2), credenciales explícitas — si viajan vacías no se
    tocan y manda la cadena por defecto de boto3 (variables de entorno,
    perfil o instancia) — y `prefix`, la carpeta lógica del bucket.

    El dict devuelto no es una URL: `bucket` y `region` identifican el
    destino y el resto se pasa tal cual a ``boto3.client``.
    """
    if not isinstance(payload, dict):
        raise ConnectorError("Se espera un objeto JSON con los datos de conexión.")

    params = {}
    for key, label in _REQUIRED_S3:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConnectorError(f"Falta el campo obligatorio «{label}» ({key}).")
        if "\x00" in value:
            raise ConnectorError(f"El campo «{key}» no puede contener caracteres nulos.")
        params[key] = value.strip()

    if not _BUCKET_RE.match(params["bucket"]):
        raise ConnectorError(
            "El nombre de bucket no es válido: de 3 a 63 caracteres, en "
            "minúsculas, dígitos, puntos y guiones, sin empezar ni terminar "
            "en punto o guion."
        )

    endpoint = payload.get("endpoint_url")
    if endpoint not in (None, ""):
        if not isinstance(endpoint, str):
            raise ConnectorError("El endpoint debe ser texto.")
        endpoint = endpoint.strip()
        if not re.match(r"^https?://[^\s/]+$", endpoint):
            raise ConnectorError("El endpoint debe empezar por http:// o https://.")
        params["endpoint_url"] = endpoint

    for key in ("aws_access_key_id", "aws_secret_access_key"):
        value = payload.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise ConnectorError(f"El campo «{key}» debe ser texto.")
        if "\x00" in value:
            raise ConnectorError(f"El campo «{key}» no puede contener caracteres nulos.")
        params[key] = value

    prefix = payload.get("prefix")
    if prefix in (None, ""):
        return params
    if not isinstance(prefix, str):
        raise ConnectorError("El prefijo debe ser texto.")
    if "\x00" in prefix:
        raise ConnectorError("El prefijo no puede contener caracteres nulos.")
    prefix = "/".join(seg for seg in prefix.strip().strip("/").split("/") if seg)
    if ".." in prefix.split("/"):
        raise ConnectorError("El prefijo no puede contener «..».")
    if prefix:
        params["prefix"] = prefix
    return params


def s3_object_key(prefix, filename):
    """Clave final del objeto: `prefijo/archivo.csv` sin traversal ni NUL."""
    if not isinstance(filename, str) or not filename.strip():
        raise ConnectorError("Falta el campo obligatorio «ruta destino» (key).")
    if "\x00" in filename:
        raise ConnectorError("La ruta destino no puede contener caracteres nulos.")
    name = "/".join(
        seg for seg in filename.strip().strip("/").split("/") if seg and seg != "."
    )
    if not name:
        raise ConnectorError("La ruta destino no puede estar vacía.")
    if ".." in name.split("/"):
        raise ConnectorError("La ruta destino no puede contener «..».")
    if len(name) > _MAX_KEY:
        raise ConnectorError(
            f"La ruta destino no puede superar {_MAX_KEY} caracteres."
        )
    prefix = (prefix or "").strip().strip("/")
    return f"{prefix}/{name}" if prefix else name


def _s3_client(params):
    """Cliente S3 con región y kwargs opcionales (endpoint/credenciales)."""
    boto3 = _load_boto3()
    kwargs = {k: params[k] for k in _S3_CLIENT_KEYS if k in params}
    return boto3.client("s3", region_name=params["region"], **kwargs)


def test_s3_connection(params):
    """`head_bucket` contra el bucket: valida credenciales, región y acceso."""
    boto3 = _load_boto3()  # error accionable si falta (y para la versión)
    try:
        client = _s3_client(params)
        client.head_bucket(Bucket=params["bucket"])
    except Exception as exc:
        raise ConnectorError(
            f"No se pudo conectar a S3: {_s3_mask(exc, params)}"
        ) from exc
    return {
        "success": True,
        "bucket": params["bucket"],
        "region": params["region"],
        "driver": f"boto3 {boto3.__version__}",
    }


def export_to_s3(df, params, key, mode="overwrite"):
    """Sube el DataFrame completo como CSV a ``s3://bucket/<key>``.

    * `overwrite` — reemplaza el objeto si ya existe.
    * `fail` — error accionable si la clave ya existe (se comprueba con
      `head_object` antes de subir).

    El CSV se genera en memoria (UTF-8, sin índice) y se sube con
    `put_object`: en S3 la subida de un objeto es atómica, así que un fallo
    no deja medio fichero en el bucket.
    """
    if mode not in ("overwrite", "fail"):
        raise ConnectorError("El modo debe ser «overwrite» o «fail».")
    if df is None or df.shape[1] == 0:
        raise ConnectorError("El dataset no tiene columnas que exportar.")

    names = [str(c) for c in df.columns]
    if len(set(names)) != len(names):
        raise ConnectorError(
            "El dataset tiene nombres de columna duplicados; "
            "renómbralos antes de exportar."
        )

    object_key = s3_object_key(params.get("prefix"), key)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    data = buffer.getvalue().encode("utf-8")

    try:
        client = _s3_client(params)
        if mode == "fail":
            exists = True
            try:
                client.head_object(Bucket=params["bucket"], Key=object_key)
            except Exception:
                exists = False  # 404 u otro error: lo dirá la subida si toca
            if exists:
                raise ConnectorError(
                    f"El objeto «{object_key}» ya existe en el bucket; "
                    "usa el modo «overwrite» o elige otra ruta."
                )
        client.put_object(Bucket=params["bucket"], Key=object_key, Body=data)
    except ConnectorError:
        raise
    except Exception as exc:
        raise ConnectorError(
            f"No se pudo exportar a S3: {_s3_mask(exc, params)}"
        ) from exc

    return {
        "success": True,
        "bucket": params["bucket"],
        "key": object_key,
        "mode": mode,
        "rows": int(df.shape[0]),
        "columns": len(names),
        "bytes": len(data),
    }


# ── BigQuery ────────────────────────────────────────────────────────
# Tercer conector real: mismo contrato que Postgres y S3 — driver
# opcional perezoso, parámetros validados antes de tocar el SDK, credenciales
# de cuenta de servicio nunca reflejadas y destino `dataset.tabla` con cada
# segmento validado (aquí NO se concatena SQL: el SDK recibe la tabla como
# identificador y el `test_connection` solo emite «SELECT 1» literal).

_REQUIRED_BQ = (("project", "proyecto"), ("dataset", "dataset"))
# Identificador de dataset/columna de BigQuery: letras, dígitos y guiones
# bajos, empezando por letra o guion bajo, hasta 1024 caracteres.
_BQ_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
# Campos mínimos de una clave de cuenta de servicio (archivo .json de GCP).
_SA_FIELDS = ("type", "client_email", "private_key")


def _load_bigquery():
    """Importa el SDK de Google en el momento de usarlo (opcional).

    Devuelve ``(bigquery, service_account)``: los dos módulos que necesita
    el conector viven en el mismo paquete `google-cloud-bigquery`.
    """
    try:
        import google.cloud.bigquery as bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        raise ConnectorError(
            "Driver «google-cloud-bigquery» no instalado. Ejecuta: "
            "pip install -r requirements-connectors.txt"
        ) from exc
    return bigquery, service_account


def _bq_mask(message, params):
    """Enmascara la clave privada si un error del SDK la reflejara."""
    text = str(message)
    creds = params.get("credentials")
    if isinstance(creds, dict):
        for key in ("private_key", "private_key_id"):
            secret = creds.get(key)
            if isinstance(secret, str) and secret:
                text = text.replace(secret, "***")
    return text


def clean_bq_params(payload):
    """Valida y normaliza los parámetros de BigQuery recibidos del front.

    Obligatorios: `project` (proyecto de trabajo/facturación) y `dataset`.
    Opcionales: `location` (US/EU/…, por defecto manda la del dataset) y
    `credentials`, el **contenido JSON** de una clave de cuenta de servicio
    — si viaja vacío se usa la cadena por defecto del SDK (Application
    Default Credentials: `GOOGLE_APPLICATION_CREDENTIALS`, `gcloud auth
    application-default login` o la identidad de la instancia).

    El JSON de la cuenta se valida aquí (campos mínimos) y se guarda ya
    parseado: el privado nunca viaja en claro a los mensajes de error.
    """
    if not isinstance(payload, dict):
        raise ConnectorError("Se espera un objeto JSON con los datos de conexión.")

    params = {}
    for key, label in _REQUIRED_BQ:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConnectorError(f"Falta el campo obligatorio «{label}» ({key}).")
        if "\x00" in value:
            raise ConnectorError(f"El campo «{key}» no puede contener caracteres nulos.")
        params[key] = value.strip()

    if not _BQ_FIELD_RE.match(params["dataset"]):
        raise ConnectorError(
            "El dataset no es válido: de 1 a 1024 caracteres, letras, "
            "dígitos y guiones bajos, empezando por letra o guion bajo."
        )

    location = payload.get("location")
    if location not in (None, ""):
        if not isinstance(location, str):
            raise ConnectorError("La ubicación debe ser texto (por ejemplo «EU»).")
        if "\x00" in location:
            raise ConnectorError("La ubicación no puede contener caracteres nulos.")
        params["location"] = location.strip()

    credentials = payload.get("credentials")
    if credentials in (None, ""):
        return params
    if not isinstance(credentials, dict):
        raise ConnectorError(
            "La cuenta de servicio debe ser el objeto JSON de la clave "
            "(pega el contenido del fichero .json)."
        )
    missing = [f for f in _SA_FIELDS if not isinstance(credentials.get(f), str) or not credentials[f].strip()]
    if missing:
        raise ConnectorError(
            "La clave de cuenta de servicio no parece válida: faltan los "
            "campos " + ", ".join(missing) + "."
        )
    for field in _SA_FIELDS:
        if "\x00" in credentials[field]:
            raise ConnectorError("La clave de cuenta de servicio no puede contener caracteres nulos.")
    params["credentials"] = credentials
    return params


def _bq_client(params, bigquery, service_account):
    """Cliente con proyecto (y ubicación) y, si viaja, cuenta de servicio."""
    kwargs = {"project": params["project"]}
    if params.get("location"):
        kwargs["location"] = params["location"]
    creds = params.get("credentials")
    if creds:
        kwargs["credentials"] = service_account.Credentials.from_service_account_info(
            dict(creds)
        )
    return bigquery.Client(**kwargs)


def test_bq_connection(params):
    """`SELECT 1` contra BigQuery: valida proyecto, credenciales y red."""
    bigquery, service_account = _load_bigquery()
    try:
        client = _bq_client(params, bigquery, service_account)
        job = client.query("SELECT 1")
        job.result()
    except Exception as exc:
        raise ConnectorError(
            f"No se pudo conectar a BigQuery: {_bq_mask(exc, params)}"
        ) from exc
    return {
        "success": True,
        "project": params["project"],
        "driver": f"google-cloud-bigquery {bigquery.__version__}",
    }


def export_to_bigquery(df, params, table, mode="replace"):
    """Carga el DataFrame completo en la tabla `<dataset>.<tabla>`.

    * `replace` — `WRITE_TRUNCATE` con `autodetect`: la tabla se crea si no
      existe y, si existe, se reescribe con los datos y el esquema nuevos.
    * `append` — `WRITE_APPEND` a la tabla existente; antes se comprueba con
      `get_table` para devolver un aviso accionable si la tabla no existe.

    El identificador viaja como destino del job (no se interpola en SQL) y
    el trabajo se espera con `job.result()`: si algo falla, la API no deja
    la tabla a medias (el job no se aprueba).
    """
    if mode not in ("replace", "append"):
        raise ConnectorError("El modo debe ser «replace» o «append».")
    if not isinstance(table, str) or not table.strip():
        raise ConnectorError("Falta el campo obligatorio «tabla» (table).")
    table = table.strip()
    if not _BQ_FIELD_RE.match(table):
        raise ConnectorError(
            "La tabla no es válida: de 1 a 1024 caracteres, letras, "
            "dígitos y guiones bajos, empezando por letra o guion bajo."
        )
    if df is None or df.shape[1] == 0:
        raise ConnectorError("El dataset no tiene columnas que exportar.")

    names = [str(c) for c in df.columns]
    if len(set(names)) != len(names):
        raise ConnectorError(
            "El dataset tiene nombres de columna duplicados; "
            "renómbralos antes de exportar."
        )
    invalid = [n for n in names if not _BQ_FIELD_RE.match(n)]
    if invalid:
        shown = ", ".join(repr(n) for n in invalid[:5])
        more = f" (+{len(invalid) - 5})" if len(invalid) > 5 else ""
        raise ConnectorError(
            "BigQuery no admite estos nombres de columna (letras, dígitos y "
            f"guiones bajos, empezando por letra o guion bajo): {shown}{more}. "
            "Renómbralos antes de exportar."
        )

    bigquery, service_account = _load_bigquery()
    destination = f"{params['dataset']}.{table}"
    config = bigquery.LoadJobConfig()
    if mode == "replace":
        config.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE
        config.create_disposition = bigquery.CreateDisposition.CREATE_IF_NEEDED
    else:
        config.write_disposition = bigquery.WriteDisposition.WRITE_APPEND
    config.autodetect = True

    try:
        client = _bq_client(params, bigquery, service_account)
        if mode == "append":
            try:
                client.get_table(destination)
            except Exception:
                raise ConnectorError(
                    f"La tabla «{destination}» no existe en BigQuery; usa el "
                    "modo «replace» para crearla o créala antes de añadir filas."
                )
        job = client.load_table_from_dataframe(df, destination, job_config=config)
        job.result()
    except ConnectorError:
        raise
    except Exception as exc:
        raise ConnectorError(
            f"No se pudo exportar a BigQuery: {_bq_mask(exc, params)}"
        ) from exc

    return {
        "success": True,
        "project": params["project"],
        "dataset": params["dataset"],
        "table": table,
        "mode": mode,
        "rows": int(df.shape[0]),
        "columns": len(names),
    }
