"""Metas plantilla (A12): registrar_30_dias, sueldo_fijo, colchon_caja, apartar_para_pedido, reservar_impuestos.

`sueldo_fijo` con regla `monto_fijo` además crea el sueldo programado (movimientos_programados, es_sueldo = true),
cerrando el anterior para conservar el historial (índice único parcial: un solo sueldo activo).
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.core.reloj import hoy
from app.db import models as m
from app.schemas.common import EstadoMeta, Frecuencia, PlantillaMeta, TipoFlujo, TipoRegla

TITULOS = {
    "registrar_30_dias": "Anotar 30 días seguidos",
    "sueldo_fijo": "Ponerme un sueldo fijo",
    "colchon_caja": "Armar un colchón de caja",
    "apartar_para_pedido": "Apartar para el pedido",
    "reservar_impuestos": "Reservar para impuestos",
}
OBJETIVO_POR_DEFECTO = {"registrar_30_dias": Decimal("30")}
DIAS = {"lunes": 1, "martes": 2, "miercoles": 3, "miércoles": 3, "jueves": 4, "viernes": 5, "sabado": 6, "sábado": 6,
        "domingo": 7}  # fmt: skip


def _dia(valor) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, int):
        return valor if 1 <= valor <= 31 else None
    texto = str(valor).strip().lower()
    return int(texto) if texto.isdigit() else DIAS.get(texto)


def _detalle(meta: m.ReglaMeta) -> str:
    if meta.tipo_regla == TipoRegla.porcentaje_de_venta and meta.valor:
        return f"S/ 1 de cada S/ {round(1 / float(meta.valor))} que vendes"
    if meta.tipo_regla == TipoRegla.monto_fijo and meta.valor:
        return f"S/ {meta.valor:.0f} fijos"
    if meta.objetivo:
        return f"Objetivo: {meta.objetivo:.0f}"
    return TITULOS[meta.plantilla.value]


def resumen_metas(db: Session, empresa_id: str) -> list[dict]:
    metas = db.scalars(select(m.ReglaMeta).where(m.ReglaMeta.empresa_id == empresa_id,
                                                 m.ReglaMeta.estado == EstadoMeta.activa)
                       .order_by(m.ReglaMeta.meta_id)).all()  # fmt: skip
    return [{"meta_id": x.meta_id, "plantilla": x.plantilla.value, "titulo": TITULOS[x.plantilla.value],
             "detalle": _detalle(x), "acumulado": float(x.acumulado), "estado": x.estado.value} for x in metas]  # fmt: skip


def _crear_sueldo(db: Session, empresa_id: str, monto: Decimal, frecuencia: Frecuencia, dia: int | None) -> str:
    dia_hoy = hoy()
    anteriores = db.scalars(select(m.MovimientoProgramado).where(
        m.MovimientoProgramado.empresa_id == empresa_id, m.MovimientoProgramado.es_sueldo,
        m.MovimientoProgramado.activo)).all()  # fmt: skip
    for anterior in anteriores:
        anterior.activo = False
        anterior.fecha_fin = max(anterior.fecha_inicio, dia_hoy - timedelta(days=1))
    db.flush()
    categoria = db.scalars(select(m.Categoria).where(m.Categoria.nombre == "retiro personal")).first()
    prog = m.MovimientoProgramado(
        programado_id=nuevo_id(db, m.MovimientoProgramado, "PRG"), empresa_id=empresa_id,
        categoria_id=categoria.categoria_id, tipo=TipoFlujo.egreso, descripcion="Sueldo del dueño", monto=monto,
        frecuencia=frecuencia, dia_semana=(dia or 6) if frecuencia == Frecuencia.semanal else None,
        dia_mes=(dia or 1) if frecuencia in (Frecuencia.mensual, Frecuencia.quincenal) else None, es_sueldo=True,
        fecha_inicio=dia_hoy,
    )  # fmt: skip
    db.add(prog)
    db.flush()
    return prog.programado_id


def crear_meta(db: Session, empresa_id: str, plantilla: str, regla: dict | None = None,
               recordatorio: dict | None = None) -> dict:  # fmt: skip
    regla = regla or {}
    recordatorio = recordatorio or {}
    plantilla = PlantillaMeta(plantilla)
    tipo_regla = TipoRegla(regla["tipo"]) if regla.get("tipo") else None
    valor = Decimal(str(regla["valor"])) if regla.get("valor") is not None else None
    frecuencia = Frecuencia(recordatorio["frecuencia"]) if recordatorio.get("frecuencia") else None
    programado_id = None
    if plantilla == PlantillaMeta.sueldo_fijo and tipo_regla == TipoRegla.monto_fijo and valor:
        programado_id = _crear_sueldo(db, empresa_id, valor, frecuencia or Frecuencia.semanal,
                                      _dia(recordatorio.get("dia")))  # fmt: skip
    meta = m.ReglaMeta(
        meta_id=nuevo_id(db, m.ReglaMeta, "MET"), empresa_id=empresa_id, plantilla=plantilla,
        programado_id=programado_id, tipo_regla=tipo_regla, valor=valor, destino=regla.get("destino"),
        objetivo=OBJETIVO_POR_DEFECTO.get(plantilla.value), acumulado=Decimal("0"),
        recordatorio_frecuencia=frecuencia, recordatorio_dia=_dia(recordatorio.get("dia")), estado=EstadoMeta.activa,
        fecha_inicio=hoy(),
    )  # fmt: skip
    db.add(meta)
    db.commit()
    respuesta = {"meta_id": meta.meta_id, "estado": meta.estado.value, "titulo": TITULOS[plantilla.value]}
    if programado_id:
        respuesta["programado_id"] = programado_id
    return respuesta
