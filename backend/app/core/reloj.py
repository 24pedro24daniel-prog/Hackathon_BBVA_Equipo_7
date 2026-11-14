"""Reloj de la app. Nunca usar date.today() ni datetime.now() directamente.

Con FECHA_DEMO definida, "hoy" es esa fecha (la demo de Pedro es reproducible) y "ahora"
es esa fecha con la hora real de Lima.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.core.config import settings


def zona() -> ZoneInfo:
    return ZoneInfo(settings.TZ)


def _ahora_real() -> datetime:
    return datetime.now(zona())


def hoy() -> date:
    return settings.FECHA_DEMO or _ahora_real().date()


def ahora() -> datetime:
    real = _ahora_real()
    if settings.FECHA_DEMO is None:
        return real
    return datetime.combine(settings.FECHA_DEMO, real.timetz())


def a_lima(dt: datetime) -> datetime:
    """Convierte a la zona de la app; un datetime sin zona se asume ya en hora de Lima."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=zona())
    return dt.astimezone(zona())


def inicio_del_dia(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=zona())
