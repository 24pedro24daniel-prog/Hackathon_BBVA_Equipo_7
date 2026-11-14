"""Foto del cuaderno de fiados → fiados propuestos (A11, versión simplificada).

No hay modelo de visión/OCR en el MVP: se responde con un fixture precalculado por foto de prueba
(`cuaderno_01..03`) y `meta.fallback_usado = true`. Una foto desconocida devuelve una lista vacía (honesto: no se
inventan fiados). Al confirmar, cada fiado se registra como venta a crédito + `cuaderno_fiado` (registrador).
"""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

PROMPT_VERSION = "cuaderno-v1"
MODELO = "fixture-cuaderno"
MODELO_VERSION = "0.1.0"

# Lo que "se lee" en cada foto de prueba (datos sintéticos). cuaderno_01 = los 3 fiados pendientes de Pedro.
FIXTURES: dict[str, dict] = {
    "cuaderno_01": {
        "fiados": [
            {"cliente": "Sra. Carmen", "detalle": "panes, leche", "monto": 120.00, "fecha": "2026-10-27",
             "confianza": 0.81},
            {"cliente": "Don Luis", "detalle": "arroz, aceite", "monto": 95.00, "fecha": "2026-11-02",
             "confianza": 0.64, "alternativas_monto": [95, 35]},
            {"cliente": "Vecina Rosa", "detalle": "gaseosas", "monto": 95.00, "fecha": "2026-11-05",
             "confianza": 0.88},
        ],
        "lineas_no_legibles": 1,
    },
    "cuaderno_02": {
        "fiados": [
            {"cliente": "Don Luis", "detalle": "fideos, atún", "monto": 18.00, "fecha": "2026-11-10",
             "confianza": 0.86},
            {"cliente": "Sra. Marta", "detalle": "detergente, jabón", "monto": 8.70, "fecha": "2026-11-11",
             "confianza": 0.72},
        ],
        "lineas_no_legibles": 0,
    },
    "cuaderno_03": {
        "fiados": [
            {"cliente": "Vecina Rosa", "detalle": "pan, huevos", "monto": 9.60, "fecha": "2026-11-12",
             "confianza": 0.9},
        ],
        "lineas_no_legibles": 2,
    },
}  # fmt: skip


@dataclass
class LecturaCuaderno:
    fiados: list[dict] = field(default_factory=list)
    lineas_no_legibles: int = 0
    fallback_usado: bool = True
    foto: str | None = None


def _nombre_foto(media_url: str) -> str:
    ruta = re.sub(r"^[a-z]+://", "", media_url or "")
    return PurePosixPath(ruta).stem.lower()


def leer_cuaderno(media_url: str, *, empresa_id: str, db=None) -> LecturaCuaderno:
    foto = _nombre_foto(media_url)
    datos = FIXTURES.get(foto)
    if datos is None:
        return LecturaCuaderno(foto=foto)
    return LecturaCuaderno(fiados=[dict(f) for f in datos["fiados"]], lineas_no_legibles=datos["lineas_no_legibles"],
                           foto=foto)  # fmt: skip
