"""Backtest del forecast (B14): MAE / MAPE / cobertura p10–p90 y precision / recall de la alerta `faltante_caja`.

    python -m tests.eval_forecast                    # BD de desarrollo (solo lectura), EMP-0001, horizonte 14
    python -m tests.eval_forecast --test             # BD de pruebas
    python -m tests.eval_forecast --horizonte 7 --json
    (en docker:  docker compose run --rm backend python -m tests.eval_forecast)

Cómo: para cada día de corte con ≥ 4 semanas de historia y `horizonte` días reales por delante, se proyecta con
`proyeccion.proyectar(..., fecha_corte=corte)` (solo usa lo registrado hasta ese día, sin fuga) y se compara con lo
que realmente pasó:
- Saldo de caja a h días (lo que ve el usuario): forecast vs "persistencia" (el saldo se queda igual). MAE, MAPE,
  sesgo y cobertura de la banda p10–p90 por horizonte.
- Flujo ordinario diario: naive estacional (media del mismo día de la semana, 4 semanas) vs "igual que ayer".
- Alerta `faltante_caja` (regla: algún p50 < 0 en los próximos 14 días) y la variante con el mismo umbral que la
  etiqueta (p50 < mínimo operativo) contra `saldo_diario.deficit_14d`. Aquí la etiqueta se usa solo para evaluar;
  nunca es feature (PLAN §8).
- Modelo LightGBM: no se evalúa porque no es integrable (modelo_ml.py explica qué features faltan en la BD).
No escribe nada en la BD. No lo recoge pytest (no empieza con test_).
"""

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models as m
from app.db.session import crear_engine
from app.services.finanzas import consultas as q
from app.services.finanzas import proyeccion as fc
from app.services.finanzas.modelo_ml import diagnostico_forecast


def _mae(errores: list[float]) -> float | None:
    return round(sum(abs(e) for e in errores) / len(errores), 2) if errores else None


def _mape(pares: list[tuple[float, float]]) -> float | None:
    validos = [(r, p) for r, p in pares if abs(r) > 1e-9]
    return round(100 * sum(abs(r - p) / abs(r) for r, p in validos) / len(validos), 1) if validos else None


def _clasificacion(pred: list[bool], real: list[bool]) -> dict:
    tp = sum(p and r for p, r in zip(pred, real, strict=True))
    fp = sum(p and not r for p, r in zip(pred, real, strict=True))
    fn = sum(r and not p for p, r in zip(pred, real, strict=True))
    tn = len(pred) - tp - fp - fn
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "tasa_falsas_alarmas": round(fp / (fp + tn), 3) if fp + tn else None}  # fmt: skip


def evaluar(db: Session, empresa_id: str = "EMP-0001", horizonte: int = 14, desde: date | None = None,
            hasta: date | None = None) -> dict:  # fmt: skip
    empresa = q.empresa_o_404(db, empresa_id)
    ultimo_ts = db.scalar(select(func.max(m.Transaccion.fecha_hora)).where(m.Transaccion.empresa_id == empresa_id))
    if ultimo_ts is None:
        raise SystemExit("La empresa no tiene movimientos.")
    ultimo = q.dia_lima(ultimo_ts)
    primer = q.primer_dia_con_datos(db, empresa_id, ultimo)
    desde = desde or primer + timedelta(days=7 * fc.SEMANAS)
    hasta = hasta or ultimo - timedelta(days=horizonte)
    if desde > hasta:
        raise SystemExit(f"No hay cortes con {horizonte} días reales por delante entre {desde} y {hasta}.")
    saldo_real = {}
    d = desde
    while d <= ultimo:
        saldo_real[d] = float(q._saldo(db, empresa, d))
        d += timedelta(days=1)
    flujos = q.flujos_ordinarios(db, empresa_id, primer, ultimo, ultimo)
    etiquetas = dict(db.execute(select(m.SaldoDiario.fecha, m.SaldoDiario.deficit_14d).where(
        m.SaldoDiario.empresa_id == empresa_id)).all())  # fmt: skip

    por_h = {h: {"err": [], "pares": [], "dentro": 0, "persist": [], "persist_pares": []} for h in range(1, horizonte + 1)}
    flujo_est, flujo_ayer, flujo_pares = [], [], []
    pred_regla, pred_umbral, real_def = [], [], []
    cortes = 0
    corte = desde
    while corte <= hasta:
        proy = fc.proyectar(db, empresa_id, corte, horizonte)
        serie = fc.serie(proy, proy.puntos())
        for h, p in enumerate(serie, start=1):
            real = saldo_real[p.fecha]
            b = por_h[h]
            b["err"].append(float(p.p50) - real)
            b["pares"].append((real, float(p.p50)))
            b["dentro"] += int(float(p.p10) <= real <= float(p.p90))
            b["persist"].append(float(proy.saldo_actual) - real)
            b["persist_pares"].append((real, float(proy.saldo_actual)))
        manana = corte + timedelta(days=1)
        real_flujo = float(flujos.get(manana, q.FlujoDia()).neto)
        pred = float(proy.media_ing[manana.weekday()] - proy.media_egr[manana.weekday()])
        flujo_est.append(pred - real_flujo)
        flujo_ayer.append(float(flujos.get(corte, q.FlujoDia()).neto) - real_flujo)
        flujo_pares.append((real_flujo, pred))
        etiqueta = etiquetas.get(corte)
        if etiqueta is not None:
            proximos = serie[:14]
            pred_regla.append(any(p.p50 < 0 for p in proximos))
            pred_umbral.append(any(p.p50 < proy.minimo for p in proximos))
            real_def.append(bool(etiqueta))
        cortes += 1
        corte += timedelta(days=1)

    horizontes = {}
    for h, b in por_h.items():
        n = len(b["err"])
        horizontes[h] = {"n": n, "mae": _mae(b["err"]), "mape_pct": _mape(b["pares"]),
                         "sesgo": round(sum(b["err"]) / n, 2) if n else None,
                         "cobertura_p10_p90": round(b["dentro"] / n, 3) if n else None,
                         "mae_persistencia": _mae(b["persist"]), "mape_persistencia_pct": _mape(b["persist_pares"])}  # fmt: skip
    ml = diagnostico_forecast()
    return {
        "empresa_id": empresa_id, "cortes": cortes, "desde": desde.isoformat(), "hasta": hasta.isoformat(),
        "horizonte": horizonte, "saldo_por_horizonte": horizontes,
        "flujo_diario": {"mae_naive_estacional": _mae(flujo_est), "mae_igual_que_ayer": _mae(flujo_ayer),
                         "mape_naive_estacional_pct": _mape(flujo_pares)},
        "faltante_caja": {"n": len(real_def), "positivos_reales": sum(real_def),
                          "regla_alerta_p50_menor_0": _clasificacion(pred_regla, real_def),
                          "umbral_minimo_operativo": _clasificacion(pred_umbral, real_def)},
        "modelo_ml": {"estado": ml["estado"], "motivos": ml.get("motivos", [])},
    }  # fmt: skip


def _imprimir(r: dict) -> None:
    print(f"Backtest del forecast · {r['empresa_id']} · {r['cortes']} cortes ({r['desde']} → {r['hasta']}), "
          f"horizonte {r['horizonte']} días\n")  # fmt: skip
    print("Saldo de caja a h días: forecast (naive estacional + pagos con fecha) vs persistencia")
    print(f"{'h':>3} {'MAE':>9} {'MAPE%':>7} {'sesgo':>9} {'cob p10–p90':>12} {'MAE pers.':>10} {'MAPE% pers.':>12}")
    for h, x in r["saldo_por_horizonte"].items():
        if h in (1, 3, 7, 10, 14) or h == r["horizonte"]:
            print(f"{h:>3} {x['mae']:>9} {x['mape_pct']:>7} {x['sesgo']:>9} {x['cobertura_p10_p90']:>12} "
                  f"{x['mae_persistencia']:>10} {x['mape_persistencia_pct']:>12}")  # fmt: skip
    f = r["flujo_diario"]
    print(f"\nFlujo ordinario de mañana: MAE naive estacional {f['mae_naive_estacional']} · MAE 'igual que ayer' "
          f"{f['mae_igual_que_ayer']} · MAPE naive estacional {f['mape_naive_estacional_pct']} %")  # fmt: skip
    a = r["faltante_caja"]
    print(f"\nAlerta faltante_caja vs saldo_diario.deficit_14d (n = {a['n']}, positivos reales = {a['positivos_reales']})")
    for nombre in ("regla_alerta_p50_menor_0", "umbral_minimo_operativo"):
        print(f"  {nombre}: {a[nombre]}")
    if a["positivos_reales"] == 0:
        print("  (la historia sintética no tiene ningún día con déficit a 14 días: el recall no es medible)")
    print(f"\nModelo LightGBM: {r['modelo_ml']['estado']} — " + "; ".join(r["modelo_ml"]["motivos"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest del forecast de TuCaserito (solo lectura).")
    parser.add_argument("--test", action="store_true", help="usar la BD de pruebas")
    parser.add_argument("--empresa", default="EMP-0001")
    parser.add_argument("--horizonte", type=int, default=14)
    parser.add_argument("--desde", type=date.fromisoformat)
    parser.add_argument("--hasta", type=date.fromisoformat)
    parser.add_argument("--json", action="store_true", help="imprimir el resultado en JSON")
    args = parser.parse_args(argv)
    if settings.es_produccion:
        raise SystemExit("El backtest no corre contra producción.")
    engine = crear_engine(settings.test_database_url if args.test else settings.database_url)
    with Session(engine) as db:
        r = evaluar(db, args.empresa, args.horizonte, args.desde, args.hasta)
        db.rollback()
    engine.dispose()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=lambda x: float(x) if isinstance(x, Decimal) else str(x))
          if args.json else "", end="")  # fmt: skip
    if not args.json:
        _imprimir(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
