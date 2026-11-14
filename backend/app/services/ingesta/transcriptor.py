"""Audio → texto con faster-whisper local (A4).

El modelo se carga recién en la primera transcripción (nunca al importar ni en los tests) y queda en memoria.
Config: WHISPER_MODEL=small, WHISPER_DEVICE=cpu, WHISPER_COMPUTE_TYPE=int8, WHISPER_CACHE_DIR.
"""

import threading
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR, settings
from app.services.ingesta import almacenamiento

_modelo: Any = None
_candado = threading.Lock()


class TranscriptorNoDisponible(Exception):
    """faster-whisper no está instalado o el modelo no se pudo cargar."""


def _cargar_modelo() -> Any:
    """Crea el WhisperModel (descarga el modelo la primera vez). Los tests reemplazan esta función."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise TranscriptorNoDisponible("faster-whisper no está instalado") from exc
    try:
        return WhisperModel(
            settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
            download_root=settings.WHISPER_CACHE_DIR,
        )
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de carga se reporta igual
        raise TranscriptorNoDisponible(f"No se pudo cargar Whisper '{settings.WHISPER_MODEL}': {exc}") from exc


def obtener_modelo() -> Any:
    global _modelo
    if _modelo is None:
        with _candado:
            if _modelo is None:
                _modelo = _cargar_modelo()
    return _modelo


def modelo_cargado() -> bool:
    return _modelo is not None


def transcribir(ruta_audio: str) -> str:
    """Transcribe un archivo local (ogg, mp3, wav…). Lanza TranscriptorNoDisponible si Whisper falla."""
    modelo = obtener_modelo()
    try:
        segmentos, _info = modelo.transcribe(ruta_audio, language=settings.WHISPER_LANGUAGE, beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segmentos).strip()
    except TranscriptorNoDisponible:
        raise
    except Exception as exc:  # noqa: BLE001 - audio corrupto, códec no soportado…
        raise TranscriptorNoDisponible(f"No pude transcribir el audio: {exc}") from exc


def resolver_media(media_url: str | None) -> Path | None:
    """file://data/audios/x.ogg, demo://audios/x.ogg o una ruta → archivo local dentro de MEDIA_DIR (o None).

    Solo se leen archivos bajo MEDIA_DIR: un media_url no puede apuntar a otra parte del servidor.
    """
    if not media_url:
        return None
    base = (BACKEND_DIR / settings.MEDIA_DIR).resolve()
    if media_url.startswith("file://"):
        crudo = media_url[len("file://"):]
        ruta = Path(crudo) if Path(crudo).is_absolute() else BACKEND_DIR / crudo
    elif media_url.startswith("demo://"):
        ruta = base / media_url[len("demo://"):]
    elif "://" in media_url:
        return None
    else:
        ruta = Path(media_url) if Path(media_url).is_absolute() else BACKEND_DIR / media_url
    ruta = ruta.resolve()
    if base not in ruta.parents or not ruta.is_file():
        return None
    return ruta


def transcribir_media(media_url: str | None, empresa_id: str | None = None) -> str | None:
    """Transcribe el audio de media_url; None si no hay archivo que escuchar.

    Acepta archivos locales (file://, demo://) y r2:// (solo claves de `empresa_id`; se baja a un temporal que se
    borra al terminar).
    """
    if almacenamiento.es_r2(media_url):
        if not empresa_id:
            return None
        try:
            with almacenamiento.archivo_temporal(media_url, empresa_id, "audio") as ruta:
                return transcribir(str(ruta))
        except almacenamiento.ObjetoNoEncontrado:
            return None
        except almacenamiento.AlmacenamientoNoDisponible as exc:
            raise TranscriptorNoDisponible(str(exc.mensaje)) from exc
    ruta = resolver_media(media_url)
    if ruta is None:
        return None
    return transcribir(str(ruta))
