"""
Público da caixa — lista fechada (sexo, categorias POR ID, idade, condição,
histórico "já/nunca recebeu X"), avaliado como o animal ESTARÁ na data `d`.

Devolve a lista de motivos (ok, texto): o primeiro não-ok é o texto do "fora"
e do pop-up de consentimento. Puro.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.sanitario.tipos import AnimalCtx, CaixaDef, Motivo


def _fmt(d: date) -> str:
    return d.strftime("%d/%m")


def idade_txt(dias: int) -> str:
    if dias < 0:
        return "—"
    if dias < 730:
        m = int(dias // 30.44)
        return f"{m} m {round(dias - m * 30.44)} d"
    a = int(dias // 365.25)
    return f"{a} a {int((dias - a * 365.25) // 30.44)} m"


def prenhe_em(a: AnimalCtx, d: date) -> bool:
    """Prenhe na data d: até o parto REAL (inclusive) quando já pariu; sem
    parto ainda, até o previsto — ou até hoje, se o previsto já passou."""
    g = a.gestacao_atual()
    if g is None or d < g.data_servico:
        return False
    if g.parto_real is not None:
        return d <= g.parto_real
    return d <= g.parto_previsto or d <= a.hoje


def produtiva_em(a: AnimalCtx, d: date) -> str | None:
    """lactacao | seca | None (nunca pariu), projetando o parto previsto."""
    eventos = [(p, "lactacao") for p in a.partos if p <= d] + [(s, "seca") for s in a.secagens if s <= d]
    g = a.gestacao_atual()
    if g and g.parto_real is None and g.parto_previsto < d and d > a.hoje:
        eventos.append((g.parto_previsto, "lactacao"))
    if not eventos:
        return None
    return max(eventos)[1]


def apta_ia_em(a: AnimalCtx, d: date) -> bool:
    if a.sexo == "M" or prenhe_em(a, d):
        return False
    if a.partos:
        return True
    return a.nasc is not None and (d - a.nasc).days >= a.idade_apta_dias


def pre_parto_em(a: AnimalCtx, d: date, dias: int = 30) -> bool:
    g = a.gestacao_atual()
    return bool(prenhe_em(a, d) and g and d >= g.parto_previsto - timedelta(days=dias))


def ja_recebeu(a: AnimalCtx, caixa_id: int | None) -> bool:
    """Qualquer registro válido da caixa — inclusive "só registro" (planilha
    importada conta como histórico vacinal)."""
    return bool(caixa_id and a.registros_da_caixa(caixa_id))


def publico(cx: CaixaDef, a: AnimalCtx, d: date) -> list[Motivo]:
    R: list[Motivo] = []
    if not a.ativo:
        R.append(Motivo(False, a.saida_txt or "Saiu do rebanho", "saiu"))
    if cx.pub_sexo in ("F", "M"):
        txt = "Fêmea" if a.sexo == "F" else "Macho" if a.sexo == "M" else "Sexo não informado"
        R.append(Motivo(a.sexo == cx.pub_sexo, txt, "sexo"))
    if cx.categorias:
        cat_id, cat_nome = a.categoria_em(d)
        dentro = cat_id in cx.categorias
        ok = dentro if cx.pub_cat_modo != "excluir" else not dentro
        nome = cat_nome or "sem categoria"
        txt = f"Em {_fmt(d)} será {nome}" if d != a.hoje else f"Categoria: {nome}"
        R.append(Motivo(ok, txt, "categoria"))
    if cx.pub_idade_min_dias is not None or cx.pub_idade_max_dias is not None:
        if a.nasc is None:
            R.append(Motivo(False, "Sem data de nascimento", "idade"))
        else:
            idade = (d - a.nasc).days
            ok = (cx.pub_idade_min_dias is None or idade >= cx.pub_idade_min_dias) and (
                cx.pub_idade_max_dias is None or idade <= cx.pub_idade_max_dias)
            R.append(Motivo(ok, f"Idade em {_fmt(d)}: {idade_txt(idade)}", "idade"))
    for cond in cx.pub_condicoes:
        if cond == "prenhe":
            ok = prenhe_em(a, d)
            g = a.gestacao_atual()
            if ok and g:
                txt = f"Prenhe · parto previsto {_fmt(g.parto_previsto)}"
            elif g and g.parto_real is None and d > g.data_servico:
                txt = f"Terá parido em {_fmt(d)} (parto previsto {_fmt(g.parto_previsto)})"
            else:
                txt = "Não está prenhe"
            R.append(Motivo(ok, txt, "prenhe_parido" if (not ok and g and g.parto_real is None and d > g.data_servico) else "prenhe"))
        elif cond == "pre_parto":
            R.append(Motivo(pre_parto_em(a, d), "Pré-parto", "pre_parto"))
        elif cond == "lactacao":
            R.append(Motivo(produtiva_em(a, d) == "lactacao", "Em lactação", "lactacao"))
        elif cond == "seca":
            R.append(Motivo(produtiva_em(a, d) == "seca", "Seca", "seca"))
        elif cond == "apta_ia":
            R.append(Motivo(apta_ia_em(a, d), "Apta para IA", "apta_ia"))
    if cx.pub_hist_tipo in ("ja", "nunca") and cx.pub_hist_caixa_id:
        tem = ja_recebeu(a, cx.pub_hist_caixa_id)
        nome = cx.pub_hist_nome or "a vacina de referência"
        ok = tem if cx.pub_hist_tipo == "ja" else not tem
        R.append(Motivo(ok, f"Já recebeu {nome}" if tem else f"Nunca recebeu {nome}", "historico"))
    # Janela por evento E período ao mesmo tempo: o período gera o ciclo e o
    # evento vira filtro (ex.: idade dentro da faixa na data-base).
    if cx.eh_periodo and cx.jan_usa_evento and cx.evento_tipo == "idade":
        if a.nasc is None:
            R.append(Motivo(False, "Sem data de nascimento", "evento"))
        else:
            idade = (d - a.nasc).days
            ok = (cx.evento_de_dias or 0) <= idade <= (cx.evento_ate_dias if cx.evento_ate_dias is not None else idade)
            R.append(Motivo(ok, f"Idade em {_fmt(d)}: {idade_txt(idade)}", "evento"))
    return R
