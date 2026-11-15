"""Piezas comunes de los tests del login de las demos (test_e_*.py).

Los tests nunca usan las credenciales reales de backend/.env: `auth_demo` configura un AUTH_SECRET y usuarios de prueba
(mismo login/contraseña que el contrato, otras empresas para que existan en el seed: EMP-0001 y EMP-0002).
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core import auth
from app.core.claves_demo import generar_hash
from app.core.config import settings
from app.core.limites import LIMITE_IA, LIMITE_LOGIN
from app.db.session import get_db
from app.main import app

P = settings.API_PREFIX
SECRETO_PRUEBA = "secreto-de-pruebas-0123456789-abcdefghijklmnopqrstuvwxyz"
# login, contraseña, usuario interno, empresa (EMP-0999 no existe en el seed)
USUARIOS_PRUEBA = [("demo1", "demo1", "USR-01", "EMP-0001"), ("demo2", "demo2", "USR-02", "EMP-0002"),
                   ("demo3", "demo3", "USR-03", "EMP-0999")]  # fmt: skip
CREDENCIALES_PRUEBA = ",".join(f"{uid}:{login}:{generar_hash(clave)}" for login, clave, uid, _ in USUARIOS_PRUEBA)
MAPA_PRUEBA = ",".join(f"{uid}:{emp}" for _, _, uid, emp in USUARIOS_PRUEBA)


@pytest.fixture
def auth_demo(monkeypatch):
    """AUTH_* de prueba y límites en cero (los contadores en memoria no se arrastran entre tests)."""
    monkeypatch.setattr(settings, "AUTH_SECRET", SecretStr(SECRETO_PRUEBA))
    monkeypatch.setattr(settings, "AUTH_CREDENCIALES", SecretStr(CREDENCIALES_PRUEBA))
    monkeypatch.setattr(settings, "AUTH_USUARIOS", MAPA_PRUEBA)
    monkeypatch.setattr(settings, "AUTH_TOKEN_TTL_S", 28800)
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FALLOS", 10)
    monkeypatch.setattr(settings, "AUTH_LOGIN_VENTANA_S", 600)
    monkeypatch.setattr(settings, "AUTH_IA_MAX_POR_SESION", 60)
    monkeypatch.setattr(settings, "AUTH_IA_MAX_POR_USUARIO", 200)
    monkeypatch.setattr(settings, "AUTH_IA_VENTANA_S", 3600)
    monkeypatch.setattr(settings, "IP_CLIENTE_CABECERA", "")
    LIMITE_LOGIN.reiniciar()
    LIMITE_IA.reiniciar()
    yield
    LIMITE_LOGIN.reiniciar()
    LIMITE_IA.reiniciar()


def token_de(login: str) -> str:
    return auth.emitir_token(auth.usuarios()[login])[0]


def bearer(login: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_de(login)}"}


def _cliente(get_db_falso) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = get_db_falso
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def cliente(db) -> Iterator[TestClient]:
    """Sin credenciales por defecto; get_db = la sesión transaccional `db` (se revierte al final)."""
    yield from _cliente(lambda: db)


@pytest.fixture
def cliente_sin_bd(_sesiones_sin_conexion) -> Iterator[TestClient]:
    """Sin credenciales; la BD de pruebas solo se toca si la ruta llega a usarla."""

    def _get_db():
        sesion = _sesiones_sin_conexion()
        try:
            yield sesion
        finally:
            sesion.close()

    yield from _cliente(_get_db)
