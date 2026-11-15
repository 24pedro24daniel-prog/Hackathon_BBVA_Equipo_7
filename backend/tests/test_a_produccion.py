"""BD de producción (Render): solo con APP_ENV=produccion, y ni reset ni tests pueden tocarla."""

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.core.config import Settings, es_misma_bd
from app.db import reset
from app.db.base import Base
from app.db.migrar import diferencias, migrar

URL_RENDER = "postgresql://usuario:clave@dpg-x-a.oregon-postgres.render.com/hackbbva"


def _settings(**kw) -> Settings:
    base = {"POSTGRES_PASSWORD": "pw", "DATABASE_URL_PRODUCCION": URL_RENDER}
    return Settings(_env_file=None, **{**base, **kw})


def test_local_ignora_la_url_de_produccion():
    s = _settings(APP_ENV="local")
    assert not s.es_produccion
    assert make_url(s.database_url).host == s.POSTGRES_HOST  # localhost, o db dentro de docker compose


def test_produccion_usa_render_con_psycopg_y_ssl():
    url = make_url(_settings(APP_ENV="produccion").database_url)
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "dpg-x-a.oregon-postgres.render.com" and url.database == "hackbbva"
    assert url.query["sslmode"] == "require"


def test_produccion_respeta_sslmode_explicito():
    s = _settings(APP_ENV="production", DATABASE_URL_PRODUCCION=URL_RENDER + "?sslmode=verify-full")
    assert make_url(s.database_url).query["sslmode"] == "verify-full"


def test_produccion_sin_url_falla_claro():
    s = _settings(APP_ENV="produccion", DATABASE_URL_PRODUCCION="")
    with pytest.raises(RuntimeError, match="DATABASE_URL_PRODUCCION"):
        _ = s.database_url


def test_url_produccion_es_secreta():
    s = _settings()
    assert isinstance(s.DATABASE_URL_PRODUCCION, SecretStr)
    assert "clave" not in repr(s)


@pytest.mark.parametrize("kw", [{"APP_ENV": "produccion"},
                                {"TEST_DATABASE_URL": "postgresql+psycopg://otro:x@dpg-x-a.oregon-postgres.render.com/hackbbva"}])  # fmt: skip
def test_tests_nunca_usan_produccion(kw):
    with pytest.raises(RuntimeError, match="producción"):
        _ = _settings(**kw).test_database_url


def test_es_misma_bd_ignora_driver_usuario_y_parametros():
    assert es_misma_bd(URL_RENDER, "postgresql+psycopg://otro:y@dpg-x-a.oregon-postgres.render.com:5432/hackbbva?sslmode=require")
    assert not es_misma_bd(URL_RENDER, "postgresql://u:c@localhost:5433/cajaclara")
    assert not es_misma_bd(URL_RENDER, None)


def test_reset_se_niega_contra_produccion(monkeypatch):
    monkeypatch.setattr(reset, "settings", _settings(APP_ENV="local"))
    engine = create_engine(URL_RENDER.replace("postgresql://", "postgresql+psycopg://"))
    with pytest.raises(reset.ResetProhibido):
        reset.recrear_esquema(engine)


def test_reset_se_niega_con_app_env_produccion(monkeypatch, engine_pruebas):
    monkeypatch.setattr(reset, "settings", _settings(APP_ENV="produccion"))
    with pytest.raises(reset.ResetProhibido):
        reset.recrear_esquema(engine_pruebas)


def test_migrar_solo_crea_lo_que_falta_y_no_borra(engine_pruebas):
    with engine_pruebas.begin() as conn:
        conn.exec_driver_sql("DROP TABLE llm_llamadas")
    assert diferencias(engine_pruebas)[0] == ["llm_llamadas"]
    assert migrar(engine_pruebas, dry_run=True) == ["llm_llamadas"]
    assert diferencias(engine_pruebas)[0] == ["llm_llamadas"]  # dry-run no crea nada

    assert migrar(engine_pruebas) == ["llm_llamadas"]
    faltan, distintas = diferencias(engine_pruebas)
    assert faltan == [] and distintas == {}
    with engine_pruebas.connect() as conn:  # los datos del seed siguen ahí
        assert conn.exec_driver_sql("SELECT count(*) FROM transacciones").scalar() > 0
    assert len(Base.metadata.tables) >= 27
