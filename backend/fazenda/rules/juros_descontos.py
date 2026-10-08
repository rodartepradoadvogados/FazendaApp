"""
Juros e descontos da BAIXA e desconto da NOTA de receita — regras v2 dos
relatórios do Financeiro (Fase A, PR 7 e PR 4; ver docs/financeiro-regras-v2.md).

Funções puras (sem Session): quem busca as contas e monta os registros da DRE é
o router (`financeiro._registros_dre_para_cascata` / `_registros_diferenca_baixa`).
Só valem com a flag `financeiro_regras_v2` da fazenda — desligada, nada daqui é
chamado e os relatórios saem como antes.

1. Diferença da baixa (`ContaGerencial.desconto_acrescimo` = valor_pago −
   valor_total, gravada por `pagar_lancamento`, pela baixa em lote detalhada,
   pela fatura de fornecedor e por `criar_lancamento` quando já nasce pago).
   Decisão do dono/contador (Q1):
     - padrão `financeiro`: a linha da conta continua com o valor CONTRATADO e a
       diferença vira um registro próprio em OUTRAS_REC_DESP, datado na
       `data_pagamento` (o fato gerador do juro/desconto é a baixa), nos DOIS
       regimes. No caixa, linha + Outras = valor_pago (fecha com o Fluxo);
     - `abatimento` (escolhido na baixa): o desconto reduz o custo/receita da
       própria conta — a parcela passa a valer o pago e nada vai para Outras.
   A baixa PARCIAL com reparcelamento grava `desconto_acrescimo = 0` (a
   diferença virou parcela nova): não gera nada aqui — regra de
   rules/vale_item.py::_base_gerencial, intocada.
   Pago SEM `valor_pago` (dado legado/bug corrigido no PR 6: grava
   `desconto_acrescimo = −valor`) não é desconto nenhum: é ignorado.

2. Desconto da nota de RECEITA (`ContaGerencial.desconto_nota`): Funrural/Senar
   retido e desconto comercial do laticínio. Decisão (Q6): DEDUÇÃO da receita.
   O item entra BRUTO em Receita de vendas e o desconto entra em
   DEDUCAO_IMPOSTOS — a receita líquida não muda. Na nota de DESPESA o desconto
   continua rateado nos itens (é o custo efetivo), como sempre foi.
"""
from __future__ import annotations

DIFERENCA_FINANCEIRA = "financeiro"
DIFERENCA_ABATIMENTO = "abatimento"
TIPOS_DIFERENCA = (DIFERENCA_FINANCEIRA, DIFERENCA_ABATIMENTO)

# Pseudocontas (não existem no plano): (codigo, rótulo, tipo do registro).
JUROS_PAGOS = ("(juros e multas pagos)", "Juros e multas pagos na baixa", "despesa")
DESCONTOS_OBTIDOS = ("(descontos obtidos)", "Descontos obtidos na baixa", "receita")
JUROS_RECEBIDOS = ("(juros recebidos)", "Juros e multas recebidos na baixa", "receita")
DESCONTOS_CONCEDIDOS = ("(descontos concedidos)", "Descontos concedidos na baixa", "despesa")
DEDUCAO_NOTA_RECEITA = ("(descontos na nota de venda)", "Funrural/Senar e descontos na nota de venda")

ORIGEM_DIFERENCA_BAIXA = "diferenca_baixa"
ORIGEM_DEDUCAO_NOTA = "deducao_nota"


def normalizar_tipo_diferenca(valor: str | None) -> str | None:
    """None/'' → None (= financeiro, o padrão). Valor fora da lista → ValueError."""
    if valor is None or not str(valor).strip():
        return None
    v = str(valor).strip().lower()
    if v not in TIPOS_DIFERENCA:
        raise ValueError(f"natureza_diferenca inválida: {valor!r} (use 'financeiro' ou 'abatimento')")
    return None if v == DIFERENCA_FINANCEIRA else v


def diferenca_da_baixa(conta) -> float:
    """Diferença REAL apurada na baixa (valor_pago − valor_total), ou 0.0 quando
    não há: conta em aberto, baixa parcial reparcelada (gravada 0), pago sem
    `valor_pago` (dado legado — não é desconto) ou `valor_pago` ≤ 0."""
    if getattr(conta, "data_pagamento", None) is None:
        return 0.0
    pago = getattr(conta, "valor_pago", None)
    if pago is None or pago <= 0:
        return 0.0
    return round(getattr(conta, "desconto_acrescimo", None) or 0.0, 2)


def eh_abatimento(conta) -> bool:
    return (getattr(conta, "diferenca_tipo", None) or None) == DIFERENCA_ABATIMENTO


def diferenca_abatida(conta) -> float:
    """Quanto a baixa ABATE do valor da própria conta (sempre ≤ 0: abatimento só
    existe para desconto). 0.0 quando a diferença é financeira."""
    d = diferenca_da_baixa(conta)
    return d if d < 0 and eh_abatimento(conta) else 0.0


def diferenca_financeira(conta) -> float:
    """A diferença que vai para Outras receitas e despesas (com sinal: > 0
    acréscimo, < 0 desconto). 0.0 quando abatida ou inexistente."""
    d = diferenca_da_baixa(conta)
    if not d or (d < 0 and eh_abatimento(conta)):
        return 0.0
    return d


def pseudoconta_da_diferenca(tipo_nota: str | None, diferenca: float) -> tuple[str, str, str]:
    """(codigo, rótulo, tipo do registro) da diferença financeira. Na nota de
    despesa: pagou a mais = juros/multa (despesa), a menos = desconto obtido
    (receita). Na de receita, o inverso."""
    if (tipo_nota or "despesa") == "receita":
        return JUROS_RECEBIDOS if diferenca > 0 else DESCONTOS_CONCEDIDOS
    return JUROS_PAGOS if diferenca > 0 else DESCONTOS_OBTIDOS


def fator_bruto_da_receita(bruto_itens: float, desconto_nota: float | None, acrescimo_nota: float | None) -> float | None:
    """Fator que leva o valor gerencial (LÍQUIDO) de uma parcela de nota de
    receita ao valor BRUTO de antes do desconto da nota:
    (líquido + desconto) / líquido, com líquido = bruto − desconto + acréscimo.
    None quando não há desconto ou a conta não fecha (líquido ≤ 0) — aí a
    parcela segue líquida, como sempre. O acréscimo da nota continua rateado
    nos itens (não é dedução)."""
    desconto = round(desconto_nota or 0.0, 2)
    if desconto <= 0:
        return None
    liquido = round((bruto_itens or 0.0) - desconto + (acrescimo_nota or 0.0), 2)
    if liquido <= 0:
        return None
    return (liquido + desconto) / liquido
