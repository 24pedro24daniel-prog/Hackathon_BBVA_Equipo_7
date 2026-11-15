"""Observabilidad interna: trazas de las llamadas al LLM/VLM (contract.md §11)."""

from datetime import date

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.meta import construir_meta
from app.core.paginacion import Pagina, parametros_pagina
from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.llm_trazas import EstadoLLM, LlamadasResponse, OrigenLLM, ResumenLLMResponse
from app.services.ingesta import llm_consultas, servicio

router = router_protegido("llm")


@router.get("/empresas/{empresa_id}/llm/llamadas", response_model=LlamadasResponse)
def listar_llamadas(
    empresa_id: EmpresaId,
    origen: OrigenLLM | None = None,
    estado: EstadoLLM | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    incluir_contenido: bool = False,
    pagina: Pagina = Depends(parametros_pagina),
    db: Session = Depends(get_db),
):
    servicio.empresa_o_404(db, empresa_id)
    cuerpo = llm_consultas.listar(db, empresa_id, pagina, origen=origen.value if origen else None,
                                  estado=estado.value if estado else None, desde=desde, hasta=hasta,
                                  con_contenido=incluir_contenido)  # fmt: skip
    return {**cuerpo, "meta": construir_meta(None, None)}


@router.get("/empresas/{empresa_id}/llm/resumen", response_model=ResumenLLMResponse)
def resumen_llm(
    empresa_id: EmpresaId,
    desde: date | None = None,
    hasta: date | None = None,
    db: Session = Depends(get_db),
):
    servicio.empresa_o_404(db, empresa_id)
    return {**llm_consultas.resumen(db, empresa_id, desde=desde, hasta=hasta), "meta": construir_meta(None, None)}
