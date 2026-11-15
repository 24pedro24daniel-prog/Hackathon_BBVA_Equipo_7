"""Hash de las contraseñas de los usuarios de las demos (scrypt de la stdlib, con sal) y su verificación.

Regenerar un hash (lo que va en AUTH_CREDENCIALES de backend/.env y del panel de Render):

    python -m app.core.claves_demo                     # pide la contraseña sin mostrarla
    python -m app.core.claves_demo <contraseña>        # o como argumento (queda en el historial de la terminal)
    python -m app.core.claves_demo --usuario USR-02 --login <login> [<contraseña>]   # entrada completa USR:login:hash

AUTH_CREDENCIALES = entradas "USR-xx:<login>:<hash>" separadas por coma. El USR-xx es el usuario interno de
AUTH_USUARIOS (parametros.env, usuario → empresa). El login va en la credencial y no en parametros.env porque en las
demos el login coincide con la contraseña.

Formato del hash: `scrypt.<n>.<r>.<p>.<sal>.<hash>` (sal y hash en base64url sin relleno). Sin `$` ni `:` para que
docker compose, python-dotenv y el separador de AUTH_CREDENCIALES no lo alteren. scrypt con n=2^14, r=8, p=1
(16 MiB, ~50 ms en un núcleo actual; ~0,5 s en la CPU compartida del plan free de Render).

Solo usa la stdlib: corre también fuera de docker (`cd backend && python -m app.core.claves_demo`).
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import re
import secrets
import sys

ALGORITMO = "scrypt"
N, R, P = 2**14, 8, 1
LARGO_HASH = 32
LARGO_SAL = 16
# Límite de memoria de OpenSSL: 128·r·n = 16 MiB con los parámetros por defecto (el de OpenSSL es 32 MiB justos).
_MAXMEM = 64 * 1024 * 1024
_FORMATO = re.compile(r"^scrypt\.(\d{1,7})\.(\d{1,2})\.(\d{1,2})\.([A-Za-z0-9_-]{16,64})\.([A-Za-z0-9_-]{32,128})$")
_LOGIN = re.compile(r"^[a-z0-9._-]{1,64}$")
_USUARIO = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _desde_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _derivar(contrasena: str, sal: bytes, n: int, r: int, p: int, largo: int) -> bytes:
    return hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=largo, maxmem=_MAXMEM)


def generar_hash(contrasena: str, *, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(LARGO_SAL)
    return ".".join([ALGORITMO, str(N), str(R), str(P), _b64(sal), _b64(_derivar(contrasena, sal, N, R, P, LARGO_HASH))])


def hash_valido(texto: str) -> bool:
    m = _FORMATO.fullmatch(texto or "")
    if not m:
        return False
    n, r, p = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # n potencia de 2 y costo acotado (un hash con n enorme no debe tumbar el servidor)
    return 2**10 <= n <= 2**17 and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4 and 128 * r * n <= _MAXMEM


def verificar(contrasena: str, hash_guardado: str) -> bool:
    """Compara en tiempo constante. Un hash mal formado nunca verifica (y no lanza)."""
    if not hash_valido(hash_guardado):
        return False
    _, n, r, p, sal, esperado = hash_guardado.split(".")
    esperado_b = _desde_b64(esperado)
    calculado = _derivar(contrasena, _desde_b64(sal), int(n), int(r), int(p), len(esperado_b))
    return hmac.compare_digest(calculado, esperado_b)


def normalizar_login(login: str) -> str:
    """Los teclados del celular ponen mayúscula inicial: el login no distingue mayúsculas ni espacios al borde."""
    return (login or "").strip().lower()


def parsear_credenciales(texto: str) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """AUTH_CREDENCIALES → ({login: (usuario_interno, hash)}, problemas). Nunca incluye el hash en los problemas."""
    credenciales: dict[str, tuple[str, str]] = {}
    problemas: list[str] = []
    for i, entrada in enumerate((texto or "").split(","), start=1):
        entrada = entrada.strip()
        if not entrada:
            continue
        partes = entrada.split(":")
        if len(partes) != 3:
            problemas.append(f"entrada {i}: se esperaba USR-xx:login:hash")
            continue
        usuario, login, hash_ = (x.strip() for x in partes)
        login = normalizar_login(login)
        if not _USUARIO.fullmatch(usuario) or not _LOGIN.fullmatch(login):
            problemas.append(f"entrada {i}: usuario interno o login con formato inválido")
        elif not hash_valido(hash_):
            problemas.append(f"entrada {i} ({usuario}): hash con formato inválido (regenéralo con app.core.claves_demo)")
        elif login in credenciales:
            problemas.append(f"entrada {i} ({usuario}): login repetido")
        else:
            credenciales[login] = (usuario, hash_)
    return credenciales, problemas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera el hash scrypt de una contraseña de demo (AUTH_CREDENCIALES).")
    parser.add_argument("contrasena", nargs="?", help="contraseña; si se omite se pide sin mostrarla")
    parser.add_argument("--usuario", help="usuario interno de AUTH_USUARIOS (p. ej. USR-02) para imprimir la entrada")
    parser.add_argument("--login", help="nombre de login (con --usuario)")
    args = parser.parse_args(argv)
    if bool(args.usuario) != bool(args.login):
        parser.error("--usuario y --login van juntos")
    contrasena = args.contrasena if args.contrasena is not None else getpass.getpass("Contraseña: ")
    if not contrasena:
        parser.error("la contraseña no puede estar vacía")
    hash_ = generar_hash(contrasena)
    print(f"{args.usuario}:{normalizar_login(args.login)}:{hash_}" if args.usuario else hash_)
    return 0


if __name__ == "__main__":
    sys.exit(main())
