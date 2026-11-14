"""A — Media en Cloudflare R2: POST /media/subidas, descarga validada y consumo desde la ingesta. Sin red (S3 falso)."""

import hashlib
import re
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.ingesta import almacenamiento, transcriptor

pytestmark = pytest.mark.db
P = settings.API_PREFIX
EMP = "EMP-0001"
CLAVE_AUDIO = f"empresas/{EMP}/audios/2026/11/aaaa.ogg"
CLAVE_FOTO = f"empresas/{EMP}/fotos/2026/11/cuaderno_01.jpg"
HASH_PEDRO = hashlib.sha256(b"+51900000001").hexdigest()


def _pedir(cliente, **cambios):
    cuerpo = {"empresa_id": EMP, "tipo": "audio", "content_type": "audio/ogg", "tamano_bytes": 50_000, **cambios}
    return cliente.post(f"{P}/media/subidas", json=cuerpo)


# ── POST /media/subidas ──


def test_subida_presignada_ok(client_db, s3_falso):
    r = _pedir(client_db)
    assert r.status_code == 201, r.text
    d = r.json()
    patron = rf"^r2://empresas/{EMP}/audios/\d{{4}}/\d{{2}}/[0-9a-f-]{{36}}\.ogg$"
    assert re.match(patron, d["media_url"])
    assert d["metodo"] == "PUT"
    assert d["headers_requeridos"] == {"Content-Type": "audio/ogg"}
    assert d["tamano_max_bytes"] == settings.MEDIA_MAX_AUDIO_BYTES
    assert d["expira_en"] and d["upload_url"].startswith("https://")
    firmado = s3_falso.presignados[0]
    assert firmado["operacion"] == "put_object" and firmado["metodo"] == "PUT"
    assert firmado["expires_in"] == settings.R2_PRESIGN_TTL_S
    assert firmado["params"]["ContentType"] == "audio/ogg" and firmado["params"]["Bucket"] == settings.R2_BUCKET
    assert d["media_url"] == f"r2://{firmado['params']['Key']}"


@pytest.mark.parametrize(("tipo", "ct", "carpeta", "ext"), [
    ("audio", "audio/webm", "audios", "webm"), ("audio", "audio/mpeg", "audios", "mp3"),
    ("audio", "audio/mp4", "audios", "m4a"), ("audio", "audio/wav", "audios", "wav"),
    ("imagen", "image/jpeg", "fotos", "jpg"), ("imagen", "image/png", "fotos", "png"),
    ("imagen", "image/webp", "fotos", "webp"),
])  # fmt: skip
def test_subida_extension_y_carpeta(client_db, s3_falso, tipo, ct, carpeta, ext):
    d = _pedir(client_db, tipo=tipo, content_type=ct).json()
    assert d["media_url"].startswith(f"r2://empresas/{EMP}/{carpeta}/") and d["media_url"].endswith(f".{ext}")


def test_subida_ignora_parametros_del_content_type(client_db, s3_falso):
    d = _pedir(client_db, content_type="audio/webm;codecs=opus").json()
    assert d["headers_requeridos"] == {"Content-Type": "audio/webm"} and d["media_url"].endswith(".webm")
    assert s3_falso.presignados[0]["params"]["ContentType"] == "audio/webm"


def test_subida_ttl_configurable(client_db, s3_falso, monkeypatch):
    monkeypatch.setattr(settings, "R2_PRESIGN_TTL_S", 120)
    _pedir(client_db)
    assert s3_falso.presignados[0]["expires_in"] == 120


def test_subida_claves_unicas(client_db, s3_falso):
    assert _pedir(client_db).json()["media_url"] != _pedir(client_db).json()["media_url"]


@pytest.mark.parametrize(("cambios", "campo"), [
    ({"content_type": "application/pdf"}, "content_type"),
    ({"content_type": "image/png"}, "content_type"),  # imagen no vale para tipo audio
    ({"tamano_bytes": settings.MEDIA_MAX_AUDIO_BYTES + 1}, "tamano_bytes"),
    ({"tamano_bytes": 0}, "tamano_bytes"),
    ({"tipo": "video"}, "tipo"),
    ({"tipo": "imagen", "content_type": "audio/ogg"}, "content_type"),
    ({"tipo": "imagen", "content_type": "image/png", "tamano_bytes": settings.MEDIA_MAX_IMAGEN_BYTES + 1}, "tamano_bytes"),
])  # fmt: skip
def test_subida_rechaza_invalidos(client_db, s3_falso, cambios, campo):
    r = _pedir(client_db, **cambios)
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "VALIDACION"
    assert any(x["campo"] == campo for x in r.json()["error"]["detalles"])
    assert s3_falso.presignados == []


def test_subida_campos_faltantes(client_db, s3_falso):
    r = client_db.post(f"{P}/media/subidas", json={"empresa_id": EMP})
    assert r.status_code == 400 and r.json()["error"]["codigo"] == "VALIDACION"


def test_subida_empresa_inexistente_404(client_db, s3_falso):
    r = _pedir(client_db, empresa_id="EMP-9999")
    assert r.status_code == 404 and r.json()["error"]["codigo"] == "NO_ENCONTRADO"


def test_subida_sin_r2_configurado_503(client_db):
    r = _pedir(client_db)
    assert r.status_code == 503
    error = r.json()["error"]
    assert error["codigo"] == "SERVICIO_NO_DISPONIBLE" and error["request_id"]


def test_subida_exige_api_key(client_sin_key):
    assert client_sin_key.post(f"{P}/media/subidas", json={}).status_code == 401


def test_health_reporta_r2_sin_red(client, s3_falso):
    assert client.get(f"{P}/health").json()["componentes"]["almacenamiento"]["estado"] == "ok"
    assert s3_falso.llamadas == [] and s3_falso.presignados == []


def test_health_r2_sin_configurar(client):
    assert client.get(f"{P}/health").json()["componentes"]["almacenamiento"]["estado"] == "sin_configurar"


# ── almacenamiento.descargar ──


@pytest.mark.parametrize("media_url", [
    "r2://empresas/EMP-0002/audios/2026/11/a.ogg",  # otra empresa
    "r2://empresas/EMP-00011/audios/a.ogg",  # prefijo parecido
    "r2://empresas/EMP-0001/../EMP-0002/audios/a.ogg",
    "r2://empresas/EMP-0001/../../secreto.ogg",
    "r2://otro/prefijo/a.ogg",
    "r2://a.ogg",
    "r2://empresas/EMP-0001/%2e%2e/a.ogg",
    "http://empresas/EMP-0001/a.ogg",
    "https://evil.test/a.ogg",
    "file://data/audios/a.ogg",
])  # fmt: skip
def test_descargar_rechaza_claves_ajenas_o_esquemas(s3_falso, media_url):
    s3_falso.poner("empresas/EMP-0002/audios/2026/11/a.ogg")
    with pytest.raises(almacenamiento.MediaInvalida):
        almacenamiento.descargar(media_url, EMP)
    assert s3_falso.llamadas == []  # ni siquiera se consulta a R2


def test_descargar_ok_y_borrado_del_temporal(s3_falso):
    url = s3_falso.poner(CLAVE_AUDIO, b"hola")
    with almacenamiento.archivo_temporal(url, EMP, "audio") as ruta:
        assert ruta.read_bytes() == b"hola" and ruta.suffix == ".ogg"
    assert not ruta.exists()
    assert [c[0] for c in s3_falso.llamadas] == ["head", "get"]


def test_descargar_borra_temporal_si_falla_el_uso(s3_falso):
    url = s3_falso.poner(CLAVE_AUDIO)
    with pytest.raises(RuntimeError), almacenamiento.archivo_temporal(url, EMP, "audio") as ruta:
        raise RuntimeError("boom")
    assert not ruta.exists()


def test_descargar_head_con_tamano_excedido_no_descarga(s3_falso):
    url = s3_falso.poner(CLAVE_AUDIO, tamano=settings.MEDIA_MAX_AUDIO_BYTES + 1)
    with pytest.raises(almacenamiento.MediaInvalida):
        almacenamiento.descargar(url, EMP, "audio")
    assert [c[0] for c in s3_falso.llamadas] == ["head"]


def test_descargar_content_type_no_permitido(s3_falso):
    url = s3_falso.poner(CLAVE_AUDIO, content_type="application/x-msdownload")
    with pytest.raises(almacenamiento.MediaInvalida):
        almacenamiento.descargar(url, EMP, "audio")
    assert [c[0] for c in s3_falso.llamadas] == ["head"]


def test_descargar_tipo_incorrecto(s3_falso):
    url = s3_falso.poner(CLAVE_AUDIO, content_type="image/png")
    with pytest.raises(almacenamiento.MediaInvalida):
        almacenamiento.descargar(url, EMP, "audio")


def test_descargar_objeto_inexistente(s3_falso):
    with pytest.raises(almacenamiento.ObjetoNoEncontrado):
        almacenamiento.descargar(f"r2://{CLAVE_AUDIO}", EMP, "audio")


def test_descargar_sin_r2_configurado():
    with pytest.raises(almacenamiento.AlmacenamientoNoDisponible):
        almacenamiento.descargar(f"r2://{CLAVE_AUDIO}", EMP, "audio")


def test_descargar_error_de_r2_es_no_disponible(s3_falso, monkeypatch):
    def _head(**_k):
        raise ConnectionError("sin red")

    monkeypatch.setattr(s3_falso, "head_object", _head)
    with pytest.raises(almacenamiento.AlmacenamientoNoDisponible):
        almacenamiento.descargar(f"r2://{CLAVE_AUDIO}", EMP, "audio")


# ── consumo desde la ingesta ──


def test_interpretar_voz_con_r2(client_db, s3_falso, whisper_falso):
    whisper_falso.texto = "saqué 50 para la casa"
    url = s3_falso.poner(CLAVE_AUDIO, b"ogg")
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "voz", "media_url": url})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["transcripcion"] == "saqué 50 para la casa" and d["meta"]["modelo"].startswith("whisper-small")
    assert len(whisper_falso.archivos) == 1 and not Path(whisper_falso.archivos[0]).exists()


def test_interpretar_voz_guarda_media_url_r2_en_el_borrador(client_db, db, s3_falso, whisper_falso):
    from app.db import models as m

    url = s3_falso.poner(CLAVE_AUDIO)
    d = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "voz", "media_url": url}).json()
    assert db.get(m.Borrador, d["borrador_id"]).media_url == url


def test_interpretar_voz_r2_inexistente_422(client_db, s3_falso, whisper_falso):
    r = client_db.post(f"{P}/ingesta/interpretar",
                       json={"empresa_id": EMP, "canal": "voz", "media_url": f"r2://{CLAVE_AUDIO}"})  # fmt: skip
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "NO_INTERPRETABLE"
    assert r.json()["error"]["detalles"][0]["campo"] == "media_url"


def test_interpretar_voz_r2_de_otra_empresa_400(client_db, s3_falso, whisper_falso):
    url = s3_falso.poner("empresas/EMP-0002/audios/2026/11/a.ogg")
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "voz", "media_url": url})
    assert r.status_code == 400 and r.json()["error"]["codigo"] == "VALIDACION"
    assert whisper_falso.archivos == []


def test_interpretar_voz_r2_demasiado_grande_400(client_db, s3_falso, whisper_falso):
    url = s3_falso.poner(CLAVE_AUDIO, tamano=settings.MEDIA_MAX_AUDIO_BYTES + 1)
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "voz", "media_url": url})
    assert r.status_code == 400 and whisper_falso.archivos == []


def test_interpretar_voz_r2_sin_configurar_nunca_500(client_db, whisper_falso):
    body = {"empresa_id": EMP, "canal": "voz", "media_url": f"r2://{CLAVE_AUDIO}"}
    assert client_db.post(f"{P}/ingesta/interpretar", json=body).status_code == 503
    con_texto = client_db.post(f"{P}/ingesta/interpretar", json={**body, "texto": "vendí dos cervezas"})
    assert con_texto.status_code == 200 and con_texto.json()["meta"]["fallback_usado"] is True


def test_interpretar_http_sigue_rechazado(client_db, s3_falso, whisper_falso):
    r = client_db.post(f"{P}/ingesta/interpretar",
                       json={"empresa_id": EMP, "canal": "voz", "media_url": "https://evil.test/a.ogg"})  # fmt: skip
    assert r.status_code == 422 and whisper_falso.archivos == [] and s3_falso.llamadas == []


def test_demo_y_file_siguen_funcionando(client_db, whisper_falso):
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "voz",
                                                         "media_url": "demo://audios/x.ogg",
                                                         "texto": "vendí dos cervezas"})  # fmt: skip
    assert r.status_code == 200 and r.json()["transcripcion"] == "vendí dos cervezas"


def test_cuaderno_con_r2_usa_fixture_por_nombre(client_db, s3_falso):
    url = s3_falso.poner(CLAVE_FOTO, b"jpg", "image/jpeg")
    r = client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": EMP, "media_url": url})
    assert r.status_code == 200, r.text
    assert len(r.json()["fiados_propuestos"]) == 3 and r.json()["meta"]["fallback_usado"] is True
    assert [c[0] for c in s3_falso.llamadas] == ["head", "get"]


def test_cuaderno_con_r2_foto_desconocida_lista_vacia(client_db, s3_falso):
    url = s3_falso.poner(f"empresas/{EMP}/fotos/2026/11/1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed.jpg", b"jpg", "image/jpeg")
    r = client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": EMP, "media_url": url})
    assert r.status_code == 200 and r.json()["fiados_propuestos"] == []


def test_cuaderno_r2_inexistente_422(client_db, s3_falso):
    r = client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": EMP, "media_url": f"r2://{CLAVE_FOTO}"})
    assert r.status_code == 422 and r.json()["error"]["detalles"][0]["campo"] == "media_url"


def test_cuaderno_r2_valida_empresa_y_tipo(client_db, s3_falso):
    ajena = s3_falso.poner("empresas/EMP-0002/fotos/2026/11/cuaderno_01.jpg", b"x", "image/jpeg")
    audio = s3_falso.poner(f"empresas/{EMP}/fotos/2026/11/a.jpg", b"x", "audio/ogg")
    for url in (ajena, audio):
        assert client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": EMP, "media_url": url}).status_code == 400


def test_cuaderno_r2_sin_configurar_503(client_db):
    r = client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": EMP, "media_url": f"r2://{CLAVE_FOTO}"})
    assert r.status_code == 503


# ── webhook ──


def _wa(cliente, **campos):
    body = {"telefono_hash": HASH_PEDRO, "empresa_id": EMP, **campos}
    r = cliente.post(f"{P}/webhooks/whatsapp", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_webhook_audio_con_r2(client_db, s3_falso, whisper_falso):
    whisper_falso.texto = "vendí dos cervezas"
    url = s3_falso.poner(CLAVE_AUDIO)
    r = _wa(client_db, tipo="audio", media_url=url)
    assert "vendí dos cervezas" in r["respuesta_texto"] and r["botones"]
    assert not Path(whisper_falso.archivos[0]).exists()


def test_webhook_imagen_con_r2(client_db, s3_falso):
    url = s3_falso.poner(CLAVE_FOTO, b"jpg", "image/jpeg")
    r = _wa(client_db, tipo="imagen", media_url=url)
    assert "Leí 3 fiados" in r["respuesta_texto"]


def test_webhook_audio_r2_ajeno_responde_texto_sin_500(client_db, s3_falso, whisper_falso):
    url = s3_falso.poner("empresas/EMP-0002/audios/2026/11/a.ogg")
    r = _wa(client_db, tipo="audio", media_url=url)
    assert r["respuesta_texto"] and r["botones"] == []


def test_transcribir_media_r2_sin_empresa_no_lee(s3_falso):
    assert transcriptor.transcribir_media(f"r2://{CLAVE_AUDIO}") is None and s3_falso.llamadas == []


def test_guarda_impide_cliente_boto3_real():
    import boto3

    with pytest.raises(AssertionError):
        boto3.client("s3")
