"""Utilidades de los tests de Dev B (no es un archivo de tests): insertar movimientos en la BD de pruebas
(dentro de la transacción que revierte la fixture `db`) y fijar el reloj."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.core import reloj
from app.core.config import settings
from app.core.ids import nuevo_id
from app.db import models as m

LIMA = ZoneInfo("America/Lima")
E = "EMP-0001"
HOY = date(2026, 11, 14)
P = settings.API_PREFIX
EMP = f"{P}/empresas/{E}"
CATEGORIA = {"venta": "CAT-01", "cobro_fiado": "CAT-07", "prestamo_recibido": "CAT-08", "otro_ingreso": "CAT-09",
             "compra": "CAT-10", "gasto_negocio": "CAT-17", "retiro_personal": "CAT-15", "pago_proveedor": "CAT-10",
             "pago_prestamo": "CAT-16", "pago_impuesto": "CAT-14"}  # fmt: skip


def dt(d: date, h: int = 12, mi: int = 0) -> datetime:
    return datetime.combine(d, time(h, mi), tzinfo=LIMA)


def tx(db, tipo: str, monto, dia: date = HOY, *, hora: int = 12, metodo: str = "efectivo", creado: datetime | None = None,
       anulada: bool = False, empresa_id: str = E, **vinculo) -> m.Transaccion:  # fmt: skip
    fh = dt(dia, hora)
    t = m.Transaccion(transaccion_id=nuevo_id(db, m.Transaccion, "MOV"), empresa_id=empresa_id, fecha_hora=fh, tipo=tipo,
                      categoria_id=CATEGORIA[tipo], monto=Decimal(str(monto)), metodo_pago=metodo,
                      afecta_caja=metodo != "credito", canal="manual", anulada=anulada,
                      creado_en=creado or fh + timedelta(minutes=1), **vinculo)  # fmt: skip
    db.add(t)
    db.flush()
    return t


def deuda_proveedor(db, monto, vence: date, inicio: date = HOY, *, proveedor_id: str = "PRV-0001", creado=None,
                    anulada: bool = False) -> m.Deuda:  # fmt: skip
    d = m.Deuda(deuda_id=nuevo_id(db, m.Deuda, "PED"), empresa_id=E, tipo="proveedor", proveedor_id=proveedor_id,
                monto_recibido=Decimal(str(monto)), monto_total_a_pagar=Decimal(str(monto)), fecha_inicio=inicio,
                fecha_vencimiento=vence, canal="voz")  # fmt: skip
    db.add(d)
    db.flush()
    tx(db, "compra", monto, inicio, metodo="credito", deuda_id=d.deuda_id, creado=creado, anulada=anulada)
    return d


def fiado(db, cliente_id: str, monto, dia: date = HOY, compromiso: date | None = None) -> m.CuadernoFiado:
    f = m.CuadernoFiado(fiado_id=nuevo_id(db, m.CuadernoFiado, "FIA"), empresa_id=E, cliente_id=cliente_id,
                        monto=Decimal(str(monto)), fecha_fiado=dia, fecha_compromiso=compromiso, canal="voz")  # fmt: skip
    db.add(f)
    db.flush()
    tx(db, "venta", monto, dia, metodo="credito", fiado_id=f.fiado_id)
    return f


@pytest.fixture
def reloj_fijo(monkeypatch):
    """Fija "hoy" = 14/11/2026 y "ahora" a una hora dada (por defecto 10:00): `reloj_fijo(22)` cambia la hora."""
    monkeypatch.setattr(settings, "FECHA_DEMO", HOY)

    def fijar(hora: int = 10, minuto: int = 0):
        monkeypatch.setattr(reloj, "ahora", lambda: dt(HOY, hora, minuto))

    fijar()
    return fijar
