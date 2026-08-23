"""
Produção de 305 dias pelo Test Interval Method (TIM) da ICAR — integração
trapezoidal dos controles leiteiros, em vez da "média aritmética × 305" que
`frontend/producao/page.tsx` fazia antes desta camada (procure por "305" e por
`projecao_305: Math.round(med * 305)`).

A conta de guardanapo antiga ignorava que cada controle representa um
intervalo de duração diferente (mensal, DHI, esporádico) e fingia que a
lactação inteira produziu no ritmo da média simples dos dias em que houve
controle. O TIM pesa cada controle pelo intervalo de tempo que ele
realmente representa:

    Produção = I₀·M₁ + I₁·(M₁+M₂)/2 + I₂·(M₂+M₃)/2 + … + Iₙ·Mₙ

onde `I` é o intervalo em dias entre duas datas de controle consecutivas e
`M` a produção do dia do controle. A ponta inicial (`I₀`, do parto ao 1º
controle) assume que a vaca já produzia no ritmo do 1º controle desde o
parto — extrapolação para trás, curta, sem alternativa melhor com o que se
tem.

A ponta final (`Iₙ`) é onde este módulo mudou: quando a lactação está
ENCERRADA (`data_fim` conhecida — secagem ou próximo parto), `Iₙ` é o trecho
curto e real até essa data, e continua mantendo o ritmo do último controle
(convenção padrão do TIM — o trecho é curto, o viés é pequeno). Quando a
lactação está EM ANDAMENTO e o último controle é anterior ao fim dos 305
dias, `Iₙ` deixa de ser um platô: vira a curva de referência declinante de
`rules/curva_lactacao_referencia.py`, ancorada no ritmo do último controle.
Um platô ali superestimava sistematicamente — toda vaca declina depois do
pico, e segurar o último ritmo como se fosse eterno inflava o total tanto
mais quanto menor o DEL do último controle. Isso continua marcado no
resultado (`estimada`), para a tela avisar que aquele trecho é projeção, não
medição — só que agora a projeção segue uma curva, não uma linha reta.

`producao_medida_kg` expõe separadamente a parte do total que vem SÓ de
trapézios entre dois controles reais (nem a ponta inicial, nem a final) —
é o numerador de "confiança" em `rules/equivalente_maduro.py`: que fração do
total projetado é leite de fato medido nesta vaca, não extrapolação para
nenhum dos dois lados.

Função pura, sem Session — mesma convenção de `rules/ordem_parto_historica.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from fazenda.rules.curva_lactacao_referencia import producao_projetada_no_trecho_final

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
    # Só a parte "de fato medida" do total: os trapézios ENTRE dois controles
    # reais, sem contar nenhuma das duas pontas extrapoladas (nem a inicial,
    # nem a final — platô ou curva, tanto faz, nenhuma das duas é medição).
    # `None` exatamente quando `producao_kg` também é `None`.
    producao_medida_kg: float | None = None


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

    dias_cobertos = (pontos[-1].data - data_parto).days
    # "Estimada": a lactação ainda está em andamento (sem secagem/próximo
    # parto conhecido) e o último controle é anterior ao fim dos 305 dias —
    # o trecho final é projeção, não observação.
    estimada = data_fim is None and pontos[-1].data < limite_da_janela

    medida_interior = 0.0
    for anterior, atual in zip(pontos, pontos[1:]):
        intervalo = (atual.data - anterior.data).days
        medida_interior += intervalo * (anterior.producao_kg + atual.producao_kg) / 2

    ponta_inicial = (pontos[0].data - data_parto).days * pontos[0].producao_kg

    if estimada:
        # Em andamento e ainda não chegou no fim da janela: a ponta final
        # segue a curva de referência declinante, ancorada no ritmo do
        # último controle — não mais um platô (ver módulo
        # `curva_lactacao_referencia`).
        ponta_final = producao_projetada_no_trecho_final(
            del_ultimo_controle=dias_cobertos,
            del_fim_janela=(limite_da_janela - data_parto).days,
            ritmo_ultimo_controle=pontos[-1].producao_kg,
        )
    else:
        # Lactação já encerrada (secagem/próximo parto conhecido): o trecho
        # final é curto e real, até uma data que de fato aconteceu — mantém
        # a convenção padrão do TIM (ritmo do último controle até lá).
        ponta_final = (limite_da_janela - pontos[-1].data).days * pontos[-1].producao_kg

    total = ponta_inicial + medida_interior + ponta_final

    return Producao305(
        round(total, 1), len(pontos), dias_cobertos, estimada,
        producao_medida_kg=round(medida_interior, 1),
    )
