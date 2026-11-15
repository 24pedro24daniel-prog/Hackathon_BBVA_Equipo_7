"""Genera data/schema.sql y data/schema_esquema.json a partir de backend/app/db/models.py.

models.py es la fuente de verdad del esquema. Este script es reproducible y no necesita una base de datos:
usa un motor "mock" de SQLAlchemy para volcar el DDL de PostgreSQL (tipos enum, tablas, CHECK, UNIQUE, FK e índices).

    PYTHONPATH=backend python data/pipeline_python/generar_schema.py            # escribe los dos archivos
    PYTHONPATH=backend python data/pipeline_python/generar_schema.py --check    # falla si están desactualizados

- schema.sql: lo ejecutan los cargadores (load_postgres.py / load_postgres.mjs) sobre una BD vacía.
- schema_esquema.json: descripción del esquema (columnas, tipos, largos, NOT NULL, PK, FK, enums, CHECK, únicos)
  que lee data/audit_quality.mjs para validar los CSV contra el esquema real.

No incluye vistas: el backend calcula todo (saldo, pendiente, atraso, estados) en Python.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint  # noqa: E402
from sqlalchemy import create_mock_engine  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from app.db import models  # noqa: E402
from app.db.base import Base  # noqa: E402

SCHEMA_SQL = RAIZ / "data" / "schema.sql"
SCHEMA_JSON = RAIZ / "data" / "schema_esquema.json"

CABECERA = """-- TuCaserito — esquema de PostgreSQL GENERADO desde backend/app/db/models.py (no editar a mano).
-- Regenerar:  PYTHONPATH=backend python data/pipeline_python/generar_schema.py
-- Incluye las {n} tablas de models.py (25 del modelo de negocio + idempotency_keys y llm_llamadas).
-- No define vistas: el backend calcula saldo, pendiente, atraso y estados en Python (services/finanzas/consultas.py).
-- Los features v_empresas_flags / v_empresas_credit_features del DBML también se calculan en el backend.
"""


def volcar_ddl() -> str:
    sentencias: list[str] = []

    def ejecutor(sql, *args, **kwargs):  # noqa: ANN001
        texto = str(sql.compile(dialect=postgresql.dialect())).strip()
        sentencias.append(texto + ";")

    motor = create_mock_engine("postgresql+psycopg://", ejecutor)
    Base.metadata.create_all(motor, checkfirst=False)
    # SQLAlchemy emite los índices de cada tabla en el orden de un set (puede cambiar entre corridas): se ordena cada
    # tramo consecutivo de CREATE INDEX para que el archivo sea reproducible y --check no falle al azar.
    ordenadas: list[str] = []
    tramo: list[str] = []
    for s in [*sentencias, ""]:
        if s.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX")):
            tramo.append(s)
            continue
        ordenadas += sorted(tramo)
        tramo = []
        if s:
            ordenadas.append(s)
    cuerpo = "\n\n".join(s.replace("\t", "    ") for s in ordenadas)
    return CABECERA.format(n=len(Base.metadata.tables)) + "\n" + cuerpo + "\n"


def tipo_columna(col) -> dict:
    tipo = col.type.compile(dialect=postgresql.dialect())
    info = {"sql": tipo, "base": re.split(r"[ (]", tipo)[0].lower()}
    m = re.search(r"\((\d+)(?:,\s*(\d+))?\)", tipo)
    if m and info["base"] in ("varchar", "character", "char", "numeric"):
        info["largo" if info["base"] != "numeric" else "precision"] = int(m.group(1))
        if m.group(2):
            info["escala"] = int(m.group(2))
    if hasattr(col.type, "enums"):
        info["enum"] = col.type.name
    return info


def describir() -> dict:
    tablas = {}
    for nombre, t in sorted(Base.metadata.tables.items()):
        columnas = []
        for c in t.columns:
            columnas.append({"nombre": c.name, "nullable": bool(c.nullable), "pk": bool(c.primary_key),
                             "tipo": tipo_columna(c), "tiene_default": c.server_default is not None or c.default is not None})
        checks, unicos, fks = [], [], []
        for k in t.constraints:
            if isinstance(k, CheckConstraint):
                checks.append({"nombre": k.name, "sql": str(k.sqltext)})
            elif isinstance(k, UniqueConstraint):
                unicos.append({"nombre": k.name, "columnas": [c.name for c in k.columns]})
            elif isinstance(k, ForeignKeyConstraint):
                e = k.elements[0]
                fks.append({"columna": e.parent.name, "tabla": e.column.table.name, "destino": e.column.name})
            elif isinstance(k, PrimaryKeyConstraint):
                pass
        for c in t.columns:  # unique=True en la columna
            if c.unique and not any(u["columnas"] == [c.name] for u in unicos):
                unicos.append({"nombre": f"uq_{nombre}_{c.name}", "columnas": [c.name]})
        indices_unicos = [{"nombre": i.name, "columnas": [c.name for c in i.columns], "parcial": i.dialect_options["postgresql"]["where"] is not None}
                          for i in sorted(t.indexes, key=lambda x: x.name) if i.unique]
        # t.constraints es un set: se ordena para que el JSON sea reproducible
        checks.sort(key=lambda x: x["nombre"] or "")
        unicos.sort(key=lambda x: (x["nombre"] or "", x["columnas"]))
        fks.sort(key=lambda x: (x["columna"], x["tabla"], x["destino"]))
        tablas[nombre] = {"columnas": columnas, "pk": [c.name for c in t.primary_key.columns], "checks": checks,
                          "unicos": unicos, "indices_unicos": indices_unicos, "fks": fks}
    enums = {}
    for t in Base.metadata.tables.values():
        for c in t.columns:
            if hasattr(c.type, "enums"):
                enums[c.type.name] = list(c.type.enums)
    return {"generado_desde": "backend/app/db/models.py", "tablas_dbml": models.TABLAS_DBML, "enums": dict(sorted(enums.items())),
            "tablas": tablas, "orden_carga": [t.name for t in Base.metadata.sorted_tables]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="solo verifica que los archivos estén al día")
    args = ap.parse_args()
    sql = volcar_ddl()
    js = json.dumps(describir(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        ok = SCHEMA_SQL.exists() and SCHEMA_SQL.read_text(encoding="utf-8") == sql and SCHEMA_JSON.exists() \
            and SCHEMA_JSON.read_text(encoding="utf-8") == js
        print("schema.sql y schema_esquema.json al día con models.py" if ok else "DESACTUALIZADOS: ejecuta generar_schema.py")
        return 0 if ok else 1
    SCHEMA_SQL.write_text(sql, encoding="utf-8", newline="\n")
    SCHEMA_JSON.write_text(js, encoding="utf-8", newline="\n")
    print(f"schema.sql ({sql.count('CREATE TABLE')} tablas, {sql.count('CREATE TYPE')} enums) y schema_esquema.json escritos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
