"""
Litros do leite mês a mês — PURO (sem Session). Decisão do dono (T4): o cálculo
de Resultado por litro / custo por litro tem de ter por base a ENTRADA DE LEITE,
ou seja, a NOTA do laticínio lançada em Financeiro (receita). A "Venda mensal do
leite" (`EntregaLeiteMensal`) passa a ser só RESERVA gerencial, para os meses
SEM nota — e a tela avisa "estimado, sem nota".

Por mês (competência "AAAA-MM"), a prioridade é:

1. `nota`          — a nota do laticínio tem litros válidos (quantidade + unidade
                      resolvida) e nenhum item de leite do mês ficou de fora da conta;
2. `venda_mensal`  — não há nota utilizável e há Venda mensal (> 0): o litro é
                      ESTIMADO;
3. `sem_dado`      — nenhum dos dois: 0 litro, e a tela ensina o que lançar.

Mês com item de leite SEM unidade (ou sem quantidade) é `nota_incompleta`: os
litros parciais da nota NÃO valem (a receita do mês tem o item inteiro; dividir
por litros incompletos inflaria o preço), então o mês cai na reserva — ou fica
`sem_dado` — e quem coleta os dados avisa qual nota está incompleta.

Quem busca no banco é `fazenda/rules/litros_leite_nota.py`; este módulo só decide.
Só vale com a flag `financeiro_regras_v2` ligada: desligada, os relatórios seguem
lendo `EntregaLeiteMensal` cru, como antes (golden).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Collection, Iterable, Mapping

from fazenda.rules.custo_leite import _dias_por_mes_no_periodo

FONTE_NOTA = "nota"
FONTE_VENDA_MENSAL = "venda_mensal"
FONTE_SEM_DADO = "sem_dado"
# Só no resumo de um período com mais de um mês e fontes diferentes.
FONTE_MISTA = "mista"
FONTES = (FONTE_NOTA, FONTE_VENDA_MENSAL, FONTE_SEM_DADO)


@dataclass(frozen=True)
class LitrosMes:
    """Litros de UMA competência (mês inteiro) e de onde vieram."""

    competencia: str
    litros: float
    fonte: str
    litros_nota: float = 0.0  # o que a nota deu (mesmo quando não valeu, p/ conferência)
    litros_venda_mensal: float = 0.0  # a reserva do mês (0 = sem Venda mensal)
    nota_incompleta: bool = False


def litros_do_leite(
    competencias: Iterable[str],
    *,
    litros_notas: Mapping[str, float],
    litros_venda_mensal: Mapping[str, float],
    meses_nota_incompleta: Collection[str] = (),
) -> dict[str, LitrosMes]:
    """Litros e fonte de cada competência pedida (nota > venda mensal > sem dado).

    `litros_notas`: litros por mês somando os itens de leite VÁLIDOS das notas.
    `litros_venda_mensal`: litros por mês da Venda mensal (já convertidos de kg).
    `meses_nota_incompleta`: meses com item de leite sem unidade/quantidade."""
    saida: dict[str, LitrosMes] = {}
    for comp in competencias:
        nota = float(litros_notas.get(comp, 0.0) or 0.0)
        venda = float(litros_venda_mensal.get(comp, 0.0) or 0.0)
        incompleta = comp in meses_nota_incompleta
        if nota > 0 and not incompleta:
            litros, fonte = nota, FONTE_NOTA
        elif venda > 0:
            litros, fonte = venda, FONTE_VENDA_MENSAL
        else:
            litros, fonte = 0.0, FONTE_SEM_DADO
        saida[comp] = LitrosMes(
            competencia=comp, litros=litros, fonte=fonte, litros_nota=nota, litros_venda_mensal=venda,
            nota_incompleta=incompleta,
        )
    return saida


def litros_no_periodo(meses: Mapping[str, LitrosMes], ini: date, fim: date) -> dict:
    """Litros do período `ini`..`fim`, mês a mês, com a MESMA projeção por dia de
    `custo_leite.litros_leite_no_periodo` (período parcial pega a fração dos dias
    do mês) — e de onde veio cada fatia.

    Devolve `litros` (total), `por_fonte` (litros de `nota` e de `venda_mensal`),
    `meses` (um item por mês tocado, na ordem: competência, fonte e litros DA
    FATIA do período), `fonte` (uma das FONTES, ou `mista` com mais de uma
    fonte com litros) e `pct_estimado` (parcela dos litros que veio da Venda
    mensal; None sem litros)."""
    total = 0.0
    por_fonte = {FONTE_NOTA: 0.0, FONTE_VENDA_MENSAL: 0.0}
    lista: list[dict] = []
    for (ano, mes), dias_no_periodo in _dias_por_mes_no_periodo(ini, fim).items():
        comp = f"{ano:04d}-{mes:02d}"
        m = meses.get(comp)
        if m is None or m.fonte == FONTE_SEM_DADO:
            lista.append({"competencia": comp, "fonte": FONTE_SEM_DADO, "litros": 0.0,
                          "nota_incompleta": bool(m and m.nota_incompleta)})
            continue
        fatia = m.litros / calendar.monthrange(ano, mes)[1] * dias_no_periodo
        total += fatia
        por_fonte[m.fonte] += fatia
        lista.append({"competencia": comp, "fonte": m.fonte, "litros": round(fatia, 1) + 0.0,
                      "nota_incompleta": m.nota_incompleta})
    com_litros = [f for f in (FONTE_NOTA, FONTE_VENDA_MENSAL) if por_fonte[f] > 0]
    if len(com_litros) > 1:
        fonte = FONTE_MISTA
    elif com_litros:
        fonte = com_litros[0]
    else:
        fonte = FONTE_SEM_DADO
    return {
        "litros": total,
        "por_fonte": por_fonte,
        "meses": lista,
        "fonte": fonte,
        "pct_estimado": round(100 * por_fonte[FONTE_VENDA_MENSAL] / total, 1) + 0.0 if total > 0 else None,
    }


def campos_fonte_para_api(resumo: dict) -> dict:
    """As chaves que a resposta dos relatórios acrescenta (SÓ com a flag
    ligada): `fonte_litros`, `litros_por_fonte`, `pct_litros_estimados` e
    `meses_litros` (a fonte de cada mês, para a tela marcar o "estimado")."""
    return {
        "fonte_litros": resumo["fonte"],
        "litros_por_fonte": {f: round(v, 1) + 0.0 for f, v in resumo["por_fonte"].items()},
        "pct_litros_estimados": resumo["pct_estimado"],
        "meses_litros": resumo["meses"],
    }
