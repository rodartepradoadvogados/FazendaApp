"""
Rotina automática da lista de espera — endpoints.

  GET  /agenda/lista-espera-rotina/status    status da fazenda atual (qualquer usuário da fazenda)
  POST /agenda/lista-espera-rotina/executar  "executar agora" — só o gestor (admin) e só com a rotina ativa
  GET  /painel-cowdata/rotina-lista-espera   resumo global, SOMENTE LEITURA (área "cockpit" do Painel CowData)

Regras em `fazenda.rules.rotina_lista_espera`; especificação em docs/agents/
auditoria-preventivo-agenda/planejamento/11-rotina-lista-de-espera.md.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from fazenda.auth import exigir_admin, exigir_area_painel_cowdata, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session, get_session_manutencao
from fazenda.models import Usuario
from fazenda.rules import rotina_lista_espera as rotina
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/agenda/lista-espera-rotina", tags=["agenda-lista-espera-rotina"])
router_cowdata = APIRouter(prefix="/painel-cowdata/rotina-lista-espera", tags=["painel-cowdata-rotina-lista-espera"])


@router.get("/status")
def status_da_rotina(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    return rotina.status_da_fazenda(session, fazenda_id_seguro(fazenda_id))


@router.post("/executar")
def executar_agora(
    session: Session = Depends(get_session), _: Usuario = Depends(exigir_admin),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is None:
        raise HTTPException(status_code=400, detail="Selecione uma fazenda para executar a rotina.")
    resultado = rotina.executar_fazenda(session, fazenda_id, "manual")
    if resultado["motivo"] == "desligada":
        raise HTTPException(status_code=400, detail="A rotina da lista de espera está desligada nos Parâmetros da fazenda.")
    return {"resultado": resultado, "status": rotina.status_da_fazenda(session, fazenda_id)}


@router_cowdata.get("")
def resumo_para_o_painel_cowdata(
    session: Session = Depends(get_session_manutencao), _: Usuario = Depends(exigir_area_painel_cowdata("cockpit")),
) -> dict:
    return rotina.resumo_global(session)
