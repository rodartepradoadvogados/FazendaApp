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

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import (
    AlimentacaoEstado, Animal, Dieta, DietaItemProgramado, DietaLancamento, DietaRegistroReal, Estoque,
    Lote, MovimentoEstoque, Usuario,
)
from fazenda.rules.alimentacao import calcular_consumo, calcular_necessidade_mensal, _codigo_grupo
from fazenda.rules.auditoria import mapa_usuarios
from fazenda.rules.farmacia import pode_baixar_estoque

# Nº de tratos por dia (fornecimentos). Hoje são 2.
NUM_TRATOS = 2

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
        # Gatilho de comunicação: só deduz insumo cujo estoque inicial/primeira
        # compra já foi registrado (None = insumo legado, mantém comportamento).
        if not pode_baixar_estoque(estoque_item):
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


# % de matéria seca padrão por ingrediente (volumosos ~33%, concentrados ~88%);
# o usuário edita na aba Matéria seca.
_MS_PADRAO = {
    "Silagem": 33.24, "Ração Teck Milk 24%": 88.0, "Milk Proteico": 88.0, "Ração Pré-parto": 88.0,
    "Corte 21": 88.0, "Ração Bezerro 1": 88.0, "Ração Bezerro 2": 88.0,
}


def _seed_materia_seca(session: Session) -> None:
    from fazenda.models import IngredienteMS
    existentes = {i.nome for i in session.exec(select(IngredienteMS)).all()}
    novos = [IngredienteMS(nome=nome, ms_pct=_MS_PADRAO.get(nome)) for nome in ALIMENTOS_PADRAO if nome not in existentes]
    if novos:
        for n in novos:
            session.add(n)
        session.commit()


@router.get("/materia-seca")
def listar_materia_seca(session: Session = Depends(get_session)) -> list[dict]:
    """Lista de ingredientes padrão com seu % de matéria seca (editável)."""
    from fazenda.models import IngredienteMS
    _seed_materia_seca(session)
    itens = session.exec(select(IngredienteMS).order_by(IngredienteMS.nome)).all()
    return [i.model_dump() for i in itens]


class IngredienteMSIn(BaseModel):
    nome: str
    ms_pct: float | None = None


@router.put("/materia-seca")
def salvar_materia_seca(dados: IngredienteMSIn, session: Session = Depends(get_session)) -> dict:
    """Upsert do % de matéria seca de um ingrediente (cadastro/edição)."""
    from fazenda.models import IngredienteMS
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome do ingrediente é obrigatório")
    item = session.exec(select(IngredienteMS).where(IngredienteMS.nome == nome)).first()
    if not item:
        item = IngredienteMS(nome=nome)
    item.ms_pct = dados.ms_pct
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.get("/tabela-nutricional")
def obter_tabela_nutricional() -> dict:
    """Tabela nutricional de referência (nutriente × alimento) — para o veterinário
    consultar num modal, com calculadora ao lado."""
    from fazenda.rules.tabela_nutricional import tabela_nutricional
    return tabela_nutricional()


class ItemProgramadoIn(BaseModel):
    alimento: str
    quantidade: float
    unidade: str
    base: str | None = None       # "MN" (matéria natural) | "MS" (matéria seca)
    ms_pct: float | None = None   # % de matéria seca do alimento


class DietaLancamentoIn(BaseModel):
    lote: int
    responsavel: str | None = None
    data_abertura: date
    data_prevista_encerramento: date | None = None
    observacao: str | None = None
    base_quantidade: str | None = None  # "total" (padrão) | "animal" (por cabeça/dia)
    leite_bezerros_kg_dia: float | None = None  # kg/dia de leite p/ bezerros (relatório Controle × Entregue)
    itens: list[ItemProgramadoIn]
    # Se True e já houver dieta ativa no lote, encerra-a na data de início
    # desta (o veterinário responde "sim" ao salvar). Se False e houver ativa,
    # devolve 409 como antes.
    encerrar_anterior: bool = False


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
    nomes = mapa_usuarios(session, {s["usuario_id"] for s in saida})
    for s in saida:
        s["usuario_nome"] = nomes.get(s["usuario_id"])
    if lote is not None:
        saida = [s for s in saida if s["lote"] == lote]
    if ativo is not None:
        saida = [s for s in saida if s["ativa"] == ativo]
    return sorted(saida, key=lambda s: s["data_abertura"], reverse=True)


@router.post("/dietas", status_code=201)
def criar_dieta(dados: DietaLancamentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um alimento do plano programado")
    ativa_existente = session.exec(
        select(DietaLancamento).where(
            DietaLancamento.lote == dados.lote, DietaLancamento.data_efetivo_encerramento == None  # noqa: E711
        )
    ).first()
    if ativa_existente:
        if dados.encerrar_anterior:
            ativa_existente.data_efetivo_encerramento = dados.data_abertura
            session.add(ativa_existente)
            session.commit()
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe uma dieta ativa para o lote {dados.lote} — encerre-a antes de lançar uma nova",
            )
    dieta = DietaLancamento(
        lote=dados.lote, responsavel=dados.responsavel, data_abertura=dados.data_abertura,
        data_prevista_encerramento=dados.data_prevista_encerramento, observacao=dados.observacao,
        base_quantidade=dados.base_quantidade or "total",
        leite_bezerros_kg_dia=dados.leite_bezerros_kg_dia,
        usuario_id=user.id,
    )
    session.add(dieta)
    session.commit()
    session.refresh(dieta)
    for item in dados.itens:
        session.add(DietaItemProgramado(dieta_lancamento_id=dieta.id, **item.model_dump()))
    session.commit()
    return _serializar_dieta(session, dieta)


def _animais_do_lote(session: Session, lote: int) -> list[Animal]:
    ativos = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
    return [
        a for a in ativos
        if not a.eh_semen and a.sexo != "M" and (_codigo_grupo(a.grupo_primario) or "") == f"{lote:02d}"
    ]


@router.get("/dietas/contexto/{lote}")
def contexto_dieta(lote: int, session: Session = Depends(get_session)) -> dict:
    """Contexto do lote para o veterinário formular a dieta: nome/nº do lote,
    nº de animais, última dieta (produtos e qtd/cabeça/dia), último controle
    leiteiro de cada animal e um resumo (DEL médio, média do CL, data do CL)."""
    lote_cad = session.exec(select(Lote).where(Lote.codigo == f"{lote:02d}")).first()
    animais = _animais_do_lote(session, lote)
    n = len(animais)

    dels = [a.del_dias for a in animais if a.del_dias is not None]
    cls = [a.ult_cl_kg for a in animais if a.ult_cl_kg is not None]
    datas_cl = [a.data_ult_leite for a in animais if a.data_ult_leite is not None]

    # Última dieta ativa do lote (produtos + qtd total/dia → por cabeça/dia).
    ativa = session.exec(
        select(DietaLancamento).where(
            DietaLancamento.lote == lote, DietaLancamento.data_efetivo_encerramento == None  # noqa: E711
        )
    ).first()
    ultima_dieta = None
    if ativa:
        itens = session.exec(select(DietaItemProgramado).where(DietaItemProgramado.dieta_lancamento_id == ativa.id)).all()
        ultima_dieta = {
            "data_abertura": ativa.data_abertura.isoformat(),
            "responsavel": ativa.responsavel,
            "itens": [
                {"alimento": it.alimento, "unidade": it.unidade, "total_dia": it.quantidade,
                 "por_cabeca": round(it.quantidade / n, 3) if n else None}
                for it in itens
            ],
        }

    return {
        "lote": lote,
        "nome": lote_cad.nome if lote_cad else None,
        "qtd_animais": n,
        "del_medio": round(sum(dels) / len(dels)) if dels else None,
        "media_cl": round(sum(cls) / len(cls), 1) if cls else None,
        "data_ult_cl": max(datas_cl).isoformat() if datas_cl else None,
        "animais": sorted([
            {"numero": a.numero, "del_dias": a.del_dias, "ult_cl_kg": a.ult_cl_kg,
             "data_ult_leite": a.data_ult_leite.isoformat() if a.data_ult_leite else None}
            for a in animais
        ], key=lambda x: (x["ult_cl_kg"] is None, -(x["ult_cl_kg"] or 0))),
        "ultima_dieta": ultima_dieta,
    }


@router.get("/dietas/{dieta_id}/apresentacao")
def apresentacao_dieta(dieta_id: int, session: Session = Depends(get_session)) -> dict:
    """Como o funcionário vê a dieta para conferir no vagão: por produto — qtd/
    cabeça, total/dia, total/trato; e o somatório de kg no vagão do lote."""
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    n = len(_animais_do_lote(session, dieta.lote))
    lote_cad = session.exec(select(Lote).where(Lote.codigo == f"{dieta.lote:02d}")).first()
    itens = session.exec(select(DietaItemProgramado).where(DietaItemProgramado.dieta_lancamento_id == dieta_id)).all()
    linhas = []
    total_dia = 0.0
    for it in itens:
        td = it.quantidade  # total do lote/dia
        linhas.append({
            "alimento": it.alimento, "unidade": it.unidade,
            "total_dia": round(td, 2),
            "por_cabeca": round(td / n, 3) if n else None,
            "total_trato": round(td / NUM_TRATOS, 2),
        })
        if (it.unidade or "").lower() in ("kg", "g"):
            total_dia += td
    return {
        "lote": dieta.lote, "nome": lote_cad.nome if lote_cad else None, "qtd_animais": n,
        "data_abertura": dieta.data_abertura.isoformat(),
        "data_prevista_encerramento": dieta.data_prevista_encerramento.isoformat() if dieta.data_prevista_encerramento else None,
        "num_tratos": NUM_TRATOS, "itens": linhas,
        # Somatório de quilos que deve estar no vagão (só itens em kg).
        "vagao_kg_dia": round(total_dia, 2),
        "vagao_kg_trato": round(total_dia / NUM_TRATOS, 2),
    }


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
def registrar_real(dieta_id: int, dados: RegistroRealIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um alimento oferecido")
    for item in dados.itens:
        session.add(DietaRegistroReal(dieta_lancamento_id=dieta_id, data=dados.data, usuario_id=user.id, **item.model_dump()))
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
