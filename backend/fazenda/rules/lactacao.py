"""
Lactação aberta/fechada — o conceito básico que o equivalente maduro precisa
para saber QUAIS lactações do rebanho já terminaram (e por isso podem entrar
no cálculo dos fatores de classe) e qual é a lactação ATUAL de cada animal
(a que aparece no par "produz hoje / produzirá").

Uma lactação é a janela entre um parto e o parto seguinte (se já houve) ou a
secagem seguinte (se o parto seguinte ainda não aconteceu). Sem nenhum dos
dois, a lactação está em andamento — `data_fim` fica `None`, o que é
resposta legítima, não dado faltando.

Esta é a mesma regra que `rules/parto_resumo.py::resumo_por_parto` já usa
inline para o quadro "por parto" da Ficha do Animal. Fica aqui como função
pura e nomeada para o equivalente maduro poder reaproveitá-la sem duplicar o
raciocínio — `parto_resumo.py` continua com a versão inline dele porque já
está em produção e mexer nela não é necessário para esta entrega.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class JanelaLactacao:
    """Uma lactação de um animal: começa no parto, termina no parto seguinte
    ou na secagem seguinte — o que vier primeiro registrado."""

    data_inicio: date
    data_fim: date | None  # None = ainda em andamento (não é dado faltando)
    encerrada: bool


def montar_janelas(datas_parto: list[date], datas_secagem: list[date]) -> list[JanelaLactacao]:
    """Uma `JanelaLactacao` por parto, na mesma ordem cronológica de
    `datas_parto` (duplicatas e ordem de entrada não importam — a função
    ordena por conta própria).

    Para cada parto, nesta ordem de prioridade:
      1. Existe um parto seguinte? A lactação termina nele — `encerrada=True`.
      2. Senão, existe uma secagem registrada depois do início? Termina nela
         — `encerrada=True`.
      3. Senão, a lactação ainda está em andamento — `data_fim=None`,
         `encerrada=False`.
    """
    inicios = sorted(datas_parto)
    secagens = sorted(datas_secagem)
    janelas: list[JanelaLactacao] = []
    n = len(inicios)
    for i, inicio in enumerate(inicios):
        fim = inicios[i + 1] if i + 1 < n else None
        encerrada = fim is not None
        if fim is None:
            secagem_da_janela = next((d for d in secagens if d >= inicio), None)
            if secagem_da_janela is not None:
                fim = secagem_da_janela
                encerrada = True
        janelas.append(JanelaLactacao(data_inicio=inicio, data_fim=fim, encerrada=encerrada))
    return janelas
