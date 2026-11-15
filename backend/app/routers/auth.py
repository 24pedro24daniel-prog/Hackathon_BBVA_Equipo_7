"""Login de las demos (contract.md §12): POST /auth/login (público) · GET /auth/sesion (Bearer)."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.auth import (
    JSON_INVALIDO,
    CredencialesInvalidas,
    DemasiadosIntentos,
    NoAutorizado,
    Principal,
    autenticar,
    cuerpo_json,
    emitir_token,
    login_configurado,
    verificar_credenciales,
)
from app.core.config import settings
from app.core.errors import ErrorAPI, ServicioNoDisponible, _detalles_validacion
from app.core.limites import LIMITE_LOGIN, ip_cliente
from app.core.reloj import zona
from app.db import models as m
from app.db.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse, Negocio, SesionResponse
from app.schemas.common import ErrorResponse

log = logging.getLogger("cajaclara.auth")

router = APIRouter(tags=["Autenticación"])

_ERRORES_LOGIN = {
    401: {"model": ErrorResponse, "description": "CREDENCIALES_INVALIDAS (igual si el usuario no existe)"},
    422: {"model": ErrorResponse, "description": "VALIDACION (body del login)"},
    429: {"model": ErrorResponse, "description": "DEMASIADOS_INTENTOS (fallos por IP; header Retry-After)"},
    503: {"model": ErrorResponse, "description": "SERVICIO_NO_DISPONIBLE (login sin configurar en el servidor)"},
}


def _fecha(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, zona())


def _negocio(db: Session, empresa_id: str) -> Negocio:
    empresa = db.get(m.Empresa, empresa_id)
    if empresa is None:
        log.error("La empresa %s de un usuario de demo no está en la BD", empresa_id)
        raise ServicioNoDisponible("La empresa de esta demo no está cargada en el servidor.")
    return Negocio(nombre=empresa.nombre_ficticio)


def _validar(cuerpo: Any) -> LoginRequest:
    """Contrato del login: body inválido → 422 VALIDACION (no el 400 del resto de la API)."""
    if cuerpo is JSON_INVALIDO:
        raise ErrorAPI(422, "VALIDACION", "El JSON enviado no es válido.",
                       [{"campo": "payload", "problema": "el JSON enviado no es válido"}])  # fmt: skip
    try:
        return LoginRequest.model_validate({} if cuerpo is None else cuerpo)
    except ValidationError as exc:
        detalles = _detalles_validacion(RequestValidationError(exc.errors()))
        primero = detalles[0]
        raise ErrorAPI(422, "VALIDACION", f"El campo '{primero['campo']}' no es válido: {primero['problema']}.",
                       detalles) from None  # fmt: skip


@router.post("/auth/login", response_model=LoginResponse, responses=_ERRORES_LOGIN,
             openapi_extra={"requestBody": {"required": True, "content": {"application/json": {
                 "schema": LoginRequest.model_json_schema()}}}})  # fmt: skip
def login(request: Request, response: Response, cuerpo: Any = Depends(cuerpo_json), db: Session = Depends(get_db)):
    ip = ip_cliente(request)
    espera = LIMITE_LOGIN.espera(ip, settings.AUTH_LOGIN_MAX_FALLOS, settings.AUTH_LOGIN_VENTANA_S)
    if espera:
        raise DemasiadosIntentos(f"Demasiados intentos fallidos. Espera {max(1, round(espera / 60))} min y vuelve a "
                                 "intentar.", espera)  # fmt: skip
    if not login_configurado():
        raise ServicioNoDisponible("El inicio de sesión no está configurado en el servidor.")
    datos = _validar(cuerpo)
    usuario = verificar_credenciales(datos.usuario, datos.contrasena)
    if usuario is None:
        LIMITE_LOGIN.registrar(ip, settings.AUTH_LOGIN_VENTANA_S)
        log.warning("Login fallido desde %s", ip)
        raise CredencialesInvalidas()
    negocio = _negocio(db, usuario.empresa_id)
    token, claims = emitir_token(usuario)
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(token=token, expira_en=claims.exp - claims.iat, expira=_fecha(claims.exp),
                         usuario=usuario.login, empresa_id=usuario.empresa_id, negocio=negocio)  # fmt: skip


@router.get("/auth/sesion", response_model=SesionResponse,
            responses={401: {"model": ErrorResponse, "description": "NO_AUTORIZADO / SESION_EXPIRADA"}})  # fmt: skip
def sesion(principal: Principal = Depends(autenticar), db: Session = Depends(get_db)):
    if not principal.es_sesion:
        raise NoAutorizado("Esta ruta es para sesiones: usa 'Authorization: Bearer <token>'.")
    return SesionResponse(usuario=principal.usuario, empresa_id=principal.empresa_id, expira=_fecha(principal.exp),
                          negocio=_negocio(db, principal.empresa_id))  # fmt: skip
