"""★ INTERFAZ B — funciones públicas que Dev A usa (confirmar, asistente, score). Firma congelada (PLAN §4.2)."""
from app.services.finanzas.analisis import analisis
from app.services.finanzas.chequeo import chequeo_pedido
from app.services.finanzas.consultas import estado_impuestos, fiados, pedidos, saldo_caja
from app.services.finanzas.forecast import crear_ajuste, forecast
from app.services.finanzas.resumen import resumen
from app.services.finanzas.simulador import simular

__all__ = [
    "saldo_caja", "fiados", "pedidos", "estado_impuestos", "resumen",
    "forecast", "crear_ajuste", "chequeo_pedido", "simular", "analisis",
]
