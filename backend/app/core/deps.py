"""Dependencias compartidas por los routers.

get_db delega en app.db.session.get_db (lo escribe Dev A). Mientras ese archivo no exista,
cede None: los stubs de la Fase 0 no usan la BD. Cuando A mergee, esto pasa a ser un import directo.
Cualquier OTRO error de import dentro de A (modelos rotos, etc.) sí se propaga.
"""
try:
    from app.db.session import get_db  # type: ignore
except ModuleNotFoundError as e:  # pragma: no cover
    if e.name not in ("app.db", "app.db.session"):
        raise

    def get_db():
        yield None
