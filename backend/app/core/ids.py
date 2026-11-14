"""IDs con prefijo: nuevo_id(db, Movimiento, "MOV", ancho=6) -> "MOV-000123"."""
from sqlalchemy import Integer, cast, func, select
from sqlalchemy import inspect as sa_inspect


def formatear_id(prefijo: str, numero: int, ancho: int = 4) -> str:
    return f"{prefijo}-{numero:0{ancho}d}"


def nuevo_id(db, modelo, prefijo: str, ancho: int = 4) -> str:
    """Siguiente ID libre = máximo sufijo numérico existente + 1 (en la misma sesión).

    Suficiente para el hackathon (un proceso). No es seguro bajo escrituras concurrentes.
    """
    pk = sa_inspect(modelo).primary_key[0]
    desde = len(prefijo) + 2  # substr es 1-indexado: salta "PREFIJO-"
    maximo = db.execute(
        select(func.max(cast(func.substr(pk, desde), Integer))).where(pk.like(f"{prefijo}-%"))
    ).scalar()
    return formatear_id(prefijo, (maximo or 0) + 1, ancho)
