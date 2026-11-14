"""F7 — Asistente financiero (contrato §7)."""

from typing import Any

from pydantic import Field

from app.schemas.common import IntencionAsistente, Meta, ModeloContrato, ModeloEntrada


class MensajeRequest(ModeloEntrada):
    conversacion_id: str | None = None
    mensaje: str = Field(min_length=1, max_length=2000)
    canal: str = Field(default="app", pattern="^(whatsapp|app|email)$")


class HerramientaLlamada(ModeloContrato):
    nombre: str
    args: dict[str, Any] = {}


class CifraUsada(ModeloContrato):
    valor: float
    fuente: str


class VerificacionCifras(ModeloContrato):
    ok: bool
    no_verificadas: list[Any] = []


class MensajeResponse(ModeloContrato):
    conversacion_id: str
    respuesta: str
    intencion: IntencionAsistente
    herramientas_llamadas: list[HerramientaLlamada] = []
    cifras_usadas: list[CifraUsada] = []
    verificacion_cifras: VerificacionCifras
    fuera_de_alcance: bool = False
    ofrecer_humano: bool = False
    disclaimer: str
    meta: Meta
