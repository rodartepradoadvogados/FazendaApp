"""
Router de sanidade — histórico de medicamentos aplicados nos animais e
lançamento de aplicação (um ou mais produtos, por animal ou por lote).
Endpoint: GET /sanidade/aplicacoes, POST /sanidade/aplicacoes
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Estoque, MovimentoEstoque, Sanidade
from fazenda.rules.unidades import pode_dar_baixa_direta, unidades_compativeis

router = APIRouter(prefix="/sanidade", tags=["sanidade"])


@router.get("/aplicacoes")
def listar_aplicacoes(session: Session = Depends(get_session)) -> dict:
    """Aplicações achatadas para o dashboard interativo (filtra no cliente)."""
    registros = []
    for s in session.exec(select(Sanidade)).all():
        d = s.data_aplicacao
        registros.append({
            "numero": s.numero_matriz,
            "raca": s.raca or "(sem raça)",
            "produto": s.produto,
            "categoria": s.categoria or "Outros",
            "dose": s.dose,
            "unidade": s.unidade,
            "atividade": s.atividade,
            "obs": s.obs,
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "mes": f"{d.year}-{d.month:02d}" if d else None,
        })
    return {"aplicacoes": registros, "total": len(registros)}


@router.get("/unidades-compativeis")
def obter_unidades_compativeis(produto: str, session: Session = Depends(get_session)) -> list[str]:
    """Unidades que fazem sentido escolher para este produto, dada sua unidade de estoque."""
    item = session.exec(select(Estoque).where(Estoque.nome == produto)).first()
    return unidades_compativeis(item.unidade if item else None)


class ItemAplicacaoIn(BaseModel):
    produto: str
    via: str | None = None
    quantidade: float
    unidade: str


class AplicacaoIn(BaseModel):
    data_aplicacao: date
    animais: list[str]
    itens: list[ItemAplicacaoIn]
    responsavel: str | None = None
    observacao: str | None = None


@router.post("/aplicacoes")
def registrar_aplicacao(dados: AplicacaoIn, session: Session = Depends(get_session)) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal ou lote")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Adicione ao menos um produto")

    criados = 0
    avisos: list[str] = []
    for item in dados.itens:
        estoque_item = session.exec(select(Estoque).where(Estoque.nome == item.produto)).first()
        compativeis = unidades_compativeis(estoque_item.unidade if estoque_item else None)
        if item.unidade not in compativeis:
            raise HTTPException(
                status_code=400,
                detail=f'Unidade "{item.unidade}" não é compatível com o produto "{item.produto}" (aceitas: {", ".join(compativeis)})',
            )

        for numero in dados.animais:
            session.add(Sanidade(
                numero_matriz=numero,
                data_aplicacao=dados.data_aplicacao,
                produto=item.produto,
                dose=item.quantidade,
                unidade=item.unidade,
                via=item.via,
                responsavel=dados.responsavel,
                obs=dados.observacao,
            ))
            criados += 1

        if estoque_item and pode_dar_baixa_direta(item.unidade, estoque_item.unidade):
            total = item.quantidade * len(dados.animais)
            estoque_item.quantidade = (estoque_item.quantidade or 0) - total
            if estoque_item.estoque_minimo is not None:
                estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
            estoque_item.atualizado_em = datetime.utcnow()
            session.add(estoque_item)
            # Sem este registro, a baixa de sanidade ficava invisível no
            # histórico de /estoque/movimentos e no custo físico do RMCA.
            session.add(MovimentoEstoque(
                nome_item=estoque_item.nome, movimento="Aplicação", quantidade=total,
                unidade=estoque_item.unidade, data_movimento=dados.data_aplicacao,
                observacao=f"Aplicação em {len(dados.animais)} animal(is) — Sanidade",
            ))
        elif estoque_item and estoque_item.unidade and estoque_item.unidade != item.unidade:
            avisos.append(
                f'Baixa de estoque de "{item.produto}" não aplicada — cadastre a equivalência entre '
                f'"{item.unidade}" e "{estoque_item.unidade}" (unidade de estoque do produto).'
            )

    session.commit()
    return {"criados": criados, "avisos": avisos}
