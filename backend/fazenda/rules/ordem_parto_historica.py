"""
Ordem de parto de um controle leiteiro NA DATA EM QUE ELE FOI FEITO.

O problema que isto resolve: `ControleLeiteiro.ordem_parto` é lido em
`routers/producao.py` e escrito por NENHUMA das quatro vias de entrada
(lançamento manual, app de campo, importação de planilha, parser legado). A tela
cai então num atalho — `ordem = c.ordem_parto or partos_por_numero.get(numero)`
— em que `partos_por_numero` é a contagem TOTAL de partos do animal.

O efeito é silencioso e sistemático: uma vaca hoje de 5ª cria aparece com "5ª"
em TODOS os seus controles, inclusive nos de quando era primípara. Como o
equivalente maduro é, por definição, ajuste por idade e ordem de parto, qualquer
cálculo sobre esse histórico sai errado — e errado de um jeito que favorece
exatamente o erro que o indicador existe para impedir, porque joga a produção
baixa da primeira cria dentro da média das maduras.

A ponte óbvia não existe: `ControleLeiteiro.data_ult_parto` só é preenchido pelo
parser legado do CSV (`parsers/controle_leiteiro.py`) e fica nulo nas três vias
que o app usa hoje. Sobra casar por DATA — o parto mais recente ANTERIOR OU
IGUAL à data do controle —, e daí ler `Parto.ordem_parto`, que É populado por
três vias.

Funções puras, sem Session: a decisão fica testável sem banco, e o script de
reconstrução só empresta os dados.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PartoRef:
    """O mínimo que a regra precisa saber de um parto."""

    data_parto: date | None
    ordem_parto: int | None


def ordem_parto_na_data(partos: list[PartoRef], data_controle: date | None) -> int | None:
    """Ordem de parto vigente na data do controle, ou `None` quando não dá para
    saber.

    `None` é resposta legítima e tem três causas distintas, todas reais no
    histórico da fazenda: controle sem data; controle anterior ao primeiro parto
    registrado (o histórico de partos não vai tão longe quanto o de controles);
    e parto sem `ordem_parto` gravada. Em nenhum dos três casos existe resposta
    honesta — e inventar uma é justamente o que o código atual faz.

    Empate de data (parto e controle no mesmo dia) resolve A FAVOR do parto:
    a vaca pariu e já está na lactação nova, que é o que o controle mede.
    """
    if data_controle is None:
        return None
    candidatos = [
        p for p in partos
        if p.data_parto is not None and p.data_parto <= data_controle and p.ordem_parto is not None
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.data_parto).ordem_parto


def ordem_parto_pelo_atalho_atual(partos: list[PartoRef]) -> int | None:
    """O que a tela mostra HOJE: a contagem total de partos do animal, aplicada
    a todos os controles dele.

    Existe só para o relatório de comparação poder mostrar, lado a lado, o que
    se vê hoje e o que é verdade — e para os testes travarem a diferença em vez
    de descreverem-na em prosa."""
    return len(partos) or None


@dataclass(frozen=True)
class Divergencia:
    """Um controle cuja ordem exibida hoje não é a ordem real."""

    numero_matriz: str
    data_controle: date | None
    ordem_hoje: int | None
    ordem_correta: int | None


def divergencias_do_animal(
    numero_matriz: str,
    partos: list[PartoRef],
    datas_de_controle: list[date | None],
) -> list[Divergencia]:
    """Compara, controle a controle, o atalho atual com a ordem real.

    Só devolve o que DIVERGE — um animal de primeira cria, ou um cujos controles
    são todos posteriores ao último parto, não aparece. É o que permite dizer ao
    dono quantos registros a reconstrução mexeria antes de mexer em nenhum."""
    atalho = ordem_parto_pelo_atalho_atual(partos)
    fora = []
    for d in datas_de_controle:
        correta = ordem_parto_na_data(partos, d)
        if correta != atalho:
            fora.append(Divergencia(numero_matriz, d, atalho, correta))
    return fora
