"""
Router do Manual da Fazenda — rotina automática, resultado, insights e
sugestões (ver fazenda.rules.manual_fazenda), parâmetros de configuração
(Configurações > Parâmetros > Manual da Fazenda) e CRUD de sugestões
customizadas.

Endpoints:
  GET/PUT  /manual-fazenda/parametros
  POST     /manual-fazenda/contrato-anexo   (placeholder — sem storage real ainda)
  GET      /manual-fazenda/sugestoes
  POST     /manual-fazenda/sugestoes
  PUT      /manual-fazenda/sugestoes/{id}
  DELETE   /manual-fazenda/sugestoes/{id}
  GET      /manual-fazenda
  GET      /manual-fazenda/pdf
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import Usuario, exigir_admin, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import ParametroManualFazenda, SugestaoManualFazenda
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.manual_fazenda import parametro_manual, montar_manual
from fazenda.rules.manual_fazenda_pdf import gerar_pdf_manual

router = APIRouter(prefix="/manual-fazenda", tags=["manual-fazenda"])


class ParametroManualFazendaIn(BaseModel):
    email_semanal_ativo: bool
    responsavel_manejo_nome: str | None = None
    responsavel_manejo_empresa: str | None = None
    tem_contrato_manejo: bool = False


@router.get("/parametros")
def obter_parametros_manual(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    return parametro_manual(session, fazenda_id_seguro(fazenda_id)).model_dump()


@router.put("/parametros")
def atualizar_parametros_manual(
    dados: ParametroManualFazendaIn, session: Session = Depends(get_session),
    _: Usuario = Depends(exigir_admin), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    p = parametro_manual(session, fazenda_id_seguro(fazenda_id))
    p.email_semanal_ativo = dados.email_semanal_ativo
    p.responsavel_manejo_nome = dados.responsavel_manejo_nome
    p.responsavel_manejo_empresa = dados.responsavel_manejo_empresa
    p.tem_contrato_manejo = dados.tem_contrato_manejo
    p.atualizado_em = datetime.utcnow()
    session.add(p)
    session.commit()
    session.refresh(p)
    return p.model_dump()


@router.post("/contrato-anexo")
async def anexar_contrato_manejo(
    arquivo: UploadFile, session: Session = Depends(get_session),
    _: Usuario = Depends(exigir_admin), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Placeholder — hoje só guarda o NOME do arquivo (sem armazenar o
    conteúdo). Quando o Supabase Storage entrar, troca para subir o arquivo
    de verdade e gravar a URL/path em vez do nome puro, sem mudar o contrato
    deste endpoint para o front (mesmo campo, mesma resposta)."""
    p = parametro_manual(session, fazenda_id_seguro(fazenda_id))
    p.contrato_manejo_arquivo_nome = arquivo.filename
    p.atualizado_em = datetime.utcnow()
    session.add(p)
    session.commit()
    session.refresh(p)
    return p.model_dump()


class SugestaoManualFazendaIn(BaseModel):
    texto: str
    categoria: str = "geral"
    ativo: bool = True
    ordem: int = 0


@router.get("/sugestoes")
def listar_sugestoes_manual(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(SugestaoManualFazenda).order_by(SugestaoManualFazenda.ordem, SugestaoManualFazenda.id)
    if fazenda_id is not None:
        query = query.where(SugestaoManualFazenda.fazenda_id == fazenda_id)
    return [s.model_dump() for s in session.exec(query).all()]


@router.post("/sugestoes")
def criar_sugestao_manual(
    dados: SugestaoManualFazendaIn, session: Session = Depends(get_session),
    _: Usuario = Depends(exigir_admin), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if not dados.texto.strip():
        raise HTTPException(status_code=400, detail="Informe o texto da sugestão")
    s = SugestaoManualFazenda(**dados.model_dump(), fazenda_id=fazenda_id_seguro(fazenda_id))
    session.add(s)
    session.commit()
    session.refresh(s)
    return s.model_dump()


@router.put("/sugestoes/{sugestao_id}")
def atualizar_sugestao_manual(
    sugestao_id: int, dados: SugestaoManualFazendaIn, session: Session = Depends(get_session),
    _: Usuario = Depends(exigir_admin), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    s = session.get(SugestaoManualFazenda, sugestao_id)
    if not s or (fazenda_id is not None and s.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Sugestão não encontrada")
    if not dados.texto.strip():
        raise HTTPException(status_code=400, detail="Informe o texto da sugestão")
    s.texto, s.categoria, s.ativo, s.ordem = dados.texto, dados.categoria, dados.ativo, dados.ordem
    session.add(s)
    session.commit()
    session.refresh(s)
    return s.model_dump()


@router.delete("/sugestoes/{sugestao_id}")
def excluir_sugestao_manual(
    sugestao_id: int, session: Session = Depends(get_session),
    _: Usuario = Depends(exigir_admin), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    s = session.get(SugestaoManualFazenda, sugestao_id)
    if not s or (fazenda_id is not None and s.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Sugestão não encontrada")
    session.delete(s)
    session.commit()
    return {"ok": True}


@router.get("/")
def obter_manual_fazenda(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    return montar_manual(session, fazenda_id_seguro(fazenda_id))


@router.get("/pdf")
def baixar_pdf_manual_fazenda(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Response:
    manual = montar_manual(session, fazenda_id_seguro(fazenda_id))
    pdf_bytes = gerar_pdf_manual(manual)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": "attachment; filename=manual_da_fazenda.pdf",
    })
