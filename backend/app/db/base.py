from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import JSON, DateTime, MetaData, Numeric
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase

CONVENCION_NOMBRES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)
    # Dinero siempre Numeric(12,2) → Decimal; fecha-hora siempre timestamptz.
    type_annotation_map = {Decimal: Numeric(12, 2), datetime: DateTime(timezone=True), dict: JSON, list: JSON}


def pg_enum(enum_cls: type[PyEnum], nombre: str) -> SAEnum:
    """Enum nativo de PostgreSQL que guarda el valor (no el nombre) del enum de Python."""
    return SAEnum(
        enum_cls,
        name=nombre,
        metadata=Base.metadata,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
