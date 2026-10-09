"""
Tela "Classificar" (Relatórios › Resultado): a fila do que a DRE deixa de fora
por falta de classificação e o lote de ações que resolve a fila.

Duas peças, as duas lendo a MESMA lista de registros que a DRE usa
(`financeiro._registros_dre_para_cascata`) e as MESMAS regras do motor
(`rules/dre.py::montar_cascata_dre`), para a fila fechar com a DRE:

1. FILA (`montar_pendencias`) — uma linha por lançamento/item, com o motivo,
   os ids para gravar, o que há hoje e uma SUGESTÃO (nunca aplicada sozinha):

   | motivo                      | o que é                                          | como se resolve        |
   |-----------------------------|--------------------------------------------------|------------------------|
   | conta_sem_linha_dre         | a conta não tem linha da DRE (nem herdada)       | linha da DRE da conta  |
   | sem_codigo_conta            | o lançamento/item não tem conta gerencial        | escolher a conta       |
   | item_sem_conta_automatica   | folha/contrato/diária gerado sem conta           | escolher a conta       |
   | natureza_nao_informada      | conta fora da DRE sem dizer o motivo (só v2)     | escolher a natureza    |

2. LOTE (`aplicar_acoes`) — ações `conta` | `natureza` | `linha_dre`, validadas
   TODAS antes de gravar qualquer coisa (tudo ou nada), com uma linha em
   `migracao_log_financeiro` por campo mudado (antes/depois, lote, motivo) —
   é por esse log que `reverter_lote` desfaz o lote inteiro.

Regras que valem aqui:
  - nada muda de número com a flag `financeiro_regras_v2` desligada: a fila só
    lista o que a regra antiga também enxerga (conta sem linha / sem conta) e a
    natureza fica TRAVADA, com o porquê (ela só tem efeito com as regras novas);
  - mês fechado (só com a flag): mexer em lançamento com competência ou
    pagamento no mês fechado exige reabrir — igual aos demais PUT do Financeiro.
    Ação sobre a CONTA DO PLANO (linha da DRE, natureza padrão) segue a regra já
    documentada do Fechamento: vale para todos os meses, não trava, e a
    resposta avisa quais meses fechados mudam;
  - nunca toca valor, data, pagamento nem conta bancária.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

from sqlmodel import Session, or_, select

from fazenda.rules import fechamento_mes, lancamento_automatico, saldo_conta
from fazenda.rules.dre import (
    CODIGOS_ATRIBUIVEIS, ESPECIFICACAO_LINHAS, LINHAS_DRE_VALIDAS, NAO_ENTRA_NA_DRE, resolver_linha_dre,
)
from fazenda.rules.migracao_log import novo_lote, registrar_mudanca
from fazenda.rules.natureza import (
    NAO_INFORMADA, OPERACIONAL, ROTULOS as ROTULOS_NATUREZA, inferir_natureza_por_nome, normalizar_natureza,
)
from fazenda.rules.parametros import regras_v2_ativas

MIGRACAO = "classificacao_manual_v1"
LIMITE_LINHAS = 1000   # linhas devolvidas pela fila (os totais contam todas)
LIMITE_ACOES = 500     # ações por lote

CONTA_SEM_LINHA_DRE = "conta_sem_linha_dre"
SEM_CODIGO_CONTA = "sem_codigo_conta"
ITEM_SEM_CONTA_AUTOMATICA = "item_sem_conta_automatica"
NATUREZA_NAO_INFORMADA = "natureza_nao_informada"

# Ordem de exibição na tela.
MOTIVOS: tuple[str, ...] = (CONTA_SEM_LINHA_DRE, SEM_CODIGO_CONTA, ITEM_SEM_CONTA_AUTOMATICA, NATUREZA_NAO_INFORMADA)

ROTULOS_MOTIVO: dict[str, str] = {
    CONTA_SEM_LINHA_DRE: "Conta sem linha da DRE",
    SEM_CODIGO_CONTA: "Lançamento sem conta",
    ITEM_SEM_CONTA_AUTOMATICA: "Folha e contratos sem conta",
    NATUREZA_NAO_INFORMADA: "Fora da DRE sem motivo",
}
EXPLICACAO_MOTIVO: dict[str, str] = {
    CONTA_SEM_LINHA_DRE: "A conta existe, mas não está ligada a nenhuma linha da DRE. Escolha a linha da conta: vale para todos os lançamentos dela.",
    SEM_CODIGO_CONTA: "O lançamento (ou o item dele) foi salvo sem conta gerencial. Escolha a conta certa.",
    ITEM_SEM_CONTA_AUTOMATICA: "Folha, férias, contrato, diária... criados pelo sistema sem uma conta configurada. Escolha a conta do item (ou configure a conta de cada origem em Parâmetros financeiros).",
    NATUREZA_NAO_INFORMADA: "A conta está marcada como “não entra na DRE”, mas ninguém disse por quê. Diga o motivo (investimento, financiamento, capital...).",
}
PORQUE_NATUREZA_SO_V2 = (
    "A natureza (investimento, financiamento, capital...) só muda os relatórios com as regras novas ligadas "
    "em Parâmetros financeiros. Com as regras antigas ela não é lida, por isso fica travada aqui."
)
PORQUE_SEM_AUTOMATICO_V1 = (
    "Folha, contratos e diárias gerados pelo sistema só entram na DRE com as regras novas ligadas; "
    "com as regras antigas não há o que classificar aqui."
)

ROTULOS_LINHA: dict[str, str] = {chave: rotulo for chave, rotulo, _op, sub in ESPECIFICACAO_LINHAS if not sub}
ROTULOS_LINHA[NAO_ENTRA_NA_DRE] = "Não entra na DRE"


# ═══════════════════════════ texto, sugestões (puras) ═══════════════════════════
def _norm(texto: str | None) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem.lower()).strip()


# (linha, tipos em que vale, padrão) — a primeira que casar vale. Só SUGESTÃO.
_PADROES_LINHA: tuple[tuple[str, tuple[str, ...], re.Pattern], ...] = (
    ("TRIBUTOS_IR_CSLL", ("despesa",), re.compile(r"\b(irpj|csll|imposto de renda)\b")),
    ("DEPRECIACAO_AMORT_EXAUSTAO", ("despesa",), re.compile(r"\b(depreciac\w*|exaustao)\b")),
    ("OUTRAS_REC_DESP", ("despesa", "receita"), re.compile(r"\b(juros?|multas?|mora|iof|tarifas? bancari\w*|rendimentos? (de )?aplicac\w*)\b")),
    ("GASTOS_PESSOAL", ("despesa",), re.compile(
        r"\b(salarios?|folha|ferias|13o|decimo terceiro|rescis\w*|fgts|inss|encargos? (sociais|trabalhist\w*)|mao de obra|diaristas?|empreit\w*|pro.?labore)\b")),
    ("DEDUCAO_IMPOSTOS", ("receita", "despesa"), re.compile(r"\b(funrural|senar|icms|cofins|pis)\b")),
    ("RECEITA_VENDAS", ("receita",), re.compile(r"\b(vendas?|leite|bezerr\w*|novilh\w*|descarte|animais|animal|receita)\b")),
    ("CUSTO_VARIAVEL", ("despesa",), re.compile(
        r"\b(racao|racoes|silagem|concentrado|volumoso|sal mineral|mineral|nucleo|farelo|milho|soja|feno|ureia|semen|"
        r"inseminac\w*|medicament\w*|vacinas?|veterinari\w*|sanidade|antibiotic\w*|alimentac\w*)\b")),
    ("DESPESA_VARIAVEL", ("despesa",), re.compile(r"\b(frete|fretes|comissao|comissoes|embalagens?)\b")),
    ("DESPESAS_OPERACIONAIS", ("despesa",), re.compile(
        r"\b(energia|luz|agua|telefone|internet|aluguel|arrendamento|manutenc\w*|conserto|reparos?|pecas?|"
        r"contabil\w*|contador|honorarios?|seguros?|limpeza|combustiv\w*|diesel|lubrificantes?|pneus?|administrativ\w*)\b")),
)


def sugerir_linha_dre(
    codigo: str, nome: str | None, tipo: str | None, mapa_linha: dict[str, str], codigos_plano: Iterable[str],
) -> dict | None:
    """Linha da DRE sugerida para uma conta sem linha. Duas fontes, nesta ordem:
    (1) as irmãs da conta (mesmo pai) que já têm linha e concordam todas;
    (2) o nome da conta. Devolve {linha, rotulo, motivo} ou None. Nunca aplica."""
    pai = codigo.rsplit(".", 1)[0] if "." in codigo else ""
    irmas = [c for c in codigos_plano if c != codigo and (c.rsplit(".", 1)[0] if "." in c else "") == pai]
    linhas = {resolver_linha_dre(c, mapa_linha) for c in irmas} - {None}
    if len(linhas) == 1:
        linha = next(iter(linhas))
        com_linha = sum(1 for c in irmas if resolver_linha_dre(c, mapa_linha))
        onde = f"de {pai}" if pai else "do mesmo nível"
        rotulo = ROTULOS_LINHA.get(linha, linha)
        return {
            "linha": linha, "rotulo": rotulo,
            "motivo": f"As outras {com_linha} conta{'s' if com_linha != 1 else ''} {onde} já estão em “{rotulo}”.",
        }
    texto = _norm(nome)
    if not texto:
        return None
    natureza, _motivo = inferir_natureza_por_nome(nome)
    if natureza:
        return {
            "linha": NAO_ENTRA_NA_DRE, "rotulo": ROTULOS_LINHA[NAO_ENTRA_NA_DRE],
            "motivo": f"Pelo nome da conta (“{nome}”): {ROTULOS_NATUREZA[natureza].split(' (')[0].lower()} não é custo nem receita da atividade.",
        }
    for linha, tipos, padrao in _PADROES_LINHA:
        if tipo and tipo not in tipos:
            continue
        if padrao.search(texto):
            return {
                "linha": linha, "rotulo": ROTULOS_LINHA[linha],
                "motivo": f"Pelo nome da conta (“{nome}”), costuma ir em “{ROTULOS_LINHA[linha]}”.",
            }
    return None


def motivo_do_registro(registro: dict, mapa_linha: dict[str, str], regras_v2: bool) -> str | None:
    """O motivo pelo qual o registro da DRE fica sem classificação — o espelho de
    `montar_cascata_dre`: só devolve motivo para o que o motor joga em
    `nao_classificado` (ou, com as regras novas, em “fora da DRE, motivo não
    informado”). None = o registro está resolvido."""
    if not (registro.get("valor") or 0):
        return None
    codigo = registro.get("codigo_conta")
    linha = resolver_linha_dre(codigo, mapa_linha)
    if regras_v2:
        if registro.get("linha_forcada") in CODIGOS_ATRIBUIVEIS:
            return None  # pseudoconta (juros/desconto da baixa, dedução da nota, multa da guia)
        natureza = registro.get("natureza") or OPERACIONAL
        if natureza == OPERACIONAL and linha == NAO_ENTRA_NA_DRE:
            natureza = NAO_INFORMADA
        if natureza == NAO_INFORMADA:
            return NATUREZA_NAO_INFORMADA
        if natureza != OPERACIONAL:
            return None  # fora da DRE COM motivo: resolvido
    if linha == NAO_ENTRA_NA_DRE or linha in CODIGOS_ATRIBUIVEIS:
        return None
    if not codigo:
        return SEM_CODIGO_CONTA
    if registro.get("papel") and codigo.startswith("(sem conta"):
        return ITEM_SEM_CONTA_AUTOMATICA
    return CONTA_SEM_LINHA_DRE


def _folha(codigo: str, codigos: Iterable[str]) -> bool:
    prefixo = codigo + "."
    return not any(c.startswith(prefixo) for c in codigos)


# ═══════════════════════════ a fila ═══════════════════════════════════════════
def _data_de_referencia(c, regime: str, regras_v2: bool) -> date | None:
    if regime == "competencia":
        return c.data_competencia
    return saldo_conta.data_caixa(c) if regras_v2 else c.data_pagamento


def _historico_por_fornecedor(session: Session, fazenda_id: int, fornecedores: set[str]) -> dict[tuple[str, str], Counter]:
    """{(fornecedor, tipo): Counter(codigo → nº de notas)} do histórico da própria
    fazenda: em que conta cada fornecedor costuma ser lançado. Uma nota conta uma
    vez por conta (várias parcelas = uma nota). Só leitura."""
    from fazenda.models import ContaGerencial, LancamentoItem

    if not fornecedores:
        return {}
    notas: dict[str, tuple[str, str, str | None]] = {}
    for cid, numero, forn, tipo, cod in session.exec(
        select(ContaGerencial.id, ContaGerencial.numero_lancamento, ContaGerencial.fornecedor_cliente,
               ContaGerencial.tipo, ContaGerencial.codigo_conta).where(
            ContaGerencial.fazenda_id == fazenda_id, ContaGerencial.fornecedor_cliente.in_(sorted(fornecedores)))
    ).all():
        notas.setdefault(numero or f"id{cid}", (forn, tipo or "", cod))
    codigos_itens: dict[str, set[str]] = {}
    numeros = [n for n in notas if not n.startswith("id")]
    for i in range(0, len(numeros), 500):
        for numero, cod in session.exec(
            select(LancamentoItem.numero_lancamento, LancamentoItem.codigo_conta_gerencial).where(
                LancamentoItem.fazenda_id == fazenda_id, LancamentoItem.numero_lancamento.in_(numeros[i:i + 500]),
                LancamentoItem.codigo_conta_gerencial.is_not(None))
        ).all():
            codigos_itens.setdefault(numero, set()).add(cod)
    historico: dict[tuple[str, str], Counter] = {}
    for numero, (forn, tipo, cod) in notas.items():
        codigos = codigos_itens.get(numero) or ({cod} if cod else set())
        for c in codigos:
            historico.setdefault((forn, tipo), Counter())[c] += 1
    return historico


def montar_pendencias(
    session: Session, fazenda_id: int, registros: list[dict], filtradas: list, mapa_linha: dict[str, str],
    *, regras_v2: bool, regime: str, limite: int = LIMITE_LINHAS,
) -> dict:
    """A fila de classificação de um período — `registros` e `filtradas` são os que
    a DRE usa (financeiro._registros_dre_para_cascata / _periodo_filtradas_dre).
    Só lê."""
    from fazenda.models import ContaGerencial, LancamentoItem, PlanoContaGerencial

    plano = list(session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.fazenda_id == fazenda_id)).all())
    plano_por_codigo = {p.codigo: p for p in plano}
    codigos_plano = [p.codigo for p in plano]
    contas_por_id = {c.id: c for c in filtradas}

    achados = [(m, r) for r in registros if (m := motivo_do_registro(r, mapa_linha, regras_v2))]
    item_ids = {r["item_id"] for _m, r in achados if r.get("item_id")}
    itens_por_id = {
        it.id: it for it in (session.exec(select(LancamentoItem).where(
            LancamentoItem.fazenda_id == fazenda_id, LancamentoItem.id.in_(sorted(item_ids)))).all() if item_ids else [])
    }
    numeros = {r["numero_lancamento"] for _m, r in achados if r.get("numero_lancamento")}
    parcelas_por_numero: dict[str, list] = {}
    for i in range(0, len(numeros), 500):
        for c in session.exec(select(ContaGerencial).where(
                ContaGerencial.fazenda_id == fazenda_id,
                ContaGerencial.numero_lancamento.in_(sorted(numeros)[i:i + 500]))).all():
            parcelas_por_numero.setdefault(c.numero_lancamento, []).append(c)
    fechados = fechamento_mes.meses_fechados(session, fazenda_id) if regras_v2 else set()

    # Uma linha por lançamento/item: as parcelas do mesmo item somam.
    linhas: dict[tuple[str, int | None], dict] = {}
    for motivo, r in achados:
        conta = contas_por_id.get(r.get("conta_id"))
        numero = r.get("numero_lancamento")
        item_id = r.get("item_id")
        chave = (numero or f"id{r.get('conta_id')}", item_id)
        linha = linhas.get(chave)
        if linha is None:
            item = itens_por_id.get(item_id) if item_id else None
            codigo = r.get("codigo_conta")
            no_plano = bool(codigo) and codigo in plano_por_codigo
            linha = linhas[chave] = {
                "chave": f"{chave[0]}|{item_id or 0}", "motivo": motivo,
                "numero_lancamento": numero, "conta_id": r.get("conta_id"), "item_id": item_id,
                "tipo": r.get("tipo") or (conta.tipo if conta else None) or "despesa",
                "valor": 0.0, "parcelas": 0, "data": None,
                "fornecedor": conta.fornecedor_cliente if conta else None,
                "descricao": conta.descricao if conta else None,
                "produto": item.produto if item else None,
                "centro_custo": (item.centro_custo if item and item.centro_custo else (conta.centro_custo if conta else None)),
                "codigo_conta": codigo, "nome_conta": plano_por_codigo[codigo].nome if no_plano else None,
                "conta_no_plano": no_plano,
                "natureza_atual": r.get("natureza") if regras_v2 else None,
                "origem_automatica": r.get("origem_automatica"),
                "mes_fechado": False, "meses_fechados": [],
                "_papel": r.get("papel"), "_plano": plano_por_codigo.get(codigo) if no_plano else None,
            }
        linha["valor"] = round(linha["valor"] + (r.get("valor") or 0.0), 2)
        linha["parcelas"] += 1
        if conta is not None:
            d = _data_de_referencia(conta, regime, regras_v2)
            if d is not None and (linha["data"] is None or d.isoformat() < linha["data"]):
                linha["data"] = d.isoformat()

    # Mês fechado: a ação sobre o lançamento mexe em TODAS as parcelas da nota.
    for linha in linhas.values():
        datas = [d for c in parcelas_por_numero.get(linha["numero_lancamento"], [])
                 for d in fechamento_mes.datas_do_lancamento(c)] if linha["numero_lancamento"] else []
        if not datas and linha["conta_id"] in contas_por_id:
            datas = fechamento_mes.datas_do_lancamento(contas_por_id[linha["conta_id"]])
        atingidos = sorted({fechamento_mes.mes_de(d) for d in datas if d} & fechados)
        linha["mes_fechado"] = bool(atingidos)
        linha["meses_fechados"] = atingidos

    historico = _historico_por_fornecedor(session, fazenda_id, {
        l["fornecedor"] for l in linhas.values() if l["motivo"] == SEM_CODIGO_CONTA and l["fornecedor"]})
    sugestao_conta_cache: dict[str, dict | None] = {}
    sugestao_linha_cache: dict[str, dict | None] = {}

    for linha in linhas.values():
        motivo = linha["motivo"]
        acoes = {"conta": True, "linha_dre": False, "natureza": False}
        travas: dict[str, str] = {}
        sugestao = None
        alvo_lanc = {"numero_lancamento": linha["numero_lancamento"], "item_id": linha["item_id"], "conta_id": linha["conta_id"]}
        if linha["mes_fechado"]:
            acoes["conta"] = False
            travas["conta"] = (
                f"{', '.join(fechamento_mes.nome_mes(m) for m in linha['meses_fechados'])} "
                f"{'está fechado' if len(linha['meses_fechados']) == 1 else 'estão fechados'}: reabra o mês em "
                "Relatórios › Fechamento do mês para mudar a conta deste lançamento."
            )
        if motivo == CONTA_SEM_LINHA_DRE and linha["conta_no_plano"]:
            acoes["linha_dre"] = True
        acoes["natureza"] = regras_v2
        if not regras_v2:
            travas["natureza"] = PORQUE_NATUREZA_SO_V2
        elif linha["mes_fechado"] and not linha["conta_no_plano"]:
            # Sem conta no plano, a natureza só pode ir no lançamento — e o mês fechado trava isso.
            acoes["natureza"] = False
            travas["natureza"] = travas.get("conta", "")
        if motivo == CONTA_SEM_LINHA_DRE and not linha["conta_no_plano"]:
            travas["linha_dre"] = f"A conta {linha['codigo_conta']} não existe no plano de contas desta fazenda: escolha uma conta do plano."

        # ── sugestão (nunca aplicada sozinha) ──
        codigo = linha["codigo_conta"]
        if motivo == CONTA_SEM_LINHA_DRE and linha["conta_no_plano"]:
            if codigo not in sugestao_linha_cache:
                sugestao_linha_cache[codigo] = sugerir_linha_dre(
                    codigo, linha["_plano"].nome, linha["tipo"], mapa_linha, codigos_plano)
            s = sugestao_linha_cache[codigo]
            if s:
                sugestao = {"tipo": "linha_dre", "alvo": {"codigo": codigo}, "valor": s["linha"],
                            "rotulo": f"Linha da DRE: {s['rotulo']}", "motivo": s["motivo"]}
        elif motivo == SEM_CODIGO_CONTA and linha["fornecedor"]:
            cont = historico.get((linha["fornecedor"], linha["tipo"] or ""))
            total = sum(cont.values()) if cont else 0
            if cont:
                for cod, n in cont.most_common():
                    p = plano_por_codigo.get(cod)
                    if p is None or p.ativa is False or not _folha(cod, codigos_plano):
                        continue
                    if n / total >= 0.5:
                        sugestao = {"tipo": "conta", "alvo": alvo_lanc, "valor": cod,
                                    "rotulo": f"Conta: {cod} {p.nome}",
                                    "motivo": f"{n} de {total} lançamento{'s' if total != 1 else ''} de {linha['fornecedor']} foram para esta conta."}
                    break
        elif motivo == ITEM_SEM_CONTA_AUTOMATICA:
            origem = lancamento_automatico.origem_do_papel(linha["_papel"])
            if origem:
                if origem not in sugestao_conta_cache:
                    sugestao_conta_cache[origem] = lancamento_automatico.sugerir_conta(origem, plano)
                s = sugestao_conta_cache[origem]
                if s and s["codigo"] in plano_por_codigo:
                    sugestao = {"tipo": "conta", "alvo": alvo_lanc, "valor": s["codigo"],
                                "rotulo": f"Conta: {s['codigo']} {s['nome']}",
                                "motivo": f"O nome da conta combina com a origem “{lancamento_automatico.ORIGENS[origem].rotulo}”."}
        elif motivo == NATUREZA_NAO_INFORMADA:
            nome_plano = linha["nome_conta"]
            for texto in (nome_plano, linha["descricao"], linha["produto"]):
                natureza, razao = inferir_natureza_por_nome(texto)
                if natureza:
                    alvo = {"codigo": codigo} if linha["conta_no_plano"] else alvo_lanc
                    sugestao = {"tipo": "natureza", "alvo": alvo, "valor": natureza,
                                "rotulo": f"Natureza: {ROTULOS_NATUREZA[natureza]}", "motivo": f"{razao.capitalize()}."}
                    break
        linha["acoes"], linha["travas"], linha["sugestao"] = acoes, travas, sugestao
        linha.pop("_papel", None)
        linha.pop("_plano", None)

    ordem = {m: i for i, m in enumerate(MOTIVOS)}
    todas = sorted(linhas.values(), key=lambda l: (ordem[l["motivo"]], l["codigo_conta"] or "", -l["valor"], l["chave"]))

    def somar(itens: list[dict]) -> tuple[float, float]:
        return (round(sum(l["valor"] for l in itens if l["tipo"] == "receita"), 2),
                round(sum(l["valor"] for l in itens if l["tipo"] != "receita"), 2))

    por_motivo = []
    for motivo in MOTIVOS:
        itens = [l for l in todas if l["motivo"] == motivo]
        rec, desp = somar(itens)
        travado = None
        if motivo == NATUREZA_NAO_INFORMADA and not regras_v2:
            travado = PORQUE_NATUREZA_SO_V2
        elif motivo == ITEM_SEM_CONTA_AUTOMATICA and not regras_v2:
            travado = PORQUE_SEM_AUTOMATICO_V1
        por_motivo.append({
            "motivo": motivo, "rotulo": ROTULOS_MOTIVO[motivo], "explicacao": EXPLICACAO_MOTIVO[motivo],
            "quantidade": len(itens), "contas": len({l["codigo_conta"] for l in itens}),
            "total_receita": rec, "total_despesa": desp, "travado": travado,
        })

    grupos: dict[tuple[str, str], dict] = {}
    for l in todas:
        g = grupos.setdefault((l["motivo"], l["codigo_conta"] or ""), {
            "motivo": l["motivo"], "codigo": l["codigo_conta"], "nome": l["nome_conta"],
            "conta_no_plano": l["conta_no_plano"], "quantidade": 0, "total_receita": 0.0, "total_despesa": 0.0,
            "sugestao": l["sugestao"] if l["sugestao"] and l["sugestao"]["tipo"] != "conta" else None,
        })
        g["quantidade"] += 1
        campo = "total_receita" if l["tipo"] == "receita" else "total_despesa"
        g[campo] = round(g[campo] + l["valor"], 2)

    rec, desp = somar(todas)
    return {
        "regras_v2": regras_v2,
        "resumo": {
            "total_pendencias": len(todas), "total_receita": rec, "total_despesa": desp,
            "mostradas": min(len(todas), limite), "truncado": len(todas) > limite,
        },
        "por_motivo": por_motivo,
        "por_conta": sorted(grupos.values(), key=lambda g: (ordem[g["motivo"]], g["codigo"] or "")),
        "pendencias": todas[:limite],
        "bloqueios": [{"motivo": m["motivo"], "porque": m["travado"]} for m in por_motivo if m["travado"]],
    }


def ultimo_lote(session: Session, fazenda_id: int) -> dict | None:
    """O último lote desta tela que ainda tem algo a desfazer (para o botão “Desfazer”)."""
    from fazenda.models import MigracaoLogFinanceiro

    base = select(MigracaoLogFinanceiro).where(
        MigracaoLogFinanceiro.fazenda_id == fazenda_id, MigracaoLogFinanceiro.migracao == MIGRACAO)
    ultima = session.exec(base.where(MigracaoLogFinanceiro.revertido_em.is_(None)).order_by(MigracaoLogFinanceiro.id.desc())).first()
    if ultima is None:
        return None
    linhas = session.exec(base.where(MigracaoLogFinanceiro.lote == ultima.lote)).all()
    pendentes = [l for l in linhas if l.revertido_em is None]
    return {
        "lote": ultima.lote, "criado_em": min(l.criado_em for l in linhas).isoformat(),
        "alteracoes": len(pendentes), "motivo": linhas[0].motivo,
    }


# ═══════════════════════════ o lote ═══════════════════════════════════════════
class ErroAcoes(Exception):
    """Lote recusado inteiro (nada foi gravado). `status` é o HTTP; `detalhe` vai no `detail`."""

    def __init__(self, status: int, detalhe: dict):
        super().__init__(detalhe.get("mensagem", ""))
        self.status = status
        self.detalhe = detalhe


@dataclass
class ResultadoLote:
    lote: str | None
    aplicadas: int = 0
    sem_mudanca: int = 0
    alteracoes: int = 0
    avisos: list[str] = field(default_factory=list)
    acoes: list[dict] = field(default_factory=list)


def _alvo_texto(alvo: dict) -> str:
    return alvo.get("codigo") or alvo.get("numero_lancamento") or f"conta #{alvo.get('conta_id')}"


def _meses_do_plano_em_uso(session: Session, fazenda_id: int, codigo: str, fechados: set[str]) -> list[str]:
    """Meses FECHADOS em que a conta do plano (ou uma filha) tem lançamento — só para AVISAR."""
    from fazenda.models import ContaGerencial, LancamentoItem

    if not fechados:
        return []
    padrao = codigo + ".%"
    numeros = set(session.exec(select(LancamentoItem.numero_lancamento).where(
        LancamentoItem.fazenda_id == fazenda_id,
        or_(LancamentoItem.codigo_conta_gerencial == codigo, LancamentoItem.codigo_conta_gerencial.like(padrao)))).all())
    criterios = [ContaGerencial.codigo_conta == codigo, ContaGerencial.codigo_conta.like(padrao)]
    if numeros:
        criterios.append(ContaGerencial.numero_lancamento.in_(sorted(numeros)))
    contas = session.exec(select(ContaGerencial).where(ContaGerencial.fazenda_id == fazenda_id, or_(*criterios))).all()
    datas = [d for c in contas for d in fechamento_mes.datas_do_lancamento(c) if d]
    return sorted({fechamento_mes.mes_de(d) for d in datas} & fechados)


def aplicar_acoes(
    session: Session, fazenda_id: int, acoes: list[dict], *, motivo: str | None = None,
) -> ResultadoLote:
    """Valida TODAS as ações e só então grava (tudo ou nada); não faz commit.

    Cada ação: {"tipo": "conta"|"natureza"|"linha_dre", "alvo": {...}, "valor": str}.
      - linha_dre: alvo {codigo} (conta do plano) · valor = uma das 9 linhas ou NAO_ENTRA_NA_DRE;
      - natureza:  alvo {codigo} (natureza PADRÃO da conta do plano) ou {numero_lancamento[, item_id]}
                   · valor = uma das 7 naturezas · só com as regras novas ligadas;
      - conta:     alvo {numero_lancamento, item_id} (o item) ou {numero_lancamento}/{conta_id} (nota
                   sem itens) · valor = código de uma conta-folha ativa do plano."""
    from fazenda.models import ContaGerencial, LancamentoItem, PlanoContaGerencial

    if not acoes:
        raise ErroAcoes(422, {"codigo": "lote_vazio", "mensagem": "Nenhuma ação para aplicar."})
    if len(acoes) > LIMITE_ACOES:
        raise ErroAcoes(422, {"codigo": "lote_grande", "mensagem": f"No máximo {LIMITE_ACOES} ações por vez."})

    regras_v2 = regras_v2_ativas(session, fazenda_id)
    fechados = fechamento_mes.meses_fechados(session, fazenda_id) if regras_v2 else set()
    plano = {p.codigo: p for p in session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.fazenda_id == fazenda_id)).all()}
    erros: list[dict] = []
    ops: list[dict] = []  # a execução, já resolvida

    def recusar(i: int, codigo: str, mensagem: str) -> None:
        erros.append({"indice": i, "codigo": codigo, "mensagem": mensagem})

    def notas(numero: str) -> list:
        return list(session.exec(select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == numero, ContaGerencial.fazenda_id == fazenda_id).order_by(ContaGerencial.id)).all())

    def itens(numero: str) -> list:
        return list(session.exec(select(LancamentoItem).where(
            LancamentoItem.numero_lancamento == numero, LancamentoItem.fazenda_id == fazenda_id).order_by(LancamentoItem.id)).all())

    def travado_pelo_mes(contas: list) -> list[str]:
        return sorted({fechamento_mes.mes_de(d) for c in contas for d in fechamento_mes.datas_do_lancamento(c) if d} & fechados)

    for i, a in enumerate(acoes):
        tipo = (a.get("tipo") or "").strip()
        alvo = a.get("alvo") or {}
        valor = a.get("valor")
        if tipo not in ("conta", "natureza", "linha_dre"):
            recusar(i, "tipo_invalido", f"Tipo de ação desconhecido: {tipo!r}. Use conta, natureza ou linha_dre.")
            continue

        if tipo == "linha_dre":
            if valor not in LINHAS_DRE_VALIDAS:
                recusar(i, "valor_invalido", f"Linha da DRE inválida: {valor!r}.")
                continue
            p = plano.get(alvo.get("codigo") or "")
            if p is None:
                recusar(i, "nao_encontrado", f"A conta {alvo.get('codigo')!r} não existe no plano de contas desta fazenda.")
                continue
            ops.append({"i": i, "tipo": tipo, "plano": p, "valor": valor})
            continue

        if tipo == "natureza":
            if not regras_v2:
                raise ErroAcoes(409, {"codigo": "regras_v2_desligadas", "mensagem": PORQUE_NATUREZA_SO_V2})
            try:
                natureza = normalizar_natureza(valor if isinstance(valor, str) else None)
            except ValueError as e:
                recusar(i, "valor_invalido", str(e))
                continue
            if natureza is None:
                recusar(i, "valor_invalido", "Informe a natureza.")
                continue
            if alvo.get("codigo"):
                p = plano.get(alvo["codigo"])
                if p is None:
                    recusar(i, "nao_encontrado", f"A conta {alvo['codigo']!r} não existe no plano de contas desta fazenda.")
                    continue
                ops.append({"i": i, "tipo": tipo, "plano": p, "valor": natureza})
                continue
            numero = alvo.get("numero_lancamento")
            contas = notas(numero) if numero else []
            if not contas:
                recusar(i, "nao_encontrado", "Lançamento não encontrado nesta fazenda.")
                continue
            atingidos = travado_pelo_mes(contas)
            if atingidos:
                erros.append({"indice": i, "codigo": "mes_fechado", "meses": atingidos,
                              "mensagem": f"{', '.join(fechamento_mes.nome_mes(m) for m in atingidos)} fechado: reabra o mês para mudar a natureza de {numero}."})
                continue
            item = None
            if alvo.get("item_id") is not None:
                item = next((it for it in itens(numero) if it.id == alvo["item_id"]), None)
                if item is None:
                    recusar(i, "nao_encontrado", f"O item {alvo['item_id']} não pertence ao lançamento {numero}.")
                    continue
            ops.append({"i": i, "tipo": tipo, "contas": contas, "item": item, "valor": natureza})
            continue

        # ── conta ──
        if not isinstance(valor, str) or not valor.strip():
            recusar(i, "valor_invalido", "Informe a conta gerencial.")
            continue
        destino = plano.get(valor.strip())
        if destino is None or destino.ativa is False:
            recusar(i, "nao_encontrado", f"A conta {valor!r} não existe (ou está inativa) no plano de contas desta fazenda.")
            continue
        if not _folha(destino.codigo, plano):
            recusar(i, "valor_invalido", f"{destino.codigo} {destino.nome} é um grupo: escolha uma conta de nível mais baixo.")
            continue
        numero = alvo.get("numero_lancamento")
        item = None
        if alvo.get("item_id") is not None:
            item = session.get(LancamentoItem, alvo["item_id"])
            if item is None or item.fazenda_id != fazenda_id or (numero and item.numero_lancamento != numero):
                recusar(i, "nao_encontrado", "Item não encontrado nesta fazenda.")
                continue
            numero = item.numero_lancamento
        if numero:
            contas = notas(numero)
        elif alvo.get("conta_id") is not None:
            c = session.get(ContaGerencial, alvo["conta_id"])
            contas = [c] if c is not None and c.fazenda_id == fazenda_id else []
        else:
            contas = []
        if not contas:
            recusar(i, "nao_encontrado", "Lançamento não encontrado nesta fazenda.")
            continue
        atingidos = travado_pelo_mes(contas)
        if atingidos:
            erros.append({"indice": i, "codigo": "mes_fechado", "meses": atingidos,
                          "mensagem": f"{', '.join(fechamento_mes.nome_mes(m) for m in atingidos)} fechado: reabra o mês para mudar a conta de {numero or 'este lançamento'}."})
            continue
        aviso = None
        if item is None and numero:
            # A DRE lê os itens: com itens, a conta é a do item. Itens GERADOS pelo sistema só valem com as
            # regras novas — com as antigas a DRE lê a nota, e a conta vai nela.
            lidos = [it for it in itens(numero) if regras_v2 or not it.gerado_por]
            if lidos:
                recusar(i, "valor_invalido", f"A nota {numero} tem itens: a conta é a do item (a DRE lê os itens). Aponte o item.")
                continue
            if itens(numero):
                aviso = (f"A nota {numero} tem itens gerados pelo sistema, que só valem com as regras novas: ao ligá-las, "
                         "a conta vem da configuração de Contas automáticas, não desta escolha.")
        ops.append({"i": i, "tipo": tipo, "contas": contas, "item": item, "numero": numero, "destino": destino, "aviso": aviso})

    if erros:
        so_mes = all(e["codigo"] == "mes_fechado" for e in erros)
        meses = sorted({m for e in erros for m in e.get("meses", [])})
        raise ErroAcoes(409 if so_mes else 422, {
            "codigo": "mes_fechado" if so_mes else "acoes_invalidas", "meses": meses, "erros": erros,
            "mensagem": (
                erros[0]["mensagem"] if len(erros) == 1
                else f"{len(erros)} ações não puderam ser aplicadas; nada foi gravado. Primeira: {erros[0]['mensagem']}"),
        })

    # ── gravar ──
    lote = novo_lote("classificacao")
    texto_motivo = "Classificação manual (tela Classificar)" + (f": {motivo.strip()}" if motivo and motivo.strip() else "")
    agora = datetime.utcnow()
    resultado = ResultadoLote(lote=lote)
    avisos_plano: dict[str, list[str]] = {}

    def mudar(tabela: str, registro, campo: str, novo: Any) -> bool:
        if getattr(registro, campo) == novo:
            return False
        registrar_mudanca(session, fazenda_id=fazenda_id, lote=lote, migracao=MIGRACAO, tabela=tabela,
                          registro=registro, campo=campo, valor_depois=novo, motivo=texto_motivo)
        if hasattr(registro, "atualizado_em"):
            registro.atualizado_em = agora
        resultado.alteracoes += 1
        return True

    for op in ops:
        mudou = False
        if op["tipo"] in ("linha_dre", "natureza") and "plano" in op:
            campo = "linha_dre" if op["tipo"] == "linha_dre" else "natureza_fin"
            mudou = mudar("plano_conta_gerencial", op["plano"], campo, op["valor"])
            if mudou and fechados:
                meses = _meses_do_plano_em_uso(session, fazenda_id, op["plano"].codigo, fechados)
                if meses:
                    avisos_plano[op["plano"].codigo] = meses
            descricao = f"{op['plano'].codigo} {op['plano'].nome}"
        elif op["tipo"] == "natureza":
            alvos = [op["item"]] if op["item"] is not None else op["contas"]
            for registro in alvos:
                tabela = "lancamento_item" if op["item"] is not None else "conta_gerencial"
                mudou = mudar(tabela, registro, "natureza_fin", op["valor"]) or mudou
            descricao = op["contas"][0].numero_lancamento or f"conta #{op['contas'][0].id}"
        else:
            destino = op["destino"]
            if op["item"] is not None:
                item = op["item"]
                antigo = item.codigo_conta_gerencial
                mudou = mudar("lancamento_item", item, "codigo_conta_gerencial", destino.codigo)
                mudou = mudar("lancamento_item", item, "nome_conta_gerencial", destino.nome) or mudou
                # Nota de um item só: o resumo da nota (`codigo_conta`) acompanha o item, como na criação.
                if op["numero"] and len(itens(op["numero"])) == 1:
                    for c in op["contas"]:
                        if (c.codigo_conta or None) == (antigo or None):
                            mudou = mudar("conta_gerencial", c, "codigo_conta", destino.codigo) or mudou
            else:
                for c in op["contas"]:
                    mudou = mudar("conta_gerencial", c, "codigo_conta", destino.codigo) or mudou
            descricao = op["numero"] or f"conta #{op['contas'][0].id}"
        if mudou and op.get("aviso"):
            resultado.avisos.append(op["aviso"])
        if mudou:
            resultado.aplicadas += 1
        else:
            resultado.sem_mudanca += 1
        resultado.acoes.append({"indice": op["i"], "tipo": op["tipo"], "mudou": mudou, "alvo": descricao})

    resultado.acoes.sort(key=lambda x: x["indice"])
    for codigo, meses in avisos_plano.items():
        resultado.avisos.append(
            f"A conta {codigo} tem lançamentos em {', '.join(fechamento_mes.nome_mes(m) for m in meses)} (já fechado"
            f"{'s' if len(meses) != 1 else ''}): os totais {'desses meses mudam' if len(meses) != 1 else 'desse mês mudam'}. "
            "A tela do Fechamento do mês mostra o aviso “mudou depois do fechamento”.")
    if resultado.alteracoes == 0:
        resultado.lote = None  # nada foi gravado: não há lote para desfazer
    return resultado


# ═══════════════════════════ desfazer ═════════════════════════════════════════
def datas_das_linhas_do_lote(session: Session, fazenda_id: int, linhas: list) -> list[date | None]:
    """Datas dos lançamentos que as linhas ainda não revertidas de um lote tocam (para a
    trava do mês fechado na reversão). Conta do plano não entra (mesma regra do lote)."""
    from fazenda.models import ContaGerencial, LancamentoItem

    datas: list[date | None] = []
    for l in linhas:
        if l.revertido_em is not None:
            continue
        if l.tabela == "conta_gerencial":
            c = session.get(ContaGerencial, l.registro_id)
            if c is not None and c.fazenda_id == fazenda_id:
                datas += fechamento_mes.datas_do_lancamento(c)
        elif l.tabela == "lancamento_item":
            it = session.get(LancamentoItem, l.registro_id)
            if it is not None and it.fazenda_id == fazenda_id and it.numero_lancamento:
                for c in session.exec(select(ContaGerencial).where(
                        ContaGerencial.numero_lancamento == it.numero_lancamento, ContaGerencial.fazenda_id == fazenda_id)).all():
                    datas += fechamento_mes.datas_do_lancamento(c)
    return datas
