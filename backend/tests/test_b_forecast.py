"""B3/B4/B5/B12 — forecast (baseline naive estacional), disponible para gastar, ajustes manuales, ML y /health."""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db import models as m
from app.services import finanzas
from app.services.finanzas import modelo_ml
from app.services.finanzas import proyeccion as fc
from tests._b_util import EMP, HOY, P, E, reloj_fijo, tx  # noqa: F401


def _sin_meta(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "meta"}


# ── forecast de Pedro ──


@pytest.mark.db
def test_dia_critico_30_11_faltan_650(db, reloj_fijo):
    f = finanzas.forecast(db, E, 30)
    assert f.saldo_actual == Decimal("2340.00") and f.minimo_operativo == Decimal("800.00")
    assert len(f.serie) == 30 and f.serie[0].fecha == date(2026, 11, 15) and f.serie[-1].fecha == date(2026, 12, 14)
    dc = f.dia_critico
    assert (dc.fecha, dc.saldo_p50) == (date(2026, 11, 30), Decimal("-650.00"))
    assert 0.5 < dc.probabilidad_deficit <= 1
    ob = dc.obligacion_asociada
    assert (ob.tipo, ob.id, ob.proveedor, ob.monto) == ("prestamo_proveedor", "PED-0012", "Distribuidora Andina", 2400)
    assert next(p for p in f.serie if p.fecha == date(2026, 11, 30)).egresos_esperados > 2400


@pytest.mark.db
def test_forecast_es_deterministico_y_bandas_ordenadas(db, reloj_fijo):
    a, b = finanzas.forecast(db, E, 30).model_dump(mode="json"), finanzas.forecast(db, E, 30).model_dump(mode="json")
    assert _sin_meta(a) == _sin_meta(b)
    serie = a["serie"]
    assert all(p["p10"] <= p["p50"] <= p["p90"] for p in serie)
    anchos = [p["p50"] - p["p10"] for p in serie]
    assert anchos == sorted(anchos) and anchos[0] > 0  # la incertidumbre crece con el horizonte
    saldo = 2340.0
    for h, p in enumerate(serie, start=1):  # p50 = saldo de ayer + ingresos − egresos (montos diarios redondeados)
        saldo = round(saldo + p["ingresos_esperados"] - p["egresos_esperados"], 2)
        assert p["p50"] == pytest.approx(saldo, abs=0.01 * h)


@pytest.mark.db
def test_eventos_con_fecha_y_fiados_ponderados_fuera_del_p50(db, reloj_fijo):
    f = finanzas.forecast(db, E, 30)
    eventos = {(e.fecha.isoformat(), e.concepto): e for e in f.proximos_eventos}
    assert eventos[("2026-11-16", "Luz y agua")].monto == Decimal("-180.00")
    assert eventos[("2026-11-30", "Pago a Distribuidora Andina")].ref_id == "PED-0012"
    sueldos = [e.fecha for e in f.proximos_eventos if e.concepto == "Sueldo de Pedro"]
    assert sueldos == [date(2026, 11, 21), date(2026, 11, 28), date(2026, 12, 5), date(2026, 12, 12)]
    fiados = [e for e in f.proximos_eventos if e.tipo == "cobro_fiado"]
    assert {e.ref_id for e in fiados} == {"FIA-0045", "FIA-0046", "FIA-0047"} and all(e.ponderado for e in fiados)
    assert all(0 < e.monto < 120 for e in fiados)
    assert f.disponible_para_gastar.componentes.cobros_esperados == sum(e.monto for e in fiados)
    # el p90 suma los fiados ponderados; el p50 no
    critico = next(p for p in f.serie if p.fecha == date(2026, 11, 30))
    assert critico.p90 - critico.p50 > critico.p50 - critico.p10


@pytest.mark.db
def test_meta_fallback_y_metricas_del_baseline(db, reloj_fijo):
    f = finanzas.forecast(db, E, 30)
    assert f.meta.fallback_usado is True and f.meta.modelo == "forecast-naive-estacional"
    assert f.baseline.nombre == "naive_estacional" and f.baseline.mae_backtest > 0
    assert f.modelo_metricas is None
    assert f.disponible is True and f.dias_con_datos == 91 and f.confianza == "media"


@pytest.mark.db
def test_un_movimiento_de_hoy_mueve_la_proyeccion(db, reloj_fijo):
    tx(db, "venta", 13, HOY)
    assert finanzas.forecast(db, E, 30).dia_critico.saldo_p50 == Decimal("-637.00")


@pytest.mark.db
def test_pago_ya_hecho_del_programado_no_se_proyecta(db, reloj_fijo):
    tx(db, "gasto_negocio", 180, HOY, programado_id="PRG-0001")  # pagó la luz hoy, antes del 16
    f = finanzas.forecast(db, E, 30)
    assert not [e for e in f.proximos_eventos if e.concepto == "Luz y agua" and e.fecha.month == 11]
    assert f.dia_critico.saldo_p50 == Decimal("-650.00")  # sale hoy en vez del 16: mismo saldo el 30


@pytest.mark.db
def test_horizonte_corto_y_poca_historia(db, reloj_fijo):
    f = finanzas.forecast(db, E, 7)
    assert len(f.serie) == 7 and f.dia_critico is None
    nuevo = finanzas.forecast(db, E, 30, fecha_corte=date(2026, 8, 20))
    assert nuevo.disponible is False and nuevo.dias_con_datos == 6 and nuevo.dias_requeridos == 28


# ── B4 disponible para gastar ──


@pytest.mark.db
def test_disponible_cero_por_el_pago_del_30(db, reloj_fijo):
    d = finanzas.forecast(db, E, 30).disponible_para_gastar
    c = d.componentes
    assert (c.saldo_actual, c.pagos_comprometidos, c.minimo_operativo, c.reserva_impuestos) == (
        Decimal("2340.00"), Decimal("3380.00"), Decimal("800.00"), Decimal("20.00"))  # 2 400 + 180 + 2 × 400
    assert d.valor == 0 and "30/11" in d.mensaje
    assert d.formula.startswith("saldo_actual + cobros_esperados")


@pytest.mark.db
def test_disponible_positivo(db, reloj_fijo):
    tx(db, "otro_ingreso", 5000, HOY)
    f = finanzas.forecast(db, E, 30)
    d = f.disponible_para_gastar
    c = d.componentes
    assert f.dia_critico is None
    assert d.valor == c.saldo_actual + c.cobros_esperados - c.pagos_comprometidos - c.minimo_operativo - c.reserva_impuestos
    assert d.valor > 0 and d.mensaje.startswith("Hoy puedes sacar hasta")


# ── B5 ajustes manuales ──


@pytest.mark.db
def test_ajuste_que_reemplaza_un_programado(client_db, db, reloj_fijo):
    r = client_db.post(f"{EMP}/forecast/ajustes", json={"fecha": "2026-11-16", "concepto": "luz y agua", "monto": 0,
                                                         "motivo": "el dueño paga la luz este mes"})  # fmt: skip
    assert r.status_code == 201 and r.json()["forecast_recalculado"] is True
    fila = db.get(m.ForecastAjuste, r.json()["ajuste_id"])
    assert fila.programado_id == "PRG-0001" and fila.activo
    f = client_db.get(f"{EMP}/forecast").json()
    assert f["dia_critico"]["saldo_p50"] == -470.0  # −650 + 180
    aplicado = f["ajustes_manuales_aplicados"][0]
    assert (aplicado["tipo"], aplicado["monto_original"], aplicado["ajuste_id"]) == ("reemplazo", 180.0, fila.ajuste_id)


@pytest.mark.db
def test_ajuste_adicional_y_validaciones(client_db, reloj_fijo):
    r = client_db.post(f"{EMP}/forecast/ajustes", json={"fecha": "2026-11-20", "concepto": "gasfitero", "monto": 120})
    assert r.status_code == 201
    f = client_db.get(f"{EMP}/forecast").json()
    assert f["dia_critico"]["saldo_p50"] == -770.0
    assert f["ajustes_manuales_aplicados"][0]["tipo"] == "adicional"
    assert client_db.post(f"{EMP}/forecast/ajustes", json={"fecha": "2026-11-14", "concepto": "x", "monto": 1}).status_code == 400
    assert client_db.post(f"{EMP}/forecast/ajustes", json={"fecha": "2026-11-20", "concepto": "x", "monto": -5}).status_code == 400
    assert client_db.post(f"{P}/empresas/EMP-9999/forecast/ajustes",
                          json={"fecha": "2026-11-20", "concepto": "x", "monto": 1}).status_code == 404  # fmt: skip


# ── ML: diagnóstico y fallback ──


def _con_artefactos(monkeypatch, ruta):
    monkeypatch.setattr(settings, "ML_ARTIFACTS_DIR", str(ruta))


def test_sin_artefactos_queda_no_disponible(monkeypatch, tmp_path):
    _con_artefactos(monkeypatch, tmp_path)
    d = modelo_ml.diagnostico_forecast()
    assert d["estado"] == "no_disponible" and "metadata.json" in d["motivos"][0]
    assert modelo_ml.diagnostico_riesgo_atraso()["estado"] == "no_disponible"


def test_features_no_construibles_dejan_el_modelo_sin_integrar(monkeypatch, tmp_path):
    base = tmp_path / "prediccion_ingreso_egreso"
    base.mkdir()
    for a in modelo_ml.ARCHIVOS_FORECAST:
        (base / a).write_bytes(b"no es un modelo")  # nunca se deserializa
    (base / "metadata.json").write_text(json.dumps({"features_en_orden": ["zona", "ingreso_lag1", "dow", "clima"],
                                                    "categorias_zona": ["urbano"]}), encoding="utf-8")  # fmt: skip
    _con_artefactos(monkeypatch, tmp_path)
    d = modelo_ml.diagnostico_forecast()
    assert d["estado"] == "no_disponible" and d["artefactos"] is True
    assert d["features_no_construibles"] == ["zona", "clima"]


@pytest.mark.db
def test_forecast_usa_baseline_si_el_modelo_no_esta(db, monkeypatch, tmp_path, reloj_fijo):
    _con_artefactos(monkeypatch, tmp_path)
    f = finanzas.forecast(db, E, 30)
    assert f.meta.fallback_usado is True and "metadata.json" in f.meta.fallback_motivo
    assert f.dia_critico.saldo_p50 == Decimal("-650.00")


def test_artefactos_reales_del_equipo_de_datos():
    meta = settings.ml_artifacts_dir / "prediccion_ingreso_egreso" / "metadata.json"
    if not meta.exists():
        pytest.skip(f"No están los artefactos reales en {meta} (monta ../modelo/artifacts o define ML_ARTIFACTS_DIR)")
    d = modelo_ml.diagnostico_forecast()
    assert d["artefactos"] is True and d["estado"] == "no_disponible"
    # rubro y zona fueron resueltos por el equipo de ML (zona -> n_trabajadores, rubro con taxonomia real),
    # pero el chequeo _CONSTRUIBLE de modelo_ml.py sigue sin reconocerlos como construibles (ver su docstring).
    assert set(d["features_no_construibles"]) == {"rubro", "n_trabajadores", "antiguedad_meses", "usa_fiado", "usa_billetera_digital"}


# ── B12 /health ──


def test_health_reporta_baseline_sin_cargar_modelos(client, monkeypatch):
    llamadas = []
    monkeypatch.setattr(fc, "proyectar", lambda *a, **k: llamadas.append(1))
    h = client.get(f"{P}/health").json()["componentes"]
    assert {"whisper", "llm", "vlm", "almacenamiento", "base_datos"} <= set(h)
    for nombre in ("forecast", "riesgo_atraso"):
        assert h[nombre]["estado"] == "baseline" and h[nombre]["ml"]["estado"] == "no_disponible"
        assert h[nombre]["ml"]["motivo"]
    assert h["forecast"]["modelo"] == "forecast-naive-estacional" and h["forecast"]["modelo_version"] == fc.VERSION
    assert llamadas == []


def test_constantes_del_horizonte():
    assert fc.Z80 == pytest.approx(1.2816) and fc.DIAS_REQUERIDOS == 28 and timedelta(days=fc.HORIZONTE_MAX).days == 120
