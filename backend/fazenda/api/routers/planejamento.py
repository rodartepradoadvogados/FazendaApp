"""
Router de Planejamento (Financeiro > Planejamento) — duas sub-sub-abas:

- Orçamento: uma linha por ano/mês/conta gerencial/centro de custo, comparada
  contra o realizado (ContaGerencial/LancamentoItem já existentes) no
  relatório orçado x realizado — mesmo padrão do PCO de ERPs como o TOTVS
  Protheus (planilha por conta+centro+período, captura automática do
  realizado, desvio absoluto/percentual).
- Planejamento financeiro: cenários de simulação (otimista/realista/
  pessimista/personalizado) com linhas de receita/despesa projetadas mês a
  mês, para uma projeção de fluxo de caixa "e se" — sem efeito algum sobre
  Estoque/Financeiro além de servir de base para "Importar para Pedidos".

Nenhum dos dois lança nada em Financeiro/Estoque sozinho.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    ContaGerencial, LancamentoItem, OrcamentoItem, Pedido, PedidoItem,
    PlanejamentoCenario, PlanejamentoItem, PlanoContaGerencial, Usuario,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.centro_custo import mapear_centro_custo
from fazenda.rules.vale_item import sem_itens_automaticos, sem_itens_de_vale
from fazenda.api.routers.pedidos import _proximo_numero_pedido

router = APIRouter(prefix="/planejamento", tags=["planejamento"])


# ─────────────────────────────────────────────────────────────────────────
# Orçamento
# ─────────────────────────────────────────────────────────────────────────
class OrcamentoItemIn(BaseModel):
    ano: int
    mes: int
    codigo_conta_gerencial: str
    centro_custo: Optional[str] = None
    tipo: str  # "receita" | "despesa"
    valor_orcado: float
    observacao: Optional[str] = None


@router.get("/orcamento")
def listar_orcamento(
    ano: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(OrcamentoItem)
    if ano:
        query = query.where(OrcamentoItem.ano == ano)
    if fazenda_id is not None:
        query = query.where(OrcamentoItem.fazenda_id == fazenda_id)
    itens = session.exec(query.order_by(OrcamentoItem.ano, OrcamentoItem.mes, OrcamentoItem.codigo_conta_gerencial)).all()
    query_nomes = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_nomes = query_nomes.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    nomes = {c.codigo: c.nome for c in session.exec(query_nomes).all()}
    return [{**i.model_dump(), "nome_conta_gerencial": nomes.get(i.codigo_conta_gerencial, i.codigo_conta_gerencial)} for i in itens]


@router.post("/orcamento", status_code=201)
def criar_item_orcamento(
    dados: OrcamentoItemIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'receita' ou 'despesa'")
    if not 1 <= dados.mes <= 12:
        raise HTTPException(status_code=400, detail="mes deve estar entre 1 e 12")
    item = OrcamentoItem(
        ano=dados.ano, mes=dados.mes, codigo_conta_gerencial=dados.codigo_conta_gerencial,
        centro_custo=mapear_centro_custo(dados.centro_custo) if dados.centro_custo else None,
        tipo=dados.tipo, valor_orcado=dados.valor_orcado, observacao=dados.observacao,
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.put("/orcamento/{item_id}")
def atualizar_item_orcamento(
    item_id: int,
    dados: OrcamentoItemIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(OrcamentoItem, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de orçamento não encontrado")
    item.ano = dados.ano
    item.mes = dados.mes
    item.codigo_conta_gerencial = dados.codigo_conta_gerencial
    item.centro_custo = mapear_centro_custo(dados.centro_custo) if dados.centro_custo else None
    item.tipo = dados.tipo
    item.valor_orcado = dados.valor_orcado
    item.observacao = dados.observacao
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.delete("/orcamento/{item_id}", status_code=204)
def excluir_item_orcamento(
    item_id: int,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> None:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(OrcamentoItem, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de orçamento não encontrado")
    session.delete(item)
    session.commit()


@router.get("/orcamento/comparativo")
def comparativo_orcado_realizado(
    ano: int = Query(...),
    mes_inicio: int = Query(1),
    mes_fim: int = Query(12),
    centro_custo: Optional[str] = Query(None),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Orçado x realizado por conta gerencial, agregando o realizado a partir
    de LancamentoItem (mesma fonte usada no DRE) por competência."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_orc = select(OrcamentoItem).where(
        OrcamentoItem.ano == ano, OrcamentoItem.mes >= mes_inicio, OrcamentoItem.mes <= mes_fim
    )
    if centro_custo:
        query_orc = query_orc.where(OrcamentoItem.centro_custo == centro_custo)
    if fazenda_id is not None:
        query_orc = query_orc.where(OrcamentoItem.fazenda_id == fazenda_id)
    orcados = session.exec(query_orc).all()

    query_nomes = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_nomes = query_nomes.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    nomes = {c.codigo: c.nome for c in session.exec(query_nomes).all()}
    linhas: dict[str, dict] = {}
    for o in orcados:
        chave = o.codigo_conta_gerencial
        l = linhas.setdefault(chave, {
            "codigo_conta_gerencial": chave, "nome_conta_gerencial": nomes.get(chave, chave),
            "tipo": o.tipo, "orcado": 0.0, "realizado": 0.0,
        })
        l["orcado"] = round(l["orcado"] + o.valor_orcado, 2)

    data_ini = date(ano, mes_inicio, 1)
    # Último dia real do mes_fim (evita cortar lançamentos do dia 29-31).
    data_fim = date(ano, mes_fim, calendar.monthrange(ano, mes_fim)[1])

    from fazenda.rules.parametros import regras_v2_ativas
    if regras_v2_ativas(session, fazenda_id):
        return _comparativo_v2(session, fazenda_id, ano, mes_inicio, mes_fim, data_ini, data_fim,
                               centro_custo or None, linhas, nomes)

    query_itens = sem_itens_automaticos(sem_itens_de_vale(
        select(LancamentoItem).where(LancamentoItem.data_competencia >= data_ini, LancamentoItem.data_competencia <= data_fim)
    ))
    if fazenda_id is not None:
        query_itens = query_itens.where(LancamentoItem.fazenda_id == fazenda_id)
    itens = session.exec(query_itens).all()
    centros_por_lanc = {}
    if centro_custo:
        query_contas = select(ContaGerencial).where(
            ContaGerencial.data_competencia >= data_ini, ContaGerencial.data_competencia <= data_fim
        )
        if fazenda_id is not None:
            query_contas = query_contas.where(ContaGerencial.fazenda_id == fazenda_id)
        for c in session.exec(query_contas).all():
            centros_por_lanc[c.numero_lancamento] = c.centro_custo

    for it in itens:
        if centro_custo and centros_por_lanc.get(it.numero_lancamento) != centro_custo:
            continue
        chave = it.codigo_conta_gerencial or "(sem conta)"
        l = linhas.setdefault(chave, {
            "codigo_conta_gerencial": chave, "nome_conta_gerencial": nomes.get(chave, it.nome_conta_gerencial or chave),
            "tipo": it.tipo, "orcado": 0.0, "realizado": 0.0,
        })
        l["realizado"] = round(l["realizado"] + it.valor_total, 2)

    resultado = []
    for l in linhas.values():
        desvio = round(l["realizado"] - l["orcado"], 2)
        desvio_pct = round((desvio / l["orcado"]) * 100, 1) if l["orcado"] else None
        resultado.append({**l, "desvio": desvio, "desvio_pct": desvio_pct})
    resultado.sort(key=lambda x: x["codigo_conta_gerencial"])

    return {
        "periodo": {"ano": ano, "mes_inicio": mes_inicio, "mes_fim": mes_fim},
        "linhas": resultado,
        "total_orcado": round(sum(l["orcado"] for l in resultado), 2),
        "total_realizado": round(sum(l["realizado"] for l in resultado), 2),
    }


def _comparativo_v2(
    session: Session, fazenda_id: int | None, ano: int, mes_inicio: int, mes_fim: int,
    data_ini: date, data_fim: date, centro_custo: Optional[str], linhas: dict[str, dict], nomes: dict[str, str],
) -> dict:
    """Realizado com as regras v2 (Fase A — R4, fonte única): os MESMOS
    registros da DRE de competência (financeiro.registros_competencia_v2), em
    vez de `LancamentoItem.valor_total` cru (PR 7: desconto da nota rateado,
    receita bruta com o Funrural/Senar numa linha de dedução, centro de custo
    por item).

    PR 8 (orçamento — fazenda/rules/orcamento.py): totais SEPARADOS por grupo
    (`totais.receita`, `deducao`, `despesa_operacional`, `fora_do_resultado`,
    nunca receita somada com despesa), herança por prefixo (o orçamento do
    grupo cobre as filhas sem orçamento próprio, Q8) e desvio só onde há
    orçado (`situacao`: favoravel/desfavoravel/no_orcado/sem_orcamento).
    `total_orcado`/`total_realizado` continuam na resposta como os totais de
    DESPESA OPERACIONAL (compatibilidade com telas antigas: o total antigo
    somava receita com despesa e com o que nem é resultado)."""
    from fazenda.api.routers.financeiro import _mapa_linha_por_codigo, registros_competencia_v2
    from fazenda.rules.orcamento import comparar_orcado_realizado

    registros = registros_competencia_v2(session, fazenda_id, data_ini, data_fim, centro_custo)
    comparativo = comparar_orcado_realizado(linhas, registros, _mapa_linha_por_codigo(session, fazenda_id), nomes)
    despesa = comparativo["totais"]["despesa_operacional"]
    return {
        "periodo": {"ano": ano, "mes_inicio": mes_inicio, "mes_fim": mes_fim},
        "linhas": comparativo["linhas"],
        "totais": comparativo["totais"],
        "total_orcado": despesa["orcado"],
        "total_realizado": despesa["realizado"],
        "regras_v2": True,
    }


# ─────────────────────────────────────────────────────────────────────────
# Fase C dos Relatórios — Plano › Orçamento (molde único)
# ─────────────────────────────────────────────────────────────────────────
def _meses_do_periodo(ini: date, fim: date) -> list[tuple[int, int]]:
    meses, ano, mes = [], ini.year, ini.month
    while (ano, mes) <= (fim.year, fim.month):
        meses.append((ano, mes))
        mes += 1
        if mes == 13:
            ano, mes = ano + 1, 1
    return meses


@router.get("/orcamento/relatorio")
def relatorio_orcamento(
    data_inicio: date = Query(..., description="Primeiro dia de um mês"),
    data_fim: date = Query(..., description="Último dia de um mês"),
    centro_custo: Optional[str] = Query(None),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Orçado × realizado do relatório "Gastei o que planejei?" (Fase C):
    o comparativo conta a conta do PR 8 (mesmas regras, mesmo motor), mais o
    orçado por LINHA DA DRE (a cascata montada com os valores orçados — ver
    rules/orcamento.py::cascata_orcada), em R$ e em R$ por litro entregue, e o
    "orçado por litro" (para o Resultado por litro comparar com o orçado).

    Só leitura. Período de meses inteiros (o orçamento é mensal), em
    competência (o orçamento é pelo mês do gasto). Com a flag
    `financeiro_regras_v2` desligada devolve o comparativo ANTIGO tal qual
    (`comparativo_antigo`, os mesmos números de GET /orcamento/comparativo) —
    o que a regra antiga não tem (totais por grupo, linha da DRE, R$/L) a tela
    trava com o porquê."""
    if data_fim < data_inicio:
        raise HTTPException(status_code=422, detail="A data final é anterior à inicial.")
    if data_inicio.day != 1 or data_fim.day != calendar.monthrange(data_fim.year, data_fim.month)[1]:
        raise HTTPException(status_code=422, detail="O orçamento é mensal: escolha um período de meses inteiros.")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    from fazenda.rules.parametros import regras_v2_ativas

    meses = _meses_do_periodo(data_inicio, data_fim)
    anos = sorted({a for a, _m in meses})
    query_orc = select(OrcamentoItem).where(OrcamentoItem.ano.in_(anos))
    if fazenda_id is not None:
        query_orc = query_orc.where(OrcamentoItem.fazenda_id == fazenda_id)
    if centro_custo:
        query_orc = query_orc.where(OrcamentoItem.centro_custo == centro_custo)
    no_periodo = set(meses)
    itens = [o for o in session.exec(query_orc).all() if (o.ano, o.mes) in no_periodo]
    base = {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "centro_custo": centro_custo, "regime": "competencia",
        "tem_orcamento": bool(itens),
        "meses": [f"{a:04d}-{m:02d}" for a, m in meses],
        "meses_com_orcamento": sorted({f"{o.ano:04d}-{o.mes:02d}" for o in itens}),
    }
    if not regras_v2_ativas(session, fazenda_id):
        if len(anos) > 1:
            return {**base, "regras_v2": False, "comparativo_antigo": None,
                    "travado": "Com as regras antigas, o orçado × realizado é de um ano por vez: escolha um período dentro do mesmo ano."}
        antigo = comparativo_orcado_realizado(
            ano=anos[0], mes_inicio=data_inicio.month, mes_fim=data_fim.month, centro_custo=centro_custo,
            session=session, fazenda_id=fazenda_id)
        return {**base, "regras_v2": False, "comparativo_antigo": antigo, "travado": None}

    from fazenda.api.routers.financeiro import _mapa_linha_por_codigo, calcular_dre, registros_competencia_v2
    from fazenda.api.routers.relatorio_resultado_litro import _entregas
    from fazenda.rules.custo_leite import litros_leite_no_periodo
    from fazenda.rules.dre import DEDUCAO_IMPOSTOS, resolver_linha_dre
    from fazenda.rules.orcamento import cascata_orcada, comparar_orcado_realizado, conferir_com_a_dre, por_linha_dre
    from fazenda.rules.resultado_litro import indicadores_por_litro, meses_no_periodo

    query_plano = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_plano = query_plano.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    plano = session.exec(query_plano).all()
    nomes = {c.codigo: c.nome for c in plano}
    orcadas: dict[str, dict] = {}
    for o in itens:
        l = orcadas.setdefault(o.codigo_conta_gerencial, {
            "codigo_conta_gerencial": o.codigo_conta_gerencial,
            "nome_conta_gerencial": nomes.get(o.codigo_conta_gerencial, o.codigo_conta_gerencial),
            "tipo": o.tipo, "orcado": 0.0, "realizado": 0.0,
        })
        l["orcado"] = round(l["orcado"] + o.valor_orcado, 2)

    mapa = _mapa_linha_por_codigo(session, fazenda_id)
    registros = registros_competencia_v2(session, fazenda_id, data_inicio, data_fim, centro_custo or None)
    comparativo = comparar_orcado_realizado({k: dict(v) for k, v in orcadas.items()}, registros, mapa, nomes)
    for l in comparativo["linhas"]:
        l["linha_dre"] = (DEDUCAO_IMPOSTOS if l["grupo"] == "deducao"
                          else None if l["grupo"] == "fora_do_resultado"
                          else resolver_linha_dre(l["codigo_conta_gerencial"], mapa))

    dre = calcular_dre(session, fazenda_id, data_inicio, data_fim, centro_custo or None, "competencia", regras_v2=True)
    dre.pop("_registros", None)
    orc = cascata_orcada(orcadas, mapa, dre["depreciacao_periodo"]["total"])
    entregas, _unidades = _entregas(session, fazenda_id, True)
    litros = round(litros_leite_no_periodo(entregas, data_inicio, data_fim), 1)

    litro_orcado = None
    if itens:
        codigos_receita = {c.codigo for c in plano if c.rmca_receita_leite}
        codigos_custo = {c.codigo for c in plano if c.rmca_custo_alimentacao}
        linhas_orc = {l["chave"]: l["valor"] for l in orc["linhas"]}
        receita_leite = round(sum(l["orcado"] for c, l in orcadas.items() if c in codigos_receita and l["tipo"] == "receita"), 2)
        # Deduções orçadas (Funrural/Senar) = a linha de deduções do orçado: na
        # fazenda de leite é a nota do laticínio.
        deducoes = round(linhas_orc.get(DEDUCAO_IMPOSTOS, 0.0), 2) if receita_leite else 0.0
        leite = {
            "receita_leite": receita_leite, "deducoes_receita_leite": deducoes,
            "receita_leite_liquida": round(receita_leite - deducoes, 2),
            "custo_alimentacao": round(sum(l["orcado"] for c, l in orcadas.items() if c in codigos_custo and l["tipo"] != "receita"), 2),
        }
        litro_orcado = indicadores_por_litro(linhas=linhas_orc, leite=leite, litros=litros,
                                             meses=meses_no_periodo(data_inicio, data_fim))

    return {
        **base,
        "regras_v2": True,
        "linhas": comparativo["linhas"],
        "totais": comparativo["totais"],
        "linhas_dre": por_linha_dre(dre["cascata"], orc["linhas"], litros),
        "cascata_orcada": orc["linhas"],
        "orcado_sem_linha": orc["sem_linha"],
        "orcado_fora_da_dre": orc["fora_da_dre"]["total"],
        "nao_classificado_dre": dre["nao_classificado"],
        "litros": litros,
        "litro_orcado": litro_orcado,
        "conferencia": conferir_com_a_dre(comparativo["linhas"], dre["cascata"], mapa),
    }


class CelulaGradeIn(BaseModel):
    codigo_conta_gerencial: str
    centro_custo: Optional[str] = None
    tipo: str  # "receita" | "despesa"
    mes: int
    valor: float


class GradeOrcamentoIn(BaseModel):
    ano: int
    celulas: list[CelulaGradeIn]


# Caminho próprio (não "/orcamento/grade"): PUT /orcamento/{item_id} viria antes e recusaria "grade" como id.
@router.put("/orcamento-grade")
def salvar_grade_orcamento(
    dados: GradeOrcamentoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """A planilha do orçamento (conta × 12 meses) salva de uma vez: cada
    célula (ano, mês, conta, centro) vira UM item de orçamento — criado se não
    existe, atualizado se existe um só. Zerar uma célula apaga o item, a não
    ser que ele tenha observação ou tenha virado pedido (aí fica com zero).
    Célula com mais de um item (lançados um a um na tela anterior) não é
    mexida: volta em `ignoradas`, para a pessoa ajustar item a item."""
    if not 2000 <= dados.ano <= 2100:
        raise HTTPException(status_code=422, detail="Ano fora do intervalo aceito.")
    if len(dados.celulas) > 6000:
        raise HTTPException(status_code=422, detail="Planilha grande demais para salvar de uma vez.")
    for c in dados.celulas:
        if c.tipo not in ("receita", "despesa"):
            raise HTTPException(status_code=422, detail="tipo deve ser 'receita' ou 'despesa'")
        if not 1 <= c.mes <= 12:
            raise HTTPException(status_code=422, detail="mes deve estar entre 1 e 12")
        if not c.codigo_conta_gerencial.strip():
            raise HTTPException(status_code=422, detail="Informe a conta gerencial de cada linha.")

    existentes: dict[tuple, list[OrcamentoItem]] = {}
    for o in session.exec(select(OrcamentoItem).where(OrcamentoItem.fazenda_id == fazenda_id, OrcamentoItem.ano == dados.ano)).all():
        existentes.setdefault((o.mes, o.codigo_conta_gerencial, o.centro_custo or None), []).append(o)
    com_pedido = set(session.exec(select(Pedido.origem_item_id).where(
        Pedido.fazenda_id == fazenda_id, Pedido.origem_tipo == "orcamento")).all())

    criadas = atualizadas = excluidas = 0
    ignoradas: list[dict] = []
    for c in dados.celulas:
        centro = mapear_centro_custo(c.centro_custo) if c.centro_custo else None
        valor = round(c.valor, 2)
        itens = existentes.get((c.mes, c.codigo_conta_gerencial, centro), [])
        if len(itens) > 1:
            ignoradas.append({"codigo_conta_gerencial": c.codigo_conta_gerencial, "centro_custo": centro, "mes": c.mes,
                              "motivo": f"{len(itens)} itens neste mês — ajuste item a item"})
            continue
        if not itens:
            if valor:
                session.add(OrcamentoItem(
                    ano=dados.ano, mes=c.mes, codigo_conta_gerencial=c.codigo_conta_gerencial, centro_custo=centro,
                    tipo=c.tipo, valor_orcado=valor, usuario_id=user.id if isinstance(user, Usuario) else None,
                    fazenda_id=fazenda_id,
                ))
                criadas += 1
            continue
        item = itens[0]
        if not valor and not (item.observacao or "").strip() and item.id not in com_pedido:
            session.delete(item)
            excluidas += 1
            continue
        if item.valor_orcado != valor or item.tipo != c.tipo:
            item.valor_orcado = valor
            item.tipo = c.tipo
            item.atualizado_em = datetime.utcnow()
            session.add(item)
            atualizadas += 1
    session.commit()
    return {"criadas": criadas, "atualizadas": atualizadas, "excluidas": excluidas, "ignoradas": ignoradas}


# ─────────────────────────────────────────────────────────────────────────
# Planejamento financeiro (cenários)
# ─────────────────────────────────────────────────────────────────────────
class CenarioIn(BaseModel):
    nome: str
    tipo: str = "personalizado"  # "otimista" | "realista" | "pessimista" | "personalizado"
    observacao: Optional[str] = None


@router.get("/cenarios")
def listar_cenarios(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(PlanejamentoCenario).where(PlanejamentoCenario.ativo == True)
    if fazenda_id is not None:
        query = query.where(PlanejamentoCenario.fazenda_id == fazenda_id)
    cenarios = session.exec(query.order_by(PlanejamentoCenario.criado_em.desc())).all()
    return [c.model_dump() for c in cenarios]


@router.post("/cenarios", status_code=201)
def criar_cenario(
    dados: CenarioIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if dados.tipo not in ("otimista", "realista", "pessimista", "personalizado"):
        raise HTTPException(status_code=400, detail="tipo de cenário inválido")
    cenario = PlanejamentoCenario(
        nome=dados.nome, tipo=dados.tipo, observacao=dados.observacao,
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )
    session.add(cenario)
    session.commit()
    session.refresh(cenario)
    return cenario.model_dump()


@router.put("/cenarios/{cenario_id}")
def atualizar_cenario(
    cenario_id: int,
    dados: CenarioIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cenario = session.get(PlanejamentoCenario, cenario_id)
    if not cenario or (fazenda_id is not None and cenario.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Cenário não encontrado")
    cenario.nome = dados.nome
    cenario.tipo = dados.tipo
    cenario.observacao = dados.observacao
    session.add(cenario)
    session.commit()
    session.refresh(cenario)
    return cenario.model_dump()


@router.delete("/cenarios/{cenario_id}", status_code=204)
def excluir_cenario(
    cenario_id: int,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> None:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cenario = session.get(PlanejamentoCenario, cenario_id)
    if not cenario or (fazenda_id is not None and cenario.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Cenário não encontrado")
    for i in session.exec(select(PlanejamentoItem).where(PlanejamentoItem.cenario_id == cenario_id)).all():
        session.delete(i)
    session.delete(cenario)
    session.commit()


class PlanejamentoItemIn(BaseModel):
    mes_competencia: str  # "YYYY-MM"
    codigo_conta_gerencial: str
    centro_custo: Optional[str] = None
    tipo: str  # "receita" | "despesa"
    valor_previsto: float
    observacao: Optional[str] = None


@router.get("/cenarios/{cenario_id}/itens")
def listar_itens_cenario(
    cenario_id: int,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cenario = session.get(PlanejamentoCenario, cenario_id)
    if not cenario or (fazenda_id is not None and cenario.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Cenário não encontrado")
    query_nomes = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_nomes = query_nomes.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    nomes = {c.codigo: c.nome for c in session.exec(query_nomes).all()}
    itens = session.exec(select(PlanejamentoItem).where(PlanejamentoItem.cenario_id == cenario_id).order_by(PlanejamentoItem.mes_competencia)).all()
    return [{**i.model_dump(), "nome_conta_gerencial": nomes.get(i.codigo_conta_gerencial, i.codigo_conta_gerencial)} for i in itens]


@router.post("/cenarios/{cenario_id}/itens", status_code=201)
def criar_item_cenario(
    cenario_id: int,
    dados: PlanejamentoItemIn,
    session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    cenario = session.get(PlanejamentoCenario, cenario_id)
    if not cenario or (fazenda_id is not None and cenario.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Cenário não encontrado")
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'receita' ou 'despesa'")
    item = PlanejamentoItem(
        cenario_id=cenario_id, mes_competencia=dados.mes_competencia, codigo_conta_gerencial=dados.codigo_conta_gerencial,
        centro_custo=mapear_centro_custo(dados.centro_custo) if dados.centro_custo else None,
        tipo=dados.tipo, valor_previsto=dados.valor_previsto, observacao=dados.observacao,
        fazenda_id=fazenda_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.put("/itens/{item_id}")
def atualizar_item_cenario(
    item_id: int,
    dados: PlanejamentoItemIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(PlanejamentoItem, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de planejamento não encontrado")
    item.mes_competencia = dados.mes_competencia
    item.codigo_conta_gerencial = dados.codigo_conta_gerencial
    item.centro_custo = mapear_centro_custo(dados.centro_custo) if dados.centro_custo else None
    item.tipo = dados.tipo
    item.valor_previsto = dados.valor_previsto
    item.observacao = dados.observacao
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.delete("/itens/{item_id}", status_code=204)
def excluir_item_cenario(
    item_id: int,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> None:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(PlanejamentoItem, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de planejamento não encontrado")
    session.delete(item)
    session.commit()


@router.get("/cenarios/{cenario_id}/projecao")
def projecao_cenario(
    cenario_id: int,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Fluxo de caixa projetado do cenário: soma receitas/despesas por mês e
    acumula o saldo — mesma lógica de agregação do Fluxo de Caixa do site,
    aplicada aos valores previstos em vez do realizado."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cenario = session.get(PlanejamentoCenario, cenario_id)
    if not cenario or (fazenda_id is not None and cenario.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Cenário não encontrado")
    itens = session.exec(select(PlanejamentoItem).where(PlanejamentoItem.cenario_id == cenario_id)).all()
    por_mes: dict[str, dict] = {}
    for it in itens:
        m = por_mes.setdefault(it.mes_competencia, {"mes": it.mes_competencia, "receitas": 0.0, "despesas": 0.0})
        if it.tipo == "receita":
            m["receitas"] = round(m["receitas"] + it.valor_previsto, 2)
        else:
            m["despesas"] = round(m["despesas"] + it.valor_previsto, 2)
    meses = sorted(por_mes.values(), key=lambda x: x["mes"])
    acumulado = 0.0
    for m in meses:
        m["saldo"] = round(m["receitas"] - m["despesas"], 2)
        acumulado = round(acumulado + m["saldo"], 2)
        m["acumulado"] = acumulado
    return {"cenario": cenario.model_dump(), "meses": meses}


# ─────────────────────────────────────────────────────────────────────────
# Importar para Pedidos
# ─────────────────────────────────────────────────────────────────────────
class ImportarParaPedidoIn(BaseModel):
    origem_tipo: str  # "orcamento" | "planejamento_financeiro"
    origem_item_id: int
    tipo_pedido: str  # "compra" | "venda"
    fornecedor_cliente: Optional[str] = None
    data_pedido: Optional[date] = None


@router.post("/importar-para-pedido", status_code=201)
def importar_para_pedido(
    dados: ImportarParaPedidoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Cria um Pedido (rascunho) a partir de uma linha de Orçamento ou de
    Planejamento financeiro — só copia os dados, não lança nada em
    Financeiro/Estoque. O usuário completa e salva o pedido normalmente."""
    if dados.origem_tipo not in ("orcamento", "planejamento_financeiro"):
        raise HTTPException(status_code=400, detail="origem_tipo inválido")
    if dados.tipo_pedido not in ("compra", "venda"):
        raise HTTPException(status_code=400, detail="tipo_pedido deve ser 'compra' ou 'venda'")

    query_nomes = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_nomes = query_nomes.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    nomes = {c.codigo: c.nome for c in session.exec(query_nomes).all()}
    if dados.origem_tipo == "orcamento":
        origem = session.get(OrcamentoItem, dados.origem_item_id)
        if not origem or (fazenda_id is not None and origem.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Item de orçamento não encontrado")
        codigo, centro, valor = origem.codigo_conta_gerencial, origem.centro_custo, origem.valor_orcado
        data_ref = date(origem.ano, origem.mes, 1)
    else:
        origem = session.get(PlanejamentoItem, dados.origem_item_id)
        if not origem or (fazenda_id is not None and origem.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Item de planejamento não encontrado")
        codigo, centro, valor = origem.codigo_conta_gerencial, origem.centro_custo, origem.valor_previsto
        ano, mes = (int(x) for x in origem.mes_competencia.split("-"))
        data_ref = date(ano, mes, 1)

    data_pedido = dados.data_pedido or date.today()
    numero_pedido = _proximo_numero_pedido(session, data_pedido.year, fazenda_id)
    pedido = Pedido(
        numero_pedido=numero_pedido, tipo=dados.tipo_pedido, fornecedor_cliente=dados.fornecedor_cliente,
        centro_custo=centro, data_pedido=data_pedido, data_prevista=data_ref,
        observacao=f"Importado de {'Orçamento' if dados.origem_tipo == 'orcamento' else 'Planejamento financeiro'}",
        origem_tipo=dados.origem_tipo, origem_item_id=dados.origem_item_id,
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )
    session.add(pedido)
    session.commit()
    session.refresh(pedido)

    session.add(PedidoItem(
        pedido_id=pedido.id, tipo_item="produto", produto_servico=nomes.get(codigo, codigo),
        codigo_conta_gerencial=codigo, nome_conta_gerencial=nomes.get(codigo, codigo),
        valor_total_estimado=valor,
        fazenda_id=fazenda_id,
    ))
    session.commit()
    return {"id": pedido.id, "numero_pedido": numero_pedido}
