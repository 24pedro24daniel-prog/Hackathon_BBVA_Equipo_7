"""core/ids.py: formato de IDs con prefijo y siguiente ID libre en la BD."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.core.ids import formatear_id, nuevo_id, numero_de_id
from app.db import models as m
from app.schemas.common import Canal


@pytest.mark.parametrize(
    ("prefijo", "numero", "ancho", "esperado"),
    [("MOV", 123, None, "MOV-000123"), ("EMP", 1, None, "EMP-0001"), ("BOR", 7781, None, "BOR-7781"),
     ("PED", 12, 4, "PED-0012"), ("MOV", 5, 3, "MOV-005"), ("FIA", 12345, None, "FIA-12345")],
)  # fmt: skip
def test_formatear_id(prefijo, numero, ancho, esperado):
    assert formatear_id(prefijo, numero, ancho) == esperado


def test_numero_de_id():
    assert numero_de_id("MOV-000123") == 123
    with pytest.raises(ValueError):
        numero_de_id("mov-12")
    with pytest.raises(ValueError):
        formatear_id("MOV", -1)


@pytest.mark.db
def test_nuevo_id_sigue_al_maximo_del_seed(db):
    assert nuevo_id(db, m.CuadernoFiado, "FIA") == "FIA-0048"
    assert nuevo_id(db, m.Deuda, "PED") == "PED-0013"
    assert nuevo_id(db, m.Borrador, "BOR") == "BOR-0001"
    total = db.query(m.Transaccion).count()  # el seed numera MOV-000001…MOV-{total} sin huecos
    assert nuevo_id(db, m.Transaccion, "MOV") == formatear_id("MOV", total + 1)


@pytest.mark.db
def test_nuevo_id_ve_lo_agregado_en_la_sesion(db):
    primero = nuevo_id(db, m.Borrador, "BOR")
    db.add(m.Borrador(borrador_id=primero, empresa_id="EMP-0001", canal=Canal.texto, payload_propuesto={},
                      creado_en=datetime.fromisoformat("2026-11-14T10:42:00-05:00"), confianza=Decimal("0.9")))  # fmt: skip
    assert nuevo_id(db, m.Borrador, "BOR") == "BOR-0002"


@pytest.mark.db
def test_nuevo_id_ignora_ids_con_otro_formato(db):
    db.add(m.Borrador(borrador_id="BOR-9X", empresa_id="EMP-0001", canal=Canal.texto, payload_propuesto={},
                      creado_en=datetime.fromisoformat("2026-11-14T10:42:00-05:00")))  # fmt: skip
    assert nuevo_id(db, m.Borrador, "BOR") == "BOR-0001"
