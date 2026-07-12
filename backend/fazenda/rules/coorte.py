"""
Motor de coorte por idade — o "cérebro" do Dossiê de Recria.

Dado o nascimento de cada animal e a data de cada evento (doença, pesagem),
calcula a idade em dias e agrupa em curvas e faixas (fases). Alimenta:
 - a curva "número de casos por idade (dias)" e o ponto crítico;
 - a incidência (%) por fase, com denominador = animais que passaram pela faixa.

Sem dependência de banco: recebe listas simples e devolve dicionários prontos
para o router serializar. Mantido testável e isolado.
"""
from __future__ import annotations

from datetime import date


def idade_em_dias(data_nasc: date | None, ref: date | None) -> int | None:
    """Idade em dias do animal na data de referência (None se faltar dado)."""
    if not data_nasc or not ref:
        return None
    return (ref - data_nasc).days


def curva_casos_por_idade(idades: list[int], limite_dias: int = 300) -> list[dict]:
    """Histograma de casos por idade (dias). `idades` = idade de cada caso.
    Retorna [{dia, casos}] ordenado por dia, só até `limite_dias`."""
    cont: dict[int, int] = {}
    for d in idades:
        if d is None or d < 0 or d > limite_dias:
            continue
        cont[d] = cont.get(d, 0) + 1
    return [{"dia": d, "casos": cont[d]} for d in sorted(cont)]


def ponto_critico(curva: list[dict], cobertura: float = 0.5) -> dict | None:
    """Janela de idade (dias) mais 'quente': a menor faixa contígua de dias que
    concentra pelo menos `cobertura` (ex.: 50%) do total de casos. Também
    devolve o dia de pico. Retorna None se não houver casos."""
    if not curva:
        return None
    total = sum(p["casos"] for p in curva)
    if total <= 0:
        return None
    pico = max(curva, key=lambda p: p["casos"])
    # Janela deslizante sobre o eixo de dias (usa só os dias com casos).
    dias = [p["dia"] for p in curva]
    casos = [p["casos"] for p in curva]
    alvo = cobertura * total
    melhor = None  # (largura_dias, dia_ini, dia_fim, casos_na_janela)
    i = 0
    soma = 0
    for j in range(len(dias)):
        soma += casos[j]
        while soma >= alvo and i <= j:
            largura = dias[j] - dias[i]
            cand = (largura, dias[i], dias[j], soma)
            if melhor is None or largura < melhor[0]:
                melhor = cand
            soma -= casos[i]
            i += 1
    if melhor is None:
        melhor = (dias[-1] - dias[0], dias[0], dias[-1], total)
    return {
        "dia_pico": pico["dia"],
        "dia_min": melhor[1],
        "dia_max": melhor[2],
        "casos_na_janela": melhor[3],
        "total_casos": total,
        "pct_na_janela": round(100 * melhor[3] / total, 1),
    }


def incidencia_por_fase(
    casos_por_animal_idade: list[tuple[str, int]],
    idade_atual_por_animal: dict[str, int],
    fases: list[dict],
) -> list[dict]:
    """Incidência (%) de uma doença por fase de idade.

    - `casos_por_animal_idade`: [(numero, idade_dias_do_caso)] — um por caso.
    - `idade_atual_por_animal`: {numero: idade_dias_hoje (ou na baixa)} — usado
      como denominador: um animal "passou" pela fase se sua idade alcançada
      chegou ao início da fase (dia_min).
    - `fases`: [{nome, dia_min, dia_max}].

    Incidência = animais_distintos_com_caso_na_fase / animais_que_passaram_pela_fase.
    """
    saida = []
    for f in fases:
        dmin, dmax = f["dia_min"], f["dia_max"]
        # Animais que atingiram (passaram por) o início da fase.
        denom = {n for n, idade in idade_atual_por_animal.items() if idade is not None and idade >= dmin}
        # Animais com pelo menos um caso dentro da fase.
        com_caso = {n for (n, idade) in casos_por_animal_idade if idade is not None and dmin <= idade <= dmax}
        casos_total = sum(1 for (_, idade) in casos_por_animal_idade if idade is not None and dmin <= idade <= dmax)
        d = len(denom)
        saida.append({
            "fase": f["nome"], "dia_min": dmin, "dia_max": dmax,
            "casos": casos_total, "animais_afetados": len(com_caso),
            "animais_em_risco": d,
            "incidencia_pct": round(100 * len(com_caso) / d, 1) if d else None,
        })
    return saida


# Fases padrão (dias) — usadas quando o consultor ainda não cadastrou as dele.
FASES_PADRAO = [
    {"nome": "0–3 dias", "dia_min": 0, "dia_max": 3},
    {"nome": "4–11 dias", "dia_min": 4, "dia_max": 11},
    {"nome": "11–18 dias", "dia_min": 11, "dia_max": 18},
    {"nome": "18–30 dias", "dia_min": 18, "dia_max": 30},
    {"nome": "30–60 dias", "dia_min": 30, "dia_max": 60},
    {"nome": "60–90 dias", "dia_min": 60, "dia_max": 90},
    {"nome": "90–120 dias", "dia_min": 90, "dia_max": 120},
    {"nome": "120–150 dias", "dia_min": 120, "dia_max": 150},
    {"nome": "150–180 dias", "dia_min": 150, "dia_max": 180},
    {"nome": "180–240 dias", "dia_min": 180, "dia_max": 240},
    {"nome": "240–365 dias", "dia_min": 240, "dia_max": 365},
]
