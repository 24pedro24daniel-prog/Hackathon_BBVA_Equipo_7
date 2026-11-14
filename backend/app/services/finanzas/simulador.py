"""B9 — Simulador determinístico. FASE 0: misma regla que el mock del front."""
from app.core.meta import construir_meta
from app.mocks import data as mock
from app.schemas.common import TipoAccionSimulador as T
from app.schemas.simulador import Accion, SimulacionResponse


def simular(db, empresa_id: str, acciones: list[Accion]) -> SimulacionResponse:
    monto, partes, cobrar = mock.PEDIDO_BASE, 1, False
    for a in acciones:
        if a.tipo == T.reducir_pedido and a.nuevo_monto is not None:
            monto = float(a.nuevo_monto)
        elif a.tipo == T.pagar_en_partes:
            partes = a.partes or 2
        elif a.tipo == T.cobrar_fiados:
            cobrar = True
    con = mock.simular_saldo(monto=monto, partes=partes, cobrar_fiados=cobrar)
    return SimulacionResponse.model_validate({
        "sin_acciones": {"saldo_minimo": mock.SALDO_BASE, "fecha": "2026-11-30", "estado_caja": "no_te_alcanza"},
        "con_acciones": {"saldo_minimo": con, "fecha": "2026-11-30", "estado_caja": mock.estado_caja(con)},
        "mejora": con - mock.SALDO_BASE,
        "serie_con_acciones": [{"fecha": "2026-11-30", "p50": con}],
        "fundamento": "Simulación con tus ventas de los últimos 3 meses.",
        "limites": "Tú decides; nada se ejecuta solo. Pagar en partes depende de que Andina acepte.",
        "confianza": "media",
        "meta": construir_meta("simulador-deterministico", "0.1.0"),
    })
