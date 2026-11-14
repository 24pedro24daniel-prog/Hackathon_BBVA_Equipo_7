"""Score de salud (A12): constancia de registro, separación personal/negocio (retiros vs sueldo), impuestos al día.

Suma ponderada, determinística y explicable. El resultado del mes en curso se guarda en `score_salud` (resultado
versionado, permitido por PLAN §8); los meses anteriores se leen de ahí para el historial.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.meta import construir_meta
from app.core.reloj import hoy, inicio_del_dia
from app.db import models as m
from app.schemas.common import Frecuencia, TipoMovimiento
from app.services import finanzas
from app.services.ingesta.texto import soles
from app.services.salud.metas import resumen_metas

log = logging.getLogger("cajaclara.salud")

VERSION_FORMULA = "score-v1"
MODELO_VERSION = "0.1.0"
PESOS = {"constancia_registro": 0.35, "separacion_personal": 0.40, "impuestos_al_dia": 0.25}
NOMBRES = {"constancia_registro": "Anotar todos los días", "separacion_personal": "Separar casa y negocio",
           "impuestos_al_dia": "Impuestos al día"}  # fmt: skip
ETAPAS = ["organizar", "estabilizar", "proteger", "crecer"]
_FRECUENCIA_TXT = {"semanal": "por semana", "mensual": "al mes", "quincenal": "por quincena", "diaria": "al día"}


def etapa(score: int) -> str:
    if score < 50:
        return "organizar"
    if score < 80:
        return "estabilizar"
    if score < 90:
        return "proteger"
    return "crecer"


def _dias_con_registro(db: Session, empresa_id: str, desde: date, hasta: date) -> set[date]:
    dia = func.date(func.timezone("America/Lima", m.Transaccion.fecha_hora))
    filas = db.execute(select(dia).distinct().where(
        m.Transaccion.empresa_id == empresa_id, ~m.Transaccion.anulada,
        m.Transaccion.fecha_hora >= inicio_del_dia(desde),
        m.Transaccion.fecha_hora < inicio_del_dia(hasta + timedelta(days=1))))  # fmt: skip
    return {f[0] for f in filas}


def _constancia(db: Session, empresa_id: str, corte: date) -> tuple[int, str]:
    inicio = corte.replace(day=1)
    dias = _dias_con_registro(db, empresa_id, inicio, corte)
    evaluados = (corte - inicio).days + 1
    if corte not in dias and evaluados > 1:
        evaluados -= 1  # el día de hoy todavía puede anotarse
    con = len(dias)
    valor = round(100 * con / evaluados) if evaluados else 0
    return min(valor, 100), f"{con} de {evaluados} días anotando este mes"


def _ocurrencias_sueldo(prog: m.MovimientoProgramado, desde: date, hasta: date) -> int:
    inicio = max(desde, prog.fecha_inicio)
    fin = min(hasta, prog.fecha_fin) if prog.fecha_fin else hasta
    n, d = 0, inicio
    while d <= fin:
        if prog.frecuencia == Frecuencia.diaria:
            n += 1
        elif prog.frecuencia == Frecuencia.semanal and d.isoweekday() == (prog.dia_semana or 6):
            n += 1
        elif prog.frecuencia == Frecuencia.quincenal and d.day in ((prog.dia_mes or 1), (prog.dia_mes or 1) + 15):
            n += 1
        elif prog.frecuencia == Frecuencia.mensual and d.day == (prog.dia_mes or 1):
            n += 1
        d += timedelta(days=1)
    return n


def _separacion(db: Session, empresa_id: str, corte: date) -> tuple[int, str]:
    inicio = corte.replace(day=1)
    retiros = Decimal(db.scalar(select(func.coalesce(func.sum(m.Transaccion.monto), 0)).where(
        m.Transaccion.empresa_id == empresa_id, m.Transaccion.tipo == TipoMovimiento.retiro_personal,
        ~m.Transaccion.anulada, m.Transaccion.afecta_caja, m.Transaccion.fecha_hora >= inicio_del_dia(inicio),
        m.Transaccion.fecha_hora < inicio_del_dia(corte + timedelta(days=1)))))  # fmt: skip
    sueldos = db.scalars(select(m.MovimientoProgramado).where(
        m.MovimientoProgramado.empresa_id == empresa_id, m.MovimientoProgramado.es_sueldo)).all()  # fmt: skip
    vigente = next((s for s in sueldos if s.activo), None)
    if vigente is None:
        return 30, f"Aún no defines un sueldo fijo; este mes sacaste {soles(retiros)} para la casa"
    esperado = sum((s.monto * _ocurrencias_sueldo(s, inicio, corte) for s in sueldos), Decimal("0"))
    base = f"Sueldo fijo de {soles(vigente.monto)} {_FRECUENCIA_TXT[vigente.frecuencia.value]}"
    if retiros <= esperado:
        return 100, f"{base}; este mes lo respetaste"
    valor = round(40 + 60 * float(esperado / retiros))
    return valor, f"{base}; este mes sacaste {soles(retiros)} ({soles(retiros - esperado)} más)"


def _impuestos(db: Session, empresa_id: str, corte: date) -> tuple[int, str]:
    try:
        estado = finanzas.estado_impuestos(db, empresa_id, corte)
    except Exception:  # noqa: BLE001 - un fallo de B no debe tumbar el score
        log.exception("estado_impuestos falló")
        return 50, "No pude revisar tus impuestos"
    if estado.estado == "vencido":
        return 0, "Tienes un impuesto vencido"
    return 100, "Al día"


def _rachas(db: Session, empresa_id: str, corte: date) -> list[dict]:
    dias = _dias_con_registro(db, empresa_id, corte - timedelta(days=371), corte)
    d = corte if corte in dias else corte - timedelta(days=1)
    seguidos = 0
    while d in dias:
        seguidos += 1
        d -= timedelta(days=1)
    semanas = 0
    lunes = corte - timedelta(days=corte.weekday())
    if not any(lunes + timedelta(days=i) in dias for i in range(7)):
        lunes -= timedelta(days=7)
    while any(lunes + timedelta(days=i) in dias for i in range(7)):
        semanas += 1
        lunes -= timedelta(days=7)
    return [{"tipo": "semanas_registrando", "valor": semanas}, {"tipo": "dias_seguidos", "valor": seguidos}]


def calcular_score(db: Session, empresa_id: str, fecha_corte: date | None = None, persistir: bool = True) -> dict:
    corte = fecha_corte or hoy()
    mes = corte.strftime("%Y-%m")
    calculos = {"constancia_registro": _constancia(db, empresa_id, corte),
                "separacion_personal": _separacion(db, empresa_id, corte),
                "impuestos_al_dia": _impuestos(db, empresa_id, corte)}  # fmt: skip
    score = round(sum(PESOS[k] * v for k, (v, _) in calculos.items()))
    subindicadores = [{"id": k, "nombre": NOMBRES[k], "valor": v, "detalle": d, "peso": PESOS[k], "destacado": True}
                      for k, (v, d) in calculos.items()]  # fmt: skip
    if persistir:
        db.merge(m.ScoreSalud(empresa_id=empresa_id, mes=mes, score=score, version_formula=VERSION_FORMULA,
                              subindicadores={k: v for k, (v, _) in calculos.items()}))  # fmt: skip
        db.commit()
    anteriores = db.scalars(select(m.ScoreSalud).where(m.ScoreSalud.empresa_id == empresa_id, m.ScoreSalud.mes < mes)
                            .order_by(m.ScoreSalud.mes)).all()  # fmt: skip
    consentimiento = db.scalar(select(m.Consentimiento.consentimiento_id).where(
        m.Consentimiento.empresa_id == empresa_id, m.Consentimiento.activo))  # fmt: skip
    return {
        "score": score,
        "score_anterior": anteriores[-1].score if anteriores else None,
        "etapa_actual": etapa(score),
        "etapas": ETAPAS,
        "subindicadores": subindicadores,
        "historial": [{"mes": s.mes, "score": s.score} for s in anteriores] + [{"mes": mes, "score": score}],
        "rachas": _rachas(db, empresa_id, corte),
        "metas_activas": resumen_metas(db, empresa_id),
        "consentimiento_compartir_historial": consentimiento is not None,
        "fundamento": "Suma ponderada de 3 reglas: anotar todos los días (35 %), separar casa y negocio (40 %) e "
                      "impuestos al día (25 %).",
        "meta": construir_meta("score-reglas", MODELO_VERSION).model_dump(mode="json"),
    }
