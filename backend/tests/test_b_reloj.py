"""core/reloj.py: FECHA_DEMO y zona America/Lima."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core import reloj
from app.core.config import settings

LIMA = ZoneInfo("America/Lima")


def test_hoy_usa_fecha_demo(monkeypatch):
    monkeypatch.setattr(settings, "FECHA_DEMO", date(2026, 11, 14))
    assert reloj.hoy() == date(2026, 11, 14)


def test_ahora_usa_fecha_demo_con_hora_de_lima(monkeypatch):
    monkeypatch.setattr(settings, "FECHA_DEMO", date(2026, 11, 14))
    ahora = reloj.ahora()
    assert ahora.date() == date(2026, 11, 14)
    assert ahora.utcoffset() == timedelta(hours=-5)


def test_sin_fecha_demo_usa_la_fecha_real_de_lima(monkeypatch):
    monkeypatch.setattr(settings, "FECHA_DEMO", None)
    fijo = datetime(2027, 1, 1, 3, 0, tzinfo=timezone.utc)  # en Lima todavía es 31/12
    monkeypatch.setattr(reloj, "_ahora_real", lambda: fijo.astimezone(LIMA))
    assert reloj.hoy() == date(2026, 12, 31)
    assert reloj.ahora() == fijo


def test_a_lima_convierte_y_asume_lima_si_no_hay_zona():
    utc = datetime(2026, 11, 14, 15, 42, tzinfo=timezone.utc)
    assert reloj.a_lima(utc).hour == 10
    ingenuo = datetime(2026, 11, 14, 10, 42)
    assert reloj.a_lima(ingenuo).utcoffset() == timedelta(hours=-5)


def test_inicio_del_dia_en_lima():
    inicio = reloj.inicio_del_dia(date(2026, 11, 30))
    assert inicio.isoformat() == "2026-11-30T00:00:00-05:00"


def test_zona_configurada_es_lima():
    assert str(reloj.zona()) == "America/Lima"
