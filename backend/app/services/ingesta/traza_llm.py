"""Trazabilidad de las llamadas al LLM/VLM: una fila de `llm_llamadas` por llamada, ok o con error.

    traza = traza_llm.crear(db, empresa_id, "extractor", prompt_version)   # None si no hay BD o está desactivada
    llm_client.chat_completion(mensajes, traza=traza)                      # registra la fila (siempre)
    traza.marcar("aceptada", referencia_tipo="borrador", referencia_id="BOR-0001")

Decisiones:
- La fila se escribe con la MISMA sesión del consumidor (`flush`, sin `commit`): así queda atada a la misma transacción
  que el borrador o el mensaje que enlaza. Va dentro de un SAVEPOINT para que un fallo del guardado no deje la sesión
  rota. Si el consumidor lanza un error controlado después de llamar al LLM (p. ej. NoInterpretable) hace
  `traza.confirmar()` antes de lanzarlo para que la fila no se pierda con el rollback.
- Sin sesión (`db=None`) no se registra nada: abrir una sesión propia escribiría en la BD principal incluso desde
  tests o scripts que no pasan `db`.
- La traza nunca rompe el flujo: cualquier fallo se registra como warning y se sigue.
- Nunca se guardan headers ni la API key, ni el base64 de las imágenes (solo sha256, bytes y mime).
"""

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import settings
from app.core.ids import nuevo_id
from app.core.reloj import ahora
from app.db import models as m

log = logging.getLogger("cajaclara.traza_llm")

MAX_ERROR = 300


@dataclass
class TrazaLLM:
    db: Any
    empresa_id: str | None
    origen: str
    prompt_version: str | None = None
    referencia_tipo: str | None = None
    referencia_id: str | None = None
    llamada_id: str | None = None  # se llena al registrar la llamada

    def registrar(self, payload: dict[str, Any], *, estado: str, latencia_ms: int | None = None,
                  http_status: int | None = None, datos: Any = None, error: str | None = None) -> None:  # fmt: skip
        """Guarda la fila. No lanza nunca."""
        try:
            fila = _armar(self, payload, estado, latencia_ms, http_status, datos, error)
            with self.db.begin_nested():
                fila.llamada_id = nuevo_id(self.db, m.LlmLlamada, "LLM", 6)
                self.db.add(fila)
                self.db.flush()
            self.llamada_id = fila.llamada_id
        except Exception:  # noqa: BLE001 - la traza no puede romper el flujo del usuario
            log.warning("No se pudo guardar la traza del LLM", exc_info=True)

    def marcar(self, resultado_uso: str | None = None, *, referencia_tipo: str | None = None,
               referencia_id: str | None = None) -> None:  # fmt: skip
        """Qué hizo el consumidor con la salida y a qué registro quedó enlazada la llamada."""
        if resultado_uso:
            self._actualizar(resultado_uso=resultado_uso)
        if referencia_id:
            self.referencia_tipo = referencia_tipo or self.referencia_tipo
            self.referencia_id = referencia_id
            self._actualizar(referencia_tipo=self.referencia_tipo, referencia_id=referencia_id)

    def confirmar(self) -> None:
        """Persiste la fila antes de que el consumidor lance un error que haría rollback."""
        if self.llamada_id is None:
            return
        try:
            self.db.commit()
        except Exception:  # noqa: BLE001
            log.warning("No se pudo confirmar la traza del LLM", exc_info=True)

    def _actualizar(self, **campos: Any) -> None:
        if self.llamada_id is None:
            return
        try:
            fila = self.db.get(m.LlmLlamada, self.llamada_id)
            if fila is not None:
                for campo, valor in campos.items():
                    setattr(fila, campo, valor)
        except Exception:  # noqa: BLE001
            log.warning("No se pudo actualizar la traza del LLM", exc_info=True)


def crear(db: Any, empresa_id: str | None, origen: str, prompt_version: str | None = None,
          referencia_tipo: str | None = None) -> TrazaLLM | None:  # fmt: skip
    """None si la traza está desactivada o no hay sesión (los consumidores lo toleran)."""
    if db is None or not settings.LLM_TRAZA_ACTIVA:
        return None
    return TrazaLLM(db, empresa_id, origen, prompt_version, referencia_tipo)


def enlazar(db: Any, llamada_id: str | None, referencia_tipo: str, referencia_id: str) -> None:
    """Enlaza una llamada ya registrada con el registro que produjo (borrador, mensaje)."""
    if db is None or not llamada_id:
        return
    t = TrazaLLM(db, None, "", llamada_id=llamada_id)
    t.marcar(referencia_tipo=referencia_tipo, referencia_id=referencia_id)


# ── armado de la fila ───────────────────────────────────────────────────────────────────────────


def _limpiar(texto: str) -> str:
    clave = settings.OPENROUTER_API_KEY.get_secret_value().strip()
    if clave:
        texto = texto.replace(clave, "***")
    return texto[:MAX_ERROR]


def _huella(url: str) -> dict[str, Any]:
    if url.startswith("data:") and ";base64," in url:
        cabecera, _, cuerpo = url.partition(";base64,")
        try:
            datos = base64.b64decode(cuerpo, validate=False)
        except ValueError:
            datos = cuerpo.encode()
        return {"imagen": {"sha256": hashlib.sha256(datos).hexdigest(), "bytes": len(datos),
                           "mime": cabecera[5:] or None}}  # fmt: skip
    return {"imagen": {"sha256": hashlib.sha256(url.encode()).hexdigest(), "bytes": None, "mime": None}}


def sin_imagenes(valor: Any) -> Any:
    """Copia del valor con cada imagen (data URL) reemplazada por {"imagen": {sha256, bytes, mime}}."""
    if isinstance(valor, dict):
        imagen = valor.get("image_url")
        if valor.get("type") == "image_url" and isinstance(imagen, dict | str):
            return _huella(imagen if isinstance(imagen, str) else str(imagen.get("url", "")))
        return {k: sin_imagenes(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [sin_imagenes(v) for v in valor]
    if isinstance(valor, str) and valor.startswith("data:") and ";base64," in valor:
        return _huella(valor)
    return valor


def _json(valor: Any) -> Any:
    return json.loads(json.dumps(valor, ensure_ascii=False, default=str))


def _nombres_tools(tools: list[dict] | None) -> list[str] | None:
    if not tools:
        return None
    return [t.get("function", {}).get("name", "?") for t in tools]


def _request(payload: dict[str, Any]) -> dict[str, Any]:
    base = {"model": payload.get("model"), "temperature": payload.get("temperature"),
            "max_tokens": payload.get("max_tokens"), "tool_choice": payload.get("tool_choice")}  # fmt: skip
    if settings.LLM_TRAZA_GUARDAR_CONTENIDO:
        base["messages"] = sin_imagenes(payload.get("messages"))
        base["tools"] = payload.get("tools")
        if payload.get("response_format"):
            base["response_format"] = payload["response_format"]
    else:
        base["n_messages"] = len(payload.get("messages") or [])
        base["tools"] = _nombres_tools(payload.get("tools"))
    return _json({k: v for k, v in base.items() if v is not None})


def _respuesta(datos: Any, estado: str) -> dict[str, Any] | None:
    if not isinstance(datos, dict):
        return None
    if estado != "ok":
        error = datos.get("error")
        return _json({"error": error}) if error else None
    eleccion = (datos.get("choices") or [{}])[0]
    mensaje = eleccion.get("message") or {}
    llamadas = mensaje.get("tool_calls")
    salida: dict[str, Any] = {"finish_reason": eleccion.get("finish_reason")}
    if settings.LLM_TRAZA_GUARDAR_CONTENIDO:
        salida["content"] = mensaje.get("content")
        if llamadas:
            salida["tool_calls"] = llamadas
    elif llamadas:
        salida["tool_calls"] = [{"name": (ll.get("function") or {}).get("name")} for ll in llamadas]
    return _json(salida)


def _entero(valor: Any) -> int | None:
    return int(valor) if isinstance(valor, int | float) and not isinstance(valor, bool) and valor >= 0 else None


def _armar(t: TrazaLLM, payload: dict[str, Any], estado: str, latencia_ms: int | None, http_status: int | None,
           datos: Any, error: str | None) -> m.LlmLlamada:  # fmt: skip
    datos = datos if isinstance(datos, dict) else {}
    uso = datos.get("usage") if isinstance(datos.get("usage"), dict) else {}
    costo = None
    if isinstance(uso.get("cost"), int | float | str) and not isinstance(uso.get("cost"), bool):
        try:
            costo = max(Decimal(str(uso["cost"])), Decimal(0))
        except InvalidOperation:
            costo = None
    return m.LlmLlamada(
        empresa_id=t.empresa_id, origen=t.origen, referencia_tipo=t.referencia_tipo, referencia_id=t.referencia_id,
        prompt_version=t.prompt_version, proveedor="openrouter", modelo_solicitado=payload.get("model"),
        modelo_respondido=str(datos["model"])[:100] if datos.get("model") else None,
        generation_id=str(datos["id"])[:100] if datos.get("id") else None,
        request=_request(payload), respuesta=_respuesta(datos, estado),
        prompt_tokens=_entero(uso.get("prompt_tokens")), completion_tokens=_entero(uso.get("completion_tokens")),
        total_tokens=_entero(uso.get("total_tokens")), costo_usd=costo, latencia_ms=latencia_ms, estado=estado,
        http_status=http_status, error=_limpiar(error) if error else None, creado_en=ahora(),
    )  # fmt: skip
