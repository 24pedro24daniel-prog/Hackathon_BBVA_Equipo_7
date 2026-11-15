"""Cada endpoint responde con el código y la forma del contrato (datos de Pedro).

Nacieron como tests de los stubs de la Fase 0; ahora todos los endpoints calculan sobre la BD, así que usan la BD de
pruebas sembrada (`client_db`, con rollback). Las cifras exactas de cada motor están en test_b_<motor>.py.
"""

from decimal import Decimal

import pytest

from app.core.config import settings
from app.schemas.alertas import Alerta, AlertasResponse
from app.schemas.cuentas import ChequeoResponse, EstadoImpuestos, FiadosResponse, PedidosResponse
from app.schemas.forecast import ForecastResponse
from app.schemas.resumen import ResumenResponse
from app.schemas.simulador import Accion, SimulacionResponse
from app.services import alertas as motor_alertas
from app.services import finanzas
from tests._b_util import reloj_fijo  # noqa: F401

P = settings.API_PREFIX
EMP = f"{P}/empresas/EMP-0001"
META = {"request_id", "generado_en", "modelo", "modelo_version", "prompt_version", "fallback_usado", "latencia_ms"}

CASOS = [
    # (método, ruta, body, status, claves obligatorias)
    ("post", f"{P}/webhooks/whatsapp",
     {"telefono_hash": "a91f", "empresa_id": "EMP-0001", "tipo": "texto", "texto": "vendí dos cervezas"}, 200,
     {"respuesta_texto", "botones", "respuesta_audio_url"}),
    ("post", f"{P}/ingesta/interpretar", {"empresa_id": "EMP-0001", "canal": "texto", "texto": "vendí dos cervezas"},
     200, {"borrador_id", "transcripcion", "movimiento_propuesto", "origen_monto", "confianza", "campos_faltantes",
           "pregunta_aclaratoria", "meta"}),
    ("post", f"{P}/ingesta/cuaderno", {"empresa_id": "EMP-0001", "media_url": "file://data/fotos/cuaderno_01.jpg"},
     200, {"borrador_id", "fiados_propuestos", "lineas_no_legibles", "meta"}),
    ("post", f"{EMP}/impuestos",
     {"periodo": "2026-10", "regimen": "nuevo_rus", "pagado": True, "monto": 20.0, "fecha_pago": "2026-11-12"}, 201,
     {"impuesto_id", "estado", "proximo_vencimiento"}),
    ("get", f"{EMP}/movimientos", None, 200, {"items", "next_cursor"}),
    ("post", f"{EMP}/movimientos", {"tipo": "venta", "monto": 13.0, "metodo_pago": "efectivo"}, 201,
     {"movimiento_id", "registros_creados", "alertas_disparadas", "saldo_caja_negocio"}),
    ("post", f"{EMP}/asistente/mensajes",
     {"conversacion_id": "CNV-0031", "mensaje": "¿Por qué me va a faltar plata a fin de mes?", "canal": "whatsapp"},
     200, {"conversacion_id", "respuesta", "intencion", "herramientas_llamadas", "cifras_usadas", "verificacion_cifras",
           "fuera_de_alcance", "ofrecer_humano", "disclaimer", "meta"}),
    ("get", f"{EMP}/salud", None, 200,
     {"score", "score_anterior", "etapa_actual", "subindicadores", "historial", "rachas",
      "consentimiento_compartir_historial", "meta"}),
    ("post", f"{EMP}/metas",
     {"plantilla": "apartar_para_pedido", "regla": {"tipo": "porcentaje_de_venta", "valor": 0.10,
      "destino": "fondo_pedidos"}, "recordatorio": {"frecuencia": "semanal", "dia": "lunes"}}, 201,
     {"meta_id", "estado"}),
    ("get", f"{EMP}/resumen?periodo=2026-11", None, 200, {"empresa_id", "periodo", "corte", "indicadores", "variacion_vs"}),
    ("get", f"{EMP}/forecast?horizonte_dias=30", None, 200,
     {"empresa_id", "fecha_corte", "horizonte_dias", "saldo_actual", "minimo_operativo", "serie", "dia_critico",
      "disponible_para_gastar", "ajustes_manuales_aplicados", "baseline", "modelo_metricas", "meta"}),
    ("post", f"{EMP}/forecast/ajustes",
     {"fecha": "2026-11-28", "concepto": "alquiler", "monto": 0.0, "motivo": "acuerdo con el dueño del local"}, 201,
     {"ajuste_id", "forecast_recalculado"}),
    ("get", f"{EMP}/fiados?estado=pendiente", None, 200, {"total_pendiente", "total_vencido", "items", "meta"}),
    ("post", f"{P}/fiados/FIA-0045/recordatorio", None, 200, {"mensaje"}),
    ("get", f"{EMP}/pedidos?estado=pendiente", None, 200, {"total_pendiente", "items", "impuestos"}),
    ("post", f"{EMP}/pedidos/chequeo",
     {"proveedor": "Distribuidora Andina", "monto": 2400.0, "fecha_vencimiento": "2026-11-30"}, 200,
     {"saldo_proyectado_al_vencimiento", "estado_caja", "venta_esperada_periodo", "exceso_vs_ventas", "sugerencias",
      "fundamento", "limites", "confianza", "meta"}),
    ("post", f"{EMP}/simular",
     {"acciones": [{"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800.0},
                   {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2,
                    "fechas": ["2026-11-30", "2026-12-15"]},
                   {"tipo": "cobrar_fiados", "fiado_ids": ["FIA-0045", "FIA-0046", "FIA-0047"],
                    "fecha": "2026-11-20"}]}, 200,
     {"sin_acciones", "con_acciones", "mejora", "serie_con_acciones", "meta"}),
    ("get", f"{EMP}/analisis?agrupar_por=categoria&tipo=egreso", None, 200,
     {"agrupar_por", "tipo", "periodo", "grupos", "comparacion_pares"}),
    ("get", f"{EMP}/alertas?estado=activa", None, 200, {"items"}),
    ("post", f"{P}/alertas/ALR-0007/accion", {"accion": "ejecutada", "detalle": "abrió simulador"}, 200, {"estado"}),
    ("post", f"{EMP}/alertas/evaluar", {}, 200, {"items"}),
    ("put", f"{EMP}/preferencias-alertas",
     {"canales": ["whatsapp"], "max_por_dia": 2, "silencio_desde": "21:00", "silencio_hasta": "07:00",
      "resumen_semanal": True}, 200, {"canales", "max_por_dia", "silencio_desde", "silencio_hasta", "resumen_semanal"}),
    ("get", f"{P}/health", None, 200, {"estado", "version_api", "componentes"}),
]  # fmt: skip


@pytest.mark.db
@pytest.mark.parametrize(("metodo", "ruta", "body", "status", "claves"), CASOS, ids=[f"{c[0]} {c[1]}" for c in CASOS])
def test_stub_responde_forma_del_contrato(client_db, reloj_fijo, metodo, ruta, body, status, claves):
    client = client_db
    if "ALR-0007" in ruta:  # la alerta la crea el motor de B al consultar
        ruta = ruta.replace("ALR-0007", client.get(f"{EMP}/alertas").json()["items"][0]["alerta_id"])
    r = client.request(metodo.upper(), ruta, json=body)
    assert r.status_code == status, r.text
    datos = r.json()
    assert claves <= set(datos), f"faltan {claves - set(datos)}"
    if "meta" in claves:
        assert META <= set(datos["meta"])
        assert datos["meta"]["request_id"] == r.headers["x-request-id"]


def test_todas_las_rutas_del_plan_tienen_caso():
    from app.main import app

    rutas = {(metodo.upper(), path) for path, ops in app.openapi()["paths"].items() for metodo in ops}
    probadas = {("POST", f"{P}/ingesta/confirmar"),  # cubierto en tests/test_a_ingesta_flujo.py
                ("POST", f"{P}/media/subidas"),  # cubierto en tests/test_a_media.py (necesita R2 falso)
                ("GET", f"{P}/empresas/{{empresa_id}}/llm/llamadas"),  # cubiertos en tests/test_a_llm_trazas.py
                ("GET", f"{P}/empresas/{{empresa_id}}/llm/resumen")}
    for metodo, ruta, *_ in CASOS:
        path = ruta.split("?")[0].replace("EMP-0001", "{empresa_id}").replace("FIA-0045", "{fiado_id}")
        probadas.add((metodo.upper(), path.replace("ALR-0007", "{alerta_id}")))
    assert rutas == probadas


# ── cifras de la historia de Pedro (calculadas sobre el seed) ──


@pytest.fixture
def client_seed(client_db, reloj_fijo):
    return client_db


@pytest.mark.db
def test_resumen_saldo_2340(client_seed):
    ind = client_seed.get(f"{EMP}/resumen").json()["indicadores"]
    assert ind["saldo_caja_negocio"]["valor"] == 2340.0
    assert ind["pendiente_cobro"] == {"valor": 310.0, "n_fiados": 3}


@pytest.mark.db
def test_forecast_dia_critico_30_11(client_seed):
    f = client_seed.get(f"{EMP}/forecast").json()
    assert f["saldo_actual"] == 2340.0
    assert len(f["serie"]) == 30
    assert f["dia_critico"]["fecha"] == "2026-11-30" and f["dia_critico"]["saldo_p50"] == -650.0
    assert f["dia_critico"]["obligacion_asociada"]["id"] == "PED-0012"
    assert all(p["p10"] <= p["p50"] <= p["p90"] for p in f["serie"])


@pytest.mark.db
def test_pedidos_y_fiados(client_seed):
    p = client_seed.get(f"{EMP}/pedidos").json()
    assert p["items"][0]["pedido_id"] == "PED-0012" and p["items"][0]["monto"] == 2400.0
    f = client_seed.get(f"{EMP}/fiados").json()
    assert f["total_pendiente"] == 310.0
    assert sum(i["monto"] for i in f["items"]) == 310.0


@pytest.mark.db
def test_chequeo_y_simulador_deterministicos(client_seed):
    ch = client_seed.post(f"{EMP}/pedidos/chequeo",
                          json={"proveedor": "Distribuidora Andina", "monto": 2400, "fecha_vencimiento": "2026-11-30"}).json()  # fmt: skip
    assert ch["saldo_proyectado_al_vencimiento"] == -650.0 and ch["estado_caja"] == "no_te_alcanza"
    assert [s["saldo_resultante"] for s in ch["sugerencias"]] == [-50.0, 550.0, 850.0]
    sim = client_seed.post(f"{EMP}/simular", json={"acciones": [
        {"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800},
        {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2}]}).json()  # fmt: skip
    assert sim["sin_acciones"]["saldo_minimo"] == -650.0
    assert sim["con_acciones"]["saldo_minimo"] == 850.0
    assert sim["mejora"] == 1500.0


@pytest.mark.db
def test_alerta_faltante_con_causas(client_seed):
    alerta = client_seed.get(f"{EMP}/alertas").json()["items"][0]
    assert alerta["tipo"] == "faltante_caja" and alerta["prioridad"] == 1 and alerta["monto"] == 650.0
    assert [c["monto"] for c in alerta["causas"]] == [700.0, 400.0, 310.0]
    assert client_seed.get(f"{EMP}/alertas?estado=atendida").json() == {"items": []}


# ── comportamiento real de ingesta: ver tests/test_a_ingesta_flujo.py ──


@pytest.mark.db
def test_recordatorio_fiado_inexistente_404(client_seed):
    assert client_seed.post(f"{P}/fiados/FIA-9999/recordatorio").status_code == 404


def test_health_reporta_componentes_sin_cargar_ia(client):
    from app.services.ingesta import transcriptor

    h = client.get(f"{P}/health").json()
    assert h["componentes"]["base_datos"] in {"ok", "caido"}
    assert h["estado"] == ("ok" if h["componentes"]["base_datos"] == "ok" else "degradado")
    assert h["componentes"]["whisper"]["modelo"] == "faster-whisper-small"
    assert h["componentes"]["llm"]["estado"] == "sin_configurar"
    assert h["componentes"]["forecast"]["estado"] == "baseline"
    assert not transcriptor.modelo_cargado()


@pytest.mark.db
def test_health_con_bd_ok(client_db):
    assert client_db.get(f"{P}/health").json()["componentes"]["base_datos"] == "ok"


# ── interfaces §4.2 (firmas congeladas, ahora con cálculo real) ──


@pytest.mark.db
def test_interfaces_finanzas_devuelven_schemas(db, reloj_fijo):
    assert finanzas.saldo_caja(db, "EMP-0001") == Decimal("2340.00")
    assert isinstance(finanzas.fiados(db, "EMP-0001"), FiadosResponse)
    assert isinstance(finanzas.pedidos(db, "EMP-0001"), PedidosResponse)
    assert isinstance(finanzas.estado_impuestos(db, "EMP-0001"), EstadoImpuestos)
    assert isinstance(finanzas.resumen(db, "EMP-0001", "2026-11"), ResumenResponse)
    assert isinstance(finanzas.forecast(db, "EMP-0001", 30), ForecastResponse)
    from datetime import date

    ch = finanzas.chequeo_pedido(db, "EMP-0001", "Distribuidora Andina", Decimal("2400"), date(2026, 11, 30))
    assert isinstance(ch, ChequeoResponse) and ch.saldo_proyectado_al_vencimiento == Decimal("-650.00")
    sim = finanzas.simular(db, "EMP-0001", [Accion(tipo="cobrar_fiados", fiado_ids=["FIA-0045"])])
    assert isinstance(sim, SimulacionResponse) and sim.con_acciones.saldo_minimo == Decimal("-530.00")


@pytest.mark.db
def test_interfaces_alertas(db, reloj_fijo):
    assert motor_alertas.evaluar_alertas(db, "EMP-0001", disparador="venta") == []
    nuevas = motor_alertas.evaluar_alertas(db, "EMP-0001", disparador="compra_credito", entidad_id="PED-0012")
    assert [a.tipo for a in nuevas] == ["faltante_caja", "pedido_excesivo"] and isinstance(nuevas[0], Alerta)
    assert isinstance(motor_alertas.alertas(db, "EMP-0001"), AlertasResponse)


@pytest.mark.db
def test_dinero_se_serializa_como_numero(client_seed):
    datos = client_seed.get(f"{EMP}/pedidos").json()
    assert isinstance(datos["total_pendiente"], float)
