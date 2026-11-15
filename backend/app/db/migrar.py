"""Crea en la BD las tablas de models.py que todavía no existen. Nunca borra ni altera tablas existentes.

    python -m app.db.migrar --dry-run                 # BD principal: solo informa qué falta
    python -m app.db.migrar                           # crea lo que falta
    APP_ENV=produccion python -m app.db.migrar ...    # BD de producción (DATABASE_URL_PRODUCCION)

Es la única forma de llevar cambios al esquema de producción (sin Alembic en el hackathon): sirve para tablas
nuevas. Si una tabla existente cambió de columnas, solo se reporta; ese cambio se hace a mano.
"""

import argparse

from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url

from app.core.config import settings
from app.db import models  # noqa: F401  registra las tablas en Base.metadata
from app.db.base import Base
from app.db.session import crear_engine


def diferencias(engine: Engine) -> tuple[list[str], dict[str, dict[str, list[str]]]]:
    """(tablas que faltan, {tabla existente: {"faltan": [...], "sobran": [...]}} con columnas distintas)."""
    insp = inspect(engine)
    existentes = set(insp.get_table_names())
    faltan = [t for t in Base.metadata.sorted_tables if t.name not in existentes]
    distintas = {}
    for tabla in Base.metadata.sorted_tables:
        if tabla.name not in existentes:
            continue
        en_bd = {c["name"] for c in insp.get_columns(tabla.name)}
        en_modelo = {c.name for c in tabla.columns}
        if en_bd != en_modelo:
            distintas[tabla.name] = {"faltan": sorted(en_modelo - en_bd), "sobran": sorted(en_bd - en_modelo)}
    return [t.name for t in faltan], distintas


def migrar(engine: Engine, dry_run: bool = False) -> list[str]:
    faltan, _ = diferencias(engine)
    if faltan and not dry_run:
        tablas = [Base.metadata.tables[n] for n in faltan]
        Base.metadata.create_all(engine, tables=tablas, checkfirst=True)
    return faltan


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea las tablas que faltan (no borra nada).")
    parser.add_argument("--dry-run", action="store_true", help="solo informa, no crea nada")
    args = parser.parse_args()

    url = settings.database_url
    engine = crear_engine(url, connect_args={"connect_timeout": 15})
    destino = make_url(url).render_as_string(hide_password=True)
    faltan, distintas = diferencias(engine)
    print(f"BD: {destino} ({'producción' if settings.es_produccion else settings.APP_ENV})")
    print(f"Tablas en models.py: {len(Base.metadata.tables)} · faltan en la BD: {faltan or 'ninguna'}")
    for tabla, d in distintas.items():
        print(f"  ⚠ {tabla}: columnas que faltan {d['faltan']} · que sobran {d['sobran']} (no se tocan)")
    if args.dry_run or not faltan:
        return
    migrar(engine)
    restantes, _ = diferencias(engine)
    print(f"Creadas: {faltan} · siguen faltando: {restantes or 'ninguna'}")


if __name__ == "__main__":
    main()
