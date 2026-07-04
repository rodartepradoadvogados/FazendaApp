"""
Router da Agenda — calcula e retorna eventos do dia ou de um período.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import AgendaManual, Animal, ContaGerencial, Estoque, Parto, Servico
from fazenda.rules.agenda_engine import AgendaEngine, AgendaItem

router = APIRouter(prefix="/agenda", tags=["agenda"])


def _model_to_dict(obj) -> dict:
    return obj.model_dump()


@router.get("/")
def calcular_agenda(
    data: date = date.today(),
    session: Session = Depends(get_session),
) -> dict:
    """
    Calcula a agenda preditiva para a data informada (padrão: hoje).
    Retorna candidatas IATF, checagem de hormônios, BST e todos os eventos.
    """
    animais = [_model_to_dict(a) for a in session.exec(select(Animal).where(Animal.ativo == True)).all()]
    servicos_ult = [
        _model_to_dict(s) for s in session.exec(
            select(Servico).where(Servico.ult_ocorrencia == 1)
        ).all()
    ]
    partos = [_model_to_dict(p) for p in session.exec(select(Parto)).all()]
    estoque = [_model_to_dict(e) for e in session.exec(select(Estoque)).all()]
    contas = [_model_to_dict(c) for c in session.exec(select(ContaGerencial)).all()]
    manuais = [_model_to_dict(m) for m in session.exec(select(AgendaManual)).all()]

    engine = AgendaEngine()
    result = engine.calcular(
        data_referencia=data,
        animais=animais,
        servicos=servicos_ult,
        partos=partos,
        estoque=estoque,
        contas=contas,
        eventos_manuais=manuais,
    )

    return {
        "data_referencia": result.data_referencia.isoformat(),
        "candidatas_iatf": [
            {"numero_matriz": c.numero_matriz, "sit_rep": c.sit_rep, "del_dias": c.del_dias, "motivo": c.motivo}
            for c in result.candidatas_iatf
        ],
        "necessidade_iatf": result.necessidade_iatf.__dict__ if result.necessidade_iatf else None,
        "hormonios_check": [h.__dict__ for h in result.hormonios_check],
        "bst_elegiveis": [b.__dict__ for b in result.bst_elegiveis],
        "bst_excluidos": [b.__dict__ for b in result.bst_excluidos],
        "contas_a_pagar": result.contas_a_pagar,
        "eventos": [
            {
                "data": e.data.isoformat(),
                "categoria": e.categoria,
                "descricao": e.descricao,
                "numero_animal": e.numero_animal,
                "observacao": e.observacao,
                "fonte": e.fonte,
                "cor": e.cor,
            }
            for e in result.eventos
        ],
        "totais": {
            "candidatas_iatf": len(result.candidatas_iatf),
            "bst_elegiveis": len(result.bst_elegiveis),
            "contas_a_pagar": len(result.contas_a_pagar),
            "eventos": len(result.eventos),
        },
    }


@router.post("/manual")
def adicionar_evento_manual(
    data_evento: date,
    descricao: str,
    categoria: str = "Gestão/Financeiro",
    numero_animal: str | None = None,
    observacao: str | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Adiciona um evento manual à agenda (equivalente à aba AGENDA_MANUAL do Excel)."""
    evento = AgendaManual(
        data_evento=data_evento,
        descricao=descricao,
        categoria=categoria,
        numero_animal=numero_animal,
        observacao=observacao,
    )
    session.add(evento)
    session.commit()
    session.refresh(evento)
    return evento.model_dump()
