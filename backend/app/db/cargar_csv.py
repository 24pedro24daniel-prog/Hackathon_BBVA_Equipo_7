"""Carga `data/csv` en una BD con el esquema de `models.py` (así local se parece a producción).

    python -m app.db.cargar_csv                  # BD principal (POSTGRES_DB): recrea el esquema y carga los CSV
    python -m app.db.cargar_csv --bd cajaclara_csv   # otra BD local (se crea si no existe)
    python -m app.db.cargar_csv --dir ../data/csv    # otra carpeta de CSV (por defecto DATA_CSV_DIR)

Hace `create_all` del esquema de `models.py` (borra el esquema `public` antes: es una carga desde cero), inserta cada CSV
en orden de llaves foráneas convirtiendo tipos (json, bool, decimal, timestamptz, enums) y valida los conteos.
Lo que no calza NO falla en silencio: se reportan las columnas del CSV que no están en `models.py`, las columnas de
`models.py` que el CSV no trae, los CSV sin tabla y las tablas sin CSV. Un conteo distinto o un valor que no se pueda
convertir termina con error.

Bloqueado en producción igual que `reset` (APP_ENV=produccion o la URL de DATABASE_URL_PRODUCCION): solo se salta con
`--produccion --confirmar hackbbva`.
"""

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as hora
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    Table,
    Time,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.sql.sqltypes import Enum as SAEnum

from app.core.config import es_misma_bd, settings
from app.db import models  # noqa: F401  registra las tablas en Base.metadata
from app.db.base import Base
from app.db.reset import ResetProhibido, recrear_esquema, verificar_no_produccion
from app.db.session import crear_engine

CONFIRMACION_PRODUCCION = "hackbbva"
LOTE = 2000


class CargaInvalida(RuntimeError):
    """Un valor del CSV no se pudo convertir o los conteos no cuadran."""


@dataclass
class Informe:
    directorio: Path
    tablas: dict[str, tuple[int, int]] = field(default_factory=dict)  # tabla → (filas en el CSV, filas en la BD)
    columnas_extra: dict[str, list[str]] = field(default_factory=dict)  # en el CSV pero no en models.py
    columnas_faltantes: dict[str, list[str]] = field(default_factory=dict)  # en models.py pero no en el CSV
    csv_sin_tabla: list[str] = field(default_factory=list)
    tablas_sin_csv: list[str] = field(default_factory=list)

    @property
    def filas(self) -> int:
        return sum(bd for _, bd in self.tablas.values())

    @property
    def hay_diferencias(self) -> bool:
        return bool(self.columnas_extra or self.columnas_faltantes or self.csv_sin_tabla)

    def lineas(self) -> list[str]:
        salida = [f"{t}: {bd} filas" + ("" if csv_ == bd else f" (¡CSV tenía {csv_}!)")
                  for t, (csv_, bd) in self.tablas.items()]  # fmt: skip
        for t, cols in self.columnas_extra.items():
            salida.append(f"AVISO {t}: columnas del CSV que models.py no tiene (se ignoraron): {', '.join(cols)}")
        for t, cols in self.columnas_faltantes.items():
            salida.append(f"AVISO {t}: columnas de models.py que el CSV no trae (quedan con su valor por defecto): "
                          f"{', '.join(cols)}")  # fmt: skip
        for t in self.csv_sin_tabla:
            salida.append(f"AVISO {t}.csv: no hay tabla con ese nombre en models.py (se ignoró)")
        if self.tablas_sin_csv:
            salida.append("Tablas sin CSV (quedan vacías): " + ", ".join(self.tablas_sin_csv))
        return salida


# ── conversión de tipos ─────────────────────────────────────────────────────────────────────────

_VERDADEROS = {"true", "t", "1", "si", "sí", "yes", "y"}
_FALSOS = {"false", "f", "0", "no", "n"}


def _convertir(valor: str, tipo, nombre: str):
    """Texto del CSV → valor Python para la columna. Cadena vacía = NULL."""
    if valor is None or valor == "":
        return None
    try:
        if isinstance(tipo, Boolean):
            v = valor.strip().lower()
            if v in _VERDADEROS:
                return True
            if v in _FALSOS:
                return False
            raise ValueError(f"booleano no reconocido: {valor!r}")
        if isinstance(tipo, (Integer, SmallInteger)):
            return int(Decimal(valor))
        if isinstance(tipo, Numeric):
            return Decimal(valor)
        if isinstance(tipo, DateTime):
            return datetime.fromisoformat(valor.strip())
        if isinstance(tipo, Date):
            return date.fromisoformat(valor.strip()[:10])
        if isinstance(tipo, Time):
            return hora.fromisoformat(valor.strip())
        if isinstance(tipo, JSON):
            return json.loads(valor)
        if isinstance(tipo, SAEnum):
            return valor.strip()
    except (ValueError, InvalidOperation, json.JSONDecodeError) as exc:
        raise CargaInvalida(f"columna '{nombre}': {valor!r} no se pudo convertir ({exc})") from exc
    return valor


def _leer(ruta: Path) -> tuple[list[str], list[dict]]:
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        return list(lector.fieldnames or []), list(lector)


def _insertar(conn, tabla: Table, columnas_csv: list[str], filas: list[dict]) -> None:
    usadas = [c for c in columnas_csv if c in tabla.c]
    registros = []
    for n, fila in enumerate(filas, start=2):  # línea 1 = encabezado
        try:
            registros.append({c: _convertir(fila[c], tabla.c[c].type, c) for c in usadas})
        except CargaInvalida as exc:
            raise CargaInvalida(f"{tabla.name}.csv línea {n}: {exc}") from exc
    for i in range(0, len(registros), LOTE):
        conn.execute(insert(tabla), registros[i:i + LOTE])


def cargar(engine: Engine, directorio: Path | None = None, *, recrear: bool = True,
           permitir_produccion: bool = False) -> Informe:  # fmt: skip
    """Crea el esquema de models.py y carga los CSV. Devuelve el informe (levanta CargaInvalida si algo no cuadra)."""
    directorio = Path(directorio) if directorio else settings.data_csv_dir
    if not directorio.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de CSV: {directorio}")
    if not permitir_produccion:
        verificar_no_produccion(engine)
    if recrear:
        # recrear_esquema vuelve a verificar producción; con el permiso explícito se hace sin esa verificación.
        if permitir_produccion:
            with engine.begin() as conn:
                conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                conn.execute(text("CREATE SCHEMA public"))
            Base.metadata.create_all(engine)
        else:
            recrear_esquema(engine)
    else:
        Base.metadata.create_all(engine)

    informe = Informe(directorio)
    tablas = {t.name: t for t in Base.metadata.sorted_tables}
    archivos = {p.stem: p for p in sorted(directorio.glob("*.csv"))}
    informe.csv_sin_tabla = [n for n in archivos if n not in tablas]
    informe.tablas_sin_csv = [n for n in tablas if n not in archivos]
    with engine.begin() as conn:
        # Las llaves foráneas se validan al final de la transacción: el orden de `sorted_tables` ya las respeta.
        for nombre, tabla in tablas.items():
            ruta = archivos.get(nombre)
            if ruta is None:
                continue
            columnas, filas = _leer(ruta)
            if extra := [c for c in columnas if c not in tabla.c]:
                informe.columnas_extra[nombre] = extra
            if faltan := [c.name for c in tabla.c if c.name not in columnas]:
                informe.columnas_faltantes[nombre] = faltan
            _insertar(conn, tabla, columnas, filas)
            en_bd = conn.scalar(select(func.count()).select_from(tabla))
            informe.tablas[nombre] = (len(filas), en_bd)
            if en_bd != len(filas):
                raise CargaInvalida(f"{nombre}: el CSV tiene {len(filas)} filas y la BD quedó con {en_bd}")
    return informe


# ── BD destino ──────────────────────────────────────────────────────────────────────────────────


def asegurar_bd(nombre: str) -> None:
    """Crea la BD local `nombre` si no existe (conectando a la BD de mantenimiento `postgres`)."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", nombre):
        raise ValueError(f"Nombre de BD no válido: {nombre!r} (minúsculas, números y _)")
    url = settings._url("postgres")
    if settings.es_produccion or es_misma_bd(url, settings.url_produccion):
        raise ResetProhibido("No se crean BD en producción.")
    admin = crear_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            existe = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": nombre})
            if not existe:
                conn.execute(text(f'CREATE DATABASE "{nombre}"'))
    finally:
        admin.dispose()


def url_destino(bd: str | None, produccion: bool, confirmar: str | None) -> str:
    if produccion:
        if confirmar != CONFIRMACION_PRODUCCION:
            raise ResetProhibido("Cargar en producción exige `--produccion --confirmar hackbbva`.")
        if not settings.url_produccion:
            raise ResetProhibido("DATABASE_URL_PRODUCCION está vacía en .env.")
        return settings.url_produccion
    if bd:
        return settings._url(bd)
    return settings.database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga data/csv en una BD con el esquema de models.py.")
    parser.add_argument("--bd", help="nombre de la BD local (se crea si no existe); por defecto POSTGRES_DB")
    parser.add_argument("--dir", help="carpeta de los CSV; por defecto DATA_CSV_DIR (../data/csv)")
    parser.add_argument("--produccion", action="store_true", help="PELIGRO: cargar en la BD de producción")
    parser.add_argument("--confirmar", help="texto de confirmación para --produccion")
    args = parser.parse_args(argv)

    try:
        url = url_destino(args.bd, args.produccion, args.confirmar)
        if args.bd and not args.produccion:
            asegurar_bd(args.bd)
        engine = crear_engine(url)
        inicio = time.perf_counter()
        informe = cargar(engine, Path(args.dir) if args.dir else None, permitir_produccion=args.produccion)
    except ResetProhibido as exc:
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 2
    except (CargaInvalida, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    destino = make_url(url).render_as_string(hide_password=True)
    print(f"CSV de {informe.directorio} cargados en {destino}: {len(informe.tablas)} tablas, {informe.filas} filas "
          f"({time.perf_counter() - inicio:.1f} s)")  # fmt: skip
    for linea in informe.lineas():
        print("  " + linea)
    return 0


if __name__ == "__main__":
    sys.exit(main())
