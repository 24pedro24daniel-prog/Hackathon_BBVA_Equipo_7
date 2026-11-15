"""D — Modelos de ML del equipo de datos integrados: LightGBM (forecast) y regresión logística (score crediticio).

Los tests con artefactos reales se saltan con un mensaje claro si no están (`ML_ARTIFACTS_DIR` / ../modelo/artifacts).
El resto de la suite corre con `FORECAST_MOTOR=baseline` (ver conftest) para que las cifras de la demo sean fijas.
"""

import ast
import inspect
import json
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db import models as m
from app.services import finanzas
from app.services.finanzas import forecast_ml as fml
from app.services.finanzas import modelo_ml
from app.services.finanzas import proyeccion as fc
from app.services.salud import credito
from tests._b_util import EMP, HOY, E, P, reloj_fijo, tx  # noqa: F401

PROHIBIDOS = {"pago_tardio", "deficit_14d", "eventos", "perfil_pago"}


def _metadata(carpeta: str) -> dict:
    ruta = settings.ml_artifacts_dir / carpeta / "metadata.json"
    if not ruta.exists():
        pytest.skip(f"No están los artefactos reales en {ruta} (monta ../modelo/artifacts o define ML_ARTIFACTS_DIR)")
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.fixture
def scoring():
    modelo_ml._SCORING.limpiar()
    modelo, motivo = modelo_ml.cargar_scoring()
    if modelo is None:
        pytest.skip(f"Credit scoring no disponible: {motivo}")
    yield modelo
    modelo_ml._SCORING.limpiar()


def _historia(n: int = 45, base_ing: float = 600.0, base_egr: float = 350.0):
    rng = np.random.default_rng(7)
    picos = rng.choice([0.0, 0.0, 0.0, 350.0], n)  # egreso ordinario "con picos" (compras, retiros), como el de las bodegas reales
    return ((base_ing + rng.normal(0, 30, n)).clip(50).tolist(), (base_egr + picos + rng.normal(0, 20, n)).clip(20).tolist())


PERFIL = fml.Perfil(rubro="bodega", n_trabajadores=1, antiguedad_meses=3, usa_fiado=True, usa_billetera_digital=False)


# ── artefactos reales: carga y coherencia con metadata.json ──


def test_artefactos_forecast_cargan_y_coinciden_con_metadata(motor_lightgbm):
    meta = _metadata("prediccion_ingreso_egreso")
    assert list(motor_lightgbm.features) == meta["features_en_orden"] and len(motor_lightgbm.features) == 28
    assert list(motor_lightgbm.categorias_rubro) == meta["categorias_rubro"]
    assert motor_lightgbm.version == meta["modelo_version"] == "lgbm_cuantiles-1.0"
    assert set(motor_lightgbm.modelos) == {(t, q) for t in ("ingreso", "egreso") for q in (10, 50, 90)}
    for modelo in motor_lightgbm.modelos.values():
        assert list(modelo.feature_name_) == meta["features_en_orden"]


def test_artefactos_scoring_cargan_y_coinciden_con_metadata(scoring):
    meta = _metadata("credit_scoring")
    assert list(scoring.columnas) == meta["columnas_en_orden"] and len(scoring.columnas) == 16
    assert scoring.scaler.n_features_in_ == 16 and scoring.modelo.coef_.shape == (1, 16)
    assert list(scoring.categorias_rubro) == meta["categorias_rubro"]


def test_carga_unica_y_cacheada(motor_lightgbm, monkeypatch):
    llamadas = []
    original = modelo_ml._FORECAST._cargador
    monkeypatch.setattr(modelo_ml._FORECAST, "_cargador", lambda ruta: llamadas.append(1) or original(ruta))
    modelo_ml.limpiar_cache()
    a, _ = modelo_ml.cargar_forecast()
    b, _ = modelo_ml.cargar_forecast()
    modelo_ml.diagnostico_forecast()
    assert a is b and llamadas == [1]


def test_nunca_se_cargan_modelos_al_importar():
    import subprocess
    import sys

    codigo = "import sys, app.main; mal = [n for n in ('lightgbm', 'sklearn', 'pandas', 'joblib') if n in sys.modules]; print(mal)"
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True).stdout.strip()
    assert salida == "[]"


# ── features: orden, nombres, categorías y cálculo ──


def test_features_en_el_orden_y_con_las_categorias_del_metadata(motor_lightgbm):
    ing, egr = _historia()
    fila = fml.fila_features(PERFIL, ing, egr, date(2026, 11, 16))
    X = fml.matriz(motor_lightgbm, [fila])
    assert list(X.columns) == _metadata("prediccion_ingreso_egreso")["features_en_orden"]
    assert list(X["rubro"].cat.categories) == ["bodega", "distribuidora", "restaurante", "taller"]
    assert X["rubro"].iloc[0] == "bodega"


def test_features_replican_el_notebook():
    ing, egr = _historia()
    f = fml.fila_features(PERFIL, ing, egr, date(2026, 11, 16))  # lunes 16 (quincena)
    s = np.asarray(ing)
    assert f["ingreso_lag1"] == ing[-1] and f["ingreso_lag7"] == ing[-7] and f["ingreso_lag14"] == ing[-14]
    assert f["ingreso_media7"] == pytest.approx(s[-7:].mean()) and f["ingreso_media30"] == pytest.approx(s[-30:].mean())
    assert f["ingreso_std14"] == pytest.approx(s[-14:].std(ddof=1))  # pandas rolling().std() usa ddof=1
    assert f["egreso_std30"] == pytest.approx(np.asarray(egr)[-30:].std(ddof=1))
    assert (f["dow"], f["dom"], f["mes"], f["es_finde"], f["es_quincena_o_finmes"]) == (0, 16, 11, 0, 1)
    assert f["usa_fiado"] == 1 and f["usa_billetera_digital"] == 0 and f["n_trabajadores"] == 1
    sabado = fml.fila_features(PERFIL, ing, egr, date(2026, 11, 28))
    assert (sabado["dow"], sabado["es_finde"], sabado["es_quincena_o_finmes"]) == (5, 1, 1)
    assert fml.fila_features(PERFIL, ing, egr, date(2026, 11, 18))["es_quincena_o_finmes"] == 0


def test_antiguedad_en_meses():
    from datetime import datetime

    assert fml.antiguedad_meses(datetime(2026, 8, 15, 8, 0), date(2026, 11, 14)) == 2
    assert fml.antiguedad_meses(datetime(2026, 8, 15, 8, 0), date(2026, 11, 15)) == 3
    assert fml.antiguedad_meses(datetime(2026, 11, 14, 8, 0), date(2026, 11, 14)) == 0


def test_no_se_usan_features_prohibidos(scoring, motor_lightgbm):
    assert not PROHIBIDOS & set(motor_lightgbm.features) and not PROHIBIDOS & set(scoring.columnas)
    for modulo in (fml, credito):  # ni el código que arma los features los lee (los docstrings sí los mencionan)
        usados = {n.attr for n in ast.walk(ast.parse(inspect.getsource(modulo))) if isinstance(n, ast.Attribute)}
        usados |= {n.id for n in ast.walk(ast.parse(inspect.getsource(modulo))) if isinstance(n, ast.Name)}
        assert not PROHIBIDOS & usados, modulo.__name__
        assert "Evento" not in usados and "Cliente" not in usados


# ── predicción: determinista, recursiva, banda ordenada ──


def test_prediccion_deterministica_recursiva_y_banda_ordenada(motor_lightgbm):
    ing, egr = _historia()
    a = fml.predecir(motor_lightgbm, PERFIL, ing, egr, date(2026, 11, 15), 30)
    b = fml.predecir(motor_lightgbm, PERFIL, ing, egr, date(2026, 11, 15), 30)
    assert a.ingreso == b.ingreso and a.egreso == b.egreso and a.sigma_bajo == b.sigma_bajo
    assert len(a.ingreso) == len(a.egreso) == 30 and all(v >= 0 for v in a.ingreso + a.egreso)
    for target in ("ingreso", "egreso"):
        assert all(p10 <= p50 <= p90 for p10, p50, p90 in a.cuantiles[target])
    anchos = [a.ancho_bajo(h) for h in range(1, 31)]
    assert anchos == sorted(anchos) and anchos[0] > 0 and anchos[-1] > anchos[0]  # la banda crece con el horizonte
    # recursivo: cambiar solo el último día de la historia cambia el día siguiente Y los siguientes
    ing2 = ing[:-1] + [ing[-1] * 3]
    c = fml.predecir(motor_lightgbm, PERFIL, ing2, egr, date(2026, 11, 15), 30)
    assert c.ingreso[0] != a.ingreso[0] and c.ingreso[10] != a.ingreso[10]


def test_cuantiles_cruzados_se_ordenan():
    assert fml._ordenar(120.0, 100.0, 90.0) == (100.0, 100.0, 100.0)
    assert fml._ordenar(80.0, 100.0, 130.0) == (80.0, 100.0, 130.0)


def test_pago_fantasma_de_los_dias_5_y_15_se_neutraliza(motor_lightgbm):
    ing, egr = _historia()
    fila5 = fml.fila_features(PERFIL, ing, egr, date(2026, 12, 5))
    assert fml._egreso(fila5)["dom"] == 4 and fml._egreso({**fila5, "dom": 15})["dom"] == 14
    assert fml._egreso({**fila5, "dom": 20})["dom"] == 20
    crudo = fml._predecir(motor_lightgbm, "egreso", 50, [fila5])[0]
    neutro = fml._predecir(motor_lightgbm, "egreso", 50, [fml._egreso(fila5)])[0]
    assert crudo > neutro * 1.5  # el modelo trae un pago grande el día 5 (proveedor): sería doble conteo con los eventos


def test_historia_corta_no_se_predice():
    with pytest.raises(ValueError, match="30 días"):
        fml.predecir(None, PERFIL, [1.0] * 10, [1.0] * 10, HOY, 5)


# ── forecast integrado (BD de pruebas con la demo de Pedro) ──


def _sin_meta(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "meta"}


@pytest.mark.db
def test_forecast_con_lightgbm(db, reloj_fijo, motor_lightgbm):
    f = finanzas.forecast(db, E, 30)
    assert f.meta.modelo == "forecast-lgbm-quantile" and f.meta.modelo_version == "lgbm_cuantiles-1.0"
    assert f.meta.fallback_usado is False and getattr(f.meta, "fallback_motivo", None) is None
    assert f.saldo_actual == Decimal("2340.00") and len(f.serie) == 30 and f.serie[0].fecha == date(2026, 11, 15)
    assert all(p.p10 <= p.p50 <= p.p90 for p in f.serie)
    anchos = [p.p50 - p.p10 for p in f.serie]
    assert anchos == sorted(anchos) and anchos[0] > 0
    assert f.baseline.nombre == "naive_estacional" and f.modelo_metricas is not None
    assert f.modelo_metricas.mae_backtest is not None and 0 <= f.modelo_metricas.cobertura_p10_p90 <= 1
    # los pagos con fecha van ENCIMA del flujo ordinario del modelo (sin doble conteo): PED-0012 sigue ahí
    pago = next(e for e in f.proximos_eventos if e.ref_id == "PED-0012")
    assert pago.fecha == date(2026, 11, 30) and pago.monto == Decimal("-2400.00")
    dia = next(p for p in f.serie if p.fecha == pago.fecha)
    assert dia.egresos_esperados >= Decimal("2400.00")
    # saldo = saldo de ayer + ingresos − egresos
    saldo = Decimal("2340.00")
    for p in f.serie:
        saldo += p.ingresos_esperados - p.egresos_esperados
        assert float(p.p50) == pytest.approx(float(saldo), abs=0.5)
    assert f.dia_critico is None or f.dia_critico.saldo_p50 < f.minimo_operativo
    b = finanzas.forecast(db, E, 30)
    assert _sin_meta(f.model_dump(mode="json")) == _sin_meta(b.model_dump(mode="json"))  # determinístico


@pytest.mark.db
def test_chequeo_simulador_y_alertas_funcionan_con_lightgbm(db, reloj_fijo, motor_lightgbm):
    from app.services import alertas

    c = finanzas.chequeo_pedido(db, E, "Distribuidora Andina", 2400, date(2026, 11, 30))
    assert c.meta.modelo == "forecast-lgbm-quantile" and c.meta.fallback_usado is False
    assert c.estado_caja in ("te_alcanza", "justo", "no_te_alcanza")
    s = finanzas.simular(db, E, [])
    assert s.meta.modelo == "simulador-deterministico" and s.meta.fallback_usado is False and s.mejora == 0
    assert all(a.meta.fallback_usado is False and "forecast-lgbm-quantile" in a.meta.modelo
               for a in alertas.evaluar_alertas(db, E))  # fmt: skip


@pytest.mark.db
def test_motor_baseline_por_configuracion(db, reloj_fijo, monkeypatch):
    monkeypatch.setattr(settings, "FORECAST_MOTOR", "baseline")
    f = finanzas.forecast(db, E, 30)
    assert f.meta.fallback_usado is True and "FORECAST_MOTOR=baseline" in f.meta.fallback_motivo
    assert f.meta.modelo == "forecast-naive-estacional" and f.modelo_metricas is None
    assert f.dia_critico.saldo_p50 == Decimal("-650.00")


@pytest.mark.db
def test_fallback_si_la_carga_falla(db, reloj_fijo, monkeypatch):
    monkeypatch.setattr(settings, "FORECAST_MOTOR", "lightgbm")
    monkeypatch.setattr(fml, "cargar_forecast", lambda: (None, "OSError: libgomp.so.1: cannot open shared object file"))
    f = finanzas.forecast(db, E, 30)
    assert f.meta.fallback_usado is True and "libgomp" in f.meta.fallback_motivo
    assert f.dia_critico.saldo_p50 == Decimal("-650.00")  # mismo baseline de siempre


@pytest.mark.db
def test_fallback_si_la_prediccion_lanza(db, reloj_fijo, monkeypatch, motor_lightgbm):
    def _falla(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(fml, "predecir", _falla)
    f = finanzas.forecast(db, E, 30)
    assert f.meta.fallback_usado is True and "boom" in f.meta.fallback_motivo and len(f.serie) == 30


@pytest.mark.db
def test_fallback_sin_artefactos(db, reloj_fijo, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FORECAST_MOTOR", "lightgbm")
    monkeypatch.setattr(settings, "ML_ARTIFACTS_DIR", str(tmp_path))
    modelo_ml.limpiar_cache()
    f = finanzas.forecast(db, E, 30)
    assert f.meta.fallback_usado is True and "metadata.json" in f.meta.fallback_motivo
    d = modelo_ml.diagnostico_forecast()
    assert d["estado"] == "no_disponible" and d["artefactos"] is False
    modelo_ml.limpiar_cache()


@pytest.mark.db
def test_historia_insuficiente_cae_al_baseline_con_motivo(db, reloj_fijo, motor_lightgbm):
    primer = db.scalar(select(func.min(m.Transaccion.fecha_hora)).where(
        m.Transaccion.empresa_id == E))  # fmt: skip
    corte = primer.date() + timedelta(days=12)
    proy = fc.proyectar(db, E, corte, 14)
    assert proy.ml is None and proy.motor.fallback is True and "Historia insuficiente" in proy.motor.motivo


# ── /health ──


def test_health_forecast_y_scoring_ok(client, motor_lightgbm, scoring):
    h = client.get(f"{P}/health").json()["componentes"]
    assert h["forecast"]["estado"] == "ok" and h["forecast"]["modelo"] == "forecast-lgbm-quantile"
    assert h["forecast"]["modelo_version"] == "lgbm_cuantiles-1.0" and h["forecast"]["ml"]["cargado"] is True
    assert h["credit_scoring"]["estado"] == "ok" and h["credit_scoring"]["ml"]["motivo"] is None
    assert h["riesgo_atraso"]["estado"] == "baseline"


def test_health_no_recarga_los_modelos_en_cada_request(client, motor_lightgbm, scoring, monkeypatch):
    def _prohibido(*_a, **_k):
        raise AssertionError("el health no debe volver a cargar modelos ya cacheados")

    monkeypatch.setattr(modelo_ml, "_cargar_joblib", _prohibido)
    for _ in range(2):
        h = client.get(f"{P}/health").json()["componentes"]
        assert h["forecast"]["estado"] == "ok" and h["credit_scoring"]["estado"] == "ok"


def test_health_baseline_y_no_disponible_con_motivo(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ML_ARTIFACTS_DIR", str(tmp_path))
    modelo_ml.limpiar_cache()
    h = client.get(f"{P}/health").json()["componentes"]
    assert h["forecast"]["estado"] == "baseline" and h["forecast"]["ml"]["estado"] == "desactivado"  # conftest: baseline
    assert "FORECAST_MOTOR=baseline" in h["forecast"]["ml"]["motivo"]
    assert h["credit_scoring"]["estado"] == "no_disponible" and "metadata.json" in h["credit_scoring"]["ml"]["motivo"]
    monkeypatch.setattr(settings, "FORECAST_MOTOR", "lightgbm")
    h = client.get(f"{P}/health").json()["componentes"]
    assert h["forecast"]["estado"] == "baseline" and h["forecast"]["ml"]["estado"] == "no_disponible"
    assert h["forecast"]["modelo"] == "forecast-naive-estacional" and h["forecast"]["ml"]["motivo"]
    modelo_ml.limpiar_cache()


# ── credit scoring ──


def test_categorias_por_rango_del_metadata():
    rangos = _metadata("credit_scoring")["rangos_categoria"]
    assert list(rangos.values()) == ["0-39", "40-69", "70-100"]
    assert [credito.categoria(s) for s in (0, 39, 40, 69, 70, 100)] == ["Rojo", "Rojo", "Amarillo", "Amarillo", "Verde", "Verde"]


@pytest.mark.db
def test_score_crediticio_de_pedro(db, reloj_fijo, scoring):
    r = credito.score_crediticio(db, E)
    assert r["disponible"] is True and isinstance(r["score"], int) and 0 <= r["score"] <= 100
    assert r["categoria"] == credito.categoria(r["score"])
    assert set(r["features"]) == {c for c in scoring.columnas if not c.startswith("rubro_")} | {"rubro"}
    assert r["features"]["rubro"] == "bodega" and r["features"]["tiene_ruc"] in (0, 1)
    assert 0 <= r["features"]["pct_dias_con_venta"] <= 1 and 0 <= r["features"]["dias_desde_ultimo_registro"] <= 1
    assert r["meta"]["modelo"] == "credit-scoring-logreg" and r["meta"]["fallback_usado"] is False
    assert "no una evaluación crediticia" in r["limites"] and "sintéticos" in r["limites"]
    otra = credito.score_crediticio(db, E)  # determinístico
    assert (otra["score"], otra["features"]) == (r["score"], r["features"])
    fila, imputados = credito.vector(scoring, {**r["features"], "pct_pagos_a_tiempo": None}, "bodega")
    assert len(fila) == 16 and "pct_pagos_a_tiempo" in imputados
    i = list(scoring.columnas).index("pct_pagos_a_tiempo")
    assert fila[i] == pytest.approx(scoring.scaler.mean_[i])  # imputado con la media de entrenamiento (aporte neutro)


@pytest.mark.db
def test_score_crediticio_aplica_la_formula_del_metadata(db, reloj_fijo, scoring):
    features, info = credito.calcular_features(db, db.get(m.Empresa, E), HOY)
    fila, _ = credito.vector(scoring, features, info["rubro"])
    import pandas as pd

    X = pd.DataFrame([fila], columns=list(scoring.columnas))
    esperado = round(float(scoring.modelo.predict_proba(scoring.scaler.transform(X))[:, 1][0]) * 100)
    assert credito.score_crediticio(db, E)["score"] == esperado


@pytest.mark.db
def test_deuda_sin_vencer_no_cuenta_como_atrasada(db, reloj_fijo):
    inicio = HOY - timedelta(days=60)
    assert db.query(m.Deuda).filter_by(empresa_id=E).count() >= 1  # PED-0012 vence el 30/11: no se puede juzgar todavía
    pct, mora = credito._puntualidad_deudas(db, E, inicio, HOY)
    assert pct != 0.0  # lo que aún no vence nunca cuenta como atrasado
    from tests._b_util import deuda_proveedor

    d = deuda_proveedor(db, 100, HOY - timedelta(days=5), HOY - timedelta(days=20))  # venció hace 5 días, impaga
    pct2, mora2 = credito._puntualidad_deudas(db, E, inicio, HOY)
    assert pct2 is not None and pct2 < 1.0 and (mora2 or 0) > (mora or 0)
    tx(db, "pago_proveedor", 100, HOY - timedelta(days=6), deuda_id=d.deuda_id)  # pagó un día antes: a tiempo
    pct3, mora3 = credito._puntualidad_deudas(db, E, inicio, HOY)
    assert pct3 > pct2 and mora3 < mora2


@pytest.mark.db
def test_score_crediticio_sin_historia_no_disponible(db, reloj_fijo, scoring):
    primer = db.scalar(select(func.min(m.Transaccion.fecha_hora)).where(m.Transaccion.empresa_id == E))
    r = credito.score_crediticio(db, E, primer.date() + timedelta(days=3))
    assert r["disponible"] is False and r["score"] is None and "Historia insuficiente" in r["motivo"]
    assert r["meta"]["fallback_usado"] is False


@pytest.mark.db
def test_score_crediticio_fallback_si_no_carga(db, reloj_fijo, monkeypatch):
    monkeypatch.setattr(credito, "cargar_scoring", lambda: (None, "ModuleNotFoundError: sklearn"))
    r = credito.score_crediticio(db, E)
    assert r["disponible"] is False and r["categoria"] is None and "sklearn" in r["motivo"]
    assert r["meta"]["fallback_usado"] is True and "sklearn" in r["meta"]["fallback_motivo"]


@pytest.mark.db
def test_salud_incluye_score_crediticio_sin_reemplazar_el_de_habitos(client_db, reloj_fijo, scoring):
    r = client_db.get(f"{EMP}/salud").json()
    assert isinstance(r["score"], int) and [s["id"] for s in r["subindicadores"]] == [
        "constancia_registro", "separacion_personal", "impuestos_al_dia"]  # fmt: skip
    assert r["meta"]["modelo"] == "score-reglas"
    sc = r["score_crediticio"]
    assert sc["disponible"] is True and sc["categoria"] in ("Rojo", "Amarillo", "Verde")
    assert sc["meta"]["modelo"] == "credit-scoring-logreg" and set(sc["rangos"]) == {"Rojo", "Amarillo", "Verde"}


@pytest.mark.db
def test_los_get_no_escriben(client_db, db, reloj_fijo, motor_lightgbm, scoring):
    tablas = [m.PrediccionSaldo, m.ScoreSalud, m.Alerta, m.Transaccion, m.ForecastAjuste]
    antes = [db.scalar(select(func.count()).select_from(t)) for t in tablas]
    for ruta in ("forecast", "salud", "resumen", "alertas", "disponible"):
        client_db.get(f"{EMP}/{ruta}")
    client_db.get(f"{P}/health")
    despues = [db.scalar(select(func.count()).select_from(t)) for t in tablas]
    assert antes == despues


@pytest.mark.db
def test_asistente_responde_con_el_forecast_lightgbm(client_db, reloj_fijo, motor_lightgbm):
    r = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?", "canal": "app"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intencion"] == "estado_caja" and d["verificacion_cifras"]["ok"] is True
    assert "obtener_forecast" in [h["nombre"] for h in d["herramientas_llamadas"]]
    assert d["respuesta"].startswith("Hoy tienes S/ 2 340")
