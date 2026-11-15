"""Congela las dependencias TRANSITIVAS del backend en constraints.txt (solo stdlib: corre en un python:slim pelado).

requirements.txt tiene las directas con `==`; constraints.txt, todo lo demás que quedó instalado. El Dockerfile instala
con `pip install -r requirements.txt -c constraints.txt`, así cada build (local y Render) trae exactamente lo mismo.
test_f_dependencias.py verifica que la imagen no tenga nada sin versión fijada.

Regenerar (desde backend/; resuelve de cero las transitivas para las directas actuales, en un contenedor limpio):

    docker run --rm -v "${PWD}:/w" -w /w python:3.12.15-slim sh -c \
        "pip install -q --root-user-action=ignore -r requirements.txt && python tests/congelar_dependencias.py > constraints.txt"

Después: `docker compose build backend` y la suite completa.
"""

import importlib.metadata as md
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
# Vienen con la imagen base (python:3.12.15-slim, versión fijada por la etiqueta), no con requirements.txt
EXCLUIDAS = {"pip", "setuptools", "wheel"}
ENCABEZADO = """\
# Dependencias transitivas congeladas (generado por tests/congelar_dependencias.py; no editar a mano salvo para subir una
# versión puntual). Las directas están en requirements.txt. Uso: pip install -r requirements.txt -c constraints.txt
# Regenerar: ver README > "Dependencias". tests/test_f_dependencias.py falla si la imagen tiene algo sin fijar.
"""
_LINEA = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(==|>=|<=|~=|!=|>|<|===)?\s*([^\s;#]*)")


def normalizar(nombre: str) -> str:
    """PEP 503: 'SQLAlchemy' == 'sqlalchemy', 'pydantic_core' == 'pydantic-core'."""
    return re.sub(r"[-_.]+", "-", nombre).lower()


def leer_pins(ruta: Path) -> dict[str, tuple[str, str]]:
    """{nombre normalizado: (operador, versión)} de un requirements/constraints ('' si la línea no tiene versión)."""
    pins: dict[str, tuple[str, str]] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0].strip()
        if not linea or linea.startswith("-"):
            continue
        m = _LINEA.match(linea)
        if m:
            pins[normalizar(m.group(1))] = (m.group(2) or "", m.group(3) or "")
    return pins


def instaladas() -> dict[str, tuple[str, str]]:
    """{nombre normalizado: (nombre como lo publica el paquete, versión)} del entorno actual, sin pip/setuptools/wheel."""
    res: dict[str, tuple[str, str]] = {}
    for dist in md.distributions():
        nombre = dist.metadata["Name"]
        if nombre and normalizar(nombre) not in EXCLUIDAS:
            res[normalizar(nombre)] = (nombre, dist.version)
    return res


def generar_constraints() -> str:
    directas = leer_pins(BACKEND_DIR / "requirements.txt")
    lineas = [f"{nombre}=={version}" for clave, (nombre, version) in sorted(instaladas().items()) if clave not in directas]
    return ENCABEZADO + "\n".join(lineas) + "\n"


if __name__ == "__main__":
    sys.stdout.write(generar_constraints())
