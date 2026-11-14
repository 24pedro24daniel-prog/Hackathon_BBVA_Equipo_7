"""
CajaClara — Cargador y Verificador en PostgreSQL (Python / psycopg v3 o psycopg2)
Lee DATABASE_URL desde data/.env, ejecuta data/schema.sql y carga todos los CSVs
de data/csv/*.csv en orden topológico.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CSV_DIR = BASE_DIR / "csv"
SCHEMA_PATH = BASE_DIR / "schema.sql"
ENV_PATH = BASE_DIR / ".env"

ORDERED_TABLES = [
    "rubros",
    "empresas",
    "preferencias_alertas",
    "categorias",
    "productos",
    "clientes",
    "proveedores",
    "conversaciones",
    "borradores",
    "movimientos_programados",
    "cuaderno_fiado",
    "deudas",
    "billeteras_digitales",
    "impuestos",
    "transacciones",
    "detalle_transaccion",
    "reglas_meta",
    "forecast_ajustes",
    "alertas",
    "consentimientos",
    "saldo_diario",
    "eventos",
    "predicciones_saldo",
    "predicciones_fiado",
    "score_salud",
]


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def connect_db(db_url: str):
    try:
        import psycopg  # type: ignore

        return psycopg.connect(db_url)
    except ImportError:
        import psycopg2  # type: ignore

        return psycopg2.connect(db_url)


def main() -> None:
    load_env(ENV_PATH)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("No se encontró DATABASE_URL en data/.env ni en el entorno.")

    print("Conectando a PostgreSQL...")
    conn = connect_db(db_url)
    try:
        with conn.cursor() as cur:
            print("Ejecutando schema.sql...")
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

            for table in ORDERED_TABLES:
                csv_file = CSV_DIR / f"{table}.csv"
                with csv_file.open("r", encoding="utf-8", newline="") as f:
                    reader = csv.reader(f)
                    headers = next(reader)
                    rows = [
                        [None if cell == "" else cell for cell in row]
                        for row in reader
                    ]
                if not rows:
                    continue
                placeholders = ", ".join(["%s"] * len(headers))
                cols = ", ".join(headers)
                sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
                cur.executemany(sql, rows)
                print(f"  ✔ {table:<26} -> {len(rows):>5} registros insertados")

        conn.commit()
        print("\n¡Carga completada exitosamente!")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

