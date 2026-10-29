# -*- coding: utf-8 -*-
"""Smoke **real** del conector S3 contra un servidor S3 de verdad.

Las corridas normales de la CI (y `pytest` en local) lo omiten: solo lo
ejecuta el job `s3-smoke` de ``.github/workflows/ci.yml``, que levanta un
service container **LocalStack S3** y pone ``CATFLIP_S3_SMOKE=1``. MinIO
dejó de distribuirse en 2026 (repo archivado), así que LocalStack es el
S3 compatible que usamos — igual que en la validación manual previa.

Lo que cubre es lo que los tests unitarios **no** pueden: `boto3` hablando
con un endpoint S3 real — `head_bucket`, la subida real del CSV, la
comprobación de `fail`/`overwrite` y el enmascado de credenciales en un
error de verdad.

Reproducción local::

    podman run -d --name catflip-s3-test -p 4566:4566 localstack/localstack:4.13.1
    CATFLIP_S3_SMOKE=1 pytest tests/test_connectors_s3_live.py -v
"""

import io
import os

import pandas as pd
import pytest

import connectors as C

pytestmark = pytest.mark.skipif(
    os.environ.get("CATFLIP_S3_SMOKE") != "1",
    reason="smoke real: necesita un S3 (job s3-smoke de la CI)",
)

_ENDPOINT = os.environ.get("CATFLIP_S3_ENDPOINT", "http://127.0.0.1:4566")
_PARAMS = {
    "bucket": os.environ.get("CATFLIP_S3_BUCKET", "catflip-smoke"),
    "region": os.environ.get("CATFLIP_S3_REGION", "us-east-1"),
    "endpoint_url": _ENDPOINT,
    "aws_access_key_id": os.environ.get("CATFLIP_S3_ACCESS_KEY", "test"),
    "aws_secret_access_key": os.environ.get("CATFLIP_S3_SECRET_KEY", "test"),
}


def _client():
    import boto3  # opcional: solo dentro del smoke, que ya lleva el driver

    return boto3.client(
        "s3",
        region_name=_PARAMS["region"],
        endpoint_url=_PARAMS["endpoint_url"],
        aws_access_key_id=_PARAMS["aws_access_key_id"],
        aws_secret_access_key=_PARAMS["aws_secret_access_key"],
    )


@pytest.fixture(scope="module")
def bucket():
    """Crea el bucket de prueba una vez (el conector solo hace head)."""
    client = _client()
    client.create_bucket(Bucket=_PARAMS["bucket"])
    return _PARAMS["bucket"]


def test_test_s3_connection_real(bucket):
    info = C.test_s3_connection(C.clean_s3_params(_PARAMS))
    assert info == {
        "success": True,
        "bucket": bucket,
        "region": _PARAMS["region"],
        "driver": f"boto3 {__import__('boto3').__version__}",
    }


def test_export_s3_sube_el_csv_y_se_puede_leer(bucket):
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "nombre": ["gato negro", "gato 'naranja'", None],
            "peso_kg": [4.5, 3.25, float("nan")],
        }
    )
    params = C.clean_s3_params({**_PARAMS, "prefix": "informes"})
    res = C.export_to_s3(df, params, "gatos.csv", mode="overwrite")

    assert res["success"] is True
    assert res["bucket"] == bucket
    assert res["key"] == "informes/gatos.csv"  # el prefijo viaja en la clave
    assert res["mode"] == "overwrite"
    assert res["rows"] == 3 and res["columns"] == 3

    obj = _client().get_object(Bucket=bucket, Key="informes/gatos.csv")
    body = obj["Body"].read()
    assert len(body) == res["bytes"]  # el resumen mide lo que hay de verdad
    assert body.decode("utf-8") == df.to_csv(index=False)  # el CSV completo

    reread = pd.read_csv(io.BytesIO(body))
    assert list(reread.columns) == ["id", "nombre", "peso_kg"]
    assert reread["nombre"].tolist()[:2] == ["gato negro", "gato 'naranja'"]
    assert pd.isna(reread["nombre"].iloc[2])  # el hueco sigue siendo un nulo


def test_export_fail_rechaza_y_overwrite_sobrescribe(bucket):
    df = pd.DataFrame({"valor": [1, 2]})
    params = C.clean_s3_params(_PARAMS)

    C.export_to_s3(df, params, "duplicado.csv", mode="overwrite")
    with pytest.raises(C.ConnectorError, match="ya existe"):
        C.export_to_s3(df, params, "duplicado.csv", mode="fail")

    res = C.export_to_s3(df * 10, params, "duplicado.csv", mode="overwrite")
    assert res["success"] is True
    obj = _client().get_object(Bucket=bucket, Key="duplicado.csv")
    assert obj["Body"].read() == (df * 10).to_csv(index=False).encode("utf-8")


def test_bucket_inexistente_enmascara_las_credenciales():
    params = C.clean_s3_params({**_PARAMS, "bucket": "catflip-no-existe"})
    with pytest.raises(C.ConnectorError) as excinfo:
        C.test_s3_connection(params)
    mensaje = str(excinfo.value)
    assert "No se pudo conectar a S3" in mensaje
    assert params["aws_secret_access_key"] not in mensaje
    assert params["aws_access_key_id"] not in mensaje
