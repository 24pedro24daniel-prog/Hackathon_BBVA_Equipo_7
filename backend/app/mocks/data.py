"""Datos sintéticos de la demo (Pedro, Bodega Don Pedro). Port de frontend/src/mocks/data.js.

Solo para la Fase 0: cada servicio real los reemplaza. TODAS las cifras son ficticias.
"""
from datetime import date, timedelta
from itertools import count

EMPRESA_ID = "EMP-0001"
CORTE = "2026-11-14"
PEDIDO_BASE = 2400.0
SALDO_BASE = -650.0
FIADOS_TOTAL = 310.0
MINIMO_OPERATIVO = 800.0

# Estado en memoria de la demo (lo mueve el stub de /ingesta/confirmar)
ESTADO = {"saldo": 2340.0}
_seq = count(7781)
_mov = count(124)
BORRADORES: dict[str, dict] = {}


def siguiente_borrador() -> str:
    return f"BOR-{next(_seq)}"


def siguiente_movimiento() -> str:
    return f"MOV-{next(_mov):06d}"


# ---------- Reglas del simulador (idénticas al mock del front) ----------
def simular_saldo(monto: float = PEDIDO_BASE, partes: int = 1, cobrar_fiados: bool = False) -> float:
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


# ---------- F2 ----------
def resumen_pedro(periodo: str = "2026-11") -> dict:
    return {
        "empresa_id": EMPRESA_ID, "periodo": periodo, "corte": CORTE, "dias_con_datos": 92,
        "indicadores": {
            "saldo_caja_negocio": {"valor": ESTADO["saldo"], "variacion_pct": None},
            "ingresos_mes": {"valor": 8540.0, "variacion_pct": -6.2},
            "egresos_mes": {"valor": 7310.0, "variacion_pct": 4.8},
            "ganancia_neta": {"valor": 980.0, "variacion_pct": -18.5, "es_aproximada": True, "rango": [760.0, 1210.0]},
            "retiros_personales": {"valor": 1900.0, "sueldo_fijo_definido": None, "promedio_historico": 1200.0},
            "pendiente_cobro": {"valor": FIADOS_TOTAL, "n_fiados": 3},
            "pagos_pendientes": {"valor": 2420.0, "n_obligaciones": 2, "detalle": "Andina + RUS"},
        },
        "variacion_vs": "2026-10 al mismo día de corte",
    }


# ---------- F3 ----------
_RUIDO = [40, -30, 55, 20, -45, 35, 60, -20, 25, -35, 50, 10, -25, 45, 0,
          30, -40, 25, 55, -15, 40, 10, -30, 35, 20, -10, 45, -25, 30, 15]


def serie_pedro() -> list[dict]:
    out, p50 = [], 2340.0
    inicio = date(2026, 11, 15)
    for i in range(30):
        d = inicio + timedelta(days=i)
        f = d.isoformat()
        ingresos = 610 + (120 if d.weekday() >= 5 else 0)
        egresos = 640
        if f == "2026-11-16":
            egresos += 180
        if f == "2026-11-20":
            ingresos += 190
        if f == "2026-11-30":
            egresos += 2400
        if f > "2026-11-30":
            egresos = 560
        p50 = p50 + ingresos - egresos + _RUIDO[i]
        if f == "2026-11-30":
            p50 = -650.0
        spread = 90 + i * 14
        out.append({
            "fecha": f, "ingresos_esperados": ingresos, "egresos_esperados": egresos,
            "p10": round(p50 - spread), "p50": round(p50), "p90": round(p50 + spread * 0.85),
        })
    return out


def forecast_pedro() -> dict:
    return {
        "empresa_id": EMPRESA_ID, "fecha_corte": CORTE, "horizonte_dias": 30,
        "saldo_actual": ESTADO["saldo"], "minimo_operativo": MINIMO_OPERATIVO,
        "serie": serie_pedro(),
        "dia_critico": {
            "fecha": "2026-11-30", "saldo_p50": -650.0, "probabilidad_deficit": 0.74,
            "obligacion_asociada": {"tipo": "prestamo_proveedor", "id": "PED-0012",
                                    "proveedor": "Distribuidora Andina", "monto": 2400.0},
        },
        "disponible_para_gastar": {
            "valor": 0.0,
            "formula": "saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento − minimo_operativo − reserva_impuestos",
            "componentes": {"saldo_actual": 2340.0, "cobros_esperados": 190.0, "pagos_comprometidos": 2420.0,
                            "minimo_operativo": 800.0, "reserva_impuestos": 20.0},
            "mensaje": "Hoy no saques para la casa: arriesgas el pago del 30/11.",
        },
        "proximos_eventos": [
            {"fecha": "2026-11-16", "concepto": "Planilla luz y agua", "monto": -180.0, "tipo": "gasto_negocio"},
            {"fecha": "2026-11-20", "concepto": "Fiados que esperas cobrar", "monto": 190.0, "tipo": "cobro_fiado", "ponderado": True},
            {"fecha": "2026-11-30", "concepto": "Pago a Andina", "monto": -2400.0, "tipo": "pago_proveedor", "ref_id": "PED-0012"},
            {"fecha": "2026-12-15", "concepto": "RUS", "monto": -20.0, "tipo": "pago_impuesto"},
        ],
        "ajustes_manuales_aplicados": [],
        "baseline": {"nombre": "naive_estacional", "mae_backtest": 212.4},
        "modelo_metricas": {"mae_backtest": 158.1, "cobertura_p10_p90": 0.82},
        "fundamento": "Tus ventas y gastos de los últimos 3 meses, tus pagos con fecha y los fiados según qué tan probable es que te paguen.",
        "limites": "No considera gastos o ventas que no hayas anotado. Mientras más lejos el día, más ancho el rango.",
        "confianza": "media",
    }


# ---------- F4 ----------
def fiados_pedro() -> dict:
    def acc(texto):
        return {"tipo": "recordatorio", "texto_boton": texto}
    return {
        "total_pendiente": FIADOS_TOTAL, "total_vencido": 215.0,
        "items": [
            {"fiado_id": "FIA-0045", "cliente_id": "CLI-0102", "cliente": "Sra. Carmen", "detalle": "panes, leche",
             "monto": 120.0, "fecha": "2026-10-27", "dias_transcurridos": 18, "estado": "vencido",
             "riesgo_atraso": {"probabilidad": 0.72, "nivel": "alto", "baseline_probabilidad": 0.6},
             "accion_sugerida": acc("Recordarle")},
            {"fiado_id": "FIA-0046", "cliente_id": "CLI-0087", "cliente": "Don Luis", "detalle": "arroz, aceite",
             "monto": 95.0, "fecha": "2026-11-02", "dias_transcurridos": 12, "estado": "por_vencer",
             "riesgo_atraso": {"probabilidad": 0.45, "nivel": "medio", "baseline_probabilidad": 0.6},
             "accion_sugerida": acc("Recordarle")},
            {"fiado_id": "FIA-0047", "cliente_id": "CLI-0110", "cliente": "Vecina Rosa", "detalle": "gaseosas",
             "monto": 95.0, "fecha": "2026-11-05", "dias_transcurridos": 9, "estado": "pendiente",
             "riesgo_atraso": {"probabilidad": 0.18, "nivel": "bajo", "baseline_probabilidad": 0.6},
             "accion_sugerida": None},
        ],
        "fundamento": "Cada riesgo sale de cuánto se demoró esa persona antes y de cuántos días lleva este fiado.",
        "limites": "Es una estimación; no sabe si el vecino tuvo un imprevisto.",
    }


def pedidos_pedro() -> dict:
    return {
        "total_pendiente": PEDIDO_BASE,
        "items": [{"pedido_id": "PED-0012", "proveedor": "Distribuidora Andina", "monto": PEDIDO_BASE,
                   "monto_pendiente": PEDIDO_BASE, "fecha_pedido": "2026-11-13", "fecha_vencimiento": "2026-11-30",
                   "estado": "por_vencer", "dias_para_vencer": 16}],
        "impuestos": impuestos_pedro(),
    }


def impuestos_pedro() -> dict:
    return {"estado": "al_dia", "proximo_vencimiento": "2026-12-15", "monto_estimado": 20.0, "nombre": "RUS de noviembre"}


def chequeo_pedro(monto: float) -> dict:
    saldo = simular_saldo(monto=monto)
    return {
        "saldo_proyectado_al_vencimiento": saldo,
        "estado_caja": estado_caja(saldo),
        "venta_esperada_periodo": 2000.0,
        "exceso_vs_ventas": max(0.0, monto - 2000.0),
        "sugerencias": [
            {"accion": "reducir_pedido", "monto_sugerido": 1800.0, "saldo_resultante": simular_saldo(monto=1800)},
            {"accion": "pagar_en_partes", "partes": 2, "saldo_resultante": simular_saldo(monto=monto, partes=2)},
            {"accion": "combinar", "detalle": "pedir 1 800 + pagar en 2 partes",
             "saldo_resultante": simular_saldo(monto=1800, partes=2)},
        ],
        "fundamento": "En 2 semanas sueles vender alrededor de S/ 2 000 y el 30/11 también vencen otros pagos.",
        "limites": "Proyección basada en tus ventas de los últimos 3 meses; no considera eventos que no hayas registrado.",
        "confianza": "media",
    }


# ---------- F6 ----------
def alerta_faltante() -> dict:
    return {
        "alerta_id": "ALR-0007", "tipo": "faltante_caja", "prioridad": 1,
        "creada_en": "2026-11-14T08:05:00-05:00", "fecha_evento": "2026-11-30", "dias_para_evento": 16,
        "monto": 650.0, "probabilidad": 0.74, "nivel_riesgo": "alto",
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
        "canales": ["whatsapp", "app"], "estado": "activa",
    }


# ---------- F5 ----------
def analisis_pedro(agrupar_por: str = "categoria", tipo: str = "egreso") -> dict:
    return {
        "agrupar_por": agrupar_por, "tipo": tipo,
        "periodo": {"desde": "2026-11-01", "hasta": CORTE},
        "grupos": [
            {"clave": "mercaderia", "monto": 4980.0, "participacion_pct": 68.1, "variacion_pct": 12.4},
            {"clave": "retiros_personales", "monto": 1900.0, "participacion_pct": 26.0, "variacion_pct": 58.3},
            {"clave": "servicios", "monto": 430.0, "participacion_pct": 5.9, "variacion_pct": -2.0},
        ],
        "comparacion_pares": {
            "metrica": "retiros_personales_sobre_ventas", "valor_empresa": 0.35, "mediana_pares": 0.22,
            "grupo_pares": "bodegas · 1–3 trabajadores · Lima Este", "n_pares": 120,
            "nota": "Comparación anónima con datos sintéticos.",
        },
    }


# ---------- F8 (stub de A) ----------
def salud_pedro() -> dict:
    sub = [
        ("constancia_registro", "Anotar todos los días", 92, "92 días anotando · 4 semanas seguidas", 0.20, True),
        ("separacion_personal", "Separar casa y negocio", 70, "Sueldo fijo de S/ 400 por semana; este mes te pasaste", 0.20, True),
        ("colchon_caja", "Colchón de caja", 45, "5 días de gastos cubiertos", 0.15, False),
        ("pedidos_acordes", "Pedidos acordes a ventas", 60, "1 de 3 pedidos excedió tus ventas", 0.15, False),
        ("cobro_fiados", "Cobrar fiados a tiempo", 80, "8 de cada 10 fiados cobrados en menos de 15 días", 0.10, True),
        ("impuestos_al_dia", "Impuestos al día", 100, "Al día", 0.10, False),
        ("meses_sin_faltante", "Meses sin faltantes", 50, "1 de 2 meses", 0.10, False),
    ]
    return {
        "score": 71, "score_anterior": 64, "etapa_actual": "estabilizar",
        "etapas": ["organizar", "estabilizar", "proteger", "crecer"],
        "subindicadores": [{"id": i, "nombre": n, "valor": v, "detalle": d, "peso": p, "destacado": h}
                           for i, n, v, d, p, h in sub],
        "historial": [{"mes": "2026-08", "score": 38}, {"mes": "2026-09", "score": 52},
                      {"mes": "2026-10", "score": 64}, {"mes": "2026-11", "score": 71}],
        "rachas": [{"tipo": "semanas_registrando", "valor": 4}],
        "metas_activas": [{"meta_id": "MET-0004", "plantilla": "apartar_para_pedido", "titulo": "Apartar para el pedido",
                           "detalle": "S/ 1 de cada S/ 10 que vendes", "acumulado": 420.0, "estado": "activa"}],
        "consentimiento_compartir_historial": False,
    }


# ---------- F1 (stubs de A) ----------
CATALOGO = {"cerveza": {"producto_id": "PRD-0031", "producto": "Cerveza 620 ml", "precio_unitario": 6.5}}
