"""Autenticación (contract.md §0 y §12): `Authorization: Bearer <token>` (login de las demos) o `X-API-Key` (bot/admin).

- Bearer: token firmado de `POST /auth/login` (app/core/tokens.py). Solo sirve para SU empresa: `verificar_acceso`
  revisa el path, la query y el body de cada solicitud (app/core/alcance.py) y responde 403 EMPRESA_NO_PERMITIDA si
  algo apunta a otra empresa. Vencido → 401 SESION_EXPIRADA; inválido/manipulado → 401 NO_AUTORIZADO.
- X-API-Key: acceso total (bot de WhatsApp, administración). Si viene, manda ella (una clave inválida es 401 aunque
  también venga un Bearer).
- Las rutas que gastan LLM/VLM/Whisper/R2 llevan además `limitar_ia` (límite de usos por sesión y por usuario).
"""

import json
import logging
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader, HTTPBearer
from sqlalchemy.orm import Session

from app.core import claves_demo, tokens
from app.core.config import settings
from app.core.errors import ErrorAPI
from app.core.limites import LIMITE_IA
from app.db.session import get_db

log = logging.getLogger("cajaclara.auth")

# Solo para el esquema OpenAPI (botón "Authorize" de /docs); la lógica lee las cabeceras crudas.
_ESQUEMA_BEARER = HTTPBearer(auto_error=False, description="Token de POST /api/v1/auth/login (sesión de una empresa)")
_ESQUEMA_API_KEY = APIKeyHeader(name="X-API-Key", auto_error=False,
                                description="Bot y administración: acceso a todas las empresas")  # fmt: skip


# ── errores ─────────────────────────────────────────────────────────────────────────────────────


class NoAutorizado(ErrorAPI):
    def __init__(self, mensaje: str = "La sesión no es válida. Vuelve a iniciar sesión."):
        super().__init__(401, "NO_AUTORIZADO", mensaje, headers={"WWW-Authenticate": "Bearer"})


class SesionExpirada(ErrorAPI):
    def __init__(self):
        super().__init__(401, "SESION_EXPIRADA", "Tu sesión venció. Vuelve a iniciar sesión.",
                         headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})  # fmt: skip


class CredencialesInvalidas(ErrorAPI):
    def __init__(self):
        super().__init__(401, "CREDENCIALES_INVALIDAS", "Usuario o contraseña incorrectos.")


class EmpresaNoPermitida(ErrorAPI):
    def __init__(self, campo: str):
        super().__init__(403, "EMPRESA_NO_PERMITIDA", "Tu sesión no tiene acceso a esa empresa.",
                         [{"campo": campo, "problema": "pertenece a otra empresa"}])  # fmt: skip


class DemasiadosIntentos(ErrorAPI):
    def __init__(self, mensaje: str, espera_s: int):
        super().__init__(429, "DEMASIADOS_INTENTOS", mensaje, [{"campo": "retry_after", "problema": f"{espera_s} s"}],
                         headers={"Retry-After": str(espera_s)})  # fmt: skip


# ── usuarios de las demos ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UsuarioDemo:
    id: str  # usuario interno de AUTH_USUARIOS (USR-01…)
    login: str
    empresa_id: str
    hash: str


def _mapa_empresas(texto: str) -> dict[str, str]:
    """AUTH_USUARIOS "USR-01:EMP-0001,USR-02:EMP-0003" → {"USR-01": "EMP-0001", …}."""
    pares = {}
    for entrada in (texto or "").split(","):
        uid, _, empresa = entrada.strip().partition(":")
        if uid.strip() and empresa.strip():
            pares[uid.strip()] = empresa.strip()
    return pares


@lru_cache(maxsize=8)
def _usuarios(credenciales: str, mapa: str) -> dict[str, UsuarioDemo]:
    por_login, problemas = claves_demo.parsear_credenciales(credenciales)
    empresas = _mapa_empresas(mapa)
    for problema in problemas:
        log.warning("AUTH_CREDENCIALES: %s", problema)
    usuarios = {}
    for login, (uid, hash_) in por_login.items():
        if uid not in empresas:
            log.warning("AUTH_CREDENCIALES: %s no tiene empresa en AUTH_USUARIOS (se ignora)", uid)
            continue
        usuarios[login] = UsuarioDemo(uid, login, empresas[uid], hash_)
    return usuarios


def usuarios() -> dict[str, UsuarioDemo]:
    return _usuarios(settings.AUTH_CREDENCIALES.get_secret_value(), settings.AUTH_USUARIOS)


def login_configurado() -> bool:
    return tokens.secreto_valido(settings.AUTH_SECRET.get_secret_value()) and bool(usuarios())


@lru_cache(maxsize=1)
def _hash_senuelo() -> str:
    """Hash con los mismos parámetros: un login inexistente cuesta lo mismo que uno con contraseña mala."""
    return claves_demo.generar_hash(secrets.token_urlsafe(16))


def verificar_credenciales(login: str, contrasena: str) -> UsuarioDemo | None:
    usuario = usuarios().get(claves_demo.normalizar_login(login))
    ok = claves_demo.verificar(contrasena, usuario.hash if usuario else _hash_senuelo())
    return usuario if usuario is not None and ok else None


def emitir_token(usuario: UsuarioDemo) -> tuple[str, tokens.Claims]:
    return tokens.emitir(settings.AUTH_SECRET.get_secret_value(), usuario.login, usuario.empresa_id,
                         settings.AUTH_TOKEN_TTL_S)  # fmt: skip


# ── quién llama ─────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Principal:
    tipo: Literal["api_key", "sesion"]
    usuario: str | None = None
    empresa_id: str | None = None
    jti: str | None = None
    exp: int | None = None

    @property
    def es_sesion(self) -> bool:
        return self.tipo == "sesion"


ADMIN = Principal("api_key")


def _desde_api_key(x_api_key: str) -> Principal:
    esperada = settings.API_KEY.get_secret_value()
    if not esperada or not secrets.compare_digest(x_api_key.encode(), esperada.encode()):
        raise NoAutorizado("La API key no es válida.")
    return ADMIN


def _desde_bearer(authorization: str) -> Principal:
    esquema, _, token = authorization.strip().partition(" ")
    if esquema.lower() != "bearer" or not token.strip():
        raise NoAutorizado("El header Authorization debe ser 'Bearer <token>'.")
    try:
        claims = tokens.validar(settings.AUTH_SECRET.get_secret_value(), token.strip(), settings.AUTH_TOKEN_TTL_S)
    except tokens.TokenVencido as exc:
        raise SesionExpirada() from exc
    except tokens.TokenInvalido as exc:
        log.info("Token rechazado: %s", exc)
        raise NoAutorizado() from exc
    usuario = usuarios().get(claims.sub)
    # Si cambió la empresa del usuario o se quitó el usuario, sus tokens dejan de servir.
    if usuario is None or usuario.empresa_id != claims.emp:
        raise NoAutorizado()
    return Principal("sesion", usuario=claims.sub, empresa_id=claims.emp, jti=claims.jti, exp=claims.exp)


async def autenticar(
    request: Request,
    _bearer: Any = Security(_ESQUEMA_BEARER),
    _api_key: Any = Security(_ESQUEMA_API_KEY),
) -> Principal:
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        principal = _desde_api_key(x_api_key)
    elif authorization := request.headers.get("authorization"):
        principal = _desde_bearer(authorization)
    else:
        raise NoAutorizado("Falta el header Authorization (Bearer) o X-API-Key.")
    request.state.principal = principal
    return principal


JSON_INVALIDO = object()


async def cuerpo_json(request: Request) -> Any:
    """Body ya leído por FastAPI, como JSON (None si no hay; JSON_INVALIDO si no se puede leer)."""
    crudo = await request.body()
    if not crudo:
        return None
    try:
        return json.loads(crudo)
    except (ValueError, UnicodeDecodeError):
        return JSON_INVALIDO


def verificar_acceso(
    request: Request,
    principal: Principal = Depends(autenticar),
    cuerpo: Any = Depends(cuerpo_json),
    db: Session = Depends(get_db),
) -> Principal:
    """Dependencia de TODAS las rutas protegidas: autentica y, con Bearer, aplica el alcance por empresa."""
    if principal.es_sesion:
        from app.core import alcance

        alcance.verificar(db, principal.empresa_id, request.path_params, request.query_params.multi_items(),
                          None if cuerpo is JSON_INVALIDO else cuerpo)  # fmt: skip
    return principal


def exigir_empresa(empresa_id: str | None, campo: str, principal: Principal) -> None:
    """Para comprobaciones que resuelve el router (p. ej. la empresa del telefono_hash del webhook)."""
    if principal.es_sesion and empresa_id is not None and empresa_id != principal.empresa_id:
        raise EmpresaNoPermitida(campo)


async def limitar_ia(principal: Principal = Depends(autenticar)) -> None:
    """Rutas que gastan LLM/VLM/Whisper/R2: como mucho AUTH_IA_MAX_POR_SESION usos por sesión y
    AUTH_IA_MAX_POR_USUARIO por usuario (todas sus sesiones) en AUTH_IA_VENTANA_S. La X-API-Key no tiene límite."""
    if not principal.es_sesion:
        return
    espera = LIMITE_IA.consumir([(f"s:{principal.jti}", settings.AUTH_IA_MAX_POR_SESION),
                                 (f"u:{principal.usuario}", settings.AUTH_IA_MAX_POR_USUARIO)],
                                settings.AUTH_IA_VENTANA_S)  # fmt: skip
    if espera:
        log.warning("Límite de uso de IA alcanzado (usuario=%s)", principal.usuario)
        minutos = max(1, round(espera / 60))
        raise DemasiadosIntentos(f"Llegaste al límite de mensajes de la demo. Intenta de nuevo en {minutos} min.", espera)
