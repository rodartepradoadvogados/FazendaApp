"""
Conciliação bancária — a parte que lê o banco de dados (a regra do casamento
é pura, em fazenda/rules/conciliacao.py). Usada pela tela de Conciliação
bancária, pelo checklist do Fechamento do mês e pelo Pacote do contador.

O "lado do sistema" de uma conta corrente num período é o mesmo dinheiro que
o saldo da conta enxerga (fazenda/rules/saldo_conta.py): lançamento PAGO cuja
data de caixa cai no período, casado pela FK `conta_corrente_id` (ou, no
histórico ainda não ligado, pelo rótulo exato da conta), valendo o valor
pago; e as transferências entre contas (saída na origem, entrada no destino).
A nota de classificação do backfill do cartão já pago não move dinheiro e
fica de fora. Lê sempre com as regras do saldo novo (abertura + movimento),
qualquer que seja a flag: a conciliação é uma tela nova e não muda número de
relatório nenhum.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, or_, select

from fazenda.models import ContaCorrente, ContaGerencial, ExtratoImportacao, ExtratoLinha, TransferenciaContas
from fazenda.rules import conciliacao, saldo_conta


def rotulo_conta(c: ContaCorrente) -> str:
    # Igual a financeiro.rotulo_conta_corrente (import local evitaria ciclo).
    return f"{c.banco} · Agência {c.agencia} · Conta corrente {c.numero_conta}"


def contas_da_fazenda(session: Session, fazenda_id: int, *, so_ativas: bool = True) -> list[ContaCorrente]:
    q = select(ContaCorrente).where(ContaCorrente.fazenda_id == fazenda_id)
    if so_ativas:
        q = q.where(ContaCorrente.ativo == True)  # noqa: E712
    return list(session.exec(q.order_by(ContaCorrente.id)).all())


def movimentos_sistema(session: Session, fazenda_id: int, conta: ContaCorrente, ini: date, fim: date) -> list[dict]:
    rotulo = rotulo_conta(conta)
    q = select(ContaGerencial).where(
        ContaGerencial.fazenda_id == fazenda_id,
        ContaGerencial.data_pagamento != None,  # noqa: E711
        or_(
            ContaGerencial.conta_corrente_id == conta.id,
            (ContaGerencial.conta_corrente_id == None) & (ContaGerencial.conta_bancaria == rotulo),  # noqa: E711
        ),
    )
    saida: list[dict] = []
    for c in session.exec(q).all():
        if not saldo_conta.conta_entra_no_caixa(c):
            continue
        dc = saldo_conta.data_caixa(c)
        if dc is None or not (ini <= dc <= fim):
            continue
        valor = saldo_conta.valor_pago_efetivo(c)
        if not valor:
            continue
        saida.append({
            "tipo": "lancamento", "id": c.id, "data": dc,
            "valor": round(valor if c.tipo == "receita" else -valor, 2),
            "descricao": c.descricao, "fornecedor": c.fornecedor_cliente,
            "numero_lancamento": c.numero_lancamento, "documento": c.numero_nota,
        })
    qt = select(TransferenciaContas).where(
        TransferenciaContas.fazenda_id == fazenda_id,
        or_(TransferenciaContas.conta_origem_id == conta.id, TransferenciaContas.conta_destino_id == conta.id),
    )
    for t in session.exec(qt).all():
        if t.data is None or not (ini <= t.data <= fim):
            continue
        entrada = t.conta_destino_id == conta.id
        saida.append({
            "tipo": "transferencia", "id": t.id, "data": t.data,
            "valor": round(t.valor if entrada else -t.valor, 2),
            "descricao": "Transferência entre contas" + (f" · {t.observacao}" if t.observacao else ""),
            "fornecedor": None, "numero_lancamento": None, "documento": None,
        })
    saida.sort(key=lambda m: (m["data"], m["tipo"], m["id"]))
    return saida


def linhas_extrato(session: Session, fazenda_id: int, conta_id: int, ini: date, fim: date) -> list[ExtratoLinha]:
    q = select(ExtratoLinha).where(
        ExtratoLinha.fazenda_id == fazenda_id, ExtratoLinha.conta_corrente_id == conta_id,
        ExtratoLinha.data >= ini, ExtratoLinha.data <= fim,
    ).order_by(ExtratoLinha.data, ExtratoLinha.id)
    return list(session.exec(q).all())


def pareados_da_conta(session: Session, fazenda_id: int, conta_id: int) -> tuple[set[int], set[int]]:
    """Ids de lançamentos e de transferências já pareados com alguma linha desta conta."""
    q = select(ExtratoLinha.lancamento_id, ExtratoLinha.transferencia_id).where(
        ExtratoLinha.fazenda_id == fazenda_id, ExtratoLinha.conta_corrente_id == conta_id,
        ExtratoLinha.status == "pareado",
    )
    lanc, transf = set(), set()
    for lid, tid in session.exec(q).all():
        if lid:
            lanc.add(lid)
        if tid:
            transf.add(tid)
    return lanc, transf


def saldo_extrato_ate(session: Session, fazenda_id: int, conta_id: int, ate: date) -> tuple[float | None, date | None]:
    """O saldo informado pelo banco mais recente até `ate` (OFX LEDGERBAL / linha de saldo do CSV)."""
    q = select(ExtratoImportacao).where(
        ExtratoImportacao.fazenda_id == fazenda_id, ExtratoImportacao.conta_corrente_id == conta_id,
        ExtratoImportacao.saldo_final != None, ExtratoImportacao.data_saldo != None,  # noqa: E711
        ExtratoImportacao.data_saldo <= ate,
    ).order_by(ExtratoImportacao.data_saldo.desc(), ExtratoImportacao.id.desc())
    imp = session.exec(q).first()
    return (imp.saldo_final, imp.data_saldo) if imp else (None, None)


def saldo_sistema_em(session: Session, fazenda_id: int, conta: ContaCorrente, ate: date) -> tuple[float, bool]:
    """Saldo da conta no fim do dia `ate` (regras do saldo novo) e se falta o saldo de abertura."""
    from fazenda.api.routers.financeiro import saldos_contas_v2  # import local: o router importa as rules

    s = saldos_contas_v2(session, [conta], fazenda_id, ate)[conta.id]
    return s.saldo, s.pendente_abertura


def _dump_linha(l: ExtratoLinha) -> dict:
    return {
        "id": l.id, "data": l.data.isoformat(), "valor": l.valor, "historico": l.historico,
        "documento": l.documento, "status": l.status, "lancamento_id": l.lancamento_id,
        "transferencia_id": l.transferencia_id, "observacao": l.observacao,
        "conciliado_em": l.conciliado_em.isoformat() if l.conciliado_em else None,
    }


def _dump_mov(m: dict) -> dict:
    return {**m, "data": m["data"].isoformat()}


def situacao(session: Session, fazenda_id: int, conta: ContaCorrente, ini: date, fim: date, *, com_sugestoes: bool = True) -> dict:
    """Extrato × sistema de uma conta num período: linhas com status e
    sugestão, movimentos do sistema sem par ("só no sistema"), saldos e
    contadores. A sugestão nunca é gravada aqui."""
    tol = timedelta(days=conciliacao.TOLERANCIA_DIAS)
    linhas = linhas_extrato(session, fazenda_id, conta.id, ini, fim)
    # Candidatos numa janela maior (a TED de 30/09 pode compensar em 01/10).
    sistema_janela = movimentos_sistema(session, fazenda_id, conta, ini - tol, fim + tol)
    lanc_par, transf_par = pareados_da_conta(session, fazenda_id, conta.id)
    livres = [m for m in sistema_janela
              if not ((m["tipo"] == "lancamento" and m["id"] in lanc_par) or (m["tipo"] == "transferencia" and m["id"] in transf_par))]
    pendentes = [l for l in linhas if l.status == "pendente"]
    sugestoes = conciliacao.sugerir(
        [{"id": l.id, "data": l.data, "valor": l.valor, "historico": l.historico} for l in pendentes], livres,
    ) if com_sugestoes and pendentes else {}
    sistema_mes = [m for m in sistema_janela if ini <= m["data"] <= fim]
    # "Só no sistema" = sem linha do extrato nem sugestão exata na fila (o sugerido espera confirmação).
    na_fila = {(v["sugestao"]["tipo"], v["sugestao"]["id"]) for v in sugestoes.values() if v.get("sugestao")}
    # Linha sem par exato mostra o candidato de "valor diferente" ao lado: ele também sai do "só no sistema".
    for v in sugestoes.values():
        if not v.get("sugestao"):
            alt = next((a for a in v.get("alternativas", []) if not a["exata"] and (a["tipo"], a["id"]) not in na_fila), None)
            if alt:
                na_fila.add((alt["tipo"], alt["id"]))
    so_no_sistema = [m for m in livres if ini <= m["data"] <= fim and (m["tipo"], m["id"]) not in na_fila]
    por_id = {(m["tipo"], m["id"]): m for m in sistema_janela}

    def par_de(l: ExtratoLinha) -> dict | None:
        if l.lancamento_id:
            m = por_id.get(("lancamento", l.lancamento_id))
            return _dump_mov(m) if m else {"tipo": "lancamento", "id": l.lancamento_id}
        if l.transferencia_id:
            m = por_id.get(("transferencia", l.transferencia_id))
            return _dump_mov(m) if m else {"tipo": "transferencia", "id": l.transferencia_id}
        return None

    saida_linhas = []
    for l in linhas:
        d = _dump_linha(l)
        d["par"] = par_de(l) if l.status == "pareado" else None
        s = sugestoes.get(l.id) or {}
        d["sugestao"] = _dump_mov(s["sugestao"]) if s.get("sugestao") else None
        d["alternativas"] = [_dump_mov(a) for a in s.get("alternativas", [])]
        saida_linhas.append(d)

    saldo_ext, data_saldo = saldo_extrato_ate(session, fazenda_id, conta.id, fim)
    # Compara na MESMA data (a do saldo informado pelo banco); sem saldo informado, no fim do período.
    data_cmp = data_saldo if data_saldo and data_saldo >= ini else fim
    if saldo_ext is not None and data_saldo is not None and data_saldo < ini:
        saldo_ext = None  # saldo de um extrato anterior ao período: não serve para este mês
    saldo_sis, pendente_abertura = saldo_sistema_em(session, fazenda_id, conta, data_cmp)
    total_ext = round(sum(l.valor for l in linhas), 2)
    total_sis = round(sum(m["valor"] for m in sistema_mes), 2)
    return {
        "conta_corrente_id": conta.id, "conta": rotulo_conta(conta), "banco": conta.banco,
        "periodo": {"inicio": ini.isoformat(), "fim": fim.isoformat()},
        "importado": bool(linhas), "linhas": saida_linhas,
        "so_no_sistema": [_dump_mov(m) for m in so_no_sistema],
        "contagem": {
            "linhas": len(linhas), "pareadas": sum(1 for l in linhas if l.status == "pareado"),
            "pendentes": len(pendentes), "sem_lancamento": sum(1 for l in linhas if l.status == "sem_lancamento"),
            "so_no_sistema": len(so_no_sistema),
            "sugestoes_exatas": sum(1 for v in sugestoes.values() if v.get("sugestao")),
        },
        "movimento": {"extrato": total_ext, "sistema": total_sis, "diferenca": round(total_ext - total_sis, 2)},
        "saldos": {**conciliacao.resumo_saldos(saldo_ext, saldo_sis), "data": data_cmp.isoformat(),
                   "pendente_saldo_abertura": pendente_abertura},
    }


def resumo_contas(session: Session, fazenda_id: int, ini: date, fim: date) -> list[dict]:
    """Uma linha por conta ativa: importou? pendências? diferença? (checklist e pacote)."""
    saida = []
    for c in contas_da_fazenda(session, fazenda_id):
        s = situacao(session, fazenda_id, c, ini, fim, com_sugestoes=False)
        tem_movimento = bool(s["linhas"]) or s["movimento"]["sistema"] != 0 or bool(s["so_no_sistema"])
        saida.append({
            "conta_corrente_id": c.id, "conta": s["conta"], "importado": s["importado"],
            "tem_movimento": tem_movimento, "pendentes": s["contagem"]["pendentes"],
            "so_no_sistema": s["contagem"]["so_no_sistema"], "saldos": s["saldos"], "movimento": s["movimento"],
            "conciliada": (not tem_movimento) or (s["importado"] and s["contagem"]["pendentes"] == 0),
        })
    return saida
