"""B10/B11 — motor de alertas (prioridades, causas, límite diario, horario silencioso, sin duplicar, acciones) y
preferencias. La BD de pruebas arranca sin alertas (el seed no las escribe). Los GET no escriben: las alertas se
guardan con POST /alertas/evaluar, al confirmar un movimiento o al accionar una alerta pendiente."""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from app.db import models as m
from app.services import alertas as motor
from tests._b_util import EMP, HOY, P, E, deuda_proveedor, reloj_fijo, tx  # noqa: F401

pytestmark = pytest.mark.db


def _filas(db, **filtro):
    return db.query(m.Alerta).filter_by(empresa_id=E, **filtro).order_by(m.Alerta.alerta_id).all()


def test_get_alertas_muestra_el_faltante_con_sus_causas_sin_escribir(client_db, db, reloj_fijo):
    items = client_db.get(f"{EMP}/alertas").json()["items"]
    assert [a["tipo"] for a in items] == ["faltante_caja", "pedido_excesivo", "retiro_excesivo", "fiado_vencido"]
    assert [a["prioridad"] for a in items] == [1, 2, 3, 6]
    f = items[0]
    assert (f["fecha_evento"], f["monto"], f["nivel_riesgo"], f["dias_para_evento"]) == ("2026-11-30", 650.0, "alto", 16)
    assert [(c["descripcion"], c["monto"]) for c in f["causas"]] == [
        ("Sacaste más de la caja de lo usual", 700.0), ("Pediste más de lo que vendes", 400.0), ("Fiados sin cobrar", 310.0)]
    assert -650 + sum(c["monto"] for c in f["causas"]) == 760  # "sin esas tres cerraría con S/ 760"
    assert f["titulo"] == "El 30/11 te faltarían S/ 650 para pagar a Distribuidora Andina"
    assert f["insight"] == "Para pagar S/ 2 400 a Distribuidora Andina te faltarían S/ 650."
    assert f["accion"] == {"tipo": "abrir_simulador", "texto_boton": "Ver qué puedo hacer", "payload": {"pedido_id": "PED-0012"}}
    assert f["canales"] == ["whatsapp", "app"] and f["meta"]["fallback_usado"] is True and 0 < f["probabilidad"] <= 1
    assert items[1]["monto"] == 400.0 and items[1]["accion"]["payload"] == {"pedido_id": "PED-0012"}
    assert items[2]["monto"] == 1100.0 and items[2]["titulo"] == "Con tus retiros ya sacaste S/ 1 900 este mes"
    fiado = items[3]
    assert fiado["titulo"] == "Sra. Carmen te debe S/ 120 y ya pasó la fecha" and fiado["monto"] == 120.0
    assert fiado["accion"] == {"tipo": "recordar_cliente", "texto_boton": "Recordar al cliente",
                               "payload": {"fiado_id": "FIA-0045", "cliente_id": "CLI-0102"}}  # fmt: skip
    assert not any("http" in (a["titulo"] + a["insight"]) for a in items)  # nunca enlaces
    # GET no escribe: nada en la tabla `alertas`, y las alertas salen marcadas como no guardadas con IDs estables
    assert _filas(db) == []
    assert all(a["persistida"] is False and a["alerta_id"].startswith("ALR-PEND.") for a in items)
    otra = client_db.get(f"{EMP}/alertas").json()["items"]
    assert [a["alerta_id"] for a in otra] == [a["alerta_id"] for a in items]
    assert _filas(db) == []


def test_post_evaluar_guarda_con_entidad_en_plural(client_db, db, reloj_fijo):
    nuevas = client_db.post(f"{EMP}/alertas/evaluar", json={}).json()["items"]
    assert len(nuevas) == 4 and all(a["persistida"] and a["alerta_id"].startswith("ALR-0") for a in nuevas)
    filas = _filas(db)
    assert [(f.tipo, f.entidad_tipo, f.entidad_id) for f in filas] == [
        ("faltante_caja", "deudas", "PED-0012"), ("pedido_excesivo", "deudas", "PED-0012"),
        ("retiro_excesivo", "mes", "2026-11"), ("fiado_vencido", "cuaderno_fiado", "FIA-0045")]  # fmt: skip
    despues = client_db.get(f"{EMP}/alertas").json()["items"]  # ahora salen las guardadas (mismos IDs)
    assert [a["alerta_id"] for a in despues] == [a["alerta_id"] for a in nuevas] and all(a["persistida"] for a in despues)
    assert client_db.post(f"{EMP}/alertas/evaluar", json={}).json() == {"items": []}  # no duplica
    assert len(_filas(db)) == 4


def test_limite_de_2_por_dia_y_sin_duplicar(client_db, db, reloj_fijo):
    client_db.post(f"{EMP}/alertas/evaluar", json={})
    enviadas = [f.enviada_en is not None for f in _filas(db)]
    assert enviadas == [True, True, False, False]  # la 3.ª y la 4.ª se guardan sin notificar (máximo 2 al día)
    client_db.get(f"{EMP}/alertas")
    assert client_db.post(f"{EMP}/alertas/evaluar", json={}).json() == {"items": []}
    assert len(_filas(db)) == 4


def test_horario_silencioso_guarda_sin_enviar(db, reloj_fijo):
    reloj_fijo(22, 30)
    nuevas = motor.evaluar_alertas(db, E)
    assert len(nuevas) == 4 and all(a.enviada_en is None for a in nuevas)
    reloj_fijo(6, 59)
    assert motor.evaluar_alertas(db, E, "compra_credito", deuda_proveedor(db, 2400, date(2026, 11, 30)).deuda_id)
    assert all(f.enviada_en is None for f in _filas(db))


def test_preferencias_cambian_el_limite_y_el_silencio(client_db, db, reloj_fijo):
    r = client_db.put(f"{EMP}/preferencias-alertas", json={"canales": ["app"], "max_por_dia": 1, "silencio_desde": "09:00",
                                                           "silencio_hasta": "09:30", "resumen_semanal": False})  # fmt: skip
    assert r.status_code == 200 and r.json()["max_por_dia"] == 1
    fila = db.get(m.PreferenciasAlertas, E)
    assert (fila.canales, fila.max_por_dia, fila.silencio_desde, fila.resumen_semanal) == (["app"], 1, time(9, 0), False)
    client_db.post(f"{EMP}/alertas/evaluar", json={})
    items = client_db.get(f"{EMP}/alertas").json()["items"]
    assert [a["enviada_en"] is not None for a in items] == [True, False, False, False] and items[0]["canales"] == ["app"]
    assert all(f.canal == "app" for f in _filas(db))


def test_preferencias_validan(client_db, reloj_fijo):
    base = {"canales": ["whatsapp"], "max_por_dia": 2, "silencio_desde": "21:00", "silencio_hasta": "07:00"}
    assert client_db.put(f"{EMP}/preferencias-alertas", json={**base, "silencio_desde": "25:00"}).status_code == 400
    assert client_db.put(f"{EMP}/preferencias-alertas", json={**base, "canales": ["paloma"]}).status_code == 400
    assert client_db.put(f"{P}/empresas/EMP-9999/preferencias-alertas", json=base).status_code == 404


def test_pedido_a_credito_dispara_faltante_y_pedido_excesivo(db, reloj_fijo):
    motor.evaluar_alertas(db, E)  # las del día ya existen (PED-0012)
    nuevo = deuda_proveedor(db, 2400, date(2026, 11, 30))
    nuevas = motor.evaluar_alertas(db, E, "compra_credito", nuevo.deuda_id)
    assert [a.tipo for a in nuevas] == ["faltante_caja", "pedido_excesivo"]
    faltante, pedido = nuevas
    assert faltante.monto == Decimal("3050.00") and faltante.accion.payload == {"pedido_id": nuevo.deuda_id}
    assert [c.monto for c in faltante.causas] == [700, 400, 310]
    assert pedido.monto == Decimal("400.00") and "S/ 400 más de lo que vendes hasta el 30/11" in pedido.titulo
    assert motor.evaluar_alertas(db, E, "compra_credito", nuevo.deuda_id) == []  # no se duplica


def test_reglas_segun_disparador(db, reloj_fijo):
    assert motor.evaluar_alertas(db, E, "venta") == []
    assert motor.evaluar_alertas(db, E, "cobro_fiado") == []
    assert [a.tipo for a in motor.evaluar_alertas(db, E, "retiro_personal")] == ["faltante_caja", "retiro_excesivo"]
    assert motor.evaluar_alertas(db, E, "gasto_negocio") == []  # el faltante ya está activo


def test_sin_problemas_no_hay_alertas(db, reloj_fijo):
    tx(db, "otro_ingreso", 5000, HOY)
    db.query(m.MovimientoProgramado).filter_by(es_sueldo=True).update({"monto": Decimal("1000")})
    assert motor.evaluar_alertas(db, E, "gasto_negocio") == []
    tipos = [a.tipo for a in motor.evaluar_alertas(db, E)]
    assert "faltante_caja" not in tipos and "retiro_excesivo" not in tipos


def test_obligacion_proxima_3_dias_antes(db, reloj_fijo):
    d = deuda_proveedor(db, 150, HOY + timedelta(days=2), inicio=date(2026, 11, 1))
    db.get(m.Impuesto, "IMP-0004").fecha_vencimiento = HOY + timedelta(days=3)
    deuda_proveedor(db, 99, HOY + timedelta(days=5), inicio=date(2026, 11, 1))  # todavía no
    db.flush()
    obligaciones = [a for a in motor.evaluar_alertas(db, E) if a.tipo == "obligacion_proxima"]
    assert [(a.prioridad, a.monto) for a in obligaciones] == [(4, Decimal("150.00")), (4, Decimal("20.00"))]
    assert obligaciones[0].titulo == "El lunes vence tu pago a Distribuidora Andina"
    assert obligaciones[0].accion.payload == {"pedido_id": d.deuda_id}
    assert obligaciones[1].titulo == "Tu RUS de noviembre vence el martes"


def test_acciones_sobre_una_alerta(client_db, db, reloj_fijo):
    client_db.post(f"{EMP}/alertas/evaluar", json={})
    ids = [a["alerta_id"] for a in client_db.get(f"{EMP}/alertas").json()["items"]]
    r0 = client_db.post(f"{P}/alertas/{ids[0]}/accion", json={"accion": "ejecutada", "detalle": "abrió simulador"}).json()
    assert r0 == {"estado": "atendida", "alerta_id": ids[0]}
    assert client_db.post(f"{P}/alertas/{ids[1]}/accion", json={"accion": "descartada"}).json()["estado"] == "descartada"
    assert client_db.post(f"{P}/alertas/{ids[2]}/accion", json={"accion": "posponer"}).json()["estado"] == "pospuesta"
    fila = db.get(m.Alerta, ids[0])
    assert (fila.estado, fila.accion_tomada) == ("atendida", "ejecutada: abrió simulador") and fila.fecha_accion
    assert db.get(m.Alerta, ids[2]).estado == "activa" and db.get(m.Alerta, ids[2]).enviada_en is None
    activas = client_db.get(f"{EMP}/alertas").json()["items"]
    assert [a["alerta_id"] for a in activas] == [ids[2], ids[3]]  # la consulta no revive lo atendido o descartado
    assert [a["alerta_id"] for a in client_db.get(f"{EMP}/alertas?estado=atendida").json()["items"]] == [ids[0]]
    assert client_db.post(f"{P}/alertas/ALR-9999/accion", json={"accion": "ejecutada"}).status_code == 404
    assert client_db.post(f"{P}/alertas/{ids[0]}/accion", json={"accion": "otra"}).status_code == 400
    assert client_db.get(f"{EMP}/alertas?estado=rara").status_code == 400


def test_accion_sobre_una_alerta_pendiente_la_guarda(client_db, db, reloj_fijo):
    items = client_db.get(f"{EMP}/alertas").json()["items"]
    pendiente = items[0]["alerta_id"]
    assert pendiente.startswith("ALR-PEND.") and _filas(db) == []
    r = client_db.post(f"{P}/alertas/{pendiente}/accion", json={"accion": "descartada"})
    assert r.status_code == 200 and r.json()["estado"] == "descartada" and r.json()["alerta_id"].startswith("ALR-0")
    fila = db.get(m.Alerta, r.json()["alerta_id"])
    assert (fila.tipo, fila.estado, fila.entidad_tipo, fila.entidad_id) == ("faltante_caja", "descartada", "deudas", "PED-0012")
    ahora = client_db.get(f"{EMP}/alertas").json()["items"]
    assert [a["tipo"] for a in ahora] == ["pedido_excesivo", "retiro_excesivo", "fiado_vencido"]  # no revive lo descartado
    assert client_db.post(f"{P}/alertas/ALR-PEND.EMP-0001.faltante_caja.PED-9999.2026-12-01/accion",
                          json={"accion": "ejecutada"}).status_code == 404  # ya no está vigente
    assert client_db.post(f"{P}/alertas/ALR-PEND.basura/accion", json={"accion": "ejecutada"}).status_code == 404
