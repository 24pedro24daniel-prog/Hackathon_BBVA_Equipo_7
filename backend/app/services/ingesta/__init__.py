"""Ingesta (Dev A): voz/texto/foto → borrador → registro. Ver PLAN_MVP.md §5 (A1–A13)."""

import importlib.util

from app.core.config import settings


def estado_ia() -> dict:
    """Estado de Whisper y del LLM para GET /health (B12). No carga modelos ni llama a la red."""
    from app.services.asistente import orquestador
    from app.services.ingesta import cuaderno, enrutador, extractor
    from app.services.ingesta.transcriptor import modelo_cargado

    whisper_instalado = importlib.util.find_spec("faster_whisper") is not None
    return {
        "r2": {"estado": "ok" if settings.r2_configurado else "sin_configurar", "bucket": settings.R2_BUCKET},
        "whisper": {
            "estado": "ok" if whisper_instalado else "no_disponible",
            "modelo": f"faster-whisper-{settings.WHISPER_MODEL}",
            "cargado": modelo_cargado(),
        },
        "llm": {
            "estado": "ok" if settings.llm_configurado else "sin_configurar",
            "modelo": settings.LLM_MODEL,
            "proveedor": "openrouter",
            "prompt_versions": {"extractor": extractor.PROMPT_VERSION, "asistente": orquestador.PROMPT_VERSION,
                                "chat": enrutador.PROMPT_VERSION, "cuaderno": cuaderno.PROMPT_VERSION},
        },
        "vlm": {
            "estado": "ok" if settings.llm_configurado else "sin_configurar",
            "modelo": settings.VLM_MODEL,
            "proveedor": "openrouter",
        },
    }
