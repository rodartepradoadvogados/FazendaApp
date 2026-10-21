"""
Ciclo — a "rodada" de uma caixa para um animal (modelo_v1 §12, "Ciclo").
O produtor não configura: o tipo de janela decide.

| Janela                         | Chave                         |
|--------------------------------|-------------------------------|
| Dose única na vida (idade)     | U                             |
| Pré-parto (cada gestação)      | G:{servico_id}                |
| Entrada em IA                  | IA:{AAAA-MM-DD}               |
| Parto / secagem / compra       | P: / S: / CP:{AAAA-MM-DD}     |
| Meses do ano                   | M:AAAA-MM  (grupo: M:AAAA-MM..MM — jun/jul = 1 dose) |
| Frequência (a cada N anos)     | F:AAAA                        |
| Contínuo sem evento            | C                             |
| Série (D1, D2...)              | doses dentro do MESMO ciclo (dose_num) |

Espelha `cicloDe`/`ciclosPeriodo`/`cicloEvento` do mockup aprovado (j1_core.js).
Tudo puro.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from fazenda.rules.sanitario.tipos import (
    FIM_NUNCA, HORIZONTE_EVENTO_DIAS, INICIO_SEMPRE, AnimalCtx, CaixaDef, Ciclo,
)

MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _fim_mes(ano: int, mes0: int) -> date:
    return date(ano, mes0 + 1, calendar.monthrange(ano, mes0 + 1)[1])


def _fmt(d: date) -> str:
    return d.strftime("%d/%m")


def chave_periodo(cx: CaixaDef, ano: int, grupo: list[int]) -> str:
    if cx.periodo_modo == "frequencia":
        return f"F:{ano}"
    if len(grupo) == 1:
        return f"M:{ano}-{grupo[0] + 1:02d}"
    return f"M:{ano}-{grupo[0] + 1:02d}..{grupo[-1] + 1:02d}"


def rotulo_grupo(grupo: list[int], ano: int) -> str:
    if len(grupo) > 1:
        return f"{MESES[grupo[0]]}–{MESES[grupo[-1]]}/{ano}"
    return f"{MESES[grupo[0]]}/{ano}"


def ciclos_periodo(cx: CaixaDef, de: date, ate: date) -> list[Ciclo]:
    """Ciclos de calendário (meses ou frequência) que tocam [de-1 ano, ate+1 ano]."""
    if not cx.eh_periodo:
        return []
    grupos = [sorted(int(m) for m in g) for g in cx.periodo_grupos if g]
    if cx.periodo_modo == "frequencia":
        grupos = grupos[:1]
    out: list[Ciclo] = []
    for ano in range(de.year - 1, ate.year + 2):
        if cx.periodo_modo == "frequencia":
            anos = max(int(cx.periodo_anos or 1), 1)
            base_ano = int(cx.periodo_ano_base or ano)
            if (ano - base_ano) % anos != 0:
                continue
        for g in grupos:
            ini = date(ano, g[0] + 1, 1)
            fim = _fim_mes(ano, g[-1])
            if cx.comecar_em and ini < cx.comecar_em:
                continue
            base = date(ano, g[0] + 1, min(max(int(cx.data_base_dia or 15), 1), 28))
            out.append(Ciclo(
                chave=chave_periodo(cx, ano, g), ini=ini, fim=fim, base=base,
                rotulo=rotulo_grupo(g, ano), per=True,
            ))
    return sorted(out, key=lambda c: c.ini)


def ciclo_evento(cx: CaixaDef, a: AnimalCtx, ref: date) -> Optional[Ciclo]:
    """Ciclo da janela por evento de vida, ou None quando o evento não existe
    (sem parto previsto, não entrou em IA, sem data de nascimento...)."""
    tipo = cx.evento_tipo
    de = int(cx.evento_de_dias or 0)
    ate = int(cx.evento_ate_dias or 0)
    c: Optional[Ciclo] = None
    if tipo == "idade":
        if a.nasc is None:
            return None
        ini, fim = a.nasc + timedelta(days=de), a.nasc + timedelta(days=ate)
        c = Ciclo(chave="U", ini=ini, fim=fim, base=ini, rotulo="única")
    elif tipo == "pre_parto":
        g = a.gestacao_atual()
        if g is None:
            return None
        ini = g.parto_previsto + timedelta(days=de)
        if g.parto_real is not None:
            # Pariu: a janela fechou na véspera do parto real (no dia do
            # parto a vacina de pré-parto já não cumpre o papel).
            fim, aberta = max(g.parto_real - timedelta(days=1), ini), False
        else:
            fim, aberta = max(g.parto_previsto, ref), True
        c = Ciclo(
            chave=f"G:{g.servico_id}", ini=ini, fim=fim, base=ini, aberta=aberta, fim_prev=g.parto_previsto,
            rotulo=f"gestação · parto {_fmt(g.parto_previsto)}",
        )
    elif tipo in ("entrada_ia", "parto", "secagem", "compra"):
        if tipo == "entrada_ia":
            marco, prefixo, nome = a.entrada_ia, "IA", "entrada em IA"
        elif tipo == "parto":
            marco, prefixo, nome = (max(a.partos) if a.partos else None), "P", "parto"
        elif tipo == "secagem":
            marco, prefixo, nome = (max(a.secagens) if a.secagens else None), "S", "secagem"
        else:
            marco, prefixo, nome = a.compra, "CP", "compra"
        if marco is None:
            return None
        ini, fim = marco + timedelta(days=de), marco + timedelta(days=ate)
        c = Ciclo(
            chave=f"{prefixo}:{marco.isoformat()}", ini=ini, fim=fim, base=ini,
            rotulo=f"{nome} {marco.strftime('%d/%m/%Y')}",
        )
    if c is None:
        return None
    # Janela que fechou há muito tempo deixa de ser acompanhada.
    if not c.aberta and c.fim < ref - timedelta(days=HORIZONTE_EVENTO_DIAS):
        return None
    return c


def ciclo_de(cx: CaixaDef, a: AnimalCtx, ref: date, modo: str = "proximo") -> Optional[Ciclo]:
    """`proximo`: o ciclo vigente ou o próximo; `ultimo`: o último que já começou."""
    if cx.eh_periodo:
        lista = ciclos_periodo(cx, ref - timedelta(days=420), ref + timedelta(days=1500))
        if modo == "proximo":
            return next((c for c in lista if c.fim >= ref), None)
        return next((c for c in reversed(lista) if c.ini <= ref), None)
    if cx.jan_usa_evento and cx.evento_tipo:
        return ciclo_evento(cx, a, ref)
    return Ciclo(chave="C", ini=INICIO_SEMPRE, fim=FIM_NUNCA, base=ref, rotulo="contínuo")


def sem_ciclo_txt(cx: CaixaDef) -> str:
    t = cx.evento_tipo
    if t == "pre_parto":
        return "Sem parto previsto"
    if t == "entrada_ia":
        return "Não entrou em IA"
    if t == "idade":
        return "Sem data de nascimento ou janela de idade encerrada há mais de 1 ano"
    if t == "parto":
        return "Sem parto"
    if t == "secagem":
        return "Sem secagem"
    if t == "compra":
        return "Não foi comprado"
    return "Sem ciclo"


def janela_txt(cx: CaixaDef, a: AnimalCtx, c: Optional[Ciclo]) -> str:
    if c is None:
        return sem_ciclo_txt(cx)
    if c.per:
        return f"Ciclo {c.rotulo}: {_fmt(c.ini)} a {_fmt(c.fim)} · data-base {_fmt(c.base)}"
    if c.chave == "C":
        return "Contínuo"
    t = cx.evento_tipo
    if t == "idade":
        de_m = round((cx.evento_de_dias or 0) / 30.44)
        ate_m = round((cx.evento_ate_dias or 0) / 30.44)
        return f"Janela de {de_m} a {ate_m} meses ({_fmt(c.ini)} a {_fmt(c.fim)})"
    if t == "pre_parto":
        extra = " (parto previsto já passou e ainda não pariu)" if c.aberta and c.fim_prev and c.fim_prev < a.hoje else ""
        return f"Pré-parto desde {_fmt(c.ini)} até o parto real{extra}"
    return f"{c.rotulo[:1].upper()}{c.rotulo[1:]} · janela {_fmt(c.ini)} a {_fmt(c.fim)}"
