"""
Router da Agenda — calcula e retorna eventos do dia ou de um período.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import AgendaManual, Animal, ContaGerencial, Estoque, EventoRealizado, Parto, Servico
from fazenda.rules.agenda_engine import AgendaEngine, AgendaItem

router = APIRouter(prefix="/agenda", tags=["agenda"])


def _model_to_dict(obj) -> dict:
    return obj.model_dump()


@router.get("/")
def calcular_agenda(
    data: date = date.today(),
    dias: int = 10,
    session: Session = Depends(get_session),
) -> dict:
    """
    Calcula a agenda preditiva para a data informada (padrão: hoje).
    `dias` é a janela de contas a pagar/receber (padrão 10, o front pede mais
    quando o usuário amplia o filtro "Até").
    Retorna candidatas IATF, checagem de hormônios, BST e todos os eventos.
    """
    animais = [_model_to_dict(a) for a in session.exec(select(Animal).where(Animal.ativo == True)).all() if not a.eh_semen and a.sexo != "M"]
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
        dias_contas_a_pagar=dias,
    )

    # Remove da lista os eventos já marcados como "realizado" (workflow da agenda).
    realizados = {r.evento_id for r in session.exec(select(EventoRealizado)).all()}
    eventos = [e for e in result.eventos if e.chave not in realizados]

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
                "id": e.chave,
                "data": e.data.isoformat(),
                "categoria": e.categoria,
                "descricao": e.descricao,
                "numero_animal": e.numero_animal,
                "observacao": e.observacao,
                "fonte": e.fonte,
                "cor": e.cor,
                "ref": e.ref,
            }
            for e in eventos
        ],
        "totais": {
            "candidatas_iatf": len(result.candidatas_iatf),
            "bst_elegiveis": len(result.bst_elegiveis),
            "contas_a_pagar": len(result.contas_a_pagar),
            "eventos": len(eventos),
        },
    }


class RealizadoIn(BaseModel):
    evento_id: str


@router.post("/realizados")
def marcar_realizado(dados: RealizadoIn, session: Session = Depends(get_session)) -> dict:
    """Marca um evento como realizado — ele sai da agenda (pendentes e futuros)."""
    existe = session.exec(select(EventoRealizado).where(EventoRealizado.evento_id == dados.evento_id)).first()
    if not existe:
        session.add(EventoRealizado(evento_id=dados.evento_id))
        session.commit()
    return {"marcado": True}


@router.delete("/realizados/{evento_id}")
def desmarcar_realizado(evento_id: str, session: Session = Depends(get_session)) -> dict:
    """Desfaz a marcação de realizado — o evento volta a aparecer na agenda."""
    existe = session.exec(select(EventoRealizado).where(EventoRealizado.evento_id == evento_id)).first()
    if existe:
        session.delete(existe)
        session.commit()
    return {"desmarcado": True}


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
