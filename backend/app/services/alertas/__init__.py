"""★ INTERFAZ B — alertas. Firma congelada (PLAN §4.2)."""
from app.services.alertas.motor import (
    alertas, evaluar_alertas, guardar_preferencias, registrar_accion,
)

__all__ = ["evaluar_alertas", "alertas", "registrar_accion", "guardar_preferencias"]
