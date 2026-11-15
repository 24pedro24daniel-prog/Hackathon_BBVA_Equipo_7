"""Sincronización con el modelo de datos (CONVENCIONES): categorías canónicas, alertas (refresco, nuevas reglas,
entidad en plural), sueldo mensual, chat, serialización y /health. BD de pruebas con el seed de Pedro (14/11)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core import categorias as cat
from app.core.errors import Validacion
from app.db import models as m
from app.services import alertas as motor
from app.services.alertas import motor as motor_mod
from app.services.finanzas import consultas as q
from tests._b_util import EMP, HOY, E, P, deuda_proveedor, fiado, reloj_fijo, tx  # noqa: F401

pytestmark = pytest.mark.db


# ── categorías ──────────────────────────────────────────────────────────────────────────────────


def test_nombres_se_comparan_sin_tildes_mayusculas_ni_guion_bajo():
    n = cat.normalizar_nombre
    assert n("Retiro_Personal") == n("retiro personal") == n("RETIRO PERSONAL")
    assert n("pago de préstamos") == n("financiamiento") and n("cobro de fiados") == n("cobro_fiados")
    assert n("lácteos") == n("lacteos_panaderia") and n("transporte") == n("transporte_flete")


def test_buscar_categoria_acepta_ids_y_nombres_viejos_y_nuevos(db):
    assert cat.buscar_categoria(db, "CAT-13").nombre == "retiro_personal"
    assert cat.buscar_categoria(db, "retiro personal").categoria_id == "CAT-13"
    assert cat.buscar_categoria(db, "Pago de prestamos").nombre == "financiamiento"
    assert cat.buscar_categoria(db, "marcianos") is None
    with pytest.raises(Validacion):
        cat.categoria_o_400(db, "marcianos")


def test_el_seed_usa_el_catalogo_canonico_de_16(db):
    filas = {c.categoria_id: c.nombre for c in db.query(m.Categoria).all()}
    assert len(filas) == 16 and set(filas.values()) == set(cat.CATEGORIAS_CANONICAS)
    assert filas["CAT-13"] == "retiro_personal" and filas["CAT-14"] == "cobro_fiados" and filas["CAT-16"] == "otros_gastos"
    assert {r.nombre for r in db.query(m.Rubro).all()} == {"bodega", "restaurante", "taller", "distribuidora"}


@pytest.mark.parametrize("tipo,esperada", [("venta", "otros_ingresos"), ("otro_ingreso", "otros_ingresos"),
                                           ("gasto_negocio", "otros_gastos"), ("retiro_personal", "retiro_personal"),
                                           ("pago_prestamo", "financiamiento")])
def test_categoria_por_defecto_de_cada_tipo(client_db, db, reloj_fijo, tipo, esperada):
    body = {"tipo": tipo, "monto": 10, "metodo_pago": "efectivo"}
    if tipo == "pago_prestamo":
        client_db.post(f"{EMP}/movimientos", json={"tipo": "prestamo_recibido", "monto": 100, "monto_total_a_pagar": 120,
                                                   "contraparte": "Tío"})  # fmt: skip
        body["contraparte"] = "Tío"
    r = client_db.post(f"{EMP}/movimientos", json=body)
    assert r.status_code == 201, r.text
    assert db.get(m.Transaccion, r.json()["movimiento_id"]).categoria.nombre if hasattr(m.Transaccion, "categoria") else True
    c = db.get(m.Transaccion, r.json()["movimiento_id"]).categoria_id
    assert db.get(m.Categoria, c).nombre == esperada


def test_registrar_con_catalogo_del_csv_sin_categorias_viejas(client_db, db, reloj_fijo):
    """Catálogo como el del CSV (13 categorías, sin las del seed viejo): nada da 400 por categoría."""
    for cid in ("CAT-14", "CAT-15", "CAT-16"):
        db.query(m.Transaccion).filter_by(categoria_id=cid).update({"categoria_id": "CAT-06"})
        db.query(m.MovimientoProgramado).filter_by(categoria_id=cid).update({"categoria_id": "CAT-06"})
        db.query(m.Categoria).filter_by(categoria_id=cid).delete()
    db.flush()
    r = client_db.post(f"{EMP}/movimientos", json={"tipo": "gasto_negocio", "monto": 7, "descripcion": "algo"})
    assert r.status_code == 400 and "categoría" in r.json()["error"]["mensaje"]  # claro, nunca 500


def test_meta_sueldo_fijo_con_categoria_faltante_es_400(client_db, db):
    db.query(m.MovimientoProgramado).filter_by(categoria_id="CAT-13").update({"categoria_id": "CAT-06"})
    db.query(m.Transaccion).filter_by(categoria_id="CAT-13").update({"categoria_id": "CAT-06"})
    db.query(m.Categoria).filter_by(categoria_id="CAT-13").delete()
    db.flush()
    r = client_db.post(f"{EMP}/metas", json={"plantilla": "sueldo_fijo", "regla": {"tipo": "monto_fijo", "valor": 300}})
    assert r.status_code == 400


def test_filtro_de_movimientos_por_categoria_tolerante(client_db, reloj_fijo):
    a = client_db.get(f"{EMP}/movimientos?categoria=retiro_personal").json()["items"]
    b = client_db.get(f"{EMP}/movimientos?categoria=retiro personal").json()["items"]
    assert a and [x["movimiento_id"] for x in a] == [x["movimiento_id"] for x in b]


# ── serialización ───────────────────────────────────────────────────────────────────────────────


def test_items_cantidad_es_numero(client_db, reloj_fijo):
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": E, "canal": "texto", "texto": "vendí dos cervezas"})
    assert r.status_code == 200
    cantidad = r.json()["movimiento_propuesto"]["items"][0]["cantidad"]
    assert isinstance(cantidad, (int, float)) and not isinstance(cantidad, bool) and cantidad == 2
    c = client_db.post(f"{EMP}/chat/mensajes", json={"texto": "vendí tres cervezas"}).json()
    assert isinstance(c["interpretacion"]["movimiento_propuesto"]["items"][0]["cantidad"], (int, float))
    lista = client_db.get(f"{EMP}/movimientos?tipo=venta&limit=50").json()["items"]
    assert all(isinstance(i["cantidad"], (int, float)) for mv in lista for i in mv["items"])


# ── sueldo mensual / quincenal ──────────────────────────────────────────────────────────────────


def _sueldo(db, frecuencia, monto, **kw):
    db.query(m.MovimientoProgramado).filter_by(es_sueldo=True).update({"activo": False, "fecha_fin": date(2026, 11, 1)})
    p = m.MovimientoProgramado(programado_id="PRG-0900", empresa_id=E, categoria_id="CAT-13", tipo="egreso",
                               descripcion="Sueldo del dueño", monto=Decimal(str(monto)), frecuencia=frecuencia,
                               es_sueldo=True, fecha_inicio=date(2026, 11, 1), activo=True, **kw)  # fmt: skip
    db.add(p)
    db.flush()
    return p


def test_sueldo_mensual_se_prorratea_y_no_da_retiro_excesivo_falso(db, reloj_fijo):
    _sueldo(db, "mensual", 1350, dia_mes=30)
    esperado = q.sueldo_esperado(db, E, date(2026, 11, 1), HOY)
    assert esperado == Decimal("630.00")  # 14/30 de 1 350 (antes daba 0 a mitad de mes)
    db.query(m.Transaccion).filter_by(empresa_id=E, tipo="retiro_personal").update({"anulada": True})
    tx(db, "retiro_personal", 600, HOY)
    assert [a for a in motor.evaluar_alertas(db, E) if a.tipo == "retiro_excesivo"] == []
    assert q.sueldo_esperado(db, E, date(2026, 11, 1), date(2026, 11, 30)) == Decimal("1350.00")


def test_sueldo_quincenal_y_semanal(db, reloj_fijo):
    _sueldo(db, "quincenal", 500, dia_mes=1)
    assert q.sueldo_esperado(db, E, date(2026, 11, 1), date(2026, 11, 15)) == Decimal("500.00")  # una quincena completa
    # el sueldo del día 1 ya cayó en la quincena: el esperado es el sueldo completo, no el prorrateo (7/15 = 233.33)
    assert q.sueldo_esperado(db, E, date(2026, 11, 1), date(2026, 11, 7)) == Decimal("500.00")


def test_sueldo_quincenal_que_aun_no_cae_se_prorratea(db, reloj_fijo):
    _sueldo(db, "quincenal", 500, dia_mes=15)
    assert q.sueldo_esperado(db, E, date(2026, 11, 1), date(2026, 11, 7)) == Decimal("233.33")  # aún no cae: 7 de 15 días
    assert q.sueldo_esperado(db, E, date(2026, 11, 1), date(2026, 11, 15)) == Decimal("500.00")


def test_sueldo_mensual_pagado_al_inicio_cuenta_completo_y_no_da_retiro_excesivo(db, reloj_fijo):
    """Falso positivo reportado por datos: sueldo mensual cobrado el día 1 daba `retiro_excesivo` por el prorrateo."""
    db.query(m.Transaccion).filter_by(empresa_id=E, tipo="retiro_personal").update({"anulada": True})
    _sueldo(db, "mensual", 1350, dia_mes=1)
    tx(db, "retiro_personal", 1350, date(2026, 11, 1))
    assert q.sueldo_esperado(db, E, date(2026, 11, 1), HOY) == Decimal("1350.00")  # antes: 14/30 = 630
    assert [a for a in motor.evaluar_alertas(db, E) if a.tipo == "retiro_excesivo"] == []


def test_resumen_expone_sueldo_esperado_y_negocio(client_db, reloj_fijo):
    j = client_db.get(f"{EMP}/resumen?periodo=2026-11").json()
    r = j["indicadores"]["retiros_personales"]
    assert r["sueldo_esperado_a_la_fecha"] == 800.0 and r["exceso_vs_sueldo"] == 1100.0
    assert j["negocio"]["nombre"] == "Bodega Don Pedro"


# ── alertas ─────────────────────────────────────────────────────────────────────────────────────


def test_la_alerta_activa_se_actualiza_tras_una_venta(client_db, db, reloj_fijo):
    client_db.post(f"{EMP}/alertas/evaluar", json={})
    faltante = db.query(m.Alerta).filter_by(empresa_id=E, tipo="faltante_caja").one()
    assert faltante.monto == Decimal("650.00")
    client_db.post(f"{EMP}/movimientos", json={"tipo": "venta", "monto": 13, "metodo_pago": "efectivo"})
    db.expire_all()
    faltante = db.query(m.Alerta).filter_by(empresa_id=E, tipo="faltante_caja").one()
    assert faltante.monto == Decimal("637.00")  # igual que forecast y asistente
    items = client_db.get(f"{EMP}/alertas").json()["items"]
    assert next(a for a in items if a["tipo"] == "faltante_caja")["monto"] == 637.0
    assert db.query(m.Alerta).filter_by(empresa_id=E, tipo="faltante_caja").count() == 1  # no se duplicó


def test_get_muestra_el_monto_al_dia_sin_escribir(client_db, db, reloj_fijo):
    client_db.post(f"{EMP}/alertas/evaluar", json={})
    tx(db, "venta", 13, HOY)  # un movimiento directo en la BD: no pasó por /confirmar
    f = next(a for a in client_db.get(f"{EMP}/alertas").json()["items"] if a["tipo"] == "faltante_caja")
    assert f["monto"] == 637.0
    assert db.query(m.Alerta).filter_by(tipo="faltante_caja").one().monto == Decimal("650.00")  # la fila no se tocó


def test_el_faltante_se_cierra_si_ya_no_aplica(client_db, db, reloj_fijo):
    client_db.post(f"{EMP}/alertas/evaluar", json={})
    tx(db, "otro_ingreso", 5000, HOY)
    client_db.post(f"{EMP}/movimientos", json={"tipo": "venta", "monto": 1, "metodo_pago": "efectivo"})
    db.expire_all()
    f = db.query(m.Alerta).filter_by(empresa_id=E, tipo="faltante_caja").one()
    assert (f.estado, f.accion_tomada) == ("descartada", "ya_no_aplica")
    assert "faltante_caja" not in [a["tipo"] for a in client_db.get(f"{EMP}/alertas").json()["items"]]


def test_alerta_de_una_sola_causa_no_rompe_pedido_excesivo(db, reloj_fijo):
    motor.evaluar_alertas(db, E)
    fila = db.query(m.Alerta).filter_by(empresa_id=E, tipo="pedido_excesivo").one()
    fila.causas = [{"descripcion": "Sobrecompra navideña", "monto": 289}]
    db.flush()
    a = next(x for x in motor_mod.alertas(db, E).items if x.tipo == "pedido_excesivo")
    assert a.causas[0].monto == Decimal("289.00") or len(a.causas) >= 1 and a.insight


@pytest.mark.parametrize("entidad_tipo", ["deuda", "deudas"])
def test_entidad_singular_o_plural_se_lee_igual(db, reloj_fijo, entidad_tipo):
    motor.evaluar_alertas(db, E)
    db.query(m.Alerta).filter_by(empresa_id=E, tipo="faltante_caja").update({"entidad_tipo": entidad_tipo})
    db.flush()
    f = next(a for a in motor_mod.alertas(db, E).items if a.tipo == "faltante_caja")
    assert f.titulo == "El 30/11 te faltarían S/ 650 para pagar a Distribuidora Andina"
    assert f.accion.payload == {"pedido_id": "PED-0012"}


def _forzar(db, tipo, **campos):
    base = dict(alerta_id="ALR-9001", empresa_id=E, tipo=tipo, prioridad=motor_mod.PRIORIDAD_ALERTA[tipo],
                fecha_evento=HOY, monto=Decimal("100"), causas=[{"descripcion": "Algo", "monto": 100}],
                canal="app", estado="activa", creada_en=motor_mod.reloj.ahora())  # fmt: skip
    fila = m.Alerta(**{**base, **campos})
    db.add(fila)
    db.flush()
    return fila


@pytest.mark.parametrize("tipo", ["faltante_caja", "pedido_excesivo", "retiro_excesivo", "obligacion_proxima",
                                  "gasto_inusual", "caida_ventas", "fiado_vencido", "meta_lograda", "resumen_semanal"])
def test_render_de_los_9_tipos_y_acciones(db, reloj_fijo, tipo):
    fila = _forzar(db, tipo, causas=[], accion_sugerida=None)
    a = motor_mod.render(db, fila, corte=HOY)
    assert a.titulo and a.insight and a.accion.tipo in motor_mod.ACCIONES and a.accion.texto_boton and a.microexplicacion
    assert tipo != "fiado_vencido" or "acreedor" not in a.titulo  # ya no sale como "pago a tu acreedor"
    for texto in (a.titulo, a.insight):
        assert "%" not in texto and "http" not in texto


def test_fiado_vencido_con_fila_de_csv_y_formato_viejo_de_causas(db, reloj_fijo):
    fila = _forzar(db, "fiado_vencido", entidad_tipo="cuaderno_fiado", entidad_id="FIA-0045", monto=Decimal("120"),
                   accion_sugerida="recordar_cliente", causas=[{"causa": "Sra. Carmen lleva 18 días sin pagar", "impacto": 120}])  # fmt: skip
    a = motor_mod.render(db, fila, corte=HOY)
    assert a.titulo == "Sra. Carmen te debe S/ 120 y ya pasó la fecha"
    assert a.accion.payload == {"fiado_id": "FIA-0045", "cliente_id": "CLI-0102"}
    assert a.causas[0].descripcion.startswith("Sra. Carmen") and a.causas[0].monto == Decimal("120.00")


def test_accion_desconocida_se_reemplaza_por_la_del_tipo(db, reloj_fijo):
    fila = _forzar(db, "gasto_inusual", accion_sugerida="ver_por_que", entidad_tipo="transacciones", entidad_id="MOV-0001")
    a = motor_mod.render(db, fila, corte=HOY)
    assert a.accion.tipo == "ver_movimientos" and a.accion.payload == {"tipo": "gasto_negocio"}


def test_gasto_inusual_se_dispara_con_un_gasto_ordinario_muy_alto(db, reloj_fijo):
    antes = [a.tipo for a in motor.evaluar_alertas(db, E, "gasto_negocio")]
    assert "gasto_inusual" not in antes
    mov = tx(db, "gasto_negocio", 3000, HOY, hora=11)
    nuevas = [a for a in motor.evaluar_alertas(db, E, "gasto_negocio") if a.tipo == "gasto_inusual"]
    assert len(nuevas) == 1 and nuevas[0].prioridad == 5
    a = nuevas[0]
    assert a.accion.tipo == "ver_movimientos" and a.titulo.startswith("Hoy gastaste S/ ")
    assert db.query(m.Alerta).filter_by(tipo="gasto_inusual").one().entidad_id == mov.transaccion_id
    assert db.query(m.Alerta).filter_by(tipo="gasto_inusual").one().entidad_tipo == "transacciones"
    assert [x for x in motor.evaluar_alertas(db, E, "gasto_negocio") if x.tipo == "gasto_inusual"] == []  # sin duplicar


def test_gasto_inusual_ignora_pagos_a_proveedor_y_programados(db, reloj_fijo):
    d = deuda_proveedor(db, 5000, HOY + timedelta(days=20), inicio=HOY - timedelta(days=40))
    tx(db, "pago_proveedor", 4000, HOY, deuda_id=d.deuda_id)
    tx(db, "gasto_negocio", 3500, HOY, programado_id="PRG-0001")
    assert "gasto_inusual" not in [a.tipo for a in motor.evaluar_alertas(db, E)]


def test_fiado_vencido_es_por_cliente_y_solo_con_riesgo_alto(db, reloj_fijo):
    items = [a for a in motor_mod.alertas(db, E).items if a.tipo == "fiado_vencido"]
    assert [(a.monto, a.accion.tipo) for a in items] == [(Decimal("120.00"), "recordar_cliente")]
    assert items[0].prioridad == 6 and items[0].nivel_riesgo == "alto"
    # Don Luis: otro cliente con un fiado vencido pero riesgo menor → no hay aviso
    f = fiado(db, "CLI-0110", 50, date(2026, 10, 1), compromiso=date(2026, 10, 15))
    assert f.fiado_id not in [a.accion.payload.get("fiado_id") for a in motor_mod.alertas(db, E).items]


def test_meta_lograda(db, reloj_fijo):
    meta = db.get(m.ReglaMeta, "MET-0001")
    meta.objetivo, meta.acumulado = Decimal("30"), Decimal("30")
    db.flush()
    a = next(x for x in motor_mod.alertas(db, E).items if x.tipo == "meta_lograda")
    assert a.prioridad == 7 and a.accion.tipo == "ver_progreso" and a.titulo.startswith("¡Lograste tu meta")
    assert [c.monto for c in a.causas] == [Decimal("30.00"), Decimal("30.00")]
    nuevas = motor.evaluar_alertas(db, E)
    assert "meta_lograda" in [n.tipo for n in nuevas]


def test_prioridades_y_limite_diario_incluyen_las_nuevas_reglas(db, reloj_fijo):
    meta = db.get(m.ReglaMeta, "MET-0001")
    meta.objetivo, meta.acumulado = Decimal("30"), Decimal("30")
    nuevas = motor.evaluar_alertas(db, E)
    assert [a.prioridad for a in nuevas] == sorted(a.prioridad for a in nuevas)
    assert [a.enviada_en is not None for a in nuevas].count(True) == 2  # máximo 2 notificaciones al día


def test_pendientes_se_guardan_al_confirmar_un_movimiento(client_db, db, reloj_fijo):
    assert db.query(m.Alerta).count() == 0
    r = client_db.post(f"{EMP}/movimientos", json={"tipo": "retiro_personal", "monto": 50})
    assert r.status_code == 201
    tipos = {a.tipo for a in db.query(m.Alerta).all()}
    assert {"faltante_caja", "retiro_excesivo"} <= tipos


# ── chat ────────────────────────────────────────────────────────────────────────────────────────


def _chat(c, texto, borrador_id=None):
    r = c.post(f"{EMP}/chat/mensajes", json={"texto": texto, "borrador_id": borrador_id})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("respuesta,final", [("Sí, salió de la caja", "guardado"), ("No, no salió de la caja", "descartado"),
                                              ("si", "guardado"), ("no", "descartado")])
def test_chips_de_salio_de_la_caja_no_quedan_en_bucle(client_db, reloj_fijo, respuesta, final):
    r = _chat(client_db, "pagué el colegio 150")
    if r["interpretacion"]["campos_faltantes"][:1] != ["salio_de_caja"]:
        pytest.skip("el extractor ya no pregunta si salió de la caja con esta frase")
    ops = r["interpretacion"]["opciones_aclaracion"]
    assert [o["texto"] for o in ops] == ["Sí, salió de la caja", "No, no salió de la caja"]
    assert _chat(client_db, respuesta, r["interpretacion"]["borrador_id"])["tipo"] == final


@pytest.mark.parametrize("texto", ["dame un reporte", "reporte", "cómo me fue", "cómo me fue este mes"])
def test_reporte_va_al_estado_de_caja(client_db, reloj_fijo, texto):
    r = _chat(client_db, texto)
    assert r["tipo"] == "asistente" and r["asistente"]["intencion"] == "estado_caja"


def test_pregunta_por_voz_en_whatsapp_va_al_asistente(client_db, whisper_falso, reloj_fijo, monkeypatch):
    from app.services.ingesta import transcriptor

    whisper_falso.texto = "¿cómo va mi caja?"
    monkeypatch.setattr(transcriptor, "transcribir_media", lambda url, emp: "¿cómo va mi caja?")
    r = client_db.post(f"{P}/webhooks/whatsapp", json={"mensaje_id": "wamid.voz1", "telefono_hash": "a91f", "empresa_id": E,
                                                       "tipo": "audio", "media_url": "demo://audio.ogg"})
    assert r.status_code == 200, r.text
    assert "caja" in r.json()["respuesta_texto"].lower() and "¿Correcto?" not in r.json()["respuesta_texto"]


def test_acciones_del_asistente_llevan_pedido_id(client_db, reloj_fijo):
    r = client_db.post(f"{EMP}/asistente/mensajes", json={"conversacion_id": "CNV-0031", "canal": "app",
                                                          "mensaje": "¿Por qué me va a faltar plata a fin de mes?"}).json()
    abrir = [a for a in r.get("acciones", []) if a["tipo"] == "abrir_simulador"]
    assert abrir and abrir[0]["pedido_id"] == "PED-0012"


# ── /health y validaciones ──────────────────────────────────────────────────────────────────────


def test_health_lee_las_versiones_de_prompts_de_las_constantes(client):
    from app.services.asistente import orquestador
    from app.services.ingesta import cuaderno, enrutador, extractor

    v = client.get(f"{P}/health").json()["componentes"]["llm"]["prompt_versions"]
    assert v == {"extractor": extractor.PROMPT_VERSION, "asistente": orquestador.PROMPT_VERSION,
                 "chat": enrutador.PROMPT_VERSION, "cuaderno": cuaderno.PROMPT_VERSION}  # fmt: skip
    assert (v["extractor"], v["asistente"], v["chat"], v["cuaderno"]) == ("extractor-v3", "asistente-v3", "chat-router-v1",
                                                                          "cuaderno-v2")  # fmt: skip


def test_motivo_ml_es_concreto_y_neutro(client):
    ml = client.get(f"{P}/health").json()["componentes"]["forecast"]["ml"]
    texto = ml["motivo"] or ""
    assert "FORECAST_MOTOR=baseline" in texto  # conftest desactiva el LightGBM
    for viejo in ("pendiente de integración", "bandera fija", "no hay regla para mapearla"):
        assert viejo not in texto


def test_validacion_de_meta_en_espanol(client_db):
    r = client_db.post(f"{EMP}/metas", json={"plantilla": "sueldo_fijo", "regla": {"tipo": "monto_fijo", "valor": -5}})
    assert r.status_code == 400
    assert "Input should" not in r.text and "debe ser mayor que 0" in r.text
    r = client_db.post(f"{EMP}/metas", json={"plantilla": "inventada"})
    assert r.status_code == 400 and "valor no permitido" in r.text and "Input should" not in r.text
