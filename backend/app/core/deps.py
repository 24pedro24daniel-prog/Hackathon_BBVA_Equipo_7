"""Dependencias compartidas por los routers.

get_db vive en app.db.session (Dev A); se re-exporta aquí para que los routers no dependan de db/.
"""
from app.db.session import get_db

__all__ = ["get_db"]
