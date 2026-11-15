"""Exporta lo que el BACKEND calcula para Pedro (EMP-0001) sobre data/csv: data/demo_pedro_backend.json.

El generador (data/generate_synthetic_data.mjs) lo lee para escribir las filas de resultado de Pedro que no puede
calcular en JavaScript: `predicciones_saldo` (forecast LightGBM y baseline a 30 días) y sus `alertas` (incluida la de
faltante de caja, que sale del forecast). Así esas filas son la salida real del backend y no cifras escritas a mano.
Nada de esto es entrada del forecast (el backend no lee `predicciones_saldo` y las alertas no cambian la proyección), por
eso basta un paso: generar -> exportar -> generar (el segundo paso solo cambia esas filas).

Corre dentro de la imagen del backend con una BD local propia (nunca la principal, la de pruebas ni producción):

    docker compose run --rm -v "<repo>/data/pipeline_python:/pipeline:ro" -e PYTHONPATH=/app backend \\
        python /pipeline/exportar_demo_backend.py --bd cajaclara_export > ../data/demo_pedro_backend.json

`--dir` cambia la carpeta de CSV (por defecto DATA_CSV_DIR) y `--borrar` elimina la BD al terminar.
"""

import argparse
import contextlib
import io
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.cargar_csv import asegurar_bd, cargar
from app.db.session import crear_engine
from app.services.alertas import motor as mot
from app.services.alertas import reglas as r
from app.services.finanzas import proyeccion as fc

EMPRESA = "EMP-0001"
CORTE = date(2026, 11, 14)
HORIZONTE = 30


def _num(x) -> float | None:
    return None if x is None else round(float(x), 2)


def _forecast(db: Session, motor: str) -> dict:
    proy = fc.proyectar(db, EMPRESA, CORTE, HORIZONTE, motor=motor)
    puntos = proy.puntos()
    critico = fc.dia_critico(proy, puntos)
    return {
        "modelo": proy.motor.modelo, "modelo_version": proy.motor.version, "fallback_usado": proy.motor.fallback,
        "saldo_actual": _num(proy.saldo_actual),
        "dia_critico": None if critico is None else {"fecha": critico.fecha.isoformat(), "saldo_p50": _num(critico.saldo_p50),
                                                     "probabilidad_deficit": critico.probabilidad_deficit},
        "serie": [{"fecha": p.fecha.isoformat(), "p10": _num(p.p10), "p50": _num(p.p50), "p90": _num(p.p90)}
                  for p in fc.serie(proy, puntos)],
    }  # fmt: skip


def _alertas(db: Session) -> list[dict]:
    ctx = r.Contexto(db, EMPRESA, CORTE)
    return [{"tipo": c.tipo.value, "fecha_evento": c.fecha_evento.isoformat(), "monto": _num(c.monto),
             "probabilidad": c.probabilidad, "nivel_riesgo": c.nivel.value if c.nivel else None,
             "causas": c.causas, "accion_sugerida": c.accion, "entidad_tipo": c.entidad_tipo, "entidad_id": c.entidad_id}
            for c in mot._candidatas(ctx, mot.reglas_para(None))]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bd", required=True, help="BD local propia para cargar el CSV (se recrea)")
    ap.add_argument("--dir", help="carpeta de los CSV (por defecto DATA_CSV_DIR)")
    ap.add_argument("--borrar", action="store_true", help="borrar la BD al terminar")
    args = ap.parse_args(argv)
    if args.bd in (settings.POSTGRES_DB, settings.POSTGRES_TEST_DB) or settings.es_produccion:
        print(f"La BD {args.bd} no puede ser la principal, la de pruebas ni producción.", file=sys.stderr)
        return 2
    asegurar_bd(args.bd)
    engine = crear_engine(settings._url(args.bd))
    with contextlib.redirect_stdout(io.StringIO()):
        cargar(engine, Path(args.dir) if args.dir else None)
    with Session(engine) as db:
        salida = {
            "generado_por": "data/pipeline_python/exportar_demo_backend.py (backend sobre data/csv; no editar a mano)",
            "empresa_id": EMPRESA, "fecha_corte": CORTE.isoformat(), "horizonte_dias": HORIZONTE,
            "forecast": {"lightgbm": _forecast(db, "lightgbm"), "baseline": _forecast(db, "baseline")},
            "alertas": _alertas(db),
        }  # fmt: skip
        db.rollback()
    engine.dispose()
    if args.borrar:
        admin = crear_engine(settings._url("postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{args.bd}"'))
        admin.dispose()
    print(json.dumps(salida, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
