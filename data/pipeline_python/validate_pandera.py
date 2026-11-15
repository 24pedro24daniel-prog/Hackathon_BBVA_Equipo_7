"""
TuCaserito — Validación complementaria con Pandera (contratos de datos de las tablas principales).

El auditor completo es `data/audit_quality.mjs` (PK/FK/NOT NULL/tipos/enums/CHECK/reglas de negocio contra el esquema real).
Este script añade un segundo chequeo independiente, en Python, de las tablas que consumen los modelos de ML y el backend:
empresas, transacciones, detalle_transaccion, cuaderno_fiado, saldo_diario y score_salud.

    pip install -r data/pipeline_python/requirements.txt
    python data/pipeline_python/validate_pandera.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_DIR = BASE_DIR / "csv"
FECHA_CORTE = "2026-11-14"
HORA_CORTE = "10:00"  # nada del 14/11 es posterior a esta hora (Lima)
CORTE_TS = pd.Timestamp(f"{FECHA_CORTE}T{HORA_CORTE}:00-05:00")

ESQUEMA = json.loads((BASE_DIR / "schema_esquema.json").read_text(encoding="utf-8"))
ENUMS = ESQUEMA["enums"]
CATEGORIAS = ["bebidas", "abarrotes", "lacteos_panaderia", "limpieza_aseo", "snacks_golosinas", "otros_ingresos", "mercaderia", "servicios",
              "alquiler_local", "transporte_flete", "impuestos", "financiamiento", "retiro_personal", "cobro_fiados", "prestamos_recibidos", "otros_gastos"]


def ruc_valido(ruc: str) -> bool:
    if not isinstance(ruc, str) or len(ruc) != 11 or not ruc.isdigit():
        return False
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(p * int(d) for p, d in zip(pesos, ruc[:10]))
    return (11 - suma % 11) % 10 == int(ruc[10])


empresas_schema = DataFrameSchema(
    {
        "empresa_id": Column(str, Check.str_matches(r"^EMP-\d{4}$"), unique=True),
        "rubro_id": Column(str, Check.isin(["RUB-01", "RUB-02", "RUB-03", "RUB-04"])),
        "telefono_whatsapp": Column(str, unique=True),
        "n_trabajadores": Column(int, Check.in_range(1, 5)),
        "tiene_ruc": Column(bool),
        "ruc": Column(str, nullable=True, checks=[Check(lambda s: s.dropna().map(ruc_valido).all(), error="RUC con dígito verificador inválido"), Check(lambda s: s.dropna().is_unique, error="RUC repetido")]),
        "saldo_inicial": Column(float, Check.ge(0)),
        "minimo_operativo": Column(float, Check.ge(0)),
    },
    checks=[Check(lambda df: (df["tiene_ruc"] == df["ruc"].notna()).all(), error="tiene_ruc debe coincidir con la presencia de ruc")],
)

transacciones_schema = DataFrameSchema(
    {
        "transaccion_id": Column(str, Check.str_matches(r"^MOV-\d{6}$"), unique=True),
        "empresa_id": Column(str, Check.str_matches(r"^EMP-\d{4}$")),
        "tipo": Column(str, Check.isin(ENUMS["tipo_movimiento"])),
        "monto": Column(float, Check.gt(0)),
        "moneda": Column(str, Check.equal_to("PEN")),
        "metodo_pago": Column(str, Check.isin(ENUMS["metodo_pago"])),
        "canal": Column(str, Check.isin(ENUMS["canal_registro"])),
        "afecta_caja": Column(bool),
        "anulada": Column(bool),
    },
    checks=[
        Check(lambda df: (df["afecta_caja"] == (df["metodo_pago"] != "credito")).all(), error="afecta_caja debe ser (metodo_pago != 'credito')"),
        Check(lambda df: (df[["fiado_id", "deuda_id", "impuesto_id", "programado_id"]].notna().sum(axis=1) <= 1).all(), error="a lo más una FK satélite"),
        Check(lambda df: (pd.to_datetime(df["fecha_hora"], utc=True) <= CORTE_TS).all(), error="hay transacciones posteriores a la hora de corte"),
        Check(lambda df: (pd.to_datetime(df["creado_en"], utc=True) <= CORTE_TS).all(), error="fuga de datos: creado_en posterior al corte"),
        Check(lambda df: (df.loc[df["metodo_pago"] == "billetera_digital", "billetera_mov_id"].notna()).all(), error="billetera_digital sin billetera_mov_id"),
    ],
)

detalle_schema = DataFrameSchema(
    {
        "cantidad": Column(float, checks=[Check(lambda s: (s == s.round()).all(), error="cantidad fraccionaria"), Check.gt(0)]),
        "precio_unitario": Column(float, Check.ge(0)),
        "subtotal": Column(float, Check.ge(0)),
    },
    checks=[Check(lambda df: ((df["cantidad"] * df["precio_unitario"]).round(2) == df["subtotal"].round(2)).all(), error="subtotal != cantidad x precio")],
)

fiado_schema = DataFrameSchema(
    {
        "fiado_id": Column(str, Check.str_matches(r"^FIA-\d{4}$"), unique=True),
        "monto": Column(float, Check.gt(0)),
        "canal": Column(str, Check.isin(ENUMS["canal_registro"])),
        "fecha_fiado": Column(str, Check(lambda s: (s <= FECHA_CORTE).all())),
        "fecha_pago_total": Column(str, nullable=True, checks=Check(lambda s: (s.dropna() <= FECHA_CORTE).all())),
    }
)

saldo_schema = DataFrameSchema(
    {
        "saldo_cierre": Column(float, Check.ge(0), title="la caja nunca es negativa"),
        "fecha": Column(str, Check(lambda s: (s <= FECHA_CORTE).all())),
    }
)

PESOS = {"constancia_registro": 0.35, "separacion_personal": 0.40, "impuestos_al_dia": 0.25}
score_schema = DataFrameSchema(
    {"score": Column(int, Check.in_range(0, 100)), "version_formula": Column(str, Check.equal_to("score-v1"))},
    checks=[
        Check(lambda df: df["subindicadores"].map(lambda j: sorted(json.loads(j)) == sorted(PESOS)).all(), error="score_salud debe tener los 3 subindicadores del backend"),
        Check(lambda df: ((df["subindicadores"].map(lambda j: sum(PESOS[k] * v for k, v in json.loads(j).items())) - df["score"]).abs() <= 1).all(), error="score != suma ponderada"),
    ],
)


def main() -> None:
    leer = lambda t: pd.read_csv(CSV_DIR / f"{t}.csv", dtype={"ruc": str, "telefono_whatsapp": str})  # noqa: E731
    empresas_schema.validate(leer("empresas"), lazy=True)
    transacciones_schema.validate(leer("transacciones"), lazy=True)
    detalle_schema.validate(leer("detalle_transaccion"), lazy=True)
    fiado_schema.validate(leer("cuaderno_fiado"), lazy=True)
    saldo_schema.validate(leer("saldo_diario"), lazy=True)
    score_schema.validate(leer("score_salud"), lazy=True)
    cats = set(leer("categorias")["nombre"])
    assert cats == set(CATEGORIAS), f"catálogo de categorías distinto del acordado: {cats ^ set(CATEGORIAS)}"
    print("OK: validación Pandera superada (empresas, transacciones, detalle, fiados, saldo_diario, score_salud, categorías).")


if __name__ == "__main__":
    main()
