from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def crear_engine(url: str | None = None, **kwargs) -> Engine:
    opciones = {"pool_pre_ping": True, "connect_args": {"connect_timeout": 5}}
    opciones.update(kwargs)
    return create_engine(url or settings.database_url, **opciones)


engine = crear_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
