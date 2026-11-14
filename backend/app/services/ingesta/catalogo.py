"""Monto por catálogo y emparejamiento de alias: productos, clientes y proveedores (A3).

`Catalogo` es una foto en memoria del catálogo de una empresa: el extractor por reglas y el LLM trabajan sobre
ella sin tocar la BD, y el set de evaluación (tests/eval_extractor.py) la arma desde el seed sin Postgres.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models as m
from app.schemas.common import TipoMovimiento
from app.services.ingesta.texto import normalizar

_GENERICAS = {"distribuidora", "distribuciones", "comercial", "inversiones", "sra", "sr", "don", "dona", "senora",
              "senor", "vecina", "vecino", "la", "el", "de", "del", "y", "sac", "eirl", "srl"}  # fmt: skip


@dataclass(frozen=True)
class ProductoCat:
    producto_id: str
    nombre: str
    precio: Decimal
    costo: Decimal | None
    categoria_id: str
    alias: tuple[str, ...]


@dataclass(frozen=True)
class ClienteCat:
    cliente_id: str
    nombre: str
    alias: tuple[str, ...]
    pendiente: Decimal = Decimal("0")


@dataclass(frozen=True)
class ProveedorCat:
    proveedor_id: str
    nombre: str
    alias: tuple[str, ...]
    plazo_pago_dias: int = 15


@dataclass(frozen=True)
class Coincidencia:
    producto: ProductoCat
    inicio: int
    fin: int


def _variantes(alias: str) -> set[str]:
    a = normalizar(alias)
    if not a:
        return set()
    salida = {a}
    ultima = a.split(" ")[-1]
    if ultima.endswith("z"):
        salida.add(a[:-1] + "ces")
    elif not ultima.endswith("s"):
        salida.add(a + ("es" if ultima[-1] not in "aeiou" else "s"))
    return salida


def _alias_persona(nombre: str, alias: list | None) -> tuple[str, ...]:
    variantes = set()
    for a in [nombre, *(alias or [])]:
        n = normalizar(a).replace(".", "")
        if n:
            variantes.add(n)
    return tuple(sorted(variantes, key=len, reverse=True))


def _alias_proveedor(nombre: str) -> tuple[str, ...]:
    n = normalizar(nombre)
    variantes = {n}
    variantes |= {t for t in n.split() if len(t) > 3 and t not in _GENERICAS}
    return tuple(sorted(variantes, key=len, reverse=True))


def _buscar_alias(texto_norm: str, alias: tuple[str, ...]) -> tuple[int, int] | None:
    for a in alias:
        if m := re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", texto_norm):
            return m.start(), m.end()
    return None


@dataclass
class Catalogo:
    empresa_id: str
    productos: list[ProductoCat] = field(default_factory=list)
    clientes: list[ClienteCat] = field(default_factory=list)
    proveedores: list[ProveedorCat] = field(default_factory=list)

    def __post_init__(self):
        pares = []
        for p in self.productos:
            for a in {*p.alias, normalizar(p.nombre)}:
                for v in _variantes(a):
                    pares.append((v, p))
        # Primero el alias más largo: "gaseosa grande" gana a "gaseosa"
        self._alias_productos = sorted(pares, key=lambda x: len(x[0]), reverse=True)

    def producto_por_id(self, producto_id: str | None) -> ProductoCat | None:
        return next((p for p in self.productos if p.producto_id == producto_id), None)

    def encontrar_productos(self, texto_norm: str) -> list[Coincidencia]:
        """Productos mencionados en la frase (sin solaparse), en orden de aparición."""
        ocupado = [False] * len(texto_norm)
        encontrados = []
        for alias, prod in self._alias_productos:
            for mt in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", texto_norm):
                if any(ocupado[mt.start():mt.end()]):
                    continue
                for i in range(mt.start(), mt.end()):
                    ocupado[i] = True
                encontrados.append(Coincidencia(prod, mt.start(), mt.end()))
        return sorted(encontrados, key=lambda c: c.inicio)

    def buscar_producto(self, texto: str) -> ProductoCat | None:
        if p := self.producto_por_id(texto):
            return p
        encontrados = self.encontrar_productos(normalizar(texto))
        return encontrados[0].producto if encontrados else None

    def buscar_cliente(self, texto: str | None) -> ClienteCat | None:
        if not texto:
            return None
        t = normalizar(texto).replace(".", "")
        mejor = None
        for c in self.clientes:
            if c.cliente_id == texto:
                return c
            pos = _buscar_alias(t, c.alias)
            if pos and (mejor is None or pos[1] - pos[0] > mejor[0]):
                mejor = (pos[1] - pos[0], c)
        return mejor[1] if mejor else None

    def buscar_proveedor(self, texto: str | None) -> ProveedorCat | None:
        if not texto:
            return None
        t = normalizar(texto)
        for p in self.proveedores:
            if p.proveedor_id == texto or _buscar_alias(t, p.alias):
                return p
        return None

    def para_prompt(self) -> dict:
        """Versión compacta para el prompt del LLM (sin datos sensibles; todo es sintético)."""
        return {
            "productos": [{"producto_id": p.producto_id, "nombre": p.nombre, "alias": list(p.alias)[:5]}
                          for p in self.productos],  # fmt: skip
            "clientes": [c.nombre for c in self.clientes],
            "proveedores": [p.nombre for p in self.proveedores],
        }


def _pendiente_por_cliente(db: Session, empresa_id: str) -> dict[str, Decimal]:
    cobrado = (
        select(m.Transaccion.fiado_id, func.sum(m.Transaccion.monto).label("cobrado"))
        .where(m.Transaccion.tipo == TipoMovimiento.cobro_fiado, ~m.Transaccion.anulada)
        .group_by(m.Transaccion.fiado_id)
        .subquery()
    )
    filas = db.execute(
        select(m.CuadernoFiado.cliente_id, func.sum(m.CuadernoFiado.monto - func.coalesce(cobrado.c.cobrado, 0)))
        .outerjoin(cobrado, cobrado.c.fiado_id == m.CuadernoFiado.fiado_id)
        .where(m.CuadernoFiado.empresa_id == empresa_id, m.CuadernoFiado.fecha_pago_total.is_(None))
        .group_by(m.CuadernoFiado.cliente_id)
    ).all()
    return {cid: Decimal(p) for cid, p in filas}


def cargar(db: Session, empresa_id: str) -> Catalogo:
    productos = db.scalars(select(m.Producto).where(m.Producto.empresa_id == empresa_id, m.Producto.activo)).all()
    clientes = db.scalars(select(m.Cliente).where(m.Cliente.empresa_id == empresa_id)).all()
    proveedores = db.scalars(select(m.Proveedor).where(m.Proveedor.empresa_id == empresa_id)).all()
    pendientes = _pendiente_por_cliente(db, empresa_id)
    return Catalogo(
        empresa_id=empresa_id,
        productos=[ProductoCat(p.producto_id, p.nombre, p.precio_venta, p.costo_unitario, p.categoria_id,
                               tuple(normalizar(a) for a in (p.alias or []))) for p in productos],  # fmt: skip
        clientes=[ClienteCat(c.cliente_id, c.nombre_ficticio, _alias_persona(c.nombre_ficticio, c.alias),
                             pendientes.get(c.cliente_id, Decimal("0"))) for c in clientes],  # fmt: skip
        proveedores=[ProveedorCat(p.proveedor_id, p.nombre_ficticio, _alias_proveedor(p.nombre_ficticio),
                                  p.plazo_pago_dias) for p in proveedores],  # fmt: skip
    )


def desde_seed() -> Catalogo:
    """El catálogo de Pedro tal como lo siembra seed_demo (sin BD), con sus fiados pendientes del 14/11."""
    from app.db import seed_demo as s

    pendientes = {"CLI-0102": Decimal("120.00"), "CLI-0087": Decimal("95.00"), "CLI-0110": Decimal("95.00")}
    return Catalogo(
        empresa_id=s.EMPRESA_ID,
        productos=[ProductoCat(s.PRODUCTO_ID[n], n, Decimal(p), Decimal(c) if c else None, s.CAT[cat],
                               tuple(normalizar(a) for a in alias)) for n, cat, p, c, alias in s.PRODUCTOS],  # fmt: skip
        clientes=[ClienteCat(cid, n, _alias_persona(n, alias), pendientes.get(cid, Decimal("0")))
                  for cid, n, alias, _tel, _perfil in s.CLIENTES],  # fmt: skip
        proveedores=[ProveedorCat(s.PRV_ANDINA, "Distribuidora Andina", _alias_proveedor("Distribuidora Andina"), 15)],
    )


# Atajos con BD (firma del esqueleto de Fase 0)


def buscar_producto(db: Session, empresa_id: str, texto: str) -> ProductoCat | None:
    return cargar(db, empresa_id).buscar_producto(texto)


def buscar_cliente(db: Session, empresa_id: str, texto: str) -> ClienteCat | None:
    return cargar(db, empresa_id).buscar_cliente(texto)


def buscar_proveedor(db: Session, empresa_id: str, texto: str) -> ProveedorCat | None:
    return cargar(db, empresa_id).buscar_proveedor(texto)
