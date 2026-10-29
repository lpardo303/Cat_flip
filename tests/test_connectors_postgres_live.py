# -*- coding: utf-8 -*-
"""Smoke **real** del conector Postgres contra un servidor de verdad.

Las corridas normales de la CI (y `pytest` en local) lo omiten: solo lo
ejecuta el job `pg-smoke` de ``.github/workflows/ci.yml``, que levanta un
service container ``postgres:16`` y pone ``CATFLIP_PG_SMOKE=1``. Sin ese
entorno no hay servidor y no tiene sentido ni intentarlo.

Lo que cubre es lo que los tests unitarios **no** pueden: el driver de verdad
hablando con un Postgres de verdad — credenciales, DDL derivado de los dtypes,
nulos reales, transacción y rollback. La regresión del boolean con nulos
(``[True, None]`` → ``object``) se comprueba aquí contra
``information_schema``.

Reproducción local::

    podman run -d --name catflip-pg-test -e POSTGRES_USER=catflip \\
      -e POSTGRES_PASSWORD=smoke_pg_2026 -e POSTGRES_DB=catflip_smoke \\
      -p 5432:5432 postgres:16
    CATFLIP_PG_SMOKE=1 pytest tests/test_connectors_postgres_live.py -v
"""

import os

import pandas as pd
import pytest

import connectors as C

pytestmark = pytest.mark.skipif(
    os.environ.get("CATFLIP_PG_SMOKE") != "1",
    reason="smoke real: necesita un Postgres (job pg-smoke de la CI)",
)

_PARAMS = {
    "host": os.environ.get("CATFLIP_PG_HOST", "127.0.0.1"),
    "port": int(os.environ.get("CATFLIP_PG_PORT", "5432")),
    "dbname": os.environ.get("CATFLIP_PG_DB", "catflip_smoke"),
    "user": os.environ.get("CATFLIP_PG_USER", "catflip"),
    "password": os.environ.get("CATFLIP_PG_PASSWORD", "smoke_pg_2026"),
}


def _connect():
    import psycopg  # opcional: solo dentro del smoke, que ya lleva el driver

    return psycopg.connect(**_PARAMS)


def test_test_connection_real():
    info = C.test_connection(C.clean_conn_params(_PARAMS))
    assert info["success"] is True
    assert "PostgreSQL" in info["version"]
    assert info["driver"].startswith("psycopg")


def test_password_equivocada_enmascarada():
    params = C.clean_conn_params({**_PARAMS, "password": "clave_mala_1234"})
    with pytest.raises(C.ConnectorError) as excinfo:
        C.test_connection(params)
    assert "clave_mala_1234" not in str(excinfo.value)


def test_export_replace_append_y_tipos_reales():
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "nombre": ["gato negro", "gato 'naranja'", 'gato "bigote"', None],
            "peso_kg": [4.5, 3.25, None, 5.1],
            # bool con None → dtype object: regresión del fix de pg_type_for
            "adopto": [True, False, True, None],
            "alta": pd.to_datetime(["2026-01-15", "2026-02-01", None, "2026-03-30"]),
        }
    )
    res = C.export_to_postgres(df, _PARAMS, "smoke_gatos", mode="replace")
    assert res == {
        "success": True,
        "schema": "public",
        "table": "smoke_gatos",
        "mode": "replace",
        "rows": 4,
        "columns": 5,
    }

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'smoke_gatos' "
            "ORDER BY ordinal_position"
        )
        assert dict(cur.fetchall()) == {
            "id": "bigint",
            "nombre": "text",
            "peso_kg": "double precision",
            "adopto": "boolean",  # el DDL debe derivar boolean, no text
            "alta": "timestamp without time zone",
        }
        cur.execute(
            'SELECT count(*), count(nombre), count(peso_kg) '
            'FROM public."smoke_gatos"'
        )
        assert cur.fetchone() == (4, 3, 3)  # NULL de verdad en dos columnas
        cur.execute('SELECT adopto FROM public."smoke_gatos" ORDER BY id')
        assert [r[0] for r in cur.fetchall()] == [True, False, True, None]
        cur.execute('SELECT nombre FROM public."smoke_gatos" WHERE id = 2')
        assert cur.fetchone()[0] == "gato 'naranja'"

    res2 = C.export_to_postgres(df.iloc[:2], _PARAMS, "smoke_gatos", mode="append")
    assert res2["rows"] == 2
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT count(*), max(id) FROM public."smoke_gatos"')
        assert cur.fetchone() == (6, 4)  # 4 del replace + 2 del append


def test_rollback_tras_fallo_no_deja_tabla_a_medias():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS public.smoke_rollback")
        cur.execute("CREATE TABLE public.smoke_rollback (id bigint NOT NULL)")
        cur.execute("INSERT INTO public.smoke_rollback VALUES (1)")

    # el INSERT de la 2ª fila viola el NOT NULL → la transacción debe revertirse
    with pytest.raises(C.ConnectorError):
        C.export_to_postgres(
            pd.DataFrame({"id": [7, None]}), _PARAMS, "smoke_rollback", mode="append"
        )

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), min(id) FROM public.smoke_rollback")
        assert cur.fetchone() == (1, 1)
