"""A2 — GET/POST /empresas/{id}/movimientos: filtros, paginación por cursor, saldo_post y registro manual."""

from decimal import Decimal

import pytest

from app.core.config import settings
from app.db import models as m

pytestmark = pytest.mark.db
P = settings.API_PREFIX
EMP = f"{P}/empresas/EMP-0001"


def test_listado_mas_reciente_primero_con_saldo_post(client_db):
    r = client_db.get(f"{EMP}/movimientos?limit=5")
    assert r.status_code == 200
    datos = r.json()
    items = datos["items"]
    assert len(items) == 5 and datos["next_cursor"]
    claves = [(i["fecha_hora"], i["movimiento_id"]) for i in items]
    assert claves == sorted(claves, reverse=True)
    # El último movimiento del seed (13/11) deja la caja en 2 340.
    assert items[0]["saldo_post"] == 2340.0
    assert items[0]["fecha_hora"].endswith("-05:00")
    assert set(items[0]) >= {"movimiento_id", "fecha_hora", "tipo", "categoria", "monto", "moneda", "metodo_pago",
                             "contraparte", "canal", "confianza_extraccion", "afecta_caja", "saldo_post",
                             "descripcion", "items"}


def test_saldo_post_consistente_entre_filas(client_db):
    items = client_db.get(f"{EMP}/movimientos?limit=30").json()["items"]
    for nuevo, previo in zip(items, items[1:]):
        delta = Decimal(str(nuevo["saldo_post"])) - Decimal(str(previo["saldo_post"]))
        esperado = Decimal("0")
        if nuevo["afecta_caja"]:
            signo = 1 if nuevo["tipo"] in ("venta", "cobro_fiado", "prestamo_recibido", "otro_ingreso") else -1
            esperado = signo * Decimal(str(nuevo["monto"]))
        assert delta == esperado, nuevo


def test_paginacion_por_cursor_sin_repetir(client_db):
    vistos, cursor = [], None
    for _ in range(3):
        url = f"{EMP}/movimientos?limit=20&desde=2026-11-12" + (f"&cursor={cursor}" if cursor else "")
        datos = client_db.get(url).json()
        vistos += [i["movimiento_id"] for i in datos["items"]]
        cursor = datos["next_cursor"]
        if not cursor:
            break
    assert len(vistos) == len(set(vistos))
    todos = client_db.get(f"{EMP}/movimientos?limit=200&desde=2026-11-12").json()["items"]
    assert vistos == [i["movimiento_id"] for i in todos][: len(vistos)]


def test_filtros_tipo_categoria_canal_y_fechas(client_db):
    ret = client_db.get(f"{EMP}/movimientos?tipo=retiro_personal&desde=2026-11-01&hasta=2026-11-13&limit=200").json()
    assert ret["items"] and all(i["tipo"] == "retiro_personal" for i in ret["items"])
    assert sum(i["monto"] for i in ret["items"]) == 1900.0
    beb = client_db.get(f"{EMP}/movimientos?categoria=bebidas&limit=50").json()["items"]
    assert beb and all(i["categoria"] == "bebidas" for i in beb)
    manual = client_db.get(f"{EMP}/movimientos?canal=manual&limit=20").json()["items"]
    assert manual and all(i["canal"] == "manual" and i["confianza_extraccion"] is None for i in manual)
    assert client_db.get(f"{EMP}/movimientos?hasta=2026-08-14").json() == {"items": [], "next_cursor": None}


def test_contraparte_de_fiados_y_pedidos(client_db):
    fiados = client_db.get(f"{EMP}/movimientos?tipo=venta&desde=2026-11-05&hasta=2026-11-05&limit=200").json()["items"]
    rosa = [i for i in fiados if i["metodo_pago"] == "credito"]
    assert rosa and rosa[0]["contraparte"] == "Vecina Rosa" and rosa[0]["afecta_caja"] is False
    pedido = client_db.get(f"{EMP}/movimientos?tipo=compra&desde=2026-11-13&hasta=2026-11-13&limit=50").json()["items"]
    assert any(i["contraparte"] == "Distribuidora Andina" and i["metodo_pago"] == "credito" for i in pedido)


def test_cursor_invalido_400(client_db):
    assert client_db.get(f"{EMP}/movimientos?cursor=xxx").status_code == 400


def test_empresa_inexistente_404(client_db):
    assert client_db.get(f"{P}/empresas/EMP-9999/movimientos").status_code == 404


def test_registro_manual_201_y_aparece_primero(client_db, db):
    r = client_db.post(f"{EMP}/movimientos", json={"tipo": "venta", "monto": 13.0, "metodo_pago": "efectivo",
                                                   "fecha_hora": "2026-11-14T10:42:00-05:00"})  # fmt: skip
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["registros_creados"] == [{"tabla": "transacciones", "id": cuerpo["movimiento_id"]}]
    assert set(cuerpo) >= {"movimiento_id", "registros_creados", "alertas_disparadas", "saldo_caja_negocio"}
    tx = db.get(m.Transaccion, cuerpo["movimiento_id"])
    assert tx.canal == "manual" and tx.borrador_id is None and tx.confianza_extraccion is None
    primero = client_db.get(f"{EMP}/movimientos?limit=1").json()["items"][0]
    assert primero["movimiento_id"] == cuerpo["movimiento_id"] and primero["saldo_post"] == 2353.0


def test_registro_manual_idempotente(client_db, db):
    cuerpo = {"tipo": "retiro_personal", "monto": 50.0, "metodo_pago": "efectivo"}
    h = {"Idempotency-Key": "manual-1"}
    a = client_db.post(f"{EMP}/movimientos", json=cuerpo, headers=h)
    b = client_db.post(f"{EMP}/movimientos", json=cuerpo, headers=h)
    assert a.status_code == b.status_code == 201 and a.json()["movimiento_id"] == b.json()["movimiento_id"]
    assert db.query(m.Transaccion).filter_by(tipo="retiro_personal", monto=Decimal("50.00"), canal="manual").count() == 1
    otro = client_db.post(f"{EMP}/movimientos", json={**cuerpo, "monto": 60.0}, headers=h)
    assert otro.status_code == 409


def test_registro_manual_invalido(client_db):
    assert client_db.post(f"{EMP}/movimientos", json={"tipo": "venta", "monto": 0}).status_code == 400
    r = client_db.post(f"{EMP}/movimientos", json={"tipo": "venta", "monto": 10, "metodo_pago": "credito"})
    assert r.status_code == 400 and r.json()["error"]["detalles"][0]["campo"] == "contraparte"


def test_listado_trae_descripcion_y_detalle(client_db):
    items = client_db.get(f"{EMP}/movimientos?desde=2026-11-13&hasta=2026-11-13&tipo=compra&limit=50").json()["items"]
    pedido = next(i for i in items if i["metodo_pago"] == "credito")
    assert pedido["descripcion"] == "Pedido a Distribuidora Andina"
    lineas = {ln["producto"]: ln for ln in pedido["items"]}
    assert set(lineas) == {"Cerveza 620 ml", "Gaseosa 500 ml"}
    assert lineas["Cerveza 620 ml"] == {"producto": "Cerveza 620 ml", "cantidad": 350.0, "precio_unitario": 4.8,
                                        "subtotal": 1680.0}  # fmt: skip
    assert sum(ln["subtotal"] for ln in pedido["items"]) == pedido["monto"] == 2400.0
    sin_detalle = next(i for i in items if i["descripcion"] == "Compra en el mercado mayorista")
    assert sin_detalle["items"] == []


def test_movimientos_de_pedro_dia_3(client_db):
    d = client_db.get(f"{P}/empresas/EMP-0002/movimientos?limit=50").json()
    assert len(d["items"]) == 13 and d["next_cursor"] is None
    assert d["items"][0]["saldo_post"] == 1120.0
    cerveza = next(i for i in d["items"] if i["items"])
    assert cerveza["items"] == [{"producto": "Cerveza 620 ml", "cantidad": 2.0, "precio_unitario": 6.5, "subtotal": 13.0}]
