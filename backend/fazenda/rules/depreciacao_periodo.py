"""
Depreciação/amortização/exaustão DO PERÍODO (não a acumulada) — a ligação
entre Patrimônio e a DRE Gerencial em cascata (ver fazenda/rules/dre.py,
linha DEPRECIACAO_AMORT_EXAUSTAO).

Arquivo SEPARADO de fazenda/rules/patrimonio.py de propósito: outro agente
mexe em patrimonio.py na mesma janela de tempo, corrigindo erros de cálculo
da depreciação acumulada — para não colidir, este módulo só IMPORTA
`calcular_depreciacao` de lá (sem alterá-lo) e resolve "depreciação do
período" por fora, como uma diferença de dois instantes.

===========================================================================
ATENÇÃO — depreciação (aqui) e principal de financiamento são OPOSTOS, não
parentes (ver o ADR completo no topo de fazenda/rules/dre.py): depreciação é
despesa que não sai do caixa e por isso TEM linha própria na DRE; principal
de financiamento é caixa que sai mas NÃO é despesa nenhuma, e por isso NUNCA
aparece aqui nem em lugar nenhum da DRE (só o juros, que é lançamento
financeiro normal, não patrimônio). Este módulo só enxerga `Patrimonio` —
nunca teria como calcular principal de financiamento mesmo que quisesse.
===========================================================================

Cálculo: depreciação do período = acumulada até `data_fim` menos acumulada
até o dia anterior a `data_inicio` — ambas via `calcular_depreciacao`
(linha reta), respeitando as mesmas regras de lá: bem não depreciável nunca
entra; bem baixado para de depreciar na data da baixa; bem com inconsistência
(vida útil não reconhecida / sem data de imobilização) não entra e é
reportado à parte, para o usuário saber que a linha está subestimada.

Ressalva sobre baixa DENTRO do período: `calcular_depreciacao` trata
`data_baixa` como estado final independente do `hoje` recebido (ver
docstring de lá) — então, para reconstituir corretamente o valor num
instante ANTERIOR à baixa, calculamos esse instante sobre uma cópia do item
com `data_baixa` temporariamente removida (ver `_acumulada_no_instante`).
Isso é só uma reconstrução aritmética local a este módulo; não altera
`patrimonio.py` nem o dado gravado.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.patrimonio import calcular_depreciacao


def _acumulada_no_instante(item: dict, data_ref: date) -> tuple[float | None, str | None]:
    """Depreciação acumulada TÉCNICA do item em `data_ref`, ignorando uma
    baixa que ainda não tinha acontecido naquela data. Necessário porque
    `calcular_depreciacao(item, hoje)` ignora `hoje` inteiramente quando
    `item["data_baixa"]` está preenchido (sempre devolve o valor final da
    baixa) — sem este ajuste, consultar um instante ANTERIOR a uma baixa que
    caiu dentro do período faria a acumulada parecer travada cedo demais.
    Devolve (acumulada, inconsistencia)."""
    data_baixa = item.get("data_baixa")
    if data_baixa and data_baixa > data_ref:
        item_ainda_sem_baixa = {**item, "data_baixa": None}
        resultado = calcular_depreciacao(item_ainda_sem_baixa, data_ref)
    else:
        resultado = calcular_depreciacao(item, data_ref)
    return resultado["depreciacao_acumulada"], resultado["inconsistencia"]


def calcular_depreciacao_periodo(itens: list[dict], data_inicio: date, data_fim: date) -> dict:
    """Recebe uma lista de dicts de Patrimonio (model_dump()) e devolve a
    depreciação DO PERÍODO [data_inicio, data_fim] (inclusive nas duas
    pontas), pronta para a linha DEPRECIACAO_AMORT_EXAUSTAO da DRE.

    Devolve:
        {"total": float,
         "itens": [{"patrimonio_id", "nome", "valor"}, ...],   # só quem contribuiu (valor > 0)
         "inconsistencias": [{"item", "numero", "motivo"}, ...]}

    Bem não depreciável (`depreciavel=False`, ex.: terra): nunca entra —
    só valoriza, não deprecia (ver rules/patrimonio.py). Bem baixado ANTES
    do período: contribuição zero (já tinha parado de depreciar). Bem com
    inconsistência (vida útil não reconhecida / sem data de imobilização):
    não entra e é reportado à parte — a linha fica subestimada, não errada
    por adivinhação."""
    um_dia = timedelta(days=1)
    total = 0.0
    detalhes: list[dict] = []
    inconsistencias: list[dict] = []

    for item in itens:
        nome = item.get("nome")
        numero = item.get("numero")

        if item.get("depreciavel") is False:
            continue  # só valoriza — nunca deprecia, nunca entra na DRE

        data_baixa = item.get("data_baixa")
        if data_baixa and data_baixa < data_inicio:
            continue  # já tinha parado de depreciar antes do período — contribuição zero, não é inconsistência

        acumulada_fim, inconsistencia_fim = _acumulada_no_instante(item, data_fim)
        acumulada_inicio, inconsistencia_inicio = _acumulada_no_instante(item, data_inicio - um_dia)
        inconsistencia = inconsistencia_fim or inconsistencia_inicio
        if inconsistencia or acumulada_fim is None or acumulada_inicio is None:
            inconsistencias.append({"item": nome, "numero": numero, "motivo": inconsistencia})
            continue

        delta = round(acumulada_fim - acumulada_inicio, 2)
        if delta <= 0:
            continue
        total = round(total + delta, 2)
        detalhes.append({"patrimonio_id": item.get("id"), "nome": nome, "valor": delta})

    return {"total": total, "itens": detalhes, "inconsistencias": inconsistencias}
