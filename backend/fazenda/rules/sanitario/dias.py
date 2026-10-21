"""
Dias marcados ("Vacina · B19 · 25/12" / "Exame · ..."): marcar, editar,
adicionar/remover animais, cancelar, fechar, ficha de campo e pacote offline.

Regras (modelo_v1 §4, §5, §12, §13):
  - Marcar com várias caixas e animais pré-selecionados (ou, sem lista, quem
    estará pronto na data). Animal fora da regra entra só com CONSENTIMENTO
    explícito (log `consentimento.*`) — nunca trava.
  - Data diferente da prevista: simula os riscos (motor puro); havendo risco,
    pede a DECISÃO (manter/ajustar/dividir), gravada no log `dia.data_diferente`.
  - Editável (data, hora, veterinário, produto, dose) com `versao_lock`.
  - Fechar: faltantes voltam para a caixa ou são dispensados (motivo
    opcional). O fechamento automático fica no job (23:59 do dia seguinte).
  - Nada aqui dá commit; toda escrita chama `recalcular` na mesma transação.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from fazenda.rules.datas import hoje_local
from fazenda.rules.sanitario.registro import _log, produto_da_versao, produto_do_dia_caixa

ESTADOS_ABERTOS = ("marcado", "em_execucao")
FAIXA_FICHA_EM_BRANCO = 3
COLUNAS_FICHA = {
    "brinco": "Brinco", "categoria": "Categoria", "lote": "Lote", "idade": "Idade", "peso": "Peso",
    "dose": "Dose", "partida": "Partida", "aplicado": "Aplicado", "resultado": "Resultado",
    "assinatura": "Assinatura", "obs": "Obs.",
}


class PrecisaDecisao(Exception):
    """O sistema avisa e pede uma decisão (consentimento, riscos de data). A
    rota devolve 409 com `{"codigo", ...detalhe}`; nada foi gravado."""

    def __init__(self, codigo: str, detalhe: dict):
        super().__init__(codigo)
        self.codigo, self.detalhe = codigo, detalhe


class Conflito(Exception):
    pass


def _caixas_validas(session: Session, fazenda_id: int, caixa_ids: list[int]) -> list:
    from fazenda.models import SanitarioCaixa

    out = []
    for cid in dict.fromkeys(int(c) for c in caixa_ids):
        cx = session.get(SanitarioCaixa, cid)
        if cx is None or cx.fazenda_id != fazenda_id or cx.estado == "arquivada":
            raise LookupError(f"Vacina/exame {cid} não encontrado (ou arquivado) nesta fazenda.")
        out.append(cx)
    if not out:
        raise ValueError("Escolha ao menos uma vacina/exame.")
    return out


def nome_dia(session: Session, dia) -> str:
    from fazenda.rules.sanitario.job import nome_dia as _nome
    return _nome(session, dia)


def _sem_dia(a, caixa_id: int):
    if caixa_id not in a.dias:
        return a
    return replace(a, dias={k: v for k, v in a.dias.items() if k != caixa_id}, _cache_cat=a._cache_cat)


def _avaliar_inclusao(cxd, a, data: date):
    """(ok, motivo, kind) de incluir o animal na caixa na data do dia."""
    from fazenda.rules.sanitario.motor import motivo_inelegivel, ok_na_data

    a2 = _sem_dia(a, cxd.caixa_id)
    nd = ok_na_data(cxd, a2, data)
    if nd.ok:
        return True, None, None
    return False, motivo_inelegivel(cxd, a2, data) or nd.texto, nd.kind


def _consent_map(consentimentos: Optional[list]) -> dict:
    out = {}
    for c in consentimentos or []:
        if not c.get("aceito"):
            continue
        aid = int(c["animal_id"])
        out[(aid, c.get("caixa_id"))] = c
    return out


def _consent_para(cmap: dict, animal_id: int, caixa_id: int):
    return cmap.get((animal_id, caixa_id)) or cmap.get((animal_id, None))


def _planejar_itens(session: Session, fazenda_id: int, caixas: list, data: date, itens: Optional[list],
                    consentimentos: Optional[list], hoje: date, *, origem_manual: str = "manual",
                    existentes: Optional[set] = None) -> tuple[list, list, list]:
    """Devolve (plano, faltando_consentimento, avisos). `plano`: lista de
    (animal_id, caixa_id, origem, consentimento|None, motivo|None)."""
    from fazenda.models import Animal
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas

    defs = {d.caixa_id: d for d in carregar_caixas(session, fazenda_id, caixa_ids=[c.id for c in caixas], so_ativas=False)}
    cmap = _consent_map(consentimentos)
    existentes = existentes or set()
    plano, faltando, avisos = [], [], []
    if itens is None:
        animais = carregar_animais(session, fazenda_id, hoje=hoje)
        for cx in caixas:
            cxd = defs.get(cx.id)
            if cxd is None:
                continue
            for a in animais.values():
                if not a.ativo or (a.id, cx.id) in existentes or cx.id in a.dias:
                    continue
                ok, _m, _k = _avaliar_inclusao(cxd, a, data)
                if ok:
                    plano.append((a.id, cx.id, "janela", None, None))
        return plano, faltando, avisos
    pedidos: dict[int, list[int]] = {}
    for it in itens:
        aid = int(it["animal_id"])
        alvo = it.get("caixa_ids") or ([it["caixa_id"]] if it.get("caixa_id") else [c.id for c in caixas])
        pedidos.setdefault(aid, [])
        for c in alvo:
            if int(c) not in pedidos[aid]:
                pedidos[aid].append(int(c))
    ids_ok = set(session.exec(select(Animal.id).where(Animal.fazenda_id == fazenda_id, Animal.id.in_(list(pedidos) or [-1]))).all())
    desconhecidos = sorted(set(pedidos) - ids_ok)
    if desconhecidos:
        raise LookupError(f"Animais não encontrados nesta fazenda: {desconhecidos}")
    animais = carregar_animais(session, fazenda_id, animal_ids=list(pedidos), hoje=hoje)
    validas = {c.id for c in caixas}
    for aid, cids in pedidos.items():
        a = animais.get(aid)
        for cid in cids:
            if cid not in validas:
                raise ValueError(f"A caixa {cid} não faz parte deste dia.")
            if (aid, cid) in existentes:
                continue
            cxd = defs.get(cid)
            if a is None or cxd is None:
                continue
            if cid in a.dias:
                avisos.append({"codigo": "ja_marcado", "animal_id": aid, "caixa_id": cid,
                               "texto": f"{a.numero} já está em outro dia aberto desta vacina/exame."})
            ok, motivo, kind = _avaliar_inclusao(cxd, a, data)
            if ok:
                plano.append((aid, cid, "janela", None, None))
                continue
            cons = _consent_para(cmap, aid, cid)
            if cons is None:
                faltando.append({"animal_id": aid, "numero": a.numero, "caixa_id": cid, "caixa": cxd.rotulo,
                                 "motivo": motivo, "kind": kind})
            else:
                plano.append((aid, cid, origem_manual, cons, motivo))
    return plano, faltando, avisos


def _exigir_consentimentos(session: Session, faltando: list, caixas: list) -> None:
    if not faltando:
        return
    from fazenda.models import SanitarioCaixaVersao

    sem_atestado = []
    for cx in caixas:
        v = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx.versao_atual_id else None
        if v is not None and not v.legal_atestado and any(f["caixa_id"] == cx.id for f in faltando):
            sem_atestado.append(cx.id)
    n = len({f["animal_id"] for f in faltando})
    raise PrecisaDecisao("consentimento_necessario", {
        "mensagem": f"{n} {'animais não cumprem' if n > 1 else 'animal não cumpre'} a regra. "
                    "O sistema avisa e pede o seu consentimento. Não trava.",
        "itens": faltando, "pergunta_atestado_caixas": sem_atestado,
    })


def _gravar_itens(session: Session, fazenda_id: int, dia, plano: list, usuario_id: Optional[int]) -> list[int]:
    from fazenda.models import SanitarioDiaItem

    ids = []
    for aid, cid, origem, cons, motivo in plano:
        log_id = None
        if cons is not None:
            lg = _log(session, fazenda_id, "consentimento.inelegivel", dia_id=dia.id, caixa_id=cid, animal_id=aid,
                      usuario_id=usuario_id, motivo_exibido=cons.get("motivo_exibido") or motivo, decisao="incluir",
                      texto_livre=f"Fora da regra ({motivo}); incluído com consentimento"
                                  f"{' · atestado pedido' if cons.get('quer_atestado') else ''}.",
                      payload={"quer_atestado": bool(cons.get("quer_atestado")),
                               "atestado_destinatario": cons.get("atestado_destinatario")})
            log_id = lg.id
        item = session.exec(select(SanitarioDiaItem).where(
            SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == dia.id,
            SanitarioDiaItem.animal_id == aid, SanitarioDiaItem.caixa_id == cid,
        )).first()
        if item is None:
            item = SanitarioDiaItem(fazenda_id=fazenda_id, dia_id=dia.id, animal_id=aid, caixa_id=cid, origem=origem,
                                    consentimento_log_id=log_id)
        else:
            item.estado, item.origem = "pendente", origem
            item.consentimento_log_id = log_id or item.consentimento_log_id
        session.add(item)
        ids.append(aid)
    session.flush()
    return ids


def _riscos(session: Session, fazenda_id: int, caixas: list, data: date, data_prevista: Optional[date],
            selecionados: Optional[dict], hoje: date) -> dict:
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas
    from fazenda.rules.sanitario.motor import simular_pura

    defs = carregar_caixas(session, fazenda_id, caixa_ids=[c.id for c in caixas], so_ativas=False)
    animais = carregar_animais(session, fazenda_id, hoje=hoje)
    if selecionados is not None:
        # Avalia cada um como se ainda não estivesse no dia.
        for aid, cids in selecionados.items():
            a = animais.get(aid)
            if a is not None:
                for cid in cids:
                    a = _sem_dia(a, cid)
                animais[aid] = a
    return simular_pura(defs, animais, data, data_prevista, selecionados)


def data_prevista(session: Session, fazenda_id: int, caixa_ids: list[int], hoje: Optional[date] = None) -> date:
    """Sugestão de data: a data-base do próximo ciclo de período (a partir de
    amanhã) ou depois de amanhã para janelas por evento/contínuas."""
    from fazenda.rules.sanitario.ciclos import ciclos_periodo
    from fazenda.rules.sanitario.contexto import carregar_caixas

    hoje = hoje or hoje_local()
    melhor = None
    for cxd in carregar_caixas(session, fazenda_id, caixa_ids=caixa_ids, so_ativas=False):
        p = hoje + timedelta(days=2)
        if cxd.eh_periodo:
            c = next((c for c in ciclos_periodo(cxd, hoje, hoje + timedelta(days=1500)) if c.fim >= hoje), None)
            if c is not None:
                p = max(c.base, hoje + timedelta(days=1))
        melhor = p if melhor is None or p < melhor else melhor
    return melhor or hoje + timedelta(days=2)


def _produtos_dos_dados(produtos: Optional[dict]) -> dict[int, dict]:
    return {int(k): (v or {}) for k, v in (produtos or {}).items()}


def _aplicar_produto(dc, versao, p: Optional[dict]) -> None:
    base = produto_da_versao(versao) if versao is not None else {}
    if dc.id is None and not p:
        p = {}
    src = {**({} if dc.id else base), **(p or {})}
    if "modo" in src:
        dc.produto_modo = src["modo"] or "vazio"
    for campo_dc, campo in (("estoque_id", "estoque_id"), ("produto_texto", "texto"), ("dose_valor", "dose_valor"),
                            ("dose_unidade", "dose_unidade"), ("dose_x_kg", "dose_x_kg")):
        if campo in src:
            setattr(dc, campo_dc, src[campo])
    if dc.produto_modo != "estoque":
        dc.estoque_id = None


def criar_dia(session: Session, fazenda_id: int, dados: dict, *, usuario_id: Optional[int],
              hoje: Optional[date] = None):
    from fazenda.models import SanitarioCaixaVersao, SanitarioDia, SanitarioDiaCaixa
    from fazenda.rules.sanitario.motor import recalcular

    hoje = hoje or hoje_local()
    caixas = _caixas_validas(session, fazenda_id, dados.get("caixa_ids") or [])
    data = dados["data"]
    plano, faltando, avisos = _planejar_itens(session, fazenda_id, caixas, data, dados.get("itens"),
                                              dados.get("consentimentos"), hoje)
    _exigir_consentimentos(session, faltando, caixas)
    prev = dados.get("data_prevista")
    decisao = dados.get("decisao_riscos")
    sim = None
    if prev is not None and prev != data:
        sel: dict[int, set] = defaultdict(set)
        for aid, cid, origem, _c, _m in plano:
            if origem == "janela":
                sel[aid].add(cid)
        sim = _riscos(session, fazenda_id, caixas, data, prev, dict(sel), hoje)
        if (sim["riscos"] or sim["entram"]) and not decisao:
            raise PrecisaDecisao("decisao_riscos_necessaria", {
                "mensagem": "A data é diferente da prevista: veja os riscos e decida (manter, ajustar ou dividir).",
                "data": data.isoformat(), "data_prevista": prev.isoformat(), **sim,
            })
    vet = dados.get("veterinario") or {}
    dia = SanitarioDia(
        fazenda_id=fazenda_id, data=data, hora=dados.get("hora"), data_prevista=prev,
        tipo="exame" if all(c.tipo == "exame" for c in caixas) else "vacina",
        veterinario_pessoa_id=vet.get("pessoa_id"), veterinario_texto=vet.get("texto"), crmv_texto=vet.get("crmv"),
        observacao=dados.get("observacao"), decisao_riscos=decisao, criado_por_usuario_id=usuario_id,
    )
    if vet.get("pessoa_id") and not vet.get("texto"):
        from fazenda.models import Pessoa
        p = session.get(Pessoa, int(vet["pessoa_id"]))
        if p is None or p.fazenda_id not in (None, fazenda_id):
            raise LookupError("Veterinário não encontrado nesta fazenda.")
        dia.veterinario_texto, dia.crmv_texto = p.nome, vet.get("crmv") or p.crmv
    session.add(dia)
    session.flush()
    produtos = _produtos_dos_dados(dados.get("produtos"))
    for cx in caixas:
        versao = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx.versao_atual_id else None
        dc = SanitarioDiaCaixa(fazenda_id=fazenda_id, dia_id=dia.id, caixa_id=cx.id,
                               caixa_versao_id=versao.id if versao else None)
        _aplicar_produto(dc, versao, produtos.get(cx.id))
        if cx.tipo == "exame":
            dc.produto_modo, dc.estoque_id = "nao_se_aplica", None
        session.add(dc)
    session.flush()
    ids = _gravar_itens(session, fazenda_id, dia, plano, usuario_id)
    if sim is not None and decisao:
        _log(session, fazenda_id, "dia.data_diferente", dia_id=dia.id, usuario_id=usuario_id,
             decisao=(decisao or {}).get("decisao"),
             texto_livre=f"Data {data.strftime('%d/%m')} diferente da prevista {prev.strftime('%d/%m')}: "
                         f"{len(sim['riscos'])} risco(s); decisão: {(decisao or {}).get('decisao')}.",
             payload={"riscos": sim["riscos"], "entram": sim["entram"], "decisao": decisao})
    if any(cx.estado != "ativa" for cx in caixas):
        avisos.append({"codigo": "caixa_inativa", "texto": "Há vacina/exame inativo neste dia: ele não gera avisos."})
    _log(session, fazenda_id, "dia.criado", dia_id=dia.id, usuario_id=usuario_id,
         texto_livre=f"{nome_dia(session, dia)} marcada com {len(set(ids))} animal(is).")
    if ids:
        recalcular(session, fazenda_id, animal_ids=set(ids), motivo="dia.criado", hoje=hoje)
    return dia, avisos


def editar_dia(session: Session, fazenda_id: int, dia, dados: dict, *, usuario_id: Optional[int],
               hoje: Optional[date] = None) -> list:
    from fazenda.models import Pessoa, SanitarioCaixa, SanitarioCaixaVersao, SanitarioDiaCaixa, SanitarioDiaItem
    from fazenda.rules.sanitario.motor import recalcular

    hoje = hoje or hoje_local()
    if dia.estado not in ESTADOS_ABERTOS:
        raise ValueError("Só dá para editar um dia aberto.")
    if int(dados["versao_lock"]) != int(dia.versao_lock or 1):
        raise Conflito("Este dia foi alterado por outra pessoa. Recarregue antes de salvar.")
    avisos: list = []
    mudou: list[str] = []
    itens = session.exec(select(SanitarioDiaItem).where(
        SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == dia.id,
        SanitarioDiaItem.estado == "pendente")).all()
    nova = dados.get("data")
    if nova is not None and nova != dia.data:
        caixas = [session.get(SanitarioCaixa, dc.caixa_id) for dc in session.exec(select(SanitarioDiaCaixa).where(
            SanitarioDiaCaixa.fazenda_id == fazenda_id, SanitarioDiaCaixa.dia_id == dia.id)).all()]
        sel: dict[int, set] = defaultdict(set)
        for it in itens:
            if it.origem == "janela":
                sel[it.animal_id].add(it.caixa_id)
        prev = dados.get("data_prevista") or dia.data_prevista or dia.data
        sim = _riscos(session, fazenda_id, caixas, nova, prev, dict(sel), hoje)
        decisao = dados.get("decisao_riscos")
        if (sim["riscos"] or sim["entram"]) and not decisao:
            raise PrecisaDecisao("decisao_riscos_necessaria", {
                "mensagem": "A nova data muda quem estará pronto: veja os riscos e decida.",
                "data": nova.isoformat(), "data_prevista": prev.isoformat(), **sim,
            })
        if decisao:
            dia.decisao_riscos = decisao
            _log(session, fazenda_id, "dia.data_diferente", dia_id=dia.id, usuario_id=usuario_id,
                 decisao=decisao.get("decisao"),
                 texto_livre=f"Data mudou de {dia.data.strftime('%d/%m')} para {nova.strftime('%d/%m')}: "
                             f"{len(sim['riscos'])} risco(s); decisão: {decisao.get('decisao')}.",
                 payload={"riscos": sim["riscos"], "entram": sim["entram"], "decisao": decisao})
        mudou.append(f"data {dia.data.strftime('%d/%m')} → {nova.strftime('%d/%m')}")
        dia.data = nova
    if "hora" in dados and dados["hora"] != dia.hora:
        mudou.append("hora")
        dia.hora = dados["hora"]
    if "observacao" in dados:
        dia.observacao = dados["observacao"]
    if "data_prevista" in dados and dados["data_prevista"] is not None:
        dia.data_prevista = dados["data_prevista"]
    vet = dados.get("veterinario")
    if vet is not None:
        dia.veterinario_pessoa_id, dia.veterinario_texto, dia.crmv_texto = vet.get("pessoa_id"), vet.get("texto"), vet.get("crmv")
        if vet.get("pessoa_id") and not vet.get("texto"):
            p = session.get(Pessoa, int(vet["pessoa_id"]))
            if p is None or p.fazenda_id not in (None, fazenda_id):
                raise LookupError("Veterinário não encontrado nesta fazenda.")
            dia.veterinario_texto, dia.crmv_texto = p.nome, vet.get("crmv") or p.crmv
        mudou.append("veterinário")
    for cid, p in _produtos_dos_dados(dados.get("produtos")).items():
        dc = session.exec(select(SanitarioDiaCaixa).where(
            SanitarioDiaCaixa.fazenda_id == fazenda_id, SanitarioDiaCaixa.dia_id == dia.id,
            SanitarioDiaCaixa.caixa_id == cid)).first()
        if dc is None:
            raise ValueError(f"A caixa {cid} não faz parte deste dia.")
        versao = session.get(SanitarioCaixaVersao, dc.caixa_versao_id) if dc.caixa_versao_id else None
        antes = produto_do_dia_caixa(dc)
        _aplicar_produto(dc, versao, p)
        session.add(dc)
        if produto_do_dia_caixa(dc) != antes:
            mudou.append(f"produto/dose da caixa {cid}")
            if dc.carencia_decisao_id and (antes.get("estoque_id") != dc.estoque_id or antes.get("modo") != dc.produto_modo):
                dc.carencia_decisao_id = None  # produto trocado: a decisão de carência precisa ser refeita
                avisos.append({"codigo": "carencia_refazer", "caixa_id": cid,
                               "texto": "Produto trocado: a decisão de carência deste dia precisa ser refeita."})
    dia.versao_lock = int(dia.versao_lock or 1) + 1
    session.add(dia)
    _log(session, fazenda_id, "dia.editado", dia_id=dia.id, usuario_id=usuario_id,
         texto_livre=f"{nome_dia(session, dia)} editada: {', '.join(mudou) or 'sem mudança de campo'}.")
    session.flush()
    if itens:
        recalcular(session, fazenda_id, animal_ids={i.animal_id for i in itens}, motivo="dia.editado", hoje=hoje)
    return avisos


def adicionar_itens(session: Session, fazenda_id: int, dia, itens: list, consentimentos: Optional[list], *,
                    usuario_id: Optional[int], hoje: Optional[date] = None) -> list:
    from fazenda.models import SanitarioCaixa, SanitarioDiaCaixa, SanitarioDiaItem
    from fazenda.rules.sanitario.motor import recalcular

    hoje = hoje or hoje_local()
    if dia.estado not in ESTADOS_ABERTOS:
        raise ValueError("Só dá para incluir animais num dia aberto.")
    caixas = [session.get(SanitarioCaixa, dc.caixa_id) for dc in session.exec(select(SanitarioDiaCaixa).where(
        SanitarioDiaCaixa.fazenda_id == fazenda_id, SanitarioDiaCaixa.dia_id == dia.id)).all()]
    existentes = {(i.animal_id, i.caixa_id) for i in session.exec(select(SanitarioDiaItem).where(
        SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == dia.id,
        SanitarioDiaItem.estado != "removido")).all()}
    data = max(hoje, dia.data)
    plano, faltando, avisos = _planejar_itens(
        session, fazenda_id, caixas, data, itens, consentimentos, hoje,
        origem_manual="curral" if dia.data <= hoje else "manual", existentes=existentes)
    _exigir_consentimentos(session, faltando, caixas)
    ids = _gravar_itens(session, fazenda_id, dia, plano, usuario_id)
    if ids:
        _log(session, fazenda_id, "dia.animais", dia_id=dia.id, usuario_id=usuario_id,
             texto_livre=f"{len(set(ids))} animal(is) incluído(s) em {nome_dia(session, dia)}"
                         f"{' (decisão no curral)' if dia.data <= hoje else ''}.")
        recalcular(session, fazenda_id, animal_ids=set(ids), motivo="dia.animais", hoje=hoje)
    return avisos


def remover_item(session: Session, fazenda_id: int, dia, item_id: int, *, usuario_id: Optional[int],
                 hoje: Optional[date] = None) -> None:
    from fazenda.models import SanitarioDiaItem
    from fazenda.rules.sanitario.motor import recalcular

    item = session.get(SanitarioDiaItem, item_id)
    if item is None or item.fazenda_id != fazenda_id or item.dia_id != dia.id:
        raise LookupError("Item não encontrado neste dia.")
    if item.estado != "pendente":
        raise ValueError("Só sai do dia o animal ainda pendente (registro feito se estorna).")
    item.estado = "removido"
    session.add(item)
    _log(session, fazenda_id, "dia.animal_removido", dia_id=dia.id, caixa_id=item.caixa_id, animal_id=item.animal_id,
         usuario_id=usuario_id, texto_livre="Animal retirado do dia: volta para a caixa.")
    session.flush()
    recalcular(session, fazenda_id, animal_ids=[item.animal_id], motivo="dia.animal_removido", hoje=hoje)


def cancelar_dia(session: Session, fazenda_id: int, dia, motivo: Optional[str], *, usuario_id: Optional[int],
                 hoje: Optional[date] = None) -> None:
    from fazenda.models import SanitarioDiaItem, SanitarioRegistro
    from fazenda.rules.sanitario.motor import recalcular

    if dia.estado not in ESTADOS_ABERTOS:
        raise ValueError("Só dá para cancelar um dia aberto.")
    tem_registro = session.exec(select(SanitarioRegistro.id).where(
        SanitarioRegistro.fazenda_id == fazenda_id, SanitarioRegistro.dia_id == dia.id,
        SanitarioRegistro.estado == "valido")).first()
    if tem_registro is not None:
        raise ValueError("O dia já tem registros: feche o dia (ou estorne os registros) em vez de cancelar.")
    afetados = set()
    for it in session.exec(select(SanitarioDiaItem).where(
        SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == dia.id,
        SanitarioDiaItem.estado == "pendente")).all():
        it.estado = "removido"
        session.add(it)
        afetados.add(it.animal_id)
    dia.estado, dia.motivo_cancelamento = "cancelado", (motivo or None)
    dia.versao_lock = int(dia.versao_lock or 1) + 1
    session.add(dia)
    _log(session, fazenda_id, "dia.cancelado", dia_id=dia.id, usuario_id=usuario_id,
         texto_livre=f"{nome_dia(session, dia)} cancelada{': ' + motivo if motivo else ''}.")
    session.flush()
    if afetados:
        recalcular(session, fazenda_id, animal_ids=afetados, motivo="dia.cancelado", hoje=hoje)


def dispensar(session: Session, fazenda_id: int, pares: list[tuple], motivo: Optional[str], *,
              usuario_id: Optional[int], acao: str = "dispensar", dia_id: Optional[int] = None,
              hoje: Optional[date] = None) -> int:
    """Dispensa (ou "descarta a vacina") o animal NESTE ciclo — decisão de
    gente gravada em `sanitario_situacao.dispensada_*` (o motor preserva).
    `pares`: (caixa_id, animal_id[, ciclo_chave, dose_num])."""
    from fazenda.models import SanitarioSituacao
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas
    from fazenda.rules.sanitario.motor import recalcular, situacao_atual

    hoje = hoje or hoje_local()
    if not pares:
        return 0
    animais = carregar_animais(session, fazenda_id, animal_ids={p[1] for p in pares}, hoje=hoje)
    defs = {d.caixa_id: d for d in carregar_caixas(session, fazenda_id, caixa_ids={p[0] for p in pares}, so_ativas=False)}
    agora = datetime.utcnow()
    n = 0
    texto_motivo = (motivo or "").strip() or None
    rotulo = "Descartada" if acao == "descartar" else "Dispensada"
    for par in pares:
        cid, aid = int(par[0]), int(par[1])
        ciclo, dose = (par[2], int(par[3] or 1)) if len(par) >= 4 and par[2] else (None, 1)
        if ciclo is None:
            a, cxd = animais.get(aid), defs.get(cid)
            if a is None or cxd is None:
                continue
            s = situacao_atual(cxd, _sem_dia(a, cid), hoje)
            if s.ciclo is None or s.estado == "aplicada":
                continue
            ciclo, dose = s.ciclo.chave, s.dose_num
        row = session.exec(select(SanitarioSituacao).where(
            SanitarioSituacao.fazenda_id == fazenda_id, SanitarioSituacao.caixa_id == cid,
            SanitarioSituacao.animal_id == aid, SanitarioSituacao.ciclo_chave == ciclo,
            SanitarioSituacao.dose_num == dose)).first()
        if row is None:
            row = SanitarioSituacao(fazenda_id=fazenda_id, caixa_id=cid, animal_id=aid, ciclo_chave=ciclo,
                                    dose_num=dose, estado="dispensada")
        row.dispensada_em, row.dispensada_por_usuario_id = agora, usuario_id
        row.dispensada_motivo = f"{rotulo}: {texto_motivo}" if texto_motivo else rotulo
        session.add(row)
        _log(session, fazenda_id, f"situacao.{'descartada' if acao == 'descartar' else 'dispensada'}", dia_id=dia_id,
             caixa_id=cid, animal_id=aid, usuario_id=usuario_id, decisao=acao,
             texto_livre=f"{rotulo} no ciclo {ciclo}{' · motivo: ' + texto_motivo if texto_motivo else ' · motivo pulado'}.")
        n += 1
    session.flush()
    recalcular(session, fazenda_id, animal_ids={p[1] for p in pares}, motivo=acao, hoje=hoje)
    return n


def fechar_dia(session: Session, fazenda_id: int, dia, faltantes: str, motivo: Optional[str], *,
               usuario_id: Optional[int], canal: str = "site", hoje: Optional[date] = None) -> dict:
    from fazenda.models import SanitarioDiaItem
    from fazenda.rules.sanitario.motor import recalcular

    hoje = hoje or hoje_local()
    if dia.estado not in ESTADOS_ABERTOS:
        raise ValueError("O dia já está fechado ou cancelado.")
    if faltantes not in ("voltar", "dispensar"):
        raise ValueError("Faltantes: use voltar ou dispensar.")
    pend = session.exec(select(SanitarioDiaItem).where(
        SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == dia.id,
        SanitarioDiaItem.estado == "pendente")).all()
    for it in pend:
        it.estado = "dispensado" if faltantes == "dispensar" else "faltou"
        session.add(it)
    dia.estado, dia.fechado_em, dia.fechado_por_usuario_id = "fechado", datetime.utcnow(), usuario_id
    dia.versao_lock = int(dia.versao_lock or 1) + 1
    session.add(dia)
    session.flush()
    if faltantes == "dispensar" and pend:
        dispensar(session, fazenda_id, [(it.caixa_id, it.animal_id) for it in pend], motivo, usuario_id=usuario_id,
                  dia_id=dia.id, hoje=hoje)
    animais = sorted({it.animal_id for it in pend})
    _log(session, fazenda_id, "dia.fechado", dia_id=dia.id, usuario_id=usuario_id, decisao=faltantes,
         texto_livre=f"{nome_dia(session, dia)} fechada ({canal}): "
                     + (f"{len(animais)} animal(is) sem registro "
                        + ("dispensados" + (f" · motivo: {motivo}" if motivo else " sem motivo") if faltantes == "dispensar"
                           else "voltaram para a caixa") if animais else "sem faltantes") + ".",
         payload={"faltantes": animais})
    if pend and faltantes == "voltar":
        recalcular(session, fazenda_id, animal_ids=set(animais), motivo="dia.fechado", hoje=hoje)
    return {"faltantes": animais, "destino": faltantes}


# ════════════════════════════════════════════════════════════════════════════
# Leituras (puras)
# ════════════════════════════════════════════════════════════════════════════
def dia_dict(session: Session, dia, *, com_itens: bool = True) -> dict:
    from fazenda.models import (
        Animal, SanitarioCaixa, SanitarioCarenciaAceite, SanitarioDiaCaixa, SanitarioDiaItem, SanitarioRegistro,
    )

    caixas = []
    for dc in session.exec(select(SanitarioDiaCaixa).where(
        SanitarioDiaCaixa.fazenda_id == dia.fazenda_id, SanitarioDiaCaixa.dia_id == dia.id).order_by(SanitarioDiaCaixa.id)).all():
        cx = session.get(SanitarioCaixa, dc.caixa_id)
        dec = session.get(SanitarioCarenciaAceite, dc.carencia_decisao_id) if dc.carencia_decisao_id else None
        caixas.append({
            "caixa_id": dc.caixa_id, "nome": cx.nome if cx else None, "nome_curto": (cx.nome_curto or cx.nome) if cx else None,
            "tipo": cx.tipo if cx else None, "caixa_versao_id": dc.caixa_versao_id,
            "produto": {"modo": dc.produto_modo, "estoque_id": dc.estoque_id, "texto": dc.produto_texto,
                        "dose_valor": dc.dose_valor, "dose_unidade": dc.dose_unidade, "dose_x_kg": dc.dose_x_kg},
            "carencia_decisao": {"modo": dec.modo_leite, "leite_dias": dec.leite_dias, "carne_dias": dec.carne_dias}
            if dec else None,
        })
    out = {
        "id": dia.id, "nome": nome_dia(session, dia), "tipo": dia.tipo, "data": dia.data.isoformat(), "hora": dia.hora,
        "data_prevista": dia.data_prevista.isoformat() if dia.data_prevista else None, "estado": dia.estado,
        "veterinario": {"pessoa_id": dia.veterinario_pessoa_id, "texto": dia.veterinario_texto, "crmv": dia.crmv_texto},
        "observacao": dia.observacao, "decisao_riscos": dia.decisao_riscos, "versao_lock": dia.versao_lock,
        "fechado_em": dia.fechado_em.isoformat() if dia.fechado_em else None, "fechamento_auto": dia.fechamento_auto,
        "motivo_cancelamento": dia.motivo_cancelamento, "caixas": caixas,
    }
    itens = session.exec(select(SanitarioDiaItem).where(
        SanitarioDiaItem.fazenda_id == dia.fazenda_id, SanitarioDiaItem.dia_id == dia.id).order_by(SanitarioDiaItem.id)).all()
    out["contagens"] = {
        "animais": len({i.animal_id for i in itens if i.estado != "removido"}),
        "pendentes": sum(1 for i in itens if i.estado == "pendente"),
        "feitos": sum(1 for i in itens if i.estado == "feito"),
        "registros_apos_fechamento": len(session.exec(select(SanitarioRegistro.id).where(
            SanitarioRegistro.fazenda_id == dia.fazenda_id, SanitarioRegistro.dia_id == dia.id,
            SanitarioRegistro.apos_fechamento == True, SanitarioRegistro.estado == "valido")).all()),  # noqa: E712
    }
    if com_itens:
        nums = {a.id: a.numero for a in session.exec(select(Animal).where(
            Animal.fazenda_id == dia.fazenda_id, Animal.id.in_({i.animal_id for i in itens} or {-1}))).all()}
        regs = {(r.dia_item_id): r.id for r in session.exec(select(SanitarioRegistro).where(
            SanitarioRegistro.fazenda_id == dia.fazenda_id, SanitarioRegistro.dia_id == dia.id,
            SanitarioRegistro.estado == "valido")).all() if r.dia_item_id}
        out["itens"] = [{
            "id": i.id, "animal_id": i.animal_id, "numero": nums.get(i.animal_id), "caixa_id": i.caixa_id,
            "origem": i.origem, "estado": i.estado, "consentimento_log_id": i.consentimento_log_id,
            "registro_id": regs.get(i.id),
        } for i in itens]
    return out


def _linha_animal(a, ctx, hoje: date) -> dict:
    from fazenda.rules.sanitario.publico import idade_txt

    cat = ctx.categoria_em(hoje)[1] if ctx is not None else None
    return {
        "animal_id": a.id, "brinco": a.numero, "categoria": cat, "lote": a.grupo_primario,
        "idade": idade_txt((hoje - a.data_nasc).days) if a.data_nasc else None,
        "peso": ctx.peso if ctx is not None else None,
    }


def ficha_dia(session: Session, fazenda_id: int, dia, hoje: Optional[date] = None) -> dict:
    """Ficha de campo PRÉ-PREENCHIDA em JSON (o front renderiza/imprime)."""
    from fazenda.models import Animal, Fazenda, SanitarioCaixa, SanitarioCaixaVersao, SanitarioDiaItem
    from fazenda.rules.sanitario.contexto import carregar_animais

    hoje = hoje or hoje_local()
    d = dia_dict(session, dia, com_itens=False)
    cols: list[str] = []
    lembretes = []
    for c in d["caixas"]:
        cx = session.get(SanitarioCaixa, c["caixa_id"])
        v = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx and cx.versao_atual_id else None
        for col in (v.ficha_colunas if v else []) or []:
            if col not in cols and col not in ("aplicado", "resultado", "obs"):
                cols.append(col)
        if v is not None and v.legal_marca_texto:
            lembretes.append(f"{cx.nome_curto or cx.nome}: {v.legal_marca_texto}")
    itens = session.exec(select(SanitarioDiaItem).where(
        SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == dia.id,
        SanitarioDiaItem.estado != "removido")).all()
    ids = sorted({i.animal_id for i in itens})
    ctxs = carregar_animais(session, fazenda_id, animal_ids=ids, hoje=hoje) if ids else {}
    linhas = []
    por_animal: dict[int, set] = defaultdict(set)
    for i in itens:
        por_animal[i.animal_id].add(i.caixa_id)
    for a in session.exec(select(Animal).where(Animal.fazenda_id == fazenda_id, Animal.id.in_(ids or [-1]))
                          .order_by(Animal.numero)).all():
        ln = _linha_animal(a, ctxs.get(a.id), hoje)
        ln["caixas"] = sorted(por_animal.get(a.id, ()))
        linhas.append(ln)
    faz = session.get(Fazenda, fazenda_id)
    return {
        "tipo": "pre_preenchida", "fazenda": faz.nome if faz else None, "titulo": d["nome"], "data": d["data"],
        "hora": d["hora"], "veterinario": d["veterinario"],
        "caixas": [{"caixa_id": c["caixa_id"], "nome_curto": c["nome_curto"], "produto": c["produto"]} for c in d["caixas"]],
        "colunas": [{"chave": c, "rotulo": COLUNAS_FICHA.get(c, c)} for c in cols]
                   + [{"chave": f"caixa:{c['caixa_id']}", "rotulo": c["nome_curto"]} for c in d["caixas"]]
                   + [{"chave": "obs", "rotulo": "Obs."}],
        "linhas": linhas, "linhas_em_branco": FAIXA_FICHA_EM_BRANCO, "lembretes": lembretes,
        "rodape": "Linhas em branco: animais incluídos na hora.",
    }


def ficha_vazia(session: Session, fazenda_id: int, caixas: list, linhas: int = 25) -> dict:
    """Ficha VAZIA (modelo de colunas das caixas) para imprimir e lançar depois
    pelo Lançamento simples (origem "ficha")."""
    from fazenda.models import Fazenda, SanitarioCaixaVersao

    cols: list[str] = []
    for cx in caixas:
        v = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx.versao_atual_id else None
        for col in (v.ficha_colunas if v else []) or []:
            if col not in cols:
                cols.append(col)
    if not cols:
        cols = ["brinco", "dose", "aplicado", "obs"]
    if "brinco" not in cols:
        cols.insert(0, "brinco")
    faz = session.get(Fazenda, fazenda_id)
    return {
        "tipo": "vazia", "fazenda": faz.nome if faz else None,
        "titulo": " · ".join((c.nome_curto or c.nome) for c in caixas) or "Vacina/exame",
        "caixa_ids": [c.id for c in caixas],
        "colunas": [{"chave": c, "rotulo": COLUNAS_FICHA.get(c, c)} for c in cols],
        "linhas_em_branco": linhas, "campos_cabecalho": ["data", "veterinario", "crmv", "produto", "partida"],
    }


def pacote_offline(session: Session, fazenda_id: int, dia, hoje: Optional[date] = None) -> dict:
    """Tudo o que o app precisa para trabalhar sem sinal: o dia, as caixas com
    as regras de aviso COMO DADOS (público, janela, carência, legal), produtos,
    veterinários e, para cada animal ativo × caixa do dia, se está na regra e o
    motivo do "fora" (texto do pop-up de consentimento). SÓ LÊ."""
    from fazenda.models import Animal, Estoque, SanitarioCaixa, SanitarioCaixaVersao, SanitarioDiaCaixa
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas
    from fazenda.rules.sanitario.permissoes import veterinarios_da_fazenda
    from fazenda.rules.sanitario.registro import carencia_precisa_decisao

    hoje = hoje or hoje_local()
    d = dia_dict(session, dia)
    dcs = {dc.caixa_id: dc for dc in session.exec(select(SanitarioDiaCaixa).where(
        SanitarioDiaCaixa.fazenda_id == fazenda_id, SanitarioDiaCaixa.dia_id == dia.id)).all()}
    defs = {x.caixa_id: x for x in carregar_caixas(session, fazenda_id, caixa_ids=list(dcs), so_ativas=False)}
    caixas = []
    estoque_ids = set()
    for cid, dc in dcs.items():
        cx = session.get(SanitarioCaixa, cid)
        v = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx.versao_atual_id else None
        prod = produto_do_dia_caixa(dc)
        if prod.get("estoque_id"):
            estoque_ids.add(prod["estoque_id"])
        caixas.append({
            "caixa_id": cid, "nome": cx.nome, "nome_curto": cx.nome_curto or cx.nome, "tipo": cx.tipo,
            "produto": prod,
            "regras": {
                "pub_sexo": v.pub_sexo if v else None, "pub_idade_min_dias": v.pub_idade_min_dias if v else None,
                "pub_idade_max_dias": v.pub_idade_max_dias if v else None,
                "pub_condicoes": (v.pub_condicoes if v else []) or [],
                "categorias": sorted(defs[cid].categorias) if cid in defs else [],
                "pub_cat_modo": v.pub_cat_modo if v else None,
                "evento_tipo": v.evento_tipo if v else None, "evento_de_dias": v.evento_de_dias if v else None,
                "evento_ate_dias": v.evento_ate_dias if v else None,
                "legal_crmv_pedir": bool(v and v.legal_crmv_pedir), "tem_atestado": bool(v and v.legal_atestado),
                "legal_leitura": v.legal_leitura if v else None, "legal_marca_texto": v.legal_marca_texto if v else None,
                "car_leite_dias": v.car_leite_dias if v else None, "car_carne_dias": v.car_carne_dias if v else None,
                "car_modo_leite": v.car_modo_leite if v else None,
                "carencia_precisa_decisao": None if cx.tipo == "exame" else carencia_precisa_decisao(session, fazenda_id, v, prod, dc),
            },
        })
    animais = carregar_animais(session, fazenda_id, hoje=hoje)
    numeros = {a.id: a for a in session.exec(select(Animal).where(Animal.fazenda_id == fazenda_id,
                                                                    Animal.ativo == True)).all()}  # noqa: E712
    data = max(hoje, dia.data)
    lista = []
    for aid, a in animais.items():
        if not a.ativo:
            continue
        reg = numeros.get(aid)
        elig = {}
        for cid, cxd in defs.items():
            ok, motivo, kind = _avaliar_inclusao(cxd, a, data)
            elig[str(cid)] = {"elegivel": ok, "motivo": motivo, "kind": kind}
        linha = _linha_animal(reg, a, hoje) if reg is not None else {"animal_id": aid, "brinco": a.numero}
        linha["caixas"] = elig
        lista.append(linha)
    lista.sort(key=lambda x: x.get("brinco") or "")
    estoques = []
    for e in session.exec(select(Estoque).where(Estoque.fazenda_id == fazenda_id, Estoque.id.in_(estoque_ids or {-1}))).all():
        estoques.append({"id": e.id, "nome": e.nome, "unidade": e.unidade, "saldo": e.quantidade})
    return {
        "gerado_em": datetime.utcnow().isoformat() + "Z", "data_referencia": data.isoformat(), "dia": d,
        "caixas": caixas, "estoques": estoques,
        "veterinarios": [{"pessoa_id": p.id, "nome": p.nome, "crmv": p.crmv} for p in veterinarios_da_fazenda(session, fazenda_id)],
        "animais": lista,
        "regras_aviso": {
            "consentimento_fora_da_regra": True, "desfazer_segundos": 10,
            "aviso_offline_horas": _aviso_offline_horas(session, fazenda_id),
            "texto_consentimento": "Estou ciente e quero incluir mesmo assim. O seu nome, a data e o motivo ficam no registro.",
        },
    }


def _aviso_offline_horas(session: Session, fazenda_id: int) -> int:
    from fazenda.models import SanitarioParametros

    p = session.exec(select(SanitarioParametros).where(SanitarioParametros.fazenda_id == fazenda_id)).first()
    return int(p.aviso_offline_horas) if p and p.aviso_offline_horas else 24
