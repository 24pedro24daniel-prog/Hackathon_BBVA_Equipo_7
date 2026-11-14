"""Idempotency-Key en los POST que crean registros (contrato §0) sobre la tabla técnica `idempotency_keys`.

Misma clave + mismo payload → se devuelve la respuesta guardada. Misma clave + otro payload → 409 CONFLICTO.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import Conflicto
from app.core.reloj import ahora
from app.db import models as m


@dataclass
class RespuestaGuardada:
    status_code: int
    respuesta: Any


def hash_payload(payload) -> str:
    crudo = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(crudo).hexdigest()


def buscar_respuesta(db: Session, clave: str | None, endpoint: str, payload) -> RespuestaGuardada | None:
    if not clave:
        return None
    fila = db.get(m.IdempotencyKey, (clave[:100], endpoint))
    if fila is None:
        return None
    if fila.payload_hash != hash_payload(payload):
        raise Conflicto("Esa Idempotency-Key ya se usó con otro contenido.",
                        [{"campo": "Idempotency-Key", "problema": "reutilizada con otro payload"}])  # fmt: skip
    return RespuestaGuardada(fila.status_code, fila.respuesta)


def guardar_respuesta(db: Session, clave: str | None, endpoint: str, payload, status_code: int, respuesta,
                      empresa_id: str | None = None) -> None:  # fmt: skip
    if not clave:
        return
    db.merge(m.IdempotencyKey(clave=clave[:100], endpoint=endpoint, empresa_id=empresa_id,
                              payload_hash=hash_payload(payload), status_code=status_code, respuesta=respuesta,
                              creado_en=ahora()))  # fmt: skip
    db.commit()
