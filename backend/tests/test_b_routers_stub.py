"""Cada endpoint stub de la Fase 0 responde con el código y la forma del contrato (datos de Pedro).

Cuando un dueño reemplace un stub por el cálculo real, estos tests siguen valiendo para la forma; los asserts de
cifras exactas del mock (marcados "mock") se ajustan o se mueven a los tests del cálculo real.
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


# Rutas de Dev A: ya no son stub, usan la BD real → se prueban con el cliente transaccional (client_db).
_PREFIJOS_A = (f"{P}/webhooks", f"{P}/ingesta", f"{EMP}/impuestos", f"{EMP}/movimientos", f"{EMP}/asistente",
               f"{EMP}/salud", f"{EMP}/metas")  # fmt: skip


@pytest.mark.parametrize(("metodo", "ruta", "body", "status", "claves"), CASOS, ids=[f"{c[0]} {c[1]}" for c in CASOS])
def test_stub_responde_forma_del_contrato(request, client, metodo, ruta, body, status, claves):
    if ruta.startswith(_PREFIJOS_A):
        client = request.getfixturevalue("client_db")
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
    probadas = {("POST", f"{P}/ingesta/confirmar")}  # cubierto en tests/test_a_ingesta_flujo.py
    for metodo, ruta, *_ in CASOS:
        path = ruta.split("?")[0].replace("EMP-0001", "{empresa_id}").replace("FIA-0045", "{fiado_id}")
        probadas.add((metodo.upper(), path.replace("ALR-0007", "{alerta_id}")))
    assert rutas == probadas


# ── cifras de la historia de Pedro (mock) ──


def test_resumen_saldo_2340(client):
    ind = client.get(f"{EMP}/resumen").json()["indicadores"]
    assert ind["saldo_caja_negocio"]["valor"] == 2340.0
    assert ind["pendiente_cobro"] == {"valor": 310.0, "n_fiados": 3}


def test_forecast_dia_critico_30_11(client):
    f = client.get(f"{EMP}/forecast").json()
    assert f["saldo_actual"] == 2340.0
    assert len(f["serie"]) == 30
    assert f["dia_critico"]["fecha"] == "2026-11-30" and f["dia_critico"]["saldo_p50"] == -650.0
    assert f["dia_critico"]["obligacion_asociada"]["id"] == "PED-0012"
    assert all(p["p10"] <= p["p50"] <= p["p90"] for p in f["serie"])


def test_pedidos_y_fiados(client):
    p = client.get(f"{EMP}/pedidos").json()
    assert p["items"][0]["pedido_id"] == "PED-0012" and p["items"][0]["monto"] == 2400.0
    f = client.get(f"{EMP}/fiados").json()
    assert f["total_pendiente"] == 310.0
    assert sum(i["monto"] for i in f["items"]) == 310.0


def test_chequeo_y_simulador_deterministicos(client):
    ch = client.post(f"{EMP}/pedidos/chequeo",
                     json={"proveedor": "Distribuidora Andina", "monto": 2400, "fecha_vencimiento": "2026-11-30"}).json()  # fmt: skip
    assert ch["saldo_proyectado_al_vencimiento"] == -650.0 and ch["estado_caja"] == "no_te_alcanza"
    assert [s["saldo_resultante"] for s in ch["sugerencias"]] == [-50.0, 550.0, 850.0]
    sim = client.post(f"{EMP}/simular", json={"acciones": [
        {"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800},
        {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2}]}).json()  # fmt: skip
    assert sim["sin_acciones"]["saldo_minimo"] == -650.0
    assert sim["con_acciones"]["saldo_minimo"] == 850.0
    assert sim["mejora"] == 1500.0


def test_alerta_faltante_con_causas(client):
    alerta = client.get(f"{EMP}/alertas").json()["items"][0]
    assert alerta["tipo"] == "faltante_caja" and alerta["prioridad"] == 1 and alerta["monto"] == 650.0
    assert [c["monto"] for c in alerta["causas"]] == [700.0, 400.0, 310.0]
    assert client.get(f"{EMP}/alertas?estado=atendida").json() == {"items": []}


# ── comportamiento real de ingesta: ver tests/test_a_ingesta_flujo.py ──


def test_recordatorio_fiado_inexistente_404(client):
    assert client.post(f"{P}/fiados/FIA-9999/recordatorio").status_code == 404


def test_health_reporta_componentes_sin_cargar_ia(client):
    from app.services.ingesta import transcriptor

    h = client.get(f"{P}/health").json()
    assert h["componentes"]["base_datos"] in {"ok", "caido"}
    assert h["estado"] == ("ok" if h["componentes"]["base_datos"] == "ok" else "degradado")
    assert h["componentes"]["whisper"]["modelo"] == "faster-whisper-small"
    assert h["componentes"]["llm"]["estado"] == "sin_configurar"
    assert not transcriptor.modelo_cargado()


@pytest.mark.db
def test_health_con_bd_ok(client_db):
    assert client_db.get(f"{P}/health").json()["componentes"]["base_datos"] == "ok"


# ── interfaces §4.2 (firmas congeladas, respuesta mock) ──


def test_interfaces_finanzas_devuelven_schemas():
    assert finanzas.saldo_caja(None, "EMP-0001") == Decimal("2340.00")
    assert isinstance(finanzas.fiados(None, "EMP-0001"), FiadosResponse)
    assert isinstance(finanzas.pedidos(None, "EMP-0001"), PedidosResponse)
    assert isinstance(finanzas.estado_impuestos(None, "EMP-0001"), EstadoImpuestos)
    assert isinstance(finanzas.resumen(None, "EMP-0001", "2026-11"), ResumenResponse)
    assert isinstance(finanzas.forecast(None, "EMP-0001", 30), ForecastResponse)
    from datetime import date

    ch = finanzas.chequeo_pedido(None, "EMP-0001", "Distribuidora Andina", Decimal("2400"), date(2026, 11, 30))
    assert isinstance(ch, ChequeoResponse) and ch.saldo_proyectado_al_vencimiento == Decimal("-650.00")
    sim = finanzas.simular(None, "EMP-0001", [Accion(tipo="cobrar_fiados", fiado_ids=["FIA-0045"])])
    assert isinstance(sim, SimulacionResponse) and sim.con_acciones.saldo_minimo == Decimal("-340.00")


def test_interfaces_alertas():
    assert motor_alertas.evaluar_alertas(None, "EMP-0001") == []
    nuevas = motor_alertas.evaluar_alertas(None, "EMP-0001", disparador="compra_credito", entidad_id="PED-0012")
    assert len(nuevas) == 1 and isinstance(nuevas[0], Alerta)
    assert isinstance(motor_alertas.alertas(None, "EMP-0001"), AlertasResponse)


def test_dinero_se_serializa_como_numero(client):
    datos = client.get(f"{EMP}/pedidos").json()
    assert isinstance(datos["total_pendiente"], float)
