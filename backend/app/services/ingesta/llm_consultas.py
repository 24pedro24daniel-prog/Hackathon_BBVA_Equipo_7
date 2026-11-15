"""Consulta de las trazas del LLM (`llm_llamadas`): listado con cursor y resumen por día y por origen.

`pct_fallback` = % de llamadas cuya salida no se usó: falló la llamada (estado ≠ ok) o el consumidor la rechazó
(`rechazada_validacion`, `rechazada_verificador`). Los días se agrupan en la zona de la app (America/Lima).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import Validacion
from app.core.paginacion import Pagina, recortar
from app.core.reloj import a_lima, inicio_del_dia
from app.db import models as m

L = m.LlmLlamada


def _filtros(empresa_id: str, desde: date | None, hasta: date | None) -> list:
    cond = [L.empresa_id == empresa_id]
    if desde:
        cond.append(L.creado_en >= inicio_del_dia(desde))
    if hasta:
        cond.append(L.creado_en < inicio_del_dia(hasta + timedelta(days=1)))
    return cond


def listar(db: Session, empresa_id: str, pagina: Pagina, *, origen: str | None = None, estado: str | None = None,
           desde: date | None = None, hasta: date | None = None, con_contenido: bool = False) -> dict:  # fmt: skip
    q = select(L).where(*_filtros(empresa_id, desde, hasta))
    if origen:
        q = q.where(L.origen == origen)
    if estado:
        q = q.where(L.estado == estado)
    if pagina.cursor:
        try:
            f_cursor = datetime.fromisoformat(pagina.cursor["f"])
            id_cursor = str(pagina.cursor["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Validacion("El cursor no es válido.", [{"campo": "cursor", "problema": "formato inválido"}]) from exc
        q = q.where(or_(L.creado_en < f_cursor, and_(L.creado_en == f_cursor, L.llamada_id < id_cursor)))
    filas = db.scalars(q.order_by(L.creado_en.desc(), L.llamada_id.desc()).limit(pagina.limit + 1)).all()
    pagina_filas, siguiente = recortar(filas, pagina.limit,
                                       lambda f: {"f": f.creado_en.isoformat(), "id": f.llamada_id})  # fmt: skip
    items = []
    for f in pagina_filas:
        item = {c: getattr(f, c) for c in (
            "llamada_id", "origen", "referencia_tipo", "referencia_id", "prompt_version", "proveedor",
            "modelo_solicitado", "modelo_respondido", "generation_id", "estado", "http_status", "error",
            "resultado_uso", "prompt_tokens", "completion_tokens", "total_tokens", "latencia_ms")}  # fmt: skip
        item["costo_usd"] = float(f.costo_usd) if f.costo_usd is not None else None
        item["creado_en"] = a_lima(f.creado_en)
        if con_contenido:
            item["request"], item["respuesta"] = f.request, f.respuesta
        items.append(item)
    return {"items": items, "next_cursor": siguiente}


def _agregados(db: Session, empresa_id: str, desde: date | None, hasta: date | None, *columnas) -> list:
    """Una fila por grupo (o una sola sin `columnas`) con los indicadores del resumen."""
    sin_uso = or_(L.estado != "ok", L.resultado_uso.in_(["rechazada_validacion", "rechazada_verificador"]))
    q = select(
        *columnas,
        func.count().label("llamadas"),
        func.count().filter(L.estado == "ok").label("ok"),
        func.sum(case((sin_uso, 1), else_=0)).label("sin_uso"),
        func.coalesce(func.sum(L.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(L.completion_tokens), 0).label("completion_tokens"),
        func.coalesce(func.sum(L.costo_usd), 0).label("costo_usd"),
        func.percentile_cont(0.5).within_group(L.latencia_ms).label("p50"),
        func.percentile_cont(0.95).within_group(L.latencia_ms).label("p95"),
    ).where(*_filtros(empresa_id, desde, hasta))
    if columnas:
        q = q.group_by(*columnas).order_by(*columnas)
    return db.execute(q).all()


def _fila(f) -> dict:
    n = f.llamadas or 0
    return {
        "llamadas": n,
        "ok": f.ok or 0,
        "errores": n - (f.ok or 0),
        "pct_fallback": round(100 * (f.sin_uso or 0) / n, 1) if n else 0.0,
        "prompt_tokens": int(f.prompt_tokens),
        "completion_tokens": int(f.completion_tokens),
        "costo_usd": float(Decimal(f.costo_usd).quantize(Decimal("0.00000001"))),
        "latencia_p50_ms": round(f.p50) if f.p50 is not None else None,
        "latencia_p95_ms": round(f.p95) if f.p95 is not None else None,
    }


def resumen(db: Session, empresa_id: str, *, desde: date | None = None, hasta: date | None = None) -> dict:
    dia = cast(func.timezone(settings.TZ, L.creado_en), Date).label("fecha")
    totales = _agregados(db, empresa_id, desde, hasta)[0]
    return {
        "desde": desde,
        "hasta": hasta,
        "totales": _fila(totales),
        "por_dia": [{"fecha": f.fecha, **_fila(f)} for f in _agregados(db, empresa_id, desde, hasta, dia)],
        "por_origen": [{"origen": f.origen, **_fila(f)} for f in _agregados(db, empresa_id, desde, hasta, L.origen)],
    }
