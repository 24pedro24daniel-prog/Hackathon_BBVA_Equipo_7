"""Alcance por empresa del Bearer (contract.md §12): con el token de una empresa nada puede apuntar a otra (path, query
o body, también por IDs de entidades), y límite de uso de las rutas de IA por sesión y por usuario."""

import hashlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.core import alcance, limites
from app.core.auth import limitar_ia, verificar_acceso
from app.core.config import settings
from app.db import models as m
from app.main import app
from app.schemas.common import CanalNotificacion, TipoAlerta
from tests._e_util import P, auth_demo, bearer, cliente, cliente_sin_bd  # noqa: F401
from tests.conftest import API_KEY_PRUEBAS

pytestmark = pytest.mark.usefixtures("auth_demo")

KEY = {"X-API-Key": API_KEY_PRUEBAS}
LIMA = ZoneInfo("America/Lima")
PUBLICAS = {f"{P}/health", f"{P}/auth/login"}
# Rutas que gastan LLM/VLM/Whisper/R2 (llevan limitar_ia)
RUTAS_IA = {("POST", f"{P}/ingesta/interpretar"), ("POST", f"{P}/ingesta/cuaderno"), ("POST", f"{P}/media/subidas"),
            ("POST", f"{P}/webhooks/whatsapp"), ("POST", f"{P}/empresas/{{empresa_id}}/chat/mensajes"),
            ("POST", f"{P}/empresas/{{empresa_id}}/asistente/mensajes")}  # fmt: skip


def _prohibido(r, campo: str | None = None) -> None:
    assert r.status_code == 403, r.text
    err = r.json()["error"]
    assert err["codigo"] == "EMPRESA_NO_PERMITIDA" and err["request_id"]
    if campo:
        assert err["detalles"] == [{"campo": campo, "problema": "pertenece a otra empresa"}]


def _efectivas(rutas):
    """Rutas con su `dependant` efectivo (FastAPI 0.16x anida los routers incluidos en _IncludedRouter)."""
    for ruta in rutas:
        if hasattr(ruta, "effective_route_contexts"):
            yield from ruta.effective_route_contexts()
        elif isinstance(ruta, APIRoute):
            yield ruta


def _rutas():
    vistas = 0
    for ruta in _efectivas(app.routes):
        if ruta.path not in PUBLICAS and ruta.dependant is not None:
            vistas += 1
            for metodo in sorted(ruta.methods):
                yield metodo, ruta
    assert vistas >= 30, "no se encontraron las rutas de la app"


def _dependencias(dependant) -> set:
    llamadas = set()
    for d in dependant.dependencies:
        llamadas.add(d.call)
        llamadas |= _dependencias(d)
    return llamadas


# ── auditoría estática: ninguna ruta se queda sin el alcance ──


def test_todas_las_rutas_protegidas_pasan_por_el_alcance():
    sin_alcance = [(metodo, r.path) for metodo, r in _rutas()
                   if verificar_acceso not in _dependencias(r.dependant) and r.path != f"{P}/auth/sesion"]  # fmt: skip
    assert not sin_alcance


def test_rutas_de_ia_tienen_limite_de_uso():
    con_limite = {(metodo, r.path) for metodo, r in _rutas() if limitar_ia in _dependencias(r.dependant)}
    assert con_limite == RUTAS_IA


def _campos(schema: dict, componentes: dict, vistos: set) -> set[str]:
    if "$ref" in schema:
        nombre = schema["$ref"].split("/")[-1]
        if nombre in vistos:
            return set()
        vistos.add(nombre)
        return _campos(componentes[nombre], componentes, vistos)
    campos = set(schema.get("properties", {}))
    adicionales = schema.get("additionalProperties")
    for sub in [*schema.get("properties", {}).values(), schema.get("items"), *schema.get("anyOf", []),
                *schema.get("allOf", []), *schema.get("oneOf", []), adicionales]:
        if isinstance(sub, dict) and sub:
            campos |= _campos(sub, componentes, vistos)
    return campos


def test_todo_campo_que_identifica_algo_esta_en_el_alcance():
    """Si alguien agrega un campo *_id a un request, este test obliga a decidir cómo se verifica su empresa."""
    esquema = app.openapi()
    componentes = esquema["components"]["schemas"]
    nombres: set[str] = set()
    for operaciones in esquema["paths"].values():
        for op in operaciones.values():
            nombres |= {p["name"] for p in op.get("parameters", [])}
            for contenido in op.get("requestBody", {}).get("content", {}).values():
                nombres |= _campos(contenido["schema"], componentes, set())
    identificadores = {n for n in nombres if n.endswith(("_id", "_ids")) or n in ("id", "media_url", "telefono_hash")}
    # mensaje_id del webhook es el id del mensaje del proveedor (idempotencia), no una fila; telefono_hash lo resuelve el
    # router del webhook; "id" va con "tipo" (cuentas/anular).
    no_entidades = {"mensaje_id", "telefono_hash", "id"}
    assert identificadores - no_entidades <= alcance.campos_revisados()


# ── path, query y body ──

_RUTAS_EMPRESA = sorted({(metodo, r.path) for metodo, r in _rutas() if "{empresa_id}" in r.path})


@pytest.mark.parametrize(("metodo", "path"), _RUTAS_EMPRESA)
def test_bearer_contra_otra_empresa_en_el_path_403(cliente_sin_bd, metodo, path):
    r = cliente_sin_bd.request(metodo, path.replace("{empresa_id}", "EMP-0002"), headers=bearer("demo1"), json={})
    _prohibido(r, "empresa_id")


def test_bearer_contra_otra_empresa_en_la_query_403(cliente_sin_bd):
    r = cliente_sin_bd.get(f"{P}/empresas/EMP-0001/resumen", params={"empresa_id": "EMP-0002"}, headers=bearer("demo1"))
    _prohibido(r, "empresa_id")


@pytest.mark.parametrize(("path", "body"), [
    ("/ingesta/interpretar", {"empresa_id": "EMP-0002", "canal": "texto", "texto": "vendí dos cervezas"}),
    ("/ingesta/cuaderno", {"empresa_id": "EMP-0002", "media_url": "demo://fotos/cuaderno.jpg"}),
    ("/media/subidas", {"empresa_id": "EMP-0002", "tipo": "audio", "content_type": "audio/ogg", "tamano_bytes": 10}),
    ("/webhooks/whatsapp", {"telefono_hash": "abcdef", "empresa_id": "EMP-0002", "tipo": "texto", "texto": "hola"}),
])  # fmt: skip
def test_bearer_contra_otra_empresa_en_el_body_403(cliente_sin_bd, path, body):
    _prohibido(cliente_sin_bd.post(f"{P}{path}", json=body, headers=bearer("demo1")), "empresa_id")


def test_body_sin_content_type_tambien_se_revisa(cliente_sin_bd):
    r = cliente_sin_bd.post(f"{P}/ingesta/interpretar", headers=bearer("demo1"),
                            content=b'{"empresa_id": "EMP-0002", "canal": "texto", "texto": "x"}')  # fmt: skip
    _prohibido(r, "empresa_id")


def test_media_r2_de_otra_empresa_403(cliente_sin_bd):
    body = {"empresa_id": "EMP-0001", "canal": "voz", "media_url": "r2://empresas/EMP-0002/audios/2026/11/a.ogg"}
    _prohibido(cliente_sin_bd.post(f"{P}/ingesta/interpretar", json=body, headers=bearer("demo1")), "media_url")


def test_alerta_pendiente_de_otra_empresa_403(cliente_sin_bd):
    r = cliente_sin_bd.post(f"{P}/alertas/ALR-PEND.EMP-0002.faltante_caja.-.2026-11-30/accion",
                            json={"accion": "posponer"}, headers=bearer("demo1"))  # fmt: skip
    _prohibido(r, "alerta_id")


# ── IDs de entidades de otra empresa ──


@pytest.fixture
def datos(db):
    """IDs reales del seed: EMP-0001 (Pedro) y EMP-0002 (día 3)."""
    fiado_1 = db.scalars(select(m.CuadernoFiado.fiado_id).where(m.CuadernoFiado.empresa_id == "EMP-0001")).first()
    fiado_2 = db.scalars(select(m.CuadernoFiado.fiado_id).where(m.CuadernoFiado.empresa_id == "EMP-0002")).first()
    deuda_1 = db.scalars(select(m.Deuda.deuda_id).where(m.Deuda.empresa_id == "EMP-0001")).first()
    tx_1 = db.scalars(select(m.Transaccion.transaccion_id).where(m.Transaccion.empresa_id == "EMP-0001")).first()
    producto_2 = db.scalars(select(m.Producto.producto_id).where(m.Producto.empresa_id == "EMP-0002")).first()
    alerta = m.Alerta(alerta_id="ALR-9901", empresa_id="EMP-0001", tipo=TipoAlerta.faltante_caja, prioridad=1,
                      fecha_evento=date(2026, 11, 30), canal=CanalNotificacion.app, creada_en=datetime(2026, 11, 14, tzinfo=LIMA))  # fmt: skip
    db.add(alerta)
    db.flush()
    assert fiado_1 and deuda_1 and tx_1 and producto_2
    return {"fiado_1": fiado_1, "fiado_2": fiado_2, "deuda_1": deuda_1, "tx_1": tx_1, "alerta_1": "ALR-9901",
            "producto_2": producto_2}


@pytest.fixture
def borrador_1(cliente):
    r = cliente.post(f"{P}/ingesta/interpretar", headers=KEY,
                     json={"empresa_id": "EMP-0001", "canal": "texto", "texto": "vendí dos cervezas"})  # fmt: skip
    assert r.status_code == 200, r.text
    return r.json()["borrador_id"]


@pytest.mark.db
def test_confirmar_borrador_de_otra_empresa_403(cliente, borrador_1):
    _prohibido(cliente.post(f"{P}/ingesta/confirmar", json={"borrador_id": borrador_1}, headers=bearer("demo2")),
               "borrador_id")  # fmt: skip
    # Su dueña sí puede
    assert cliente.post(f"{P}/ingesta/confirmar", json={"borrador_id": borrador_1}, headers=bearer("demo1")).status_code == 201


@pytest.mark.db
def test_correcciones_anidadas_con_id_de_otra_empresa_403(cliente, borrador_1, datos):
    item = {"producto_id": datos["producto_2"], "cantidad": 1, "precio_unitario": 1, "subtotal": 1}
    body = {"borrador_id": borrador_1, "correcciones": {"items": [item]}}
    _prohibido(cliente.post(f"{P}/ingesta/confirmar", json=body, headers=bearer("demo1")), "producto_id")
    if datos["fiado_2"]:
        body = {"borrador_id": borrador_1, "correcciones": {"fiado_id": datos["fiado_2"]}}
        _prohibido(cliente.post(f"{P}/ingesta/confirmar", json=body, headers=bearer("demo1")), "fiado_id")


@pytest.mark.db
def test_chat_con_borrador_de_otra_empresa_403(cliente, borrador_1):
    r = cliente.post(f"{P}/empresas/EMP-0002/chat/mensajes", json={"texto": "sí", "borrador_id": borrador_1},
                     headers=bearer("demo2"))  # fmt: skip
    _prohibido(r, "borrador_id")


@pytest.mark.db
def test_conversacion_de_otra_empresa_403_en_asistente_y_chat(cliente):
    cid = cliente.post(f"{P}/empresas/EMP-0001/asistente/mensajes", json={"mensaje": "hola"}, headers=KEY).json()[
        "conversacion_id"]
    r = cliente.post(f"{P}/empresas/EMP-0002/asistente/mensajes", json={"mensaje": "hola", "conversacion_id": cid},
                     headers=bearer("demo2"))  # fmt: skip
    _prohibido(r, "conversacion_id")
    r = cliente.post(f"{P}/empresas/EMP-0002/chat/mensajes", json={"texto": "hola", "conversacion_id": cid},
                     headers=bearer("demo2"))  # fmt: skip
    _prohibido(r, "conversacion_id")
    # La dueña sigue su conversación
    r = cliente.post(f"{P}/empresas/EMP-0001/asistente/mensajes", json={"mensaje": "gracias", "conversacion_id": cid},
                     headers=bearer("demo1"))  # fmt: skip
    assert r.status_code == 200 and r.json()["conversacion_id"] == cid


@pytest.mark.db
def test_recordatorio_de_fiado_de_otra_empresa_403(cliente, datos):
    _prohibido(cliente.post(f"{P}/fiados/{datos['fiado_1']}/recordatorio", headers=bearer("demo2")), "fiado_id")
    assert cliente.post(f"{P}/fiados/{datos['fiado_1']}/recordatorio", headers=bearer("demo1")).status_code == 200


@pytest.mark.db
def test_accion_sobre_alerta_de_otra_empresa_403(cliente, datos):
    url = f"{P}/alertas/{datos['alerta_1']}/accion"
    _prohibido(cliente.post(url, json={"accion": "posponer"}, headers=bearer("demo2")), "alerta_id")
    assert cliente.post(url, json={"accion": "posponer"}, headers=bearer("demo1")).status_code == 200


@pytest.mark.db
@pytest.mark.parametrize(("path", "cuerpo", "campo"), [
    ("cuentas/anular", lambda d: {"tipo": "fiado", "id": d["fiado_1"]}, "id"),
    ("cuentas/anular", lambda d: {"tipo": "pedido", "id": d["deuda_1"]}, "id"),
    ("simular", lambda d: {"acciones": [{"tipo": "cobrar_fiados", "fiado_ids": [d["fiado_1"]]}]}, "fiado_ids"),
    ("simular", lambda d: {"acciones": [{"tipo": "reducir_pedido", "pedido_id": d["deuda_1"], "nuevo_monto": 1}]},
     "pedido_id"),
    ("movimientos", lambda d: {"tipo": "cobro_fiado", "monto": 10, "fiado_id": d["fiado_1"]}, "fiado_id"),
    ("alertas/evaluar", lambda d: {"disparador": "venta", "entidad_id": d["tx_1"]}, "entidad_id"),
])  # fmt: skip
def test_ids_de_otra_empresa_en_el_body_403(cliente, datos, path, cuerpo, campo):
    r = cliente.post(f"{P}/empresas/EMP-0002/{path}", json=cuerpo(datos), headers=bearer("demo2"))
    _prohibido(r, campo)


@pytest.mark.db
def test_webhook_por_telefono_de_otra_empresa_403(cliente, db):
    telefono = db.get(m.Empresa, "EMP-0001").telefono_whatsapp
    body = {"telefono_hash": hashlib.sha256(telefono.encode()).hexdigest()[:12], "tipo": "texto", "texto": "hola"}
    _prohibido(cliente.post(f"{P}/webhooks/whatsapp", json=body, headers=bearer("demo2")), "telefono_hash")
    assert cliente.post(f"{P}/webhooks/whatsapp", json=body, headers=bearer("demo1")).status_code == 200


@pytest.mark.db
def test_x_api_key_puede_tocar_entidades_de_cualquier_empresa(cliente, datos):
    assert cliente.post(f"{P}/fiados/{datos['fiado_1']}/recordatorio", headers=KEY).status_code == 200


@pytest.mark.db
def test_id_inexistente_no_es_403_sino_lo_de_siempre(cliente):
    r = cliente.post(f"{P}/fiados/FIA-9999/recordatorio", headers=bearer("demo1"))
    assert r.status_code == 404 and r.json()["error"]["codigo"] == "NO_ENCONTRADO"


# ── límite de uso de IA ──


@pytest.mark.db
def test_limite_de_uso_por_sesion_con_retry_after(cliente, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_IA_MAX_POR_SESION", 2)
    monkeypatch.setattr(limites, "_reloj", lambda: 5000.0)
    url, cabecera = f"{P}/empresas/EMP-0001/asistente/mensajes", bearer("demo1")
    for _ in range(2):
        assert cliente.post(url, json={"mensaje": "hola"}, headers=cabecera).status_code == 200
    r = cliente.post(url, json={"mensaje": "hola"}, headers=cabecera)
    assert r.status_code == 429 and r.json()["error"]["codigo"] == "DEMASIADOS_INTENTOS"
    assert r.headers["retry-after"] == str(settings.AUTH_IA_VENTANA_S)
    # Otra sesión del mismo usuario tiene su propio cupo; la X-API-Key no tiene límite
    assert cliente.post(url, json={"mensaje": "hola"}, headers=bearer("demo1")).status_code == 200
    assert cliente.post(url, json={"mensaje": "hola"}, headers=KEY).status_code == 200
    # Las rutas sin IA no cuentan
    assert cliente.get(f"{P}/empresas/EMP-0001/resumen", headers=cabecera).status_code == 200


@pytest.mark.db
def test_limite_de_uso_por_usuario_suma_todas_sus_sesiones(cliente, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_IA_MAX_POR_SESION", 10)
    monkeypatch.setattr(settings, "AUTH_IA_MAX_POR_USUARIO", 3)
    url = f"{P}/empresas/EMP-0001/asistente/mensajes"
    sesiones = [bearer("demo1") for _ in range(3)]
    assert [cliente.post(url, json={"mensaje": "hola"}, headers=s).status_code for s in sesiones] == [200] * 3
    assert cliente.post(url, json={"mensaje": "hola"}, headers=bearer("demo1")).status_code == 429
    # Otro usuario no se ve afectado
    assert cliente.post(f"{P}/empresas/EMP-0002/asistente/mensajes", json={"mensaje": "hola"},
                        headers=bearer("demo2")).status_code == 200  # fmt: skip


def test_un_403_no_gasta_cupo(cliente_sin_bd, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_IA_MAX_POR_SESION", 1)
    cabecera = bearer("demo1")
    for _ in range(3):
        _prohibido(cliente_sin_bd.post(f"{P}/empresas/EMP-0002/asistente/mensajes", json={"mensaje": "hola"},
                                       headers=cabecera))  # fmt: skip
    assert limites.LIMITE_IA.espera("s:x", 1, 60) == 0  # nada registrado para nadie
    assert not limites.LIMITE_IA._eventos
