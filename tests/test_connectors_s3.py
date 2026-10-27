# -*- coding: utf-8 -*-
"""Tests del conector real de S3 (Open Core).

Tres propiedades que defender:

1. **Gating en el servidor**: sin licencia `/connectors/s3/*` responde 404
   y `/premium/status` no anuncia «s3» — el gating no vive en el front.
2. **Ninguna entrada hostil llega al SDK**: bucket, clave y prefijo se
   validan (bucket DNS, sin `..`, sin NUL) y las credenciales se
   enmascaran si un error del driver las reflejara.
3. **Driver opcional**: sin ``boto3`` la app sigue viva y el error es
   accionable (la CI instala solo requirements.txt y requirements-dev.txt).

El SDK se sustituye con un doble inyectado en ``sys.modules["boto3"]``:
estos tests no tocan red ni necesitan credenciales.
"""

import sys

import pandas as pd
import pytest

import app as app_module
import connectors  # noqa: F401  (registro del módulo junto a sus funciones)
from connectors import (
    ConnectorError,
    clean_s3_params,
    export_to_s3,
    s3_object_key,
)
# Alias: sin él, pytest coleccionaría `test_s3_connection` como un test.
from connectors import test_s3_connection as s3_probe


# ── Driver falso (doble de boto3) ─────────────────────────────────────
class FakeS3Client:
    """Doble de `boto3.client("s3")`: registra llamadas y simula fallos."""

    def __init__(self, bucket_ok=True, object_exists=False, put_error=None):
        self.bucket_ok = bucket_ok
        self.object_exists = object_exists
        self.put_error = put_error
        self.calls = []
        self.body = None

    def head_bucket(self, Bucket):
        self.calls.append(("head_bucket", Bucket))
        if not self.bucket_ok:
            raise RuntimeError("403 Forbidden")
        return {}

    def head_object(self, Bucket, Key):
        self.calls.append(("head_object", Bucket, Key))
        if not self.object_exists:
            raise RuntimeError("404 Not Found")
        return {}

    def put_object(self, Bucket, Key, Body):
        self.calls.append(("put_object", Bucket, Key))
        if self.put_error is not None:
            raise self.put_error
        self.body = Body
        return {}


class LeakyClient(FakeS3Client):
    """Cliente cuyo error REFLEJA las credenciales (peor caso a enmascarar)."""

    def head_bucket(self, Bucket):
        raise RuntimeError("403: signature AKIADEMO with secret s3cr3t failed")


class FakeBoto3:
    """Sustituto mínimo de `boto3` con la misma superficie que usamos."""

    __version__ = "0.0-fake"

    def __init__(self, client=None):
        self.fake_client = client or FakeS3Client()
        self.client_calls = []

    def client(self, name, **kwargs):
        self.client_calls.append((name, kwargs))
        return self.fake_client


@pytest.fixture()
def fake_boto3(monkeypatch):
    """Inyecta un módulo `boto3` falso en sys.modules (sin red)."""

    def install(client=None):
        fake = FakeBoto3(client)
        monkeypatch.setitem(sys.modules, "boto3", fake)
        return fake

    return install


def s3_params(**overrides):
    """Payload válido de ejemplo (bucket + región + prefijo + clave)."""
    payload = {
        "bucket": "catflip-datos",
        "region": "eu-west-1",
        "prefix": "etl/limpios",
        "key": "empleados_limpios.csv",
    }
    payload.update(overrides)
    return clean_s3_params(payload)


# ── clean_s3_params ───────────────────────────────────────────────────
def test_params_no_dict():
    with pytest.raises(ConnectorError, match="objeto JSON"):
        clean_s3_params(["catflip-datos"])


def test_params_requiere_bucket_y_region():
    with pytest.raises(ConnectorError, match="bucket"):
        clean_s3_params({"region": "eu-west-1"})
    with pytest.raises(ConnectorError, match="región"):
        clean_s3_params({"bucket": "catflip-datos"})


def test_params_bucket_invalido_rechazado():
    with pytest.raises(ConnectorError, match="bucket"):
        clean_s3_params({"bucket": "Mi_Bucket", "region": "eu-west-1"})
    with pytest.raises(ConnectorError, match="bucket"):
        clean_s3_params({"bucket": "ab", "region": "eu-west-1"})


def test_params_caracteres_nulos_rechazados():
    with pytest.raises(ConnectorError, match="nulos"):
        clean_s3_params({"bucket": "catflip\x00datos", "region": "eu-west-1"})


def test_params_endpoint_validacion():
    ok = clean_s3_params({
        "bucket": "catflip-datos",
        "region": "eu-west-1",
        "endpoint_url": "https://minio.local:9000",
    })
    assert ok["endpoint_url"] == "https://minio.local:9000"
    with pytest.raises(ConnectorError, match="endpoint"):
        clean_s3_params({
            "bucket": "catflip-datos",
            "region": "eu-west-1",
            "endpoint_url": "ftp://minio.local",
        })
    with pytest.raises(ConnectorError, match="endpoint"):
        clean_s3_params({
            "bucket": "catflip-datos",
            "region": "eu-west-1",
            "endpoint_url": 123,
        })


def test_params_credenciales_opcionales():
    # Vacías no viajan: manda la cadena por defecto de boto3 (env/perfil).
    params = clean_s3_params({
        "bucket": "catflip-datos",
        "region": "eu-west-1",
        "aws_access_key_id": "",
        "aws_secret_access_key": "",
    })
    assert "aws_access_key_id" not in params
    assert "aws_secret_access_key" not in params
    # Con valor, viajan tal cual (se enmascaran en los errores).
    params = clean_s3_params({
        "bucket": "catflip-datos",
        "region": "eu-west-1",
        "aws_access_key_id": "AKIADEMO",
        "aws_secret_access_key": "s3cr3t",
    })
    assert params["aws_access_key_id"] == "AKIADEMO"
    assert params["aws_secret_access_key"] == "s3cr3t"
    with pytest.raises(ConnectorError, match="debe ser texto"):
        clean_s3_params({
            "bucket": "catflip-datos",
            "region": "eu-west-1",
            "aws_secret_access_key": 123,
        })


def test_params_credencial_con_nulos_rechazada():
    with pytest.raises(ConnectorError, match="nulos"):
        clean_s3_params({
            "bucket": "catflip-datos",
            "region": "eu-west-1",
            "aws_secret_access_key": "s3cr\x003t",
        })


def test_params_prefijo_hostil_rechazado_y_normalizado():
    with pytest.raises(ConnectorError, match=r"\.\."):
        s3_params(prefix="../secrets")
    with pytest.raises(ConnectorError, match="prefijo"):
        s3_params(prefix=42)
    with pytest.raises(ConnectorError, match="nulos"):
        s3_params(prefix="etl\x00x")
    params = s3_params(prefix="/etl//limpios/")
    assert params["prefix"] == "etl/limpios"
    # Prefijo vacío ⇒ la clave va a la raíz del bucket.
    params = clean_s3_params({"bucket": "catflip-datos", "region": "eu-west-1"})
    assert "prefix" not in params


# ── s3_object_key ─────────────────────────────────────────────────────
def test_object_key_con_prefijo():
    assert s3_object_key("etl/limpios", "empleados.csv") == "etl/limpios/empleados.csv"
    assert s3_object_key(None, "empleados.csv") == "empleados.csv"
    assert s3_object_key("etl", "/empleados.csv") == "etl/empleados.csv"
    assert s3_object_key("etl", "informes/mensual.csv") == "etl/informes/mensual.csv"


def test_object_key_traversal_rechazado():
    with pytest.raises(ConnectorError, match=r"\.\."):
        s3_object_key("etl", "../../etc/passwd.csv")
    with pytest.raises(ConnectorError, match="ruta destino"):
        s3_object_key(None, "   ")
    with pytest.raises(ConnectorError, match="vacía"):
        s3_object_key(None, "///")
    with pytest.raises(ConnectorError, match="nulos"):
        s3_object_key(None, "mal\x00o.csv")


def test_object_key_demasiado_larga():
    with pytest.raises(ConnectorError, match="1024"):
        s3_object_key(None, "x" * 2000 + ".csv")


# ── test_s3_connection (head_bucket) ──────────────────────────────────
def test_test_connection_ok(fake_boto3):
    fake = fake_boto3()
    result = s3_probe(s3_params())
    assert result == {
        "success": True,
        "bucket": "catflip-datos",
        "region": "eu-west-1",
        "driver": "boto3 0.0-fake",
    }
    assert fake.client_calls == [("s3", {"region_name": "eu-west-1"})]
    assert ("head_bucket", "catflip-datos") in fake.fake_client.calls


def test_test_connection_pasa_endpoint_y_credenciales(fake_boto3):
    fake = fake_boto3()
    s3_probe(clean_s3_params({
        "bucket": "catflip-datos",
        "region": "eu-west-1",
        "endpoint_url": "https://minio.local:9000",
        "aws_access_key_id": "AKIADEMO",
        "aws_secret_access_key": "s3cr3t",
    }))
    name, kwargs = fake.client_calls[0]
    assert name == "s3"
    assert kwargs == {
        "region_name": "eu-west-1",
        "endpoint_url": "https://minio.local:9000",
        "aws_access_key_id": "AKIADEMO",
        "aws_secret_access_key": "s3cr3t",
    }


def test_test_connection_fallo_es_connector_error(fake_boto3):
    fake_boto3(FakeS3Client(bucket_ok=False))
    with pytest.raises(ConnectorError, match="No se pudo conectar a S3"):
        s3_probe(s3_params())


def test_test_connection_enmascara_credenciales(fake_boto3):
    fake_boto3(LeakyClient())
    params = s3_params(aws_access_key_id="AKIADEMO", aws_secret_access_key="s3cr3t")
    with pytest.raises(ConnectorError) as excinfo:
        s3_probe(params)
    msg = str(excinfo.value)
    assert "s3cr3t" not in msg
    assert "AKIADEMO" not in msg
    assert "***" in msg


def test_sin_driver_error_accionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(ConnectorError, match="requirements-connectors.txt"):
        s3_probe(s3_params())


# ── export_to_s3 (put_object del CSV) ─────────────────────────────────
def test_export_sube_csv_al_bucket(fake_boto3):
    fake = fake_boto3()
    df = pd.DataFrame({"nombre": ["Ana", "Luis"], "saldo": [3200.5, None]})
    result = export_to_s3(df, s3_params(), "empleados_limpios.csv")
    assert result["success"] is True
    assert result["bucket"] == "catflip-datos"
    assert result["key"] == "etl/limpios/empleados_limpios.csv"
    assert result["mode"] == "overwrite"
    assert result["rows"] == 2
    assert result["columns"] == 2
    assert result["bytes"] > 0
    assert fake.fake_client.calls == [
        ("put_object", "catflip-datos", "etl/limpios/empleados_limpios.csv")
    ]
    text = fake.fake_client.body.decode("utf-8")
    assert text.splitlines()[0] == "nombre,saldo"
    assert "Ana,3200.5" in text


def test_export_fail_si_existe_no_sube(fake_boto3):
    fake = fake_boto3(FakeS3Client(object_exists=True))
    with pytest.raises(ConnectorError, match="ya existe"):
        export_to_s3(pd.DataFrame({"a": [1]}), s3_params(), "empleados_limpios.csv", mode="fail")
    assert [c[0] for c in fake.fake_client.calls] == ["head_object"]


def test_export_fail_objeto_ausente_sube(fake_boto3):
    fake = fake_boto3(FakeS3Client(object_exists=False))
    result = export_to_s3(pd.DataFrame({"a": [1]}), s3_params(), "nuevo.csv", mode="fail")
    assert result["success"] is True
    assert result["mode"] == "fail"
    assert [c[0] for c in fake.fake_client.calls] == ["head_object", "put_object"]


def test_export_modo_invalido():
    with pytest.raises(ConnectorError, match="overwrite"):
        export_to_s3(pd.DataFrame({"a": [1]}), s3_params(), "x.csv", mode="append")


def test_export_dataset_vacio_y_columnas_duplicadas():
    with pytest.raises(ConnectorError, match="columnas"):
        export_to_s3(pd.DataFrame(), s3_params(), "x.csv")
    df = pd.DataFrame([[1, 2]], columns=["a", "a"])
    with pytest.raises(ConnectorError, match="duplicados"):
        export_to_s3(df, s3_params(), "x.csv")


def test_export_error_del_sdk_enmascara(fake_boto3):
    fake_boto3(FakeS3Client(put_error=RuntimeError("AccessDenied for s3cr3t")))
    params = s3_params(aws_secret_access_key="s3cr3t")
    with pytest.raises(ConnectorError) as excinfo:
        export_to_s3(pd.DataFrame({"a": [1]}), params, "x.csv")
    msg = str(excinfo.value)
    assert "No se pudo exportar a S3" in msg
    assert "s3cr3t" not in msg
    assert "***" in msg


def test_export_sin_driver_error_accionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(ConnectorError, match="requirements-connectors.txt"):
        export_to_s3(pd.DataFrame({"a": [1]}), s3_params(), "x.csv")


# ── Gating premium (vive en el servidor) ──────────────────────────────
def test_rutas_s3_ocultas_sin_licencia(client, monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    resp = client.post("/connectors/s3/test", json={"bucket": "x", "region": "eu-west-1"})
    assert resp.status_code == 404
    assert "licencia" in resp.get_json()["error"]
    resp = client.post("/connectors/s3/export", json={})
    assert resp.status_code == 404


def test_status_anuncia_s3_solo_con_licencia(client, monkeypatch):
    monkeypatch.delenv("CATFLIP_PREMIUM_KEY", raising=False)
    assert client.get("/premium/status").get_json()["connectors"] == []
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    assert client.get("/premium/status").get_json()["connectors"] == ["postgres", "s3"]


def test_export_s3_sin_datos_con_licencia(client, monkeypatch):
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    resp = client.post(
        "/connectors/s3/export",
        json={"bucket": "catflip-datos", "region": "eu-west-1", "key": "x.csv"},
    )
    assert resp.status_code == 400
    assert "datos" in resp.get_json()["error"]


def test_export_s3_end_to_end_con_licencia(client, monkeypatch, fake_boto3):
    fake = fake_boto3()
    monkeypatch.setenv("CATFLIP_PREMIUM_KEY", "demo")
    app_module.current_df = pd.DataFrame({"a": [1, 2]})
    resp = client.post(
        "/connectors/s3/export",
        json={"bucket": "catflip-datos", "region": "eu-west-1", "key": "salida.csv"},
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert data["rows"] == 2
    assert data["key"] == "salida.csv"
    assert fake.fake_client.calls[-1] == (
        "put_object", "catflip-datos", "salida.csv"
    )
