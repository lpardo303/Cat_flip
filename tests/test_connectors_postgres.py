# -*- coding: utf-8 -*-
"""Tests del conector real de Postgres (Open Core).

Tres propiedades que defender:

1. **Gating en el servidor**: sin licencia `/connectors/postgres/*`
   responde 404 y `/premium/status` ni siquiera anuncia el conector — el
   gating no vive en el front.
2. **Ninguna entrada del usuario toca el SQL sin comillar**: los
   identificadores pasan por ``quote_ident`` (comillas dobles duplicadas)
   y los valores viajan como parámetros ``%s`` de psycopg.
3. **Driver opcional**: sin ``psycopg`` instalado la app sigue viva y el
   error es accionable (la CI instala solo requirements.txt y
   requirements-dev.txt).

La conexión se ejercita con un driver FALSO (monkeypatch de
``connectors._load_psycopg``) que graba sentencias y parámetros: así estos
tests no necesitan un Postgres real ni instalar el driver.
"""

import sys

import numpy as np
import pandas as pd
import pytest

import app as app_module
import connectors
from connectors import ConnectorError, clean_conn_params, pg_type_for, quote_ident


# ── Driver falso (grabador de sentencias) ─────────────────────────────
class FakeCursor:
    def __init__(self, log):
        self.log = log
        self._rows = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append(("execute", sql))
        self._rows = (
            [("PostgreSQL 16.2 on x86_64 compiled by gcc",)]
            if "version()" in sql
            else None
        )

    def executemany(self, sql, seq):
        rows = [tuple(r) for r in seq]
        self.log.append(("executemany", sql, rows))

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(self, log, kwargs):
        self.log = log
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Réplica de psycopg: al salir SIN excepción se confirma la
        # transacción; con excepción se revierte (nada grabado).
        if exc_type is None:
            self.log.append(("commit",))
        return False

    def cursor(self):
        return FakeCursor(self.log)


class FakePsycopg:
    """Sustituto mínimo de `psycopg` con la misma superficie que usamos."""

    __version__ = "3.3.6-fake"

    def __init__(self, log, fail=None):
        self.log = log
        self.fail = fail  # mensaje de error a simular al conectar

    def connect(self, **kwargs):
        self.log.append(("connect", kwargs))
        if self.fail:
            raise RuntimeError(self.fail)
        return FakeConn(self.log, kwargs)


@pytest.fixture()
def licensed(monkeypatch):
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")


@pytest.fixture()
def fake_pg(monkeypatch):
    """Driver falso cargable por `connectors._load_psycopg` (devuelve su log)."""
    log = []

    def loader():
        return FakePsycopg(log)

    monkeypatch.setattr(connectors, "_load_psycopg", loader)
    return log


# ── 1. Gating premium (servidor, no front) ────────────────────────────
def test_rutas_postgres_sin_licencia_devuelven_404(client, monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    for path in ("/connectors/postgres/test", "/connectors/postgres/export"):
        resp = client.post(path, json={"host": "h", "dbname": "d", "user": "u"})
        assert resp.status_code == 404, path
        assert "licencia" in resp.get_json()["error"].lower()


def test_status_sin_licencia_no_anuncia_el_conector(client, monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    data = client.get("/premium/status").get_json()
    assert data["connectors"] == []


def test_status_con_licencia_anuncia_postgres(client, licensed):
    data = client.get("/premium/status").get_json()
    assert data["connectors"] == ["postgres", "s3", "bigquery"]


def test_export_sin_datos_responde_400(client, licensed, fake_pg):
    resp = client.post(
        "/connectors/postgres/export",
        json={"host": "h", "dbname": "d", "user": "u", "table": "t"},
    )
    assert resp.status_code == 400
    assert "datos" in resp.get_json()["error"].lower()


# ── 2. Validación de la entrada (400 accionables) ─────────────────────
def test_faltan_campos_obligatorios(client, licensed, fake_pg):
    resp = client.post("/connectors/postgres/test", json={"host": "localhost"})
    assert resp.status_code == 400
    assert "base de datos" in resp.get_json()["error"]


@pytest.mark.parametrize("bad_port", ["no-numero", 0, 70000, True, 3.5])
def test_puerto_invalido(licensed, fake_pg, bad_port):
    with pytest.raises(ConnectorError):
        clean_conn_params(
            {"host": "h", "dbname": "d", "user": "u", "port": bad_port}
        )


def test_tabla_obligatoria_en_export(client, licensed, fake_pg, monkeypatch):
    app_module.current_df = pd.DataFrame({"a": [1]})
    resp = client.post(
        "/connectors/postgres/export",
        json={"host": "h", "dbname": "d", "user": "u", "table": "   "},
    )
    assert resp.status_code == 400
    assert "tabla" in resp.get_json()["error"].lower()


def test_modo_invalido_rechazado_antes_de_conectar(client, licensed, fake_pg):
    app_module.current_df = pd.DataFrame({"a": [1]})
    resp = client.post(
        "/connectors/postgres/export",
        json={"host": "h", "dbname": "d", "user": "u", "table": "t", "mode": "borrar"},
    )
    assert resp.status_code == 400
    assert "replace" in resp.get_json()["error"]
    assert not [e for e in fake_pg if e[0] == "connect"]  # nunca conectó


def test_columnas_duplicadas_rechazadas(client, licensed, fake_pg):
    df = pd.DataFrame([[1, 2]])
    df.columns = ["col", "col"]
    app_module.current_df = df
    resp = client.post(
        "/connectors/postgres/export",
        json={"host": "h", "dbname": "d", "user": "u", "table": "t"},
    )
    assert resp.status_code == 400
    assert "duplicados" in resp.get_json()["error"]


# ── 3. Driver opcional (CI sin requirements-connectors.txt) ───────────
def test_driver_ausente_da_error_accionable(client, licensed, monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)  # ← import falla
    resp = client.post(
        "/connectors/postgres/test",
        json={"host": "h", "dbname": "d", "user": "u"},
    )
    assert resp.status_code == 400
    assert "requirements-connectors.txt" in resp.get_json()["error"]


def test_driver_ausente_también_en_export(client, licensed, monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)
    app_module.current_df = pd.DataFrame({"a": [1]})
    resp = client.post(
        "/connectors/postgres/export",
        json={"host": "h", "dbname": "d", "user": "u", "table": "t"},
    )
    assert resp.status_code == 400
    assert "psycopg" in resp.get_json()["error"]


# ── 4. Unidades de connectors.py ──────────────────────────────────────
def test_quote_ident_duplica_comillas_internas():
    assert quote_ident("mi tabla") == '"mi tabla"'
    assert quote_ident('mi"tabla') == '"mi""tabla"'
    assert quote_ident('"; drop table x; --') == '"""; drop table x; --"'


@pytest.mark.parametrize("bad", ["", "   ", None, 42, "a\x00b", "x" * 64])
def test_quote_ident_rechaza_entradas_invalidas(bad):
    with pytest.raises(ConnectorError):
        quote_ident(bad)


def test_clean_conn_params_normaliza():
    params = clean_conn_params(
        {"host": "  localhost ", "dbname": "db", "user": "u", "port": "5433"}
    )
    assert params == {
        "host": "localhost",
        "dbname": "db",
        "user": "u",
        "port": 5433,
    }  # puerto por defecto cuando no llega; contraseña ausente no viaja


def test_clean_conn_params_puerto_por_defecto_y_password():
    params = clean_conn_params(
        {"host": "h", "dbname": "d", "user": "u", "password": "secreta"}
    )
    assert params["port"] == 5432
    assert params["password"] == "secreta"


def test_clean_conn_params_rechaza_nul():
    with pytest.raises(ConnectorError):
        clean_conn_params({"host": "h\x00", "dbname": "d", "user": "u"})


def test_clean_conn_params_rechaza_payload_no_objeto():
    with pytest.raises(ConnectorError, match="objeto JSON"):
        clean_conn_params("host=localhost")


def test_clean_conn_params_rechaza_password_no_texto():
    base = {"host": "h", "dbname": "d", "user": "u"}
    with pytest.raises(ConnectorError, match="texto"):
        clean_conn_params({**base, "password": 1234})
    with pytest.raises(ConnectorError, match="nulos"):
        clean_conn_params({**base, "password": "a\x00b"})


def test_py_value_con_tipo_exotico_se_queda_igual():
    import datetime

    fecha = datetime.date(2024, 1, 1)  # psycopg la adapta nativamente
    assert connectors._py_value(fecha) is fecha


def test_export_dataset_sin_columnas(client, licensed, fake_pg):
    app_module.current_df = pd.DataFrame()  # 0 columnas
    resp = client.post(
        "/connectors/postgres/export",
        json={"host": "h", "dbname": "d", "user": "u", "table": "t"},
    )
    assert resp.status_code == 400
    assert "columnas" in resp.get_json()["error"]
    assert not [e for e in fake_pg if e[0] == "connect"]


def test_load_psycopg_real_si_esta_instalado():
    """Con el driver presente, `_load_psycopg` lo importa de verdad.

    La CI no instala `requirements-connectors.txt` → salta ahí y corre en
    local/desarrollo, donde sí está el driver.
    """
    pytest.importorskip("psycopg")
    assert connectors._load_psycopg().__name__ == "psycopg"


def test_pg_type_for_mapea_dtypes():
    tz = pd.Series(pd.to_datetime(["2024-01-01"])).dt.tz_localize("Europe/Madrid")
    df = pd.DataFrame(
        {
            "flag": pd.Series([True, False]),
            "entero": pd.Series([1, 2], dtype="int64"),
            "decimal": pd.Series([1.5, 2.5]),
            "fecha": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "texto": pd.Series(["a", "b"], dtype="str"),
        }
    )
    assert [pg_type_for(df[c]) for c in df.columns] == [
        "boolean",
        "bigint",
        "double precision",
        "timestamp",
        "text",
    ]
    assert pg_type_for(pd.Series(tz)) == "timestamptz"


def test_row_batches_convierte_nulos_y_numpy():
    df = pd.DataFrame(
        {
            "entero": pd.Series([1, 2, 3], dtype="int64"),
            "f": [1.5, float("nan"), 3.5],
            "d": pd.to_datetime(["2024-01-01", None, "2024-01-03"]),
        }
    )
    batches = list(connectors.row_batches(df, size=2))
    assert [len(b) for b in batches] == [2, 1]
    first = batches[0][0]
    assert first == (1, 1.5, pd.Timestamp("2024-01-01").to_pydatetime())
    assert type(first[0]) is int  # numpy.int64 → int de Python
    nan_row = batches[0][1]
    assert nan_row[1] is None and nan_row[2] is None  # NaN y NaT → None
    assert batches[1][0][1] == 3.5


def test_py_value_convierte_scalars_de_numpy():
    assert connectors._py_value(np.int64(7)) == 7
    assert type(connectors._py_value(np.int64(7))) is int
    assert connectors._py_value(np.float64(2.5)) == 2.5
    assert connectors._py_value(np.bool_(True)) is True
    assert connectors._py_value(np.float64("nan")) is None


# ── 5. Exportación con driver falso ───────────────────────────────────
def _payload(**extra):
    base = {
        "host": "db.local",
        "dbname": "analitica",
        "user": "etl",
        "password": "secreta-123",
        "table": "empleados",
    }
    base.update(extra)
    return base


def test_export_replace_crea_la_tabla_y_escribe_todo(client, licensed, fake_pg):
    app_module.current_df = pd.DataFrame(
        {"nombre": ["Ana", "Luis"], "edad": [30, 25], "activo": [True, False]}
    )
    resp = client.post("/connectors/postgres/export", json=_payload())
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data == {
        "success": True,
        "schema": "public",
        "table": "empleados",
        "mode": "replace",
        "rows": 2,
        "columns": 3,
    }

    executed = [e[1] for e in fake_pg if e[0] == "execute"]
    assert 'DROP TABLE IF EXISTS "public"."empleados";' in executed
    ddl = [s for s in executed if s.startswith("CREATE TABLE")][0]
    assert ddl == (
        'CREATE TABLE "public"."empleados" '
        '("nombre" text, "edad" bigint, "activo" boolean);'
    )

    inserts = [e for e in fake_pg if e[0] == "executemany"]
    assert len(inserts) == 1
    sql, rows = inserts[0][1], inserts[0][2]
    # Los valores SIEMPRE son parámetros %s, nunca texto interpolado
    assert sql == (
        'INSERT INTO "public"."empleados" ("nombre", "edad", "activo") '
        "VALUES (%s, %s, %s)"
    )
    assert rows == [("Ana", 30, True), ("Luis", 25, False)]
    assert ("commit",) in fake_pg  # `with conn` confirma al salir sin error

    # La contraseña viaja como kwarg y NUNCA aparece en la respuesta
    connect_kwargs = [e[1] for e in fake_pg if e[0] == "connect"][0]
    assert connect_kwargs["password"] == "secreta-123"
    assert "secreta-123" not in str(data)


def test_export_append_no_reescribe_la_tabla(client, licensed, fake_pg):
    app_module.current_df = pd.DataFrame({"a": [1, 2, 3]})
    resp = client.post(
        "/connectors/postgres/export", json=_payload(mode="append")
    )
    assert resp.status_code == 200
    executed = [e[1] for e in fake_pg if e[0] == "execute"]
    assert executed == []  # sin DROP ni CREATE
    assert resp.get_json()["mode"] == "append"
    assert resp.get_json()["rows"] == 3


def test_export_con_identificador_hostil_queda_comillado(
    client, licensed, fake_pg
):
    app_module.current_df = pd.DataFrame({"a": [1]})
    tabla = 'x"; drop table usuarios; --'
    resp = client.post(
        "/connectors/postgres/export", json=_payload(table=tabla)
    )
    assert resp.status_code == 200
    executed = [e[1] for e in fake_pg if e[0] == "execute"]
    # El nombre hostil entra COMILLADO dentro del propio identificador:
    # no puede cerrar la sentencia ni llegar a ser SQL ejecutable aparte
    assert f'DROP TABLE IF EXISTS "public"."x""; drop table usuarios; --";' in executed
    assert all(";" not in s.split('"')[0] for s in executed)  # nada previo al ident


def test_export_conexion_fallida_enmascara_la_password(
    client, licensed, monkeypatch
):
    log = []
    fake = FakePsycopg(log, fail='password authentication failed for "etl" secreta-123')
    monkeypatch.setattr(connectors, "_load_psycopg", lambda: fake)
    app_module.current_df = pd.DataFrame({"a": [1]})
    resp = client.post("/connectors/postgres/export", json=_payload())
    assert resp.status_code == 400
    error = resp.get_json()["error"]
    assert "secreta-123" not in error
    assert "***" in error
    assert ("commit",) not in log  # fallo → rollback, nada confirmado


def test_export_esquema_personalizado_se_comilla(client, licensed, fake_pg):
    app_module.current_df = pd.DataFrame({"a": [1]})
    resp = client.post(
        "/connectors/postgres/export",
        json=_payload(schema="Datos Sucios"),
    )
    assert resp.status_code == 200
    executed = [e[1] for e in fake_pg if e[0] == "execute"]
    assert 'DROP TABLE IF EXISTS "Datos Sucios"."empleados";' in executed


# ── 6. Prueba de conexión con driver falso ────────────────────────────
def test_test_connection_devuelve_version(client, licensed, fake_pg):
    resp = client.post(
        "/connectors/postgres/test",
        json={"host": "db.local", "dbname": "d", "user": "u"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["version"].startswith("PostgreSQL 16.2")
    assert data["driver"] == "psycopg 3.3.6-fake"
    # Sin contraseña en el payload, no se inyecta el kwarg
    assert "password" not in [e[1] for e in fake_pg if e[0] == "connect"][0]


def test_test_connection_fallida_devuelve_400(client, licensed, monkeypatch):
    log = []
    fake = FakePsycopg(log, fail="connection to server failed: Connection refused")
    monkeypatch.setattr(connectors, "_load_psycopg", lambda: fake)
    resp = client.post(
        "/connectors/postgres/test",
        json={"host": "db.local", "dbname": "d", "user": "u"},
    )
    assert resp.status_code == 400
    assert "No se pudo conectar" in resp.get_json()["error"]
    assert ("commit",) not in log
