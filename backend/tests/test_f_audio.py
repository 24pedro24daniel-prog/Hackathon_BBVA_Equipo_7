"""Regresión de audio: PyAV decodifica lo que manda el navegador y la transcripción real funciona.

Contexto: faster-whisper 1.2.1 declara `av>=11` pero llama a `av.open(..., metadata_errors="ignore")`; av 19 quitó ese
argumento y TODA nota de voz real fallaba (`TypeError: open() got an unexpected keyword argument 'metadata_errors'`,
que el servicio convertía en "Ahora no puedo escuchar audios"). requirements.txt fija av==18.1.0.

- Tests baratos (sin Whisper): codifican un audio en memoria con PyAV en los formatos del MediaRecorder y lo decodifican
  con `faster_whisper.audio.decode_audio` (la misma función que usa `WhisperModel.transcribe`).
- Test caro: transcribe de verdad una nota corta con el servicio del backend (`servicio.transcribir` → `transcriptor`),
  con el modelo de `WHISPER_MODEL`. Se salta si el modelo no está en la caché (`WHISPER_CACHE_DIR`): nunca descarga.

Las notas de `tests/datos/audio/` son sintéticas: TTS de Windows ("Microsoft Sabina", es-MX) diciendo "pagué la luz del
local, 180 soles", recodificadas con PyAV como las graba cada navegador: webm/opus sin cues ni duración (Chrome, Edge),
ogg/opus (Firefox, WhatsApp) y MP4/AAC fragmentado (Safari).
"""

import io
import unicodedata
from pathlib import Path

import numpy as np
import pytest

av = pytest.importorskip("av")
fw_audio = pytest.importorskip("faster_whisper.audio")

from app.core.config import settings  # noqa: E402
from app.schemas.common import Canal  # noqa: E402
from app.schemas.ingesta import InterpretarRequest  # noqa: E402
from app.services.ingesta import servicio, transcriptor  # noqa: E402

DATOS = Path(__file__).parent / "datos" / "audio"
NOTAS = {  # archivo → content-type con el que lo sube el front
    "pague_luz_180.webm": "audio/webm;codecs=opus",
    "pague_luz_180.ogg": "audio/ogg;codecs=opus",
    "pague_luz_180.m4a": "audio/mp4",
}
# Capturado al importar, antes de que la fixture autouse `_sin_ia_real` lo reemplace por la guardia
_CARGAR_MODELO_REAL = transcriptor._cargar_modelo

# (id, formato del contenedor, códec, opciones del muxer): lo que graba MediaRecorder en cada navegador
FORMATOS_NAVEGADOR = [
    ("webm-opus", "webm", "libopus", {}),
    ("webm-opus-live", "webm", "libopus", {"live": "1"}),  # Chrome: sin cues ni duración (se graba en streaming)
    ("ogg-opus", "ogg", "libopus", {}),
    ("mp4-aac", "mp4", "aac", {}),
    ("mp4-aac-fragmentado", "mp4", "aac", {"movflags": "frag_keyframe+empty_moov+default_base_moof"}),  # Safari
    ("wav-pcm", "wav", "pcm_s16le", {}),
]
DURACION_S = 1.5


def _senal(segundos: float = DURACION_S, rate: int = 48000) -> np.ndarray:
    """Tono con vibrato y envolvente (no es voz, pero ejercita el códec igual). int16 mono, forma (1, n)."""
    t = np.arange(int(segundos * rate)) / rate
    onda = np.sin(2 * np.pi * (220 + 30 * np.sin(2 * np.pi * 3 * t)) * t) * (0.5 + 0.4 * np.sin(2 * np.pi * 2 * t))
    return (onda * 0.6 * 32767).astype(np.int16).reshape(1, -1)


def _codificar(formato: str, codec: str, opciones: dict, rate: int = 48000) -> bytes:
    """Codifica `_senal()` en memoria con PyAV (no hace falta ffmpeg en la imagen)."""
    buf = io.BytesIO()
    with av.open(buf, "w", format=formato, options=opciones) as salida:
        stream = salida.add_stream(codec, rate=rate, layout="mono")
        ctx = stream.codec_context
        tam = ctx.frame_size or 1024
        resampler = av.AudioResampler(format=ctx.format.name if ctx.format else "s16", layout="mono", rate=rate)
        fifo = av.AudioFifo()
        frame = av.AudioFrame.from_ndarray(_senal(rate=rate), format="s16", layout="mono")
        frame.sample_rate = rate
        for convertido in [*resampler.resample(frame), *resampler.resample(None)]:
            convertido.pts = None
            fifo.write(convertido)
        while fifo.samples:
            for paquete in stream.encode(fifo.read(min(tam, fifo.samples))):
                salida.mux(paquete)
        for paquete in stream.encode(None):
            salida.mux(paquete)
    return buf.getvalue()


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


# ── baratos: PyAV + decode_audio de faster-whisper, sin cargar Whisper ───────────────────────────


def test_av_acepta_metadata_errors_como_lo_usa_faster_whisper():
    """El contrato exacto que rompió av 19."""
    datos = _codificar("wav", "pcm_s16le", {})
    try:
        with av.open(io.BytesIO(datos), mode="r", metadata_errors="ignore") as cont:
            assert cont.streams.audio
    except TypeError as exc:  # pragma: no cover - solo con una versión de av incompatible
        pytest.fail(f"av {av.__version__} no es compatible con faster-whisper (fija av==18.1.0): {exc}")


@pytest.mark.parametrize("formato,codec,opciones", [f[1:] for f in FORMATOS_NAVEGADOR],
                         ids=[f[0] for f in FORMATOS_NAVEGADOR])  # fmt: skip
def test_decode_audio_formatos_del_navegador(formato, codec, opciones, tmp_path):
    datos = _codificar(formato, codec, opciones)
    ruta = tmp_path / f"nota.{formato}"
    ruta.write_bytes(datos)
    # El servicio le pasa a Whisper una ruta; decode_audio también acepta un archivo en memoria
    for entrada in (str(ruta), io.BytesIO(datos)):
        audio = fw_audio.decode_audio(entrada, sampling_rate=16000)
        assert audio.dtype == np.float32
        assert abs(len(audio) / 16000 - DURACION_S) < 0.15, f"{formato}/{codec}: {len(audio) / 16000:.3f} s"
        assert float(np.sqrt(np.mean(audio**2))) > 0.05, f"{formato}/{codec}: audio decodificado en silencio"


@pytest.mark.parametrize("archivo", sorted(NOTAS))
def test_decode_audio_notas_de_prueba(archivo):
    audio = fw_audio.decode_audio(str(DATOS / archivo), sampling_rate=16000)
    assert 3.0 < len(audio) / 16000 < 4.5
    assert float(np.abs(audio).max()) > 0.1


@pytest.fixture
def whisper_falso_que_decodifica(monkeypatch):
    """Modelo falso que, como el real, decodifica el archivo con PyAV antes de 'transcribir'."""

    class _Modelo:
        def transcribe(self, ruta, **_kw):
            fw_audio.decode_audio(ruta)
            return [], None

    monkeypatch.setattr(transcriptor, "_cargar_modelo", _Modelo)


def test_audio_corrupto_da_error_controlado(whisper_falso_que_decodifica):
    """Un archivo que no es audio no revienta el request: el servicio lo trata como Whisper no disponible."""
    with pytest.raises(transcriptor.TranscriptorNoDisponible, match="No pude transcribir"):
        transcriptor.transcribir(str(Path(__file__)))  # un .py no es audio


# ── caro: transcripción real con el servicio del backend ─────────────────────────────────────────


def _modelo_en_cache() -> str | None:
    """Motivo para saltar, o None si el modelo de WHISPER_MODEL ya está descargado (no se descarga en los tests)."""
    try:
        from faster_whisper.utils import download_model
    except ImportError:  # pragma: no cover
        return "faster-whisper no está instalado"
    if Path(settings.WHISPER_MODEL).is_dir():
        return None
    try:
        download_model(settings.WHISPER_MODEL, local_files_only=True, cache_dir=settings.WHISPER_CACHE_DIR)
    except Exception:  # noqa: BLE001 - LocalEntryNotFoundError y similares
        return (f"el modelo Whisper '{settings.WHISPER_MODEL}' no está en la caché (WHISPER_CACHE_DIR="
                f"{settings.WHISPER_CACHE_DIR or 'caché de Hugging Face'}); se descarga con la primera nota de voz real "
                "o con: docker compose run --rm backend python -c \"from faster_whisper.utils import download_model; "
                f"download_model('{settings.WHISPER_MODEL}', cache_dir='/models/whisper')\"")  # fmt: skip
    return None


@pytest.fixture(scope="module")
def modelo_whisper_real():
    motivo = _modelo_en_cache()
    if motivo:
        pytest.skip(motivo)
    modelo = _CARGAR_MODELO_REAL()  # el mismo cargador del servicio (WHISPER_MODEL, device, compute_type, caché)
    yield modelo
    del modelo


@pytest.mark.parametrize("archivo", sorted(NOTAS))
def test_transcripcion_real_nota_de_voz(archivo, modelo_whisper_real, monkeypatch):
    monkeypatch.setattr(transcriptor, "_cargar_modelo", lambda: modelo_whisper_real)
    monkeypatch.setattr(settings, "MEDIA_DIR", str(DATOS))  # el servicio solo lee archivos dentro de MEDIA_DIR
    req = InterpretarRequest(empresa_id="EMP-0001", canal=Canal.voz, media_url=f"file://{DATOS / archivo}")

    texto, transcripcion, uso_whisper, fallback_voz = servicio.transcribir(req)

    assert uso_whisper is True and fallback_voz is False
    assert texto == transcripcion
    plano = _sin_tildes(texto)
    assert "luz" in plano and "180" in plano, f"{archivo} ({NOTAS[archivo]}): {texto!r}"
