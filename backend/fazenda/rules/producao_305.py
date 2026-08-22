"""
Produção de 305 dias pelo Test Interval Method (TIM) da ICAR — integração
trapezoidal dos controles leiteiros, em vez da "média aritmética × 305" que
`frontend/producao/page.tsx` faz hoje (procure por "305" e por
`projecao_305: Math.round(med * 305)`).

A conta de guardanapo atual ignora que cada controle representa um
intervalo de duração diferente (mensal, DHI, esporádico) e finge que a
lactação inteira produziu no ritmo da média simples dos dias em que houve
controle. O TIM pesa cada controle pelo intervalo de tempo que ele
realmente representa:

    Produção = I₀·M₁ + I₁·(M₁+M₂)/2 + I₂·(M₂+M₃)/2 + … + Iₙ·Mₙ

onde `I` é o intervalo em dias entre duas datas de controle consecutivas e
`M` a produção do dia do controle. A ponta inicial (`I₀`, do parto ao 1º
controle) assume que a vaca já produzia no ritmo do 1º controle desde o
parto; a ponta final (`Iₙ`, do último controle até o fim da janela de 305
dias ou o fim da lactação) assume que ela manteve o ritmo do último
controle até lá. É a mesma convenção do TIM oficial, e por isso o método
TAMBÉM superestima — o viés cresce quanto mais espaçados os controles. Um
rebanho com controle mensal erra menos que um com controle trimestral.
Isso fica marcado no resultado (`estimada`), para a tela avisar em vez de
fingir precisão de duas casas decimais.

Função pura, sem Session — mesma convenção de `rules/ordem_parto_historica.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

DIAS_PADRAO = 305


@dataclass(frozen=True)
class PontoControle:
    """Um controle leiteiro: data e produção do dia (kg)."""

    data: date
    producao_kg: float


@dataclass(frozen=True)
class Producao305:
    """Resultado da integração — ou a recusa honesta de integrar.

    `producao_kg` é `None` quando não dá para calcular (menos de dois
    controles utilizáveis); `motivo` explica por quê. `estimada=True` quando
    a ponta final foi extrapolada (a lactação ainda está em andamento e não
    completou nem os 305 dias nem uma secagem) — o total inclui um trecho
    que não tem controle real por trás, só a manutenção do último ritmo
    observado."""

    producao_kg: float | None
    n_controles: int
    dias_cobertos: int | None  # dias reais entre o parto e o último controle usado
    estimada: bool
    motivo: str | None = None


def producao_305_dias(
    controles: list[PontoControle],
    data_parto: date,
    data_fim: date | None = None,
    dias: int = DIAS_PADRAO,
) -> Producao305:
    """Produção acumulada em `dias` dias (305 por padrão) a partir do parto,
    ou até `data_fim` (secagem ou parto seguinte já registrado), o que vier
    primeiro.

    Trata os casos degenerados em vez de inventar:
      - `data_parto` ausente: sem parto não há de onde contar o período.
      - menos de dois controles utilizáveis (depois de filtrar datas
        inválidas e ordenar): TIM exige pelo menos dois pontos para montar
        um único intervalo — com um só, não há como saber o ritmo entre
        eles.
      - controles fora de ordem: são ordenados antes de integrar, a ordem
        de entrada não importa.
      - datas duplicadas (mais de um lançamento no mesmo dia — reenvio,
        conflito de importação): funde pela MÉDIA dos valores daquele dia,
        em vez de contar o mesmo dia duas vezes ou descartar um dos dois
        arbitrariamente.
      - controles antes do parto ou depois de `data_fim`: fora da janela
        desta lactação, descartados.
    """
    if data_parto is None:
        return Producao305(None, 0, None, False, motivo="sem data de parto")

    limite_da_janela = data_parto + timedelta(days=dias)
    if data_fim is not None and data_fim > data_parto:
        limite_da_janela = min(limite_da_janela, data_fim)

    por_data: dict[date, list[float]] = {}
    for c in controles:
        if c.data is None or c.producao_kg is None:
            continue
        if c.data < data_parto or c.data > limite_da_janela:
            continue
        por_data.setdefault(c.data, []).append(float(c.producao_kg))
    pontos = sorted(
        (PontoControle(d, sum(vs) / len(vs)) for d, vs in por_data.items()),
        key=lambda p: p.data,
    )

    if len(pontos) < 2:
        return Producao305(
            None, len(pontos), None, False,
            motivo=(
                "menos de dois controles dentro da janela (parto até 305 dias ou até secagem/"
                "próximo parto) — o Test Interval Method exige ao menos dois pontos para integrar"
            ),
        )

    total = 0.0
    total += (pontos[0].data - data_parto).days * pontos[0].producao_kg
    for anterior, atual in zip(pontos, pontos[1:]):
        intervalo = (atual.data - anterior.data).days
        total += intervalo * (anterior.producao_kg + atual.producao_kg) / 2
    total += (limite_da_janela - pontos[-1].data).days * pontos[-1].producao_kg

    dias_cobertos = (pontos[-1].data - data_parto).days
    # "Estimada": a lactação ainda está em andamento (sem secagem/próximo
    # parto conhecido) e o último controle é anterior ao fim dos 305 dias —
    # o trecho final foi extrapolado, não observado.
    estimada = data_fim is None and pontos[-1].data < limite_da_janela

    return Producao305(round(total, 1), len(pontos), dias_cobertos, estimada)
