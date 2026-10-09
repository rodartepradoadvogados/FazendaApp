"""
Resultado por litro — motor PURO (sem Session) do relatório "Quanto sobra de
cada litro?" (Financeiro › Relatórios › Resultado, Fase B do redesenho).

Não inventa número novo: reparte por litro o que a DRE do servidor já mostra
(a cascata de `GET /financeiro/dre`, a mesma da aba DRE, da Capa e do e-mail
do Portal) e as contas do leite/alimentação que o RMCA já usa. Quem busca no
banco é o router (fazenda/api/routers/relatorio_resultado_litro.py).

Definições (metodologia CNA/Embrapa, simplificada — ver docs/financeiro-regras-v2.md):

- preço bruto do leite = receita das contas marcadas "receita do leite" ÷ litros;
  preço líquido = (receita − Funrural/Senar e descontos da nota de venda) ÷ litros
  (sem as regras v2 não há dedução separada: líquido = bruto);
- COE (custo operacional efetivo, o "custeio") = as linhas de custo da cascata
  ANTES da depreciação: custo variável + despesas variáveis + pessoal +
  despesas operacionais. É a receita líquida menos o EBITDA, mas lido linha a
  linha (outras receitas, como venda de animais, não abatem o custo);
- COT (custo operacional total) = COE + depreciação do período (a mesma linha
  da DRE). Pró-labore e remuneração do capital (CT) ficam para depois — não há
  parâmetro para eles ainda;
- margem por litro = preço líquido − COE/L; margem sobre a receita do leite (%)
  = (receita líquida do leite − COE) ÷ receita líquida do leite;
- ponto de equilíbrio (ESTIMATIVA): custos fixos ÷ (preço líquido − custo
  variável por litro), com variável = custo variável + despesas variáveis e
  fixo = pessoal + despesas operacionais + depreciação (é a leitura da própria
  cascata, que já separa variável de fixo).

Tudo None quando falta o divisor (sem litros ou sem receita): a tela mostra o
que falta configurar em vez de um número inventado.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from fazenda.rules.dre import (
    CUSTO_VARIAVEL,
    DEPRECIACAO_AMORT_EXAUSTAO,
    DESPESA_VARIAVEL,
    DESPESAS_OPERACIONAIS,
    GASTOS_PESSOAL,
    RECEITA_LIQUIDA,
    RESULTADO_LIQUIDO,
)


def _r(v: float | None, casas: int = 2) -> float | None:
    return None if v is None else round(v, casas) + 0.0


def meses_no_periodo(ini: date, fim: date) -> float:
    """Quantos meses o período cobre, em fração de mês por dia (jan inteiro =
    1; de 1 a 15 de abril = 0,5). Base do ponto de equilíbrio "por mês"."""
    if fim < ini:
        return 0.0
    total = 0.0
    d = ini
    while d <= fim:
        dias_mes = calendar.monthrange(d.year, d.month)[1]
        ultimo = date(d.year, d.month, dias_mes)
        ate = min(ultimo, fim)
        total += ((ate - d).days + 1) / dias_mes
        d = ate + timedelta(days=1)
    return round(total, 4)


def meses_da_serie(fim: date, quantidade: int) -> list[tuple[date, date]]:
    """Os `quantidade` meses fechados que terminam no mês de `fim` (o mais
    antigo primeiro) — a série de 12 meses do gráfico."""
    out: list[tuple[date, date]] = []
    ano, mes = fim.year, fim.month
    for _ in range(max(0, quantidade)):
        ini = date(ano, mes, 1)
        out.append((ini, date(ano, mes, calendar.monthrange(ano, mes)[1])))
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    return list(reversed(out))


def indicadores_por_litro(*, linhas: dict[str, float], leite: dict, litros: float, meses: float) -> dict:
    """`linhas`: valor de cada linha da cascata da DRE, pela chave (as linhas
    de custo vêm em magnitude positiva — ver rules/dre.py). `leite`: retorno de
    `leite_e_alimentacao_por_registros` (receita do leite, deduções, custo com
    alimentação). `litros`: litros entregues no período (já convertidos de kg
    quando a fazenda usa as regras v2). `meses`: ver `meses_no_periodo`."""
    custo_variavel = linhas.get(CUSTO_VARIAVEL, 0.0) + linhas.get(DESPESA_VARIAVEL, 0.0)
    pessoal = linhas.get(GASTOS_PESSOAL, 0.0)
    operacionais = linhas.get(DESPESAS_OPERACIONAIS, 0.0)
    depreciacao = linhas.get(DEPRECIACAO_AMORT_EXAUSTAO, 0.0)
    coe = custo_variavel + pessoal + operacionais
    cot = coe + depreciacao
    fixo = pessoal + operacionais + depreciacao

    receita_bruta = leite.get("receita_leite", 0.0) or 0.0
    deducoes = leite.get("deducoes_receita_leite", 0.0) or 0.0
    receita_liquida = leite.get("receita_leite_liquida", receita_bruta - deducoes)
    if receita_liquida is None:
        receita_liquida = receita_bruta - deducoes
    comida = leite.get("custo_alimentacao", 0.0) or 0.0
    outros = coe - comida - pessoal

    tem_litros = litros > 0
    por_l = (lambda v: v / litros) if tem_litros else (lambda v: None)
    preco_liq = por_l(receita_liquida)
    coe_l = por_l(coe)
    cot_l = por_l(cot)
    variavel_l = por_l(custo_variavel)

    ponto = None
    if tem_litros and preco_liq is not None and variavel_l is not None:
        contribuicao = preco_liq - variavel_l
        if contribuicao > 0:
            litros_pe = fixo / contribuicao
            ponto = {
                "litros_periodo": _r(litros_pe, 0),
                "litros_mes": _r(litros_pe / meses, 0) if meses > 0 else None,
                "receita_periodo": _r(litros_pe * preco_liq),
                "folga_pct": _r(100 * (litros / litros_pe - 1), 1) if litros_pe > 0 else None,
                "contribuicao_por_litro": _r(contribuicao, 4),
            }

    return {
        "litros": _r(litros, 1),
        "litros_mes": _r(litros / meses, 0) if meses > 0 else None,
        "meses": meses,
        "receita_leite_bruta": _r(receita_bruta),
        "deducoes_leite": _r(deducoes),
        "receita_leite_liquida": _r(receita_liquida),
        "comida": _r(comida),
        "pessoal": _r(pessoal),
        "outros_custeio": _r(outros),
        "custo_variavel": _r(custo_variavel),
        "custo_fixo": _r(fixo),
        "coe": _r(coe),
        "depreciacao": _r(depreciacao),
        "cot": _r(cot),
        "preco_bruto_l": _r(por_l(receita_bruta), 4),
        "preco_liquido_l": _r(preco_liq, 4),
        "comida_l": _r(por_l(comida), 4),
        "pessoal_l": _r(por_l(pessoal), 4),
        "outros_l": _r(por_l(outros), 4),
        "coe_l": _r(coe_l, 4),
        "depreciacao_l": _r(por_l(depreciacao), 4),
        "cot_l": _r(cot_l, 4),
        "margem_l": _r(preco_liq - coe_l, 4) if preco_liq is not None and coe_l is not None else None,
        "margem_cot_l": _r(preco_liq - cot_l, 4) if preco_liq is not None and cot_l is not None else None,
        "margem_pct": _r(100 * (receita_liquida - coe) / receita_liquida, 1) if receita_liquida > 0 else None,
        "ponto_equilibrio": ponto,
        # Para conferência com a DRE (o resultado é o MESMO da aba DRE).
        "receita_liquida_dre": _r(linhas.get(RECEITA_LIQUIDA, 0.0)),
        "resultado_liquido_dre": _r(linhas.get(RESULTADO_LIQUIDO, 0.0)),
    }
