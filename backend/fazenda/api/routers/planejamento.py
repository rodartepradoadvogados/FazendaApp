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

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    ContaGerencial, LancamentoItem, OrcamentoItem, Pedido, PedidoItem,
    PlanejamentoCenario, PlanejamentoItem, PlanoContaGerencial, Usuario,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.centro_custo import mapear_centro_custo
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
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

    query_itens = select(LancamentoItem).where(LancamentoItem.data_competencia >= data_ini, LancamentoItem.data_competencia <= data_fim)
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Cria um Pedido (rascunho) a partir de uma linha de Orçamento ou de
    Planejamento financeiro — só copia os dados, não lança nada em
    Financeiro/Estoque. O usuário completa e salva o pedido normalmente."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
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
