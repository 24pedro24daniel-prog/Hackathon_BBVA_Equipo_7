"""
TuCaserito — Cargador de data/csv en PostgreSQL (psycopg v3).

Crea el esquema desde data/schema.sql (GENERADO desde backend/app/db/models.py con
data/pipeline_python/generar_schema.py), carga los CSV en orden de llaves foráneas y valida los conteos.

    python data/load_postgres.py                       # BD vacía: crea el esquema y carga
    python data/load_postgres.py --recrear             # borra SOLO las tablas y tipos del esquema y vuelve a crear
    python data/load_postgres.py --url postgresql://usuario:clave@localhost:5433/mi_bd

La URL sale de --url, de DATABASE_URL (entorno) o de data/.env. Nunca se imprime.

SALVAGUARDA DE PRODUCCIÓN: se rechaza cualquier host *.render.com o APP_ENV=produccion, salvo que se pase
    --produccion --confirmar <nombre_de_la_bd>
con el nombre exacto de la base de datos de destino (y aun así hace falta --recrear si ya hay tablas).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
CSV_DIR = BASE_DIR / "csv"
SCHEMA_PATH = BASE_DIR / "schema.sql"
ESQUEMA_JSON = BASE_DIR / "schema_esquema.json"
ENV_PATH = BASE_DIR / ".env"


def cargar_env(ruta: Path) -> None:
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def datos_url(url: str) -> tuple[str, str]:
    """(host, nombre de la base) sin exponer credenciales."""
    p = urlparse(url)
    return (p.hostname or "", unquote(p.path.lstrip("/")))


def verificar_destino(url: str, produccion: bool, confirmar: str | None) -> None:
    host, bd = datos_url(url)
    es_prod = host.endswith(".render.com") or host.startswith("dpg-") or os.environ.get("APP_ENV", "").lower() in ("produccion", "producción", "production")
    if not es_prod:
        return
    if not produccion or confirmar != bd:
        sys.exit(
            f"RECHAZADO: el destino parece PRODUCCIÓN (host '{host}', base '{bd}', APP_ENV='{os.environ.get('APP_ENV', '')}').\n"
            "Para cargar de verdad pasa --produccion --confirmar <nombre_exacto_de_la_bd>."
        )
    print(f"ATENCIÓN: cargando en PRODUCCIÓN (host '{host}', base '{bd}'), confirmado por el usuario.")


def leer_esquema() -> dict:
    if not ESQUEMA_JSON.exists():
        sys.exit("Falta data/schema_esquema.json: ejecuta PYTHONPATH=backend python data/pipeline_python/generar_schema.py")
    return json.loads(ESQUEMA_JSON.read_text(encoding="utf-8"))


def filas_csv(tabla: str) -> tuple[list[str], int]:
    ruta = CSV_DIR / f"{tabla}.csv"
    with ruta.open("r", encoding="utf-8", newline="") as f:
        lector = csv.reader(f)
        encabezado = next(lector)
        return encabezado, sum(1 for _ in lector)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="URL de PostgreSQL (por defecto DATABASE_URL o data/.env)")
    ap.add_argument("--recrear", action="store_true", help="borra las tablas y tipos del esquema antes de crear")
    ap.add_argument("--produccion", action="store_true", help="permite un destino de producción (requiere --confirmar)")
    ap.add_argument("--confirmar", help="nombre exacto de la BD de producción")
    args = ap.parse_args()

    cargar_env(ENV_PATH)
    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("No hay URL: usa --url, DATABASE_URL o data/.env")
    url = url.replace("postgresql+psycopg://", "postgresql://")
    verificar_destino(url, args.produccion, args.confirmar)

    import psycopg  # type: ignore

    esquema = leer_esquema()
    orden = esquema["orden_carga"]
    tablas_esquema = list(esquema["tablas"].keys())
    enums = list(esquema["enums"].keys())
    sql_esquema = SCHEMA_PATH.read_text(encoding="utf-8")

    host, bd = datos_url(url)
    print(f"Destino: host '{host}', base '{bd}'")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = ANY(%s)", (tablas_esquema,))
            existentes = [r[0] for r in cur.fetchall()]
            if existentes:
                if not args.recrear:
                    sys.exit(f"Ya existen {len(existentes)} tablas del esquema en '{bd}'. Usa --recrear para borrarlas y volver a crear.")
                for t in tablas_esquema:
                    cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
                for e in enums:
                    cur.execute(f'DROP TYPE IF EXISTS "{e}" CASCADE')
            print("Creando el esquema desde schema.sql (idéntico a backend/app/db/models.py)...")
            cur.execute(sql_esquema)

            total = 0
            for tabla in orden:
                if not (CSV_DIR / f"{tabla}.csv").exists():
                    continue  # tablas técnicas (idempotency_keys, llm_llamadas): sin CSV
                encabezado, n_csv = filas_csv(tabla)
                columnas_bd = [c["nombre"] for c in esquema["tablas"][tabla]["columnas"]]
                desconocidas = [c for c in encabezado if c not in columnas_bd]
                if desconocidas:
                    sys.exit(f"{tabla}.csv tiene columnas que no existen en el esquema: {desconocidas}")
                faltantes = [c["nombre"] for c in esquema["tablas"][tabla]["columnas"] if c["nombre"] not in encabezado and not c["nullable"] and not c["tiene_default"]]
                if faltantes:
                    sys.exit(f"{tabla}.csv no trae columnas obligatorias: {faltantes}")
                if n_csv:
                    cols = ", ".join(f'"{c}"' for c in encabezado)
                    with (CSV_DIR / f"{tabla}.csv").open("rb") as f, cur.copy(f'COPY "{tabla}" ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)') as copia:
                        while bloque := f.read(1 << 20):
                            copia.write(bloque)
                cur.execute(f'SELECT count(*) FROM "{tabla}"')
                n_bd = cur.fetchone()[0]
                if n_bd != n_csv:
                    conn.rollback()
                    sys.exit(f"{tabla}: el CSV tiene {n_csv} filas y la BD {n_bd}")
                total += n_bd
                print(f"  OK {tabla:<26} {n_bd:>6} filas")
        conn.commit()
    print(f"\nCarga completada: {total} filas en {len([t for t in orden if (CSV_DIR / f'{t}.csv').exists()])} tablas; conteos validados contra los CSV.")


if __name__ == "__main__":
    main()
