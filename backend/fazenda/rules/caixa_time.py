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


def datas_entrega_da_sessao(session: Session, fazenda_id: int | None) -> list[tuple[int, int]]:
    """Mesmas datas de `parametros.caixa_time_datas_entrega`, lidas pela PRÓPRIA sessão do
    chamador (sem abrir outra): é o que o pagamento da folha precisa, que está no meio de
    uma transação e não pode ter uma segunda sessão lendo parâmetros ao lado."""
    from fazenda.models import ParametroFazenda
    from fazenda.rules import parametros

    valores = []
    for chave, padrao in (("caixa_time_entrega_1", "01/06"), ("caixa_time_entrega_2", "01/12")):
        linha = None
        if fazenda_id is not None:
            linha = session.exec(select(ParametroFazenda).where(
                ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == fazenda_id)).first()
        if linha is None:
            linha = session.exec(select(ParametroFazenda).where(
                ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == None)).first()  # noqa: E711
        valores.append(linha.valor if linha is not None and linha.valor is not None else padrao)
    return parametros.interpretar_datas_entrega(valores)


def resumos_para_recibo(session: Session, fazenda_id: int | None, pessoa_ids: list[int] | None = None) -> dict[int, dict]:
    """Rodapé do holerite/recibo: por pessoa, o saldo do caixa individual e a parte
    ESTIMADA em cada caixa do time (proporcional aos dias do período em apuração, sem
    penalidades — estimativa, não promessa). Só entra quem tem saldo ou participa de
    algum time com saldo. Lê tudo em lote (movimentos e times da fazenda uma vez)."""
    from fazenda.models import CaixaMovimento

    query = select(CaixaMovimento)
    if fazenda_id is not None:
        query = query.where(CaixaMovimento.fazenda_id == fazenda_id)
    saldos: dict[int, float] = {}
    for m in session.exec(query).all():
        saldos[m.pessoa_id] = round(saldos.get(m.pessoa_id, 0.0) + m.valor, 2)

    inicio, fim, _ = periodo_em_apuracao(date.today(), datas_entrega_da_sessao(session, fazenda_id))
    query_t = select(CaixaTime).where(CaixaTime.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_t = query_t.where(CaixaTime.fazenda_id == fazenda_id)
    partes: dict[int, list[dict]] = {}
    for t in session.exec(query_t).all():
        saldo_t = saldo_do_time(session, t.id)
        if saldo_t <= 0:
            continue
        membros = [m for m in membros_do_periodo(session, t, inicio, fim) if m["dias"] > 0]
        if not membros:
            continue
        calc = calcular_partes(saldo_t, [{"pessoa_id": m["pessoa_id"], "dias": m["dias"], "penalidade_pct": 0} for m in membros])
        for c in calc:
            partes.setdefault(c["pessoa_id"], []).append({"time": t.nome, "saldo": saldo_t, "parte_estimada": c["parte_final"]})

    alvo = set(pessoa_ids) if pessoa_ids is not None else set(saldos) | set(partes)
    saida: dict[int, dict] = {}
    for pid in alvo:
        saldo = saldos.get(pid, 0.0)
        times = partes.get(pid, [])
        if saldo == 0 and not times:
            continue
        saida[pid] = {"saldo_individual": saldo, "times": times}
    return saida


def registrar_saida_dos_times(session: Session, pessoa: Pessoa, data_saida: date, fazenda_id: int | None) -> None:
    """Rescisão: a pessoa deixa os caixas do time na data do desligamento, mas CONTA os
    dias em que participou (continua no rateio do período, só até a saída). Quem entrava
    por tipo vira membro por nome já encerrado, para não sumir do rateio ao ser inativado."""
    query = select(CaixaTime).where(CaixaTime.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(CaixaTime.fazenda_id == fazenda_id)
    grupos = set(grupos_da_pessoa(pessoa))
    for t in session.exec(query).all():
        m = session.exec(select(CaixaTimeMembro).where(
            CaixaTimeMembro.time_id == t.id, CaixaTimeMembro.pessoa_id == pessoa.id)).first()
        por_tipo = bool(grupos & {x for x in (t.auto_tipos or "").split(",") if x})
        if m is None and not por_tipo:
            continue
        if m is None:
            m = CaixaTimeMembro(fazenda_id=fazenda_id, time_id=t.id, pessoa_id=pessoa.id,
                                entrada=pessoa.data_admissao or data_saida)
        if m.saida is None or m.saida > data_saida:
            m.saida = data_saida
        session.add(m)


DIAS_AVISO_RATEIO = 15


def rateios_proximos(session: Session, fazenda_id: int | None, hoje: date | None = None,
                     dias: int = DIAS_AVISO_RATEIO) -> list[dict]:
    """Caixas do time com saldo cuja próxima data de rateio cai nos próximos `dias` dias
    e que ainda não têm rascunho aberto — é o que a Agenda lembra de preparar."""
    from fazenda.models import CaixaRateio
    from fazenda.rules import parametros

    hoje = hoje or date.today()
    entrega = proxima_entrega(hoje, parametros.caixa_time_datas_entrega())
    faltam = (entrega - hoje).days
    if faltam > dias:
        return []
    query = select(CaixaTime).where(CaixaTime.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(CaixaTime.fazenda_id == fazenda_id)
    saida = []
    for t in session.exec(query).all():
        saldo = saldo_do_time(session, t.id)
        if saldo <= 0:
            continue
        rascunho = session.exec(select(CaixaRateio).where(
            CaixaRateio.time_id == t.id, CaixaRateio.situacao == "rascunho")).first()
        if rascunho is not None:
            continue
        saida.append({"time_id": t.id, "nome": t.nome, "saldo": saldo, "entrega": entrega, "faltam": faltam})
    return saida
