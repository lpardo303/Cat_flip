"""Tests de auto-detección de codificación al cargar CSVs (roadmap encoding).

Antes: `pd.read_csv(BytesIO)` sin `encoding` → pandas exige UTF-8 y un CSV
en cp1252/latin-1 revienta el /upload con UnicodeDecodeError. Ahora
`read_table()` decodea: UTF-8 si pasa el decode (caso normal intacto), si no
charset-normalizer con fallback latin-1 (mapea todo byte, nunca lanza).

Cubre: carga cp1252 correcta (sin mojibake), campo `detected_encoding` de
/upload (solo cuando no es utf-8), la expresión de código y el script
exportado con `encoding=`, regresión del caso utf-8 y ascii, upload_right
(cp1252 en el frame derecho), y el formato no soportado sigue 400.
"""
import io

# cp1252 y latin-1 coinciden en estos bytes: é=0xE9, á=0xE1, ñ=0xF1, ó=0xF3
CP1252_CSV = (
    "Nombre,Ciudad\n"
    "José Márquez,Sevilla\n"
    "Ana Añadir,Córdoba\n"
    "Luis Ñoño,Málaga\n"
    "María Díaz,Granada\n"
    "Pablo Sáez,Jaén\n"
).encode("cp1252")

UTF8_CSV = CP1252_CSV.decode("cp1252").encode("utf-8")
ASCII_CSV = b"Nombre,Valor\nAlice,1\nBob,2\n"


# ── helpers ────────────────────────────────────────────────────────────
def upload(client, raw=b"Nombre,Valor\nAlice,1\nBob,2\n", filename="data.csv"):
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(raw), filename)},
        content_type="multipart/form-data",
    )
    return resp


def op(client, operation, params=None):
    return client.post(
        "/operation", json={"operation": operation, "params": params or {}}
    )


def names(resp):
    data = resp.get_json()["data"]
    i = data["columns"].index("Nombre")
    return [row[i] for row in data["data"]]


# ── carga cp1252 / latin-1 ─────────────────────────────────────────────
def test_cp1252_csv_loads_without_mojibake(client):
    resp = upload(client, CP1252_CSV)
    assert resp.status_code == 200, resp.get_json()
    assert names(resp) == ["José Márquez", "Ana Añadir", "Luis Ñoño",
                           "María Díaz", "Pablo Sáez"]


def test_cp1252_upload_reports_detected_encoding(client):
    body = upload(client, CP1252_CSV).get_json()
    enc = body["detected_encoding"]
    # La familia windows-125x se normaliza a cp1252 en read_table (el byte
    # 0xF1 es 'ñ' en cp1252 y 'ń' en cp1250; el empate lo resuelve el
    # proyecto a favor del español) — así el front anuncia siempre cp1252.
    assert enc == "cp1252"


def test_generated_code_includes_encoding(client):
    body = upload(client, CP1252_CSV).get_json()
    assert "encoding=" in body["code"]
    script = client.post("/export_script", json={"filename": "p"}).data.decode("utf-8")
    assert "encoding=" in script
    assert "read_csv('data.csv'" in script


def test_semicolon_csv_with_cp1252(client):
    raw = "Nombre;Ciudad\nJosé;Sevilla\nAna;Córdoba\n".encode("cp1252")
    resp = upload(client, raw)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["data"]["columns"] == ["Nombre", "Ciudad"]
    assert body["detected_encoding"]


def test_upload_right_accepts_cp1252(client):
    resp = client.post(
        "/upload_right",
        data={"file": (io.BytesIO(CP1252_CSV), "derecho.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert "José Márquez" in [r[data["columns"].index("Nombre")] for r in data["data"]]


# ── regresión: caso normal intacto ─────────────────────────────────────
def test_utf8_csv_unchanged(client):
    resp = upload(client, UTF8_CSV)
    body = resp.get_json()
    assert body["success"] is True
    assert body["detected_encoding"] is None
    assert names(resp) == ["José Márquez", "Ana Añadir", "Luis Ñoño",
                           "María Díaz", "Pablo Sáez"]
    assert "encoding=" not in body["code"]


def test_ascii_csv_has_no_detection(client):
    body = upload(client, ASCII_CSV).get_json()
    assert body["detected_encoding"] is None
    assert "encoding=" not in body["code"]


def test_unsupported_format_still_400(client):
    resp = upload(client, b"\x00\x01\x02", filename="data.bin")
    assert resp.status_code == 400
    assert "Formato no soportado" in resp.get_json()["error"]


def test_pipeline_after_cp1252_upload_works(client):
    upload(client, CP1252_CSV)
    resp = op(client, "trim", {"column": "Nombre"})
    assert resp.status_code == 200, resp.get_json()
