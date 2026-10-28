# -*- coding: utf-8 -*-
"""Tests del conector real de BigQuery (Open Core).

Tres propiedades que defender:

1. **Gating en el servidor**: sin licencia `/connectors/bigquery/*`
   responde 404 y `/premium/status` no anuncia «bigquery» — el gating no
   vive en el front.
2. **Ninguna entrada hostil llega al SDK**: `project`/`dataset`/`tabla` se
   validan (identificador de BigQuery, sin NUL), la clave de cuenta de
   servicio se exige con sus campos mínimos y la clave privada se
   enmascara si un error del driver la reflejara.
3. **Driver opcional**: sin ``google-cloud-bigquery`` la app sigue viva y
   el error es accionable (la CI instala solo requirements.txt y
   requirements-dev.txt).

El SDK se sustituye con un doble inyectado en ``sys.modules``: estos tests
no tocan red ni necesitan credenciales reales. Las firmas que usa el
módulo (`Client(project=, location=, credentials=)`, `query`,
`load_table_from_dataframe(df, destino, job_config=)`, `LoadJobConfig`,
`WriteDisposition`, `CreateDisposition` y `Credentials.
from_service_account_info`) se validaron contra el SDK real 3.46.2.
"""

import sys
import types

import pandas as pd
import pytest

import app as app_module
import connectors  # noqa: F401  (registro del módulo junto a sus funciones)
from connectors import (
    ConnectorError,
    clean_bq_params,
    export_to_bigquery,
)
# Alias: sin él, pytest coleccionaría `test_bq_connection` como un test.
from connectors import test_bq_connection as bq_probe


# ── Driver falso (doble de google-cloud-bigquery) ─────────────────────
class FakeQueryJob:
    def __init__(self, error=None):
        self.error = error

    def result(self):
        if self.error is not None:
            raise self.error
        return []


class FakeLoadJob:
    def __init__(self, error=None, num_bytes=4096):
        self.error = error
        self.num_bytes = num_bytes

    def result(self):
        if self.error is not None:
            raise self.error
        return self


class FakeBQClient:
    """Doble de `bigquery.Client`: registra llamadas y simula fallos."""

    def __init__(self, query_error=None, load_error=None, table_exists=True):
        self.project = "mi-proyecto-42"
        self.location = None
        self.query_error = query_error
        self.load_error = load_error
        self.table_exists = table_exists
        self.calls = []

    def query(self, sql, **kwargs):
        self.calls.append(("query", sql))
        return FakeQueryJob(self.query_error)

    def get_table(self, destination):
        self.calls.append(("get_table", destination))
        if not self.table_exists:
            raise RuntimeError(f"404 Not Found: Table {destination} was not found")
        return {"table": destination}

    def load_table_from_dataframe(self, dataframe, destination, job_config=None):
        self.calls.append(("load_table_from_dataframe", destination, dataframe))
        self.job_config = job_config
        self.dataframe = dataframe
        return FakeLoadJob(self.load_error)


class FakeLoadJobConfig:
    def __init__(self, **kwargs):
        self.write_disposition = kwargs.get("write_disposition")
        self.create_disposition = kwargs.get("create_disposition")
        self.autodetect = kwargs.get("autodetect")


class FakeCredentials:
    calls = []

    @classmethod
    def from_service_account_info(cls, info, **kwargs):
        cls.calls.append(dict(info))
        return f"creds:{info.get('client_email')}"


class FakeBigQuery:
    """Sustituto mínimo del módulo `google.cloud.bigquery`."""

    __version__ = "0.0-fake"

    def __init__(self, client=None):
        self.fake_client = client or FakeBQClient()
        self.client_calls = []
        self.LoadJobConfig = FakeLoadJobConfig
        self.WriteDisposition = types.SimpleNamespace(
            WRITE_TRUNCATE="WRITE_TRUNCATE", WRITE_APPEND="WRITE_APPEND"
        )
        self.CreateDisposition = types.SimpleNamespace(
            CREATE_IF_NEEDED="CREATE_IF_NEEDED"
        )

    def Client(self, **kwargs):  # noqa: N802  (misma forma que el SDK)
        self.client_calls.append(kwargs)
        return self.fake_client


@pytest.fixture()
def fake_bq(monkeypatch):
    """Inyecta los módulos `google.*` falsos en sys.modules (sin red)."""

    def install(client=None):
        fake = FakeBigQuery(client)
        google = types.ModuleType("google")
        cloud = types.ModuleType("google.cloud")
        oauth2 = types.ModuleType("google.oauth2")
        sa = types.ModuleType("google.oauth2.service_account")
        sa.Credentials = FakeCredentials
        oauth2.service_account = sa
        google.cloud = cloud
        google.oauth2 = oauth2
        monkeypatch.setitem(sys.modules, "google", google)
        monkeypatch.setitem(sys.modules, "google.cloud", cloud)
        monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake)
        monkeypatch.setitem(sys.modules, "google.oauth2", oauth2)
        monkeypatch.setitem(sys.modules, "google.oauth2.service_account", sa)
        FakeCredentials.calls = []
        return fake

    return install


def bq_params(**overrides):
    """Payload crudo de ejemplo — lo que manda el front, antes de limpiar."""
    payload = {
        "project": "mi-proyecto-42",
        "dataset": "analytics",
    }
    payload.update(overrides)
    return payload


def sa_key():
    """Clave de cuenta de servicio de ejemplo (los campos mínimos)."""
    return {
        "type": "service_account",
        "project_id": "mi-proyecto-42",
        "client_email": "etl@mi-proyecto-42.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\nS3CR3T\n-----END-----",
    }


# ── clean_bq_params ───────────────────────────────────────────────────
def test_params_no_dict():
    with pytest.raises(ConnectorError, match="objeto JSON"):
        clean_bq_params(["mi-proyecto-42"])


def test_params_requiere_project_y_dataset():
    with pytest.raises(ConnectorError, match="proyecto"):
        clean_bq_params({"dataset": "analytics"})
    with pytest.raises(ConnectorError, match="dataset"):
        clean_bq_params({"project": "mi-proyecto-42"})
    with pytest.raises(ConnectorError, match="dataset"):
        clean_bq_params({"project": "mi-proyecto-42", "dataset": "   "})


def test_params_rechaza_caracteres_nulos():
    with pytest.raises(ConnectorError, match="nulos"):
        clean_bq_params({"project": "p\x00", "dataset": "analytics"})
    with pytest.raises(ConnectorError, match="nulos"):
        clean_bq_params({"project": "p", "dataset": "analytics\x00"})


def test_params_dataset_con_identificador_invalido():
    for bad in ("mal dataset", "1empieza", "con-guion", "a" * 1025):
        with pytest.raises(ConnectorError, match="dataset no es válido"):
            clean_bq_params({"project": "p", "dataset": bad})


def test_params_dataset_valido_y_strip():
    params = clean_bq_params({"project": "p", "dataset": "  analitica_2026 "})
    assert params["dataset"] == "analitica_2026"
    assert "location" not in params
    assert "credentials" not in params


def test_params_location_opcional():
    assert clean_bq_params(bq_params()) == {
        "project": "mi-proyecto-42",
        "dataset": "analytics",
    }
    assert clean_bq_params(bq_params(location="EU"))["location"] == "EU"
    with pytest.raises(ConnectorError, match="ubicación"):
        clean_bq_params(bq_params(location=42))
    with pytest.raises(ConnectorError, match="nulos"):
        clean_bq_params(bq_params(location="E\x00U"))


def test_params_credentials_vacias_no_viajan():
    for empty in (None, ""):
        assert "credentials" not in clean_bq_params(bq_params(credentials=empty))


def test_params_credentials_no_objeto():
    with pytest.raises(ConnectorError, match="objeto JSON"):
        clean_bq_params(bq_params(credentials="pega el .json"))


def test_params_credentials_faltan_campos():
    with pytest.raises(ConnectorError, match="private_key"):
        clean_bq_params(bq_params(credentials={"type": "service_account"}))


def test_params_credentials_con_nulo():
    key = sa_key()
    key["private_key"] = "clave\x00mala"
    with pytest.raises(ConnectorError, match="nulos"):
        clean_bq_params(bq_params(credentials=key))


def test_params_credentials_valida_se_conserva():
    key = sa_key()
    assert clean_bq_params(bq_params(credentials=key))["credentials"] == key


# ── test_bq_connection ────────────────────────────────────────────────
def test_connection_ok_sin_credenciales_explicitas(fake_bq):
    fake = fake_bq()
    result = bq_probe(bq_params())
    assert result["success"] is True
    assert result["project"] == "mi-proyecto-42"
    assert result["driver"] == "google-cloud-bigquery 0.0-fake"
    assert fake.client_calls == [{"project": "mi-proyecto-42"}]
    assert fake.fake_client.calls == [("query", "SELECT 1")]


def test_connection_con_cuenta_de_servicio_y_location(fake_bq):
    fake = fake_bq()
    bq_probe(bq_params(location="EU", credentials=sa_key()))
    kwargs = fake.client_calls[0]
    assert kwargs["project"] == "mi-proyecto-42"
    assert kwargs["location"] == "EU"
    assert kwargs["credentials"] == "creds:etl@mi-proyecto-42.iam.gserviceaccount.com"
    assert FakeCredentials.calls[0]["client_email"].startswith("etl@")
    # from_service_account_info recibe una copia: el SDK no muta nuestro dict


def test_connection_error_del_sdk_es_accionable(fake_bq):
    fake_bq(FakeBQClient(query_error=RuntimeError("403 Forbidden")))
    with pytest.raises(ConnectorError, match="No se pudo conectar a BigQuery"):
        bq_probe(bq_params())


def test_connection_enmascara_la_clave_privada(fake_bq):
    key = sa_key()
    fake_bq(FakeBQClient(query_error=RuntimeError(f"auth failed with {key['private_key']}")))
    with pytest.raises(ConnectorError) as excinfo:
        bq_probe(bq_params(credentials=key))
    msg = str(excinfo.value)
    assert key["private_key"] not in msg
    assert "***" in msg


def test_connection_sin_driver_error_accionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", None)
    with pytest.raises(ConnectorError, match="requirements-connectors.txt"):
        bq_probe(bq_params())


# ── export_to_bigquery ────────────────────────────────────────────────
def test_export_reemplaza_con_autodetect_y_creación(fake_bq):
    fake = fake_bq()
    df = pd.DataFrame({"nombre": ["Ana"], "saldo": [3200.5]})
    result = export_to_bigquery(df, bq_params(), "empleados_limpios", mode="replace")
    config = fake.fake_client.job_config
    assert config.write_disposition == "WRITE_TRUNCATE"
    assert config.create_disposition == "CREATE_IF_NEEDED"
    assert config.autodetect is True
    kind, destination, sent = fake.fake_client.calls[-1]
    assert (kind, destination) == ("load_table_from_dataframe", "analytics.empleados_limpios")
    assert sent is df
    assert result == {
        "success": True,
        "project": "mi-proyecto-42",
        "dataset": "analytics",
        "table": "empleados_limpios",
        "mode": "replace",
        "rows": 1,
        "columns": 2,
    }


def test_export_append_comprueba_la_tabla(fake_bq):
    fake = fake_bq()
    export_to_bigquery(pd.DataFrame({"a": [1]}), bq_params(), "empleados_limpios", mode="append")
    config = fake.fake_client.job_config
    assert config.write_disposition == "WRITE_APPEND"
    assert config.create_disposition is None  # no toca la creación en append
    assert [c[0] for c in fake.fake_client.calls] == [
        "get_table",
        "load_table_from_dataframe",
    ]


def test_export_append_tabla_ausente_no_carga(fake_bq):
    fake = fake_bq(FakeBQClient(table_exists=False))
    with pytest.raises(ConnectorError, match="no existe"):
        export_to_bigquery(pd.DataFrame({"a": [1]}), bq_params(), "empleados_limpios", mode="append")
    assert [c[0] for c in fake.fake_client.calls] == ["get_table"]


def test_export_modo_invalido_y_tabla_invalida():
    with pytest.raises(ConnectorError, match="replace"):
        export_to_bigquery(pd.DataFrame({"a": [1]}), bq_params(), "x", mode="upsert")
    with pytest.raises(ConnectorError, match="tabla"):
        export_to_bigquery(pd.DataFrame({"a": [1]}), bq_params(), "   ")
    with pytest.raises(ConnectorError, match="tabla no es válida"):
        export_to_bigquery(pd.DataFrame({"a": [1]}), bq_params(), "tabla con espacio")


def test_export_dataset_vacio_y_columnas_duplicadas():
    with pytest.raises(ConnectorError, match="columnas"):
        export_to_bigquery(None, bq_params(), "t")
    with pytest.raises(ConnectorError, match="columnas"):
        export_to_bigquery(pd.DataFrame(), bq_params(), "t")
    df = pd.DataFrame([[1, 2]], columns=["a", "a"])
    with pytest.raises(ConnectorError, match="duplicados"):
        export_to_bigquery(df, bq_params(), "t")


def test_export_rechaza_nombres_de_columna_invalidos():
    df = pd.DataFrame([[1]], columns=["nombre con espacio"])
    with pytest.raises(ConnectorError, match="nombre con espacio"):
        export_to_bigquery(df, bq_params(), "t")
    # Más de cinco inválidos: se citan los cinco primeros y el recuento
    df = pd.DataFrame([[1] * 7], columns=[f"col {i}" for i in range(7)])
    with pytest.raises(ConnectorError, match=r"\(\+2\)"):
        export_to_bigquery(df, bq_params(), "t")


def test_export_error_del_job_es_accionable(fake_bq):
    fake_bq(FakeBQClient(load_error=RuntimeError("AccessDenied: see job abc")))
    with pytest.raises(ConnectorError, match="No se pudo exportar a BigQuery"):
        export_to_bigquery(pd.DataFrame({"a": [1]}), bq_params(), "t")


def test_export_enmascara_la_clave_privada(fake_bq):
    key = sa_key()
    fake_bq(FakeBQClient(load_error=RuntimeError(f"token {key['private_key']} vencido")))
    params = clean_bq_params(bq_params(credentials=key))
    with pytest.raises(ConnectorError) as excinfo:
        export_to_bigquery(pd.DataFrame({"a": [1]}), params, "t")
    msg = str(excinfo.value)
    assert "S3CR3T" not in msg
    assert "***" in msg


def test_export_sin_driver_error_accionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", None)
    with pytest.raises(ConnectorError, match="requirements-connectors.txt"):
        export_to_bigquery(pd.DataFrame({"a": [1]}), bq_params(), "t")


# ── Gating premium (vive en el servidor) ──────────────────────────────
def test_rutas_bigquery_ocultas_sin_licencia(client, monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    resp = client.post("/connectors/bigquery/test", json=bq_params(table="t"))
    assert resp.status_code == 404
    assert "licencia" in resp.get_json()["error"]
    resp = client.post("/connectors/bigquery/export", json={})
    assert resp.status_code == 404


def test_status_anuncia_bigquery_solo_con_licencia(client, monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    assert client.get("/premium/status").get_json()["connectors"] == []
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    assert client.get("/premium/status").get_json()["connectors"] == [
        "postgres",
        "s3",
        "bigquery",
    ]


def test_export_bigquery_sin_datos_con_licencia(client, monkeypatch):
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    resp = client.post("/connectors/bigquery/export", json=bq_params(table="t"))
    assert resp.status_code == 400
    assert "datos" in resp.get_json()["error"]


def test_export_bigquery_sin_tabla_con_licencia(client, monkeypatch):
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    app_module.current_df = pd.DataFrame({"a": [1]})
    resp = client.post("/connectors/bigquery/export", json=bq_params())
    assert resp.status_code == 400
    assert "tabla" in resp.get_json()["error"]


def test_ruta_test_end_to_end_con_licencia(client, monkeypatch, fake_bq):
    fake = fake_bq()
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    resp = client.post("/connectors/bigquery/test", json=bq_params(table="t"))
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert data["project"] == "mi-proyecto-42"
    assert fake.fake_client.calls == [("query", "SELECT 1")]


def test_export_bigquery_end_to_end_con_licencia(client, monkeypatch, fake_bq):
    fake = fake_bq()
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    app_module.current_df = pd.DataFrame({"a": [1, 2]})
    resp = client.post(
        "/connectors/bigquery/export",
        json=bq_params(table="empleados_limpios", mode="append"),
    )
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data["success"] is True
    assert data["rows"] == 2
    assert data["dataset"] == "analytics"
    assert data["table"] == "empleados_limpios"
    assert fake.fake_client.job_config.write_disposition == "WRITE_APPEND"
