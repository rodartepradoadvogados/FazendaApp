"""
Curva de Wood — y(t) = a · t^b · e^(−c·t), o modelo clássico de curva de
lactação (Wood, 1967): sobe rápido até o pico e depois declina lentamente,
igual à forma real de uma lactação.

Ajustada aos PONTOS REAIS do próprio animal (não à média do rebanho) — serve
para responder "esta vaca está produzindo acima ou abaixo do que ELA MESMA
deveria, dada a trajetória que os controles dela já mostraram?" e para
projetar a cauda de uma lactação ainda em aberto (útil para estimar onde a
produção vai parar antes do fim).

Sem `scipy` — não é dependência do projeto (ver backend/requirements.txt), e
adicionar uma lib pesada só para ajustar 3 parâmetros não se justifica. O
ajuste usa a linearização clássica do modelo de Wood: tomando o log dos dois
lados,

    ln(y) = ln(a) + b·ln(t) − c·t

a equação vira LINEAR nos parâmetros (ln(a), b, c) — resolvida por mínimos
quadrados comuns (equações normais 3×3, eliminação gaussiana com
pivoteamento parcial), pura aritmética, sem depender de nenhuma biblioteca
externa. É a abordagem padrão em zootecnia quando não há um otimizador
não-linear à mão; minimiza o erro em escala logarítmica (dá peso relativo
maior aos pontos de produção baixa) em vez do erro em kg — suficiente para o
que a ficha precisa (mostrar a trajetória esperada e projetar a cauda), não
uma calibração científica de precisão.
"""
from __future__ import annotations

import math

# Precisa de pelo menos estes pontos de controle para o ajuste fazer sentido.
# Com 3 (o nº de parâmetros do modelo) o sistema tem solução exata e não diz
# nada sobre se a curva é plausível — abaixo disso a resposta é None (sem
# curva inventada a partir de 2-3 pontos) em vez de uma curva de "ajuste
# perfeito" sem significado nenhum.
PONTOS_MINIMOS_AJUSTE = 4

# Quantos dias além do maior DEL do animal a série projetada cobre — mostra a
# cauda esperada de uma lactação ainda em aberto.
MARGEM_PROJECAO_DIAS = 60

# Teto de segurança para o tamanho da série devolvida — protege contra um DEL
# sujo nos dados (ex. um controle com DEL absurdo) gerando uma série enorme;
# bem acima de qualquer lactação real (a mais longa comum passa de 305 dias
# só em casos raros de lactação estendida).
DEL_MAXIMO_SERIE = 1200


def _wood(a: float, b: float, c: float, t: float) -> float:
    """y(t) = a·t^b·e^(−c·t). Zero em t<=0 (sem lactação antes do parto)."""
    if t <= 0:
        return 0.0
    try:
        return a * (t ** b) * math.exp(-c * t)
    except (OverflowError, ValueError):
        return 0.0


def _resolver_sistema_3x3(m: list[list[float]], v: list[float]) -> list[float] | None:
    """Resolve M·x = v (3 equações, 3 incógnitas) por eliminação gaussiana
    com pivoteamento parcial. None se o sistema for degenerado (ex.: todos os
    pontos no mesmo DEL — não há como separar os 3 parâmetros)."""
    n = 3
    aug = [row[:] + [v[i]] for i, row in enumerate(m)]
    for col in range(n):
        pivo = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivo][col]) < 1e-12:
            return None
        aug[col], aug[pivo] = aug[pivo], aug[col]
        for lin in range(col + 1, n):
            fator = aug[lin][col] / aug[col][col]
            for c in range(col, n + 1):
                aug[lin][c] -= fator * aug[col][c]
    x = [0.0, 0.0, 0.0]
    for lin in range(n - 1, -1, -1):
        soma = aug[lin][n] - sum(aug[lin][c] * x[c] for c in range(lin + 1, n))
        x[lin] = soma / aug[lin][lin]
    return x


def ajustar_curva_wood(
    pontos: list[tuple[float, float]],
    margem_dias: int = MARGEM_PROJECAO_DIAS,
) -> dict | None:
    """Ajusta y(t) = a·t^b·e^(−c·t) aos pontos (DEL, kg) reais de um animal.

    `pontos`: lista de (del, kg) — tipicamente vinda dos controles leiteiros
    do animal. Pontos com DEL ou kg ausentes, zero ou negativos são
    descartados (o log da linearização exige os dois estritamente
    positivos).

    Devolve {"a", "b", "c", "pontos"} — `pontos` é a série (DEL, kg
    projetado) do DEL 0 até o maior DEL válido do animal + `margem_dias`,
    pronta para desenhar.

    None quando: faltam pontos válidos (menos de `PONTOS_MINIMOS_AJUSTE`);
    o sistema de mínimos quadrados é degenerado; ou o ajuste resulta em
    parâmetros não finitos / `a` não positivo (curva sem sentido físico —
    preferível não desenhar nada a desenhar uma curva absurda).
    """
    validos = [
        (float(d), float(k)) for d, k in pontos
        if d is not None and k is not None and float(d) > 0 and float(k) > 0
    ]
    if len(validos) < PONTOS_MINIMOS_AJUSTE:
        return None

    # Regressão linear de ln(kg) = ln(a) + b·ln(DEL) − c·DEL — três
    # "colunas" (1, ln(t), t) contra o alvo ln(y), resolvida pelas equações
    # normais X'X·β = X'y (3×3, β = [ln(a), b, −c]).
    xs = [(1.0, math.log(t), t) for t, _ in validos]
    ys = [math.log(k) for _, k in validos]

    m = [[0.0, 0.0, 0.0] for _ in range(3)]
    v = [0.0, 0.0, 0.0]
    for linha, y in zip(xs, ys):
        for i in range(3):
            v[i] += linha[i] * y
            for j in range(3):
                m[i][j] += linha[i] * linha[j]

    solucao = _resolver_sistema_3x3(m, v)
    if solucao is None:
        return None
    ln_a, b, neg_c = solucao
    try:
        a = math.exp(ln_a)
    except OverflowError:
        return None
    c = -neg_c
    if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c)) or a <= 0:
        return None

    maior_del = max(t for t, _ in validos)
    ate = min(int(maior_del) + margem_dias, DEL_MAXIMO_SERIE)
    serie = [{"del": t, "kg": round(_wood(a, b, c, t), 2)} for t in range(0, ate + 1)]

    return {"a": a, "b": b, "c": c, "pontos": serie}
