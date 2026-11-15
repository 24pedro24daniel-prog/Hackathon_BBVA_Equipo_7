"""Restaura UNA empresa a su estado de `data/csv` (p. ej. después de una demo en vivo que registró movimientos).

    python -m app.db.restaurar_demo --empresa EMP-0001                      # BD principal (POSTGRES_DB)
    python -m app.db.restaurar_demo --empresa EMP-0001 --bd cajaclara_csv   # otra BD local
    python -m app.db.restaurar_demo --empresa EMP-0001 --dir ../data/csv    # otra carpeta de CSV (por defecto DATA_CSV_DIR)
    python -m app.db.restaurar_demo --empresa EMP-0001 --produccion --confirmar <nombre de la BD de producción>

En UNA transacción: borra SOLO las filas de esa empresa en todas las tablas (hijas primero, en orden inverso de llaves
foráneas; las tablas sin `empresa_id`, como `detalle_transaccion` o `predicciones_fiado`, por la llave a su tabla padre)
y vuelve a insertar SOLO sus filas desde los CSV, convirtiendo tipos igual que `app.db.cargar_csv`. No toca otras
empresas, ni los catálogos globales (`rubros`, `categorias`), ni `llm_llamadas` (las trazas de IA se conservan: por eso
la fila de `empresas` se actualiza en su lugar en vez de borrarse). `idempotency_keys` de la empresa se borran (no hay CSV).

Bloqueado en producción (APP_ENV=produccion o la URL de DATABASE_URL_PRODUCCION) igual que `cargar_csv`: solo con
`--produccion --confirmar <nombre de la BD de producción>`.
"""

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Table, delete, func, insert, or_, select, update
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.sql import Select

from app.core.config import settings
from app.db import models  # noqa: F401  registra las tablas en Base.metadata
from app.db.base import Base
from app.db.cargar_csv import CargaInvalida, _convertir, _insertar, _leer, asegurar_bd
from app.db.reset import ResetProhibido, verificar_no_produccion
from app.db.session import crear_engine

GLOBALES = {"rubros", "categorias"}
CONSERVADAS = {"llm_llamadas"}
_EMPRESA = re.compile(r"^EMP-\d{4,}$")


@dataclass
class Informe:
    empresa_id: str
    directorio: Path
    tablas: dict[str, tuple[int, int]] = field(default_factory=dict)  # tabla → (borradas, insertadas)

    @property
    def borradas(self) -> int:
        return sum(b for b, _ in self.tablas.values())

    @property
    def insertadas(self) -> int:
        return sum(i for _, i in self.tablas.values())


def _alcance() -> dict[str, list[tuple[str, Table]]]:
    """Tablas de una empresa → [] si tienen `empresa_id`, o [(columna, tabla padre)] si llegan por una llave foránea."""
    alcance: dict[str, list[tuple[str, Table]]] = {}
    for tabla in Base.metadata.sorted_tables:
        if tabla.name in GLOBALES or tabla.name in CONSERVADAS or tabla.name == "empresas":
            continue
        if "empresa_id" in tabla.c:
            alcance[tabla.name] = []
            continue
        padres = [(fk.parent.name, fk.column.table) for fk in tabla.foreign_keys if fk.column.table.name in alcance]
        if padres:
            alcance[tabla.name] = padres
    return alcance


def _llave(tabla: Table):
    columnas = list(tabla.primary_key.columns)
    if len(columnas) != 1:
        raise CargaInvalida(f"{tabla.name}: se necesita una llave primaria simple para filtrar a sus hijas")
    return columnas[0]


def _de_la_empresa(tabla: Table, alcance: dict, empresa_id: str):
    """Condición SQL "fila de esta empresa" para `tabla`."""
    if not alcance[tabla.name]:
        return tabla.c.empresa_id == empresa_id
    return or_(*[tabla.c[col].in_(_ids(padre, alcance, empresa_id)) for col, padre in alcance[tabla.name]])


def _ids(tabla: Table, alcance: dict, empresa_id: str) -> Select:
    return select(_llave(tabla)).where(_de_la_empresa(tabla, alcance, empresa_id))


def restaurar(conn: Connection, empresa_id: str, directorio: Path | None = None, *,
              permitir_produccion: bool = False) -> Informe:  # fmt: skip
    """Borra y recarga las filas de `empresa_id` dentro de la transacción de `conn` (no hace commit)."""
    if not _EMPRESA.fullmatch(empresa_id or ""):
        raise ValueError(f"empresa_id no válido: {empresa_id!r} (formato EMP-0001)")
    directorio = Path(directorio) if directorio else settings.data_csv_dir
    if not directorio.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de CSV: {directorio}")
    if not permitir_produccion:
        verificar_no_produccion(conn.engine)

    tablas = {t.name: t for t in Base.metadata.sorted_tables}
    alcance = _alcance()
    empresas = tablas["empresas"]
    columnas_emp, filas_emp = _leer(directorio / "empresas.csv")
    fila_emp = next((f for f in filas_emp if f.get("empresa_id") == empresa_id), None)
    if fila_emp is None:
        raise CargaInvalida(f"{empresa_id} no está en {directorio / 'empresas.csv'}")

    informe = Informe(empresa_id, directorio)
    borradas: dict[str, int] = {}
    for tabla in reversed(Base.metadata.sorted_tables):
        if tabla.name in alcance:
            borradas[tabla.name] = conn.execute(delete(tabla).where(_de_la_empresa(tabla, alcance, empresa_id))).rowcount

    valores = {c: _convertir(fila_emp[c], empresas.c[c].type, c) for c in columnas_emp if c in empresas.c}
    if conn.scalar(select(func.count()).select_from(empresas).where(empresas.c.empresa_id == empresa_id)):
        conn.execute(update(empresas).where(empresas.c.empresa_id == empresa_id)
                     .values({k: v for k, v in valores.items() if k != "empresa_id"}))  # fmt: skip
    else:
        conn.execute(insert(empresas), [valores])
    informe.tablas["empresas"] = (0, 1)

    claves: dict[str, set[str]] = {"empresas": {empresa_id}}
    for tabla in Base.metadata.sorted_tables:
        if tabla.name not in alcance:
            continue
        ruta = directorio / f"{tabla.name}.csv"
        filas: list[dict] = []
        if ruta.exists():
            columnas, todas = _leer(ruta)
            if not alcance[tabla.name]:
                filas = [f for f in todas if f.get("empresa_id") == empresa_id]
            else:
                filas = [f for f in todas
                         if any(f.get(col) and f[col] in claves.get(padre.name, set()) for col, padre in alcance[tabla.name])]  # fmt: skip
            if filas:
                _insertar(conn, tabla, columnas, filas)
            if len(tabla.primary_key.columns) == 1 and (pk := _llave(tabla).name) in columnas:
                claves[tabla.name] = {f[pk] for f in filas}
        en_bd = conn.scalar(select(func.count()).select_from(tabla).where(_de_la_empresa(tabla, alcance, empresa_id)))
        if en_bd != len(filas):
            raise CargaInvalida(f"{tabla.name}: el CSV tiene {len(filas)} filas de {empresa_id} y la BD quedó con {en_bd}")
        informe.tablas[tabla.name] = (borradas.get(tabla.name, 0), len(filas))
    return informe


def url_destino(bd: str | None, produccion: bool, confirmar: str | None) -> str:
    if produccion:
        if not settings.url_produccion:
            raise ResetProhibido("DATABASE_URL_PRODUCCION está vacía en .env.")
        if not confirmar or confirmar != make_url(settings.url_produccion).database:
            raise ResetProhibido("Restaurar en producción exige `--produccion --confirmar <nombre de la BD de producción>`.")
        return settings.url_produccion
    if bd:
        return settings._url(bd)
    return settings.database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restaura una empresa de demo a su estado de data/csv.")
    parser.add_argument("--empresa", required=True, help="empresa a restaurar, p. ej. EMP-0001")
    parser.add_argument("--bd", help="nombre de la BD local; por defecto POSTGRES_DB")
    parser.add_argument("--dir", help="carpeta de los CSV; por defecto DATA_CSV_DIR (../data/csv)")
    parser.add_argument("--produccion", action="store_true", help="PELIGRO: restaurar en la BD de producción")
    parser.add_argument("--confirmar", help="nombre de la BD de producción (con --produccion)")
    args = parser.parse_args(argv)

    try:
        url = url_destino(args.bd, args.produccion, args.confirmar)
        if args.bd and not args.produccion:
            asegurar_bd(args.bd)
        engine = crear_engine(url)
        inicio = time.perf_counter()
        with engine.begin() as conn:
            informe = restaurar(conn, args.empresa, Path(args.dir) if args.dir else None,
                                permitir_produccion=args.produccion)  # fmt: skip
    except ResetProhibido as exc:
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 2
    except (CargaInvalida, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    destino = make_url(url).render_as_string(hide_password=True)
    print(f"{informe.empresa_id} restaurada desde {informe.directorio} en {destino}: {informe.borradas} filas borradas, "
          f"{informe.insertadas} insertadas ({time.perf_counter() - inicio:.1f} s)")  # fmt: skip
    for nombre, (b, i) in informe.tablas.items():
        if b or i:
            print(f"  {nombre}: -{b} +{i}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
