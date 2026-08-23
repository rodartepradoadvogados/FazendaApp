"""
Curva de referência para projetar o TRECHO FINAL de uma lactação ABERTA cujo
último controle é anterior ao fim da janela de 305 dias — substitui o platô
("segura o último ritmo constante até 305") que `rules/producao_305.py` usava
antes desta mudança.

Por que o platô estava errado: toda vaca em lactação DECLINA depois do pico
de produção — segurar o ritmo do último controle como se ela fosse produzir
aquilo para sempre superestima o total, e o viés cresce quanto MENOR o DEL do
último controle (mais dias projetados, mais declínio real que o platô ignora).
Um levantamento anterior mediu esse viés em até +30% em DEL baixo.

## A forma: curva de Wood

Padrão da literatura de curva de lactação (Wood, 1967):

    y(t) = a · t^b · e^(−c·t)

sobe até o pico em `t = b/c` dias de lactação, depois declina exponencialmente.
Com poucos controles por lactação (2, às vezes 3), não há como AJUSTAR `a`,
`b` e `c` a cada animal — não é um problema de otimização que os dados
sustentem. Em vez disso, fixamos uma FORMA de referência (`b`, `c` — o
"quão cedo é o pico" e "quão rápido declina depois dele") e só ANCORAMOS a
escala no último ritmo REALMENTE observado da vaca: dali em diante, o ritmo
projetado segue a forma da curva, não um platô.

Concretamente: se o último controle foi no dia `t₀` com ritmo `M₀`, o ritmo
projetado em qualquer dia `t > t₀` é

    M(t) = M₀ · [forma(t) / forma(t₀)]

— a escala `a` cancela nessa razão, então nunca precisamos calculá-la à parte.

## Risco explícito

`B_REFERENCIA` e `C_REFERENCIA` vêm de conhecimento treinado sobre o formato
típico de curva de Holandês (pico entre 40 e 70 dias em leite, persistência
moderada) — NÃO de tabela CDCB/ICAR conferida ao vivo (rede bloqueada neste
ambiente). São constantes editáveis, expostas para o painel de aferição, não
normas verificadas. Foram calibradas visualmente para duas propriedades:

  (a) quando o último controle já está perto do fim da janela de 305 dias, a
      projeção deve ficar perto do platô antigo — a troca de método não deve
      mexer no caso "lactação quase fechada", só no caso "muita coisa ainda
      por vir";
  (b) quando o último controle é cedo (DEL baixo), a projeção deve declinar
      de forma perceptível em relação ao platô — é exatamente o caso em que
      o platô mais superestimava.

## DEL_MINIMO_ANCORAGEM

Perto de `t = 0` a curva de Wood tende a zero (`t^b → 0` com `b > 0`), o que
faria a escala implícita explodir se ancorada num controle literalmente cedo
demais (poucos dias de lactação) — é instabilidade numérica da fórmula, não
sinal real sobre a vaca. Ancoramos no DEL real do último controle, mas nunca
abaixo deste piso; controles antes disso (raros — o app não pede o primeiro
controle tão cedo) usam o piso como ponto de ancoragem.

Função pura, sem Session — mesmo padrão de `rules/producao_305.py`.
"""
from __future__ import annotations

import math

# [risco] Forma de referência (Holandês genérico) — ver docstring do módulo.
# Editáveis no painel de aferição, não normas CDCB/ICAR conferidas ao vivo.
B_REFERENCIA = 0.20
C_REFERENCIA = 0.0035
# Pico implícito da forma acima: b/c ≈ 57 dias em leite — dentro da faixa
# típica (40-70 DEL) descrita na literatura para Holandês.

DEL_MINIMO_ANCORAGEM = 15


def _forma(t: float, b: float = B_REFERENCIA, c: float = C_REFERENCIA) -> float:
    """`t^b · e^(−c·t)`, sem escala — só a FORMA (sobe até o pico, depois
    declina). Zero em `t <= 0` (antes do parto não há lactação)."""
    if t <= 0:
        return 0.0
    return (t ** b) * math.exp(-c * t)


def ritmo_projetado(del_ultimo_controle: float, del_alvo: float, ritmo_ultimo_controle: float) -> float:
    """Ritmo diário (kg/dia) projetado em `del_alvo`, ancorado no ritmo REAL
    observado no último controle e seguindo a partir dali a FORMA da curva de
    referência — nunca o platô.

    `del_alvo` anterior ao último controle não é um caso desta função (é
    território medido, não projetado) — devolve o próprio ritmo observado,
    sem extrapolar para trás."""
    if ritmo_ultimo_controle <= 0 or del_alvo <= del_ultimo_controle:
        return ritmo_ultimo_controle
    t_ancora = max(del_ultimo_controle, DEL_MINIMO_ANCORAGEM)
    forma_ancora = _forma(t_ancora)
    if forma_ancora <= 0:
        return ritmo_ultimo_controle
    t_alvo = max(del_alvo, DEL_MINIMO_ANCORAGEM)
    return ritmo_ultimo_controle * (_forma(t_alvo) / forma_ancora)


def producao_projetada_no_trecho_final(
    del_ultimo_controle: float, del_fim_janela: float, ritmo_ultimo_controle: float, passo_dias: float = 1.0,
) -> float:
    """Integra (trapézio, passo de `passo_dias`) a curva de referência entre
    o último controle e o fim da janela de 305 dias — substitui o termo
    `Iₙ·Mₙ` do TIM (que seria o platô) por uma soma que segue a curva
    declinante em vez de manter o ritmo constante.

    `passo_dias=1` já é preciso o bastante para uma janela de até ~305 dias —
    a curva não tem variação abrupta de um dia para o outro."""
    if del_fim_janela <= del_ultimo_controle:
        return 0.0
    total = 0.0
    t = float(del_ultimo_controle)
    fim = float(del_fim_janela)
    while t < fim:
        t2 = min(t + passo_dias, fim)
        y1 = ritmo_projetado(del_ultimo_controle, t, ritmo_ultimo_controle)
        y2 = ritmo_projetado(del_ultimo_controle, t2, ritmo_ultimo_controle)
        total += (t2 - t) * (y1 + y2) / 2
        t = t2
    return total
