"""Respuestas fijas de la Fase 0 (mismos JSON que frontend/src/mocks/data.js y handlers.js).

Temporal: cada dueño reemplaza estas funciones por el cálculo real y borra lo que deje de usar.
Datos de Pedro: saldo S/ 2 340, déficit −S/ 650 el 30/11, pedido S/ 2 400 a Distribuidora Andina, fiados S/ 310.
"""

import copy
from datetime import date, timedelta

from app.core.meta import construir_meta

CORTE = "2026-11-14"
PEDIDO_BASE = 2400.0
SALDO_BASE = -650.0
FIADOS_TOTAL = 310.0
SALDO_NEGOCIO = 2340.0
MINIMO_OPERATIVO = 800.0

def _meta(modelo: str, version: str, **extra) -> dict:
    return construir_meta(modelo, version, **extra).model_dump(mode="json")


def simular_saldo(monto: float = PEDIDO_BASE, partes: int = 1, cobrar_fiados: bool = False) -> float:
    """saldo_30/11 = −650 + (2400 − monto) + (2 partes ? monto/2 : 0) + (cobrar fiados ? 310 : 0)."""
    saldo = SALDO_BASE + (PEDIDO_BASE - monto)
    if partes >= 2:
        saldo += monto / 2
    if cobrar_fiados:
        saldo += FIADOS_TOTAL
    return saldo


def estado_caja(saldo: float) -> str:
    if saldo < 0:
        return "no_te_alcanza"
    if saldo < MINIMO_OPERATIVO:
        return "justo"
    return "te_alcanza"


# ── F2 ──────────────────────────────────────────────────────────────────────────────────────────

_RESUMEN = {
    "empresa_id": "EMP-0001",
    "periodo": "2026-11",
    "corte": CORTE,
    "dias_con_datos": 92,
    "indicadores": {
        "saldo_caja_negocio": {"valor": 2340.0, "variacion_pct": None},
        "ingresos_mes": {"valor": 8540.0, "variacion_pct": -6.2},
        "egresos_mes": {"valor": 7310.0, "variacion_pct": 4.8},
        "ganancia_neta": {"valor": 980.0, "variacion_pct": -18.5, "es_aproximada": True, "rango": [760.0, 1210.0]},
        "retiros_personales": {"valor": 1900.0, "sueldo_fijo_definido": None, "promedio_historico": 1200.0},
        "pendiente_cobro": {"valor": 310.0, "n_fiados": 3},
        "pagos_pendientes": {"valor": 2420.0, "n_obligaciones": 2, "detalle": "Andina + RUS"},
    },
    "variacion_vs": "2026-10 al mismo día de corte",
}


def resumen(periodo: str | None = None) -> dict:
    r = copy.deepcopy(_RESUMEN)
    if periodo:
        r["periodo"] = periodo
    return r


# ── F3 ──────────────────────────────────────────────────────────────────────────────────────────

_RUIDO = [40, -30, 55, 20, -45, 35, 60, -20, 25, -35, 50, 10, -25, 45, 0, 30, -40, 25, 55, -15, 40, 10, -30, 35, 20,
          -10, 45, -25, 30, 15]  # fmt: skip


def _serie(horizonte: int = 30) -> list[dict]:
    """Serie determinística del mock: baja por retiros, cae el 30/11 con el pago a Andina y se recupera."""
    out, p50 = [], 2340.0
    inicio = date(2026, 11, 15)
    for i in range(horizonte):
        d = inicio + timedelta(days=i)
        fecha = d.isoformat()
        ingresos = 610.0 + (120.0 if d.weekday() >= 5 else 0.0)
        egresos = 640.0
        if fecha == "2026-11-16":
            egresos += 180
        if fecha == "2026-11-20":
            ingresos += 190
        if fecha == "2026-11-30":
            egresos += 2400
        if fecha > "2026-11-30":
            egresos = 560.0
        p50 = p50 + ingresos - egresos + _RUIDO[i % len(_RUIDO)]
        if fecha == "2026-11-30":
            p50 = -650.0
        spread = 90 + i * 14
        out.append({"fecha": fecha, "ingresos_esperados": ingresos, "egresos_esperados": egresos,
                    "p10": round(p50 - spread), "p50": round(p50), "p90": round(p50 + spread * 0.85)})  # fmt: skip
    return out


def forecast(horizonte_dias: int = 30) -> dict:
    return {
        "empresa_id": "EMP-0001",
        "fecha_corte": CORTE,
        "horizonte_dias": horizonte_dias,
        "saldo_actual": 2340.0,
        "minimo_operativo": MINIMO_OPERATIVO,
        "serie": _serie(horizonte_dias),
        "dia_critico": {
            "fecha": "2026-11-30",
            "saldo_p50": -650.0,
            "probabilidad_deficit": 0.74,
            "obligacion_asociada": {"tipo": "prestamo_proveedor", "id": "PED-0012", "proveedor": "Distribuidora Andina",
                                    "monto": 2400.0},  # fmt: skip
        },
        "disponible_para_gastar": {
            "valor": 0.0,
            "formula": "saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento − minimo_operativo − reserva_impuestos",
            "componentes": {"saldo_actual": 2340.0, "cobros_esperados": 190.0, "pagos_comprometidos": 2420.0,
                            "minimo_operativo": 800.0, "reserva_impuestos": 20.0},  # fmt: skip
            "mensaje": "Hoy no saques para la casa: arriesgas el pago del 30/11.",
        },
        "proximos_eventos": [
            {"fecha": "2026-11-16", "concepto": "Planilla luz y agua", "monto": -180.0, "tipo": "gasto_negocio"},
            {"fecha": "2026-11-20", "concepto": "Fiados que esperas cobrar", "monto": 190.0, "tipo": "cobro_fiado",
             "ponderado": True},
            {"fecha": "2026-11-30", "concepto": "Pago a Andina", "monto": -2400.0, "tipo": "pago_proveedor",
             "ref_id": "PED-0012"},
            {"fecha": "2026-12-15", "concepto": "RUS", "monto": -20.0, "tipo": "pago_impuesto"},
        ],  # fmt: skip
        "ajustes_manuales_aplicados": [],
        "baseline": {"nombre": "naive_estacional", "mae_backtest": 212.4},
        "modelo_metricas": {"mae_backtest": 158.1, "cobertura_p10_p90": 0.82},
        "fundamento": "Tus ventas y gastos de los últimos 3 meses, tus pagos con fecha y los fiados según qué tan "
        "probable es que te paguen.",
        "limites": "No considera gastos o ventas que no hayas anotado. Mientras más lejos el día, más ancho el rango.",
        "confianza": "media",
        "meta": _meta("forecast-lgbm-quantile", "0.3.1"),
    }


# ── F4 ──────────────────────────────────────────────────────────────────────────────────────────

_FIADOS = [
    {"fiado_id": "FIA-0045", "cliente_id": "CLI-0102", "cliente": "Sra. Carmen", "detalle": "panes, leche",
     "monto": 120.0, "fecha": "2026-10-27", "dias_transcurridos": 18, "estado": "vencido",
     "riesgo_atraso": {"probabilidad": 0.72, "nivel": "alto", "baseline_probabilidad": 0.6},
     "accion_sugerida": {"tipo": "recordatorio", "texto_boton": "Recordarle"}},
    {"fiado_id": "FIA-0046", "cliente_id": "CLI-0087", "cliente": "Don Luis", "detalle": "arroz, aceite",
     "monto": 95.0, "fecha": "2026-11-02", "dias_transcurridos": 12, "estado": "por_vencer",
     "riesgo_atraso": {"probabilidad": 0.45, "nivel": "medio", "baseline_probabilidad": 0.6},
     "accion_sugerida": {"tipo": "recordatorio", "texto_boton": "Recordarle"}},
    {"fiado_id": "FIA-0047", "cliente_id": "CLI-0110", "cliente": "Vecina Rosa", "detalle": "gaseosas",
     "monto": 95.0, "fecha": "2026-11-05", "dias_transcurridos": 9, "estado": "pendiente",
     "riesgo_atraso": {"probabilidad": 0.18, "nivel": "bajo", "baseline_probabilidad": 0.6},
     "accion_sugerida": None},
]  # fmt: skip


def fiados() -> dict:
    return {
        "total_pendiente": 310.0,
        "total_vencido": 215.0,
        "items": copy.deepcopy(_FIADOS),
        "fundamento": "Cada riesgo sale de cuánto se demoró esa persona antes y de cuántos días lleva este fiado.",
        "limites": "Es una estimación; no sabe si el vecino tuvo un imprevisto.",
        "meta": _meta("riesgo-atraso-clf", "0.2.0"),
    }


def recordatorio(fiado_id: str) -> dict | None:
    f = next((x for x in _FIADOS if x["fiado_id"] == fiado_id), None)
    if f is None:
        return None
    monto = f"{f['monto']:.0f}" if float(f["monto"]).is_integer() else f"{f['monto']:.2f}"
    return {"mensaje": f"Hola, {f['cliente']} 😊 Le recuerdo amablemente los S/ {monto} pendientes en la bodega. ¡Gracias!"}


def estado_impuestos() -> dict:
    return {"estado": "al_dia", "proximo_vencimiento": "2026-12-15", "monto_estimado": 20.0, "nombre": "RUS de noviembre"}


def pedidos() -> dict:
    return {
        "total_pendiente": 2400.0,
        "items": [{"pedido_id": "PED-0012", "proveedor": "Distribuidora Andina", "monto": 2400.0,
                   "monto_pendiente": 2400.0, "fecha_pedido": "2026-11-13", "fecha_vencimiento": "2026-11-30",
                   "estado": "por_vencer", "dias_para_vencer": 16}],  # fmt: skip
        "impuestos": estado_impuestos(),
    }


def chequeo(monto: float = PEDIDO_BASE) -> dict:
    saldo = simular_saldo(monto)
    return {
        "saldo_proyectado_al_vencimiento": saldo,
        "estado_caja": estado_caja(saldo),
        "venta_esperada_periodo": 2000.0,
        "exceso_vs_ventas": max(0.0, monto - 2000.0),
        "sugerencias": [
            {"accion": "reducir_pedido", "monto_sugerido": 1800.0, "saldo_resultante": simular_saldo(1800)},
            {"accion": "pagar_en_partes", "partes": 2, "saldo_resultante": simular_saldo(monto, partes=2)},
            {"accion": "combinar", "detalle": "pedir 1 800 + pagar en 2 partes",
             "saldo_resultante": simular_saldo(1800, partes=2)},
        ],  # fmt: skip
        "fundamento": "En 2 semanas sueles vender unos S/ 2 000 y ese día no tendrás colchón.",
        "limites": "Proyección basada en tus ventas de los últimos 3 meses; no considera eventos que no hayas registrado.",
        "confianza": "media",
        "meta": _meta("forecast-lgbm-quantile", "0.3.1"),
    }


def simulacion(acciones: list[dict]) -> dict:
    monto, partes, cobrar = PEDIDO_BASE, 1, False
    for a in acciones:
        if a.get("tipo") == "reducir_pedido" and a.get("nuevo_monto") is not None:
            monto = float(a["nuevo_monto"])
        if a.get("tipo") == "pagar_en_partes":
            partes = int(a.get("partes") or 2)
        if a.get("tipo") == "cobrar_fiados":
            cobrar = True
    con = simular_saldo(monto, partes, cobrar)
    return {
        "sin_acciones": {"saldo_minimo": SALDO_BASE, "fecha": "2026-11-30", "estado_caja": "no_te_alcanza"},
        "con_acciones": {"saldo_minimo": con, "fecha": "2026-11-30", "estado_caja": estado_caja(con)},
        "mejora": con - SALDO_BASE,
        "serie_con_acciones": [{"fecha": "2026-11-30", "p50": con}],
        "fundamento": "Simulación con tus ventas de los últimos 3 meses.",
        "limites": "Tú decides; nada se ejecuta solo. Pagar en partes depende de que Andina acepte.",
        "confianza": "media",
        "meta": _meta("simulador-deterministico", "0.1.0"),
    }


# ── F5 ──────────────────────────────────────────────────────────────────────────────────────────


def analisis(agrupar_por: str = "categoria", tipo: str = "egreso") -> dict:
    return {
        "agrupar_por": agrupar_por,
        "tipo": tipo,
        "periodo": {"desde": "2026-11-01", "hasta": CORTE},
        "grupos": [
            {"clave": "mercaderia", "monto": 4980.0, "participacion_pct": 68.1, "variacion_pct": 12.4},
            {"clave": "retiros_personales", "monto": 1900.0, "participacion_pct": 26.0, "variacion_pct": 58.3},
        ],
        "comparacion_pares": {"metrica": "retiros_personales_sobre_ventas", "valor_empresa": 0.35,
                              "mediana_pares": 0.22, "grupo_pares": "bodegas · 1–3 trabajadores · Lima Este",
                              "n_pares": 120, "nota": "Comparación anónima con datos sintéticos."},  # fmt: skip
    }


# ── F6 ──────────────────────────────────────────────────────────────────────────────────────────


def alerta_faltante() -> dict:
    return {
        "alerta_id": "ALR-0007",
        "tipo": "faltante_caja",
        "prioridad": 1,
        "creada_en": "2026-11-14T08:05:00-05:00",
        "fecha_evento": "2026-11-30",
        "dias_para_evento": 16,
        "monto": 650.0,
        "probabilidad": 0.74,
        "nivel_riesgo": "alto",
        "titulo": "El 30/11 te faltarían S/ 650 para pagar a Andina",
        "titulo_corto": "El 30/11 no te alcanzará",
        "insight": "Para pagar S/ 2 400 a Distribuidora Andina te faltarían S/ 650.",
        "resumen_causas": "más plata para la casa, pedido grande y fiados sin cobrar.",
        "causas": [
            {"descripcion": "Sacaste más para la casa", "monto": 700.0},
            {"descripcion": "Pediste más de lo que vendes", "monto": 400.0},
            {"descripcion": "Fiados sin cobrar", "monto": 310.0},
        ],
        "accion": {"tipo": "abrir_simulador", "texto_boton": "Ver qué puedo hacer", "payload": {"pedido_id": "PED-0012"}},
        "microexplicacion": "Cuando el dinero de la casa y del negocio se mezclan, es difícil saber cuánto puedes pedir.",
        "canales": ["whatsapp", "app"],
        "estado": "activa",
        "meta": _meta("reglas-alertas + forecast-lgbm-quantile", "0.3.1"),
    }


def alertas() -> dict:
    return {"items": [alerta_faltante()]}
