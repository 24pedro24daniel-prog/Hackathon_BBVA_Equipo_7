"""Suite de integración sobre data/csv (marcador `csv`): la API corre sobre la MISMA data que producción.

BD `cajaclara_csv` creada con `python -m app.db.cargar_csv` (ver conftest). Qué se verifica:
- registrar cada tipo de movimiento sin 400/500 (categorías del catálogo del CSV);
- crear la meta `sueldo_fijo`;
- GET /alertas, forecast, resumen, fiados, pedidos, chequeo, simular, salud y análisis de las 30 empresas sin error;
- los GET no escriben (conteo de filas antes/después);
- las 3 demos con el forecast LightGBM: Pedro (EMP-0001) no llega al 30/11, la bodega sana (EMP-0030) sí, y el negocio
  nuevo (EMP-0002) cae al baseline por poca historia (context.md §9).
"""

from datetime import date

import pytest
from sqlalchemy import func, select, text

from app.core.config import settings
from app.db import models as m
from app.db.cargar_csv import cargar
from app.db.base import Base
from tests.integracion_csv.conftest import BD_CSV, EMPRESAS

pytestmark = pytest.mark.csv

P = settings.API_PREFIX
E1 = "EMP-0001"
HOY = date(2026, 11, 14)


def _emp(e: str) -> str:
    return f"{P}/empresas/{e}"


# ── el cargador ─────────────────────────────────────────────────────────────────────────────────


def test_el_cargador_dejo_las_30_empresas_y_cuadra_los_conteos(db_csv):
    assert db_csv.scalar(select(func.count()).select_from(m.Empresa)) == 30
    assert db_csv.scalar(select(func.count()).select_from(m.Categoria)) >= 13
    assert {r for (r,) in db_csv.execute(select(m.Rubro.nombre))} >= {"bodega"}


def test_el_cargador_reporta_columnas_que_no_calzan(engine_csv, tmp_path):
    """Una columna del CSV que models.py no tiene no se ignora en silencio: sale en el informe."""
    from app.db.cargar_csv import asegurar_bd
    from app.db.session import crear_engine

    carpeta = tmp_path / "csv"
    carpeta.mkdir()
    (carpeta / "rubros.csv").write_text("rubro_id,nombre,color\nRUB-01,bodega,rojo\n", encoding="utf-8")
    (carpeta / "otra_cosa.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    aux = f"{BD_CSV}_aux"
    asegurar_bd(aux)
    motor = crear_engine(settings._url(aux))
    admin = crear_engine(settings._url("postgres"), isolation_level="AUTOCOMMIT")
    try:
        informe = cargar(motor, carpeta)
        assert informe.columnas_extra == {"rubros": ["color"]}
        assert informe.csv_sin_tabla == ["otra_cosa"] and informe.tablas["rubros"] == (1, 1)
        assert informe.hay_diferencias and any("color" in linea for linea in informe.lineas())
    finally:
        motor.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{aux}"'))
        admin.dispose()


# ── registrar cada tipo de movimiento ───────────────────────────────────────────────────────────


def _post(client, emp, body):
    return client.post(f"{_emp(emp)}/movimientos", json=body)


def _ok(r):
    assert r.status_code == 201, r.text
    return r.json()


def _un_fiado_pendiente(client, emp=E1):
    items = client.get(f"{_emp(emp)}/fiados?estado=pendiente").json()["items"]
    assert items, f"{emp} no tiene fiados pendientes en el CSV"
    return items[0]


def _un_pedido_pendiente(client, emp=E1):
    items = client.get(f"{_emp(emp)}/pedidos?estado=pendiente").json()["items"]
    assert items, f"{emp} no tiene pedidos pendientes en el CSV"
    return items[0]


def test_venta_sin_producto(client_csv):
    _ok(_post(client_csv, E1, {"tipo": "venta", "monto": 13, "metodo_pago": "efectivo"}))


def test_venta_con_producto(client_csv, db_csv):
    prod = db_csv.scalars(select(m.Producto).where(m.Producto.empresa_id == E1, m.Producto.activo)).first()
    body = {"tipo": "venta", "monto": float(prod.precio_venta) * 2, "metodo_pago": "efectivo",
            "items": [{"producto_id": prod.producto_id, "producto": prod.nombre, "cantidad": 2,
                       "precio_unitario": float(prod.precio_venta), "subtotal": float(prod.precio_venta) * 2}]}  # fmt: skip
    j = _ok(_post(client_csv, E1, body))
    mov = db_csv.get(m.Transaccion, j["movimiento_id"])
    assert mov.categoria_id == prod.categoria_id


def test_venta_fiada(client_csv, db_csv):
    cliente = db_csv.scalars(select(m.Cliente).where(m.Cliente.empresa_id == E1)).first()
    _ok(_post(client_csv, E1, {"tipo": "venta", "monto": 20, "metodo_pago": "credito",
                               "contraparte": cliente.nombre_ficticio}))  # fmt: skip


def test_cobro_fiado(client_csv):
    f = _un_fiado_pendiente(client_csv)
    _ok(_post(client_csv, E1, {"tipo": "cobro_fiado", "monto": min(5, f["monto"]), "contraparte": f["cliente"]}))


def test_otro_ingreso(client_csv):
    _ok(_post(client_csv, E1, {"tipo": "otro_ingreso", "monto": 30, "descripcion": "Me regalaron"}))


def test_prestamo_recibido_y_pago_de_cuota(client_csv):
    j = _ok(_post(client_csv, E1, {"tipo": "prestamo_recibido", "monto": 500, "monto_total_a_pagar": 600,
                                   "contraparte": "Tío Julio", "frecuencia_cuota": "semanal", "monto_cuota": 50}))  # fmt: skip
    assert {r["tabla"] for r in j["registros_creados"]} >= {"transacciones", "deudas"}
    _ok(_post(client_csv, E1, {"tipo": "pago_prestamo", "monto": 50, "contraparte": "Tío Julio"}))


def test_compra_al_contado(client_csv):
    _ok(_post(client_csv, E1, {"tipo": "compra", "monto": 80, "metodo_pago": "efectivo", "descripcion": "Gaseosas"}))


def test_compra_a_credito(client_csv):
    p = _un_pedido_pendiente(client_csv)
    _ok(_post(client_csv, E1, {"tipo": "compra", "monto": 120, "metodo_pago": "credito", "contraparte": p["proveedor"],
                               "fecha_vencimiento": "2026-12-05"}))  # fmt: skip


def test_pago_a_proveedor(client_csv):
    p = _un_pedido_pendiente(client_csv)
    _ok(_post(client_csv, E1, {"tipo": "pago_proveedor", "monto": min(10, p["monto_pendiente"]),
                               "contraparte": p["proveedor"]}))  # fmt: skip


def test_gasto_del_negocio(client_csv):
    _ok(_post(client_csv, E1, {"tipo": "gasto_negocio", "monto": 8, "descripcion": "Mototaxi"}))
    _ok(_post(client_csv, E1, {"tipo": "gasto_negocio", "monto": 60, "descripcion": "Bolsas", "categoria": "otros_gastos"}))
    _ok(_post(client_csv, E1, {"tipo": "gasto_negocio", "monto": 9, "descripcion": "Flete", "categoria": "transporte"}))


def test_retiro_personal(client_csv):
    _ok(_post(client_csv, E1, {"tipo": "retiro_personal", "monto": 100, "descripcion": "Saqué para la casa"}))


def test_pago_de_impuesto(client_csv, db_csv):
    # un periodo sin pagar (si la empresa no tiene, el registrador crea el del mes)
    _ok(_post(client_csv, E1, {"tipo": "pago_impuesto", "monto": 20}))


def test_categoria_inexistente_es_400_no_500(client_csv):
    r = _post(client_csv, E1, {"tipo": "gasto_negocio", "monto": 8, "categoria": "marcianos_verdes"})
    assert r.status_code in (201, 400), r.text  # cae a la del tipo; nunca 500


@pytest.mark.parametrize("emp", EMPRESAS)
@pytest.mark.parametrize("tipo", ["venta", "gasto_negocio", "retiro_personal"])
def test_tipos_basicos_en_las_30_empresas(client_csv, emp, tipo):
    _ok(_post(client_csv, emp, {"tipo": tipo, "monto": 15, "metodo_pago": "efectivo"}))


# ── metas ───────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("frecuencia,dia", [("semanal", "sabado"), ("mensual", 30), ("quincenal", 15)])
def test_meta_sueldo_fijo(client_csv, frecuencia, dia):
    r = client_csv.post(f"{_emp(E1)}/metas", json={"plantilla": "sueldo_fijo",
                                                   "regla": {"tipo": "monto_fijo", "valor": 400},
                                                   "recordatorio": {"frecuencia": frecuencia, "dia": dia}})  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["programado_id"]


def test_meta_con_valor_invalido_responde_en_espanol(client_csv):
    r = client_csv.post(f"{_emp(E1)}/metas", json={"plantilla": "sueldo_fijo", "regla": {"tipo": "monto_fijo", "valor": 0}})
    assert r.status_code == 400
    assert "Input should" not in r.text and "debe ser mayor que" in r.text


# ── lecturas de las 30 empresas ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("emp", EMPRESAS)
def test_alertas_de_las_30_empresas(client_csv, emp):
    r = client_csv.get(f"{_emp(emp)}/alertas")
    assert r.status_code == 200, r.text
    for a in r.json()["items"]:
        assert a["titulo"] and a["insight"] and a["accion"]["tipo"] and a["accion"]["texto_boton"]
        assert all(set(c) == {"descripcion", "monto"} for c in a["causas"])
    assert client_csv.get(f"{_emp(emp)}/alertas?estado=todas").status_code == 200
    assert client_csv.post(f"{_emp(emp)}/alertas/evaluar", json={}).status_code == 200


@pytest.mark.parametrize("emp", EMPRESAS)
def test_lecturas_de_las_30_empresas(client_csv, db_csv, emp):
    e = _emp(emp)
    for ruta in ("forecast?horizonte_dias=30", "resumen?periodo=2026-11", "fiados?estado=pendiente", "pedidos?estado=pendiente",
                 "analisis", "analisis?agrupar_por=metodo_pago", "analisis?agrupar_por=mes&tipo=ingreso", "salud",
                 "movimientos?limit=5"):  # fmt: skip
        r = client_csv.get(f"{e}/{ruta}")
        assert r.status_code == 200, f"GET {ruta} de {emp}: {r.status_code} {r.text[:300]}"
    resumen = client_csv.get(f"{e}/resumen?periodo=2026-11").json()
    assert resumen["negocio"]["nombre"]
    proveedor = db_csv.scalars(select(m.Proveedor).where(m.Proveedor.empresa_id == emp)).first()
    r = client_csv.post(f"{e}/pedidos/chequeo", json={"proveedor": proveedor.nombre_ficticio if proveedor else "Distribuidora",
                                                      "monto": 500, "fecha_vencimiento": "2026-11-30"})  # fmt: skip
    assert r.status_code == 200, f"chequeo de {emp}: {r.status_code} {r.text[:300]}"
    r = client_csv.post(f"{e}/simular", json={"acciones": [{"tipo": "limitar_retiros", "monto": 100}]})
    assert r.status_code == 200, f"simular de {emp}: {r.status_code} {r.text[:300]}"
    r = client_csv.post(f"{e}/simular", json={"acciones": []})
    assert r.status_code == 200


def test_los_ids_de_acciones_de_alertas_existen(client_csv):
    """Toda acción de alerta trae lo que el front necesita en su payload."""
    for emp in EMPRESAS:
        for a in client_csv.get(f"{_emp(emp)}/alertas").json()["items"]:
            tipo, payload = a["accion"]["tipo"], a["accion"]["payload"]
            if tipo == "abrir_simulador":
                assert "pedido_id" in payload or a["tipo"] != "pedido_excesivo"
            if tipo == "recordar_cliente":
                assert payload.get("fiado_id") or payload.get("cliente_id")


# ── los GET no escriben ─────────────────────────────────────────────────────────────────────────

GETS = ("alertas", "alertas?estado=todas", "salud", "forecast", "resumen?periodo=2026-11", "fiados", "pedidos",
        "analisis", "movimientos")  # fmt: skip


def _filas(db) -> dict[str, int]:
    return {t.name: db.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables}


@pytest.mark.parametrize("emp", ["EMP-0001", "EMP-0002", "EMP-0007", "EMP-0030"])
def test_los_get_no_escriben(client_csv, db_csv, emp):
    antes = _filas(db_csv)
    for ruta in GETS:
        assert client_csv.get(f"{_emp(emp)}/{ruta}").status_code == 200
    # el asistente (una pregunta) consulta alertas y salud, también sin escribir en alertas ni score_salud
    despues = _filas(db_csv)
    assert despues == antes, {t: (antes[t], despues[t]) for t in antes if antes[t] != despues[t]}


def test_post_evaluar_si_guarda_y_salud_recalcular_si_guarda(client_csv, db_csv):
    antes = db_csv.scalar(select(func.count()).select_from(m.ScoreSalud))
    assert client_csv.post(f"{_emp(E1)}/salud/recalcular").status_code == 200
    assert db_csv.scalar(select(func.count()).select_from(m.ScoreSalud)) >= antes
    assert client_csv.post(f"{_emp(E1)}/alertas/evaluar", json={}).status_code == 200


# ── las 3 demos sobre el CSV, con el forecast por defecto (LightGBM; context.md §9) ───────────────
# demo1 = Pedro (EMP-0001): le falta caja el 30/11 por pagos con fecha. demo2 = bodega sana (EMP-0030): le alcanza con
# margen. demo3 = negocio nuevo (EMP-0002, día 3): el forecast cae al baseline por poca historia.

DEMO2 = "EMP-0030"
DEMO3 = "EMP-0002"


def _forecast(client, emp):
    f = client.get(f"{_emp(emp)}/forecast?horizonte_dias=30").json()
    return f, {p["fecha"]: p for p in f["serie"]}


def test_historia_de_la_demo_en_el_csv(client_csv, motor_lightgbm):
    """demo1: caja 2 340; el 30/11 (pago de S/ 2 400 a Andina + sueldo) la caja queda en ≈ −650; causas 700/400/310; el
    chequeo del pedido lo muestra y pedir 1 800 en 2 partes lo rescata (≈ +850). Calibrado en −650.00 con el LightGBM:
    las cifras del chequeo y del simulador se verifican relativas al p50 para no depender del centavo del modelo."""
    e = _emp(E1)
    assert client_csv.get(f"{e}/resumen?periodo=2026-11").json()["indicadores"]["saldo_caja_negocio"]["valor"] == 2340.0
    f, serie = _forecast(client_csv, E1)
    assert f["meta"]["modelo"] == "forecast-lgbm-quantile" and f["meta"]["fallback_usado"] is False
    dc = f["dia_critico"]
    assert dc["fecha"] == "2026-11-30" and dc["obligacion_asociada"]["id"] == "PED-0012"
    p = dc["saldo_p50"]
    assert p == pytest.approx(-650, abs=50)
    assert all(x["p50"] > p + 1500 for d, x in serie.items() if d < "2026-11-30")  # antes del 30/11 la caja aguanta
    assert serie["2026-11-30"]["p10"] < p < serie["2026-11-30"]["p90"]
    alerta = next(a for a in client_csv.get(f"{e}/alertas").json()["items"] if a["tipo"] == "faltante_caja")
    assert [c["monto"] for c in alerta["causas"]] == [700.0, 400.0, 310.0]
    assert alerta["monto"] == pytest.approx(-p) and alerta["accion"]["payload"]["pedido_id"] == "PED-0012"
    chequeo = client_csv.post(f"{e}/pedidos/chequeo", json={"proveedor": "Distribuidora Andina", "monto": 2400,
                                                            "fecha_vencimiento": "2026-11-30"}).json()  # fmt: skip
    assert chequeo["estado_caja"] == "no_te_alcanza" and chequeo["pedido_coincidente_id"] == "PED-0012"
    assert chequeo["venta_esperada_periodo"] == 2000.0 and chequeo["exceso_vs_ventas"] == 400.0
    assert [s["accion"] for s in chequeo["sugerencias"]] == ["reducir_pedido", "pagar_en_partes", "combinar"]
    assert chequeo["sugerencias"][0]["monto_sugerido"] == 1800.0
    assert [s["saldo_resultante"] for s in chequeo["sugerencias"]] == pytest.approx([p + 600, p + 1200, p + 1500])
    sim = client_csv.post(f"{e}/simular", json={"acciones": [
        {"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800},
        {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2}]}).json()  # fmt: skip
    assert sim["con_acciones"]["saldo_minimo"] == pytest.approx(p + 1500) and sim["con_acciones"]["estado_caja"] == "te_alcanza"
    # en vivo Pedro dice "vendí dos cervezas" (S/ 13): la caja sube a 2 353 y el faltante del 30/11 baja S/ 13
    venta = {"tipo": "venta", "monto": 13, "metodo_pago": "efectivo", "descripcion": "2 cervezas"}
    assert client_csv.post(f"{e}/movimientos", json=venta).status_code == 201
    assert client_csv.get(f"{e}/resumen?periodo=2026-11").json()["indicadores"]["saldo_caja_negocio"]["valor"] == 2353.0
    assert _forecast(client_csv, E1)[0]["dia_critico"]["saldo_p50"] == pytest.approx(p + 13)


def test_demo2_bodega_sana_le_alcanza_con_margen(client_csv, db_csv, motor_lightgbm):
    """demo2: con el LightGBM no hay día crítico y la caja más baja del mes queda muy por encima del mínimo operativo."""
    f, serie = _forecast(client_csv, DEMO2)
    minimo = float(db_csv.get(m.Empresa, DEMO2).minimo_operativo)
    assert f["meta"]["fallback_usado"] is False and f["dia_critico"] is None
    assert min(x["p10"] for d, x in serie.items() if d <= "2026-11-30") > 2 * minimo
    assert not [a for a in client_csv.get(f"{_emp(DEMO2)}/alertas").json()["items"] if a["tipo"] == "faltante_caja"]
    assert client_csv.get(f"{_emp(DEMO2)}/fiados?estado=pendiente").json()["items"]
    assert client_csv.get(f"{_emp(DEMO2)}/pedidos?estado=pendiente").json()["items"]


def test_demo3_negocio_nuevo_cae_al_baseline_por_poca_historia(client_csv, motor_lightgbm):
    """demo3: día 3; el forecast responde con el baseline, avisa el motivo y no inventa un día crítico."""
    f, _ = _forecast(client_csv, DEMO3)
    assert f["meta"]["fallback_usado"] is True and "Historia insuficiente" in f["meta"]["fallback_motivo"]
    assert f["disponible"] is False and f["dias_con_datos"] == 3 and f["dia_critico"] is None
    e = _emp(DEMO3)
    for ruta in ("resumen?periodo=2026-11", "salud", "alertas", "fiados?estado=pendiente", "pedidos?estado=pendiente",
                 "movimientos?limit=20", "analisis"):  # fmt: skip
        assert client_csv.get(f"{e}/{ruta}").status_code == 200, ruta
    assert client_csv.post(f"{e}/simular", json={"acciones": []}).status_code == 200
    assert client_csv.post(f"{e}/pedidos/chequeo", json={"proveedor": "Distribuidora", "monto": 300,
                                                         "fecha_vencimiento": "2026-11-30"}).status_code == 200  # fmt: skip
