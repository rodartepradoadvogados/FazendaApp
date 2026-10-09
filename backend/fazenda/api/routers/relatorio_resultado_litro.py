"""
Resultado por litro — `GET /financeiro/resultado-por-litro` (Fase B do
redesenho dos Relatórios: "Quanto sobra de cada litro?"). Só LEITURA, arquivo
próprio no mesmo prefixo `/financeiro` (como relatorio_custo_hectare.py).

É uma agregação, não um cálculo novo: para cada período roda o MESMO motor da
DRE (`calcular_dre`, com a flag `financeiro_regras_v2` da fazenda, o regime e
o centro de custo pedidos) e reparte por litro — ver fazenda/rules/resultado_litro.py.
Com `serie_meses`, devolve também os N meses fechados que terminam no mês de
`data_fim` (o gráfico de 12 meses preço × custo).

Flag desligada: as linhas da DRE são as de antes da Fase A e os litros saem do
campo cru da entrega (como o custo por litro antigo); nenhum outro relatório
muda por causa deste endpoint.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import EntregaLeiteMensal, PlanoContaGerencial
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.custo_leite import litros_leite_no_periodo
from fazenda.rules.parametros import regras_v2_ativas
from fazenda.rules.resultado_litro import indicadores_por_litro, meses_da_serie, meses_no_periodo
from fazenda.rules.unidades import leite_em_litros

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


def _entregas(session: Session, fazenda_id: int | None, regras_v2: bool) -> tuple[dict[str, float], dict[str, set[str]]]:
    query = select(EntregaLeiteMensal)
    if fazenda_id is not None:
        query = query.where(EntregaLeiteMensal.fazenda_id == fazenda_id)
    por_comp: dict[str, float] = {}
    unidades: dict[str, set[str]] = {}
    for e in session.exec(query).all():
        qtd = e.quantidade_litros or 0.0
        # Regras v2 (PR 4): kg vira litro de verdade; sem a flag, o número cru (como o custo por litro antigo).
        valor = leite_em_litros(qtd, e.unidade) if regras_v2 else qtd
        por_comp[e.competencia] = por_comp.get(e.competencia, 0.0) + valor
        unidades.setdefault(e.competencia, set()).add("L" if (e.unidade or "kg").strip().upper() == "L" else "kg")
    return por_comp, unidades


def _periodo(session, fazenda_id, ini, fim, centro_custo, regime, regras_v2, entregas, codigos_receita, codigos_custo) -> dict:
    # Import tardio: financeiro.py é o dono do motor da DRE (e importa muita coisa).
    from fazenda.api.routers.financeiro import calcular_dre, leite_e_alimentacao_por_registros

    dre = calcular_dre(session, fazenda_id, ini, fim, centro_custo, regime, regras_v2=regras_v2)
    linhas = {linha["chave"]: linha["valor"] for linha in dre["cascata"]}
    leite = leite_e_alimentacao_por_registros(dre.get("_registros") or [], codigos_receita, codigos_custo)
    litros = litros_leite_no_periodo(entregas, ini, fim)
    ind = indicadores_por_litro(linhas=linhas, leite=leite, litros=litros, meses=meses_no_periodo(ini, fim))
    ind["nao_classificado"] = round(dre["nao_classificado"].get("total", 0.0), 2) + 0.0
    return ind


@router.get("/resultado-por-litro")
def resultado_por_litro(
    data_inicio: date = Query(..., description="Data inicial"),
    data_fim: date = Query(..., description="Data final"),
    regime: str = Query("competencia", description="'competencia' ou 'caixa' (o mesmo da DRE)"),
    centro_custo: str | None = Query(None),
    serie_meses: int = Query(0, ge=0, le=24, description="Meses fechados da série, terminando no mês de data_fim"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Preço médio do leite, COE/L, COT/L, margem por litro (R$ e %) e ponto
    de equilíbrio do período — e, com `serie_meses`, os mesmos números mês a
    mês. Os custos são as linhas da DRE do servidor (mesmo regime e centro);
    a receita do leite e a alimentação são as contas marcadas para o RMCA."""
    if data_fim < data_inicio:
        raise HTTPException(status_code=422, detail="A data final é anterior à inicial.")
    if regime not in ("competencia", "caixa"):
        raise HTTPException(status_code=422, detail="Regime deve ser 'competencia' ou 'caixa'.")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    regras_v2 = regras_v2_ativas(session, fazenda_id)

    query_plano = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_plano = query_plano.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    plano = session.exec(query_plano).all()
    codigos_receita = {c.codigo for c in plano if c.rmca_receita_leite}
    codigos_custo = {c.codigo for c in plano if c.rmca_custo_alimentacao}
    entregas, unidades_por_comp = _entregas(session, fazenda_id, regras_v2)

    def calc(ini: date, fim: date) -> dict:
        return _periodo(session, fazenda_id, ini, fim, centro_custo, regime, regras_v2, entregas, codigos_receita, codigos_custo)

    atual = calc(data_inicio, data_fim)
    serie = [{"competencia": f"{ini:%Y-%m}", **calc(ini, fim)} for ini, fim in meses_da_serie(data_fim, serie_meses)]

    # Aviso de kg só quando a conversão mexeu num mês mostrado (período ou série).
    comp_ini = min([f"{data_inicio:%Y-%m}"] + [m["competencia"] for m in serie])
    comp_fim = f"{data_fim:%Y-%m}"
    unidades = set().union(*[u for c, u in unidades_por_comp.items() if comp_ini <= c <= comp_fim]) if unidades_por_comp else set()
    avisos: list[str] = []
    if regras_v2 and "kg" in unidades:
        avisos.append("A entrega de leite lançada em kg foi convertida para litros (1 L = 1,029 kg).")
    if not regras_v2 and "kg" in unidades:
        avisos.append("Entregas lançadas em kg contam como litros enquanto as regras novas dos relatórios estiverem desligadas.")
    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "regime": regime,
        "centro_custo": centro_custo,
        "regras_v2": regras_v2,
        "configuracao": {
            "contas_leite": sorted(c.nome for c in plano if c.codigo in codigos_receita),
            "contas_alimentacao": sorted(c.nome for c in plano if c.codigo in codigos_custo),
            "tem_entrega": bool(entregas),
        },
        "atual": atual,
        "serie": serie,
        "avisos": avisos,
    }
