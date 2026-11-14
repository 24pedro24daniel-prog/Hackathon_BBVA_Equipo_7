"""★ INTERFAZ B (PLAN_MVP.md §4.2): motor de alertas.

La tabla `alertas` la escribe B (es salida de su motor). Fase 0: respuestas mock del contrato.
"""

from sqlalchemy.orm import Session

from app import mock_contrato as mock
from app.schemas.alertas import Alerta, AlertasResponse

__all__ = ["evaluar_alertas", "alertas"]

# Disparadores que en el mock producen la alerta de faltante del 30/11 (un pedido a crédito grande).
_DISPARADORES_FALTANTE = {"compra_credito", "pedido", "chequeo_pedido"}


def evaluar_alertas(
    db: Session, empresa_id: str, disparador: str | None = None, entidad_id: str | None = None
) -> list[Alerta]:
    if disparador in _DISPARADORES_FALTANTE:
        return [Alerta.model_validate(mock.alerta_faltante())]
    return []


def alertas(db: Session, empresa_id: str, estado: str = "activa") -> AlertasResponse:
    if estado != "activa":
        return AlertasResponse(items=[])
    return AlertasResponse.model_validate(mock.alertas())
