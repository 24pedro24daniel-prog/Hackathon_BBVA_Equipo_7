"""B10/B11 — Motor de alertas: evalúa reglas, máx. 2/día, horario silencioso (enviada_en = None),
sin duplicar la misma alerta activa. Escribe en la tabla `alertas` (la tabla es de B).

FASE 0: mock. Convención del stub: se dispara la alerta de faltante solo si
disparador == "compra_credito" (así el flujo "pedí 2 400 a Andina" muestra alertas_disparadas).
"""
from app.core.meta import construir_meta
from app.mocks import data as mock
from app.schemas.alertas import (
    AccionAlertaRequest, AccionAlertaResponse, Alerta, AlertasResponse, PreferenciasAlertas,
)

DISPARADOR_COMPRA_CREDITO = "compra_credito"


def _alerta_faltante() -> Alerta:
    return Alerta.model_validate({
        **mock.alerta_faltante(),
        "meta": construir_meta("reglas-alertas + forecast-lgbm-quantile", "0.3.1"),
    })


def evaluar_alertas(db, empresa_id: str, disparador: str | None = None, entidad_id: str | None = None) -> list[Alerta]:
    if disparador == DISPARADOR_COMPRA_CREDITO:
        return [_alerta_faltante()]
    return []


def alertas(db, empresa_id: str, estado: str = "activa") -> AlertasResponse:
    return AlertasResponse(items=[_alerta_faltante()] if estado == "activa" else [])


def registrar_accion(db, alerta_id: str, req: AccionAlertaRequest) -> AccionAlertaResponse:
    estado = {"ejecutada": "atendida", "descartada": "descartada", "posponer": "pospuesta"}[req.accion]
    return AccionAlertaResponse(estado=estado)


def guardar_preferencias(db, empresa_id: str, prefs: PreferenciasAlertas) -> PreferenciasAlertas:
    return prefs
