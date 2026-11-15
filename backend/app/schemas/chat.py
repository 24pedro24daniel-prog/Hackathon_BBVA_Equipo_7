"""Chat de la app (contrato §1.7): un solo endpoint que decide si el mensaje es un registro, una corrección del
borrador pendiente, una confirmación o una pregunta para el asistente."""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.asistente import MensajeResponse
from app.schemas.common import Meta, ModeloContrato, ModeloEntrada
from app.schemas.ingesta import ConfirmarResponse, InterpretarResponse


class ChatMensajeRequest(ModeloEntrada):
    texto: str | None = Field(default=None, max_length=2000)
    canal: Literal["texto", "voz"] = "texto"
    media_url: str | None = Field(default=None, max_length=255)
    borrador_id: str | None = Field(default=None, max_length=20)
    conversacion_id: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _texto_o_media(self):
        if not (self.texto and self.texto.strip()) and not (self.canal == "voz" and self.media_url):
            raise ValueError("Envía 'texto' (o 'media_url' con canal 'voz')")
        return self


class ChatMensajeResponse(ModeloContrato):
    tipo: Literal["registro", "borrador_actualizado", "guardado", "descartado", "asistente"]
    mensaje: str | None = None
    transcripcion: str | None = None
    interpretacion: InterpretarResponse | None = None
    confirmacion: ConfirmarResponse | None = None
    asistente: MensajeResponse | None = None
    conversacion_id: str | None = None
    meta: Meta
