"""Backtest del forecast (B14): LightGBM vs baseline naive estacional — MAE / MAPE / cobertura p10–p90 y alerta `faltante_caja`.

    python -m tests.eval_forecast                    # BD de desarrollo (solo lectura), EMP-0001, horizonte 14
    python -m tests.eval_forecast --empresa todas    # resumen de todas las empresas con historia (horizonte 7)
    python -m tests.eval_forecast --test             # BD de pruebas
    python -m tests.eval_forecast --horizonte 7 --json
    (en docker:  docker compose run --rm backend python -m tests.eval_forecast)

Cómo: para cada día de corte con ≥ 31 días de historia y `horizonte` días reales por delante, se proyecta con
`proyeccion.proyectar(..., fecha_corte=corte, motor=...)` para CADA motor (solo usa lo registrado hasta ese día, sin fuga)
y se compara con lo que realmente pasó:
- Saldo de caja a h días (lo que ve el usuario): lightgbm vs baseline vs "persistencia" (el saldo se queda igual). MAE, MAPE,
  sesgo y cobertura de la banda p10–p90 por horizonte.
- Flujo ordinario de mañana (ingreso, egreso y neto): MAE de cada motor y de "igual que ayer".
- Alerta `faltante_caja` (regla: algún p50 < 0 en los próximos 14 días) y la variante con el umbral del mínimo operativo
  contra `saldo_diario.deficit_14d` (la etiqueta se usa solo para evaluar; nunca es feature, PLAN §8).
Los dos motores corren sobre los MISMOS cortes. Nota: el LightGBM se entrenó con datos sintéticos de otra escala; aquí se mide
cómo se comporta sobre la historia de la BD (train/serve skew), no su MAE de entrenamiento.
No escribe nada en la BD. No lo recoge pytest (no empieza con test_).
"""

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.config import settings
from app.db import models as m
from app.db.session import crear_engine
from app.services.finanzas import consultas as q
from app.services.finanzas import proyeccion as fc
from app.services.finanzas.modelo_ml import diagnostico_forecast

MOTORES = ("baseline", "lightgbm")


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


def _flujo_manana(proy: fc.Proyeccion, manana: date) -> tuple[float, float]:
    """(ingreso, egreso) ordinarios esperados para mañana según el motor de la proyección."""
    if proy.ml is not None:
        return float(proy.ml.ingreso[0]), float(proy.ml.egreso[0])
    wd = manana.weekday()
    return float(proy.media_ing[wd]), float(proy.media_egr[wd])


def evaluar(db: Session, empresa_id: str = "EMP-0001", horizonte: int = 14, desde: date | None = None,
            hasta: date | None = None) -> dict:  # fmt: skip
    empresa = q.empresa_o_404(db, empresa_id)
    ultimo_ts = db.scalar(select(func.max(m.Transaccion.fecha_hora)).where(m.Transaccion.empresa_id == empresa_id))
    if ultimo_ts is None:
        raise SystemExit("La empresa no tiene movimientos.")
    ultimo = q.dia_lima(ultimo_ts)
    primer = q.primer_dia_con_datos(db, empresa_id, ultimo)
    desde = desde or primer + timedelta(days=31)  # 28 días para el baseline, 30 para el LightGBM (+1 de margen)
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

    acum = {mo: {"h": {h: {"err": [], "pares": [], "dentro": 0, "persist": [], "persist_pares": []}
                       for h in range(1, horizonte + 1)},
                 "ing": [], "egr": [], "neto": [], "neto_pares": [], "regla": [], "umbral": [], "real": [], "fallbacks": 0}
            for mo in MOTORES}  # fmt: skip
    ayer = []
    cortes = 0
    corte = desde
    while corte <= hasta:
        manana = corte + timedelta(days=1)
        real_f = flujos.get(manana, q.FlujoDia())
        etiqueta = etiquetas.get(corte)
        ayer.append(float(flujos.get(corte, q.FlujoDia()).neto) - float(real_f.neto))
        for motor in MOTORES:
            proy = fc.proyectar(db, empresa_id, corte, horizonte, motor=motor)
            a = acum[motor]
            if motor == "lightgbm" and proy.ml is None:  # sin LightGBM en este corte: no se compara
                a["fallbacks"] += 1
                continue
            serie = fc.serie(proy, proy.puntos())
            for h, p in enumerate(serie, start=1):
                real, b = saldo_real[p.fecha], a["h"][h]
                b["err"].append(float(p.p50) - real)
                b["pares"].append((real, float(p.p50)))
                b["dentro"] += int(float(p.p10) <= real <= float(p.p90))
                b["persist"].append(float(proy.saldo_actual) - real)
                b["persist_pares"].append((real, float(proy.saldo_actual)))
            ing, egr = _flujo_manana(proy, manana)
            a["ing"].append(ing - float(real_f.ingreso))
            a["egr"].append(egr - float(real_f.egreso))
            a["neto"].append((ing - egr) - float(real_f.neto))
            a["neto_pares"].append((float(real_f.neto), ing - egr))
            if etiqueta is not None:
                a["real"].append(bool(etiqueta))
                a["regla"].append(any(p.p50 < 0 for p in serie[:14]))
                a["umbral"].append(any(p.p50 < proy.minimo for p in serie[:14]))
        cortes += 1
        corte += timedelta(days=1)

    salida = {}
    for motor, a in acum.items():
        horizontes = {}
        for h, b in a["h"].items():
            n = len(b["err"])
            horizontes[h] = {"n": n, "mae": _mae(b["err"]), "mape_pct": _mape(b["pares"]),
                             "sesgo": round(sum(b["err"]) / n, 2) if n else None,
                             "cobertura_p10_p90": round(b["dentro"] / n, 3) if n else None,
                             "mae_persistencia": _mae(b["persist"]),
                             "mape_persistencia_pct": _mape(b["persist_pares"])}  # fmt: skip
        n_reg = len(a["regla"])
        salida[motor] = {
            "cortes_evaluados": len(a["neto"]), "cortes_con_baseline_por_fallback": a["fallbacks"],
            "saldo_por_horizonte": horizontes,
            "flujo_ordinario_de_manana": {"mae_ingreso": _mae(a["ing"]), "mae_egreso": _mae(a["egr"]),
                                          "mae_neto": _mae(a["neto"]), "mape_neto_pct": _mape(a["neto_pares"])},
            "faltante_caja": {"n": n_reg, "positivos_reales": sum(a["real"]),
                              "regla_alerta_p50_menor_0": _clasificacion(a["regla"], a["real"]),
                              "umbral_minimo_operativo": _clasificacion(a["umbral"], a["real"])},
        }  # fmt: skip
    ml = diagnostico_forecast()
    return {"empresa_id": empresa_id, "cortes": cortes, "desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "horizonte": horizonte, "motores": salida, "mae_neto_igual_que_ayer": _mae(ayer),
            "modelo_ml": {"estado": ml["estado"], "motivos": ml.get("motivos", [])}}  # fmt: skip


def _imprimir(r: dict) -> None:
    print(f"Backtest del forecast · {r['empresa_id']} · {r['cortes']} cortes ({r['desde']} → {r['hasta']}), "
          f"horizonte {r['horizonte']} días · LightGBM: {r['modelo_ml']['estado']}\n")  # fmt: skip
    print("Saldo de caja a h días (forecast + pagos con fecha) — MAE en S/ · cobertura de la banda p10–p90")
    cab = f"{'h':>3} | " + " | ".join(f"{mo:>9} MAE {'cob':>5}" for mo in MOTORES) + f" | {'persist.':>9}"
    print(cab)
    horizontes = list(r["motores"]["baseline"]["saldo_por_horizonte"])
    for h in horizontes:
        if h in (1, 3, 7, 10, 14) or h == r["horizonte"]:
            celdas = []
            for mo in MOTORES:
                x = r["motores"][mo]["saldo_por_horizonte"][h]
                celdas.append(f"{x['mae']!s:>13} {x['cobertura_p10_p90']!s:>5}")
            pers = r["motores"]["baseline"]["saldo_por_horizonte"][h]["mae_persistencia"]
            print(f"{h:>3} | " + " | ".join(celdas) + f" | {pers!s:>9}")
    print("\nFlujo ordinario de mañana (S/ por día) — MAE")
    for mo in MOTORES:
        f = r["motores"][mo]["flujo_ordinario_de_manana"]
        print(f"  {mo:>9}: ingreso {f['mae_ingreso']} · egreso {f['mae_egreso']} · neto {f['mae_neto']} "
              f"(MAPE neto {f['mape_neto_pct']} %) · cortes {r['motores'][mo]['cortes_evaluados']}"
              + (f" (+{r['motores'][mo]['cortes_con_baseline_por_fallback']} sin LightGBM)"
                 if r["motores"][mo]["cortes_con_baseline_por_fallback"] else ""))  # fmt: skip
    print(f"  {'ayer':>9}: neto {r['mae_neto_igual_que_ayer']}")
    for mo in MOTORES:
        a = r["motores"][mo]["faltante_caja"]
        print(f"\nAlerta faltante_caja [{mo}] vs saldo_diario.deficit_14d (n = {a['n']}, positivos reales = "
              f"{a['positivos_reales']})")  # fmt: skip
        for nombre in ("regla_alerta_p50_menor_0", "umbral_minimo_operativo"):
            print(f"  {nombre}: {a[nombre]}")
    if r["motores"]["baseline"]["faltante_caja"]["positivos_reales"] == 0:
        print("  (la historia no tiene ningún día con déficit a 14 días: el recall no es medible)")


def _resumen_todas(db: Session, horizonte: int) -> dict:
    """MAE del saldo a 1, 7 y `horizonte` días por empresa y motor (empresas con ≥ 45 días de historia)."""
    filas = []
    for emp in db.scalars(select(m.Empresa).order_by(m.Empresa.empresa_id)):
        try:
            r = evaluar(db, emp.empresa_id, horizonte)
        except SystemExit:
            continue
        fila = {"empresa_id": emp.empresa_id, "cortes": r["cortes"]}
        for mo in MOTORES:
            hs = r["motores"][mo]["saldo_por_horizonte"]
            for h in (1, 7, horizonte):
                fila[f"{mo}_mae_h{h}"] = hs[h]["mae"]
            fila[f"{mo}_cob_h{horizonte}"] = hs[horizonte]["cobertura_p10_p90"]
        filas.append(fila)
    return {"horizonte": horizonte, "empresas": filas}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest del forecast de TuCaserito (solo lectura).")
    parser.add_argument("--test", action="store_true", help="usar la BD de pruebas")
    parser.add_argument("--empresa", default="EMP-0001", help="id de empresa o 'todas'")
    parser.add_argument("--horizonte", type=int, default=14)
    parser.add_argument("--desde", type=date.fromisoformat)
    parser.add_argument("--hasta", type=date.fromisoformat)
    parser.add_argument("--json", action="store_true", help="imprimir el resultado en JSON")
    args = parser.parse_args(argv)
    if settings.es_produccion:
        raise SystemExit("El backtest no corre contra producción.")
    engine = crear_engine(settings.test_database_url if args.test else settings.database_url)
    with Session(engine) as db:
        r = _resumen_todas(db, args.horizonte if args.horizonte != 14 else 7) if args.empresa == "todas" else \
            evaluar(db, args.empresa, args.horizonte, args.desde, args.hasta)  # fmt: skip
        db.rollback()
    engine.dispose()
    if args.json:
        print(json.dumps(r, indent=2, ensure_ascii=False, default=lambda x: float(x) if isinstance(x, Decimal) else str(x)))
    elif args.empresa == "todas":
        h = r["horizonte"]
        print(f"MAE del saldo (S/) a 1, 7 y {h} días — baseline | lightgbm · fecha de hoy {reloj.hoy()}")
        for f in r["empresas"]:
            print(f"{f['empresa_id']} cortes {f['cortes']:>3} | " + " | ".join(
                f"h1 {f[mo + '_mae_h1']} h7 {f[mo + '_mae_h7']} h{h} {f[mo + f'_mae_h{h}']} cob {f[mo + f'_cob_h{h}']}"
                for mo in MOTORES))  # fmt: skip
    else:
        _imprimir(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
