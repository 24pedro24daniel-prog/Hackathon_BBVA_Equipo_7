"""B9 — simulador determinístico: cada acción, combinaciones y la ventana de evaluación."""

import random
from datetime import date
from decimal import Decimal

import pytest

from app.core.errors import Validacion
from app.schemas.simulador import Accion
from app.services import finanzas
from app.services.finanzas import proyeccion as fc
from tests._b_util import EMP, E, reloj_fijo  # noqa: F401

pytestmark = pytest.mark.db
D30 = date(2026, 11, 30)


def _sim(db, *acciones):
    return finanzas.simular(db, E, [Accion.model_validate(a) for a in acciones])


def _base(db):
    return {p.fecha: p.p50 for p in finanzas.forecast(db, E, 30).serie}


def test_sin_acciones_es_el_dia_critico(db, reloj_fijo):
    s = _sim(db, {"tipo": "ajustar_gasto", "monto": 0})
    assert (s.sin_acciones.saldo_minimo, s.sin_acciones.fecha, s.sin_acciones.estado_caja) == (
        Decimal("-650.00"), D30, "no_te_alcanza")
    assert s.con_acciones == s.sin_acciones and s.mejora == 0
    assert len(s.serie_con_acciones) == 30 and s.ventana_hasta == D30
    assert s.meta.modelo == "simulador-deterministico"


@pytest.mark.parametrize(("acciones", "esperado", "estado"), [
    ([{"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800}], "-50.00", "no_te_alcanza"),
    ([{"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 2000}], "-250.00", "no_te_alcanza"),
    ([{"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2}], "550.00", "justo"),
    ([{"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800},
      {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2, "fechas": ["2026-11-30", "2026-12-15"]}],
     "850.00", "te_alcanza"),
    ([{"tipo": "cobrar_fiados", "fiado_ids": ["FIA-0045", "FIA-0046", "FIA-0047"], "fecha": "2026-11-20"}],
     "-340.00", "no_te_alcanza"),
    ([{"tipo": "cobrar_fiados", "fiado_ids": ["FIA-0045"]}], "-530.00", "no_te_alcanza"),
    ([{"tipo": "ajustar_gasto", "monto": 100, "fecha": "2026-11-20"}], "-750.00", "no_te_alcanza"),
    # contrato §4.6: pedir 1 800 + 2 partes + cobrar los fiados el 20/11 → 1 160
    ([{"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800},
      {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2, "fechas": ["2026-11-30", "2026-12-15"]},
      {"tipo": "cobrar_fiados", "fiado_ids": ["FIA-0045", "FIA-0046", "FIA-0047"], "fecha": "2026-11-20"}],
     "1160.00", "te_alcanza"),
])  # fmt: skip
def test_acciones_y_combinaciones(db, reloj_fijo, acciones, esperado, estado):
    s = _sim(db, *acciones)
    assert s.con_acciones.saldo_minimo == Decimal(esperado) and s.con_acciones.fecha == D30
    assert s.con_acciones.estado_caja == estado
    assert s.mejora == Decimal(esperado) - Decimal("-650.00")


def test_el_orden_de_las_acciones_no_importa(db, reloj_fijo):
    acciones = [{"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2},
                {"tipo": "cobrar_fiados", "fecha": "2026-11-20"},
                {"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800}]  # fmt: skip
    resultados = set()
    for _ in range(3):
        random.shuffle(acciones)
        resultados.add(_sim(db, *acciones).con_acciones.saldo_minimo)
    assert resultados == {Decimal("1160.00")}


def test_pagar_en_partes_dentro_del_horizonte_alarga_la_ventana(db, reloj_fijo):
    base = _base(db)
    s = _sim(db, {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2, "fechas": ["2026-11-30", "2026-12-10"]})
    # base paga 2 400 el 30/11; ahora 1 200 el 30/11 y 1 200 el 10/12 → desde el 10/12 queda igual que la base
    ajustado = {d: v + (1200 if d >= D30 else 0) - (1200 if d >= date(2026, 12, 10) else 0) for d, v in base.items()}
    esperado = min(v for d, v in ajustado.items() if d <= date(2026, 12, 10))
    assert s.ventana_hasta == date(2026, 12, 10) and s.con_acciones.saldo_minimo == esperado
    assert s.con_acciones.fecha == date(2026, 12, 10) and s.con_acciones.saldo_minimo < 0  # no se esconde el problema
    assert s.notas == []


def test_diferir_pago(db, reloj_fijo):
    base = _base(db)
    dentro = _sim(db, {"tipo": "diferir_pago", "pedido_id": "PED-0012", "fecha": "2026-12-05"})
    ajustado = {d: v + (2400 if d < date(2026, 12, 5) else 0) for d, v in base.items()}
    assert dentro.con_acciones.saldo_minimo == min(v for d, v in ajustado.items() if d <= date(2026, 12, 5))
    fuera = _sim(db, {"tipo": "diferir_pago", "pedido_id": "PED-0012", "fecha": "2026-12-20"})
    assert fuera.notas and "20/12" in fuera.limites
    assert fuera.con_acciones.saldo_minimo == min(v + 2400 if d >= D30 else v for d, v in base.items() if d <= D30)


def test_limitar_retiros(db, reloj_fijo):
    proy = fc.proyectar(db, E, None, 30)
    s = _sim(db, {"tipo": "limitar_retiros", "monto": 0})
    dias = [d for d in proy.fechas if d <= D30]
    mejora = sum(proy.media_ret[d.weekday()] for d in dias)
    assert mejora > 0 and s.mejora == pytest.approx(mejora, abs=Decimal("0.05"))
    assert _sim(db, {"tipo": "limitar_retiros", "monto": 100000}).mejora == 0


def test_pedido_por_defecto_y_errores(db, reloj_fijo):
    assert _sim(db, {"tipo": "pagar_en_partes", "partes": 2}).con_acciones.saldo_minimo == Decimal("550.00")
    with pytest.raises(Validacion):
        _sim(db, {"tipo": "reducir_pedido", "pedido_id": "PED-0001", "nuevo_monto": 10})  # ya pagado
    with pytest.raises(Validacion):
        _sim(db, {"tipo": "cobrar_fiados", "fiado_ids": ["FIA-0001"]})
    with pytest.raises(Validacion):
        _sim(db, {"tipo": "reducir_pedido", "pedido_id": "PED-0012"})


def test_endpoint_simular(client_db, reloj_fijo):
    body = {"acciones": [{"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800},
                         {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2}]}  # fmt: skip
    j = client_db.post(f"{EMP}/simular", json=body).json()
    assert (j["sin_acciones"]["saldo_minimo"], j["con_acciones"]["saldo_minimo"], j["mejora"]) == (-650.0, 850.0, 1500.0)
    assert client_db.post(f"{EMP}/simular", json={"acciones": [{"tipo": "reducir_pedido", "pedido_id": "PED-9",
                                                                "nuevo_monto": 1}]}).status_code == 400  # fmt: skip
    assert client_db.post(f"{EMP}/simular", json={"acciones": []}).status_code == 400
