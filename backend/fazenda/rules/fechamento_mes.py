"""
Fechamento do mês (Fase C5 — docs/financeiro-fechamento-conciliacao.md).

Três peças:
1. ESTADO: o mês está aberto ou fechado = o último evento da trilha
   append-only `fechamento_mes_evento` daquela fazenda e mês.
2. TRAVA: `exigir_meses_abertos` — com a flag `financeiro_regras_v2` LIGADA e
   o mês fechado, editar, dar baixa, estornar ou excluir lançamento com
   competência ou pagamento naquele mês responde 409 ("reabra com motivo").
   Flag desligada (ou fazenda sem fechamento nenhum): não faz nada — o
   comportamento de hoje, e os goldens, ficam intactos.
3. CHECKLIST e RETRATO: as conferências do mês calculadas ao vivo (sem conta,
   natureza, contas automáticas, saldo de abertura, faturas do cartão, folha,
   conciliação, depreciação) e o retrato dos totais (DRE de competência e de
   caixa, movimento e saldos) cujo SHA-256 vai para a trilha no fechamento.

Nada aqui reescreve valor histórico: fechar só grava uma linha na trilha.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import date
from typing import Iterable

from fastapi import HTTPException
from sqlmodel import Session, select

from fazenda.models import (
    ContaCorrente, FaturaCartao, CartaoCredito, FechamentoMesEvento, FolhaPagamento, ContaGerencial,
)
from fazenda.rules import saldo_conta
from fazenda.rules.datas import hoje_local
from fazenda.rules.parametros import regras_v2_ativas

RE_MES = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
            "outubro", "novembro", "dezembro"]


def limites_do_mes(mes: str) -> tuple[date, date]:
    m = RE_MES.match(mes or "")
    if not m:
        raise HTTPException(status_code=422, detail="Mês inválido: use AAAA-MM (ex.: 2026-09).")
    ano, mm = int(m.group(1)), int(m.group(2))
    return date(ano, mm, 1), date(ano, mm, calendar.monthrange(ano, mm)[1])


def mes_de(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def nome_mes(mes: str) -> str:
    ano, mm = mes.split("-")
    return f"{MESES_PT[int(mm) - 1]}/{ano}"


# ── estado ────────────────────────────────────────────────────────────────
def eventos(session: Session, fazenda_id: int, mes: str | None = None) -> list[FechamentoMesEvento]:
    q = select(FechamentoMesEvento).where(FechamentoMesEvento.fazenda_id == fazenda_id)
    if mes:
        q = q.where(FechamentoMesEvento.mes == mes)
    return list(session.exec(q.order_by(FechamentoMesEvento.id)).all())


def ultimo_evento_por_mes(session: Session, fazenda_id: int) -> dict[str, FechamentoMesEvento]:
    ultimo: dict[str, FechamentoMesEvento] = {}
    for ev in eventos(session, fazenda_id):
        ultimo[ev.mes] = ev  # em ordem de id: o último sobrescreve
    return ultimo


def meses_fechados(session: Session, fazenda_id: int | None) -> set[str]:
    if not isinstance(fazenda_id, int):
        return set()
    return {m for m, ev in ultimo_evento_por_mes(session, fazenda_id).items() if ev.acao == "fechar"}


def esta_fechado(session: Session, fazenda_id: int, mes: str) -> FechamentoMesEvento | None:
    evs = eventos(session, fazenda_id, mes)
    return evs[-1] if evs and evs[-1].acao == "fechar" else None


# ── trava ─────────────────────────────────────────────────────────────────
def exigir_meses_abertos(session: Session, fazenda_id: int | None, datas: Iterable[date | None], acao: str = "alterar") -> None:
    """409 se alguma data cair num mês FECHADO desta fazenda (só com a flag
    `financeiro_regras_v2`). `acao` entra na mensagem ("alterar", "dar baixa",
    "excluir"...)."""
    if not isinstance(fazenda_id, int):
        return
    datas = [d for d in datas if d is not None]
    if not datas or not regras_v2_ativas(session, fazenda_id):
        return
    fechados = meses_fechados(session, fazenda_id)
    if not fechados:
        return
    atingidos = sorted({mes_de(d) for d in datas} & fechados)
    if not atingidos:
        return
    nomes = ", ".join(nome_mes(m) for m in atingidos)
    plural = len(atingidos) > 1
    raise HTTPException(status_code=409, detail={
        "codigo": "mes_fechado", "meses": atingidos,
        "mensagem": (
            f"{nomes[0].upper()}{nomes[1:]} {'estão fechados' if plural else 'está fechado'}: para {acao} um lançamento "
            f"com competência ou pagamento {'nesses meses' if plural else 'nesse mês'}, um administrador precisa reabrir "
            "com motivo em Relatórios › Fechamento do mês (fica registrado na trilha)."
        ),
    })


def datas_do_lancamento(c: ContaGerencial) -> list[date | None]:
    """Competência e data de caixa (pagamento; cartão avulso = vencimento do cartão)."""
    return [c.data_competencia, c.data_pagamento, saldo_conta.data_caixa(c)]


# ── retrato ───────────────────────────────────────────────────────────────
def _linhas_cascata(dre: dict) -> dict[str, float]:
    return {l["chave"]: round(l["valor"] or 0.0, 2) for l in dre.get("cascata") or []}


def retrato(session: Session, fazenda_id: int, mes: str) -> dict:
    """Totais do mês que o fechamento congela na trilha (não grava nada)."""
    from fazenda.api.routers.financeiro import calcular_dre, saldos_contas_v2

    ini, fim = limites_do_mes(mes)
    v2 = regras_v2_ativas(session, fazenda_id)
    comp = calcular_dre(session, fazenda_id, ini, fim, None, "competencia", regras_v2=v2)
    cx = calcular_dre(session, fazenda_id, ini, fim, None, "caixa", regras_v2=v2)
    entradas = saidas = 0.0
    q = select(ContaGerencial).where(ContaGerencial.fazenda_id == fazenda_id, ContaGerencial.data_pagamento != None)  # noqa: E711
    for c in session.exec(q).all():
        dc = saldo_conta.data_caixa(c)
        if dc is None or not (ini <= dc <= fim) or not saldo_conta.conta_entra_no_caixa(c):
            continue
        v = saldo_conta.valor_pago_efetivo(c)
        if c.tipo == "receita":
            entradas += v
        else:
            saidas += v
    contas = list(session.exec(select(ContaCorrente).where(ContaCorrente.fazenda_id == fazenda_id).order_by(ContaCorrente.id)).all())
    saldos = {str(cid): s.saldo for cid, s in saldos_contas_v2(session, contas, fazenda_id, fim).items()}

    def bloco(d: dict) -> dict:
        nao = d.get("nao_classificado") or {}
        return {
            "linhas": _linhas_cascata(d),
            "nao_classificado": round(nao.get("total") or 0.0, 2),
            "fora_da_dre": round((d.get("fora_da_dre") or {}).get("total") or 0.0, 2),
        }

    return {
        "mes": mes, "regras_v2": v2,
        "dre_competencia": bloco(comp), "dre_caixa": bloco(cx),
        "caixa": {"entradas": round(entradas, 2), "saidas": round(saidas, 2), "saldos_fim_do_mes": saldos},
    }


def json_canonico(dados: dict) -> str:
    return json.dumps(dados, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_retrato(dados: dict) -> str:
    return hashlib.sha256(json_canonico(dados).encode("utf-8")).hexdigest()


# ── checklist ─────────────────────────────────────────────────────────────
def _item(id_: str, nome: str, txt: str, itens: list[dict], *, bloqueia: bool = True, destino: str | None = None,
          rotulo_acao: str | None = None, resumo: str | None = None) -> dict:
    return {
        "id": id_, "nome": nome, "txt": txt, "ok": not itens, "bloqueia": bloqueia, "itens": itens,
        "quantidade": len(itens), "destino": destino, "rotulo_acao": rotulo_acao, "resumo": resumo,
    }


def checklist(session: Session, fazenda_id: int, mes: str) -> list[dict]:
    """As conferências do mês, ao vivo. `bloqueia` = entra na conta do "Fechar"
    (o resto é aviso). Cada item diz onde resolver (`destino`)."""
    from fazenda.api.routers.financeiro import calcular_dre
    from fazenda.rules import conciliacao_banco

    ini, fim = limites_do_mes(mes)
    v2 = regras_v2_ativas(session, fazenda_id)
    comp = calcular_dre(session, fazenda_id, ini, fim, None, "competencia", regras_v2=v2)
    saida: list[dict] = []

    nao = comp.get("nao_classificado") or {}
    sem_conta = [{
        "codigo": c.get("codigo"), "nome": c.get("nome"),
        "receita": round(c.get("receita", 0.0) or 0.0, 2),
        "despesa": round(c.get("despesa", c.get("valor", 0.0)) or 0.0, 2),
    } for c in nao.get("contas") or []]
    saida.append(_item(
        "sem_conta", "Lançamentos sem conta ou sem linha da DRE",
        "Não entram em nenhuma linha da DRE até a conta ganhar uma linha (ou o lançamento ganhar uma conta).",
        sem_conta, destino="classificar", rotulo_acao="Classificar",
    ))
    saida.append(_item(
        "natureza", "Natureza a revisar",
        "Despesa marcada como investimento sem bem no Patrimônio: sai da DRE e não deprecia.",
        list(comp.get("pendencias_natureza") or []), destino="consultas", rotulo_acao="Revisar em Consultas",
    ))
    saida.append(_item(
        "contas_automaticas", "Contas automáticas configuradas",
        "Folha, contratos, diárias e vales gerados pelo sistema precisam de uma conta para entrar na linha certa da DRE.",
        [{"rotulo": p.get("rotulo"), "valor": p.get("valor"), "lancamentos": p.get("lancamentos")}
         for p in comp.get("pendencias_contas_automaticas") or []],
        destino="parametros_contas_automaticas", rotulo_acao="Configurar",
    ))
    contas = list(session.exec(select(ContaCorrente).where(
        ContaCorrente.fazenda_id == fazenda_id, ContaCorrente.ativo == True)).all())  # noqa: E712
    saida.append(_item(
        "saldo_abertura", "Saldo de abertura das contas correntes",
        "Sem o saldo de abertura conferido com o extrato, o saldo do sistema é só a soma dos lançamentos.",
        [{"conta_corrente_id": c.id, "conta": f"{c.banco} · Ag. {c.agencia} · C/C {c.numero_conta}"}
         for c in contas if c.saldo_abertura is None or c.data_saldo_abertura is None],
        destino="parametros_contas_correntes", rotulo_acao="Informar o saldo",
    ))
    faturas = session.exec(select(FaturaCartao).where(
        FaturaCartao.fazenda_id == fazenda_id, FaturaCartao.status == "aberta",
        FaturaCartao.data_fechamento <= fim)).all()
    apelidos = {c.id: c.apelido for c in session.exec(select(CartaoCredito).where(CartaoCredito.fazenda_id == fazenda_id)).all()}
    saida.append(_item(
        "cartao", "Faturas do cartão fechadas",
        "Fatura com data de fechamento até o fim do mês ainda aberta: compras podem estar faltando no mês.",
        [{"fatura_id": f.id, "cartao": apelidos.get(f.cartao_id, "Cartão"), "competencia": f.competencia,
          "data_fechamento": f.data_fechamento.isoformat()} for f in faturas],
        destino="cartao_credito", rotulo_acao="Fechar a fatura",
    ))
    folhas = session.exec(select(FolhaPagamento).where(
        FolhaPagamento.fazenda_id == fazenda_id, FolhaPagamento.competencia == mes,
        FolhaPagamento.status != "pago")).all()
    saida.append(_item(
        "folha", "Folha do mês fechada e paga",
        "Folha da competência ainda pendente: o custo de pessoal do mês pode mudar.",
        [{"folha_id": f.id, "valor_liquido": round(f.valor_liquido or 0.0, 2), "status": f.status} for f in folhas],
        destino="folha", rotulo_acao="Ir à folha", bloqueia=True,
    ))
    conc = conciliacao_banco.resumo_contas(session, fazenda_id, ini, fim)
    pend_conc = [{
        "conta_corrente_id": c["conta_corrente_id"], "conta": c["conta"], "importado": c["importado"],
        "pendentes": c["pendentes"], "diferenca": c["saldos"].get("diferenca"),
    } for c in conc if not c["conciliada"]]
    saida.append(_item(
        "conciliacao", "Conciliação bancária feita",
        "Extrato do mês importado em cada conta com movimento, sem linha pendente.",
        pend_conc, destino="conciliacao", rotulo_acao="Conciliar",
    ))
    dep = (comp.get("depreciacao_periodo") or {}).get("inconsistencias") or []
    saida.append(_item(
        "depreciacao", "Depreciação do mês calculada",
        "Bens sem data de imobilização ou vida útil reconhecida ficam fora da depreciação (a linha fica subestimada).",
        [{"item": i.get("item"), "numero": i.get("numero"), "motivo": i.get("motivo")} for i in dep],
        destino="patrimonio", rotulo_acao="Completar o cadastro do bem",
        resumo="Depreciação do mês: R$ " + f"{((comp.get('depreciacao_periodo') or {}).get('total') or 0.0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
    ))
    return saida


def situacao_do_mes(session: Session, fazenda_id: int, mes: str, *, com_checklist: bool = True) -> dict:
    """Tudo o que a tela do Fechamento precisa para um mês."""
    ini, fim = limites_do_mes(mes)
    v2 = regras_v2_ativas(session, fazenda_id)
    evs = eventos(session, fazenda_id, mes)
    ultimo = evs[-1] if evs else None
    fechado = bool(ultimo and ultimo.acao == "fechar")
    hoje = hoje_local()
    resposta = {
        "mes": mes, "inicio": ini.isoformat(), "fim": fim.isoformat(), "regras_v2": v2,
        "status": "fechado" if fechado else ("em_curso" if fim >= hoje else "aberto"),
        "pode_fechar_a_partir_de": date.fromordinal(fim.toordinal() + 1).isoformat(),
        "evento_atual": dump_evento(ultimo) if ultimo else None,
        "trilha_do_mes": [dump_evento(e) for e in reversed(evs)],
    }
    if com_checklist:
        cl = checklist(session, fazenda_id, mes)
        resposta["checklist"] = cl
        resposta["pendencias"] = sum(1 for c in cl if not c["ok"] and c["bloqueia"])
        atual = retrato(session, fazenda_id, mes)
        resposta["retrato_atual"] = atual
        resposta["retrato_atual_sha256"] = sha256_retrato(atual)
        if fechado and ultimo.retrato_sha256:
            resposta["retrato_fechamento"] = json.loads(ultimo.retrato_json) if ultimo.retrato_json else None
            resposta["mudou_desde_o_fechamento"] = ultimo.retrato_sha256 != resposta["retrato_atual_sha256"]
    return resposta


def dump_evento(e: FechamentoMesEvento) -> dict:
    return {
        "id": e.id, "mes": e.mes, "acao": e.acao, "motivo": e.motivo, "usuario": e.usuario_nome,
        "criado_em": e.criado_em.isoformat() if e.criado_em else None,
        "retrato_sha256": e.retrato_sha256, "pendencias_no_fechamento": e.pendencias_no_fechamento,
    }
