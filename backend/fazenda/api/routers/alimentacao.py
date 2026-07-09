"""
Router de alimentação — plano de dieta por lote, consumo diário estimado,
necessidade mensal (com conversão para sacos) e a baixa automática de
estoque (opção A: o sistema recalcula quantos dias se passaram desde a
última baixa e desconta o consumo acumulado de uma vez, sempre que a tela
é aberta — sem botão manual nem cron real).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    AlimentacaoEstado, Animal, Dieta, DietaItemProgramado, DietaLancamento, DietaRegistroReal, Estoque,
    MovimentoEstoque,
)
from fazenda.rules.alimentacao import calcular_consumo, calcular_necessidade_mensal

router = APIRouter(prefix="/alimentacao", tags=["alimentacao"])

# Alimentos do protocolo padrão — sugestão no lançamento; o campo aceita
# qualquer texto (inclusive itens do Estoque não listados aqui).
ALIMENTOS_PADRAO = [
    "Silagem", "Ração Teck Milk 24%", "Milk Proteico", "Ração Pré-parto", "Corte 21",
    "Ração Bezerro 1", "Ração Bezerro 2",
]


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
        if not estoque_item or not item["consumo_dia"] or estoque_item.estocavel is False:
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


# ---------------------------------------------------------------------------
# Lançamento de dieta (Lançamentos > Alimentação) — histórico por lote, com
# comparação entre o programado (nutricionista) e o real oferecido. Só uma
# dieta pode estar ativa (sem encerramento efetivo) por lote de cada vez.
# ---------------------------------------------------------------------------
@router.get("/alimentos-padrao")
def alimentos_padrao() -> list[str]:
    return ALIMENTOS_PADRAO


class ItemProgramadoIn(BaseModel):
    alimento: str
    quantidade: float
    unidade: str


class DietaLancamentoIn(BaseModel):
    lote: int
    responsavel: str | None = None
    data_abertura: date
    data_prevista_encerramento: date | None = None
    observacao: str | None = None
    itens: list[ItemProgramadoIn]


def _serializar_dieta(session: Session, d: DietaLancamento) -> dict:
    itens = session.exec(
        select(DietaItemProgramado).where(DietaItemProgramado.dieta_lancamento_id == d.id)
    ).all()
    return {**d.model_dump(), "ativa": d.data_efetivo_encerramento is None, "itens_programados": [i.model_dump() for i in itens]}


@router.get("/dietas")
def listar_dietas(
    lote: int | None = None, ativo: bool | None = None, session: Session = Depends(get_session),
) -> list[dict]:
    dietas = session.exec(select(DietaLancamento)).all()
    saida = [_serializar_dieta(session, d) for d in dietas]
    if lote is not None:
        saida = [s for s in saida if s["lote"] == lote]
    if ativo is not None:
        saida = [s for s in saida if s["ativa"] == ativo]
    return sorted(saida, key=lambda s: s["data_abertura"], reverse=True)


@router.post("/dietas", status_code=201)
def criar_dieta(dados: DietaLancamentoIn, session: Session = Depends(get_session)) -> dict:
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um alimento do plano programado")
    ativa_existente = session.exec(
        select(DietaLancamento).where(
            DietaLancamento.lote == dados.lote, DietaLancamento.data_efetivo_encerramento == None  # noqa: E711
        )
    ).first()
    if ativa_existente:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma dieta ativa para o lote {dados.lote} — encerre-a antes de lançar uma nova",
        )
    dieta = DietaLancamento(
        lote=dados.lote, responsavel=dados.responsavel, data_abertura=dados.data_abertura,
        data_prevista_encerramento=dados.data_prevista_encerramento, observacao=dados.observacao,
    )
    session.add(dieta)
    session.commit()
    session.refresh(dieta)
    for item in dados.itens:
        session.add(DietaItemProgramado(dieta_lancamento_id=dieta.id, **item.model_dump()))
    session.commit()
    return _serializar_dieta(session, dieta)


class EncerrarDietaIn(BaseModel):
    data_efetivo_encerramento: date


@router.put("/dietas/{dieta_id}/encerrar")
def encerrar_dieta(dieta_id: int, dados: EncerrarDietaIn, session: Session = Depends(get_session)) -> dict:
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    if dieta.data_efetivo_encerramento is not None:
        raise HTTPException(status_code=400, detail="Esta dieta já está encerrada")
    dieta.data_efetivo_encerramento = dados.data_efetivo_encerramento
    session.add(dieta)
    session.commit()
    return {"encerrada": True, "lote": dieta.lote}


class RegistroRealIn(BaseModel):
    data: date
    itens: list[ItemProgramadoIn]


@router.post("/dietas/{dieta_id}/real", status_code=201)
def registrar_real(dieta_id: int, dados: RegistroRealIn, session: Session = Depends(get_session)) -> dict:
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um alimento oferecido")
    for item in dados.itens:
        session.add(DietaRegistroReal(dieta_lancamento_id=dieta_id, data=dados.data, **item.model_dump()))
    session.commit()
    return {"registrados": len(dados.itens)}


@router.get("/dietas/{dieta_id}/comparativo")
def comparativo_dieta(dieta_id: int, session: Session = Depends(get_session)) -> dict:
    """Programado × real por alimento — soma total real e média por dia distinto registrado."""
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    programados = session.exec(select(DietaItemProgramado).where(DietaItemProgramado.dieta_lancamento_id == dieta_id)).all()
    reais = session.exec(select(DietaRegistroReal).where(DietaRegistroReal.dieta_lancamento_id == dieta_id)).all()

    por_alimento: dict[str, dict] = {}
    for p in programados:
        acc = por_alimento.setdefault(p.alimento, {"alimento": p.alimento, "unidade": p.unidade, "programado": 0.0, "real_total": 0.0, "real_dias": 0, "real_media_dia": None})
        acc["programado"] += p.quantidade

    dias_por_alimento: dict[str, set] = {}
    for r in reais:
        acc = por_alimento.setdefault(r.alimento, {"alimento": r.alimento, "unidade": r.unidade, "programado": 0.0, "real_total": 0.0, "real_dias": 0, "real_media_dia": None})
        acc["real_total"] = round(acc["real_total"] + r.quantidade, 2)
        dias_por_alimento.setdefault(r.alimento, set()).add(r.data.isoformat())

    for alimento, dias in dias_por_alimento.items():
        por_alimento[alimento]["real_dias"] = len(dias)
        por_alimento[alimento]["real_media_dia"] = round(por_alimento[alimento]["real_total"] / len(dias), 2) if dias else None

    return {"dieta": _serializar_dieta(session, dieta), "itens": sorted(por_alimento.values(), key=lambda x: x["alimento"])}
