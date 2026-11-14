"""Audios y fotos en Cloudflare R2 (API S3): URL prefirmada de subida y descarga validada.

El front sube directo a R2 con la URL PUT prefirmada y luego manda `media_url = "r2://<clave>"` a la ingesta.
Para leer un `r2://` solo se acepta una clave bajo `empresas/{empresa_id}/` (no se puede leer lo de otra empresa
ni apuntar a otra parte). El cliente boto3 se crea recién al usarse (nunca al importar ni en los tests).
"""

import logging
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import ServicioNoDisponible, Validacion
from app.core.reloj import ahora

log = logging.getLogger("cajaclara.media")

ESQUEMA = "r2://"
EXTENSIONES = {
    "audio/ogg": "ogg", "audio/webm": "webm", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav",
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
}  # fmt: skip
CARPETAS = {"audio": "audios", "imagen": "fotos"}
_CLAVE_VALIDA = re.compile(r"^[A-Za-z0-9._/-]+$")

_cliente: Any = None
_candado = threading.Lock()


class AlmacenamientoNoDisponible(ServicioNoDisponible):
    """R2 sin configurar o inaccesible."""

    def __init__(self, mensaje: str = "El almacenamiento de audios y fotos no está disponible por ahora."):
        super().__init__(mensaje)


class MediaInvalida(Validacion):
    """El media_url no es aceptable (otra empresa, tamaño o tipo no permitido…)."""

    def __init__(self, mensaje: str, problema: str):
        super().__init__(mensaje, [{"campo": "media_url", "problema": problema}])


class ObjetoNoEncontrado(Exception):
    """La clave no existe en el bucket."""


@dataclass(frozen=True)
class SubidaPrefirmada:
    media_url: str
    upload_url: str
    metodo: str
    headers_requeridos: dict[str, str]
    expira_en: datetime
    tamano_max_bytes: int


def _crear_cliente() -> Any:
    """Cliente S3 de R2. Los tests reemplazan esta función por un cliente falso."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID.strip()}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID.get_secret_value().strip(),
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY.get_secret_value().strip(),
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, connect_timeout=5, read_timeout=20,
                      retries={"max_attempts": 2}),
    )  # fmt: skip


def obtener_cliente() -> Any:
    global _cliente
    if not settings.r2_configurado:
        raise AlmacenamientoNoDisponible("R2 no está configurado en el servidor (faltan credenciales o cuenta).")
    if _cliente is None:
        with _candado:
            if _cliente is None:
                _cliente = _crear_cliente()
    return _cliente


def tipos_permitidos(tipo: str | None = None) -> list[str]:
    if tipo == "audio":
        return settings.media_tipos_audio
    if tipo == "imagen":
        return settings.media_tipos_imagen
    return settings.media_tipos_audio + settings.media_tipos_imagen


def tamano_maximo(tipo: str) -> int:
    return settings.MEDIA_MAX_AUDIO_BYTES if tipo == "audio" else settings.MEDIA_MAX_IMAGEN_BYTES


def normalizar_content_type(content_type: str) -> str:
    """'audio/webm;codecs=opus' → 'audio/webm' (los parámetros no se firman ni se guardan)."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def _tipo_de_content_type(content_type: str) -> str | None:
    if content_type in settings.media_tipos_audio:
        return "audio"
    if content_type in settings.media_tipos_imagen:
        return "imagen"
    return None


def clave_nueva(empresa_id: str, tipo: str, content_type: str) -> str:
    fecha = ahora()
    extension = EXTENSIONES.get(content_type, "bin")
    return f"empresas/{empresa_id}/{CARPETAS[tipo]}/{fecha:%Y}/{fecha:%m}/{uuid.uuid4()}.{extension}"


def presignar_subida(empresa_id: str, tipo: str, content_type: str, tamano_bytes: int) -> SubidaPrefirmada:
    """Valida tipo/tamaño y devuelve la URL PUT prefirmada (el Content-Type queda firmado)."""
    ct = normalizar_content_type(content_type)
    if ct not in tipos_permitidos(tipo):
        raise Validacion(f"El tipo '{ct or content_type}' no está permitido para {tipo}.",
                         [{"campo": "content_type", "problema": f"permitidos: {', '.join(tipos_permitidos(tipo))}"}])  # fmt: skip
    maximo = tamano_maximo(tipo)
    if tamano_bytes > maximo:
        raise Validacion(f"El archivo pesa demasiado (máximo {maximo // (1024 * 1024)} MB para {tipo}).",
                         [{"campo": "tamano_bytes", "problema": f"máximo {maximo} bytes"}])  # fmt: skip
    cliente = obtener_cliente()
    clave = clave_nueva(empresa_id, tipo, ct)
    ttl = settings.R2_PRESIGN_TTL_S
    try:
        url = cliente.generate_presigned_url(
            "put_object", Params={"Bucket": settings.R2_BUCKET, "Key": clave, "ContentType": ct},
            ExpiresIn=ttl, HttpMethod="PUT")  # fmt: skip
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo presignar la subida: %s", type(exc).__name__)
        raise AlmacenamientoNoDisponible() from exc
    return SubidaPrefirmada(media_url=f"{ESQUEMA}{clave}", upload_url=url, metodo="PUT",
                            headers_requeridos={"Content-Type": ct}, expira_en=ahora() + timedelta(seconds=ttl),
                            tamano_max_bytes=maximo)  # fmt: skip


def es_r2(media_url: str | None) -> bool:
    return bool(media_url) and media_url.startswith(ESQUEMA)


def clave_de(media_url: str, empresa_id: str) -> str:
    """Valida el r2:// y devuelve la clave; solo claves bajo empresas/{empresa_id}/."""
    if not es_r2(media_url):
        raise MediaInvalida("El media_url debe empezar con r2://.", "esquema no permitido")
    clave = media_url[len(ESQUEMA):]
    if (not _CLAVE_VALIDA.fullmatch(clave) or ".." in clave.split("/") or "//" in clave
            or not clave.startswith(f"empresas/{empresa_id}/") or clave.endswith("/")):  # fmt: skip
        raise MediaInvalida("Ese archivo no pertenece a tu empresa.", "clave no permitida")
    return clave


def _es_no_encontrado(exc: Exception) -> bool:
    codigo = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
    return codigo in {"404", "NoSuchKey", "NotFound"}


def _guardar(cuerpo: Any, maximo: int, sufijo: str) -> Path:
    fd, ruta = tempfile.mkstemp(prefix="cajaclara_", suffix=sufijo)
    try:
        with os.fdopen(fd, "wb") as destino:
            leidos = 0
            while trozo := cuerpo.read(1024 * 1024):
                leidos += len(trozo)
                if leidos > maximo:
                    raise MediaInvalida("El archivo pesa demasiado.", f"tamaño excede {maximo} bytes")
                destino.write(trozo)
    except MediaInvalida:
        Path(ruta).unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        Path(ruta).unlink(missing_ok=True)
        log.warning("Lectura de R2 falló: %s", type(exc).__name__)
        raise AlmacenamientoNoDisponible() from exc
    return Path(ruta)


def descargar(media_url: str, empresa_id: str, tipo: str | None = None) -> Path:
    """Descarga el objeto a un archivo temporal (quien llama lo borra; ver `archivo_temporal`).

    Antes de bajar nada hace HEAD y verifica tamaño y content-type.
    """
    clave = clave_de(media_url, empresa_id)
    cliente = obtener_cliente()
    try:
        cabecera = cliente.head_object(Bucket=settings.R2_BUCKET, Key=clave)
    except Exception as exc:  # noqa: BLE001
        if _es_no_encontrado(exc):
            raise ObjetoNoEncontrado(clave) from exc
        log.warning("HEAD a R2 falló: %s", type(exc).__name__)
        raise AlmacenamientoNoDisponible() from exc
    ct = normalizar_content_type(cabecera.get("ContentType", ""))
    if ct not in tipos_permitidos(tipo):
        raise MediaInvalida("El archivo no es de un tipo permitido.", f"content-type '{ct}' no permitido")
    maximo = tamano_maximo(tipo or _tipo_de_content_type(ct) or "imagen")
    tamano = int(cabecera.get("ContentLength", 0))
    if tamano > maximo:
        raise MediaInvalida("El archivo pesa demasiado.", f"tamaño {tamano} excede {maximo} bytes")
    try:
        cuerpo = cliente.get_object(Bucket=settings.R2_BUCKET, Key=clave)["Body"]
    except Exception as exc:  # noqa: BLE001
        if _es_no_encontrado(exc):
            raise ObjetoNoEncontrado(clave) from exc
        log.warning("GET a R2 falló: %s", type(exc).__name__)
        raise AlmacenamientoNoDisponible() from exc
    try:
        return _guardar(cuerpo, maximo, f".{EXTENSIONES.get(ct, 'bin')}")
    finally:
        if cerrar := getattr(cuerpo, "close", None):
            cerrar()


@contextmanager
def archivo_temporal(media_url: str, empresa_id: str, tipo: str | None = None) -> Iterator[Path]:
    """`descargar` + borrado del temporal al terminar (con o sin error)."""
    ruta = descargar(media_url, empresa_id, tipo)
    try:
        yield ruta
    finally:
        ruta.unlink(missing_ok=True)
