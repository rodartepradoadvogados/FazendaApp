"""
Caixa do time (participação nos lucros) — regras puras e de consulta.

O caixa do time é dinheiro do coletivo. Em datas fixas (parâmetros financeiros,
padrão 01/06 e 01/12) é repartido entre os membros em partes proporcionais aos
dias de participação no período, com ajuste individual por penalidade (percentual
retirado da parte da pessoa e repartido entre os demais). Toda conta é feita em
CENTAVOS inteiros, com o resto distribuído pelo maior resto, para que a soma das
partes seja sempre exatamente o total.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from fazenda.models import CaixaTime, CaixaTimeMembro, CaixaTimeMovimento, Pessoa
from fazenda.rules.caixa_funcionario import grupos_da_pessoa

CATEGORIA_PENALIDADE = "Documento de ciência de penalidade"


def _data(ano: int, mes: int, dia: int) -> date:
    try:
        return date(ano, mes, dia)
    except ValueError:  # 29/02 em ano comum
        return date(ano, mes, 28)


def proxima_entrega(hoje: date, datas: list[tuple[int, int]]) -> date:
    """A próxima data de rateio a partir de HOJE (inclusive)."""
    for ano in (hoje.year, hoje.year + 1):
        for mes, dia in datas:
            d = _data(ano, mes, dia)
            if d >= hoje:
                return d
    raise ValueError("sem datas de entrega")


def periodo_em_apuracao(hoje: date, datas: list[tuple[int, int]]) -> tuple[date, date, date]:
    """(início, fim, entrega): do dia da entrega anterior até o dia anterior à próxima."""
    entrega = proxima_entrega(hoje, datas)
    anteriores = [
        _data(ano, mes, dia) for ano in (entrega.year - 1, entrega.year) for mes, dia in datas
        if _data(ano, mes, dia) < entrega
    ]
    inicio = max(anteriores)
    return inicio, entrega - timedelta(days=1), entrega


def _repartir(total_c: int, pesos: list[int]) -> list[int]:
    """Reparte `total_c` centavos em proporção a `pesos` (maior resto). Soma exata."""
    soma = sum(pesos)
    if soma <= 0:
        return [0] * len(pesos)
    base = [total_c * p // soma for p in pesos]
    restos = sorted(range(len(pesos)), key=lambda i: (-(total_c * pesos[i] % soma), i))
    faltam = total_c - sum(base)
    for i in restos[:faltam]:
        base[i] += 1
    return base


def calcular_partes(total: float, linhas: list[dict]) -> list[dict]:
    """`linhas`: [{pessoa_id, dias, penalidade_pct}]. Devolve a mesma lista, em ordem,
    com `parte_calculada` e `parte_final`. A penalidade de uma pessoa (pct da parte
    DELA) vai para as pessoas SEM penalidade, proporcionalmente à parte delas.
    ValueError se há penalidade e ninguém sem penalidade para receber."""
    total_c = round(total * 100)
    calc = _repartir(total_c, [max(int(l["dias"]), 0) for l in linhas])
    retirado = [round(c * min(max(float(l.get("penalidade_pct") or 0), 0.0), 100.0) / 100) for c, l in zip(calc, linhas)]
    a_distribuir = sum(retirado)
    receptores = [i for i, l in enumerate(linhas) if not (l.get("penalidade_pct") or 0) and calc[i] > 0]
    ganhos = [0] * len(linhas)
    if a_distribuir:
        if not receptores:
            raise ValueError("Não há quem receba a parte retirada: todos os membros têm penalidade.")
        for i, v in zip(receptores, _repartir(a_distribuir, [calc[i] for i in receptores])):
            ganhos[i] = v
    saida = []
    for l, c, r, g in zip(linhas, calc, retirado, ganhos):
        saida.append({**l, "parte_calculada": c / 100, "parte_final": (c - r + g) / 100})
    return saida


def dias_no_periodo(entrada: date | None, saida: date | None, inicio: date, fim: date) -> int:
    """Dias corridos (inclusive) de participação dentro de [inicio, fim]."""
    ini = max(entrada, inicio) if entrada else inicio
    fi = min(saida, fim) if saida else fim
    return max((fi - ini).days + 1, 0)


def membros_do_periodo(session: Session, time: CaixaTime, inicio: date, fim: date) -> list[dict]:
    """Membros efetivos no período: os explícitos (por nome, com entrada/saída) e, por
    tipo, os ativos que o filtro alcança. Cada um com `dias`; quem tem 0 fica de fora."""
    explicitos = list(session.exec(
        select(CaixaTimeMembro).where(CaixaTimeMembro.time_id == time.id)
    ).all())
    por_id = {m.pessoa_id: m for m in explicitos}
    tipos = {t for t in (time.auto_tipos or "").split(",") if t}
    candidatos: dict[int, tuple[Pessoa, date | None, date | None, str]] = {}
    for m in explicitos:
        p = session.get(Pessoa, m.pessoa_id)
        if p is not None and (time.fazenda_id is None or p.fazenda_id == time.fazenda_id):
            candidatos[p.id] = (p, m.entrada, m.saida, "nome")
    if tipos:
        query = select(Pessoa).where(Pessoa.ativo == True)  # noqa: E712
        if time.fazenda_id is not None:
            query = query.where(Pessoa.fazenda_id == time.fazenda_id)
        for p in session.exec(query).all():
            if p.id in por_id or not (set(grupos_da_pessoa(p)) & tipos):
                continue
            candidatos[p.id] = (p, p.data_admissao, None, "tipo")
    saida = []
    for p, entrada, sai, origem in candidatos.values():
        dias = dias_no_periodo(entrada, sai, inicio, fim)
        saida.append({
            "pessoa_id": p.id, "nome": p.nome, "tipo": p.tipo, "grupos": grupos_da_pessoa(p),
            "entrada": entrada, "saida": sai, "origem": origem, "dias": dias,
        })
    return sorted(saida, key=lambda m: m["nome"])


def saldo_do_time(session: Session, time_id: int) -> float:
    return round(sum(m.valor for m in session.exec(
        select(CaixaTimeMovimento).where(CaixaTimeMovimento.time_id == time_id)
    ).all()), 2)
