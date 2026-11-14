"""Herramientas (function calling) que envuelven las funciones de B (contrato §7, PLAN_MVP.md §4.2).

obtener_resumen, obtener_forecast, obtener_alertas, obtener_fiados, obtener_pedidos, simular, obtener_salud,
crear_meta, explicar_concepto (+ chequear_pedido, extensión). Todas devuelven JSON (dict) listo para el
verificador de cifras: las cifras que el asistente puede decir son exactamente las que salen de aquí.
"""

from datetime import date
from decimal import Decimal

from app.core.reloj import hoy
from app.schemas.simulador import Accion
from app.services import alertas as motor_alertas
from app.services import finanzas
from app.services.asistente.plantillas import MICROEXPLICACIONES, PRESTAMO_INFORMAL_EJEMPLO


def _fn(nombre: str, descripcion: str, propiedades: dict | None = None, requeridos: list | None = None) -> dict:
    return {"type": "function", "function": {"name": nombre, "description": descripcion,
            "parameters": {"type": "object", "properties": propiedades or {}, "required": requeridos or []}}}  # fmt: skip


_ESTADO = {"type": "string"}
DEFINICIONES: list[dict] = [
    _fn("obtener_resumen", "Resumen del mes: caja, ingresos, egresos, retiros, fiados y pagos pendientes",
        {"periodo": {"type": "string", "description": "AAAA-MM"}}),
    _fn("obtener_forecast", "Proyección de caja día a día y día crítico", {"horizonte_dias": {"type": "integer"}}),
    _fn("obtener_alertas", "Alertas con sus causas", {"estado": _ESTADO}),
    _fn("obtener_fiados", "Fiados por cobrar", {"estado": _ESTADO}),
    _fn("obtener_pedidos", "Pedidos a crédito por pagar e impuestos", {"estado": _ESTADO}),
    _fn("simular", "Simula acciones sobre la caja", {"acciones": {"type": "array", "items": {"type": "object"}}},
        ["acciones"]),
    _fn("chequear_pedido", "Chequeo antes de un pedido a crédito",
        {"proveedor": {"type": "string"}, "monto": {"type": "number"}, "fecha_vencimiento": {"type": "string"}},
        ["proveedor", "monto", "fecha_vencimiento"]),
    _fn("obtener_salud", "Score de salud del negocio"),
    _fn("crear_meta", "Crea una meta plantilla", {"plantilla": {"type": "string"}, "regla": {"type": "object"}},
        ["plantilla"]),
    _fn("explicar_concepto", "Microexplicación fija revisada por el equipo", {"tema": {"type": "string"}}, ["tema"]),
]  # fmt: skip


class HerramientaDesconocida(Exception):
    pass


def ejecutar(db, empresa_id: str, nombre: str, args: dict) -> dict:
    args = args or {}
    if nombre == "obtener_resumen":
        return finanzas.resumen(db, empresa_id, args.get("periodo") or hoy().strftime("%Y-%m")).model_dump(mode="json")
    if nombre == "obtener_forecast":
        return finanzas.forecast(db, empresa_id, int(args.get("horizonte_dias") or 30)).model_dump(mode="json")
    if nombre == "obtener_alertas":
        return motor_alertas.alertas(db, empresa_id, args.get("estado") or "activa").model_dump(mode="json")
    if nombre == "obtener_fiados":
        return finanzas.fiados(db, empresa_id, args.get("estado") or "pendiente").model_dump(mode="json")
    if nombre == "obtener_pedidos":
        return finanzas.pedidos(db, empresa_id, args.get("estado") or "pendiente").model_dump(mode="json")
    if nombre == "simular":
        acciones = [a if isinstance(a, Accion) else Accion.model_validate(a) for a in args.get("acciones", [])]
        return finanzas.simular(db, empresa_id, acciones).model_dump(mode="json")
    if nombre == "chequear_pedido":
        return finanzas.chequeo_pedido(db, empresa_id, args["proveedor"], Decimal(str(args["monto"])),
                                       date.fromisoformat(str(args["fecha_vencimiento"]))).model_dump(mode="json")  # fmt: skip
    if nombre == "obtener_salud":
        from app.services.salud.score import calcular_score

        return calcular_score(db, empresa_id, persistir=False)
    if nombre == "crear_meta":
        from app.services.salud.metas import crear_meta

        return crear_meta(db, empresa_id, args["plantilla"], args.get("regla"), args.get("recordatorio"))
    if nombre == "explicar_concepto":
        tema = args.get("tema", "")
        resultado = {"tema": tema, "texto": MICROEXPLICACIONES.get(tema)}
        if tema == "prestamo_informal":
            resultado["ejemplo"] = dict(PRESTAMO_INFORMAL_EJEMPLO)
        return resultado
    raise HerramientaDesconocida(nombre)
