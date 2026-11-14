"""STUB (Dueño: Dev A) — POST /webhooks/whatsapp."""
from typing import Any

from fastapi import APIRouter, Body

from app.mocks import stubs_a

router = APIRouter(tags=["F1 Ingesta"])


@router.post("/webhooks/whatsapp")
def whatsapp(body: dict[str, Any] = Body(...)):
    texto = body.get("texto") or ""
    res = stubs_a.interpretar_respuesta("texto", texto)
    if res is None:
        r = stubs_a.asistente(texto, None)
        return {"respuesta_texto": r["respuesta"], "botones": [], "respuesta_audio_url": None}
    bid = res["borrador_id"]
    return {
        "respuesta_texto": res.get("pregunta_aclaratoria") or f"Anotado: S/ {res['movimiento_propuesto']['monto']:.2f} ✅ ¿Correcto?",
        "botones": [{"id": f"confirmar:{bid}", "texto": "✅ Correcto"}, {"id": f"corregir:{bid}", "texto": "✏️ Corregir"}],
        "respuesta_audio_url": None,
    }
