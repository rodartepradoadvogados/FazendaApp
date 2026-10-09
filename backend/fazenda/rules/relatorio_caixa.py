"""
Relatórios do grupo CAIXA (Fase C1 do redesenho dos Relatórios do Financeiro):
fôlego do Caixa real, Fluxo de caixa mensal (realizado × previsto) e Livro
caixa da atividade rural. Funções PURAS — recebem os movimentos já lidos e
achatados; quem busca no banco é o router (fazenda/api/routers/relatorio_caixa.py).

Nenhuma regra nova de VALOR mora aqui: o valor de cada movimento (pago, em
aberto, data de caixa) é decidido no router com as mesmas funções do Caixa
Real e da DRE (rules/saldo_conta.py, rules/vale_item.py, calcular_dre). Aqui
só se agrupa por mês/dia/conta, acumula e soma.
"""
from __future__ import annotations

from datetime import date, timedelta

SEM_CONTA = "(sem conta)"


def r2(v: float) -> float:
    return round(v + 0.0, 2) + 0.0


def meses_entre(ini: date, fim: date) -> list[str]:
    """['AAAA-MM', ...] de `ini` a `fim`, inclusive (vazio se fim < ini)."""
    if fim < ini:
        return []
    out, a, m = [], ini.year, ini.month
    while (a, m) <= (fim.year, fim.month):
        out.append(f"{a:04d}-{m:02d}")
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return out


# ── Fôlego ───────────────────────────────────────────────────────────────
def folego(saldo_hoje: float, saidas_janela: float, dias_janela: int) -> dict:
    """Fôlego de caixa em dias = saldo de hoje ÷ saída média diária da janela
    (PLANO §5, indicador 9). Sem saída na janela não há média: `None` (a tela
    diz "sem saídas para medir"), nunca infinito. Saldo zero ou negativo: 0."""
    media = r2(saidas_janela / dias_janela) if dias_janela > 0 and saidas_janela > 0 else None
    if media is None:
        dias = None
    elif saldo_hoje <= 0:
        dias = 0
    else:
        dias = int(saldo_hoje // media)
    return {
        "saldo_hoje": r2(saldo_hoje), "saidas_janela": r2(saidas_janela), "dias_janela": dias_janela,
        "saida_media_diaria": media, "folego_dias": dias,
    }


# ── Fluxo de caixa ───────────────────────────────────────────────────────
def fluxo_de_caixa(movimentos: list[dict], ini: date, fim: date, hoje: date, *, por_dia: bool = False) -> dict:
    """Agrupa os movimentos de caixa do período por mês (e, com `por_dia`, por
    dia) e por conta gerencial.

    `movimentos`: dicts com `data` (date), `tipo` ("receita" entra, qualquer
    outro sai), `valor` (magnitude, > 0), `previsto` (bool: em aberto ou
    agendado — ainda não passou no banco), `vencido` (bool, só previsto),
    `codigo`/`conta` (conta gerencial, só para o detalhe por conta).
    Movimento fora de [ini, fim] é ignorado.

    O mês é `realizado` (terminou antes de hoje), `em_curso` (contém hoje) ou
    `projetado` (começa depois de hoje)."""
    meses = {m: {"competencia": m, "entradas": 0.0, "saidas": 0.0, "previsto_entradas": 0.0, "previsto_saidas": 0.0,
                 "vencidos": 0.0, "quantidade": 0} for m in meses_entre(ini, fim)}
    dias: dict[str, dict] = {}
    contas: dict[str, dict] = {}
    for mv in movimentos:
        d = mv["data"]
        if d is None or not (ini <= d <= fim):
            continue
        valor = abs(mv.get("valor") or 0.0)
        if not valor:
            continue
        entra = mv.get("tipo") == "receita"
        previsto = bool(mv.get("previsto"))
        chave_m = f"{d.year:04d}-{d.month:02d}"
        bm = meses[chave_m]
        campo = ("previsto_" if previsto else "") + ("entradas" if entra else "saidas")
        bm[campo] += valor
        bm["quantidade"] += 1
        if previsto and mv.get("vencido"):
            bm["vencidos"] += valor
        if por_dia:
            bd = dias.setdefault(d.isoformat(), {"data": d.isoformat(), "entradas": 0.0, "saidas": 0.0,
                                                 "previsto_entradas": 0.0, "previsto_saidas": 0.0})
            bd[campo] += valor
        if not previsto:
            codigo = mv.get("codigo") or SEM_CONTA
            bc = contas.setdefault(codigo, {"codigo": None if codigo == SEM_CONTA else codigo,
                                            "nome": mv.get("conta") or SEM_CONTA, "entradas": 0.0, "saidas": 0.0})
            bc["entradas" if entra else "saidas"] += valor

    lista = []
    for m in meses.values():
        ini_m = date(int(m["competencia"][:4]), int(m["competencia"][5:]), 1)
        fim_m = (date(ini_m.year + (ini_m.month == 12), ini_m.month % 12 + 1, 1) - timedelta(days=1))
        situacao = "realizado" if fim_m < hoje else ("projetado" if ini_m > hoje else "em_curso")
        for k in ("entradas", "saidas", "previsto_entradas", "previsto_saidas", "vencidos"):
            m[k] = r2(m[k])
        m["sobra"] = r2(m["entradas"] - m["saidas"])
        m["sobra_prevista"] = r2(m["sobra"] + m["previsto_entradas"] - m["previsto_saidas"])
        m["situacao"] = situacao
        lista.append(m)

    tot = {k: r2(sum(m[k] for m in lista)) for k in ("entradas", "saidas", "previsto_entradas", "previsto_saidas", "vencidos")}
    tot["sobra"] = r2(tot["entradas"] - tot["saidas"])
    tot["sobra_prevista"] = r2(tot["sobra"] + tot["previsto_entradas"] - tot["previsto_saidas"])

    out = {
        "meses": lista,
        "totais": tot,
        "contas": sorted(
            ({**c, "entradas": r2(c["entradas"]), "saidas": r2(c["saidas"]), "liquido": r2(c["entradas"] - c["saidas"])}
             for c in contas.values()),
            key=lambda c: (-(c["entradas"] + c["saidas"]), c["nome"]),
        ),
        "meses_com_movimento": sum(1 for m in lista if m["quantidade"]),
    }
    if por_dia:
        acumulado = 0.0
        lista_dias = []
        for k in sorted(dias):
            bd = dias[k]
            for c in ("entradas", "saidas", "previsto_entradas", "previsto_saidas"):
                bd[c] = r2(bd[c])
            bd["sobra"] = r2(bd["entradas"] - bd["saidas"] + bd["previsto_entradas"] - bd["previsto_saidas"])
            acumulado = r2(acumulado + bd["sobra"])
            bd["acumulado"] = acumulado
            lista_dias.append(bd)
        out["dias"] = lista_dias
    return out


def repartir_por_itens(valor: float, itens: list[tuple[str | None, str | None, float]]) -> list[tuple[str | None, str | None, float]]:
    """Reparte `valor` entre os itens (codigo, nome, peso) pelo peso — o último
    leva o resto, para a soma fechar no centavo. Sem peso positivo: devolve []."""
    total = sum(p for _c, _n, p in itens if p and p > 0)
    validos = [(c, n, p) for c, n, p in itens if p and p > 0]
    if total <= 0 or not validos:
        return []
    out, acumulado = [], 0.0
    for i, (c, n, p) in enumerate(validos):
        fatia = r2(valor - acumulado) if i == len(validos) - 1 else r2(valor * p / total)
        acumulado = r2(acumulado + fatia)
        out.append((c, n, fatia))
    return out


# ── Livro caixa da atividade rural ───────────────────────────────────────
CATEGORIAS_LIVRO = ("receita", "custeio", "investimento")


def montar_livro(lancamentos: list[dict], ini: date, fim: date) -> dict:
    """Livro caixa no formato do contador: cronológico (data, receita antes de
    despesa, id), com o saldo acumulado do período, os totais de cada mês e do
    período.

    `lancamentos`: dicts com `data`, `id`, `receita` e `custeio`/`investimento`
    (magnitudes já decididas pelo router — fiscal com as regras v2; com as
    regras antigas tudo o que saiu vai em `custeio` e `categoria` fica None) e
    os campos de texto (historico, fornecedor, documento, numero_lancamento)."""
    linhas = sorted(
        (x for x in lancamentos if x.get("data") is not None),
        key=lambda x: (x["data"], 0 if (x.get("receita") or 0) > 0 else 1, x.get("id") or 0),
    )
    meses = {m: {"competencia": m, "receitas": 0.0, "custeio": 0.0, "investimentos": 0.0, "quantidade": 0}
             for m in meses_entre(ini, fim)}
    saldo = 0.0
    out_linhas = []
    for x in linhas:
        rec = r2(x.get("receita") or 0.0)
        cus = r2(x.get("custeio") or 0.0)
        inv = r2(x.get("investimento") or 0.0)
        despesa = r2(cus + inv)
        if not rec and not despesa:
            continue
        saldo = r2(saldo + rec - despesa)
        chave = f"{x['data'].year:04d}-{x['data'].month:02d}"
        bm = meses.setdefault(chave, {"competencia": chave, "receitas": 0.0, "custeio": 0.0, "investimentos": 0.0, "quantidade": 0})
        bm["receitas"] += rec
        bm["custeio"] += cus
        bm["investimentos"] += inv
        bm["quantidade"] += 1
        out_linhas.append({
            "data": x["data"].isoformat(), "id": x.get("id"), "numero_lancamento": x.get("numero_lancamento"),
            "documento": x.get("documento"), "historico": x.get("historico") or "", "fornecedor": x.get("fornecedor") or "",
            "conta": x.get("conta"), "receita": rec, "despesa": despesa, "custeio": cus, "investimento": inv,
            "categoria": x.get("categoria"), "saldo": saldo,
        })
    lista_meses = []
    for k in sorted(meses):
        m = meses[k]
        for c in ("receitas", "custeio", "investimentos"):
            m[c] = r2(m[c])
        m["despesas"] = r2(m["custeio"] + m["investimentos"])
        m["resultado"] = r2(m["receitas"] - m["despesas"])
        lista_meses.append(m)
    receitas = r2(sum(m["receitas"] for m in lista_meses))
    custeio = r2(sum(m["custeio"] for m in lista_meses))
    investimentos = r2(sum(m["investimentos"] for m in lista_meses))
    return {
        "linhas": out_linhas,
        "meses": lista_meses,
        "totais": {
            "receitas": receitas, "custeio": custeio, "investimentos": investimentos,
            "despesas": r2(custeio + investimentos), "resultado": r2(receitas - custeio - investimentos),
            "quantidade": len(out_linhas),
        },
    }


def classificar_registro_livro(registro: dict, classificado: bool) -> tuple[str, float]:
    """Onde um registro da DRE de CAIXA (regras v2) cai no livro caixa da
    atividade rural. Devolve (destino, valor com sinal no resultado):

      - "receita" / "custeio" / "investimento": entra no livro;
      - "deducao": Funrural/Senar e descontos da nota de venda — a receita do
        livro é a BRUTA (como a DRE), e a dedução não é despesa paga;
      - "sem_conta": operacional sem linha da DRE — fora até ser classificado
        (a mesma regra da DRE: prefere o buraco a um número errado);
      - a natureza (FINANCIAMENTO, CAPITAL, TRANSFERENCIA, ADIANTAMENTO,
        OBRIGACAO, NAO_INFORMADA): fora do livro.

    Sinal: receita soma, o resto subtrai (item redutor e desconto obtido na
    baixa voltam com o tipo invertido e abatem a despesa da própria nota)."""
    from fazenda.rules import juros_descontos
    from fazenda.rules.natureza import INVESTIMENTO, OPERACIONAL

    valor = abs(registro.get("valor") or 0.0)
    sinal = 1.0 if registro.get("tipo") == "receita" else -1.0
    natureza = registro.get("natureza") or OPERACIONAL
    if registro.get("origem") == juros_descontos.ORIGEM_DEDUCAO_NOTA:
        # Dedução de uma venda fora da DRE (ex.: venda de bem) fica fora com a nota.
        return ("deducao" if natureza == OPERACIONAL else natureza), r2(sinal * valor)
    nota_receita = registro.get("tipo_nota") == "receita"
    if natureza == OPERACIONAL:
        if not classificado:
            return "sem_conta", r2(sinal * valor)
        return ("receita" if nota_receita else "custeio"), r2(sinal * valor)
    if natureza == INVESTIMENTO:
        return ("receita" if nota_receita else "investimento"), r2(sinal * valor)
    return natureza, r2(sinal * valor)
