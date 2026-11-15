"""B3/B5 — Forecast F3 (GET /forecast) y ajustes manuales (POST /forecast/ajustes).

El cálculo vive en proyeccion.py (baseline naive estacional + eventos con fecha + ajustes; ver su docstring).
Los artefactos LightGBM de modelo/artifacts/forecast/ no son integrables (modelo_ml.py): `meta.fallback_usado = true`.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.core import reloj
from app.core.ids import nuevo_id
from app.db import models as m
from app.schemas.forecast import AjusteRequest, AjusteResponse, Baseline, ForecastResponse, ProximoEvento
from app.services.finanzas import consultas as q
from app.services.finanzas.modelo_ml import meta_b, motivo_fallback_forecast
from app.services.finanzas.proyeccion import (
    DIAS_REQUERIDOS,
    MODELO,
    VERSION,
    _coincide,
    _textos_programado,
    confianza,
    dia_critico,
    proyectar,
    serie,
)

__all__ = ["forecast", "crear_ajuste", "MODELO", "VERSION", "DIAS_REQUERIDOS"]


def forecast(db: Session, empresa_id: str, horizonte_dias: int = 30, fecha_corte: date | None = None) -> ForecastResponse:
    from app.services.finanzas.disponible import calcular_disponible

    proy = proyectar(db, empresa_id, fecha_corte, horizonte_dias)
    puntos = proy.puntos()
    critico = dia_critico(proy, puntos)
    eventos = sorted(proy.eventos + proy.cobros_fiado, key=lambda e: (e.fecha, e.monto))
    return ForecastResponse(
        empresa_id=empresa_id, fecha_corte=proy.corte, horizonte_dias=proy.horizonte, saldo_actual=proy.saldo_actual,
        minimo_operativo=proy.minimo, serie=serie(proy, puntos), dia_critico=critico,
        disponible_para_gastar=calcular_disponible(proy, critico),
        proximos_eventos=[ProximoEvento(fecha=e.fecha, concepto=e.concepto, monto=e.monto, tipo=e.tipo,
                                        ponderado=e.ponderado or None, ref_id=e.ref_id) for e in eventos],
        ajustes_manuales_aplicados=proy.ajustes,
        baseline=Baseline(nombre="naive_estacional", mae_backtest=proy.mae_baseline),
        modelo_metricas=None,
        fundamento=("Tus ventas y gastos de las últimas 4 semanas (mismo día de la semana), tus pagos con fecha "
                    "(pedidos a crédito, sueldo, servicios, impuestos) y tus ajustes."),
        limites=("Los fiados no se cuentan en la línea esperada (sí en el rango optimista y en lo que puedes gastar), "
                 "porque cobrarlos a tiempo es incierto. No considera ventas o gastos que no hayas anotado. Mientras "
                 "más lejos el día, más ancho el rango."),
        confianza=confianza(proy), disponible=proy.dias_con_datos >= DIAS_REQUERIDOS,
        dias_con_datos=proy.dias_con_datos, dias_requeridos=DIAS_REQUERIDOS,
        meta=meta_b(MODELO, VERSION, fallback=True, motivo=motivo_fallback_forecast()),
    )  # fmt: skip


# ── B5: ajustes manuales ───────────────────────────────────────────────────────────────────────


def crear_ajuste(db: Session, empresa_id: str, ajuste: AjusteRequest) -> AjusteResponse:
    from app.core.errors import Validacion

    q.empresa_o_404(db, empresa_id)
    if ajuste.monto < 0:
        raise Validacion("El monto del ajuste no puede ser negativo.", [{"campo": "monto", "problema": "< 0"}])
    if ajuste.fecha <= reloj.hoy():
        raise Validacion("El ajuste es para un día que todavía no llega.",
                         [{"campo": "fecha", "problema": "debe ser posterior a hoy"}])  # fmt: skip
    textos = _textos_programado(db, empresa_id)
    programado_id = next((pid for pid, t in textos.items() if _coincide(ajuste.concepto, t)), None)
    fila = m.ForecastAjuste(ajuste_id=nuevo_id(db, m.ForecastAjuste, "AJU"), empresa_id=empresa_id,
                            programado_id=programado_id, fecha=ajuste.fecha, concepto=ajuste.concepto[:100],
                            monto=ajuste.monto, motivo=(ajuste.motivo or None) and ajuste.motivo[:255], activo=True,
                            creado_en=reloj.ahora())  # fmt: skip
    db.add(fila)
    db.commit()
    return AjusteResponse(ajuste_id=fila.ajuste_id, forecast_recalculado=True)
