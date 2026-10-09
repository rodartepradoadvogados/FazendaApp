"""
Relatórios › Leite (Fase C): `GET /financeiro/custos-leite` ("Quanto custa
meu litro?") e `GET /financeiro/rmca-vaca` ("Quanto sobra da comida por
vaca?"). Só LEITURA, arquivo próprio no prefixo `/financeiro` (como
relatorio_resultado_litro.py).

Nenhum número novo de custo nasce aqui:
- custos-leite = o Resultado por litro (mesma DRE do servidor, mesmo regime e
  centro; COE e depreciação com os numeradores únicos da Fase A) + as
  estimativas CNA/Embrapa que dependem de PARÂMETRO (família e capital — ver
  rules/relatorio_leite.py). Parâmetro em 0 = não informado: nada é inventado;
- rmca-vaca = o RMCA de GET /financeiro/rmca (gerencial e físico, mesma regra
  por flag) dividido pelas vacas em lactação × dias (Controle leiteiro), mês a
  mês, e uma estimativa por lote (controle × preço do leite; comida pelo
  consumo registrado por lote × preço do Estoque).

Flag `financeiro_regras_v2` desligada: os valores de base são os mesmos das
telas anteriores (o RMCA sai do mesmo `rmca_gerencial` com a regra antiga; o
Resultado por litro já respeita a flag).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Animal, ConsumoAlimento, ControleLeiteiro, Estoque, PlanoContaGerencial
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.custo_leite import litros_leite_no_periodo
from fazenda.rules.parametros import get_param, regras_v2_ativas
from fazenda.rules.relatorio_leite import (
    estimativas_custo_leite, media_ponderada_por_litro, rmca_por_vaca_dia, vaca_dias,
)
from fazenda.rules.resultado_litro import meses_da_serie
from fazenda.rules.unidades import leite_em_litros

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


def _validar(data_inicio: date, data_fim: date) -> None:
    if data_fim < data_inicio:
        raise HTTPException(status_code=422, detail="A data final é anterior à inicial.")


def parametros_custo_leite() -> dict:
    """Os parâmetros das estimativas (Parâmetros financeiros), já com o padrão."""
    return {
        "familia_mes": float(get_param("custo_remuneracao_familia_mensal", 0.0) or 0.0),
        "taxa_capital_aa": float(get_param("custo_taxa_retorno_capital", 6.0) or 0.0),
        "capital_rebanho": float(get_param("custo_capital_rebanho", 0.0) or 0.0),
        "capital_maquinas": float(get_param("custo_capital_maquinas", 0.0) or 0.0),
        "capital_terra": float(get_param("custo_capital_terra", 0.0) or 0.0),
    }


@router.get("/custos-leite")
def custos_do_leite(
    data_inicio: date = Query(...),
    data_fim: date = Query(...),
    regime: str = Query("competencia"),
    centro_custo: str | None = Query(None),
    serie_meses: int = Query(12, ge=0, le=24),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """COE/L, COT/L e CT/L (CNA/Embrapa) do período, a média ponderada dos
    últimos `serie_meses` meses e, em `litro`, a resposta INTEIRA de
    GET /financeiro/resultado-por-litro com os mesmos parâmetros (a tela
    reaproveita o gráfico preço × custo e as linhas comida/gente/outros)."""
    _validar(data_inicio, data_fim)
    # Import tardio: o motor da DRE mora em financeiro.py (importa muita coisa).
    from fazenda.api.routers.relatorio_resultado_litro import resultado_por_litro

    litro = resultado_por_litro(
        data_inicio=data_inicio, data_fim=data_fim, regime=regime, centro_custo=centro_custo,
        serie_meses=serie_meses, session=session, fazenda_id=fazenda_id,
    )
    a = litro["atual"]
    p = parametros_custo_leite()
    est = estimativas_custo_leite(
        coe=a["coe"], depreciacao=a["depreciacao"], litros=a["litros"], meses=a["meses"], **p,
    )
    serie = litro["serie"]
    media = {
        "meses": sum(1 for m in serie if (m.get("litros") or 0) > 0),
        "coe_l": media_ponderada_por_litro(serie, "coe"),
        "cot_l": media_ponderada_por_litro(serie, "cot"),
        "preco_liquido_l": media_ponderada_por_litro(serie, "receita_leite_liquida"),
    }
    # Regras antigas: a comida por litro da tela anterior (GET /financeiro/custo-litro-leite)
    # é outro número (itens crus ÷ litros) — a tela mostra ESTE, nunca um novo.
    alimentacao_antiga = None
    if not litro["regras_v2"]:
        from fazenda.api.routers.financeiro import calcular_custo_litro_leite

        alimentacao_antiga = calcular_custo_litro_leite(session, fazenda_id_seguro(fazenda_id), data_inicio, data_fim, regras_v2=False)
    return {
        "periodo": litro["periodo"], "regime": litro["regime"], "centro_custo": litro["centro_custo"],
        "regras_v2": litro["regras_v2"],
        "alimentacao_tela_anterior": alimentacao_antiga,
        "litro": litro,
        "estimativas": est,
        "media_serie": media,
    }


# ---------------------------------------------------------------------------
# RMCA por vaca/dia
# ---------------------------------------------------------------------------
def _controles(session: Session, fazenda_id: int | None, ini: date, fim: date) -> list[ControleLeiteiro]:
    query = select(ControleLeiteiro).where(ControleLeiteiro.data_controle >= ini, ControleLeiteiro.data_controle <= fim)
    if fazenda_id is not None:
        query = query.where(ControleLeiteiro.fazenda_id == fazenda_id)
    return list(session.exec(query).all())


def _entregas(session: Session, fazenda_id: int | None, regras_v2: bool) -> dict[str, float]:
    from fazenda.models import EntregaLeiteMensal

    query = select(EntregaLeiteMensal)
    if fazenda_id is not None:
        query = query.where(EntregaLeiteMensal.fazenda_id == fazenda_id)
    out: dict[str, float] = {}
    for e in session.exec(query).all():
        qtd = e.quantidade_litros or 0.0
        out[e.competencia] = out.get(e.competencia, 0.0) + (leite_em_litros(qtd, e.unidade) if regras_v2 else qtd)
    return out


def _lote_do_animal(grupo: str | None) -> str:
    return (grupo or "").strip() or "Sem lote"


def _comida_por_lote(session: Session, fazenda_id: int | None, ini: date, fim: date) -> dict[int, dict]:
    """{lote (int, como na Alimentação): {custo, kg, sem_preco_kg}} do consumo
    REGISTRADO por lote no período × preço por kg do item no Estoque (o mesmo
    `_preco_por_kg` do simulador do RMCA). Alimento sem preço não vira zero:
    fica em `sem_preco_kg`."""
    from fazenda.api.routers.financeiro import _preco_por_kg

    query = select(ConsumoAlimento).where(ConsumoAlimento.data >= ini, ConsumoAlimento.data <= fim)
    query_estoque = select(Estoque)
    if fazenda_id is not None:
        query = query.where(ConsumoAlimento.fazenda_id == fazenda_id)
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)
    estoque_por_nome = {e.nome: e.model_dump() for e in session.exec(query_estoque).all()}
    out: dict[int, dict] = {}
    for c in session.exec(query).all():
        acc = out.setdefault(c.lote, {"custo": 0.0, "kg": 0.0, "sem_preco_kg": 0.0})
        kg = c.quantidade or 0.0
        if (c.unidade or "kg").strip().lower() not in ("kg", "quilo", "quilos"):
            acc["sem_preco_kg"] += kg
            continue
        item = estoque_por_nome.get(c.alimento)
        preco = _preco_por_kg(item, (item or {}).get("valor_unitario")) if item else None
        if preco is None:
            acc["sem_preco_kg"] += kg
            continue
        acc["kg"] += kg
        acc["custo"] += kg * preco
    return out


def _numero_lote(grupo: str) -> int | None:
    """"01 - Alta produção" → 1 (a ponte entre Animal.grupo_primario e o lote
    int da Alimentação, como em `apresentacao_dieta`)."""
    cabeca = grupo.split("-", 1)[0].strip()
    return int(cabeca) if cabeca.isdigit() else None


@router.get("/rmca-vaca")
def rmca_por_vaca(
    data_inicio: date = Query(...),
    data_fim: date = Query(...),
    serie_meses: int = Query(12, ge=0, le=24),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """A sobra da comida (RMCA) total e por vaca em lactação por dia, a
    comida ÷ receita (%), 12 meses e a tabela por lote. A base (receita do
    leite e custo de alimentação, gerencial e físico) é a de
    GET /financeiro/rmca — chamada aqui, não recalculada."""
    _validar(data_inicio, data_fim)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    from fazenda.api.routers.financeiro import rmca as rmca_legado, rmca_gerencial

    base = rmca_legado(data_inicio=data_inicio, data_fim=data_fim, session=session, fazenda_id=fazenda_id)
    regras_v2 = regras_v2_ativas(session, fazenda_id)
    entregas = _entregas(session, fazenda_id, regras_v2)

    query_plano = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_plano = query_plano.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    plano = session.exec(query_plano).all()
    codigos_receita = {c.codigo for c in plano if c.rmca_receita_leite}
    codigos_custo = {c.codigo for c in plano if c.rmca_custo_alimentacao}

    serie_periodos = meses_da_serie(data_fim, serie_meses)
    ini_total = min([data_inicio] + [i for i, _ in serie_periodos])
    controles = _controles(session, fazenda_id, ini_total, data_fim)
    pares = [(c.numero_matriz, c.data_controle) for c in controles]

    def indicadores(ini: date, fim: date, g: dict) -> dict:
        vd = vaca_dias(pares, ini, fim)
        ind = rmca_por_vaca_dia(
            receita_bruta=g["receita_leite"], receita_liquida=g.get("receita_leite_liquida"),
            comida=g["custo_alimentacao"], vaca_dias_total=vd["vaca_dias"],
            litros=litros_leite_no_periodo(entregas, ini, fim),
        )
        return {**ind, **vd}

    g = base["gerencial"]
    atual = indicadores(data_inicio, data_fim, g)
    fisico_custo = base["fisico"]["custo_alimentacao"]
    fisico = rmca_por_vaca_dia(
        receita_bruta=g["receita_leite"], receita_liquida=g.get("receita_leite_liquida"), comida=fisico_custo,
        vaca_dias_total=atual["vaca_dias"], litros=atual["litros"] or 0.0,
    )
    serie = []
    for ini, fim in serie_periodos:
        gm = rmca_gerencial(session, fazenda_id, ini, fim, codigos_receita, codigos_custo, regras_v2=regras_v2)
        serie.append({"competencia": f"{ini:%Y-%m}", **indicadores(ini, fim, gm)})

    # ── Por lote (estimativa): vacas e leite do Controle leiteiro, preço médio
    # do leite do período, comida pelo consumo registrado por lote.
    query_animais = select(Animal)
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    lote_por_numero = {a.numero: _lote_do_animal(a.grupo_primario) for a in session.exec(query_animais).all()}
    no_periodo = [c for c in controles if c.data_controle and data_inicio <= c.data_controle <= data_fim]
    preco_bruto_l = (g["receita_leite"] / atual["litros"]) if atual["litros"] else None
    comida_lote = _comida_por_lote(session, fazenda_id, data_inicio, data_fim)
    grupos: dict[str, list[ControleLeiteiro]] = {}
    for c in no_periodo:
        grupos.setdefault(lote_por_numero.get(c.numero_matriz, "Sem lote"), []).append(c)
    por_lote = []
    for lote, cs in sorted(grupos.items()):
        vd = vaca_dias([(c.numero_matriz, c.data_controle) for c in cs], data_inicio, data_fim)
        pesagens = [c.producao_kg for c in cs if c.producao_kg]
        kg_dia = sum(pesagens) / len(pesagens) if pesagens else None
        litros_dia = (leite_em_litros(kg_dia, "kg") if regras_v2 else kg_dia) if kg_dia is not None else None
        receita_dia = litros_dia * preco_bruto_l if (litros_dia is not None and preco_bruto_l is not None) else None
        n = _numero_lote(lote)
        consumo = comida_lote.get(n) if n is not None else None
        comida_dia = consumo["custo"] / vd["vaca_dias"] if (consumo and consumo["kg"] > 0 and vd["vaca_dias"]) else None
        por_lote.append({
            "lote": lote, "vacas": vd["vacas"], "vacas_media": vd["vacas_media"], "vaca_dias": vd["vaca_dias"],
            "leite_l_vaca_dia": None if litros_dia is None else round(litros_dia, 2),
            "receita_vaca_dia": None if receita_dia is None else round(receita_dia, 4),
            "comida_vaca_dia": None if comida_dia is None else round(comida_dia, 4),
            "rmca_vaca_dia": round(receita_dia - comida_dia, 4) if (receita_dia is not None and comida_dia is not None) else None,
            "consumo_sem_preco_kg": round(consumo["sem_preco_kg"], 1) if consumo else 0.0,
        })

    avisos: list[str] = []
    if base["configurado"] and atual["vaca_dias"] == 0:
        avisos.append("Sem Controle leiteiro no período: não dá para dividir por vaca. O RMCA total continua valendo.")
    return {
        "periodo": base["periodo"],
        "regras_v2": regras_v2,
        "configurado": base["configurado"],
        "contas_receita": base["contas_receita"],
        "contas_custo": base["contas_custo"],
        # Códigos (drill para Consultas filtrada pela conta).
        "contas_receita_codigos": sorted(({"codigo": c.codigo, "nome": c.nome} for c in plano if c.codigo in codigos_receita), key=lambda x: x["codigo"]),
        "contas_custo_codigos": sorted(({"codigo": c.codigo, "nome": c.nome} for c in plano if c.codigo in codigos_custo), key=lambda x: x["codigo"]),
        "meta_rmca": base["meta_rmca"],
        "gerencial": base["gerencial"],
        "atual": atual,
        "fisico": {**fisico, "itens": base["fisico"]["itens"]},
        "preco_medio_litro_leite": base.get("preco_medio_litro_leite"),
        "serie": serie,
        "por_lote": por_lote,
        "preco_bruto_l": None if preco_bruto_l is None else round(preco_bruto_l, 4),
        "avisos": avisos,
    }
