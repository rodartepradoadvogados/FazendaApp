"""
Backfill dos itens das notas automáticas do HISTÓRICO (Fase A, PR 2/3).

Os listeners de `rules/lancamento_automatico.py` dão conta e itens às notas
automáticas NOVAS (e mantêm as que já têm itens gerados). As notas que já
existiam — folhas, férias, 13º, rescisões, guias, contratos, empreitas,
diárias, vales, caixa do funcionário — só ganham itens por aqui, por comando
(`scripts/backfill_itens_automaticos.py`), simulação por padrão.

Regras:
  - só nota automática reconhecida (tipo de documento + registro de origem),
    SEM item nenhum e SEM `codigo_conta` (quem o usuário já classificou à mão
    é PRESERVADO e sai na lista; a guia de FGTS/DCTF tem código fixo do
    sistema, então entra);
  - os itens são os mesmos que a nota teria se nascesse hoje (folha pelo
    bruto, encargos, retidos, vale), na conta padrão de cada origem, e somam
    o total da nota;
  - item gerado que ficou SEM conta (origem sem conta configurada na época)
    ganha a conta configurada agora;
  - NUNCA muda `valor_total`/`valor_pago` nem a conta da nota; cada item
    criado e cada conta preenchida vira uma linha em
    `migracao_log_financeiro` — `--reverter LOTE` apaga o que foi criado e
    devolve o que foi preenchido.

Com a flag desligada, os relatórios ignoram itens gerados: rodar o backfill
ANTES de ligar a flag não muda número nenhum (é a ordem recomendada).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from fazenda.rules import lancamento_automatico as la

MIGRACAO = "backfill_itens_automaticos_v1"


@dataclass
class PlanoBackfill:
    criar: list[dict] = field(default_factory=list)
    preencher: list[dict] = field(default_factory=list)
    preservadas: list[dict] = field(default_factory=list)
    sem_conta: dict[str, int] = field(default_factory=dict)


def planejar(session: Session, fazenda_id: int) -> PlanoBackfill:
    from fazenda.models import ContaGerencial, LancamentoItem

    if not isinstance(fazenda_id, int):
        raise ValueError("Informe a fazenda (uma por vez).")
    cfg = la.carregar_configuracao(session, fazenda_id)
    contas = session.exec(select(ContaGerencial).where(
        ContaGerencial.fazenda_id == fazenda_id,
        ContaGerencial.tipo_documento.in_(sorted(la.TIPOS_DOCUMENTO_AUTOMATICOS)),
    )).all()
    por_numero: dict[str, list] = {}
    for c in contas:
        if c.numero_lancamento:
            por_numero.setdefault(c.numero_lancamento, []).append(c)
    itens_por_numero: dict[str, list] = {}
    if por_numero:
        for it in session.exec(select(LancamentoItem).where(
            LancamentoItem.fazenda_id == fazenda_id, LancamentoItem.numero_lancamento.in_(sorted(por_numero)),
        )).all():
            itens_por_numero.setdefault(it.numero_lancamento, []).append(it)

    plano = PlanoBackfill()
    for numero in sorted(por_numero):
        parcelas = sorted(por_numero[numero], key=lambda c: (c.parcela_num or 0, c.id or 0))
        itens = itens_por_numero.get(numero, [])
        if itens:
            if any(not it.gerado_por for it in itens):
                continue  # nota com item de gente: não é deste backfill
            for it in itens:
                if it.codigo_conta_gerencial:
                    continue
                conta = cfg.conta(la.origem_do_papel(it.gerado_por))
                if conta.codigo:
                    plano.preencher.append({
                        "item_id": it.id, "numero_lancamento": numero, "papel": it.gerado_por,
                        "codigo": conta.codigo, "nome": conta.nome,
                    })
            continue
        composicao = la.compor_itens(session, parcelas, fazenda_id)
        if composicao is None:
            continue
        origem, desejados = composicao
        if origem != "guia" and any(c.codigo_conta for c in parcelas):
            plano.preservadas.append({
                "numero_lancamento": numero, "origem": origem, "codigo_conta": parcelas[0].codigo_conta,
                "motivo": "nota já classificada à mão (conta preenchida): preservada",
            })
            continue
        finais = la.resolver_itens(desejados, cfg)
        if round(sum(f.valor for f in finais), 2) != round(sum(c.valor_total or 0 for c in parcelas), 2):
            plano.preservadas.append({"numero_lancamento": numero, "origem": origem,
                                      "motivo": "itens não fecham com o total da nota: revisar"})
            continue
        for f in finais:
            if not f.codigo and (f.natureza in (None, la.OPERACIONAL)) and not la.PAPEIS[f.papel].linha_forcada:
                origem_item = la.origem_do_papel(f.papel) or "?"
                plano.sem_conta[origem_item] = plano.sem_conta.get(origem_item, 0) + 1
        plano.criar.append({
            "numero_lancamento": numero, "origem": origem, "conta_id": parcelas[0].id,
            "total": round(sum(c.valor_total or 0 for c in parcelas), 2),
            "itens": finais,
        })
    return plano


def aplicar(session: Session, plano: PlanoBackfill, lote: str, fazenda_id: int) -> int:
    """Grava o plano (sem commit). Devolve quantas linhas de log gravou."""
    from fazenda.models import ContaGerencial, LancamentoItem
    from fazenda.rules.migracao_log import registrar_criacao, registrar_mudanca

    linhas = 0
    for nota in plano.criar:
        conta = session.get(ContaGerencial, nota["conta_id"])
        if conta is None or conta.fazenda_id != fazenda_id:
            continue
        for final in nota["itens"]:
            item = la.novo_item(conta, final)
            session.add(item)
            session.flush()
            registrar_criacao(
                session, fazenda_id=fazenda_id, lote=lote, migracao=MIGRACAO, tabela="lancamento_item",
                registro=item, marca=final.papel, motivo=f"item {final.papel} da nota {nota['numero_lancamento']}",
            )
            linhas += 1
    for p in plano.preencher:
        item = session.get(LancamentoItem, p["item_id"])
        if item is None or item.fazenda_id != fazenda_id or item.codigo_conta_gerencial:
            continue
        registrar_mudanca(session, fazenda_id=fazenda_id, lote=lote, migracao=MIGRACAO, tabela="lancamento_item",
                          registro=item, campo="codigo_conta_gerencial", valor_depois=p["codigo"],
                          motivo=f"conta automática de {la.origem_do_papel(p['papel'])}")
        linhas += 1
        if p.get("nome"):
            registrar_mudanca(session, fazenda_id=fazenda_id, lote=lote, migracao=MIGRACAO, tabela="lancamento_item",
                              registro=item, campo="nome_conta_gerencial", valor_depois=p["nome"],
                              motivo="nome da conta automática")
            linhas += 1
    return linhas
