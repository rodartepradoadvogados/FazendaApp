"""
Réguas de referência — o NÚMERO DA FAZENDA de cada régua (motor PURO, sem Session).

A tela de Réguas (Financeiro › Relatórios › Leite) põe o indicador da fazenda ao
lado da faixa. Esse indicador não é conta nova: sai dos MESMOS números que os
relatórios do servidor já mostram para o mesmo período, regime e centro —
a cascata da DRE (`calcular_dre`), o Resultado por litro
(`rules/resultado_litro.indicadores_por_litro`, que usa as contas do RMCA para a
receita do leite e a comida) e o saldo de hoje do Caixa real. Quem busca no banco
é o router (`api/routers/reguas_referencia.py`, rota `/indicadores-fazenda`).

Cada régua devolve `valor` (None quando falta o divisor ou o dado) com a conta
escrita (`conta`, os dois números em R$) e o relatório que explica o número
(`relatorio`, id da árvore de Relatórios do front), ou o `motivo` de não haver
número. Nada aqui depende das faixas: o número da fazenda aparece mesmo quando a
régua está em validação, retirada, vencida ou sem faixa.
"""
from __future__ import annotations

from typing import Any, Optional

from fazenda.rules.dre import RECEITA_VENDAS

# Ids da árvore de Relatórios do front (frontend/lib/relatoriosNavegacao.ts).
REL_LITRO = "rel_litro"
REL_DRE = "rel_dre"
REL_RMCA = "rmca"
REL_CAIXA = "rel_caixa"  # Fase C1: o Caixa real no molde (o id antigo "caixa_real" só redireciona)

MOTIVOS_SEM_DADO = {
    "concentrado_receita": "O plano de contas ainda não separa o concentrado do resto da comida.",
    "lactacao_vacas": "Esta tela ainda não lê o rebanho (vacas em lactação e secas).",
    "lactacao_rebanho": "Esta tela ainda não lê o rebanho (vacas em lactação e total de animais).",
    "parcelas_receita": "As parcelas de financiamento (principal e juros) ainda não são separadas nos relatórios.",
    "cobertura_divida": "O serviço da dívida (principal e juros) ainda não é separado nos relatórios.",
    "litros_pessoa_dia": "Falta informar quantas pessoas trabalham na atividade leiteira.",
    "litros_ha_ano": "Falta informar a área (hectares) da atividade leiteira.",
}


def _brl(v: float) -> str:
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'−' if v < 0 else ''}R$ {s}"


def _litros(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def _r(v: Optional[float], casas: int) -> Optional[float]:
    return None if v is None else round(v, casas) + 0.0


def _item(valor: Optional[float], casas: int, *, conta: Optional[str] = None, relatorio: Optional[str] = None,
          motivo: Optional[str] = None) -> dict[str, Any]:
    if valor is None:
        return {"valor": None, "conta": None, "relatorio": relatorio, "motivo": motivo or "Sem dado no período."}
    return {"valor": _r(valor, casas), "conta": conta, "relatorio": relatorio, "motivo": None}


def indicadores_da_fazenda(
    *, litro: dict[str, Any], linhas: dict[str, float], saldo_caixa: Optional[float] = None,
    motivo_saldo: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """`litro`: retorno de `indicadores_por_litro` do período. `linhas`: valor de
    cada linha da cascata da DRE do MESMO período (custo em magnitude positiva).
    `saldo_caixa`: saldo de hoje do Caixa real (None quando a pessoa não pode ver
    o caixa; `motivo_saldo` diz por quê)."""
    receita_bruta = linhas.get(RECEITA_VENDAS, 0.0) or 0.0
    receita_leite = litro.get("receita_leite_bruta") or 0.0
    comida = litro.get("comida") or 0.0
    coe = litro.get("coe") or 0.0
    cot = litro.get("cot") or 0.0
    pessoal = litro.get("pessoal") or 0.0
    depreciacao = litro.get("depreciacao") or 0.0
    meses = litro.get("meses") or 0.0

    out: dict[str, dict[str, Any]] = {}
    out["comida_receita"] = _item(
        100 * comida / receita_leite if receita_leite > 0 else None, 1,
        conta=f"Alimentação {_brl(comida)} ÷ receita do leite {_brl(receita_leite)}",
        relatorio=REL_RMCA, motivo="Sem receita do leite no período (contas do leite marcadas e venda lançada).",
    )
    out["coe_receita"] = _item(
        100 * coe / receita_bruta if receita_bruta > 0 else None, 1,
        conta=f"Custeio (COE) {_brl(coe)} ÷ receita bruta {_brl(receita_bruta)}",
        relatorio=REL_DRE, motivo="Sem receita no período.",
    )
    out["mao_obra_receita"] = _item(
        100 * pessoal / receita_bruta if receita_bruta > 0 else None, 1,
        conta=f"Pessoal da DRE (folha e encargos) {_brl(pessoal)} ÷ receita bruta {_brl(receita_bruta)}",
        relatorio=REL_DRE, motivo="Sem receita no período.",
    )
    out["depreciacao_cot"] = _item(
        100 * depreciacao / cot if cot > 0 else None, 1,
        conta=f"Desgaste dos bens {_brl(depreciacao)} ÷ custo operacional total (COT) {_brl(cot)}",
        relatorio=REL_LITRO, motivo="Sem custo no período.",
    )
    out["coe_litro_reais"] = _item(
        litro.get("coe_l"), 4,
        conta=f"Custeio (COE) {_brl(coe)} ÷ {_litros(litro.get('litros') or 0.0)} L entregues",
        relatorio=REL_LITRO, motivo="Sem litros entregues no período.",
    )
    custeio_mes = coe / meses if meses > 0 else 0.0
    if saldo_caixa is None:
        out["reserva_caixa"] = _item(None, 1, relatorio=REL_CAIXA, motivo=motivo_saldo or "Sem saldo de caixa.")
    else:
        out["reserva_caixa"] = _item(
            saldo_caixa / custeio_mes if custeio_mes > 0 else None, 1,
            conta=f"Saldo de caixa de hoje {_brl(saldo_caixa)} ÷ custeio médio por mês no período {_brl(custeio_mes)}",
            relatorio=REL_CAIXA, motivo="Sem custeio no período.",
        )
    for codigo, motivo in MOTIVOS_SEM_DADO.items():
        out[codigo] = _item(None, 1, motivo=motivo)
    return out
