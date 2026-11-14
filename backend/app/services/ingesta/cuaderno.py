"""Foto del cuaderno de fiados → fiados propuestos (A11).

Orden: (a) modelo de visión vía OpenRouter (`vision.py`) si hay OPENROUTER_API_KEY; (b) si falla (sin key, timeout,
error HTTP, salida inválida o no hay archivo que ver) → fixture precalculado por nombre de foto (`cuaderno_01..03`) para
que la demo nunca se rompa, o lista vacía si la foto es desconocida; en (b) `fallback_usado = true`.
Cada fiado se empareja con los clientes existentes por alias; si no existe se propone como cliente nuevo (se crea
recién al confirmar). Al confirmar, cada fiado se registra como venta a crédito + `cuaderno_fiado` (registrador).
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path, PurePosixPath

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import NoInterpretable
from app.db import models as m
from app.services.ingesta import almacenamiento, llm_client, transcriptor, vision
from app.services.ingesta import catalogo as cat_mod

log = logging.getLogger("cajaclara.cuaderno")

PROMPT_VERSION = vision.PROMPT_VERSION
MODELO = vision.MODELO
PROMPT_VERSION_FIXTURE = "cuaderno-v1"
MODELO_FIXTURE = "fixture-cuaderno"
MODELO_VERSION_FIXTURE = "0.1.0"

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
    lineas_tachadas: int = 0
    fallback_usado: bool = True
    foto: str | None = None
    modelo: str = MODELO_FIXTURE
    modelo_version: str = MODELO_VERSION_FIXTURE
    prompt_version: str = PROMPT_VERSION_FIXTURE
    motivo_fallback: str | None = None


def _nombre_foto(media_url: str) -> str:
    ruta = re.sub(r"^[a-z]+://", "", media_url or "")
    return PurePosixPath(ruta).stem.lower()


def _bytes_imagen(ruta: Path) -> bytes:
    maximo = settings.MEDIA_MAX_IMAGEN_BYTES
    if ruta.stat().st_size > maximo:
        raise almacenamiento.MediaInvalida("La foto pesa demasiado.", f"tamaño excede {maximo} bytes")
    return ruta.read_bytes()


def _cargar_imagen(media_url: str, empresa_id: str) -> bytes | None:
    """Bytes de la foto (r2:// de la empresa, file:// o demo://); None si no hay archivo local que leer."""
    if almacenamiento.es_r2(media_url):
        # Se valida y descarga el objeto (empresa, tipo, tamaño) a un temporal que se borra al terminar.
        try:
            with almacenamiento.archivo_temporal(media_url, empresa_id, "imagen") as ruta:
                return _bytes_imagen(ruta)
        except almacenamiento.ObjetoNoEncontrado:
            raise NoInterpretable("No encontré la foto. ¿Me la mandas otra vez?",
                                  [{"campo": "media_url", "problema": "archivo no encontrado"}]) from None  # fmt: skip
    ruta = transcriptor.resolver_media(media_url)
    return _bytes_imagen(ruta) if ruta is not None else None


def _proponer(fiados: list[dict], cat: cat_mod.Catalogo, db, empresa_id: str) -> list[dict]:
    """Empareja cada cliente con el catálogo (alias) y marca los que ya están en cuaderno_fiado."""
    salida = []
    for f in fiados:
        f = dict(f)
        cli = cat.buscar_cliente(f["cliente"])
        f["cliente_nuevo"] = cli is None
        if cli is not None:
            f["cliente_id"] = cli.cliente_id
            f["cliente"] = cli.nombre
            if db is not None:
                existe = db.scalars(select(m.CuadernoFiado.fiado_id).where(
                    m.CuadernoFiado.empresa_id == empresa_id, m.CuadernoFiado.cliente_id == cli.cliente_id,
                    m.CuadernoFiado.monto == Decimal(str(f["monto"])),
                    m.CuadernoFiado.fecha_fiado == date.fromisoformat(f["fecha"]))).first()  # fmt: skip
                f["posible_duplicado"] = existe is not None
        salida.append(f)
    return salida


def leer_cuaderno(media_url: str, *, empresa_id: str, db=None) -> LecturaCuaderno:
    imagen = _cargar_imagen(media_url, empresa_id)
    foto = _nombre_foto(media_url)
    motivo = "VLM sin configurar"
    if settings.llm_configurado and imagen is None:
        motivo = "no hay archivo de imagen que leer"
    elif settings.llm_configurado:
        tipo = vision.tipo_de_imagen(imagen)
        if tipo is None or tipo not in settings.media_tipos_imagen:
            raise almacenamiento.MediaInvalida("La foto no es de un tipo permitido.", "tipo de imagen no permitido")
        cat = cat_mod.cargar(db, empresa_id) if db is not None else cat_mod.Catalogo(empresa_id)
        try:
            vista = vision.leer(imagen, tipo, clientes=[c.nombre for c in cat.clientes])
            return LecturaCuaderno(
                fiados=_proponer(vista.fiados, cat, db, empresa_id), lineas_no_legibles=vista.lineas_no_legibles,
                lineas_tachadas=vista.lineas_tachadas, fallback_usado=False, foto=foto, modelo=MODELO,
                modelo_version=settings.VLM_MODEL[:30], prompt_version=PROMPT_VERSION)  # fmt: skip
        except (llm_client.LLMNoDisponible, vision.SalidaInvalida) as exc:
            motivo = str(exc)
            log.warning("Cuaderno: uso fixture (%s)", motivo)
    datos = FIXTURES.get(foto)
    if datos is None:
        return LecturaCuaderno(foto=foto, motivo_fallback=motivo)
    cat = cat_mod.cargar(db, empresa_id) if db is not None else cat_mod.Catalogo(empresa_id)
    return LecturaCuaderno(fiados=_proponer(datos["fiados"], cat, db, empresa_id),
                           lineas_no_legibles=datos["lineas_no_legibles"], foto=foto, motivo_fallback=motivo)  # fmt: skip
