"""IDs con prefijo legible del contrato: EMP-0001, MOV-000123, BOR-7781…"""

import re

from sqlalchemy import Integer, cast, func, inspect, select
from sqlalchemy.orm import Session

# Ancho por prefijo. Lo que no está aquí usa 4 dígitos.
ANCHOS = {"MOV": 6, "DET": 6, "MSG": 6, "SAL": 6, "PRE": 6}


def formatear_id(prefijo: str, numero: int, ancho: int | None = None) -> str:
    if numero < 0:
        raise ValueError("El número de un ID no puede ser negativo")
    return f"{prefijo}-{numero:0{ancho or ANCHOS.get(prefijo, 4)}d}"


def numero_de_id(id_: str) -> int:
    m = re.fullmatch(r"[A-Z]+-(\d+)", id_)
    if not m:
        raise ValueError(f"ID con formato inválido: {id_!r}")
    return int(m.group(1))


def nuevo_id(db: Session, modelo, prefijo: str, ancho: int | None = None) -> str:
    """Siguiente ID libre para `modelo` (máximo numérico existente con ese prefijo + 1).

    Hace flush antes de consultar para ver lo agregado en la sesión. No es seguro ante dos escrituras
    concurrentes del mismo prefijo; para la demo basta (un solo proceso, una empresa).
    """
    db.flush()
    columna = inspect(modelo).primary_key[0]
    largo = len(prefijo) + 2  # posición del primer dígito en substr (1-indexado)
    consulta = select(func.max(cast(func.substr(columna, largo), Integer))).where(
        columna.op("~")(f"^{re.escape(prefijo)}-[0-9]+$")
    )
    maximo = db.execute(consulta).scalar_one_or_none() or 0
    return formatear_id(prefijo, maximo + 1, ancho)
