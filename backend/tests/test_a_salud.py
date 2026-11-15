"""A12 — GET /salud (3 subindicadores, historial en score_salud) y POST /metas (plantillas, sueldo fijo)."""

from datetime import date

import pytest

from app.core.config import settings
from app.db import models as m
from app.services.salud import score

pytestmark = pytest.mark.db
P = settings.API_PREFIX
EMP = f"{P}/empresas/EMP-0001"


def test_score_de_pedro_con_tres_subindicadores(client_db, db):
    r = client_db.get(f"{EMP}/salud")
    assert r.status_code == 200, r.text
    d = r.json()
    subs = {s["id"]: s for s in d["subindicadores"]}
    assert set(subs) == {"constancia_registro", "separacion_personal", "impuestos_al_dia"}
    assert sum(s["peso"] for s in subs.values()) == pytest.approx(1.0)
    # 13 de 13 días anotando (el 14/11 aún no tiene registros); retiros 1 900 vs sueldo esperado 800 (7 y 14/11).
    assert subs["constancia_registro"]["valor"] == 100 and subs["constancia_registro"]["detalle"].startswith("13 de 13")
    assert subs["separacion_personal"]["valor"] == round(40 + 60 * 800 / 1900)
    assert "S/ 1 900" in subs["separacion_personal"]["detalle"]
    assert subs["impuestos_al_dia"]["valor"] == 100
    esperado = round(0.35 * 100 + 0.40 * round(40 + 60 * 800 / 1900) + 0.25 * 100)
    assert d["score"] == esperado and d["score_anterior"] == 64 and d["etapa_actual"] == score.etapa(esperado)
    assert [h["mes"] for h in d["historial"]] == ["2026-08", "2026-09", "2026-10", "2026-11"]
    assert d["historial"][-1]["score"] == esperado
    guardado = db.get(m.ScoreSalud, ("EMP-0001", "2026-11"))
    assert guardado.score == esperado and guardado.version_formula == "score-v1"
    assert {r["tipo"] for r in d["rachas"]} == {"semanas_registrando", "dias_seguidos"}
    assert d["metas_activas"][0]["meta_id"] == "MET-0001" and d["consentimiento_compartir_historial"] is False
    assert d["meta"]["modelo"] == "score-reglas"
    assert subs["separacion_personal"]["nombre"] == "Ponerte un sueldo fijo"
    assert d["etapas"] == ["organizar", "estabilizar", "proteger", "crecer"] and d["fundamento"]
    assert all(s["destacado"] is True for s in d["subindicadores"]) and d["metas_activas"][0]["titulo"]
    textos = [d["fundamento"], *(s["nombre"] + s["detalle"] for s in d["subindicadores"])]
    assert not any("casa" in t.lower() or "%" in t for t in textos)


def test_score_es_idempotente(client_db, db):
    a = client_db.get(f"{EMP}/salud").json()["score"]
    b = client_db.get(f"{EMP}/salud").json()["score"]
    assert a == b and db.query(m.ScoreSalud).filter_by(empresa_id="EMP-0001").count() == 4


def test_sin_sueldo_fijo_baja_la_separacion(db):
    db.query(m.MovimientoProgramado).filter_by(es_sueldo=True).update({"activo": False})
    r = score.calcular_score(db, "EMP-0001", date(2026, 11, 14), persistir=False)
    sep = next(s for s in r["subindicadores"] if s["id"] == "separacion_personal")
    assert sep["valor"] == 30 and "Aún no defines un sueldo fijo" in sep["detalle"] and "casa" not in sep["detalle"]


def test_crear_meta_plantilla(client_db, db):
    r = client_db.post(f"{EMP}/metas", json={"plantilla": "colchon_caja",
                                             "regla": {"tipo": "monto_fijo", "valor": 20, "destino": "colchon"}})  # fmt: skip
    assert r.status_code == 201 and r.json()["estado"] == "activa"
    meta = db.get(m.ReglaMeta, r.json()["meta_id"])
    assert (meta.plantilla, meta.tipo_regla, meta.destino) == ("colchon_caja", "monto_fijo", "colchon")


def test_meta_sueldo_fijo_crea_programado_y_cierra_el_anterior(client_db, db):
    r = client_db.post(f"{EMP}/metas", json={"plantilla": "sueldo_fijo", "regla": {"tipo": "monto_fijo", "valor": 350},
                                             "recordatorio": {"frecuencia": "semanal", "dia": "sábado"}})  # fmt: skip
    assert r.status_code == 201, r.text
    nuevo = db.get(m.MovimientoProgramado, r.json()["programado_id"])
    assert (nuevo.es_sueldo, nuevo.activo, nuevo.monto, nuevo.dia_semana) == (True, True, 350, 6)
    anterior = db.get(m.MovimientoProgramado, "PRG-0002")
    assert anterior.activo is False and anterior.fecha_fin == date(2026, 11, 13)
    assert db.query(m.MovimientoProgramado).filter_by(es_sueldo=True, activo=True).count() == 1


def test_meta_invalida_400(client_db):
    assert client_db.post(f"{EMP}/metas", json={"plantilla": "hacerme_rico"}).status_code == 400
