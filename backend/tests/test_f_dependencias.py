"""Todas las dependencias con versión exacta: directas en requirements.txt, transitivas en constraints.txt.

El entorno instalado (la imagen de docker) debe coincidir con esos dos archivos: un paquete nuevo sin fijar o una versión
distinta rompe la suite. Para regenerar constraints.txt ver tests/congelar_dependencias.py y README > "Dependencias".
"""

from pathlib import Path

import pytest

from tests.congelar_dependencias import BACKEND_DIR, generar_constraints, instaladas, leer_pins

REQUIREMENTS = BACKEND_DIR / "requirements.txt"
CONSTRAINTS = BACKEND_DIR / "constraints.txt"
EN_IMAGEN = Path("/.dockerenv").exists()


def test_requirements_y_constraints_solo_tienen_versiones_exactas():
    directas, transitivas = leer_pins(REQUIREMENTS), leer_pins(CONSTRAINTS)
    sin_fijar = {n: op + v for n, (op, v) in {**directas, **transitivas}.items() if op != "==" or not v}
    assert not sin_fijar, f"Dependencias sin '==': {sin_fijar}"
    repetidas = sorted(set(directas) & set(transitivas))
    assert not repetidas, f"Van solo en requirements.txt (directas), no también en constraints.txt: {repetidas}"


def test_av_fijado_en_version_compatible_con_faster_whisper():
    assert leer_pins(REQUIREMENTS)["av"] == ("==", "18.1.0")


def test_dockerfile_instala_con_constraints():
    dockerfile = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install -r requirements.txt -c constraints.txt" in dockerfile
    assert "backend/constraints.txt" in dockerfile


@pytest.mark.skipif(not EN_IMAGEN, reason="solo en la imagen de docker (un venv local puede tener paquetes extra)")
def test_imagen_instalada_igual_a_los_pines():
    pins = {**leer_pins(REQUIREMENTS), **leer_pins(CONSTRAINTS)}
    instalado = instaladas()
    sin_pin = sorted(f"{nombre}=={v}" for clave, (nombre, v) in instalado.items() if clave not in pins)
    distintas = sorted(f"{clave}: instalado {instalado[clave][1]}, fijado {v}"
                       for clave, (_op, v) in pins.items() if clave in instalado and instalado[clave][1] != v)  # fmt: skip
    assert not sin_pin, f"Instaladas sin versión fijada (regenera constraints.txt): {sin_pin}"
    assert not distintas, f"Versiones distintas a las fijadas: {distintas}"
    assert generar_constraints() == CONSTRAINTS.read_text(encoding="utf-8")
