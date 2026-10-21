"""
Tratos por dia da dieta e janela (ciclo de 24h) da sobra de cocho.

Regras puras, sem banco — usadas pelo router de Alimentação
(`fazenda/api/routers/alimentacao.py`), pela Agenda (alerta de sobra) e pelo
Assistente. Espelhadas no front em `frontend/lib/tratos.ts` (mesmas contas
para o resumo "A sobra se refere ao…", que o app precisa montar até offline).

Decisões do dono (2026-10-21, ver ESPEC de tratos):

- Os tratos são cadastrados POR DIETA (`DietaLancamento.tratos_pct`): 1 a 4,
  cada um com um %, somando 100%. Identificados só por número (Trato 1..4).
  O % vale para a dieta inteira (todos os alimentos na mesma proporção).
- Dieta antiga, sem cadastro (`tratos_pct` NULL), vale como 2 tratos 50/50 —
  exatamente a conta que o sistema fazia quando o nº de tratos era fixo em 2.
- A dieta também guarda a POSIÇÃO DA LEITURA DA SOBRA no ciclo
  (`DietaLancamento.sobra_posicao_leitura`): o número `p` do trato depois do
  qual a sobra é medida — a leitura acontece entre o Trato p e o Trato p+1
  (com p = N, entre o último trato e o Trato 1 do dia seguinte).

Janela da sobra (o "ciclo de 24h"), a regra que tudo aqui segue:

- A sobra é medida no dia da LEITURA (D), antes do trato seguinte a `p`.
  O ciclo que ela fecha são os N tratos imediatamente anteriores à leitura:
    · p < N → Tratos p+1..N do dia D-1  +  Tratos 1..p do dia D
      (ex.: 3 tratos, leitura entre T1 e T2 em 21/10 → T2 e T3 de 20/10 e
      T1 de 21/10 — o exemplo do dono);
    · p = N → Tratos 1..N do dia D-1 (leitura de manhã, antes do 1º trato,
      referente ao dia anterior — a mesma regra que a tela do site já
      ensinava: "a sobra se refere, em regra, ao dia anterior");
    · 1 trato → p é sempre 1 (não se pergunta), então a janela é o trato do
      dia anterior até a leitura.
- Sem posição (`None`) — dieta antiga, ou quem preferiu não informar — vale o
  comportamento de SEMPRE: a data informada é o próprio dia do fornecimento e
  a janela é o dia civil inteiro (todos os tratos daquele dia).

`ConsumoSobra.data` guarda a data de FECHAMENTO do ciclo (o dia do último
trato da janela) — não a data da leitura (que fica em `data_leitura`). É isso
que mantém "uma sobra por lote por ciclo" na MESMA UniqueConstraint de
sempre (fazenda, lote, data): no comportamento antigo (dia civil) a data de
fechamento é a própria data informada, então nada muda para quem não
configurou; e uma leitura entre o último e o primeiro trato em 21/10 fecha o
mesmo ciclo que a sobra "do dia 20/10" lançada do jeito antigo — relançar
substitui em vez de duplicar.

Base da sobra % = fornecido NA JANELA:
- lançamento de consumo COM trato (parâmetro "lançar consumo por trato"
  ligado): entra inteiro se (dia, trato) está na janela;
- lançamento SEM trato (lançado por dia): entra rateado pelo % dos tratos da
  janela naquele dia (ex.: ontem 1000 kg, tratos 40/30/30, janela T2+T3 de
  ontem → 600 kg; mais 40% do lançado hoje para o T1).
As duas regras convivem no mesmo dia (a fazenda pode ter trocado o
parâmetro no meio do caminho) sem nada contar duas vezes.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Iterable

MAX_TRATOS = 4
TRATOS_PADRAO: tuple[float, ...] = (50.0, 50.0)
# Tolerância da soma dos % (arredondamento de 3 tratos: 33,33 + 33,33 + 33,34).
_TOLERANCIA_SOMA = 0.01


class TratosInvalidos(ValueError):
    """Cadastro de tratos/posição recusado — a mensagem vai direto ao usuário."""


def ler_tratos(tratos_pct_json: str | None) -> list[float]:
    """% de cada trato a partir da coluna JSON; NULL (ou ilegível) = 2×50%."""
    if not tratos_pct_json:
        return list(TRATOS_PADRAO)
    try:
        valores = [float(v) for v in json.loads(tratos_pct_json)]
    except (TypeError, ValueError):
        return list(TRATOS_PADRAO)
    return valores if 1 <= len(valores) <= MAX_TRATOS else list(TRATOS_PADRAO)


def gravar_tratos(pcts: list[float] | None) -> str | None:
    return json.dumps([round(float(p), 2) for p in pcts]) if pcts is not None else None


def validar_tratos(pcts: list[float]) -> list[float]:
    """1 a 4 tratos, cada um > 0, somando 100% (± 0,01)."""
    if not (1 <= len(pcts) <= MAX_TRATOS):
        raise TratosInvalidos(f"Informe de 1 a {MAX_TRATOS} tratos por dia.")
    if any(p is None or p <= 0 for p in pcts):
        raise TratosInvalidos("Cada trato precisa de um % maior que zero.")
    soma = sum(pcts)
    if abs(soma - 100) > _TOLERANCIA_SOMA:
        raise TratosInvalidos(f"Os % dos tratos precisam somar 100% (hoje somam {round(soma, 2)}%).")
    return [round(float(p), 2) for p in pcts]


def validar_posicao(n_tratos: int, posicao: int | None) -> int | None:
    """Com 1 trato não se pergunta: a posição é sempre 1. Com 2+, `None` é
    aceito (comportamento antigo, dia civil) ou 1..N."""
    if n_tratos == 1:
        return 1
    if posicao is None:
        return None
    if not (1 <= posicao <= n_tratos):
        raise TratosInvalidos(f"Posição da leitura da sobra inválida: escolha entre o Trato 1 e o Trato {n_tratos}.")
    return posicao


def dividir_por_trato(total: float | None, pcts: list[float]) -> list[float | None]:
    """Quantidade de cada trato — `None` se o total não é conhecido."""
    if total is None:
        return [None for _ in pcts]
    return [round(total * p / 100, 2) for p in pcts]


def valor_unico_por_trato(total: float | None, pcts: list[float]) -> float | None:
    """O antigo "total/trato": só existe quando todos os tratos têm o mesmo %
    (senão um número único enganaria — cada trato leva uma quantidade)."""
    if total is None or len({round(p, 2) for p in pcts}) != 1:
        return None
    return round(total / len(pcts), 2)


def data_fechamento(data_informada: date, n_tratos: int, posicao: int | None) -> date:
    """Dia do último trato da janela (é o que vai em `ConsumoSobra.data`)."""
    if posicao is None:
        return data_informada           # dia civil — a data informada é o dia do fornecimento
    if posicao >= n_tratos:
        return data_informada - timedelta(days=1)   # leitura antes do 1º trato: ciclo de ontem
    return data_informada


def data_leitura(fechamento: date, n_tratos: int, posicao: int | None) -> date:
    """Inverso de `data_fechamento` — para exibir a data em que a sobra foi lida."""
    if posicao is not None and posicao >= n_tratos:
        return fechamento + timedelta(days=1)
    return fechamento


def janela(fechamento: date, n_tratos: int, posicao: int | None) -> list[tuple[date, int]]:
    """(dia, trato) de cada trato do ciclo que fecha em `fechamento`, em ordem."""
    if posicao is None or posicao >= n_tratos:
        return [(fechamento, t) for t in range(1, n_tratos + 1)]
    anterior = fechamento - timedelta(days=1)
    return [(anterior, t) for t in range(posicao + 1, n_tratos + 1)] + [(fechamento, t) for t in range(1, posicao + 1)]


def _lista_tratos(tratos: list[int]) -> str:
    nums = [str(t) for t in tratos]
    texto = nums[0] if len(nums) == 1 else ", ".join(nums[:-1]) + " e " + nums[-1]
    return f"{'ao trato' if len(nums) == 1 else 'aos tratos'} {texto}"


def descrever_janela(itens: list[tuple[date, int]]) -> str:
    """O resumo que o usuário confirma — ex.: "A sobra se refere aos tratos 2
    e 3 do dia 20/10 e ao trato 1 do dia 21/10?"."""
    por_dia: dict[date, list[int]] = {}
    for d, t in itens:
        por_dia.setdefault(d, []).append(t)
    partes = [f"{_lista_tratos(ts)} do dia {d.strftime('%d/%m')}" for d, ts in por_dia.items()]
    return "A sobra se refere " + " e ".join(partes) + "?"


def ciclo_do_registro(sobra) -> tuple[list[tuple[date, int]], list[float]]:
    """Janela e % dos tratos de um `ConsumoSobra` já gravado (retrato do
    lançamento). Registro antigo (tudo NULL) = dia civil `data`, 2×50%."""
    pcts = ler_tratos(getattr(sobra, "tratos_pct", None))
    return janela(sobra.data, len(pcts), getattr(sobra, "posicao_leitura", None)), pcts


def fornecido_na_janela(
    consumos: Iterable[tuple[date, int | None, str, float]],
    itens_janela: list[tuple[date, int]],
    pcts: list[float],
) -> dict[str, float]:
    """kg fornecido por alimento dentro da janela.

    `consumos` = (dia, trato ou None, alimento, kg) — só o que já converteu
    para kg. Lançamento com trato entra inteiro se estiver na janela; sem
    trato, entra pela fração dos tratos da janela naquele dia."""
    na_janela = set(itens_janela)
    fracao_dia: dict[date, float] = {}
    for d, t in itens_janela:
        if 1 <= t <= len(pcts):
            fracao_dia[d] = fracao_dia.get(d, 0.0) + pcts[t - 1] / 100
    saida: dict[str, float] = {}
    for d, trato, alimento, kg in consumos:
        if trato is not None:
            parcela = kg if (d, trato) in na_janela else 0.0
        else:
            parcela = kg * fracao_dia.get(d, 0.0)
        if parcela:
            saida[alimento] = saida.get(alimento, 0.0) + parcela
    return saida
