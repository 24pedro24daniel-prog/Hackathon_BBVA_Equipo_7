"""Alcance por empresa de una sesión Bearer (contract.md §12): nada del path, la query ni el body puede apuntar a
otra empresa. Lo usa `auth.verificar_acceso` en TODAS las rutas protegidas (la X-API-Key no pasa por aquí).

Se revisan los campos que identifican algo de una empresa, a cualquier profundidad del body (así entran
`correcciones` de /ingesta/confirmar, `acciones[]` de /simular o `items[]` de /movimientos):

- `empresa_id` → se compara directo.
- IDs de entidades (`borrador_id`, `fiado_id`, `fiado_ids`, `pedido_id`, `deuda_id`, `alerta_id`, …) → se busca la fila
  y se compara su `empresa_id`. Un ID que no existe no se rechaza aquí (la ruta responde su 404/400 de siempre).
- `conversacion_id` → empresas con mensajes en esa conversación.
- `media_url` r2:// → la empresa de la clave (`empresas/{empresa_id}/…`).
- `entidad_id` (alertas/evaluar) → transacción, fiado, deuda, impuesto o meta con ese ID.
- `{"tipo": "fiado"|"pedido"|"impuesto", "id": …}` (cuentas/anular).

Lo que el router resuelve por su cuenta (empresa del `telefono_hash` del webhook) usa `auth.exigir_empresa`.
"""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Validacion

PROFUNDIDAD_MAXIMA = 12
MAX_IDENTIFICADORES = 200


def _modelos() -> dict[str, Any]:
    from app.db import models as m

    return {
        "borrador_id": m.Borrador,
        "fiado_id": m.CuadernoFiado, "fiado_ids": m.CuadernoFiado,
        "deuda_id": m.Deuda, "pedido_id": m.Deuda,
        "impuesto_id": m.Impuesto,
        "alerta_id": m.Alerta,
        "producto_id": m.Producto, "cliente_id": m.Cliente, "proveedor_id": m.Proveedor,
        "movimiento_id": m.Transaccion, "transaccion_id": m.Transaccion,
        "programado_id": m.MovimientoProgramado,
        "meta_id": m.ReglaMeta,
        "ajuste_id": m.ForecastAjuste,
        "id:fiado": m.CuadernoFiado, "id:pedido": m.Deuda, "id:impuesto": m.Impuesto,
    }  # fmt: skip


def _modelos_entidad() -> tuple:
    from app.db import models as m

    return m.Transaccion, m.CuadernoFiado, m.Deuda, m.Impuesto, m.ReglaMeta


ESPECIALES = {"empresa_id", "media_url", "conversacion_id", "entidad_id"}
TIPOS_CUENTA = {"fiado", "pedido", "impuesto"}


def campos_revisados() -> set[str]:
    return ESPECIALES | {c for c in _modelos() if not c.startswith("id:")}


def _recolectar(nodo: Any, campos: set[str], salida: list[tuple[str, str]], profundidad: int = 0) -> None:
    if profundidad > PROFUNDIDAD_MAXIMA:
        raise Validacion("El cuerpo de la solicitud está demasiado anidado.", [{"campo": "payload", "problema": "anidado"}])
    if isinstance(nodo, dict):
        tipo = nodo.get("tipo")
        if isinstance(tipo, str) and tipo in TIPOS_CUENTA and isinstance(nodo.get("id"), str):
            salida.append((f"id:{tipo}", nodo["id"]))
        for clave, valor in nodo.items():
            if clave in campos:
                if isinstance(valor, str):
                    salida.append((clave, valor))
                elif isinstance(valor, list):
                    salida.extend((clave, v) for v in valor if isinstance(v, str))
            if isinstance(valor, (dict, list)):
                _recolectar(valor, campos, salida, profundidad + 1)
    elif isinstance(nodo, list):
        for valor in nodo:
            if isinstance(valor, (dict, list)):
                _recolectar(valor, campos, salida, profundidad + 1)


def _duenas(db: Session, campo: str, valor: str) -> set[str]:
    """Empresas a las que pertenece lo que identifica (campo, valor); vacío si no existe o no es de ninguna."""
    if campo == "empresa_id":
        return {valor}
    if campo == "media_url":
        if valor.startswith("r2://"):
            partes = valor[len("r2://"):].split("/")
            if len(partes) >= 2 and partes[0] == "empresas" and partes[1]:
                return {partes[1]}
        return set()
    if campo == "alerta_id" and valor.startswith("ALR-PEND."):
        partes = valor.split(".")
        return {partes[1]} if len(partes) > 1 and partes[1] else set()
    if campo == "conversacion_id":
        from app.db import models as m

        return set(db.scalars(select(m.Conversacion.empresa_id).where(m.Conversacion.conversacion_id == valor)
                              .distinct()).all())  # fmt: skip
    if campo == "entidad_id":
        return {f.empresa_id for modelo in _modelos_entidad() if (f := db.get(modelo, valor)) is not None}
    modelo = _modelos().get(campo)
    if modelo is None:
        return set()
    fila = db.get(modelo, valor)
    return {fila.empresa_id} if fila is not None else set()


def verificar(db: Session, empresa_sesion: str, path_params: dict[str, Any], query: Iterable[tuple[str, str]],
              cuerpo: Any) -> None:  # fmt: skip
    """403 EMPRESA_NO_PERMITIDA si algo de la solicitud pertenece a otra empresa que la de la sesión."""
    from app.core.auth import EmpresaNoPermitida

    campos = campos_revisados()
    pares: list[tuple[str, str]] = []
    pares += [(k, v) for k, v in path_params.items() if k in campos and isinstance(v, str)]
    pares += [(k, v) for k, v in query if k in campos]
    _recolectar(cuerpo, campos, pares)
    vistos: set[tuple[str, str]] = set()
    for campo, valor in pares:
        if (campo, valor) in vistos or not valor:
            continue
        vistos.add((campo, valor))
        if len(vistos) > MAX_IDENTIFICADORES:
            raise Validacion("La solicitud trae demasiados identificadores.",
                             [{"campo": "payload", "problema": "demasiados IDs"}])  # fmt: skip
        if _duenas(db, campo, valor) - {empresa_sesion}:
            raise EmpresaNoPermitida("id" if campo.startswith("id:") else campo)
