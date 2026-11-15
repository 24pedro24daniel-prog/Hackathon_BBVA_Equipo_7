"""Borra y recrea el esquema y siembra la demo de Pedro.

    python -m app.db.reset              # BD principal (POSTGRES_DB), con la demo de Pedro (seed_demo)
    python -m app.db.reset --fuente csv # BD principal cargada desde data/csv (igual que producción; ver cargar_csv)
    python -m app.db.reset --test       # BD de pruebas (POSTGRES_TEST_DB)
    python -m app.db.reset --sin-seed   # solo tablas vacías

Nunca corre contra la BD de producción (APP_ENV=produccion o DATABASE_URL_PRODUCCION): ahí se usa app.db.migrar.
"""

import argparse
import time

from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.core.config import es_misma_bd, settings
from app.db import models  # noqa: F401  registra las tablas en Base.metadata
from app.db.base import Base
from app.db.seed_demo import sembrar
from app.db.session import crear_engine


class ResetProhibido(RuntimeError):
    """Se intentó borrar la BD de producción."""


def verificar_no_produccion(engine: Engine) -> None:
    if settings.es_produccion or es_misma_bd(engine.url.render_as_string(), settings.url_produccion):
        raise ResetProhibido("reset borra todo: nunca contra producción. Usa `python -m app.db.migrar`.")


def recrear_esquema(engine: Engine) -> None:
    """DROP SCHEMA public CASCADE: también limpia tipos enum y tablas que ya no existen en models.py."""
    verificar_no_produccion(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(engine)


def resetear(engine: Engine, con_seed: bool = True, fuente: str = "seed") -> int:
    """`fuente = seed` siembra la demo de Pedro (fixture de los tests); `csv` carga data/csv con el cargador."""
    if fuente == "csv" and con_seed:
        from app.db.cargar_csv import cargar

        return cargar(engine).filas
    recrear_esquema(engine)
    if not con_seed:
        return 0
    with Session(engine) as db:
        filas = sembrar(db)
        db.commit()
    return filas


def main() -> None:
    parser = argparse.ArgumentParser(description="Recrea la BD de TuCaserito y siembra la demo de Pedro.")
    parser.add_argument("--test", action="store_true", help="usar la BD de pruebas (POSTGRES_TEST_DB)")
    parser.add_argument("--sin-seed", action="store_true", help="crear las tablas sin datos")
    parser.add_argument("--fuente", choices=("seed", "csv"), default="seed",
                        help="con qué se llena: seed (demo de Pedro) o csv (data/csv, igual que producción)")
    args = parser.parse_args()

    url = settings.test_database_url if args.test else settings.database_url
    engine = crear_engine(url)
    inicio = time.perf_counter()
    filas = resetear(engine, con_seed=not args.sin_seed, fuente=args.fuente)
    destino = make_url(url).render_as_string(hide_password=True)
    print(f"BD recreada en {destino}: {len(Base.metadata.tables)} tablas, {filas} filas "
          f"({time.perf_counter() - inicio:.1f} s)")  # fmt: skip


if __name__ == "__main__":
    main()
