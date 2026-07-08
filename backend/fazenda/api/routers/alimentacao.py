"""
Router de alimentação — plano de dieta por lote, consumo diário estimado,
necessidade mensal (com conversão para sacos) e a baixa automática de
estoque (opção A: o sistema recalcula quantos dias se passaram desde a
última baixa e desconta o consumo acumulado de uma vez, sempre que a tela
é aberta — sem botão manual nem cron real).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import AlimentacaoEstado, Animal, Dieta, Estoque, MovimentoEstoque
from fazenda.rules.alimentacao import calcular_consumo, calcular_necessidade_mensal

router = APIRouter(prefix="/alimentacao", tags=["alimentacao"])


def _dietas_e_animais(session: Session) -> tuple[list[dict], list[dict]]:
    dietas = [d.model_dump() for d in session.exec(select(Dieta)).all()]
    animais = [
        a.model_dump() for a in session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
        if not a.eh_semen and a.sexo != "M"
    ]
    return dietas, animais


def _dar_baixa_automatica(session: Session) -> dict:
    """
    Baixa automática de estoque por dias decorridos (opção A). Usa uma trava
    otimista (compare-and-swap) na linha única de AlimentacaoEstado: só quem
    conseguir avançar `ultima_data_deducao` de fato aplica a baixa — uma
    segunda requisição concorrente vê 0 linhas afetadas e não faz nada,
    evitando baixa duplicada quando dois usuários abrem a tela ao mesmo tempo.
    """
    hoje = date.today()
    estado = session.get(AlimentacaoEstado, 1)
    if not estado:
        # Primeiro acesso: cria a linha única de estado. Duas requisições
        # concorrentes podem cair aqui ao mesmo tempo — a segunda perde a
        # corrida na constraint de chave primária; trata como "já criada"
        # e segue sem tentar deduzir nada agora (não há baseline anterior).
        try:
            session.add(AlimentacaoEstado(id=1, ultima_data_deducao=hoje))
            session.commit()
        except IntegrityError:
            session.rollback()
        return {"dias_deduzidos": 0, "ultima_data_deducao": hoje.isoformat()}

    dias = (hoje - estado.ultima_data_deducao).days if estado.ultima_data_deducao else 0
    if dias <= 0:
        return {"dias_deduzidos": 0, "ultima_data_deducao": estado.ultima_data_deducao.isoformat()}

    resultado = session.execute(
        text("UPDATE alimentacao_estado SET ultima_data_deducao = :novo WHERE id = 1 AND ultima_data_deducao = :antigo"),
        {"novo": hoje.isoformat(), "antigo": estado.ultima_data_deducao.isoformat()},
    )
    session.commit()
    if resultado.rowcount == 0:
        # Outra requisição venceu a corrida e já processou essa janela de dias.
        atualizado = session.get(AlimentacaoEstado, 1)
        return {"dias_deduzidos": 0, "ultima_data_deducao": atualizado.ultima_data_deducao.isoformat()}

    dietas, animais = _dietas_e_animais(session)
    consumo_total = calcular_consumo(dietas, animais)["consumo_total"]

    itens_baixados = []
    for item in consumo_total:
        estoque_item = session.exec(select(Estoque).where(Estoque.nome == item["ingrediente"])).first()
        if not estoque_item or not item["consumo_dia"]:
            continue
        baixa = round(item["consumo_dia"] * dias, 2)
        estoque_item.quantidade = round((estoque_item.quantidade or 0) - baixa, 2)
        if estoque_item.estoque_minimo is not None:
            estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
        estoque_item.atualizado_em = datetime.utcnow()
        session.add(estoque_item)
        session.add(MovimentoEstoque(
            nome_item=estoque_item.nome, movimento="Saída de ajuste", quantidade=baixa,
            unidade=estoque_item.unidade, data_movimento=hoje,
            observacao=f"Baixa automática da Alimentação — {dias} dia(s) desde a última baixa",
        ))
        itens_baixados.append({"ingrediente": item["ingrediente"], "baixa": baixa})

    session.commit()
    return {"dias_deduzidos": dias, "ultima_data_deducao": hoje.isoformat(), "itens": itens_baixados}


@router.get("/")
def obter_alimentacao(session: Session = Depends(get_session)) -> dict:
    """Plano de dieta por lote cruzado com o efetivo atual → consumo/dia por ingrediente."""
    _dar_baixa_automatica(session)
    dietas, animais = _dietas_e_animais(session)
    return calcular_consumo(dietas, animais)


@router.get("/necessidade-mensal")
def necessidade_mensal(session: Session = Depends(get_session)) -> dict:
    """Projeção de 30 dias por ingrediente, convertida em sacos quando o item é ensacado."""
    _dar_baixa_automatica(session)
    dietas, animais = _dietas_e_animais(session)
    consumo_total = calcular_consumo(dietas, animais)["consumo_total"]
    estoque_por_nome = {e.nome: e.model_dump() for e in session.exec(select(Estoque)).all()}
    return {"itens": calcular_necessidade_mensal(consumo_total, estoque_por_nome)}


@router.get("/estado-baixa")
def estado_baixa(session: Session = Depends(get_session)) -> dict:
    """Última data em que a baixa automática de estoque foi aplicada."""
    estado = session.get(AlimentacaoEstado, 1)
    return {"ultima_data_deducao": estado.ultima_data_deducao.isoformat() if estado and estado.ultima_data_deducao else None}
