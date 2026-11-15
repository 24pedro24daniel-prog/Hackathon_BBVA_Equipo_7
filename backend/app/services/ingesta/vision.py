"""Foto del cuaderno → fiados con un modelo de visión (VLM) vía OpenRouter (A11).

La imagen se manda como data URL base64 (nunca una URL de R2) y el modelo responde con una tool forzada
(`registrar_fiados`). La salida se valida con pydantic y se normaliza de forma determinística: montos fuera de
rango, líneas tachadas (ya pagadas) o ilegibles no se proponen, y las fechas sin año o relativas se resuelven con
`core/reloj.hoy()`. Si algo falla se lanza `LLMNoDisponible` o `SalidaInvalida` y quien llama usa el fallback.
"""

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import settings
from app.core.reloj import hoy
from app.services.ingesta import llm_client, traza_llm
from app.services.ingesta.texto import normalizar

log = logging.getLogger("cajaclara.vision")

PROMPT_VERSION = "cuaderno-v2"
MODELO = "vlm-openrouter"
MONTO_MAXIMO = Decimal("10000")  # un fiado de bodega por encima de esto es casi seguro un error de lectura
MAX_FIADOS = 60
_DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

TOOL_FIADOS = {
    "type": "function",
    "function": {
        "name": "registrar_fiados",
        "description": "Lista los fiados escritos en la foto de un cuaderno de bodega.",
        "parameters": {
            "type": "object",
            "properties": {
                "fiados": {
                    "type": "array",
                    "description": "Una entrada por línea del cuaderno donde se anota lo que un cliente debe",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cliente": {"type": "string", "description": "Nombre o apodo tal como está escrito"},
                            "monto": {"type": "number", "description": "Soles, en número (15.50). Sin 'S/'"},
                            "fecha": {"type": ["string", "null"], "description": "AAAA-MM-DD; null si no se ve"},
                            "concepto": {"type": ["string", "null"], "description": "Qué se llevó, si está escrito"},
                            "tachado": {"type": "boolean", "description": "true si la línea está tachada o cruzada"},
                            "legible": {"type": "boolean", "description": "false si no se puede leer con seguridad"},
                        },
                        "required": ["cliente", "monto", "tachado", "legible"],
                    },
                },
                "lineas_no_legibles": {"type": "integer",
                                       "description": "Líneas con texto que no pudiste leer y no pusiste en fiados"},
            },
            "required": ["fiados", "lineas_no_legibles"],
        },
    },
}

_SISTEMA = """Lees la foto de un cuaderno de fiados de una bodega en Perú y llamas a la función registrar_fiados. \
Hoy es {hoy} ({dia}), zona America/Lima.

- Cada línea suele ser: cliente (nombre, apodo o "Doña/Don/Sra./Vecina ..."), lo que se llevó y el monto que debe.
- Montos: "S/ 15.50", "s/. 15", "15.50", "15,50", "15 soles" → número en soles (15.5). No sumes ni inventes \
cifras; si hay un total de página o de cliente, ponlo solo si es lo que debe ese cliente.
- Fechas: "12/11" o "12-11" es día/mes. Devuélvelas como AAAA-MM-DD; sin año usa el año de hoy (o el anterior si \
quedaría en el futuro). Para "lunes", "ayer", "hoy" usa la fecha más reciente que corresponda. Si no hay fecha, null.
- Una línea tachada, cruzada o marcada como pagada (✓, "pagó", "cancelado") es una deuda ya pagada: tachado = true.
- Si no puedes leer con seguridad el nombre o el monto, legible = false (o cuéntala en lineas_no_legibles). \
No adivines.
- Ignora títulos, dibujos y notas que no sean deudas de clientes.
{conocidos}"""


class _FiadoVLM(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cliente: str = Field(default="", max_length=100)
    monto: Decimal | None = None
    fecha: str | None = None
    concepto: str | None = Field(default=None, max_length=255)
    tachado: bool = False
    legible: bool = True

    @field_validator("cliente", mode="before")
    @classmethod
    def _cliente(cls, v):
        return "" if v is None else str(v).strip()[:100]

    @field_validator("monto", mode="before")
    @classmethod
    def _monto(cls, v):
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, str):
            limpio = re.sub(r"(?i)s\s*/\s*\.?|soles?", "", v).strip().replace(",", ".")
            try:
                return Decimal(limpio)
            except InvalidOperation:
                return None
        try:
            return Decimal(str(v))
        except InvalidOperation:
            return None

    @field_validator("fecha", "concepto", mode="before")
    @classmethod
    def _vacio_es_none(cls, v):
        return None if v is None or (isinstance(v, str) and v.strip().lower() in ("", "null", "none")) else str(v).strip()

    @field_validator("tachado", "legible", mode="before")
    @classmethod
    def _bool(cls, v, info):
        return (info.field_name == "legible") if v is None else v

    @field_validator("concepto", mode="after")
    @classmethod
    def _recorta(cls, v):
        return v[:255] if v else v


class SalidaVLM(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fiados: list[_FiadoVLM] = []
    lineas_no_legibles: int = Field(default=0, ge=0, le=500)

    @field_validator("fiados", mode="before")
    @classmethod
    def _fiados_null(cls, v):
        return [] if v is None else v

    @field_validator("lineas_no_legibles", mode="before")
    @classmethod
    def _lineas_null(cls, v):
        return 0 if v is None else v


class SalidaInvalida(Exception):
    """El modelo respondió, pero sin una tool call válida."""


@dataclass
class LecturaVisual:
    fiados: list[dict] = field(default_factory=list)
    lineas_no_legibles: int = 0
    lineas_tachadas: int = 0


def tipo_de_imagen(datos: bytes) -> str | None:
    """Content-Type por los primeros bytes (no se confía en la extensión del nombre)."""
    if datos[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def data_url(datos: bytes, tipo: str) -> str:
    return f"data:{tipo};base64,{base64.b64encode(datos).decode('ascii')}"


def _fecha(texto: str | None, dia: date) -> date | None:
    """ISO, dd/mm[/aaaa] o día de la semana → fecha. Sin año usa el de `dia`; si queda en el futuro, el anterior."""
    if not texto:
        return None
    t = normalizar(texto).strip()
    if t in ("hoy",):
        return dia
    if t == "ayer":
        return dia - timedelta(days=1)
    if t in _DIAS:
        return dia - timedelta(days=(dia.weekday() - _DIAS.index(t)) % 7)
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t):
        a, mes, d = int(m[1]), int(m[2]), int(m[3])
    elif m := re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?", t):
        d, mes = int(m[1]), int(m[2])
        a = int(m[3]) if m[3] else dia.year
        a += 2000 if a < 100 else 0
    else:
        return None
    f = _valida(a, mes, d)
    if f is None:
        return None
    if f > dia:  # fecha futura: el modelo se equivocó de año
        anterior = _valida(f.year - 1, f.month, f.day)
        return anterior if anterior and (dia - anterior).days < 366 else None
    return f


def _valida(a: int, mes: int, d: int) -> date | None:
    try:
        return date(a, mes, d)
    except ValueError:
        return None


def normalizar_salida(salida: SalidaVLM, dia: date) -> LecturaVisual:
    lectura = LecturaVisual(lineas_no_legibles=salida.lineas_no_legibles)
    for f in salida.fiados[:MAX_FIADOS]:
        if f.tachado:
            lectura.lineas_tachadas += 1
            continue
        monto = f.monto.quantize(Decimal("0.01")) if f.monto is not None and f.monto.is_finite() else None
        if not f.legible or not f.cliente or monto is None or not (0 < monto <= MONTO_MAXIMO):
            lectura.lineas_no_legibles += 1
            continue
        fecha = _fecha(f.fecha, dia)
        confianza = 0.85 if fecha else 0.65
        lectura.fiados.append({"cliente": f.cliente, "detalle": f.concepto, "monto": float(monto),
                               "fecha": (fecha or dia).isoformat(), "confianza": confianza})  # fmt: skip
    return lectura


def _sistema(dia: date, clientes: list[str]) -> str:
    conocidos = ""
    if clientes:
        conocidos = ("\nClientes que el dueño ya conoce (solo para reconocer apodos; escribe el nombre como está en "
                     f"el cuaderno): {', '.join(clientes[:60])}.")
    return _SISTEMA.format(hoy=dia.isoformat(), dia=_DIAS_ES[dia.weekday()], conocidos=conocidos)


def leer(datos: bytes, tipo: str, *, clientes: list[str] | None = None,
         traza: traza_llm.TrazaLLM | None = None) -> LecturaVisual:  # fmt: skip
    """Manda la foto al VLM y devuelve los fiados normalizados.

    Lanza LLMNoDisponible (sin key, timeout, error HTTP) o SalidaInvalida (sin tool call / argumentos inválidos).
    """
    dia = hoy()
    mensaje = llm_client.chat_completion(
        [
            {"role": "system", "content": _sistema(dia, clientes or [])},
            {"role": "user", "content": [
                {"type": "text", "text": "Esta es la foto del cuaderno. Registra los fiados."},
                {"type": "image_url", "image_url": {"url": data_url(datos, tipo)}},
            ]},
        ],
        tools=[TOOL_FIADOS],
        tool_choice={"type": "function", "function": {"name": "registrar_fiados"}},
        model=settings.VLM_MODEL,
        max_tokens=settings.VLM_MAX_TOKENS,
        timeout_s=settings.VLM_TIMEOUT_S,
        traza=traza,
    )
    llamadas = mensaje.get("tool_calls") or []
    if not llamadas:
        if traza:
            traza.marcar("rechazada_validacion")
        raise SalidaInvalida("el VLM no llamó a la función")
    argumentos = llamadas[0].get("function", {}).get("arguments")
    try:
        datos_tool = json.loads(argumentos) if isinstance(argumentos, str) else argumentos
        salida = SalidaVLM.model_validate(datos_tool)
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        if traza:
            traza.marcar("rechazada_validacion")
        raise SalidaInvalida(f"argumentos inválidos: {exc}") from exc
    if traza:
        traza.marcar("aceptada")
    return normalizar_salida(salida, dia)
