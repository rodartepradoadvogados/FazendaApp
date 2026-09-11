"""
Checklist da Ocorrência — Fase 1, passos 7-8 do redesenho do evento
sanitário (docs/redesenho-evento-sanitario.md, seções 3.2.2/3.4). Motor puro
de estado sobre `ChecklistItem`/`ChecklistTemplateItem`
(fazenda.models.sanidade) — quem decide QUANDO materializar/consultar é o
router (Fase 1, endpoint novo; Fase 2, telas do site).

Vocabulário: item nasce "pendente", vira "cumprido" ou "pulado" — nunca outro
valor, nunca volta a "pendente" sozinho (só reabrindo a Ocorrência inteira,
ver rules.cronograma_sanitario.reabrir). Comportamento especial por `chave`
(seção 3.4 do redesenho):
  - "estoque": aviso — nunca bloqueia, só é lido pela UI (não bloqueado aqui).
  - "vet": exige `resposta` em ("sim", "nao") para virar "cumprido"; "não"
    exige `observacao` (justificativa) — sempre cumprido, nunca pulado por
    responder (pular é recusar responder, outro caminho).
  - "horario": exige `resposta` (valor "HH:MM" não vazio) para confirmar.
  - "lotes": não tem valor próprio — "cumprido" é só "revisei a tela".
  - "financeiro"/"custom": sem exigência própria além do status.
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, or_, select

from fazenda.models import (
    CalendarioSanitarioChecklistItem, ChecklistItem, ChecklistTemplateItem, CronogramaSanitario, EventoSanitario,
)


class ChecklistError(Exception):
    """Erro de uso do checklist — o router converte em HTTP 400."""


# Tipo de template usado por cada categoria_preventiva — "tratamento"
# reaproveita o de "vacina" (mesmos campos/fluxo, seção 3.7.0 do redesenho).
def tipo_template_do_evento(evento: EventoSanitario) -> str:
    return "exame" if evento.categoria_preventiva == "exame" else "vacina"


class _ItemFonte:
    """Formato mínimo comum entre `ChecklistTemplateItem` e
    `CalendarioSanitarioChecklistItem` — o que `materializar_checklist`
    precisa de qualquer uma das duas fontes (template do tipo, ou
    customização da regra) para copiar dentro de uma Ocorrência nova."""

    __slots__ = ("chave", "nome", "ordem")

    def __init__(self, chave: str, nome: str, ordem: int) -> None:
        self.chave = chave
        self.nome = nome
        self.ordem = ordem


def template_do_tipo(session: Session, tipo: str, fazenda_id: int | None) -> list[_ItemFonte]:
    """Itens ativos do template padrão de um tipo (vacina/exame — seção 3.7.3
    do redesenho), globais (`fazenda_id` nulo) + os que esta fazenda
    personalizou, mesclados por `chave` (fazenda vence sobre o global,
    mesma regra de `fazenda.rules.parametros._linha`, aplicada item a item
    porque cada item tem sua própria "linha"). Usado tanto para materializar
    o checklist de uma Ocorrência nova (quando a regra não tem customização
    própria) quanto para semear o passo 4 do wizard de cadastro com o ponto
    de partida do tipo escolhido no passo 1."""
    query = (
        select(ChecklistTemplateItem)
        .where(ChecklistTemplateItem.tipo == tipo)
        .where(ChecklistTemplateItem.ativo == True)  # noqa: E712
        .where(or_(ChecklistTemplateItem.fazenda_id == fazenda_id, ChecklistTemplateItem.fazenda_id.is_(None)))
        .order_by(ChecklistTemplateItem.ordem)
    )
    template = session.exec(query).all()
    # Fazenda que personalizou o template (linha própria) não vê também a
    # global do mesmo nome/ordem duplicada — mesma regra de "quem
    # personalizou vence" de fazenda.rules.parametros._linha, aplicada item a
    # item (chave como identidade lógica do item, não nome — nome pode ter
    # sido editado).
    por_chave: dict[str, ChecklistTemplateItem] = {}
    for item in template:
        atual = por_chave.get(item.chave)
        if atual is None or (atual.fazenda_id is None and item.fazenda_id is not None):
            por_chave[item.chave] = item
    ordenados = sorted(por_chave.values(), key=lambda i: i.ordem)
    return [_ItemFonte(i.chave, i.nome, i.ordem) for i in ordenados]


def checklist_customizado_da_regra(session: Session, calendario_sanitario_id: int) -> list[_ItemFonte]:
    """Checklist que o passo 4 do wizard congelou para ESTA regra (seção
    3.7.0) — vazio quando a regra nunca passou pelo wizard novo (cadastrada
    antes dele, ou nunca editada por ele), caso em que `materializar_checklist`
    cai de volta no template do tipo, dinamicamente, como sempre fez."""
    itens = session.exec(
        select(CalendarioSanitarioChecklistItem)
        .where(CalendarioSanitarioChecklistItem.calendario_sanitario_id == calendario_sanitario_id)
        .order_by(CalendarioSanitarioChecklistItem.ordem)
    ).all()
    return [_ItemFonte(i.chave, i.nome, i.ordem) for i in itens]


def materializar_checklist(session: Session, cronograma: CronogramaSanitario, evento: EventoSanitario) -> list[ChecklistItem]:
    """Copia o checklist desta regra (customizado pelo wizard, seção 3.7.0) —
    ou, na ausência de customização, o template padrão do tipo do evento —
    para dentro desta Ocorrência. Idempotente: se a Ocorrência já tem itens
    (em qualquer status), devolve os existentes sem duplicar nem resetar o
    que já foi respondido."""
    existentes = session.exec(
        select(ChecklistItem).where(ChecklistItem.cronograma_id == cronograma.id).order_by(ChecklistItem.ordem)
    ).all()
    if existentes:
        return existentes

    fonte = checklist_customizado_da_regra(session, cronograma.calendario_sanitario_id)
    if not fonte:
        tipo = tipo_template_do_evento(evento)
        fonte = template_do_tipo(session, tipo, cronograma.fazenda_id)

    novos = [
        ChecklistItem(
            cronograma_id=cronograma.id, chave=item.chave, nome=item.nome, ordem=item.ordem,
            fazenda_id=cronograma.fazenda_id,
        )
        for item in fonte
    ]
    session.add_all(novos)
    session.commit()
    for item in novos:
        session.refresh(item)
    return novos


def _item_da_fazenda(session: Session, item_id: int, fazenda_id: int | None) -> ChecklistItem:
    item = session.get(ChecklistItem, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise ChecklistError("Item do checklist não encontrado")
    return item


def marcar_cumprido(
    session: Session, item_id: int, usuario_id: int | None, hoje: datetime, fazenda_id: int | None = None,
) -> ChecklistItem:
    """Uso genérico ("estoque", "financeiro", "custom") — itens com
    comportamento próprio (vet/horario/lotes) têm função dedicada abaixo, que
    também termina marcando "cumprido"."""
    item = _item_da_fazenda(session, item_id, fazenda_id)
    item.status = "cumprido"
    item.responsavel_usuario_id = usuario_id
    item.respondido_em = hoje
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def marcar_pulado(
    session: Session, item_id: int, motivo: str | None, usuario_id: int | None, hoje: datetime,
    fazenda_id: int | None = None,
) -> ChecklistItem:
    """Pular sempre disponível, em qualquer item, sem exceção — inclusive o
    financeiro (arquitetura travada, seção 1, ponto 6 do redesenho)."""
    item = _item_da_fazenda(session, item_id, fazenda_id)
    item.status = "pulado"
    item.observacao = motivo
    item.responsavel_usuario_id = usuario_id
    item.respondido_em = hoje
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def responder_veterinario(
    session: Session, item_id: int, resposta: str, justificativa: str | None, usuario_id: int | None, hoje: datetime,
    fazenda_id: int | None = None,
) -> ChecklistItem:
    """Item "vet" — Sim/Não sempre marca "cumprido" (responder É cumprir o
    item; "Não" é uma resposta válida, não uma recusa). "Não" exige
    justificativa — vira o alerta persistente "Veterinário não confirmou"
    (lido pela UI a partir de resposta=="nao", propagado até a resposta
    mudar ou o item ser reaberto)."""
    if resposta not in ("sim", "nao"):
        raise ChecklistError('Resposta inválida — use "sim" ou "nao"')
    if resposta == "nao" and not (justificativa or "").strip():
        raise ChecklistError("Justificativa obrigatória quando o veterinário não confirma")
    item = _item_da_fazenda(session, item_id, fazenda_id)
    if item.chave != "vet":
        raise ChecklistError('Este item não é do tipo "vet"')
    item.status = "cumprido"
    item.resposta = resposta
    item.observacao = justificativa if resposta == "nao" else None
    item.responsavel_usuario_id = usuario_id
    item.respondido_em = hoje
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def confirmar_horario(
    session: Session, item_id: int, valor: str, usuario_id: int | None, hoje: datetime, fazenda_id: int | None = None,
) -> ChecklistItem:
    """Item "horario" — exige preencher a hora antes de confirmar (não é um
    toggle de "cumprido"). `valor` livre (ex.: "09:30") — validação de
    formato fica na UI, aqui só exige não-vazio."""
    if not (valor or "").strip():
        raise ChecklistError("Informe o horário antes de confirmar")
    item = _item_da_fazenda(session, item_id, fazenda_id)
    if item.chave != "horario":
        raise ChecklistError('Este item não é do tipo "horario"')
    item.status = "cumprido"
    item.resposta = valor.strip()
    item.responsavel_usuario_id = usuario_id
    item.respondido_em = hoje
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def marcar_lotes_revisado(
    session: Session, item_id: int, usuario_id: int | None, hoje: datetime, fazenda_id: int | None = None,
) -> ChecklistItem:
    """Item "lotes" — "Marcar como revisado", não "cumprido" genérico (não
    há nada a cumprir, é uma conferência da distribuição por lote de
    manejo, que a UI já mostrou antes de habilitar este botão)."""
    item = _item_da_fazenda(session, item_id, fazenda_id)
    if item.chave != "lotes":
        raise ChecklistError('Este item não é do tipo "lotes"')
    item.status = "cumprido"
    item.responsavel_usuario_id = usuario_id
    item.respondido_em = hoje
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def checklist_completo(session: Session, cronograma_id: int) -> bool:
    """100% Cumprido/Pulado — habilita "Confirmar ocorrência" (seção 3.2.2).
    Checklist vazio (Ocorrência ainda não materializada) NUNCA conta como
    completo — evita "Confirmar" antes mesmo de abrir a aba Checklist."""
    itens = session.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == cronograma_id)).all()
    if not itens:
        return False
    return all(item.status != "pendente" for item in itens)


def alerta_clinico_ativo(session: Session, cronograma_id: int) -> bool:
    """True quando o item "vet" foi respondido "Não" e continua assim — o
    selo vermelho persistente "Veterinário não confirmou" (seção 3.2.2)."""
    item_vet = session.exec(
        select(ChecklistItem).where(ChecklistItem.cronograma_id == cronograma_id).where(ChecklistItem.chave == "vet")
    ).first()
    return bool(item_vet and item_vet.resposta == "nao")


def desconsiderar_cronograma(
    session: Session, cronograma: CronogramaSanitario, motivo: str | None, hoje: datetime,
) -> CronogramaSanitario:
    """"Desconsiderar cronograma" (seção 3.2.5) — confirma a Ocorrência sem
    passar pelo checklist. Decisão por Ocorrência, nunca muda a Regra
    (CalendarioSanitario intocado). Bloqueado só quando já Realizado
    (`status == "concluido"`) — arquitetura travada, seção 1, ponto 2."""
    if cronograma.status == "concluido":
        raise ChecklistError("Esta ocorrência já foi realizada — não é possível desconsiderar o cronograma agora")
    cronograma.checklist_desconsiderado = True
    cronograma.checklist_desconsiderado_motivo = motivo
    cronograma.checklist_desconsiderado_em = hoje
    cronograma.atualizado_em = hoje
    session.add(cronograma)
    session.commit()
    session.refresh(cronograma)
    return cronograma


def confirmado(session: Session, cronograma: CronogramaSanitario) -> bool:
    """"Confirmado" do modelo novo (seção 3.3): checklist 100%
    Cumprido/Pulado OU desconsiderado — independe de `modo_execucao`/
    `status` (a decisão veterinário-vs-própria, seção R2.3, deixou de ser
    pré-requisito)."""
    if cronograma.checklist_desconsiderado:
        return True
    return checklist_completo(session, cronograma.id)


def estado_ocorrencia(session: Session, cronograma: CronogramaSanitario) -> str:
    """Estado da Ocorrência no vocabulário do redesenho (seção 3.3):
    "provavel" | "em_edicao" | "confirmado" | "realizado" — computado por
    leitura a cada chamada, sem mudar o `status` (aberto/agendado/concluido/
    cancelado) que o motor antigo (rules.cronograma_sanitario, ainda em uso
    pela trilha veterinário-vs-própria) continua gravando.

    Decisão de leitura registrada em docs/redesenho-evento-sanitario.md
    (gap apontado na seção 2/5): como o cronograma hoje já nasce
    materializado assim que a Agenda roda (não existe pré-materialização),
    "provavel" é lido, não um estado próprio gravado — vale enquanto NADA do
    checklist foi tocado ainda, mesmo já existindo a linha."""
    if cronograma.status == "concluido":
        return "realizado"
    if confirmado(session, cronograma):
        return "confirmado"
    itens = session.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == cronograma.id)).all()
    algum_respondido = any(item.status != "pendente" for item in itens)
    return "em_edicao" if algum_respondido else "provavel"


def salvar_checklist_da_regra(
    session: Session, calendario_sanitario_id: int, itens: list[tuple[str, str, int]] | None, fazenda_id: int | None,
) -> None:
    """Passo 4 do wizard de cadastro (seção 3.7.0) — grava o checklist
    congelado desta regra, substituindo por completo qualquer customização
    anterior. `itens is None` significa "o wizard não passou pelo passo de
    checklist" (chamada antiga, fora do wizard novo) — não toca em nada,
    preservando uma customização já existente. Lista vazia (`[]`) É uma
    escolha válida do usuário (removeu todos os itens no passo 4) e some com
    a customização anterior, se houver — a partir daí `materializar_checklist`
    cai de volta no template do tipo dinamicamente para esta regra, igual a
    uma regra que nunca passou pelo wizard novo."""
    if itens is None:
        return
    existentes = session.exec(
        select(CalendarioSanitarioChecklistItem)
        .where(CalendarioSanitarioChecklistItem.calendario_sanitario_id == calendario_sanitario_id)
    ).all()
    for item in existentes:
        session.delete(item)
    novos = [
        CalendarioSanitarioChecklistItem(
            calendario_sanitario_id=calendario_sanitario_id, chave=chave, nome=nome, ordem=ordem,
            fazenda_id=fazenda_id,
        )
        for chave, nome, ordem in itens
    ]
    session.add_all(novos)
    session.commit()
