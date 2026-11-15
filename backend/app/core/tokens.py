"""Token de sesión de las demos: JWT compacto HS256 (HMAC-SHA256 con AUTH_SECRET), sin dependencias externas.

Claims: `sub` (login), `emp` (empresa), `iat`, `exp` (segundos Unix, hora real; no la FECHA_DEMO) y `jti` (id de la
sesión, para el límite de uso por sesión). Validación estricta: la cabecera tiene que ser exactamente la que emite este
módulo (no se acepta otro `alg`, ni `none`), la firma se compara en tiempo constante sobre su codificación canónica,
los claims tienen que ser exactamente esos y con su tipo, y `exp - iat` no puede pasar del TTL configurado.
Para el front el token es opaco.
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass

MIN_LARGO_SECRETO = 32
LARGO_MAXIMO = 1024
TOLERANCIA_RELOJ_S = 60
_CABECERA = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode("ascii")
_FORMA = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
_CLAIMS = {"sub", "emp", "iat", "exp", "jti"}


class TokenInvalido(Exception):
    """Firma, forma o claims inválidos (o servidor sin AUTH_SECRET)."""


class TokenVencido(Exception):
    """Firma válida pero `exp` ya pasó."""


@dataclass(frozen=True)
class Claims:
    sub: str
    emp: str
    iat: int
    exp: int
    jti: str


def _ahora() -> int:
    """Hora real (los tests la reemplazan)."""
    return int(time.time())


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _desde_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def secreto_valido(secreto: str) -> bool:
    return len(secreto or "") >= MIN_LARGO_SECRETO


def _firma(secreto: str, mensaje: str) -> str:
    return _b64(hmac.new(secreto.encode("utf-8"), mensaje.encode("ascii"), hashlib.sha256).digest())


def emitir(secreto: str, sub: str, emp: str, ttl_s: int, *, ahora: int | None = None) -> tuple[str, Claims]:
    if not secreto_valido(secreto):
        raise TokenInvalido("AUTH_SECRET vacío o demasiado corto")
    iat = _ahora() if ahora is None else ahora
    claims = Claims(sub=sub, emp=emp, iat=iat, exp=iat + ttl_s, jti=secrets.token_hex(12))
    cuerpo = _b64(json.dumps(claims.__dict__, separators=(",", ":"), ensure_ascii=True).encode("ascii"))
    mensaje = f"{_CABECERA}.{cuerpo}"
    return f"{mensaje}.{_firma(secreto, mensaje)}", claims


def validar(secreto: str, token: str, ttl_max_s: int) -> Claims:
    if not secreto_valido(secreto):
        raise TokenInvalido("AUTH_SECRET vacío o demasiado corto")
    if not token or len(token) > LARGO_MAXIMO or not _FORMA.fullmatch(token):
        raise TokenInvalido("forma")
    cabecera, cuerpo, firma = token.split(".")
    if not hmac.compare_digest(cabecera, _CABECERA):
        raise TokenInvalido("cabecera")
    if not hmac.compare_digest(firma, _firma(secreto, f"{cabecera}.{cuerpo}")):
        raise TokenInvalido("firma")
    try:
        datos = json.loads(_desde_b64(cuerpo))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TokenInvalido("cuerpo") from exc
    if not isinstance(datos, dict) or set(datos) != _CLAIMS:
        raise TokenInvalido("claims")
    enteros = [datos["iat"], datos["exp"]]
    if not all(isinstance(datos[k], str) and datos[k] for k in ("sub", "emp", "jti")) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in enteros):  # fmt: skip
        raise TokenInvalido("tipos")
    claims = Claims(**datos)
    ahora = _ahora()
    if claims.iat > ahora + TOLERANCIA_RELOJ_S or claims.exp <= claims.iat or claims.exp - claims.iat > ttl_max_s:
        raise TokenInvalido("vigencia")
    if claims.exp <= ahora:
        raise TokenVencido()
    return claims
