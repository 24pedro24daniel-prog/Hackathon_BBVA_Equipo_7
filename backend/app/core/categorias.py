"""Catálogo canónico de categorías (CONVENCIONES: 16 nombres `snake_case`) y su resolución tolerante.

La BD puede traer el catálogo canónico (data/csv, Render) o el viejo del seed ("retiro personal", "pago de
prestamos"…). Los nombres se comparan sin importar mayúsculas, tildes ni la diferencia `_` ≡ espacio, y los nombres
viejos se tratan como alias de los canónicos (en ambos lados: lo que pide el código y lo que hay en la BD).
"""

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Validacion
from app.db import models as m
from app.schemas.common import TipoMovimiento

T = TipoMovimiento

CATEGORIAS_CANONICAS = (
    "bebidas", "abarrotes", "lacteos_panaderia", "limpieza_aseo", "snacks_golosinas", "otros_ingresos", "mercaderia",
    "servicios", "alquiler_local", "transporte_flete", "impuestos", "financiamiento", "retiro_personal", "cobro_fiados",
    "prestamos_recibidos", "otros_gastos",
)  # fmt: skip

# Categoría por defecto de cada tipo de movimiento (cuando no hay producto ni categoría explícita).
CATEGORIA_POR_TIPO = {
    T.venta: "otros_ingresos", T.cobro_fiado: "cobro_fiados", T.prestamo_recibido: "prestamos_recibidos",
    T.otro_ingreso: "otros_ingresos", T.compra: "mercaderia", T.gasto_negocio: "otros_gastos",
    T.retiro_personal: "retiro_personal", T.pago_proveedor: "mercaderia", T.pago_prestamo: "financiamiento",
    T.pago_impuesto: "impuestos",
}  # fmt: skip

# Nombres antiguos (ya normalizados) → canónico (normalizado).
_ALIAS = {
    "cobro de fiados": "cobro fiados", "cobro de fiado": "cobro fiados", "cobro fiado": "cobro fiados",
    "pago de prestamos": "financiamiento", "pago de prestamo": "financiamiento", "pago prestamo": "financiamiento",
    "prestamo recibido": "prestamos recibidos", "alquiler": "alquiler local", "transporte": "transporte flete",
    "flete": "transporte flete", "lacteos": "lacteos panaderia", "panaderia": "lacteos panaderia",
    "limpieza": "limpieza aseo", "golosinas": "snacks golosinas", "snacks": "snacks golosinas",
    "retiros personales": "retiro personal", "impuesto": "impuestos", "gasto": "otros gastos",
}


def normalizar_nombre(texto: str) -> str:
    """minúsculas, sin tildes, `_` ≡ espacio y espacios colapsados."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))
    clave = re.sub(r"[\s_]+", " ", sin_tildes.strip().lower())
    return _ALIAS.get(clave, clave)


def buscar_categoria(db: Session, nombre: str | None) -> m.Categoria | None:
    """La categoría de la BD cuyo `categoria_id` o nombre equivale a `nombre` (None si no hay)."""
    if not nombre or not nombre.strip():
        return None
    filas = db.scalars(select(m.Categoria).order_by(m.Categoria.categoria_id)).all()
    por_id = next((c for c in filas if c.categoria_id.lower() == nombre.strip().lower()), None)
    if por_id is not None:
        return por_id
    clave = normalizar_nombre(nombre)
    return next((c for c in filas if normalizar_nombre(c.nombre) == clave), None)


def categoria_o_400(db: Session, nombre: str | None, campo: str = "categoria") -> m.Categoria:
    cat = buscar_categoria(db, nombre)
    if cat is None:
        raise Validacion(f"No existe la categoría '{nombre}'.", [{"campo": campo, "problema": "no existe"}])
    return cat


def categoria_por_tipo(db: Session, tipo: TipoMovimiento | str) -> m.Categoria:
    """Categoría por defecto del tipo de movimiento; 400 claro si el catálogo de esta BD no la tiene."""
    return categoria_o_400(db, CATEGORIA_POR_TIPO[T(tipo)], "categoria")
