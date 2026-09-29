"""
Cruzamento do agendamento preventivo com Compras, Estoque e Financeiro (fatia 9
do planejamento unificado — docs/agents/auditoria-preventivo-agenda/planejamento/
06-planejamento-unificado.md, secao 7; mockup fluxo-completo, store-b.js:
criarCotacao / criarPedido / vincularPagamento / criarContaPagar).

O agendamento (CronogramaSanitario) nao ganha coluna nova: cada ligacao e uma
linha de `CronogramaSanitarioVinculo` (tipo pagamento | conta | cotacao | pedido).
Nada e criado nem apagado em silencio — cada acao grava quem/quando/por que no
log do agendamento (`CronogramaSanitarioLog`) e no proprio vinculo.

  * Comunicar compra   -> cotacao (rascunho, ou enviada) ou pedido do insumo que falta
                          (quantidade = dose x animais); ou "ja comprei" (sem alvo).
  * Vincular pagamento -> escolhe um lancamento JA PAGO do Financeiro (sem duplicar);
                          valor proporcional ao que este agendamento usa, ou o que resta.
  * Conta a pagar      -> lanca no Financeiro (honorario do veterinario ou produtos),
                          valor previsto = custo do produto x dose, vencimento, fornecedor.
  * Cancelar           -> pergunta o destino de cada alvo (conta: manter/cancelar;
                          pagamento: manter/desvincular; cotacao: manter/cancelar).
                          Conta cancelada SAI do Financeiro (fora de "A pagar" e dos
                          totais); o vinculo guarda a foto e o estado "cancelado".
  * Custo previsto     -> preco do produto x dose total; "a informar" quando o frasco e
                          do veterinario (estoque desconsiderado) ou nao ha preco.
  * Estoque desconsiderado -> o item de compra vira "Nao necessaria".
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlmodel import Session, select

from fazenda.models import (
    CalendarioSanitario, ChecklistItem, ContaGerencial, Cotacao, CotacaoFornecedor, CotacaoItem, CronogramaSanitario,
    CronogramaSanitarioAnimal, CronogramaSanitarioVinculo, Estoque, EventoSanitario, Fornecedor, LancamentoItem, Pedido,
    PedidoItem, Usuario,
)
from fazenda.rules import cotacao as cotacao_rules
from fazenda.rules.aplicacao_preventiva import (
    AplicacaoError, _marca_e_item, _modo_dose, _uid, calcular_doses, registrar_log,
)

STATUS_ATIVOS = ("agendado", "em_montagem")
CATEGORIA_COTACAO = "Medicamentos e produtos veterinários"
MODOS_COMPRA = ("cotacao", "pedido", "ja_comprei")
SUBTIPOS_CONTA = ("honorario", "produto")
MOTIVO_FRASCO_VET = "frasco do veterinário"
NOME_ITEM_COMPRA = "Comunicação de compra/cotação"
NOME_ITEM_FINANCEIRO = "Lançamento financeiro"


def _r2(v: float) -> float:
    return round(float(v) + 1e-9, 2)


def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _cron_ativo(cron: CronogramaSanitario) -> None:
    if cron.status not in STATUS_ATIVOS:
        raise AplicacaoError("Este agendamento já foi encerrado — o financeiro dele não muda mais")


# ───────────────────────────── itens do checklist ─────────────────────────────
def _itens(session: Session, cron: CronogramaSanitario) -> list[ChecklistItem]:
    return list(session.exec(
        select(ChecklistItem).where(ChecklistItem.cronograma_id == cron.id).order_by(ChecklistItem.ordem, ChecklistItem.id)
    ).all())


def item_por_chave(session: Session, cron: CronogramaSanitario, chave: str) -> ChecklistItem | None:
    return next((i for i in _itens(session, cron) if i.chave == chave), None)


def garantir_item(session: Session, cron: CronogramaSanitario, chave: str, nome: str) -> ChecklistItem:
    """O item existe (agendamentos antigos nasceram sem 'compra'); criado no fim, pendente."""
    item = item_por_chave(session, cron, chave)
    if item is not None:
        return item
    itens = _itens(session, cron)
    item = ChecklistItem(
        cronograma_id=cron.id, chave=chave, nome=nome, ordem=max([i.ordem for i in itens] or [0]) + 1,
        fazenda_id=cron.fazenda_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def estoque_desconsiderado(session: Session, cron: CronogramaSanitario) -> tuple[bool, str | None]:
    """(o item de estoque foi desconsiderado?, motivo)."""
    it = item_por_chave(session, cron, "estoque")
    if it is not None and it.status == "pulado":
        return True, (it.observacao or None)
    return False, None


def _marcar(session: Session, item: ChecklistItem, status: str, resposta: str | None, observacao: str | None, uid, agora) -> None:
    item.status = status
    item.resposta = resposta
    item.observacao = observacao
    item.responsavel_usuario_id = uid
    item.respondido_em = agora
    session.add(item)


def _reabrir(session: Session, item: ChecklistItem) -> None:
    item.status = "pendente"
    item.resposta = None
    item.observacao = None
    item.respondido_em = None
    item.responsavel_usuario_id = None
    session.add(item)


def sincronizar_itens(session: Session, cron: CronogramaSanitario, *, user=None, agora: datetime | None = None) -> None:
    """Mantem os itens 'financeiro' e 'compra' coerentes com os vinculos ativos e com o estoque.

    financeiro: resolvido enquanto houver pagamento vinculado ou conta a pagar ativa; volta a
    pendente quando o ultimo vinculo cai (a nao ser que o usuario o tenha desconsiderado).
    compra: 'Nao necessaria' quando o estoque foi desconsiderado (e ninguem comunicou compra);
    resolvido enquanto houver cotacao/pedido ativo."""
    agora = agora or datetime.utcnow()
    uid = _uid(user)
    ativos = _vinculos(session, cron.id, apenas_ativos=True)
    fin = item_por_chave(session, cron, "financeiro")
    tem_fin = any(v.tipo in ("pagamento", "conta") for v in ativos)
    if tem_fin:
        fin = fin or garantir_item(session, cron, "financeiro", NOME_ITEM_FINANCEIRO)
        if fin.status != "cumprido":
            tipos = sorted({v.tipo for v in ativos if v.tipo in ("pagamento", "conta")})
            _marcar(session, fin, "cumprido", "+".join(tipos), None, uid, agora)
    elif fin is not None and fin.status == "cumprido" and (fin.resposta or "") in ("pagamento", "conta", "conta+pagamento", "pagamento+conta"):
        _reabrir(session, fin)

    compra = item_por_chave(session, cron, "compra")
    tem_compra = any(v.tipo in ("cotacao", "pedido") for v in ativos)
    desc, _ = estoque_desconsiderado(session, cron)
    if compra is not None:
        if tem_compra:
            tipos = sorted({v.tipo for v in ativos if v.tipo in ("cotacao", "pedido")})
            if compra.status != "cumprido" or compra.resposta in (None, "nao_necessaria"):
                _marcar(session, compra, "cumprido", tipos[-1], None, uid, agora)
        elif desc and compra.status == "pendente":
            _marcar(session, compra, "cumprido", "nao_necessaria", "Estoque desconsiderado", uid, agora)
        elif not desc and compra.status == "cumprido" and compra.resposta in ("cotacao", "pedido"):
            _reabrir(session, compra)   # o ultimo cotacao/pedido foi cancelado
        elif not desc and compra.status == "cumprido" and compra.resposta == "nao_necessaria":
            _reabrir(session, compra)   # o estoque voltou a valer
    session.commit()


def garantir_itens_financeiros(session: Session, cron: CronogramaSanitario, evento: EventoSanitario | None) -> None:
    """Vacina: o agendamento traz o item de compra desde o inicio (Nao necessaria se o estoque foi desconsiderado)."""
    if evento is not None and evento.categoria_preventiva == "exame":
        return
    if not _itens(session, cron):
        return  # regra sem checklist nenhum: nao inventa item
    item = garantir_item(session, cron, "compra", NOME_ITEM_COMPRA)
    sincronizar_itens(session, cron)
    session.refresh(item)


# ───────────────────────────── necessidade e custo ─────────────────────────────
def _contexto_produto(session: Session, cron: CronogramaSanitario):
    cal = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    ev = session.get(EventoSanitario, cal.evento_sanitario_id) if cal else None
    produto = ((cal.produto if cal else None) or (ev.produto_padrao if ev else None) or "").strip() or None
    return cal, ev, produto


def necessidade(session: Session, cron: CronogramaSanitario, fazenda_id: int | None, hoje: date | None = None) -> dict:
    """Quanto do insumo o agendamento usa (dose x animais), o saldo, o que falta e o custo previsto."""
    cal, ev, produto = _contexto_produto(session, cron)
    ck_est = item_por_chave(session, cron, "estoque")
    pref = None
    if ck_est is not None and ck_est.status == "cumprido" and ck_est.resposta:
        import json
        try:
            pref = (json.loads(ck_est.resposta) or {}).get("estoque_id")
        except ValueError:
            pref = None
    numeros = [l.numero_matriz for l in session.exec(
        select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
        .where(CronogramaSanitarioAnimal.status == "incluido")
    ).all()]
    desc, motivo_desc = estoque_desconsiderado(session, cron)
    return calcular_necessidade(session, ev, produto, numeros, fazenda_id, hoje, estoque_pref=pref, desconsiderado=desc, motivo_desc=motivo_desc)


def calcular_necessidade(
    session: Session, ev: EventoSanitario | None, produto: str | None, numeros: list[str], fazenda_id: int | None,
    hoje: date | None = None, *, estoque_pref: int | None = None, desconsiderado: bool = False, motivo_desc: str | None = None,
) -> dict:
    """Miolo da necessidade — serve ao agendamento existente e a previa do assistente (animais ainda so marcados)."""
    hoje = hoje or date.today()
    try:
        item, marca = _marca_e_item(session, produto, fazenda_id, estoque_pref)
    except AplicacaoError:
        item, marca = _marca_e_item(session, produto, fazenda_id, None)
    modo = _modo_dose(ev, marca)
    doses = calcular_doses(session, numeros, modo, fazenda_id, hoje) if numeros else {}
    valores = [d["dose"] for d in doses.values() if d.get("dose") is not None]
    precisa = round(sum(valores), 4) if valores else 0.0
    aproximada = bool(numeros) and (len(valores) < len(numeros) or any(d.get("peso_estimado") for d in doses.values()))
    saldo = item.quantidade if item is not None else None
    falta = max(0.0, round(precisa - (saldo or 0.0), 4)) if precisa else 0.0
    desc = bool(desconsiderado)
    frasco_vet = bool(desc and (motivo_desc or "").strip().lower() == MOTIVO_FRASCO_VET)
    preco = item.valor_unitario if item is not None else None
    custo_a_informar = True
    custo_previsto = None
    custo_motivo = None
    if frasco_vet:
        custo_motivo = "Frasco do veterinário: sem custo calculado"
    elif preco is None:
        custo_motivo = "Sem preço cadastrado para este produto" if item is not None else "Produto fora do estoque desta fazenda"
    elif not precisa:
        custo_motivo = "Sem animais neste agendamento"
    else:
        custo_previsto = _r2(precisa * preco)
        custo_a_informar = False
    unidade = modo.get("unidade") or (item.unidade if item is not None else None)
    return {
        "produto": produto, "estoque_id": item.id if item is not None else None, "estoque_encontrado": item is not None,
        "unidade": unidade, "unidade_estoque": item.unidade if item is not None else None,
        "animais": len(numeros), "por_peso": bool(modo.get("por_peso")),
        "dose_por_animal": None if modo.get("por_peso") else modo.get("dose"), "precisa": precisa, "aproximada": aproximada,
        "saldo": saldo, "falta": falta, "estoque_desconsiderado": desc, "estoque_motivo": motivo_desc,
        "cobre": bool(item is not None and not desc and precisa and (saldo or 0) >= precisa),
        "preco_unitario": preco, "custo_previsto": custo_previsto, "custo_a_informar": custo_a_informar,
        "custo_motivo": custo_motivo,
    }


def previa_do_assistente(session: Session, calendario_id: int, numeros: list[str], fazenda_id: int | None) -> dict:
    """Passo Checklist do assistente 'Criar agendamento': o agendamento ainda nao existe, mas a necessidade,
    o custo previsto e os pagamentos ja pagos do mesmo produto ja podem ser mostrados."""
    cal = session.get(CalendarioSanitario, calendario_id)
    if cal is None or (fazenda_id is not None and cal.fazenda_id != fazenda_id):
        raise AplicacaoError("Protocolo não encontrado", 404)
    ev = session.get(EventoSanitario, cal.evento_sanitario_id)
    produto = ((cal.produto or (ev.produto_padrao if ev else None)) or "").strip() or None
    nec = calcular_necessidade(session, ev, produto, list(dict.fromkeys(numeros)), fazenda_id)
    return {"necessidade": nec, "pagamentos": _candidatos(session, nec, fazenda_id, set())["pagamentos"], "produto": produto}


# ───────────────────────────── vinculos ─────────────────────────────
def _vinculos(session: Session, cronograma_id: int, *, apenas_ativos: bool = False, tipo: str | None = None) -> list[CronogramaSanitarioVinculo]:
    q = select(CronogramaSanitarioVinculo).where(CronogramaSanitarioVinculo.cronograma_id == cronograma_id)
    if apenas_ativos:
        q = q.where(CronogramaSanitarioVinculo.estado == "ativo")
    if tipo:
        q = q.where(CronogramaSanitarioVinculo.tipo == tipo)
    return list(session.exec(q.order_by(CronogramaSanitarioVinculo.id)).all())


def _conta(session: Session, alvo_id: int, fazenda_id: int | None) -> ContaGerencial | None:
    c = session.get(ContaGerencial, alvo_id)
    if c is None or (fazenda_id is not None and c.fazenda_id != fazenda_id):
        return None
    return c


def _nomes(session: Session, ids: set) -> dict:
    from fazenda.rules.auditoria import mapa_usuarios
    return mapa_usuarios(session, {i for i in ids if i})


def serializar_vinculo(session: Session, v: CronogramaSanitarioVinculo, fazenda_id: int | None, nomes: dict | None = None) -> dict:
    """O vinculo + o estado AO VIVO do alvo (pago? cotacao respondida? ...)."""
    nomes = nomes if nomes is not None else _nomes(session, {v.criado_por_usuario_id, v.encerrado_por_usuario_id})
    d = {
        "id": v.id, "cronograma_id": v.cronograma_id, "tipo": v.tipo, "alvo_id": v.alvo_id,
        "numero_lancamento": v.numero_lancamento, "estado": v.estado, "valor": v.valor, "modo": v.modo,
        "subtipo": v.subtipo, "rotulo": v.rotulo, "descricao": v.descricao, "vencimento": _iso(v.vencimento),
        "criado_por": nomes.get(v.criado_por_usuario_id), "criado_em": v.criado_em.isoformat(),
        "encerrado_por": nomes.get(v.encerrado_por_usuario_id), "encerrado_em": _iso(v.encerrado_em),
        "motivo_encerramento": v.motivo_encerramento, "alvo": None,
    }
    if v.tipo in ("pagamento", "conta"):
        c = _conta(session, v.alvo_id, fazenda_id)
        if c is not None:
            d["alvo"] = {
                "existe": True, "fornecedor": c.fornecedor_cliente, "valor_total": c.valor_total, "valor_pago": c.valor_pago,
                "data_pagamento": _iso(c.data_pagamento), "data_vencimento": _iso(c.data_vencimento),
                "paga": c.data_pagamento is not None or c.valor_pago is not None,
            }
        else:
            d["alvo"] = {"existe": False}
    elif v.tipo == "cotacao":
        c = session.get(Cotacao, v.alvo_id)
        d["alvo"] = {"existe": c is not None, "status": c.status if c else None, "numero": c.numero_cotacao if c else v.numero_lancamento}
    elif v.tipo == "pedido":
        p = session.get(Pedido, v.alvo_id)
        d["alvo"] = {"existe": p is not None, "status": p.status if p else None, "numero": p.numero_pedido if p else v.numero_lancamento}
    return d


def vinculos_por_cronogramas(session: Session, ids: list[int], fazenda_id: int | None) -> dict[int, list[dict]]:
    """{cronograma_id: [vinculo serializado]} — para Concluidos/Acompanhamento em lote."""
    if not ids:
        return {}
    linhas = session.exec(
        select(CronogramaSanitarioVinculo).where(CronogramaSanitarioVinculo.cronograma_id.in_(ids)).order_by(CronogramaSanitarioVinculo.id)
    ).all()
    nomes = _nomes(session, {l.criado_por_usuario_id for l in linhas} | {l.encerrado_por_usuario_id for l in linhas})
    saida: dict[int, list[dict]] = {}
    for l in linhas:
        saida.setdefault(l.cronograma_id, []).append(serializar_vinculo(session, l, fazenda_id, nomes))
    return saida


def bloco_financeiro(vinculos: list[dict], nec: dict | None = None) -> dict:
    """Resumo enxuto (Conferir, resumo pos-aplicacao, Concluidos) a partir dos vinculos serializados."""
    ativos = [v for v in vinculos if v["estado"] == "ativo"]
    contas = [v for v in vinculos if v["tipo"] == "conta"]
    pagamentos = [v for v in vinculos if v["tipo"] == "pagamento"]
    compras = [v for v in vinculos if v["tipo"] in ("cotacao", "pedido")]
    bloco = {
        "contas": contas, "pagamentos": pagamentos, "compras": compras,
        "conta_a_pagar_total": _r2(sum(v["valor"] or 0 for v in contas if v["estado"] == "ativo")),
        "contas_ativas": sum(1 for v in contas if v["estado"] == "ativo"),
        "pagamento_vinculado_total": _r2(sum(v["valor"] or 0 for v in pagamentos if v["estado"] == "ativo")),
        "tem_ativo": bool(ativos),
        "link_contas_a_pagar": "/financeiro?aba=contas-a-pagar",
    }
    if nec is not None:
        bloco.update(custo_previsto=nec["custo_previsto"], custo_a_informar=nec["custo_a_informar"], custo_motivo=nec["custo_motivo"])
    return bloco


def estado_compra(session: Session, cron: CronogramaSanitario, nec: dict, ativos: list[CronogramaSanitarioVinculo]) -> str:
    """pendente | ok | nao_necessaria | desconsiderado (lido do item + vinculos + estoque; nao escreve)."""
    if any(v.tipo in ("cotacao", "pedido") for v in ativos):
        return "ok"
    item = item_por_chave(session, cron, "compra")
    if item is not None and item.status == "cumprido" and item.resposta == "ja_comprei":
        return "ok"
    if item is not None and item.status == "pulado":
        return "desconsiderado"
    if nec["estoque_desconsiderado"]:
        return "nao_necessaria"
    if nec["cobre"]:
        return "nao_necessaria"
    return "pendente"


def resumo(session: Session, cron: CronogramaSanitario, fazenda_id: int | None, hoje: date | None = None) -> dict:
    nec = necessidade(session, cron, fazenda_id, hoje)
    todos = _vinculos(session, cron.id)
    ativos = [v for v in todos if v.estado == "ativo"]
    ser = [serializar_vinculo(session, v, fazenda_id) for v in todos]
    fin_item = item_por_chave(session, cron, "financeiro")
    compra_item = item_por_chave(session, cron, "compra")
    tem_pag = any(v.tipo == "pagamento" for v in ativos)
    tem_conta = any(v.tipo == "conta" for v in ativos)
    bloco = bloco_financeiro(ser, nec)
    return {
        "cronograma_id": cron.id, "necessidade": nec, **bloco,
        "compra": {
            "estado": estado_compra(session, cron, nec, ativos), "item_id": compra_item.id if compra_item else None,
            "observacao": compra_item.observacao if compra_item else None,
        },
        "pagamento": {"estado": "ok" if tem_pag else ("pulado" if fin_item is not None and fin_item.status == "pulado" else "pendente")},
        "conta_pagar": {"estado": "ok" if tem_conta else ("pulado" if fin_item is not None and fin_item.status == "pulado" else "pendente")},
        "financeiro_item_id": fin_item.id if fin_item else None,
        "vinculos": ser,
    }


# ───────────────────────────── comunicar compra ─────────────────────────────
def comunicar_compra(session: Session, cron: CronogramaSanitario, dados: dict, *, user=None, fazenda_id: int | None) -> dict:
    """Cotacao ou pedido do insumo (quantidade padrao = o que falta, ou o que o agendamento usa),
    ou 'ja comprei'. Nunca bloqueia o agendamento."""
    _cron_ativo(cron)
    modo = dados.get("modo") or "cotacao"
    if modo not in MODOS_COMPRA:
        raise AplicacaoError('Modo inválido — use "cotacao", "pedido" ou "ja_comprei"')
    nec = necessidade(session, cron, fazenda_id)
    if not nec["produto"]:
        raise AplicacaoError("O protocolo não tem produto definido — não há o que comprar")
    agora = datetime.utcnow()
    uid = _uid(user)
    hoje = date.today()
    item = garantir_item(session, cron, "compra", NOME_ITEM_COMPRA)
    necessario_ate = dados.get("necessario_ate") or cron.data_evento
    if isinstance(necessario_ate, str):
        necessario_ate = date.fromisoformat(necessario_ate)
    agendamento = f"Agendamento #{cron.id} — {cron.data_evento.strftime('%d/%m/%Y')}"

    if modo == "ja_comprei":
        _marcar(session, item, "cumprido", "ja_comprei", (dados.get("observacao") or "Já comprei").strip(), uid, agora)
        registrar_log(session, cron, "Marcou compra como já feita", user=user, detalhe=f"{nec['produto']} · sem cotação/pedido no sistema", agora=agora)
        session.commit()
        return {"modo": modo, "vinculo": None, "resumo": resumo(session, cron, fazenda_id)}

    quantidade = dados.get("quantidade")
    if quantidade in (None, ""):
        quantidade = nec["falta"] or nec["precisa"]
    quantidade = float(quantidade or 0)
    if quantidade <= 0:
        raise AplicacaoError("Informe a quantidade a comprar")
    fornecedor_ids = [int(i) for i in (dados.get("fornecedor_ids") or [])]
    fornecedores: list[Fornecedor] = []
    for fid in fornecedor_ids:
        f = session.get(Fornecedor, fid)
        if f is None or (fazenda_id is not None and f.fazenda_id != fazenda_id):
            raise AplicacaoError("Fornecedor inválido")
        fornecedores.append(f)
    unidade = nec["unidade_estoque"] or nec["unidade"]

    if modo == "cotacao":
        from fazenda.api.routers.cotacoes import _proximo_numero_cotacao
        prazo = datetime.combine(necessario_ate, time(18, 0))
        if prazo <= agora:
            prazo = agora + timedelta(days=1)
        numero = _proximo_numero_cotacao(session, hoje.year, fazenda_id)
        cot = Cotacao(
            numero_cotacao=numero, categoria=CATEGORIA_COTACAO, modo="completo", prazo_resposta=prazo,
            observacao=f"{agendamento} ({nec['produto']})", usuario_id=uid, fazenda_id=fazenda_id,
            status=cotacao_rules.STATUS_RASCUNHO,
        )
        session.add(cot)
        session.flush()
        session.add(CotacaoItem(
            cotacao_id=cot.id, estoque_id=nec["estoque_id"], produto=nec["produto"], quantidade=quantidade, unidade=unidade,
            fazenda_id=fazenda_id,
        ))
        import secrets
        for f in fornecedores:
            session.add(CotacaoFornecedor(
                cotacao_id=cot.id, fornecedor_id=f.id, canal=dados.get("canal") or "email",
                token_publico=secrets.token_urlsafe(32), fazenda_id=fazenda_id,
            ))
        session.flush()
        alvo_id, numero_alvo, tipo = cot.id, numero, "cotacao"
        estimativa = _r2(quantidade * (nec["preco_unitario"] or 0)) if nec["preco_unitario"] else None
        rotulo = ", ".join(f.nome for f in fornecedores) or "Fornecedores a escolher em Cotações"
        detalhe = f"Cotação {numero}: {quantidade:g} {unidade or ''} de {nec['produto']}".replace("  ", " ").strip()
    else:
        from fazenda.api.routers.pedidos import _proximo_numero_pedido
        nome_forn = (dados.get("fornecedor_nome") or (fornecedores[0].nome if fornecedores else "") or "").strip()
        if not nome_forn:
            raise AplicacaoError("Informe o fornecedor do pedido")
        numero = _proximo_numero_pedido(session, hoje.year, fazenda_id)
        preco = nec["preco_unitario"]
        ped = Pedido(
            numero_pedido=numero, tipo="compra", fornecedor_cliente=nome_forn, centro_custo="Pecuária Leiteira",
            data_pedido=hoje, data_prevista=necessario_ate, observacao=f"{agendamento} ({nec['produto']})",
            origem_tipo="sanidade_agendamento", origem_item_id=cron.id, usuario_id=uid, fazenda_id=fazenda_id,
        )
        session.add(ped)
        session.flush()
        session.add(PedidoItem(
            pedido_id=ped.id, tipo_item="produto", produto_servico=nec["produto"], quantidade=quantidade,
            valor_unitario_estimado=preco, valor_total_estimado=_r2(quantidade * preco) if preco else 0.0, fazenda_id=fazenda_id,
        ))
        session.flush()
        alvo_id, numero_alvo, tipo = ped.id, numero, "pedido"
        estimativa = _r2(quantidade * preco) if preco else None
        rotulo = nome_forn
        detalhe = f"Pedido {numero}: {quantidade:g} {unidade or ''} de {nec['produto']} · {nome_forn}".replace("  ", " ").strip()

    v = CronogramaSanitarioVinculo(
        fazenda_id=cron.fazenda_id, cronograma_id=cron.id, tipo=tipo, alvo_id=alvo_id, numero_lancamento=numero_alvo,
        valor=estimativa, rotulo=rotulo, descricao=f"{quantidade:g} {unidade or ''} de {nec['produto']}".replace("  ", " ").strip(),
        vencimento=necessario_ate, criado_por_usuario_id=uid, criado_em=agora,
    )
    session.add(v)
    _marcar(session, item, "cumprido", tipo, None, uid, agora)
    registrar_log(session, cron, "Comunicou compra", user=user, detalhe=detalhe, agora=agora)
    session.commit()
    session.refresh(v)
    saida = {"modo": modo, "vinculo": serializar_vinculo(session, v, fazenda_id), "dispatch": None}
    if dados.get("disparar") and tipo == "cotacao":
        if not fornecedores:
            raise AplicacaoError("Escolha ao menos um fornecedor para enviar a cotação")
        from fazenda.api.routers.cotacoes import DisparoIn, disparar_cotacao
        saida["dispatch"] = disparar_cotacao(alvo_id, DisparoIn(), session=session, fazenda_id=fazenda_id)
        registrar_log(session, cron, "Enviou pedido de cotação", user=user, detalhe=detalhe)
        session.commit()
    saida["resumo"] = resumo(session, cron, fazenda_id)
    return saida


# ───────────────────────────── pagamento ja realizado ─────────────────────────────
def _usado_do_pagamento(session: Session, alvo_id: int, excluir_cronograma: int | None = None) -> float:
    linhas = session.exec(
        select(CronogramaSanitarioVinculo).where(CronogramaSanitarioVinculo.tipo == "pagamento")
        .where(CronogramaSanitarioVinculo.alvo_id == alvo_id).where(CronogramaSanitarioVinculo.estado == "ativo")
    ).all()
    return _r2(sum(l.valor or 0 for l in linhas if l.cronograma_id != excluir_cronograma))


def _quantidade_do_lancamento(session: Session, c: ContaGerencial, produto: str | None) -> float | None:
    if not c.numero_lancamento:
        return None
    q = select(LancamentoItem).where(LancamentoItem.numero_lancamento == c.numero_lancamento)
    if c.fazenda_id is not None:
        q = q.where(LancamentoItem.fazenda_id == c.fazenda_id)
    itens = session.exec(q).all()
    alvo = (produto or "").strip().lower()
    for it in itens:
        if alvo and alvo in (it.produto or "").lower() and it.quantidade:
            return float(it.quantidade)
    return None


def candidatos_pagamento(session: Session, cron: CronogramaSanitario, fazenda_id: int | None, hoje: date | None = None) -> dict:
    """Compras JA PAGAS (despesa com baixa) que cobrem o produto do protocolo — para vincular sem duplicar."""
    nec = necessidade(session, cron, fazenda_id, hoje)
    ja_vinculados = {v.alvo_id for v in _vinculos(session, cron.id, apenas_ativos=True, tipo="pagamento")}
    return _candidatos(session, nec, fazenda_id, ja_vinculados, hoje)


def _candidatos(session: Session, nec: dict, fazenda_id: int | None, ja_vinculados: set[int], hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    produto = (nec["produto"] or "").strip().lower()
    q = select(ContaGerencial).where(ContaGerencial.tipo == "despesa").where(ContaGerencial.data_pagamento.is_not(None))
    if fazenda_id is not None:
        q = q.where(ContaGerencial.fazenda_id == fazenda_id)
    q = q.where(ContaGerencial.data_pagamento >= hoje - timedelta(days=400)).order_by(ContaGerencial.data_pagamento.desc())
    saida = []
    for c in session.exec(q).all():
        itens_txt = ""
        if c.numero_lancamento:
            iq = select(LancamentoItem).where(LancamentoItem.numero_lancamento == c.numero_lancamento)
            if c.fazenda_id is not None:
                iq = iq.where(LancamentoItem.fazenda_id == c.fazenda_id)
            itens_txt = " ".join((i.produto or "") for i in session.exec(iq).all())
        texto = f"{c.descricao or ''} {itens_txt}".lower()
        if not produto or produto not in texto:
            continue
        valor = float(c.valor_pago if c.valor_pago is not None else (c.valor_total or 0))
        qtd = _quantidade_do_lancamento(session, c, nec["produto"])
        usado = _usado_do_pagamento(session, c.id)
        precisa = nec["precisa"] or float(nec["animais"] or 0)
        prop = _r2(valor / qtd * precisa) if qtd and precisa else None
        saida.append({
            "id": c.id, "numero_lancamento": c.numero_lancamento, "fornecedor": c.fornecedor_cliente,
            "data_pagamento": _iso(c.data_pagamento), "valor": _r2(valor), "descricao": c.descricao,
            "doses": qtd, "usado": usado, "resta": _r2(valor - usado), "proporcional": prop,
            "ja_vinculado": c.id in ja_vinculados,
        })
        if len(saida) >= 30:
            break
    return {"produto": nec["produto"], "precisa": nec["precisa"], "unidade": nec["unidade"], "pagamentos": saida}


def vincular_pagamento(
    session: Session, cron: CronogramaSanitario, pagamento_id: int, modo: str = "proporcional", *, user=None, fazenda_id: int | None,
) -> dict:
    _cron_ativo(cron)
    if modo not in ("proporcional", "inteiro"):
        raise AplicacaoError('Modo inválido — use "proporcional" ou "inteiro"')
    c = _conta(session, pagamento_id, fazenda_id)
    if c is None or c.tipo != "despesa":
        raise AplicacaoError("Pagamento não encontrado", 404)
    if c.data_pagamento is None and c.valor_pago is None:
        raise AplicacaoError("Este lançamento ainda não foi pago — para uma conta em aberto, lance uma conta a pagar")
    if any(v.alvo_id == c.id for v in _vinculos(session, cron.id, apenas_ativos=True, tipo="pagamento")):
        raise AplicacaoError("Este pagamento já está vinculado a este agendamento")
    nec = necessidade(session, cron, fazenda_id)
    valor_pago = float(c.valor_pago if c.valor_pago is not None else (c.valor_total or 0))
    usado = _usado_do_pagamento(session, c.id)
    resta = _r2(valor_pago - usado)
    qtd = _quantidade_do_lancamento(session, c, nec["produto"])
    precisa = nec["precisa"] or float(nec["animais"] or 0)
    prop = _r2(valor_pago / qtd * precisa) if qtd and precisa else None
    if modo == "inteiro" or prop is None:
        valor = resta
    else:
        valor = min(prop, resta)
    if valor <= 0:
        raise AplicacaoError("Este pagamento já está totalmente vinculado a outros agendamentos")
    agora = datetime.utcnow()
    v = CronogramaSanitarioVinculo(
        fazenda_id=cron.fazenda_id, cronograma_id=cron.id, tipo="pagamento", alvo_id=c.id, numero_lancamento=c.numero_lancamento,
        valor=valor, modo=modo if prop is not None else "inteiro", rotulo=c.fornecedor_cliente, descricao=c.descricao,
        vencimento=c.data_pagamento, criado_por_usuario_id=_uid(user), criado_em=agora,
    )
    session.add(v)
    session.flush()
    acima = bool(prop is not None and modo == "proporcional" and prop > resta + 0.001)
    registrar_log(
        session, cron, "Vinculou pagamento já realizado", user=user, agora=agora,
        detalhe=f"{c.fornecedor_cliente or 'Pagamento'} · R$ {valor_pago:,.2f} · vinculado R$ {valor:,.2f} ({v.modo})",
    )
    session.commit()
    sincronizar_itens(session, cron, user=user, agora=agora)
    session.refresh(v)
    return {"vinculo": serializar_vinculo(session, v, fazenda_id), "acima": acima, "resumo": resumo(session, cron, fazenda_id)}


# ───────────────────────────── conta a pagar ─────────────────────────────
def lancar_conta_pagar(session: Session, cron: CronogramaSanitario, dados: dict, *, user, fazenda_id: int) -> dict:
    """Lanca no Financeiro uma conta a pagar decorrente do protocolo e a vincula ao agendamento."""
    _cron_ativo(cron)
    subtipo = dados.get("subtipo") or "produto"
    if subtipo not in SUBTIPOS_CONTA:
        raise AplicacaoError('Subtipo inválido — use "honorario" ou "produto"')
    nec = necessidade(session, cron, fazenda_id)
    fornecedor = (dados.get("fornecedor") or "").strip()
    if not fornecedor:
        raise AplicacaoError("Informe o fornecedor ou o serviço")
    valor = dados.get("valor")
    if valor in (None, "") and subtipo == "produto":
        valor = nec["custo_previsto"]
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        valor = 0.0
    if valor <= 0:
        raise AplicacaoError("Informe o valor da conta a pagar" + (" (o custo do produto não é conhecido: frasco do veterinário ou sem preço)" if subtipo == "produto" else ""))
    venc = dados.get("vencimento")
    if isinstance(venc, str):
        venc = date.fromisoformat(venc) if venc else None
    if venc is None:
        raise AplicacaoError("Informe o vencimento")
    cal, ev, produto = _contexto_produto(session, cron)
    nome_protocolo = ev.nome if ev else "Protocolo preventivo"
    descricao = (dados.get("descricao") or "").strip() or (
        f"Honorário — {nome_protocolo}" if subtipo == "honorario" else f"{nome_protocolo} — {produto or 'produto'}"
    )
    # Import local: financeiro importa muita coisa; aqui so precisamos da funcao de criar o lancamento.
    from fazenda.api.routers.financeiro import ItemIn, LancamentoIn, criar_lancamento
    # Sem quantidade/tipo_item "produto": a conta e uma PREVISAO — dar entrada no estoque agora
    # seria contar um frasco que ainda nao chegou. A entrada continua pelo Pedido/Estoque.
    item = ItemIn(
        produto=f"{descricao} (agendamento #{cron.id})", tipo_item="servico" if subtipo == "honorario" else None,
        descricao=descricao, valor_total=valor,
    )
    lanc = LancamentoIn(
        tipo="despesa", itens=[item], fornecedor_cliente=fornecedor, centro_custo="Pecuária Leiteira",
        classificacao="Serviços veterinários" if subtipo == "honorario" else "Medicamentos",
        data_vencimento=venc, data_competencia=cron.data_evento, responsavel=getattr(user, "username", None),
    )
    resp = criar_lancamento(lanc, session=session, user=user, fazenda_id=fazenda_id)
    ids = resp["ids"]
    agora = datetime.utcnow()
    v = CronogramaSanitarioVinculo(
        fazenda_id=cron.fazenda_id, cronograma_id=cron.id, tipo="conta", alvo_id=ids[0], numero_lancamento=resp["numero_lancamento"],
        valor=_r2(valor), subtipo=subtipo, rotulo=fornecedor, descricao=descricao, vencimento=venc,
        criado_por_usuario_id=_uid(user), criado_em=agora,
    )
    session.add(v)
    session.flush()
    registrar_log(
        session, cron, "Lançou conta a pagar", user=user, agora=agora,
        detalhe=f"{fornecedor} · R$ {valor:,.2f} · vence {venc.strftime('%d/%m/%Y')} · {resp['numero_lancamento']}",
    )
    session.commit()
    sincronizar_itens(session, cron, user=user, agora=agora)
    session.refresh(v)
    return {"vinculo": serializar_vinculo(session, v, fazenda_id), "numero_lancamento": resp["numero_lancamento"], "resumo": resumo(session, cron, fazenda_id)}


# ───────────────────────────── encerrar vinculos ─────────────────────────────
def _cancelar_conta_no_financeiro(session: Session, v: CronogramaSanitarioVinculo, fazenda_id: int | None) -> str:
    """Tira a conta do Financeiro (parcelas em aberto e itens da nota). Recusa se ja houve baixa."""
    c = _conta(session, v.alvo_id, fazenda_id)
    if c is None:
        return "A conta já não existe no Financeiro"
    q = select(ContaGerencial).where(ContaGerencial.numero_lancamento == c.numero_lancamento) if c.numero_lancamento else None
    parcelas = [c]
    if q is not None:
        if c.fazenda_id is not None:
            q = q.where(ContaGerencial.fazenda_id == c.fazenda_id)
        parcelas = list(session.exec(q).all()) or [c]
    if any(p.data_pagamento is not None or p.valor_pago is not None for p in parcelas):
        raise AplicacaoError(
            f"A conta {c.numero_lancamento or ''} já foi paga. Estorne a baixa em Financeiro › Contas a pagar antes de cancelar "
            "(ou mantenha a conta).".replace("  ", " "), 409,
        )
    if c.numero_lancamento:
        iq = select(LancamentoItem).where(LancamentoItem.numero_lancamento == c.numero_lancamento)
        if c.fazenda_id is not None:
            iq = iq.where(LancamentoItem.fazenda_id == c.fazenda_id)
        for it in session.exec(iq).all():
            session.delete(it)
    for p in parcelas:
        session.delete(p)
    return "Conta retirada do Financeiro (fora de A pagar e dos totais)"


def _encerrar(session: Session, v: CronogramaSanitarioVinculo, estado: str, motivo: str | None, user, agora: datetime) -> None:
    v.estado = estado
    v.encerrado_por_usuario_id = _uid(user)
    v.encerrado_em = agora
    v.motivo_encerramento = (motivo or None)
    session.add(v)


def encerrar_vinculo(
    session: Session, cron: CronogramaSanitario, vinculo_id: int, acao: str, motivo: str | None, *, user=None,
    fazenda_id: int | None, agora: datetime | None = None, commit: bool = True,
) -> dict:
    """acao: cancelar_conta | desvincular_pagamento | cancelar_cotacao. Motivo obrigatorio."""
    v = session.get(CronogramaSanitarioVinculo, vinculo_id)
    if v is None or v.cronograma_id != cron.id or (fazenda_id is not None and v.fazenda_id != fazenda_id):
        raise AplicacaoError("Vínculo não encontrado", 404)
    if v.estado != "ativo":
        raise AplicacaoError("Este vínculo já foi encerrado")
    esperado = {"cancelar_conta": "conta", "desvincular_pagamento": "pagamento", "cancelar_cotacao": "cotacao"}
    if acao not in esperado or v.tipo != esperado[acao]:
        raise AplicacaoError("Ação inválida para este vínculo")
    if not (motivo or "").strip():
        raise AplicacaoError("Informe o motivo")
    agora = agora or datetime.utcnow()
    if acao == "cancelar_conta":
        nota = _cancelar_conta_no_financeiro(session, v, fazenda_id)
        _encerrar(session, v, "cancelado", motivo.strip(), user, agora)
        registrar_log(session, cron, "Cancelou conta a pagar do agendamento", user=user, motivo=motivo.strip(), agora=agora,
                      detalhe=f"{v.rotulo or 'Conta'} · R$ {(v.valor or 0):,.2f} · {v.numero_lancamento or ''} · {nota}")
    elif acao == "desvincular_pagamento":
        _encerrar(session, v, "desvinculado", motivo.strip(), user, agora)
        registrar_log(session, cron, "Desvinculou pagamento já realizado", user=user, motivo=motivo.strip(), agora=agora,
                      detalhe=f"{v.rotulo or 'Pagamento'} · R$ {(v.valor or 0):,.2f} · o lançamento continua no Financeiro")
    else:
        cot = session.get(Cotacao, v.alvo_id)
        if cot is not None and cot.status == cotacao_rules.STATUS_PEDIDOS_GERADOS:
            raise AplicacaoError("Esta cotação já gerou pedidos — cancele ou mantenha em Cotações", 409)
        if cot is not None and cot.status != cotacao_rules.STATUS_CANCELADA:
            cot.status = cotacao_rules.STATUS_CANCELADA
            cot.atualizado_em = agora
            session.add(cot)
        _encerrar(session, v, "cancelado", motivo.strip(), user, agora)
        registrar_log(session, cron, "Cancelou cotação do agendamento", user=user, motivo=motivo.strip(), agora=agora,
                      detalhe=f"{v.numero_lancamento or 'Cotação'} · {v.descricao or ''}".strip())
    if commit:
        session.commit()
        sincronizar_itens(session, cron, user=user, agora=agora)
    return serializar_vinculo(session, v, fazenda_id)


DESTINOS_CONTA = ("manter", "cancelar")
DESTINOS_PAGAMENTO = ("manter", "desvincular")
DESTINOS_COTACAO = ("manter", "cancelar")


def validar_destinos_cancelamento(session: Session, cron: CronogramaSanitario, dados: dict) -> dict:
    """Antes de cancelar o agendamento: para cada tipo de vinculo ativo, o destino tem de ter sido escolhido."""
    ativos = _vinculos(session, cron.id, apenas_ativos=True)
    tem = {t: [v for v in ativos if v.tipo == t] for t in ("conta", "pagamento", "cotacao", "pedido")}
    conta, pagamento, cotacao = dados.get("destino_conta"), dados.get("destino_pagamento"), dados.get("destino_cotacao")
    if tem["conta"]:
        if conta not in DESTINOS_CONTA:
            raise AplicacaoError("Escolha o destino da conta a pagar deste agendamento: manter ou cancelar")
        if conta == "cancelar":
            for v in tem["conta"]:  # falha antes de cancelar qualquer coisa
                c = _conta(session, v.alvo_id, cron.fazenda_id)
                if c is not None and (c.data_pagamento is not None or c.valor_pago is not None):
                    raise AplicacaoError(
                        f"A conta {v.numero_lancamento or ''} já foi paga: estorne a baixa em Financeiro antes de cancelar, ou mantenha a conta".replace("  ", " "), 409,
                    )
    if tem["pagamento"] and pagamento not in DESTINOS_PAGAMENTO:
        raise AplicacaoError("Escolha o destino do pagamento vinculado: manter o vínculo ou desvincular")
    if tem["cotacao"] and cotacao not in DESTINOS_COTACAO:
        raise AplicacaoError("Escolha o destino da cotação deste agendamento: manter ou cancelar")
    return {"conta": conta if tem["conta"] else None, "pagamento": pagamento if tem["pagamento"] else None,
            "cotacao": cotacao if tem["cotacao"] else None, "tem": {k: len(v) for k, v in tem.items()}}


def aplicar_destinos_cancelamento(session: Session, cron: CronogramaSanitario, dest: dict, motivo: str, *, user=None, fazenda_id: int | None) -> list[str]:
    """Executa (e loga, um a um) o que o usuario escolheu para cada vinculo. Devolve as linhas do resumo."""
    agora = datetime.utcnow()
    resumo_linhas: list[str] = []
    for v in _vinculos(session, cron.id, apenas_ativos=True):
        if v.tipo == "conta":
            if dest["conta"] == "cancelar":
                encerrar_vinculo(session, cron, v.id, "cancelar_conta", motivo, user=user, fazenda_id=fazenda_id, agora=agora, commit=False)
                resumo_linhas.append(f"conta {v.numero_lancamento or v.id} cancelada")
            else:
                registrar_log(session, cron, "Manteve conta a pagar do agendamento", user=user, motivo=motivo, agora=agora,
                              detalhe=f"{v.rotulo or 'Conta'} · R$ {(v.valor or 0):,.2f} · {v.numero_lancamento or ''} · continua em A pagar")
                resumo_linhas.append(f"conta {v.numero_lancamento or v.id} mantida")
        elif v.tipo == "pagamento":
            if dest["pagamento"] == "desvincular":
                encerrar_vinculo(session, cron, v.id, "desvincular_pagamento", motivo, user=user, fazenda_id=fazenda_id, agora=agora, commit=False)
                resumo_linhas.append(f"pagamento {v.numero_lancamento or v.id} desvinculado")
            else:
                registrar_log(session, cron, "Manteve pagamento vinculado", user=user, motivo=motivo, agora=agora,
                              detalhe=f"{v.rotulo or 'Pagamento'} · R$ {(v.valor or 0):,.2f} · segue vinculado ao agendamento cancelado")
                resumo_linhas.append(f"pagamento {v.numero_lancamento or v.id} mantido")
        elif v.tipo == "cotacao":
            if dest["cotacao"] == "cancelar":
                encerrar_vinculo(session, cron, v.id, "cancelar_cotacao", motivo, user=user, fazenda_id=fazenda_id, agora=agora, commit=False)
                resumo_linhas.append(f"cotação {v.numero_lancamento or v.id} cancelada")
            else:
                registrar_log(session, cron, "Manteve cotação do agendamento", user=user, motivo=motivo, agora=agora,
                              detalhe=f"{v.numero_lancamento or 'Cotação'} · segue em Cotações")
                resumo_linhas.append(f"cotação {v.numero_lancamento or v.id} mantida")
        elif v.tipo == "pedido":
            registrar_log(session, cron, "Manteve pedido do agendamento", user=user, motivo=motivo, agora=agora,
                          detalhe=f"{v.numero_lancamento or 'Pedido'} · segue em Pedidos")
            resumo_linhas.append(f"pedido {v.numero_lancamento or v.id} mantido")
    return resumo_linhas


# ───────────────────────────── etapa do checklist (payload do assistente) ─────────────────────────────
def aplicar_payload_financeiro(session: Session, cron: CronogramaSanitario, dados: dict, *, user, fazenda_id: int) -> None:
    """`checklist.financeiro` do assistente: {compra:{...}, pagamento:{pagamento_id,modo}, contas:[{...}]}.
    Cada parte usa exatamente as funcoes das acoes avulsas (mesmos logs)."""
    if not dados:
        return
    compra = dados.get("compra")
    if compra:
        comunicar_compra(session, cron, compra, user=user, fazenda_id=fazenda_id)
    pag = dados.get("pagamento")
    if pag and pag.get("pagamento_id"):
        vincular_pagamento(session, cron, int(pag["pagamento_id"]), pag.get("modo") or "proporcional", user=user, fazenda_id=fazenda_id)
    for conta in dados.get("contas") or []:
        lancar_conta_pagar(session, cron, conta, user=user, fazenda_id=fazenda_id)


def validar_payload_financeiro(dados: dict | None) -> None:
    """Confere, SEM tocar no banco, os campos obrigatorios do payload `checklist.financeiro`
    do assistente (chamado antes de criar o agendamento: nada fica pela metade)."""
    if not dados:
        return
    compra = dados.get("compra")
    if compra:
        if (compra.get("modo") or "cotacao") not in MODOS_COMPRA:
            raise AplicacaoError('Modo de compra inválido — use "cotacao", "pedido" ou "ja_comprei"')
        if (compra.get("modo") == "pedido") and not ((compra.get("fornecedor_nome") or "").strip() or compra.get("fornecedor_ids")):
            raise AplicacaoError("Informe o fornecedor do pedido")
        q = compra.get("quantidade")
        if q not in (None, "") and float(q) <= 0:
            raise AplicacaoError("Informe a quantidade a comprar")
    pag = dados.get("pagamento")
    if pag and pag.get("modo") not in (None, "proporcional", "inteiro"):
        raise AplicacaoError('Modo do pagamento inválido — use "proporcional" ou "inteiro"')
    for conta in dados.get("contas") or []:
        if (conta.get("subtipo") or "produto") not in SUBTIPOS_CONTA:
            raise AplicacaoError('Subtipo da conta inválido — use "honorario" ou "produto"')
        if not (conta.get("fornecedor") or "").strip():
            raise AplicacaoError("Informe o fornecedor ou o serviço da conta a pagar")
        if not conta.get("vencimento"):
            raise AplicacaoError("Informe o vencimento da conta a pagar")
        if conta.get("valor") not in (None, "") and float(conta["valor"]) <= 0:
            raise AplicacaoError("Informe o valor da conta a pagar")


def origem_preventivo_das_contas(session: Session, conta_ids: list[int]) -> dict[int, dict]:
    """{ContaGerencial.id: {cronograma_id, protocolo, subtipo, data_evento}} das contas que nasceram de um
    agendamento preventivo e ainda estao ativas — Financeiro > Contas a pagar mostra o link de volta."""
    if not conta_ids:
        return {}
    linhas = session.exec(
        select(CronogramaSanitarioVinculo).where(CronogramaSanitarioVinculo.tipo == "conta")
        .where(CronogramaSanitarioVinculo.estado == "ativo").where(CronogramaSanitarioVinculo.alvo_id.in_(conta_ids))
    ).all()
    saida: dict[int, dict] = {}
    for l in linhas:
        cron = session.get(CronogramaSanitario, l.cronograma_id)
        if cron is None:
            continue
        _cal, ev, _p = _contexto_produto(session, cron)
        saida[l.alvo_id] = {
            "cronograma_id": cron.id, "protocolo": ev.nome if ev else "Protocolo preventivo", "subtipo": l.subtipo,
            "data_evento": cron.data_evento.isoformat(),
        }
    return saida
