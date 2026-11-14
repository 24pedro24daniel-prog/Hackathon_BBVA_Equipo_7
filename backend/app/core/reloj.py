"""Reloj del sistema. Usar SIEMPRE hoy()/ahora(), nunca date.today()/datetime.now().

Con FECHA_DEMO definido, "hoy" es esa fecha (la demo de Pedro es reproducible).
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def zona() -> ZoneInfo:
    return ZoneInfo(get_settings().TZ)


def hoy() -> date:
    s = get_settings()
    if s.FECHA_DEMO:
        return s.FECHA_DEMO
    return datetime.now(zona()).date()


def ahora() -> datetime:
    """Fecha-hora con zona. Con FECHA_DEMO: esa fecha + la hora real del reloj."""
    real = datetime.now(zona())
    s = get_settings()
    if s.FECHA_DEMO:
        return real.replace(year=s.FECHA_DEMO.year, month=s.FECHA_DEMO.month, day=s.FECHA_DEMO.day)
    return real
