"""
Aplicar um agendamento preventivo (fatia 8 do planejamento unificado — docs/
agents/auditoria-preventivo-agenda/planejamento/06-planejamento-unificado.md,
secao 7). Protocolos > Acompanhamento e a Agenda chamam a MESMA funcao
(`aplicar`), so muda o `canal` gravado.

O que uma aplicacao faz, tudo ou nada (validacoes antes de gravar qualquer coisa):
  * aplicador obrigatorio (B19 e tuberculose: so veterinario);
  * animais aplicados (total ou parcial) — quem ficou de fora volta a lista de
    espera ou e desconsiderado, sempre com motivo;
  * frasco/lote/validade e baixa de estoque por animal (ou "desconsiderar
    estoque" com motivo: frasco do veterinario, sem baixa);
  * dose fixa do protocolo ou, quando a marca e por kg de peso vivo, dose
    individual pelo peso do animal (pesagem > estimativa pela media do lote);
  * ciencia dos itens pendentes do checklist (nunca bloqueia; fica gravada);
  * carencia calculada, linha em Sanidade por animal e log com quem/quando/canal;
  * EXAME (tuberculina/brucelose): inoculacao -> leitura (72 h) com resultado por animal, ou coleta —
    ver `fazenda.rules.exame_preventivo` (mesmo endpoint, mesmo canal, mesmo desfazer/estornar).

Desfazer (<= 10 s, sem motivo) e Estornar (admin, com motivo) revertem tudo e
preservam o registro original como "estornada".
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta

from sqlalchemy import or_
from sqlmodel import Session, select

from fazenda.models import (
    Animal, CalendarioSanitario, ChecklistItem, CronogramaSanitario, CronogramaSanitarioAnimal,
    CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacaoAnimal, CronogramaSanitarioLog, Estoque, EventoSanitario,
    LoteEstoque, MovimentoEstoque, Pessoa, PesagemCorporal, Sanidade,
)
from fazenda.rules import checklist_sanitario as checklist_rules
from fazenda.rules.checklist_sanitario import ChecklistError, materializar_checklist
from fazenda.rules.estoque_baixa import (
    baixar as _estoque_baixar, carencia_para_item, devolver as _estoque_devolver, lotes_disponiveis,
    resolver_item as _resolver_item, resolver_marca_comercial,
)
from fazenda.rules.unidades import pode_dar_baixa_direta, unidades_compativeis, unidades_iguais

DESFAZER_SEGUNDOS = 10
# Protocolos > Acompanhamento, Agenda (site e app) e Curral (app do peao: 1o toque simples, aplicador obrigatorio).
CANAIS = ("Protocolos", "Agenda", "Curral")
DESTINOS = ("espera", "naoSeAplica")
MOTIVOS_JA_APLICADO = ("Dose extra", "Reforço", "Outro")   # "aplicar mesmo assim" (animal que já recebeu o produto no ciclo)
_HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_B19_RE = re.compile(r"\bb19\b")
B19_MESES_MIN, B19_MESES_MAX = 3, 8
_PALAVRAS_VET = re.compile(r"(brucelose|\bb19\b|\brb51\b|tuberculose|tuberculina|\bppd\b|\btb\b)")


class AplicacaoError(Exception):
    """Erro de uso da aplicacao — o router converte em HTTP (400 por padrao)."""

    def __init__(self, mensagem: str, status: int = 400) -> None:
        super().__init__(mensagem)
        self.status = status


# ───────────────────────────── utilitarios ─────────────────────────────
def _norm(s: str | None) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _uid(user) -> int | None:
    return getattr(user, "id", None) if user is not None else None


def _nome_usuario(user) -> str | None:
    return (getattr(user, "nome", None) or getattr(user, "username", None)) if user is not None else None


def _json_lista(txt: str | None) -> list:
    if not txt:
        return []
    try:
        v = json.loads(txt)
    except (TypeError, ValueError):
        return []
    return v if isinstance(v, list) else []


def exige_veterinario(evento: EventoSanitario | None, produto: str | None = None, doenca_nome: str | None = None) -> bool:
    """Brucelose (B19/RB51) e tuberculose (TB) so podem ser aplicadas por
    veterinario habilitado — regra sanitaria oficial (PNCEBT)."""
    texto = _norm(" ".join(filter(None, [evento.nome if evento else None, produto, doenca_nome])))
    return bool(_PALAVRAS_VET.search(texto))


def eh_b19(evento: EventoSanitario | None, produto: str | None = None) -> bool:
    return bool(_B19_RE.search(_norm(" ".join(filter(None, [evento.nome if evento else None, produto])))))


def _idade_em_meses(nasc: date, hoje: date) -> int:
    meses = (hoje.year - nasc.year) * 12 + hoje.month - nasc.month
    return meses - (1 if hoje.day < nasc.day else 0)


def restricao_b19(animal: Animal | None, hoje: date | None = None, *, so_sexo: bool = False) -> str | None:
    """Brucelose B19: so femea de 3 a 8 meses. Devolve o motivo da restricao (ou None). `so_sexo=True` confere
    apenas o sexo (a idade so trava na hora de aplicar)."""
    if animal is None:
        return None
    if (animal.sexo or "").upper() == "M":
        return "B19 só vale para fêmeas de 3 a 8 meses: este animal é macho"
    if so_sexo or animal.data_nasc is None:
        return None
    meses = _idade_em_meses(animal.data_nasc, hoje or date.today())
    if meses < B19_MESES_MIN or meses > B19_MESES_MAX:
        return f"B19 só vale para fêmeas de 3 a 8 meses: este animal tem {meses} {'mês' if meses == 1 else 'meses'}"
    return None


def _tipo_veterinario(pessoa: Pessoa | None) -> bool:
    return pessoa is not None and "veterinario" in _norm(pessoa.tipo)


def eh_veterinario(pessoa: Pessoa | None) -> bool:
    """So veterinario COM CRMV preenchido pode aplicar/inocular/ler B19, brucelose e tuberculose."""
    return _tipo_veterinario(pessoa) and bool((getattr(pessoa, "crmv", None) or "").strip())


def exigir_veterinario_habilitado(evento, produto: str | None, doenca_nome: str | None, aplicador: Pessoa) -> None:
    if not exige_veterinario(evento, produto, doenca_nome) or eh_veterinario(aplicador):
        return
    if _tipo_veterinario(aplicador):
        raise AplicacaoError(f"{evento.nome}: Cadastre o CRMV de {aplicador.nome} em Pessoas para ele(a) aplicar.")
    raise AplicacaoError(f"{evento.nome}: só veterinário habilitado (CRMV) aplica. Escolha o veterinário em “Quem aplicou”.")


def _pessoa_da_fazenda(session: Session, pessoa_id: int | None, fazenda_id: int | None) -> Pessoa | None:
    if not pessoa_id:
        return None
    p = session.get(Pessoa, pessoa_id)
    if p is None or not p.ativo or (fazenda_id is not None and p.fazenda_id not in (None, fazenda_id)):
        return None
    return p


def pessoas_da_fazenda(session: Session, fazenda_id: int | None) -> list[Pessoa]:
    query = select(Pessoa).where(Pessoa.ativo == True)  # noqa: E712
    pessoas = session.exec(query.order_by(Pessoa.nome)).all()
    return [p for p in pessoas if fazenda_id is None or p.fazenda_id in (None, fazenda_id)]


def registrar_log(
    session: Session, cron: CronogramaSanitario, acao: str, *, user=None, canal: str | None = None,
    motivo: str | None = None, detalhe: str | None = None, aplicacao_id: int | None = None, agora: datetime | None = None,
) -> CronogramaSanitarioLog:
    linha = CronogramaSanitarioLog(
        fazenda_id=cron.fazenda_id, cronograma_id=cron.id, aplicacao_id=aplicacao_id, usuario_id=_uid(user),
        usuario_nome=_nome_usuario(user), acao=acao, canal=canal, motivo=(motivo or None), detalhe=detalhe,
        criado_em=agora or datetime.utcnow(),
    )
    session.add(linha)
    return linha


def log_do_agendamento(session: Session, cronograma_id: int) -> list[dict]:
    linhas = session.exec(
        select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == cronograma_id)
        .order_by(CronogramaSanitarioLog.id)
    ).all()
    return [
        {"id": l.id, "acao": l.acao, "canal": l.canal, "motivo": l.motivo, "detalhe": l.detalhe,
         "usuario_id": l.usuario_id, "usuario_nome": l.usuario_nome, "criado_em": l.criado_em.isoformat(),
         "aplicacao_id": l.aplicacao_id}
        for l in linhas
    ]


# ───────────────────────────── checklist ─────────────────────────────
def _compra_nao_necessaria(session: Session, cron: CronogramaSanitario, itens: list[ChecklistItem]) -> bool:
    """Item de compra pendente que nao precisa de acao: o estoque foi desconsiderado ou o estoque cobre."""
    est = next((i for i in itens if i.chave == "estoque"), None)
    if est is not None and est.status == "pulado":
        return True
    from fazenda.rules import financeiro_preventivo as fin
    try:
        return bool(fin.necessidade(session, cron, cron.fazenda_id)["cobre"])
    except AplicacaoError:
        return False


def _bloco_veterinario(session: Session, cron: CronogramaSanitario, itens: list[ChecklistItem]) -> dict | None:
    """Quem foi confirmado como veterinario (Pessoa/CRMV), por quem e quando."""
    vet = next((i for i in itens if i.chave == "vet"), None)
    if vet is None and not cron.veterinario_pessoa_id:
        return None
    pessoa = session.get(Pessoa, cron.veterinario_pessoa_id) if cron.veterinario_pessoa_id else None
    confirmado = bool(vet is not None and vet.status == "cumprido" and vet.resposta == "sim")
    por = _nomes_usuarios(session, {vet.responsavel_usuario_id}).get(vet.responsavel_usuario_id) if vet is not None and vet.responsavel_usuario_id else None
    return {
        "estado": "confirmado" if confirmado else ("desconsiderado" if vet is not None and vet.status == "pulado" else "pendente"),
        "pessoa_id": pessoa.id if pessoa else None, "nome": pessoa.nome if pessoa else None,
        "crmv": getattr(pessoa, "crmv", None) if pessoa else None,
        "confirmado_em": vet.respondido_em.isoformat() if confirmado and vet.respondido_em else None,
        "registrado_por": por, "observacao": vet.observacao if vet is not None else None,
    }


def checklist_resumo(session: Session, cron: CronogramaSanitario) -> dict:
    """x/y do checklist do agendamento. Desconsiderado inteiro conta como
    resolvido (e nao gera ciencia de pendentes). Compra 'Nao necessaria'
    (estoque desconsiderado ou que cobre) conta como resolvida."""
    itens = session.exec(
        select(ChecklistItem).where(ChecklistItem.cronograma_id == cron.id).order_by(ChecklistItem.ordem, ChecklistItem.id)
    ).all()
    compra_ok = any(i.chave == "compra" and i.status == "pendente" for i in itens) and _compra_nao_necessaria(session, cron, itens)

    def _pendente(i: ChecklistItem) -> bool:
        if i.status != "pendente" or cron.checklist_desconsiderado:
            return False
        return not (i.chave == "compra" and compra_ok)

    pendentes = [i for i in itens if _pendente(i)]
    resolvidos = len(itens) if cron.checklist_desconsiderado else len(itens) - len(pendentes)
    vet = next((i for i in itens if i.chave == "vet"), None)

    def _linha(i: ChecklistItem) -> dict:
        derivado = i.chave == "compra" and i.status == "pendente" and compra_ok
        return {"id": i.id, "chave": i.chave, "nome": i.nome, "status": "cumprido" if derivado else i.status,
                "resposta": "nao_necessaria" if derivado else i.resposta, "observacao": i.observacao, "ordem": i.ordem}

    return {
        "total": len(itens), "resolvidos": resolvidos, "desconsiderado": bool(cron.checklist_desconsiderado),
        "vet_nao_confirmou": bool(vet and vet.resposta == "nao"),
        "veterinario": _bloco_veterinario(session, cron, list(itens)),
        "itens": [_linha(i) for i in itens],
        "pendentes": [{"id": i.id, "chave": i.chave, "nome": i.nome} for i in pendentes],
    }


def _item_checklist(session: Session, cron: CronogramaSanitario, chave: str) -> ChecklistItem | None:
    return session.exec(
        select(ChecklistItem).where(ChecklistItem.cronograma_id == cron.id).where(ChecklistItem.chave == chave)
        .order_by(ChecklistItem.ordem, ChecklistItem.id)
    ).first()


def _reabrir_item(session: Session, item: ChecklistItem) -> None:
    item.status = "pendente"
    item.resposta = None
    item.observacao = None
    item.respondido_em = None
    item.responsavel_usuario_id = None
    session.add(item)
    session.commit()


def _motivo_obrigatorio(motivo: str | None, o_que: str) -> str:
    m = (motivo or "").strip()
    if not m:
        raise AplicacaoError(f"Informe o motivo para desconsiderar {o_que}")
    return m


def aplicar_checklist(
    session: Session, cron: CronogramaSanitario, dados: dict, *, user=None, fazenda_id: int | None = None,
) -> None:
    """Passo "Checklist" do assistente Criar agendamento (e edicao posterior):
    veterinario confirmado/desconsiderado (motivo), estoque vinculado/
    desconsiderado (motivo, com lote/validade do veterinario), data e os demais
    itens/extras. Valida tudo antes de mexer (nada pela metade)."""
    calendario = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    evento = session.get(EventoSanitario, calendario.evento_sanitario_id) if calendario else None
    if evento is not None:
        materializar_checklist(session, cron, evento)
    agora = datetime.utcnow()
    uid = _uid(user)

    vet = dados.get("veterinario") or None
    est = dados.get("estoque") or None
    data = dados.get("data") or None
    extras = [(e.get("texto") or "").strip() for e in (dados.get("extras") or [])]
    itens = dados.get("itens") or []

    # ── validacao ──
    vet_pessoa: Pessoa | None = None
    if vet and vet.get("estado") == "confirmado":
        vet_pessoa = _pessoa_da_fazenda(session, vet.get("pessoa_id"), fazenda_id)
        if vet_pessoa is None:
            raise AplicacaoError("Veterinário não encontrado")
    vet_quando: datetime | None = None
    if vet and vet.get("estado") == "confirmado" and vet.get("quando"):
        try:
            vet_quando = datetime.fromisoformat(str(vet["quando"]).replace("Z", ""))
        except ValueError:
            raise AplicacaoError("Data e hora da confirmação do veterinário inválidas")
        if vet_quando > agora + timedelta(minutes=5):
            raise AplicacaoError("A confirmação com o veterinário não pode estar no futuro")
    if vet and vet.get("estado") == "desconsiderado":
        _motivo_obrigatorio(vet.get("motivo"), "o veterinário")
    est_item: Estoque | None = None
    if est and est.get("estado") == "vinculado":
        est_item = session.get(Estoque, est.get("estoque_id")) if est.get("estoque_id") else None
        if est_item is None or (fazenda_id is not None and est_item.fazenda_id != fazenda_id):
            raise AplicacaoError("Produto do estoque não encontrado")
        if est.get("lote_id"):
            lote = session.get(LoteEstoque, est["lote_id"])
            if lote is None or lote.estoque_id != est_item.id:
                raise AplicacaoError("Frasco/lote não pertence a este produto")
    if est and est.get("estado") == "desconsiderado":
        _motivo_obrigatorio(est.get("motivo"), "o estoque")
    if data and data.get("estado") == "confirmado" and not (cron.hora or "").strip():
        raise AplicacaoError("Informe a hora do agendamento antes de confirmar a data")
    validos = {i.id: i for i in session.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == cron.id)).all()}
    for it in itens:
        item = validos.get(it.get("item_id"))
        if item is None:
            raise AplicacaoError("Item do checklist não pertence a este agendamento")
        acao = it.get("acao")
        if acao not in ("cumprir", "pular", "reabrir"):
            raise AplicacaoError('Ação inválida — use "cumprir", "pular" ou "reabrir"')
        if acao == "pular":
            _motivo_obrigatorio(it.get("motivo"), f'o item "{item.nome}"')

    # ── gravacao ──
    try:
        if vet:
            item = _item_checklist(session, cron, "vet")
            if vet.get("estado") == "confirmado":
                cron.veterinario_pessoa_id = vet_pessoa.id
                cron.modo_execucao = "veterinario"
                if item is not None:
                    checklist_rules.responder_veterinario(session, item.id, "sim", None, uid, vet_quando or agora, cron.fazenda_id)
                    if (vet.get("observacao") or "").strip():
                        item = session.get(ChecklistItem, item.id)
                        item.observacao = vet["observacao"].strip()
                        session.add(item)
                        session.commit()
                quando_txt = (vet_quando or agora).strftime("%d/%m/%Y %H:%M")
                registrar_log(
                    session, cron, "Confirmou o veterinário", user=user, agora=agora,
                    detalhe=f"{vet_pessoa.nome}{f' ({vet_pessoa.crmv})' if getattr(vet_pessoa, 'crmv', None) else ''} · confirmado em {quando_txt}",
                )
            elif vet.get("estado") == "desconsiderado" and item is not None:
                checklist_rules.marcar_pulado(session, item.id, vet["motivo"].strip(), uid, agora, cron.fazenda_id)
            elif vet.get("estado") == "pendente" and item is not None:
                _reabrir_item(session, item)
        if est:
            item = _item_checklist(session, cron, "estoque")
            if item is not None:
                if est.get("estado") == "vinculado":
                    checklist_rules.marcar_cumprido(session, item.id, uid, agora, cron.fazenda_id)
                    item = session.get(ChecklistItem, item.id)
                    ref = {"estoque_id": est_item.id}
                    if est.get("lote_id"):
                        ref["lote_id"] = est["lote_id"]
                    item.resposta = json.dumps(ref)
                    session.add(item)
                    session.commit()
                elif est.get("estado") == "desconsiderado":
                    checklist_rules.marcar_pulado(session, item.id, est["motivo"].strip(), uid, agora, cron.fazenda_id)
                    item = session.get(ChecklistItem, item.id)
                    ref = {k: v for k, v in (("lote", (est.get("lote") or "").strip() or None), ("validade", est.get("validade"))) if v}
                    item.resposta = json.dumps(ref) if ref else None
                    session.add(item)
                    session.commit()
                elif est.get("estado") == "pendente":
                    _reabrir_item(session, item)
        if data:
            item = _item_checklist(session, cron, "horario")
            if item is not None:
                if data.get("estado") == "confirmado":
                    checklist_rules.confirmar_horario(session, item.id, cron.hora, uid, agora, cron.fazenda_id)
                elif data.get("estado") == "pendente":
                    _reabrir_item(session, item)
        ordem = max([i.ordem for i in validos.values()] or [0])
        for texto in extras:
            if not texto:
                continue
            ordem += 1
            session.add(ChecklistItem(cronograma_id=cron.id, chave="custom", nome=texto, ordem=ordem, fazenda_id=cron.fazenda_id))
        session.commit()
        for it in itens:
            acao = it["acao"]
            if acao == "cumprir":
                checklist_rules.marcar_cumprido(session, it["item_id"], uid, agora, cron.fazenda_id)
            elif acao == "pular":
                checklist_rules.marcar_pulado(session, it["item_id"], it["motivo"].strip(), uid, agora, cron.fazenda_id)
            else:
                _reabrir_item(session, session.get(ChecklistItem, it["item_id"]))
        cron.atualizado_em = agora
        session.add(cron)
        session.commit()
    except ChecklistError as e:
        session.rollback()
        raise AplicacaoError(str(e))

    # Fatia 9: compra/pagamento/conta a pagar. O estoque desconsiderado torna a compra "Nao necessaria".
    from fazenda.rules import financeiro_preventivo as fin
    if est or dados.get("financeiro"):
        if evento is not None and cron.status in fin.STATUS_ATIVOS:
            fin.garantir_itens_financeiros(session, cron, evento)
        fin.sincronizar_itens(session, cron, user=user, agora=agora)
    if dados.get("financeiro"):
        fin.aplicar_payload_financeiro(session, cron, dados["financeiro"], user=user, fazenda_id=fazenda_id)


# ───────────────────────────── dose e estoque ─────────────────────────────
def _marca_e_item(
    session: Session, produto: str | None, fazenda_id: int | None, estoque_id: int | None,
):
    """(item de estoque, marca comercial) do produto do protocolo. Um `estoque_id`
    de OUTRA fazenda nunca e aceito (nem cai em silencio para outro item)."""
    item = None
    if estoque_id is not None:
        item = session.get(Estoque, estoque_id)
        if item is None or (fazenda_id is not None and item.fazenda_id != fazenda_id):
            raise AplicacaoError("Produto do estoque não encontrado nesta fazenda")
    else:
        item = _resolver_item(session, fazenda_id=fazenda_id, produto=produto)
    marca = resolver_marca_comercial(
        session, item=item, nome=produto, principio_ativo_id=item.principio_ativo_id if item else None,
    )
    return item, marca


def _modo_dose(evento: EventoSanitario | None, marca) -> dict:
    """Dose fixa por animal ou por kg de peso vivo (`dose_base = por_kg_pv`)."""
    unidade = (marca.unidade_dose if marca and marca.unidade_dose else None) or (evento.unidade_padrao if evento else None)
    if marca and marca.dose_base == "por_kg_pv" and marca.dose_referencia_kg and marca.dose_padrao:
        return {"por_peso": True, "dose_ref": float(marca.dose_padrao), "kg_ref": float(marca.dose_referencia_kg),
                "unidade": unidade or (evento.unidade_padrao if evento else None)}
    dose = evento.dose_padrao if evento and evento.dose_padrao is not None else (marca.dose_padrao if marca else None)
    return {"por_peso": False, "dose": dose, "unidade": (evento.unidade_padrao if evento and evento.unidade_padrao else unidade)}


def _peso_animal(session: Session, numero: str, fazenda_id: int | None, hoje: date) -> float | None:
    query = select(PesagemCorporal).where(PesagemCorporal.numero_matriz == numero).where(PesagemCorporal.data_pesagem <= hoje)
    if fazenda_id is not None:
        query = query.where(PesagemCorporal.fazenda_id == fazenda_id)
    p = session.exec(query.order_by(PesagemCorporal.data_pesagem.desc(), PesagemCorporal.id.desc())).first()
    return p.peso_kg if p else None


def calcular_doses(
    session: Session, numeros: list[str], modo: dict, fazenda_id: int | None, hoje: date, pesos: dict[str, float] | None = None,
) -> dict[str, dict]:
    """Dose e peso de cada animal. Por peso: peso informado na hora > ultima
    pesagem > estimativa (media do lote); sem nenhum dos tres, `dose=None`."""
    pesos = pesos or {}
    animais = {
        a.numero: a for a in session.exec(select(Animal).where(Animal.numero.in_(numeros))).all()
        if fazenda_id is None or a.fazenda_id == fazenda_id
    } if numeros else {}
    saida: dict[str, dict] = {}
    media_lote: dict[str, float | None] = {}

    def _media(grupo: str | None) -> float | None:
        if not grupo:
            return None
        if grupo not in media_lote:
            colegas = [a.numero for a in session.exec(select(Animal).where(Animal.grupo_primario == grupo)).all()
                       if fazenda_id is None or a.fazenda_id == fazenda_id]
            valores = [p for p in (_peso_animal(session, n, fazenda_id, hoje) for n in colegas) if p]
            media_lote[grupo] = sum(valores) / len(valores) if valores else None
        return media_lote[grupo]

    for n in numeros:
        if not modo["por_peso"]:
            saida[n] = {"dose": modo.get("dose"), "peso_kg": None, "peso_estimado": False}
            continue
        peso, estimado = pesos.get(n), False
        if peso is None:
            peso = _peso_animal(session, n, fazenda_id, hoje)
        if peso is None:
            peso, estimado = _media(animais[n].grupo_primario if n in animais else None), True
        dose = round(peso / modo["kg_ref"] * modo["dose_ref"], 4) if peso else None
        saida[n] = {"dose": dose, "peso_kg": round(peso, 2) if peso else None, "peso_estimado": bool(peso and estimado)}
    return saida


def _vencido(lote: LoteEstoque | None, data: date) -> bool:
    return bool(lote and lote.validade and lote.validade < data)


def _escolher_lote(item: Estoque, lote_id: int | None, session: Session, data: date) -> LoteEstoque | None:
    """Lote escolhido, ou o valido mais antigo (nunca o vencido de graca)."""
    if lote_id is not None:
        lote = session.get(LoteEstoque, lote_id)
        if lote is None or lote.estoque_id != item.id:
            raise AplicacaoError("Frasco/lote não pertence a este produto")
        return lote
    lotes = lotes_disponiveis(session, estoque_id=item.id)
    if not lotes:
        return None
    return next((l for l in lotes if not _vencido(l, data)), lotes[0])


# ───────────────────────────── serializacao ─────────────────────────────
def _animais_da_aplicacao(session: Session, aplicacao_id: int) -> list[CronogramaSanitarioAplicacaoAnimal]:
    linhas = session.exec(
        select(CronogramaSanitarioAplicacaoAnimal).where(CronogramaSanitarioAplicacaoAnimal.aplicacao_id == aplicacao_id)
    ).all()
    return sorted(linhas, key=lambda l: (len(l.numero_matriz), l.numero_matriz))


def pode_desfazer(ap: CronogramaSanitarioAplicacao, agora: datetime | None = None) -> bool:
    agora = agora or datetime.utcnow()
    return ap.estado == "aplicada" and (agora - ap.registrado_em).total_seconds() <= DESFAZER_SEGUNDOS


def _rotulo_estado(ap: CronogramaSanitarioAplicacao, *, exame: bool) -> str:
    """"Exame realizado" para exame (nunca "Aplicado"), "Aplicado" para vacina/vermifugo, "Estornada" quando revertida."""
    if ap.estado == "estornada":
        return "Estornada"
    return "Exame realizado" if exame else "Aplicado"


def _unidade_do_estoque(session: Session, ap: CronogramaSanitarioAplicacao) -> str | None:
    item = session.get(Estoque, ap.estoque_id) if ap.estoque_id else None
    return item.unidade if item else None


def serializar_aplicacao(session: Session, ap: CronogramaSanitarioAplicacao, *, animais: bool = True) -> dict:
    d = ap.model_dump()
    for k, v in list(d.items()):
        if isinstance(v, (date, datetime)):
            d[k] = v.isoformat()
    d["excecoes"] = _json_lista(ap.excecoes)
    d["ciencia_itens"] = _json_lista(ap.ciencia_itens)
    agora = datetime.utcnow()
    d["pode_desfazer"] = pode_desfazer(ap, agora)
    d["desfazer_restante_s"] = max(0, DESFAZER_SEGUNDOS - int((agora - ap.registrado_em).total_seconds())) if d["pode_desfazer"] else 0
    if animais:
        d["animais"] = [
            {"numero_matriz": a.numero_matriz, "resultado": a.resultado, "origem": a.origem, "motivo_origem": a.motivo_origem,
             "dose": a.dose, "unidade": a.unidade, "peso_kg": a.peso_kg, "peso_estimado": a.peso_estimado,
             "motivo_nao": a.motivo_nao, "destino_nao": a.destino_nao,
             "exame_resultado": a.exame_resultado, "espessura_mm": a.espessura_mm, "reteste_em": _iso(a.reteste_em),
             "notificado_em": a.notificado_em.isoformat() if a.notificado_em else None,
             "notificado_por": a.notificado_por_nome, "notificacao_ref": a.notificacao_ref}
            for a in _animais_da_aplicacao(session, ap.id)
        ]
    d["rotulo_estado"] = _rotulo_estado(ap, exame=ap.fase is not None)
    # Unidade da dose x unidade do estoque: a baixa so e automatica quando sao iguais (nada e convertido em silencio).
    item = session.get(Estoque, ap.estoque_id) if ap.estoque_id else None
    d["unidade_estoque"] = item.unidade if item else None
    d["baixa_automatica"] = bool(item is not None and not ap.estoque_desconsiderado and pode_dar_baixa_direta(ap.unidade or "", item.unidade))
    return d


# ───────────────────────────── aplicar ─────────────────────────────
def aplicar(session: Session, cron: CronogramaSanitario, dados: dict, *, user=None, fazenda_id: int | None = None) -> dict:
    """Aplica o agendamento. `dados` (ver AplicarAgendamentoIn no router):
    canal, aplicador_pessoa_id, animais_aplicados, nao_aplicados, data_aplicacao,
    hora, estoque_id, lote_id, ciente_vencido, desconsiderar_estoque + motivo/
    lote/validade do veterinario, pesos, custo, ciencia_pendentes/motivo,
    observacao, chave_idempotencia. Devolve {aplicacao, agendamento, avisos,
    idempotente}."""
    hoje = date.today()
    agora = datetime.utcnow()
    chave = (dados.get("chave_idempotencia") or "").strip() or None
    if chave:
        existente = session.exec(
            select(CronogramaSanitarioAplicacao).where(CronogramaSanitarioAplicacao.cronograma_id == cron.id)
            .where(CronogramaSanitarioAplicacao.chave_idempotencia == chave)
        ).first()
        if existente is not None:
            session.refresh(cron)
            return {"aplicacao": serializar_aplicacao(session, existente), "agendamento": cron, "avisos": [], "idempotente": True,
                    "financeiro": _financeiro_da_aplicacao(session, cron, existente, fazenda_id)}

    canal = dados.get("canal") or "Protocolos"
    if canal not in CANAIS:
        raise AplicacaoError('Canal inválido — use "Protocolos", "Agenda" ou "Curral"')
    if cron.status != "agendado":
        if cron.status == "concluido":
            raise AplicacaoError("Este agendamento já foi aplicado")
        if cron.status == "cancelado":
            raise AplicacaoError("Este agendamento foi cancelado — só um agendamento em estado Agendado pode ser aplicado")
        raise AplicacaoError("Só um agendamento em estado Agendado pode ser aplicado "
                             f"(este está {'em montagem' if cron.status == 'em_montagem' else 'na lista de espera'})")
    calendario = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    evento = session.get(EventoSanitario, calendario.evento_sanitario_id) if calendario else None
    if calendario is None or evento is None:
        raise AplicacaoError("Protocolo do agendamento não encontrado", 404)
    if evento.categoria_preventiva == "exame":
        from fazenda.rules import exame_preventivo
        return exame_preventivo.aplicar_exame(
            session, cron, calendario, evento, dados, user=user, fazenda_id=fazenda_id, canal=canal, chave=chave,
        )

    # ── aplicador ──
    aplicador = _pessoa_da_fazenda(session, dados.get("aplicador_pessoa_id"), fazenda_id)
    if aplicador is None:
        raise AplicacaoError("Escolha quem aplicou (aplicador não encontrado)")
    produto = (calendario.produto or evento.produto_padrao or "").strip() or None
    doenca_nome = None
    if evento.doenca_id:
        from fazenda.models import Doenca
        d = session.get(Doenca, evento.doenca_id)
        doenca_nome = d.nome if d else None
    exigir_veterinario_habilitado(evento, produto, doenca_nome, aplicador)

    # ── data e hora ──
    data_ap = dados.get("data_aplicacao") or hoje
    if isinstance(data_ap, str):
        data_ap = date.fromisoformat(data_ap)
    if data_ap > hoje:
        raise AplicacaoError("A data real da aplicação não pode ser futura")
    hora = (dados.get("hora") or "").strip() or None
    if hora and not _HORA_RE.match(hora):
        raise AplicacaoError("Hora inválida — use HH:MM")
    if hora is None and data_ap == hoje:
        hora = datetime.now().strftime("%H:%M")

    # ── animais ──
    linhas = session.exec(
        select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
        .where(CronogramaSanitarioAnimal.status == "incluido")
    ).all()
    por_numero = {l.numero_matriz: l for l in linhas}
    aplicados = list(dict.fromkeys((n or "").strip() for n in (dados.get("animais_aplicados") or []) if (n or "").strip()))
    if not aplicados:
        raise AplicacaoError("Marque pelo menos 1 animal aplicado")
    for n in aplicados:
        if n not in por_numero:
            raise AplicacaoError(f"Animal {n} não está neste agendamento")
    nao_in = {(x.get("numero_matriz") or "").strip(): x for x in (dados.get("nao_aplicados") or [])}
    restantes = sorted((n for n in por_numero if n not in aplicados), key=lambda n: (len(n), n))
    for n in restantes:
        x = nao_in.get(n)
        if not x or not (x.get("motivo") or "").strip():
            raise AplicacaoError(f"Informe o motivo do animal {n} que não foi aplicado")
        if (x.get("destino") or "espera") not in DESTINOS:
            raise AplicacaoError(f"Destino inválido para o animal {n} — use espera ou naoSeAplica")
    for n in nao_in:
        if n not in restantes:
            raise AplicacaoError(f"Animal {n} não pode constar como não aplicado")
    # Animal que JÁ recebeu o produto no ciclo (por qualquer caminho): aplicar de novo exige decisão explícita por animal.
    from fazenda.rules.cronograma_sanitario import _data_devida
    from fazenda.rules.ja_aplicado_preventivo import aplicacoes_no_ciclo, fmt_data
    ja_no_ciclo = aplicacoes_no_ciclo(session, calendario, aplicados, hoje=hoje, devida=_data_devida(cron), ate=data_ap, evento=evento)
    decisoes = {(k or "").strip(): (v or {}) for k, v in (dados.get("ja_aplicados") or {}).items()}
    for n in aplicados:
        if n not in ja_no_ciclo:
            continue
        info = ja_no_ciclo[n]
        d = decisoes.get(n) or {}
        motivo_ja = (d.get("motivo") or "").strip()
        if not motivo_ja:
            raise AplicacaoError(
                f"Animal {n} já recebeu {info['produto']} em {fmt_data(info['data'])} ({info['fonte']}), dentro do ciclo desta regra. "
                "Escolha 'Aplicar mesmo assim' (dose extra ou reforço) ou desconsidere o animal do agendamento."
            )
        if motivo_ja not in MOTIVOS_JA_APLICADO:
            raise AplicacaoError(f"Motivo inválido para o animal {n} — use {', '.join(MOTIVOS_JA_APLICADO)}")
        if motivo_ja == "Outro" and not (d.get("observacao") or "").strip():
            raise AplicacaoError(f"Descreva o motivo de aplicar de novo no animal {n}")
    from fazenda.rules import exame_preventivo
    exame_preventivo.recusar_reagentes(session, fazenda_id, aplicados, "vacina nem outro agendamento")
    if eh_b19(evento, produto):
        animais_b19 = {a.numero: a for a in session.exec(select(Animal).where(Animal.numero.in_(aplicados))).all()
                       if fazenda_id is None or a.fazenda_id == fazenda_id}
        proibidos = [(n, restricao_b19(animais_b19.get(n), hoje)) for n in aplicados]
        proibidos = [(n, m) for n, m in proibidos if m]
        if proibidos:
            raise AplicacaoError(
                "Brucelose B19: só fêmeas de 3 a 8 meses. "
                + "; ".join(f"animal {n}: {m.split(': ', 1)[1]}" for n, m in proibidos)
                + ". Desmarque esses animais (motivo: Outro)."
            )

    # ── produto, frasco e dose ──
    desconsiderar = bool(dados.get("desconsiderar_estoque"))
    motivo_estoque = (dados.get("motivo_desconsiderar_estoque") or "").strip()
    if desconsiderar and not motivo_estoque:
        raise AplicacaoError("Informe o motivo para desconsiderar o estoque")
    item, marca = _marca_e_item(session, produto, fazenda_id, dados.get("estoque_id"))
    if item is None and not desconsiderar:
        raise AplicacaoError(
            f'"{produto or "produto do protocolo"}" não está no estoque desta fazenda: escolha o frasco ou '
            "desconsidere o estoque informando o motivo"
        )
    modo = _modo_dose(evento, marca)
    if modo.get("unidade") is None or (not modo["por_peso"] and modo.get("dose") is None):
        raise AplicacaoError(f'Informe a dose e a unidade no protocolo "{evento.nome}" (cadastro do protocolo)')
    if item is not None and not desconsiderar and modo["unidade"] not in unidades_compativeis(item.unidade):
        raise AplicacaoError(
            f'Unidade "{modo["unidade"]}" não é compatível com o produto "{item.nome}" '
            f'(aceitas: {", ".join(unidades_compativeis(item.unidade))})'
        )
    doses = calcular_doses(session, aplicados, modo, fazenda_id, hoje, dados.get("pesos"))
    sem_peso = [n for n in aplicados if doses[n]["dose"] is None]
    if sem_peso:
        raise AplicacaoError("Sem peso para calcular a dose de: " + ", ".join(sem_peso) + ". Informe o peso desses animais.")

    lote = None
    lote_texto = None
    validade = None
    ciente_vencido = bool(dados.get("ciente_vencido"))
    if desconsiderar:
        lote_texto = (dados.get("lote_veterinario") or "").strip() or None
        validade = dados.get("validade_veterinario")
        if isinstance(validade, str):
            validade = date.fromisoformat(validade)
    elif item is not None:
        lote = _escolher_lote(item, dados.get("lote_id"), session, data_ap)
        if lote is not None:
            lote_texto, validade = lote.numero_lote, lote.validade
            if _vencido(lote, data_ap) and not ciente_vencido:
                raise AplicacaoError(
                    f"Frasco vencido: o lote {lote.numero_lote or lote.id} venceu em {lote.validade.strftime('%d/%m/%Y')}. "
                    "Marque a ciência para usar assim mesmo."
                )

    # ── ciencia dos pendentes ──
    resumo = checklist_resumo(session, cron)
    pendentes = resumo["pendentes"]
    ciente_pend = bool(dados.get("ciencia_pendentes"))
    if pendentes and not ciente_pend:
        raise AplicacaoError(
            f"Marque a ciência dos {len(pendentes)} {'item pendente' if len(pendentes) == 1 else 'itens pendentes'} "
            f"do checklist ({', '.join(p['nome'] for p in pendentes)}). Aplicar não é bloqueado."
        )

    # ── tudo validado: grava ──
    total = round(sum(doses[n]["dose"] for n in aplicados), 4)
    custo = dados.get("custo")
    if custo is None and item is not None and not desconsiderar and item.valor_unitario is not None:
        custo = round(total * item.valor_unitario, 2)
    carencia = carencia_para_item(item, marca, data_aplicacao=data_ap)
    fora = sum(1 for n in aplicados if por_numero[n].origem == "fora_janela")
    excecoes: list[str] = []
    if fora:
        excecoes.append(f"{fora} {'animal' if fora == 1 else 'animais'} fora da janela de aplicação")
    if desconsiderar:
        excecoes.append("Frasco do veterinário (sem baixa de estoque)" if motivo_estoque.lower() == "frasco do veterinário"
                        else f"Estoque desconsiderado (sem baixa): {motivo_estoque}")
    if lote is not None and _vencido(lote, data_ap):
        excecoes.append(f"Frasco vencido usado com ciência (lote {lote_texto or lote.id})")
    if pendentes:
        excecoes.append(f"Ciência de {len(pendentes)} {'item pendente' if len(pendentes) == 1 else 'itens pendentes'} do checklist")
    if item is not None and not desconsiderar and not unidades_iguais(modo["unidade"], item.unidade):
        excecoes.append(
            f'Unidade da dose ({modo["unidade"]}) diferente da do estoque ({item.unidade or "sem unidade"}): sem baixa automática'
        )
    for n in aplicados:
        if n in ja_no_ciclo:
            d = decisoes[n]
            extra = f": {d['observacao'].strip()}" if (d.get("motivo") == "Outro" and d.get("observacao")) else ""
            excecoes.append(
                f"Animal {n} aplicado mesmo já tendo recebido o produto em {fmt_data(ja_no_ciclo[n]['data'])} ({d['motivo']}{extra})"
            )
    if data_ap < hoje:
        excecoes.append("Lançamento retroativo")
    if data_ap < cron.data_evento:
        excecoes.append(f"Aplicado antes da data agendada ({cron.data_evento.strftime('%d/%m/%Y')})")

    ap = CronogramaSanitarioAplicacao(
        fazenda_id=cron.fazenda_id, cronograma_id=cron.id, estado="aplicada", canal=canal,
        aplicador_pessoa_id=aplicador.id, aplicador_nome=aplicador.nome, aplicador_crmv=getattr(aplicador, "crmv", None),
        data_aplicacao=data_ap, hora=hora,
        produto=produto, unidade=modo["unidade"], via=evento.via_padrao, dose_total=total,
        estoque_id=None if desconsiderar else (item.id if item else None),
        lote_id=lote.id if lote else None, lote_texto=lote_texto, validade=validade,
        frasco_vencido_ciente=bool(lote is not None and _vencido(lote, data_ap) and ciente_vencido),
        estoque_desconsiderado=desconsiderar, estoque_motivo=motivo_estoque or None, custo=custo,
        carencia_leite_ate=date.fromisoformat(carencia["liberacao_leite"]) if carencia.get("liberacao_leite") else None,
        carencia_carne_ate=date.fromisoformat(carencia["liberacao_carne"]) if carencia.get("liberacao_carne") else None,
        carencia_texto=carencia.get("texto"),
        ciencia_itens=json.dumps([{"chave": p["chave"], "nome": p["nome"]} for p in pendentes]) if pendentes else None,
        ciencia_motivo=(dados.get("ciencia_motivo") or None) if pendentes else None,
        ciencia_usuario_id=_uid(user) if pendentes else None, ciencia_em=agora if pendentes else None,
        retroativo=data_ap < hoje, excecoes=json.dumps(excecoes) if excecoes else None,
        observacao=(dados.get("observacao") or None), chave_idempotencia=chave,
        registrado_por_usuario_id=_uid(user), registrado_em=agora,
    )
    avisos: list[str] = []
    try:
        session.add(ap)
        session.flush()
        for n in aplicados:
            linha = por_numero[n]
            d = doses[n]
            san = Sanidade(
                numero_matriz=n, data_aplicacao=data_ap, produto=produto or "", dose=d["dose"], unidade=modo["unidade"],
                via=evento.via_padrao, responsavel=aplicador.nome, lote=lote_texto, natureza="preventivo",
                obs=f"Preventivo: {evento.nome} (agendamento #{cron.id}, {canal})"
                    + (f" · {decisoes[n]['motivo']} (já aplicado em {fmt_data(ja_no_ciclo[n]['data'])})" if n in ja_no_ciclo else ""),
                usuario_id=_uid(user),
                fazenda_id=cron.fazenda_id,
            )
            session.add(san)
            session.flush()
            session.add(CronogramaSanitarioAplicacaoAnimal(
                aplicacao_id=ap.id, fazenda_id=cron.fazenda_id, numero_matriz=n, resultado="aplicado", origem=linha.origem,
                motivo_origem=linha.motivo if linha.origem == "fora_janela" else None, dose=d["dose"],
                unidade=modo["unidade"], peso_kg=d["peso_kg"], peso_estimado=d["peso_estimado"], sanidade_id=san.id,
            ))
            if item is not None and not desconsiderar:
                avisos.extend(_estoque_baixar(
                    session, item=item, quantidade=d["dose"], unidade=modo["unidade"], data=data_ap, fazenda_id=cron.fazenda_id,
                    observacao=f"Aplicação em {n} — Sanidade (agendamento #{cron.id})", usuario_id=_uid(user),
                    origem_tipo="sanidade", origem_id=san.id, produto=produto, lote_id=lote.id if lote else None,
                ))
            linha.status = "aplicado"
            linha.data_aplicacao = data_ap
            session.add(linha)
        for n in restantes:
            linha = por_numero[n]
            x = nao_in[n]
            destino = x.get("destino") or "espera"
            motivo = x["motivo"].strip()
            session.add(CronogramaSanitarioAplicacaoAnimal(
                aplicacao_id=ap.id, fazenda_id=cron.fazenda_id, numero_matriz=n, resultado="nao_aplicado", origem=linha.origem,
                motivo_origem=linha.motivo if linha.origem == "fora_janela" else None, motivo_nao=motivo, destino_nao=destino,
            ))
            if destino == "espera" and linha.origem != "fora_janela":
                from fazenda.rules.cronograma_sanitario import _data_devida, cronograma_aberto_ou_novo
                espera = cronograma_aberto_ou_novo(session, calendario, _data_devida(cron))
                ja = session.exec(
                    select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == espera.id)
                    .where(CronogramaSanitarioAnimal.numero_matriz == n)
                ).first()
                if ja is not None:
                    session.delete(ja)
                    session.flush()
                linha.cronograma_id = espera.id
                linha.status = "sugerido"
                linha.origem = "janela"
                linha.motivo = None
                linha.data_decisao = None
            else:
                linha.status = "excluido"
                linha.motivo = motivo
                linha.data_decisao = data_ap
            session.add(linha)
        cron.status = "concluido"
        cron.concluido_em = agora
        cron.atualizado_em = agora
        session.add(cron)
        resumo_txt = f"{len(aplicados)} {'animal' if len(aplicados) == 1 else 'animais'}"
        registrar_log(
            session, cron, "Aplicou", user=user, canal=canal, aplicacao_id=ap.id, agora=agora,
            detalhe=f"{resumo_txt}{f' · lote {lote_texto}' if lote_texto else ''} · aplicador {aplicador.nome}",
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(cron)
    session.refresh(ap)
    return {
        "aplicacao": serializar_aplicacao(session, ap), "agendamento": cron, "avisos": avisos, "idempotente": False,
        "financeiro": _financeiro_da_aplicacao(session, cron, ap, fazenda_id),
    }



def _financeiro_da_aplicacao(session: Session, cron: CronogramaSanitario, ap: CronogramaSanitarioAplicacao, fazenda_id: int | None,
                             vinculos: list[dict] | None = None) -> dict:
    """Custo da aplicacao (real, 'a informar' se nao ha) + contas/pagamentos/compras do agendamento."""
    from fazenda.rules import financeiro_preventivo as fin
    if vinculos is None:
        vinculos = fin.vinculos_por_cronogramas(session, [cron.id], fazenda_id).get(cron.id, [])
    motivo = None
    if ap.custo is None:
        if ap.estoque_desconsiderado and (ap.estoque_motivo or "").strip().lower() == fin.MOTIVO_FRASCO_VET:
            motivo = "Frasco do veterinário: informe o custo do frasco"
        else:
            motivo = "Sem preço cadastrado para este produto"
    bloco = fin.bloco_financeiro(vinculos, {"custo_previsto": ap.custo, "custo_a_informar": ap.custo is None, "custo_motivo": motivo})
    bloco["custo"] = ap.custo
    return bloco

# ───────────────────────────── desfazer / estornar ─────────────────────────────
def _reverter(session: Session, ap: CronogramaSanitarioAplicacao, cron: CronogramaSanitario, user, agora: datetime) -> None:
    animais = _animais_da_aplicacao(session, ap.id)
    calendario = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    if ap.fase is not None:
        from fazenda.rules import exame_preventivo
        exame_preventivo.reverter(session, ap, cron, user, agora)
    for a in animais:
        if a.resultado != "aplicado":
            continue
        if a.sanidade_id is not None:
            mov = session.exec(
                select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "sanidade")
                .where(MovimentoEstoque.origem_id == a.sanidade_id).where(MovimentoEstoque.movimento == "Aplicação")
                .order_by(MovimentoEstoque.id.desc())
            ).first()
            if mov is not None and mov.estoque_id is not None and not ap.estoque_desconsiderado:
                _estoque_devolver(
                    session, item=session.get(Estoque, mov.estoque_id), quantidade=mov.quantidade, unidade=mov.unidade,
                    data=agora.date(), fazenda_id=cron.fazenda_id,
                    observacao=f"Estorno da aplicação em {a.numero_matriz} — Sanidade (agendamento #{cron.id})",
                    usuario_id=_uid(user), origem_tipo="sanidade", origem_id=a.sanidade_id, produto=ap.produto,
                    lote_id=mov.lote_id,
                )
            san = session.get(Sanidade, a.sanidade_id)
            if san is not None:
                session.delete(san)
        linha = session.exec(
            select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
            .where(CronogramaSanitarioAnimal.numero_matriz == a.numero_matriz)
        ).first()
        if linha is not None:
            linha.status = "incluido"
            linha.data_aplicacao = None
            session.add(linha)
    for a in animais:
        if a.resultado != "nao_aplicado":
            continue
        linha = session.exec(
            select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
            .where(CronogramaSanitarioAnimal.numero_matriz == a.numero_matriz)
        ).first()
        if linha is None and calendario is not None:
            # voltou a lista de espera: traz de volta se ainda estiver la
            ativos = session.exec(
                select(CronogramaSanitarioAnimal, CronogramaSanitario)
                .join(CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAnimal.cronograma_id)
                .where(CronogramaSanitario.calendario_sanitario_id == calendario.id)
                .where(CronogramaSanitario.status == "aberto")
                .where(CronogramaSanitarioAnimal.numero_matriz == a.numero_matriz)
                .where(CronogramaSanitarioAnimal.status == "sugerido")
            ).first()
            if ativos is not None:
                linha = ativos[0]
                linha.cronograma_id = cron.id
        if linha is not None:
            linha.status = "incluido"
            linha.motivo = a.motivo_origem if a.origem == "fora_janela" else None
            linha.data_decisao = None
            session.add(linha)
    cron.status = "agendado"
    cron.concluido_em = None
    cron.atualizado_em = agora
    session.add(cron)


def _carregar(session: Session, aplicacao_id: int, fazenda_id: int | None) -> tuple[CronogramaSanitarioAplicacao, CronogramaSanitario]:
    ap = session.get(CronogramaSanitarioAplicacao, aplicacao_id)
    if ap is None or (fazenda_id is not None and ap.fazenda_id != fazenda_id):
        raise AplicacaoError("Aplicação não encontrada", 404)
    cron = session.get(CronogramaSanitario, ap.cronograma_id)
    if cron is None:
        raise AplicacaoError("Agendamento não encontrado", 404)
    return ap, cron


def desfazer(session: Session, aplicacao_id: int, *, user, fazenda_id: int | None, admin: bool) -> dict:
    """Desfazer: ate 10 s depois de aplicar, sem motivo, por quem aplicou (ou admin)."""
    ap, cron = _carregar(session, aplicacao_id, fazenda_id)
    if ap.estado != "aplicada":
        raise AplicacaoError("Esta aplicação já foi estornada")
    if not admin and _uid(user) != ap.registrado_por_usuario_id:
        raise AplicacaoError("Só quem aplicou (ou o administrador) pode desfazer", 403)
    agora = datetime.utcnow()
    from fazenda.rules import exame_preventivo
    exame_preventivo.validar_estorno(session, ap)
    if not pode_desfazer(ap, agora):
        raise AplicacaoError(
            f"Passaram mais de {DESFAZER_SEGUNDOS} segundos: agora só o administrador pode Estornar, informando o motivo", 409,
        )
    return _finalizar_estorno(session, ap, cron, user, agora, tipo="desfazer", motivo=None)


def estornar(session: Session, aplicacao_id: int, motivo: str | None, *, user, fazenda_id: int | None) -> dict:
    """Estornar (administrador, motivo obrigatorio): reverte estoque, Sanidade e
    o agendamento; a original fica preservada como "estornada"."""
    ap, cron = _carregar(session, aplicacao_id, fazenda_id)
    if not (motivo or "").strip():
        raise AplicacaoError("Informe o motivo do estorno")
    if ap.estado != "aplicada":
        raise AplicacaoError("Esta aplicação já foi estornada")
    from fazenda.rules import exame_preventivo
    exame_preventivo.validar_estorno(session, ap)
    return _finalizar_estorno(session, ap, cron, user, datetime.utcnow(), tipo="estorno", motivo=motivo.strip())


def _finalizar_estorno(session, ap, cron, user, agora, *, tipo: str, motivo: str | None) -> dict:
    try:
        _reverter(session, ap, cron, user, agora)
        ap.estado = "estornada"
        ap.tipo_estorno = tipo
        ap.motivo_estorno = motivo
        ap.estornado_por_usuario_id = _uid(user)
        ap.estornado_em = agora
        session.add(ap)
        registrar_log(
            session, cron, "Desfez" if tipo == "desfazer" else "Estornou", user=user, canal=ap.canal, motivo=motivo,
            aplicacao_id=ap.id, agora=agora,
            detalhe="Desfeito em até 10 s; a original ficou como Estornada" if tipo == "desfazer"
            else "A original ficou preservada como Estornada; estoque devolvido",
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(cron)
    session.refresh(ap)
    return {"aplicacao": serializar_aplicacao(session, ap), "agendamento": cron}


# ───────────────────────────── consultas (telas) ─────────────────────────────
def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _tipo_do_evento(evento: EventoSanitario | None) -> str:
    return (evento.categoria_preventiva if evento else None) or "vacina"


def _dose_texto(modo: dict) -> str:
    un = modo.get("unidade") or ""
    if modo["por_peso"]:
        return f"{modo['dose_ref']:g} {un} por {modo['kg_ref']:g} kg de peso vivo".strip()
    if modo.get("dose") is None:
        return "dose não cadastrada"
    return f"{modo['dose']:g} {un} por animal".strip()


def estado_visual(cron: CronogramaSanitario, hoje: date, adiado: bool = False) -> str:
    """em_montagem | atrasado | hoje | adiado (foi adiado e a nova data ainda vem) | agendado."""
    if cron.status == "em_montagem":
        return "em_montagem"
    if cron.data_evento < hoje:
        return "atrasado"
    if cron.data_evento == hoje:
        return "hoje"
    return "adiado" if adiado else "agendado"


_DATA_ANTES_RE = re.compile(r"de (\d{2})/(\d{2})/(\d{4}) para")


def _data_antes_do_adiamento(log: CronogramaSanitarioLog | None) -> str | None:
    """Data que valia antes do ultimo adiamento (gravada no detalhe do log)."""
    m = _DATA_ANTES_RE.search(log.detalhe or "") if log else None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _responsavel(session: Session, cron: CronogramaSanitario) -> dict:
    vet = session.get(Pessoa, cron.veterinario_pessoa_id) if cron.veterinario_pessoa_id else None
    if vet is not None:
        return {"pessoa_id": vet.id, "nome": vet.nome, "crmv": getattr(vet, "crmv", None), "modo": "veterinario"}
    return {"pessoa_id": None, "nome": "Equipe própria", "crmv": None, "modo": cron.modo_execucao or "propria"}


def _fase_exame_do_agendamento(session: Session, cron: CronogramaSanitario, cal, ev) -> dict:
    """`fase` (inoculacao | leitura | coleta) e `leitura_prevista_em` para exame; vazio para vacina/vermifugo."""
    from fazenda.rules import exame_preventivo
    if not exame_preventivo.eh_exame(ev):
        return {"fase": None, "leitura_prevista_em": None}
    _, _, tipo = exame_preventivo.contexto_do_evento(session, cal, ev)
    fase = exame_preventivo.fase_atual(session, cron, tipo)
    ino = exame_preventivo.inoculacao_ativa(session, cron.id) if fase == "leitura" else None
    return {"fase": fase, "leitura_prevista_em": _iso(ino.leitura_prevista_em) if ino else None,
            "leitura_limite_em": _iso(ino.leitura_limite_em) if ino else None}


def acompanhamento(session: Session, fazenda_id: int | None, hoje: date | None = None) -> dict:
    """Protocolos > Acompanhamento (preventivo): so o que ja esta agendado (ou
    em montagem) — a lista de espera nunca entra aqui."""
    hoje = hoje or date.today()
    query = select(CronogramaSanitario).where(CronogramaSanitario.status.in_(("agendado", "em_montagem")))
    if fazenda_id is not None:
        query = query.where(CronogramaSanitario.fazenda_id == fazenda_id)
    crons = session.exec(query.order_by(CronogramaSanitario.data_evento, CronogramaSanitario.hora)).all()
    calendarios = {c.id: c for c in session.exec(select(CalendarioSanitario)).all()}
    eventos = {e.id: e for e in session.exec(select(EventoSanitario)).all()}
    saida = []
    from fazenda.rules import financeiro_preventivo as fin
    vinculos_lote = fin.vinculos_por_cronogramas(session, [c.id for c in crons], fazenda_id)
    for cron in crons:
        cal = calendarios.get(cron.calendario_sanitario_id)
        ev = eventos.get(cal.evento_sanitario_id) if cal else None
        linhas = session.exec(
            select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
            .where(CronogramaSanitarioAnimal.status == "incluido")
        ).all()
        numeros = [l.numero_matriz for l in linhas]
        animais = {a.numero: a for a in session.exec(select(Animal).where(Animal.numero.in_(numeros))).all()
                   if fazenda_id is None or a.fazenda_id == fazenda_id} if numeros else {}
        lotes = sorted({animais[n].grupo_primario for n in numeros if n in animais and animais[n].grupo_primario})
        adiou = session.exec(
            select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == cron.id)
            .where(CronogramaSanitarioLog.acao == "Adiou").order_by(CronogramaSanitarioLog.id.desc())
        ).first()
        produto = (cal.produto if cal else None) or (ev.produto_padrao if ev else None)
        saida.append({
            "id": cron.id, "calendario_sanitario_id": cron.calendario_sanitario_id,
            "protocolo_nome": ev.nome if ev else "Protocolo", "tipo": _tipo_do_evento(ev), "produto": produto,
            "status": cron.status, "estado_visual": estado_visual(cron, hoje, adiado=adiou is not None),
            "data_evento": cron.data_evento.isoformat(), "hora": cron.hora, "data_original": _iso(cron.data_original),
            "data_antes_do_adiamento": _data_antes_do_adiamento(adiou),
            "motivo_adiamento": adiou.motivo if adiou else None, "observacao": cron.observacao,
            "responsavel": _responsavel(session, cron),
            "animais_total": len(linhas), "animais_fora_janela": sum(1 for l in linhas if l.origem == "fora_janela"),
            "lotes": lotes, "checklist": checklist_resumo(session, cron),
            "financeiro": fin.bloco_financeiro(vinculos_lote.get(cron.id, []), fin.necessidade(session, cron, fazenda_id, hoje)),
            "exige_veterinario": exige_veterinario(ev, produto),
            **_fase_exame_do_agendamento(session, cron, cal, ev),
        })
    agendados = [i for i in saida if i["status"] == "agendado"]
    return {
        "hoje": hoje.isoformat(), "agendamentos": saida,
        "totais": {
            "hoje": sum(1 for i in agendados if i["estado_visual"] == "hoje"),
            "atrasados": sum(1 for i in agendados if i["estado_visual"] == "atrasado"),
            "agendados": len(agendados),
        },
    }


def concluidos(
    session: Session, fazenda_id: int | None, *, calendario_id: int | None = None, de: date | None = None,
    ate: date | None = None, fora_janela: bool = False, q: str | None = None, incluir_cancelados: bool = True,
) -> dict:
    """Protocolos > Concluidos (preventivo): aplicacoes (inclusive estornadas, com
    selo) e agendamentos cancelados, do mais recente para o mais antigo."""
    # A inoculacao do exame e so a 1a etapa: o registro concluido e a leitura (ou a coleta).
    query = select(CronogramaSanitarioAplicacao).where(
        or_(CronogramaSanitarioAplicacao.fase.is_(None), CronogramaSanitarioAplicacao.fase != "inoculacao"))
    if fazenda_id is not None:
        query = query.where(CronogramaSanitarioAplicacao.fazenda_id == fazenda_id)
    if de is not None:
        query = query.where(CronogramaSanitarioAplicacao.data_aplicacao >= de)
    if ate is not None:
        query = query.where(CronogramaSanitarioAplicacao.data_aplicacao <= ate)
    aps = session.exec(query.order_by(CronogramaSanitarioAplicacao.data_aplicacao.desc(), CronogramaSanitarioAplicacao.id.desc())).all()
    calendarios = {c.id: c for c in session.exec(select(CalendarioSanitario)).all()}
    eventos = {e.id: e for e in session.exec(select(EventoSanitario)).all()}
    usuarios = _nomes_usuarios(session, {a.registrado_por_usuario_id for a in aps} | {a.estornado_por_usuario_id for a in aps})
    busca = _norm((q or "").strip())
    itens: list[dict] = []
    from fazenda.rules import exame_preventivo, financeiro_preventivo as fin
    vinculos_lote = fin.vinculos_por_cronogramas(session, list({a.cronograma_id for a in aps}), fazenda_id)
    for ap in aps:
        cron = session.get(CronogramaSanitario, ap.cronograma_id)
        if cron is None or (calendario_id is not None and cron.calendario_sanitario_id != calendario_id):
            continue
        cal = calendarios.get(cron.calendario_sanitario_id)
        ev = eventos.get(cal.evento_sanitario_id) if cal else None
        animais = _animais_da_aplicacao(session, ap.id)
        aplicados = [a for a in animais if a.resultado == "aplicado"]
        n_fora = sum(1 for a in aplicados if a.origem == "fora_janela")
        if fora_janela and not n_fora:
            continue
        if busca:
            alvo = _norm(" ".join([ev.nome if ev else "", ap.produto or "", ap.lote_texto or "", ap.aplicador_nome or ""]
                                  + [a.numero_matriz for a in animais]))
            if busca not in alvo:
                continue
        excecoes = _json_lista(ap.excecoes)
        agora = datetime.utcnow()
        itens.append({
            "id": ap.id, "cronograma_id": ap.cronograma_id, "calendario_sanitario_id": cron.calendario_sanitario_id,
            "protocolo_nome": ev.nome if ev else "Protocolo", "tipo": _tipo_do_evento(ev), "produto": ap.produto,
            "dose_total": ap.dose_total, "unidade": ap.unidade, "unidade_estoque": _unidade_do_estoque(session, ap),
            "estado": ap.estado, "data": ap.data_aplicacao.isoformat(), "hora": ap.hora,
            "animais_aplicados": len(aplicados), "animais_nao_aplicados": len(animais) - len(aplicados), "fora_janela": n_fora,
            "aplicador_nome": ap.aplicador_nome, "aplicador_crmv": ap.aplicador_crmv,
            "frasco": ap.lote_texto or ("sem baixa de estoque" if ap.estoque_desconsiderado else "—"),
            "validade": _iso(ap.validade), "estoque_desconsiderado": ap.estoque_desconsiderado,
            "carencia_leite_ate": _iso(ap.carencia_leite_ate), "carencia_carne_ate": _iso(ap.carencia_carne_ate),
            "carencia_texto": ap.carencia_texto, "custo": ap.custo, "retroativo": ap.retroativo, "canal": ap.canal,
            "financeiro": _financeiro_da_aplicacao(session, cron, ap, fazenda_id, vinculos_lote.get(cron.id, [])),
            "excecoes": excecoes, "com_excecao": bool(excecoes),
            "registrado_por": usuarios.get(ap.registrado_por_usuario_id), "registrado_em": ap.registrado_em.isoformat(),
            "motivo_estorno": ap.motivo_estorno, "tipo_estorno": ap.tipo_estorno,
            "estornado_por": usuarios.get(ap.estornado_por_usuario_id), "estornado_em": _iso(ap.estornado_em),
            "pode_desfazer": pode_desfazer(ap, agora),
            "desfazer_restante_s": max(0, DESFAZER_SEGUNDOS - int((agora - ap.registrado_em).total_seconds())) if pode_desfazer(ap, agora) else 0,
            "rotulo_estado": _rotulo_estado(ap, exame=ap.fase is not None),
            "exame": exame_preventivo.resumo_do_registro(session, ap, animais),
        })
    if incluir_cancelados and not fora_janela and not busca:
        qc = select(CronogramaSanitario).where(CronogramaSanitario.status == "cancelado")
        if fazenda_id is not None:
            qc = qc.where(CronogramaSanitario.fazenda_id == fazenda_id)
        if calendario_id is not None:
            qc = qc.where(CronogramaSanitario.calendario_sanitario_id == calendario_id)
        cancelados = session.exec(qc).all()
        vinculos_canc = fin.vinculos_por_cronogramas(session, [c.id for c in cancelados], fazenda_id)
        for cron in cancelados:
            dia = cron.atualizado_em.date()
            if (de and dia < de) or (ate and dia > ate):
                continue
            cal = calendarios.get(cron.calendario_sanitario_id)
            ev = eventos.get(cal.evento_sanitario_id) if cal else None
            n = len(session.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)).all())
            itens.append({
                "id": None, "cronograma_id": cron.id, "calendario_sanitario_id": cron.calendario_sanitario_id,
                "protocolo_nome": ev.nome if ev else "Protocolo", "tipo": _tipo_do_evento(ev), "produto": None,
                "estado": "cancelado", "data": dia.isoformat(), "hora": None, "animais_aplicados": 0,
                "animais_nao_aplicados": n, "fora_janela": 0, "aplicador_nome": None, "aplicador_crmv": None,
                "frasco": "—", "validade": None, "estoque_desconsiderado": False, "carencia_leite_ate": None,
                "carencia_carne_ate": None, "carencia_texto": None, "custo": None, "retroativo": False, "canal": None,
                "excecoes": [], "com_excecao": False, "registrado_por": None, "registrado_em": cron.atualizado_em.isoformat(),
                "financeiro": fin.bloco_financeiro(vinculos_canc.get(cron.id, [])),
                "rotulo_estado": "Cancelado", "exame": None,
                "motivo": cron.motivo_cancelamento, "motivo_estorno": None, "tipo_estorno": None, "estornado_por": None,
                "estornado_em": None, "pode_desfazer": False, "desfazer_restante_s": 0,
            })
    itens.sort(key=lambda i: (i["data"], i["registrado_em"]), reverse=True)
    return {
        "total": len(itens), "itens": itens,
        "resumo": {
            "aplicados": sum(1 for i in itens if i["estado"] == "aplicada"),
            "animais": sum(i["animais_aplicados"] for i in itens if i["estado"] == "aplicada"),
            "estornados": sum(1 for i in itens if i["estado"] == "estornada"),
        },
    }


def _nomes_usuarios(session: Session, ids: set) -> dict:
    from fazenda.rules.auditoria import mapa_usuarios
    return mapa_usuarios(session, {i for i in ids if i})


def detalhe_aplicacao(session: Session, aplicacao_id: int, fazenda_id: int | None) -> dict:
    ap, cron = _carregar(session, aplicacao_id, fazenda_id)
    cal = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    ev = session.get(EventoSanitario, cal.evento_sanitario_id) if cal else None
    usuarios = _nomes_usuarios(session, {ap.registrado_por_usuario_id, ap.estornado_por_usuario_id, ap.ciencia_usuario_id})
    nomes = {a.numero: a.nome for a in session.exec(select(Animal).where(
        Animal.numero.in_([x.numero_matriz for x in _animais_da_aplicacao(session, ap.id)]))).all()
        if fazenda_id is None or a.fazenda_id == fazenda_id}
    d = serializar_aplicacao(session, ap)
    for a in d["animais"]:
        a["nome"] = nomes.get(a["numero_matriz"])
    d.update(
        protocolo_nome=ev.nome if ev else "Protocolo", tipo=_tipo_do_evento(ev), registrado_por=usuarios.get(ap.registrado_por_usuario_id),
        estornado_por=usuarios.get(ap.estornado_por_usuario_id), ciencia_usuario=usuarios.get(ap.ciencia_usuario_id),
        log=[l for l in log_do_agendamento(session, cron.id) if l["aplicacao_id"] in (None, ap.id, ap.inoculacao_aplicacao_id)],
        checklist=checklist_resumo(session, cron), agendamento_status=cron.status,
        financeiro=_financeiro_da_aplicacao(session, cron, ap, fazenda_id),
    )
    from fazenda.rules import exame_preventivo
    d["exame"] = exame_preventivo.resumo_do_registro(session, ap, _animais_da_aplicacao(session, ap.id))
    ino = session.get(CronogramaSanitarioAplicacao, ap.inoculacao_aplicacao_id) if ap.inoculacao_aplicacao_id else None
    d["inoculacao"] = exame_preventivo._resumo_inoculacao(ino)
    return d


def contexto_aplicar(session: Session, cron: CronogramaSanitario, fazenda_id: int | None, hoje: date | None = None) -> dict:
    """Tudo o que a gaveta Aplicar precisa (a mesma em Protocolos e na Agenda)."""
    from fazenda.rules import exame_preventivo, financeiro_preventivo as fin
    hoje = hoje or date.today()
    cal = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    ev = session.get(EventoSanitario, cal.evento_sanitario_id) if cal else None
    produto = ((cal.produto if cal else None) or (ev.produto_padrao if ev else None) or "").strip() or None
    checklist = checklist_resumo(session, cron)
    ref = {}
    item_ck = next((i for i in checklist["itens"] if i["chave"] == "estoque"), None)
    if item_ck and item_ck["resposta"]:
        try:
            ref = json.loads(item_ck["resposta"])
        except ValueError:
            ref = {}
    estoque_pref = ref.get("estoque_id") if item_ck and item_ck["status"] == "cumprido" else None
    try:
        item, marca = _marca_e_item(session, produto, fazenda_id, estoque_pref)
    except AplicacaoError:
        item, marca = _marca_e_item(session, produto, fazenda_id, None)
    modo = _modo_dose(ev, marca)
    linhas = session.exec(
        select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
        .where(CronogramaSanitarioAnimal.status == "incluido")
    ).all()
    linhas = sorted(linhas, key=lambda l: (len(l.numero_matriz), l.numero_matriz))
    numeros = [l.numero_matriz for l in linhas]
    animais = {a.numero: a for a in session.exec(select(Animal).where(Animal.numero.in_(numeros))).all()
               if fazenda_id is None or a.fazenda_id == fazenda_id} if numeros else {}
    doses = calcular_doses(session, numeros, modo, fazenda_id, hoje)
    from fazenda.rules.cronograma_sanitario import _data_devida
    from fazenda.rules.ja_aplicado_preventivo import aplicacoes_no_ciclo
    ja_no_ciclo = aplicacoes_no_ciclo(session, cal, numeros, hoje=hoje, devida=_data_devida(cron), evento=ev) if cal else {}
    b19 = eh_b19(ev, produto)
    estoque = {"encontrado": item is not None, "estoque_id": item.id if item else None, "nome": item.nome if item else produto,
               "unidade": item.unidade if item else modo.get("unidade"), "saldo": item.quantidade if item else None, "lotes": []}
    if item is not None:
        for l in lotes_disponiveis(session, estoque_id=item.id):
            estoque["lotes"].append({
                "id": l.id, "numero_lote": l.numero_lote, "saldo": l.quantidade_restante, "validade": _iso(l.validade),
                "vencido": _vencido(l, hoje),
                "vence_em_dias": (l.validade - hoje).days if l.validade else None,
            })
        # mais antigo valido primeiro; o vencido nunca vem escolhido
        estoque["lote_sugerido_id"] = next((l["id"] for l in estoque["lotes"] if not l["vencido"]), None)
    ck_estoque = {"estado": "pendente"}
    if item_ck and item_ck["status"] == "cumprido":
        ck_estoque = {"estado": "vinculado", **ref}
    elif item_ck and item_ck["status"] == "pulado":
        ck_estoque = {"estado": "desconsiderado", "motivo": item_ck["observacao"], **ref}
    estoque["checklist"] = ck_estoque
    carencia = carencia_para_item(item, marca)
    unidade_estoque = item.unidade if item else None
    diverge = bool(item is not None and modo.get("unidade") and not unidades_iguais(modo["unidade"], item.unidade))
    aviso_unidade = (
        f'A dose do protocolo está em "{modo["unidade"]}" e o estoque de "{item.nome}" é controlado em "{item.unidade or "sem unidade"}". '
        "A unidade não é convertida sozinha: a baixa automática só acontece quando as duas são iguais; "
        "caso contrário o sistema avisa e o estoque precisa ser ajustado à mão."
    ) if diverge else None
    pessoas = [
        {"id": p.id, "nome": p.nome, "tipo": p.tipo, "crmv": getattr(p, "crmv", None), "veterinario": eh_veterinario(p)}
        for p in pessoas_da_fazenda(session, fazenda_id)
    ]
    vet_ck = next((i for i in checklist["itens"] if i["chave"] == "vet"), None)
    aplicador_sugerido = cron.veterinario_pessoa_id if (vet_ck is None or vet_ck["status"] == "cumprido") else None
    return {
        "cronograma_id": cron.id, "estado": cron.status, "protocolo_nome": ev.nome if ev else "Protocolo", "tipo": _tipo_do_evento(ev),
        "produto": produto, "via": ev.via_padrao if ev else None, "unidade": modo.get("unidade"),
        "por_peso": modo["por_peso"], "dose_ref": modo.get("dose_ref"), "kg_ref": modo.get("kg_ref"),
        "unidade_estoque": unidade_estoque, "unidade_diverge": diverge, "aviso_unidade": aviso_unidade,
        "dose_texto": _dose_texto(modo), "exige_veterinario": exige_veterinario(ev, produto),
        "data_evento": cron.data_evento.isoformat(), "hora": cron.hora, "responsavel": _responsavel(session, cron),
        "aplicador_sugerido_id": aplicador_sugerido,
        "animais": [
            {"numero_matriz": n, "nome": animais[n].nome if n in animais else None,
             "lote": animais[n].grupo_primario if n in animais else None,
             "origem": l.origem, "motivo": l.motivo if l.origem == "fora_janela" else None, **doses[n],
             "sem_peso": modo["por_peso"] and doses[n]["dose"] is None,
             "ja_aplicado": ({"data": ja_no_ciclo[n]["data"].isoformat(), "produto": ja_no_ciclo[n]["produto"],
                              "fonte": ja_no_ciclo[n]["fonte"], "dias": (hoje - ja_no_ciclo[n]["data"]).days}
                             if n in ja_no_ciclo else None),
             "restricao": restricao_b19(animais.get(n), hoje) if b19 else None}
            for l, n in zip(linhas, numeros)
        ],
        "n_ja_aplicados": len(ja_no_ciclo), "motivos_ja_aplicado": list(MOTIVOS_JA_APLICADO),
        "estoque": estoque, "pessoas": pessoas, "carencia": carencia, "checklist": checklist,
        "financeiro": fin.resumo(session, cron, fazenda_id, hoje),
        "log": log_do_agendamento(session, cron.id), "desfazer_segundos": DESFAZER_SEGUNDOS, "hoje": hoje.isoformat(),
        "exame": exame_preventivo.contexto(session, cron, cal, ev),
    }
