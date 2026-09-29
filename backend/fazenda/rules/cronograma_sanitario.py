"""
Cronograma sanitário — motor de estado do workflow dinâmico de acompanhamento
de uma regra do calendário sanitário (CalendarioSanitario). É a "Ocorrência"
do redesenho do evento sanitário (docs/redesenho-evento-sanitario.md, seção
1) — entidade generalizada, não uma tabela nova.

Hoje só roda para regra marcada `usa_cronograma=True`. Atrás da feature flag
por fazenda `usar_ocorrencia_universal` (R-1 do redesenho, Fase 1), passa a
rodar para TODA regra ativa — comportamento inalterado (False) até a fazenda
ligar explicitamente.

Duas trilhas independentes, que se encontram na aplicação:
  (1) trilha do animal — CronogramaSanitarioAnimal: todo dia, animais que
      batem o critério do EventoSanitario entram "sugeridos" no cronograma
      ABERTO da regra; o funcionário aprova ("incluido") ou recusa
      ("excluido") pela Agenda. Regra por EVENTO DE VIDA é alimentada por
      `fazenda.rules.eventos_sanitarios` (gatilho por animal, já existia).
      Regra por ÉPOCA (`EventoSanitario.tipo_agendamento != "evento"`) é
      alimentada aqui mesmo, via `fazenda.rules.projecao_categoria` (R-2) —
      projeta quem vai estar na categoria-alvo na data prevista da
      Ocorrência, não em quem está na categoria HOJE.
  (2) trilha do agendamento — os campos do próprio CronogramaSanitario:
      decide COM QUEM (veterinário cadastrado como Pessoa, ou equipe
      própria) e QUANDO a aplicação acontece. Sem decisão, a Agenda cobra
      confirmação obrigatória `cronograma_sanitario_dias_aviso` dias antes
      da data prevista (ver fazenda.rules.parametros).

Existe no máximo 1 cronograma "em aberto" (status aberto/agendado) por regra
a qualquer momento — ver `cronograma_aberto()`.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from fazenda.models import (
    Animal, CalendarioSanitario, CronogramaSanitario, CronogramaSanitarioAnimal, EventoSanitario, Pessoa, Sanidade,
)
from fazenda.rules.calendario_sanitario import _somar_meses, proxima_ocorrencia
from fazenda.rules.checklist_sanitario import materializar_checklist
from fazenda.rules.parametros import cronograma_sanitario_dias_aviso, usar_ocorrencia_universal
from fazenda.rules.projecao_categoria import animais_projetados_na_categoria

PREFIXO_CRONOGRAMA = "cronograma_sanitario_"

# "aberto" = lista de espera (R1) | "agendado" = agendamento (R2, único que vira
# tarefa da Agenda) | "em_montagem" = rascunho do assistente "Criar agendamento".
_ABERTOS = ("aberto", "agendado", "em_montagem")
_HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class CronogramaError(Exception):
    """Erro de uso do workflow — o router converte em HTTP 400."""


def cronograma_aberto(session: Session, calendario: CalendarioSanitario) -> CronogramaSanitario:
    """Devolve o cronograma "aberto" da regra — a LISTA DE ESPERA (R1) — criando
    um novo (com a próxima data projetada) se não houver nenhum. Agendamentos
    (status "agendado"/"em_montagem") convivem com ele: montar um agendamento
    parcial deixa o resto da lista de espera no cronograma aberto."""
    existente = session.exec(
        select(CronogramaSanitario)
        .where(CronogramaSanitario.calendario_sanitario_id == calendario.id)
        .where(CronogramaSanitario.status == "aberto")
        .order_by(CronogramaSanitario.data_evento)
    ).first()
    if existente:
        return existente

    # Ainda há agendamento em curso (mesmo ciclo): quem chega agora espera na
    # mesma data devida, não na próxima ocorrência.
    em_curso = session.exec(
        select(CronogramaSanitario)
        .where(CronogramaSanitario.calendario_sanitario_id == calendario.id)
        .where(CronogramaSanitario.status.in_(_ABERTOS))
        .order_by(CronogramaSanitario.data_evento)
    ).first()
    ultimo = session.exec(
        select(CronogramaSanitario)
        .where(CronogramaSanitario.calendario_sanitario_id == calendario.id)
        .order_by(CronogramaSanitario.criado_em.desc())
    ).first()
    # Sem cronograma anterior: a 1ª ocorrência é a própria data_evento da
    # regra (mesma referência usada por _ocorrencias_recorrentes). Com um
    # anterior (concluído/cancelado), projeta a próxima a partir dele.
    if em_curso:
        proxima = em_curso.data_original or em_curso.data_evento
    elif ultimo:
        proxima = proxima_ocorrencia(ultimo.data_evento, calendario.frequencia_valor, calendario.frequencia_unidade)
    else:
        proxima = calendario.data_evento
    novo = CronogramaSanitario(
        calendario_sanitario_id=calendario.id, data_evento=proxima, fazenda_id=calendario.fazenda_id,
    )
    session.add(novo)
    session.commit()
    session.refresh(novo)
    return novo


def _linhas_da_regra(
    session: Session, calendario_id: int, numeros: list[str] | None = None,
) -> list[tuple[CronogramaSanitarioAnimal, CronogramaSanitario]]:
    """Linhas de animal (qualquer status) dos cronogramas ATIVOS da regra —
    base do R8 (um animal em uma lista/agendamento ativo por protocolo) e da
    dedupe da lista de espera."""
    query = (
        select(CronogramaSanitarioAnimal, CronogramaSanitario)
        .join(CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAnimal.cronograma_id)
        .where(CronogramaSanitario.calendario_sanitario_id == calendario_id)
        .where(CronogramaSanitario.status.in_(_ABERTOS))
    )
    if numeros is not None:
        query = query.where(CronogramaSanitarioAnimal.numero_matriz.in_(numeros))
    return list(session.exec(query).all())


def _reagentes(session: Session, calendario: CalendarioSanitario, numeros: list[str]) -> dict:
    from fazenda.rules.exame_preventivo import animais_reagentes
    return animais_reagentes(session, calendario.fazenda_id, numeros)


def sugerir_animal(session: Session, calendario: CalendarioSanitario, numero_matriz: str, hoje: date) -> CronogramaSanitarioAnimal | None:
    """Garante uma linha "sugerido" para o animal no cronograma aberto da
    regra. Idempotente: devolve None (não gera pendência de novo) se o
    animal já tem linha nesse cronograma, em qualquer status."""
    if _linhas_da_regra(session, calendario.id, [numero_matriz]):
        return None  # R8: já está em alguma lista/agendamento ativo desta regra
    if _reagentes(session, calendario, [numero_matriz]):
        return None  # reagente em exame: sai de todo agendamento e nunca volta a ser sugerido
    cron = cronograma_aberto(session, calendario)
    linha = CronogramaSanitarioAnimal(
        cronograma_id=cron.id, numero_matriz=numero_matriz, data_sugestao=hoje, fazenda_id=calendario.fazenda_id,
    )
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha


def sugerir_animais_em_lote(session: Session, calendario: CalendarioSanitario, numeros_matriz: list[str], hoje: date) -> None:
    """Versão em lote de `sugerir_animal` — evita 1 SELECT (+ eventual
    INSERT/COMMIT) por animal a cada carregamento da Agenda (relatado: até
    centenas de idas ao banco num rebanho grande, toda vez que a tela abre).
    Mesmo resultado final: garante 1 linha "sugerido" por animal no
    cronograma aberto da regra, idempotente por (cronograma_id, numero_matriz)
    — só que checando os já-existentes de uma vez e inserindo o resto junto."""
    if not numeros_matriz:
        return
    # R8: quem já tem linha em QUALQUER cronograma ativo da regra (lista de
    # espera, agendamento, rascunho) não entra de novo.
    existentes = {l.numero_matriz for l, _ in _linhas_da_regra(session, calendario.id, list(numeros_matriz))}
    pendentes = [n for n in dict.fromkeys(numeros_matriz) if n not in existentes]  # preserva ordem, sem duplicata
    if pendentes:
        reagentes = _reagentes(session, calendario, pendentes)   # reagente em exame nunca volta a ser sugerido
        pendentes = [n for n in pendentes if n not in reagentes]
    if not pendentes:
        return
    cron = cronograma_aberto(session, calendario)
    novos = [
        CronogramaSanitarioAnimal(cronograma_id=cron.id, numero_matriz=n, data_sugestao=hoje, fazenda_id=calendario.fazenda_id)
        for n in pendentes
    ]
    session.add_all(novos)
    session.commit()


def incluir_animal_manual(
    session: Session, cronograma: CronogramaSanitario, numero_matriz: str, hoje: date, motivo: str | None = None,
) -> CronogramaSanitarioAnimal:
    """Inclusão manual, fora da janela de aplicação — bug relatado pelo
    usuário em 12/09/2026 ("não tem como colocar animal fora da janela"): a
    trilha do animal (sugerir_animal/sugerir_animais_em_lote) só cria linha
    para quem bate o critério automático (idade/gatilho/categoria projetada).
    Um animal fora desse critério nunca ganhava linha nenhuma, então nunca
    aparecia pra decidir. Aqui a linha nasce direto "incluido" (pula
    "sugerido" — não houve sugestão automática nenhuma para aceitar/recusar),
    igual ao efeito final de `decidir_animal(incluir=True)`."""
    if cronograma.status in ("concluido", "cancelado"):
        raise CronogramaError("Este cronograma já foi encerrado — não é possível incluir animal")
    existente = session.exec(
        select(CronogramaSanitarioAnimal)
        .where(CronogramaSanitarioAnimal.cronograma_id == cronograma.id)
        .where(CronogramaSanitarioAnimal.numero_matriz == numero_matriz)
    ).first()
    if existente:
        raise CronogramaError(f"Matriz {numero_matriz} já está neste cronograma ({existente.status})")
    linha = CronogramaSanitarioAnimal(
        cronograma_id=cronograma.id, numero_matriz=numero_matriz, status="incluido",
        data_sugestao=hoje, data_decisao=hoje, fazenda_id=cronograma.fazenda_id,
        origem="fora_janela", motivo=(motivo or "").strip() or None,
    )
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha


def decidir_animal(session: Session, cronograma_animal_id: int, incluir: bool, hoje: date) -> CronogramaSanitarioAnimal:
    linha = session.get(CronogramaSanitarioAnimal, cronograma_animal_id)
    if not linha:
        raise CronogramaError("Animal não encontrado no cronograma")
    if linha.status != "sugerido":
        raise CronogramaError("Este animal já foi decidido")
    linha.status = "incluido" if incluir else "excluido"
    linha.data_decisao = hoje
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha


def remover_animal(session: Session, cronograma_animal_id: int, hoje: date) -> CronogramaSanitarioAnimal:
    """Remove um animal já incluído (ou ainda sugerido) do cronograma — pedido
    do usuário em 13/09/2026 ("adicionar OU remover animais manualmente"):
    `decidir_animal` só decide uma linha "sugerido" pela primeira vez (nunca
    desfaz), e a inclusão manual (`incluir_animal_manual`) não tinha
    contrapartida nenhuma para tirar o animal de volta. Vira "excluido",
    igual ao efeito de recusar uma sugestão — nunca em animal já aplicado
    (isso já virou aplicação de verdade, com baixa de estoque)."""
    linha = session.get(CronogramaSanitarioAnimal, cronograma_animal_id)
    if not linha:
        raise CronogramaError("Animal não encontrado no cronograma")
    if linha.status == "aplicado":
        raise CronogramaError("Este animal já foi aplicado — não é possível remover")
    if linha.status == "excluido":
        raise CronogramaError("Este animal já está excluído")
    linha.status = "excluido"
    linha.data_decisao = hoje
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha


def decidir_modo(
    session: Session, cronograma: CronogramaSanitario, modo: str | None, veterinario_pessoa_id: int | None,
) -> CronogramaSanitario:
    """Veterinário agendado / aplicação própria / de volta para "em branco"
    (modo=None) — chamado tanto na criação do cronograma quanto na
    confirmação pedida pelo aviso obrigatório de N dias antes."""
    if modo not in (None, "veterinario", "propria"):
        raise CronogramaError("Modo inválido — use veterinario, propria ou deixe em branco")
    if modo == "veterinario":
        if not veterinario_pessoa_id:
            raise CronogramaError("Selecione o veterinário")
        pessoa = session.get(Pessoa, veterinario_pessoa_id)
        if not pessoa or not pessoa.ativo:
            raise CronogramaError("Veterinário não encontrado")
    cronograma.modo_execucao = modo
    cronograma.veterinario_pessoa_id = veterinario_pessoa_id if modo == "veterinario" else None
    cronograma.status = "agendado" if modo else "aberto"
    cronograma.atualizado_em = datetime.utcnow()
    session.add(cronograma)
    session.commit()
    session.refresh(cronograma)
    return cronograma


def adiar(
    session: Session, cronograma: CronogramaSanitario, nova_data: date, motivo: str | None,
    manter_agendamento: bool = False, hora: str | None = None,
) -> CronogramaSanitario:
    """Reabre o ciclo de decisão com uma nova data — usado tanto a partir do
    aviso obrigatório de N dias antes quanto, por conveniência, a qualquer
    momento em que o cronograma ainda não tenha sido aplicado."""
    if cronograma.status == "concluido":
        raise CronogramaError("Este cronograma já foi aplicado — não é possível adiar")
    if manter_agendamento:
        # R9: adiar um AGENDAMENTO só muda quando; os animais, o responsável e o
        # estado (agendado/em montagem) ficam como estão.
        if cronograma.status not in ("agendado", "em_montagem", "aguardando_confirmacao"):
            raise CronogramaError("Só um agendamento pode ser adiado (a lista de espera não tem data)")
        if hora is not None and hora != "" and not _HORA_RE.match(hora):
            raise CronogramaError("Hora inválida — use HH:MM")
    if cronograma.data_original is None:
        cronograma.data_original = cronograma.data_evento
    cronograma.data_evento = nova_data
    if manter_agendamento:
        if hora:
            cronograma.hora = hora
    else:
        cronograma.modo_execucao = None
        cronograma.veterinario_pessoa_id = None
        cronograma.status = "aberto"
    if motivo:
        cronograma.observacao = (f"{cronograma.observacao} | " if cronograma.observacao else "") + f"Adiado: {motivo}"
    cronograma.atualizado_em = datetime.utcnow()
    session.add(cronograma)
    session.commit()
    session.refresh(cronograma)
    return cronograma


def reabrir(session: Session, cronograma: CronogramaSanitario, motivo: str | None = None) -> CronogramaSanitario:
    """"Reabrir" de verdade — Fase 0, passo 4 do redesenho do evento
    sanitário (docs/redesenho-evento-sanitario.md, seção 3.3: "Confirmado →
    Em edição", a qualquer momento, sem limite, até Realizado). Igual a
    `adiar()` na devolução ao estado editável (modo/veterinário zerados,
    status "aberto"), mas SEM mudar `data_evento` nem gravar `data_original`
    — `adiar` sempre muda a data; `reabrir` nunca muda.

    Só permitido a partir de "agendado" (o único estado hoje que corresponde
    ao "Confirmado" do redesenho — decisão de modo já tomada, aguardando a
    data). Nunca a partir de "concluido": esse é o "Realizado" do redesenho,
    terminal quanto ao registro em Sanidade — reabrir de lá quebraria a
    arquitetura travada com o usuário (seção 1, ponto 2 do documento).
    Reabrir um cronograma já "aberto" é idempotente (no-op, exceto o
    motivo)."""
    if cronograma.status == "concluido":
        raise CronogramaError("Este cronograma já foi aplicado — não é possível reabrir (só \"Adicionar observação\")")
    if cronograma.status == "cancelado":
        raise CronogramaError("Este cronograma foi cancelado — não é possível reabrir")
    if cronograma.status == "aberto":
        return cronograma
    cronograma.modo_execucao = None
    cronograma.veterinario_pessoa_id = None
    cronograma.status = "aberto"
    if motivo:
        cronograma.observacao = (f"{cronograma.observacao} | " if cronograma.observacao else "") + f"Reaberto: {motivo}"
    cronograma.atualizado_em = datetime.utcnow()
    session.add(cronograma)
    session.commit()
    session.refresh(cronograma)
    return cronograma


def animais_por_status(session: Session, cronograma_id: int, status: str) -> list[CronogramaSanitarioAnimal]:
    return session.exec(
        select(CronogramaSanitarioAnimal)
        .where(CronogramaSanitarioAnimal.cronograma_id == cronograma_id)
        .where(CronogramaSanitarioAnimal.status == status)
    ).all()


def concluir(session: Session, cronograma: CronogramaSanitario, animais_aplicados: list[str], hoje: date) -> None:
    """Marca o cronograma como concluído e os animais aplicados de fato —
    chamado pelo router depois de registrar a aplicação real (ver
    /sanidade/cronograma/{id}/aplicar)."""
    incluidos = animais_por_status(session, cronograma.id, "incluido")
    aplicados = {n for n in animais_aplicados}
    restantes = False
    for linha in incluidos:
        if linha.numero_matriz in aplicados:
            linha.status = "aplicado"
            linha.data_aplicacao = hoje
            session.add(linha)
        else:
            restantes = True
    # Só fecha o cronograma quando TODOS os incluídos foram aplicados —
    # aplicação individualizada, feita aos poucos, mantém o cronograma aberto
    # até o último animal ser confirmado.
    if not restantes:
        cronograma.status = "concluido"
        cronograma.concluido_em = datetime.utcnow()
    cronograma.atualizado_em = datetime.utcnow()
    session.add(cronograma)
    session.commit()


def _regra_e_por_epoca(calendario: CalendarioSanitario, eventos_por_id: dict) -> bool:
    """True quando a regra é do tipo "época" (frequência/categoria, sem
    gatilho por animal) — o único caso que precisa do motor de projeção
    (R-2). Regra por evento de vida (`EventoSanitario.tipo_agendamento ==
    "evento"`) já tem sugestão própria, alimentada por
    fazenda.rules.eventos_sanitarios; nunca passa por aqui, mesmo com a flag
    `usar_ocorrencia_universal` ligada."""
    evento = eventos_por_id.get(calendario.evento_sanitario_id)
    return evento is None or evento.tipo_agendamento != "evento"


# ---------------------------------------------------------------------------
# Eventos da Agenda — as 4 pendências do desenho (ver docs/plano no chat):
# animal sugerido (incluir/excluir), decisão de modo (recém-criado),
# confirmar-ou-adiar (obrigatório, N dias antes, ainda em branco) e aplicar
# (dia do evento, modo já definido).
# ---------------------------------------------------------------------------
def _data_devida(cron: CronogramaSanitario) -> date:
    """Data devida do ciclo do cronograma: para um agendamento remarcado/criado
    com data diferente, é a data original (a do agendamento não desloca o ciclo)."""
    return cron.data_original or cron.data_evento


def _inicio_do_ciclo(cron: CronogramaSanitario, calendario: CalendarioSanitario) -> date:
    """Começo do ciclo que termina na data prevista da Ocorrência (data prevista
    menos UMA frequência da regra). Aplicação do produto da regra a partir daqui
    já cobre a época — o animal não volta para a lista de espera."""
    n, un = calendario.frequencia_valor, calendario.frequencia_unidade
    devida = _data_devida(cron)
    if un == "dias":
        return devida - timedelta(days=n)
    return _somar_meses(devida, -(n * 12 if un == "anos" else n))


def _ja_vacinados_no_ciclo(
    session: Session, cron: CronogramaSanitario, calendario: CalendarioSanitario, produto: str | None, numeros: list[str],
) -> set[str]:
    """Animais (entre `numeros`) com aplicação do produto da regra dentro do
    ciclo da Ocorrência — não viram "sugerido" (dedupe da época)."""
    if not numeros:
        return set()
    desde = _inicio_do_ciclo(cron, calendario)
    ev = session.get(EventoSanitario, calendario.evento_sanitario_id)
    if ev is not None and ev.categoria_preventiva == "exame":
        # Exame: quem ja fez o exame deste protocolo no ciclo (leitura/coleta nao estornada) nao volta para a lista de espera.
        from fazenda.models import CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacaoAnimal
        feitos = session.exec(
            select(CronogramaSanitarioAplicacaoAnimal.numero_matriz)
            .join(CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacao.id == CronogramaSanitarioAplicacaoAnimal.aplicacao_id)
            .join(CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAplicacao.cronograma_id)
            .where(CronogramaSanitario.calendario_sanitario_id == calendario.id)
            .where(CronogramaSanitarioAplicacao.estado == "aplicada")
            .where(CronogramaSanitarioAplicacao.fase.in_(("leitura", "coleta")))
            .where(CronogramaSanitarioAplicacao.data_aplicacao >= desde)
            .where(CronogramaSanitarioAplicacaoAnimal.exame_resultado.is_not(None))
            .where(CronogramaSanitarioAplicacaoAnimal.numero_matriz.in_(numeros))
        ).all()
        return set(feitos)
    if not produto:
        return set()
    alvo = produto.strip().lower()
    query = (
        select(Sanidade.numero_matriz, Sanidade.produto)
        .where(Sanidade.numero_matriz.in_(numeros))
        .where(Sanidade.data_aplicacao >= desde)
    )
    if calendario.fazenda_id is not None:
        query = query.where(Sanidade.fazenda_id == calendario.fazenda_id)
    linhas = session.exec(query).all()
    return {n for n, prod in linhas if (prod or "").strip().lower() == alvo}


def resumo_lista_espera(session: Session, fazenda_id: int | None = None) -> list[dict]:
    """Atalho da Agenda para Protocolos (R1): quantos animais estão na lista de
    espera ("sugerido") de cada cronograma em aberto. NÃO é tarefa — a Agenda
    só mostra o número e leva para Protocolos, onde se decide/agenda."""
    query = (
        select(CronogramaSanitario, CalendarioSanitario)
        .join(CalendarioSanitario, CalendarioSanitario.id == CronogramaSanitario.calendario_sanitario_id)
        .where(CronogramaSanitario.status.in_(_ABERTOS))
        .where(CalendarioSanitario.ativo == True)  # noqa: E712
    )
    if fazenda_id is not None:
        query = query.where(CalendarioSanitario.fazenda_id == fazenda_id)
    pares = session.exec(query).all()
    if not pares:
        return []
    contagem: dict[int, int] = {}
    hoje = date.today()
    for linha in session.exec(
        select(CronogramaSanitarioAnimal)
        .where(CronogramaSanitarioAnimal.cronograma_id.in_([c.id for c, _ in pares]))
        .where(CronogramaSanitarioAnimal.status == "sugerido")
    ).all():
        if linha.reteste and linha.data_devida and linha.data_devida > hoje:
            continue   # reteste de exame: so entra na lista de espera na data devida
        contagem[linha.cronograma_id] = contagem.get(linha.cronograma_id, 0) + 1
    from fazenda.models import EventoSanitario
    nomes = {e.id: e.nome for e in session.exec(select(EventoSanitario)).all()}
    return [
        {
            "cronograma_id": c.id, "evento_sanitario_id": cal.evento_sanitario_id,
            "evento_nome": nomes.get(cal.evento_sanitario_id, "Evento sanitário"),
            "categoria_alvo": cal.categoria_alvo, "data_evento": c.data_evento.isoformat(),
            "quantidade": contagem[c.id],
        }
        for c, cal in pares if contagem.get(c.id)
    ]


def eventos_agenda(
    session: Session, hoje: date, realizados: set[str], fazenda_id: int | None = None, escrever: bool = False,
) -> list[dict]:
    """Tarefas da Agenda vindas do cronograma sanitário: SÓ o agendamento
    (status "agendado", modo/data definidos) no dia da aplicação (R2). Animal na
    janela/lista de espera e cronograma "aberto" (sem decisão) NUNCA são
    tarefa (R1) — ver `resumo_lista_espera`.

    `escrever=False` (padrão, usado por GET /agenda) só lê. Criar cronograma,
    materializar checklist e sugerir animais (`escrever=True`) é papel de
    `materializar` (POST /agenda/materializar)."""
    query = select(CalendarioSanitario).where(CalendarioSanitario.ativo == True)  # noqa: E712
    # `usa_cronograma` continua filtrando por padrão (comportamento de
    # sempre); com a flag ligada para a fazenda (R-1), toda regra ativa passa
    # a ter Ocorrência — o campo deixa de ser opt-in.
    if not usar_ocorrencia_universal():
        query = query.where(CalendarioSanitario.usa_cronograma == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(CalendarioSanitario.fazenda_id == fazenda_id)
    regras = {c.id: c for c in session.exec(query).all()}
    if not regras:
        return []

    from fazenda.models import EventoSanitario
    # Mesmo padrão de fazenda.rules.eventos_sanitarios.eventos_agenda (já
    # revisado) — sem o filtro, esta leitura de EventoSanitario crescia com o
    # catálogo de TODAS as fazendas-cliente, não só a atual.
    query_eventos = select(EventoSanitario)
    if fazenda_id is not None:
        query_eventos = query_eventos.where(EventoSanitario.fazenda_id == fazenda_id)
    eventos_por_id = {e.id: e for e in session.exec(query_eventos).all()}
    # Pessoa (veterinário) NÃO filtra por fazenda de propósito — ver o
    # comentário em fazenda/models/pessoal.py:Pessoa.fazenda_id: só a
    # listagem/cadastro principal (GET/POST /pessoas) considera esse campo
    # por enquanto, os demais seletores (este incluso) continuam enxergando
    # todas as pessoas, independente da fazenda.
    pessoas_por_id = {p.id: p for p in session.exec(select(Pessoa)).all()}
    dias_aviso = cronograma_sanitario_dias_aviso()

    # Garante que toda regra usa_cronograma=True já tem um cronograma aberto
    # esperando decisão — nasce no ato, mesmo antes do 1º animal ser sugerido
    # (é a leitura da Agenda, chamada o tempo todo, que faz esse papel de
    # "criar" — não depende de nenhuma ação manual do usuário). Antes disso
    # chamava cronograma_aberto() (1 SELECT, e às vezes INSERT+COMMIT) para
    # CADA regra a cada carregamento da Agenda, mesmo quando ela já tinha um
    # cronograma aberto (o caso comum) — a busca em lote abaixo resolve isso
    # numa consulta só, e só entra na função (que cria) quem realmente está
    # sem cronograma aberto.
    cronogramas = session.exec(
        select(CronogramaSanitario)
        .where(CronogramaSanitario.calendario_sanitario_id.in_(tuple(regras)))
        .where(CronogramaSanitario.status.in_(_ABERTOS))
    ).all()
    regras_com_cronograma = {c.calendario_sanitario_id for c in cronogramas}
    if escrever:
        for calendario_id, calendario in regras.items():
            if calendario_id not in regras_com_cronograma:
                cronogramas.append(cronograma_aberto(session, calendario))

    # Checklist da Ocorrência (Fase 1, passo 7) — materializa (idempotente,
    # nunca duplica/reseta) assim que o cronograma existe, no mesmo espírito
    # de "nasce no ato" do comentário acima. Puramente aditivo: só cria linha
    # numa tabela nova que ninguém lê ainda fora deste redesenho — sem flag.
    for cron in (cronogramas if escrever else []):
        evento = eventos_por_id.get(regras[cron.calendario_sanitario_id].evento_sanitario_id)
        if evento is not None:
            materializar_checklist(session, cron, evento)

    # Trilha do animal (1) para regras por ÉPOCA — só sob a flag (R-1): usa o
    # motor de projeção (R-2, fazenda.rules.projecao_categoria) para sugerir
    # quem vai bater a categoria-alvo na data PREVISTA de cada cronograma
    # aberto, não em quem bate hoje. Regra por evento de vida continua sendo
    # alimentada por fazenda.rules.eventos_sanitarios (gatilho por animal, já
    # existia antes deste redesenho) — nunca duplicada aqui.
    # `coletar_dados_criterios` (rebanho inteiro + histórico reprodutivo) só
    # é buscado se existir ao menos 1 regra por época com cronograma aberto —
    # 1 consulta pesada por carregamento da Agenda, nunca uma por regra.
    if escrever and usar_ocorrencia_universal():
        # Um cronograma de referência por regra: a lista de espera ("aberto") se
        # houver; senão o agendamento em curso (a data devida do ciclo é a mesma).
        por_regra: dict[int, CronogramaSanitario] = {}
        for c in sorted(cronogramas, key=lambda c: (c.status != "aberto", c.data_evento)):
            por_regra.setdefault(c.calendario_sanitario_id, c)
        cronogramas_epoca = [
            c for c in por_regra.values()
            if _regra_e_por_epoca(regras[c.calendario_sanitario_id], eventos_por_id)
        ]
        if cronogramas_epoca:
            from fazenda.api.routers.lotes import coletar_dados_criterios
            dados_criterios = coletar_dados_criterios(session, fazenda_id)
            for cron in cronogramas_epoca:
                calendario = regras[cron.calendario_sanitario_id]
                numeros = animais_projetados_na_categoria(calendario.categoria_alvo or "", _data_devida(cron), dados_criterios)
                ev_regra = eventos_por_id.get(calendario.evento_sanitario_id)
                produto = calendario.produto or (ev_regra.produto_padrao if ev_regra else None)
                vacinados = _ja_vacinados_no_ciclo(session, cron, calendario, produto, numeros)
                numeros = [n for n in numeros if n not in vacinados]
                if numeros:
                    sugerir_animais_em_lote(session, calendario, numeros, hoje)

    # Trilhas do animal (1) e de aplicação (3) abaixo, em lote para TODOS os
    # cronogramas de uma vez — antes eram 2 SELECTs por cronograma aberto
    # (um por "sugerido", outro por "incluído" quando o dia de aplicar
    # chegava), virando dezenas de idas ao banco numa fazenda com várias
    # regras de cronograma simultâneas.
    cronograma_ids = [c.id for c in cronogramas]
    animais_cronograma = session.exec(
        select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id.in_(cronograma_ids))
    ).all() if cronograma_ids else []
    incluidos_por_cronograma: dict[int, list[CronogramaSanitarioAnimal]] = {}
    for linha in animais_cronograma:
        if linha.status == "incluido":
            incluidos_por_cronograma.setdefault(linha.cronograma_id, []).append(linha)

    # Resumo do checklist (x/y) de cada agendamento — a Agenda mostra o selo
    # "checklist pendente" (nunca some, nunca bloqueia; aplicar pede a ciência).
    checklist_por_cron: dict[int, list[str]] = {}
    if cronograma_ids:
        from fazenda.models import ChecklistItem
        for item in session.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id.in_(cronograma_ids))).all():
            checklist_por_cron.setdefault(item.cronograma_id, []).append(item.status)
    desconsiderados = {c.id for c in cronogramas if c.checklist_desconsiderado}
    # Quem pode aplicar (app do peão/Curral: aplicador obrigatório, escolhido por toque; funciona offline porque
    # a lista viaja junto com a Agenda que o app guarda).
    aplicadores: list[dict] | None = None

    saida: list[dict] = []
    for cron in cronogramas:
        calendario = regras[cron.calendario_sanitario_id]
        ev = eventos_por_id.get(calendario.evento_sanitario_id)
        nome = ev.nome if ev else "Evento sanitário"
        alvo = calendario.categoria_alvo or "rebanho"

        # Trilha do animal (sugerido = lista de espera) e cronograma "aberto"
        # (sem modo/data decididos) NÃO viram tarefa (R1/R2): a Agenda só
        # mostra o resumo `resumo_lista_espera`. Só o agendamento entra, no dia.
        if cron.status != "agendado" or hoje < cron.data_evento:
            continue

        # Dia do agendamento chegou, com modo já definido — aplicar.
        eid = f"{PREFIXO_CRONOGRAMA}aplicar_{cron.id}"
        if eid in realizados:
            continue
        incluidos = incluidos_por_cronograma.get(cron.id, [])
        vet = pessoas_por_id.get(cron.veterinario_pessoa_id) if cron.veterinario_pessoa_id else None
        quem = f"com {vet.nome}" if vet else "pela equipe própria"
        fase_exame, leitura_prevista = None, None
        if ev is not None and ev.categoria_preventiva == "exame":
            from fazenda.rules import exame_preventivo
            fase_exame = exame_preventivo.fase_do_agendamento(session, cron)
            ino = exame_preventivo.inoculacao_ativa(session, cron.id) if fase_exame == "leitura" else None
            leitura_prevista = ino.leitura_prevista_em.isoformat() if ino else None
        if aplicadores is None:
            from fazenda.rules.aplicacao_preventiva import eh_veterinario, pessoas_da_fazenda
            aplicadores = [
                {"id": p.id, "nome": p.nome, "crmv": getattr(p, "crmv", None), "veterinario": eh_veterinario(p)}
                for p in pessoas_da_fazenda(session, fazenda_id) if "robo" not in (p.tipo or "").lower().replace("ô", "o")
            ]
        from fazenda.rules.aplicacao_preventiva import exige_veterinario as _exige_vet
        produto_ev = calendario.produto or (ev.produto_padrao if ev else None)
        verbo = "Registrar leitura de" if fase_exame == "leitura" else ("Coletar" if fase_exame == "coleta" else
                                                                       "Inocular" if fase_exame == "inoculacao" else "Aplicar")
        saida.append({
            "id": eid, "data": cron.data_evento.isoformat(), "categoria": "sanidade",
            "descricao": f"{verbo} {nome} hoje{f' às {cron.hora}' if cron.hora else ''} — {quem}",
            "fase": fase_exame, "exame_leitura_prevista_em": leitura_prevista,
            "tipo_protocolo": (ev.categoria_preventiva if ev else None) or "vacina",
            "exige_veterinario": _exige_vet(ev, produto_ev), "aplicadores": aplicadores,
            "aplicador_sugerido_id": cron.veterinario_pessoa_id if cron.modo_execucao == "veterinario" else None,
            "numero_animal": None,
            "observacao": f"{len(incluidos)} animal(is) incluído(s) — Aplicar abre a mesma gaveta de Protocolos.",
            "fonte": "auto", "cor": "var(--dourado)", "ref": None,
            "tipo": "cronograma_sanitario_aplicar",
            "cronograma_id": cron.id, "evento_sanitario_id": calendario.evento_sanitario_id,
            "animais": [l.numero_matriz for l in incluidos],
            "modo_execucao": cron.modo_execucao, "veterinario": vet.nome if vet else None,
            "hora": cron.hora, "protocolo_nome": nome,
            "checklist_total": len(checklist_por_cron.get(cron.id, [])),
            "checklist_resolvidos": len(checklist_por_cron.get(cron.id, [])) if cron.id in desconsiderados
            else sum(1 for st in checklist_por_cron.get(cron.id, []) if st != "pendente"),
        })

    return saida


def materializar(session: Session, hoje: date, fazenda_id: int | None = None) -> None:
    """Parte que ESCREVE do que a Agenda antes fazia dentro do GET: cria o
    cronograma aberto de cada regra, materializa o checklist e coloca animais
    na lista de espera ("sugerido"). Idempotente. Chamado por
    POST /agenda/materializar — nunca por GET."""
    from fazenda.rules.eventos_sanitarios import eventos_agenda as _eventos_sanitarios_agenda
    eventos_agenda(session, hoje, set(), fazenda_id, escrever=True)
    _eventos_sanitarios_agenda(session, hoje, set(), fazenda_id, escrever=True)


# ---------------------------------------------------------------------------
# Lista de espera, "Criar agendamento", adiar e cancelar (fatia 7, R1-R9).
#
# Sem tabela nova: a LISTA DE ESPERA de uma regra são os animais "sugerido" dos
# cronogramas ativos dela (normalmente o cronograma "aberto"); o AGENDAMENTO é
# um cronograma "agendado" (ou "em_montagem", rascunho). Criar agendamento move
# os animais escolhidos para ele; cancelar devolve à lista de espera.
# ---------------------------------------------------------------------------
def _animais_da_fazenda(session: Session, fazenda_id: int | None, numeros: list[str] | None = None) -> dict[str, Animal]:
    query = select(Animal)
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    if numeros is not None:
        query = query.where(Animal.numero.in_(numeros))
    return {a.numero: a for a in session.exec(query).all()}


def _datas_do_gatilho_por_animal(
    session: Session, ev: EventoSanitario | None, hoje: date, fazenda_id: int | None, animais_cache: dict[str, Animal],
) -> tuple[dict[str, date], dict[str, date]]:
    """Regra por EVENTO DE VIDA: por animal, quando a janela abriu e quando fecha
    (mesmo cálculo da Agenda). Regra por época devolve dois dicionários vazios —
    ali a data devida é a do cronograma."""
    if ev is None or ev.tipo_agendamento != "evento" or not ev.gatilho:
        return {}, {}
    from fazenda.rules.eventos_sanitarios import _datas_gatilho

    tem_janela_de = ev.janela_de_valor is not None and ev.janela_de_unidade is not None
    valor, unidade = (ev.janela_de_valor, ev.janela_de_unidade) if tem_janela_de else ((ev.offset_dias or 0), "dias")

    def _por_animal(offset: int, un: str) -> dict[str, date]:
        saida: dict[str, date] = {}
        for numero, quando in _datas_gatilho(
            session, ev.gatilho, ev.gatilho_lote, ev.gatilho_idade_meses, offset, ev.sexo_alvo, fazenda_id,
            animais_cache=animais_cache, offset_unidade=un,
        ):
            atual = saida.get(numero)
            # ocorrência mais recente que já passou (ou a única, se todas forem futuras)
            if atual is None or (quando <= hoje and (atual > hoje or quando > atual)):
                saida[numero] = quando
        return saida

    abre = _por_animal(valor, unidade)
    fecha: dict[str, date] = {}
    if tem_janela_de and ev.janela_ate_valor is not None and ev.janela_ate_unidade is not None:
        fecha = _por_animal(ev.janela_ate_valor, ev.janela_ate_unidade)
    return abre, fecha


def lista_espera(
    session: Session, hoje: date, fazenda_id: int | None = None, calendario_id: int | None = None,
) -> dict:
    """Lista de espera por protocolo (regra): quem está "sugerido", com a
    situação de cada animal — "atrasada" (passou da data devida, a janela segue
    aberta; `dias_atraso`) ou "na_janela" (`fecha_em` = dias até a janela
    fechar, quando há janela cadastrada). Vendidos/baixados e animais que não
    existem mais no rebanho ficam de fora."""
    query = (
        select(CronogramaSanitarioAnimal, CronogramaSanitario, CalendarioSanitario)
        .join(CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAnimal.cronograma_id)
        .join(CalendarioSanitario, CalendarioSanitario.id == CronogramaSanitario.calendario_sanitario_id)
        .where(CronogramaSanitarioAnimal.status == "sugerido")
        .where(CronogramaSanitario.status.in_(_ABERTOS))
        .where(CalendarioSanitario.ativo == True)  # noqa: E712
    )
    if fazenda_id is not None:
        query = query.where(CronogramaSanitario.fazenda_id == fazenda_id)
    if calendario_id is not None:
        query = query.where(CalendarioSanitario.id == calendario_id)
    trios = session.exec(query).all()
    vazio = {"total": 0, "atrasadas": 0, "fecham_7d": 0, "agendamentos_ativos": 0, "grupos": []}
    query_ag = select(CronogramaSanitario).where(CronogramaSanitario.status.in_(("agendado", "em_montagem")))
    if fazenda_id is not None:
        query_ag = query_ag.where(CronogramaSanitario.fazenda_id == fazenda_id)
    vazio["agendamentos_ativos"] = len(session.exec(query_ag).all())
    if not trios:
        return vazio

    animais = _animais_da_fazenda(session, fazenda_id)
    query_ev = select(EventoSanitario)
    if fazenda_id is not None:
        query_ev = query_ev.where(EventoSanitario.fazenda_id == fazenda_id)
    eventos = {e.id: e for e in session.exec(query_ev).all()}

    por_regra: dict[int, list[tuple[CronogramaSanitarioAnimal, CronogramaSanitario]]] = {}
    regras: dict[int, CalendarioSanitario] = {}
    for linha, cron, cal in trios:
        a = animais.get(linha.numero_matriz)
        if a is None or not a.ativo:
            continue
        if linha.reteste and linha.data_devida and linha.data_devida > hoje:
            continue   # reteste de exame (60 dias): so aparece a partir da data devida
        por_regra.setdefault(cal.id, []).append((linha, cron))
        regras[cal.id] = cal

    grupos: list[dict] = []
    for cal_id, linhas in por_regra.items():
        cal = regras[cal_id]
        ev = eventos.get(cal.evento_sanitario_id)
        abre, fecha = _datas_do_gatilho_por_animal(session, ev, hoje, fazenda_id, animais)
        itens: list[dict] = []
        for linha, cron in linhas:
            a = animais[linha.numero_matriz]
            devida = linha.data_devida or abre.get(linha.numero_matriz) or _data_devida(cron)
            fim = fecha.get(linha.numero_matriz)
            atraso = max(0, (hoje - devida).days)
            rotulo = None
            if linha.reteste:
                rotulo = "Reteste atrasado" if atraso > 0 else "Reteste"
            itens.append({
                "linha_id": linha.id, "cronograma_id": cron.id, "numero_matriz": linha.numero_matriz,
                "nome": a.nome, "lote": a.grupo_primario, "sexo": a.sexo,
                "situacao": "atrasada" if atraso > 0 else "na_janela", "dias_atraso": atraso,
                "devida": devida.isoformat(), "janela_fim": fim.isoformat() if fim else None,
                "fecha_em": (fim - hoje).days if fim else None,
                "desde": linha.data_sugestao.isoformat(),
                "reteste": bool(linha.reteste), "situacao_rotulo": rotulo,
                "motivo_entrada": linha.motivo_entrada or "Entrou na janela pela regra do protocolo",
            })
        itens.sort(key=lambda i: (-i["dias_atraso"], i["numero_matriz"]))
        fechamentos = [i["fecha_em"] for i in itens if i["fecha_em"] is not None]
        lotes = sorted({i["lote"] for i in itens if i["lote"]})
        grupos.append({
            "calendario_id": cal.id, "evento_sanitario_id": cal.evento_sanitario_id,
            "protocolo_nome": ev.nome if ev else "Evento sanitário", "categoria_alvo": cal.categoria_alvo,
            "tipo": (ev.categoria_preventiva if ev else None) or "vacina",
            "produto": cal.produto or (ev.produto_padrao if ev else None),
            "dose": ev.dose_padrao if ev else None, "unidade": ev.unidade_padrao if ev else None,
            "via": ev.via_padrao if ev else None,
            "lotes": lotes,
            "janela_de": min(i["devida"] for i in itens),
            "janela_ate": max((i["janela_fim"] for i in itens if i["janela_fim"]), default=None),
            "quantidade": len(itens),
            "atrasadas": sum(1 for i in itens if i["situacao"] == "atrasada"),
            "dias_atraso": max(i["dias_atraso"] for i in itens),
            "fecha_em": min(fechamentos) if fechamentos else None,
            "situacao": "atrasada" if any(i["situacao"] == "atrasada" for i in itens) else "na_janela",
            "animais": itens,
        })
    grupos.sort(key=lambda g: (-g["dias_atraso"], g["protocolo_nome"]))
    todos = [i for g in grupos for i in g["animais"]]
    return {
        "total": len(todos),
        "atrasadas": sum(1 for i in todos if i["situacao"] == "atrasada"),
        "fecham_7d": sum(1 for i in todos if i["fecha_em"] is not None and 0 <= i["fecha_em"] <= 7),
        "agendamentos_ativos": vazio["agendamentos_ativos"],
        "grupos": grupos,
    }


def _upsert_linha(
    session: Session, cronograma_id: int, numero: str, fazenda_id: int | None, **campos,
) -> CronogramaSanitarioAnimal:
    existente = session.exec(
        select(CronogramaSanitarioAnimal)
        .where(CronogramaSanitarioAnimal.cronograma_id == cronograma_id)
        .where(CronogramaSanitarioAnimal.numero_matriz == numero)
    ).first()
    if existente is None:
        existente = CronogramaSanitarioAnimal(
            cronograma_id=cronograma_id, numero_matriz=numero, data_sugestao=campos.pop("data_sugestao", date.today()),
            fazenda_id=fazenda_id,
        )
    for k, v in campos.items():
        setattr(existente, k, v)
    session.add(existente)
    return existente


def criar_agendamento(
    session: Session, calendario: CalendarioSanitario, *, animais_janela: list[str],
    animais_fora: list[tuple[str, str | None]], data_evento: date, hora: str | None, hoje: date,
    modo_execucao: str | None = None, veterinario_pessoa_id: int | None = None,
    observacao: str | None = None, rascunho: bool = False,
) -> CronogramaSanitario:
    """"Criar agendamento" a partir da lista de espera: os animais da janela
    saem da lista e entram no agendamento; os de fora da janela entram marcados
    ("fora_janela") com motivo obrigatório (R6). Um animal só pode estar em uma
    lista/agendamento ativo por protocolo (R8). Todas as validações acontecem
    antes de gravar qualquer coisa."""
    janela = list(dict.fromkeys(n.strip() for n in animais_janela if (n or "").strip()))
    fora: dict[str, str] = {}
    for numero, motivo in animais_fora:
        numero = (numero or "").strip()
        if not numero:
            continue
        if not (motivo or "").strip():
            raise CronogramaError(f"Informe o motivo para incluir o animal {numero} fora da janela")
        fora[numero] = motivo.strip()
    if not janela and not fora:
        raise CronogramaError("Escolha pelo menos um animal para o agendamento")
    repetidos = sorted(set(janela) & set(fora))
    if repetidos:
        raise CronogramaError(f"Animal {repetidos[0]} está na janela e fora da janela ao mesmo tempo")
    if hora and not _HORA_RE.match(hora):
        raise CronogramaError("Hora inválida — use HH:MM")
    if not rascunho:
        modo = modo_execucao or "propria"
        if modo not in ("veterinario", "propria"):
            raise CronogramaError("Modo inválido — use veterinario ou propria")
        if modo == "veterinario":
            if not veterinario_pessoa_id:
                raise CronogramaError("Selecione o veterinário")
            pessoa = session.get(Pessoa, veterinario_pessoa_id)
            if not pessoa or not pessoa.ativo:
                raise CronogramaError("Veterinário não encontrado")
    else:
        modo = None

    from fazenda.rules.aplicacao_preventiva import eh_b19, restricao_b19
    from fazenda.rules.exame_preventivo import recusar_reagentes
    try:
        recusar_reagentes(session, calendario.fazenda_id, janela + list(fora), "agendamento")
    except Exception as e:   # AplicacaoError -> erro de uso do workflow
        raise CronogramaError(str(e))
    animais_da_regra = _linhas_da_regra(session, calendario.id, janela + list(fora))
    espera = {l.numero_matriz: (l, c) for l, c in animais_da_regra if l.status == "sugerido"}
    ocupados = {l.numero_matriz: c for l, c in animais_da_regra if l.status in ("incluido", "aplicado")}
    ativos = _animais_da_fazenda(session, calendario.fazenda_id, janela + list(fora))

    for numero in janela:
        if numero not in espera:
            if numero in ocupados:
                raise CronogramaError(f"Animal {numero} já está em outro agendamento deste protocolo")
            raise CronogramaError(f"Animal {numero} não está na lista de espera deste protocolo")
        a = ativos.get(numero)
        if a is None or not a.ativo:
            raise CronogramaError(f"Animal {numero} não está mais no rebanho (vendido/baixado)")
    evento_b19 = session.get(EventoSanitario, calendario.evento_sanitario_id)
    if eh_b19(evento_b19, calendario.produto):
        for numero in janela + list(fora):
            motivo_b19 = restricao_b19(ativos.get(numero), so_sexo=True)
            if motivo_b19:
                raise CronogramaError(f"Animal {numero}: brucelose B19 só vale para fêmeas de 3 a 8 meses — este animal é macho")
    for numero in fora:
        a = ativos.get(numero)
        if a is None:
            raise CronogramaError(f"Animal {numero} não encontrado")
        if not a.ativo:
            raise CronogramaError(f"Animal {numero} não está mais no rebanho (vendido/baixado)")
        if numero in espera:
            raise CronogramaError(f"Animal {numero} já está na lista de espera — inclua como animal da janela")
        if numero in ocupados:
            raise CronogramaError(f"Animal {numero} já está em outro agendamento deste protocolo")

    origens = {espera[n][1].id: espera[n][1] for n in janela}
    reaproveita: CronogramaSanitario | None = None
    if len(origens) == 1:
        origem = next(iter(origens.values()))
        sugeridos_da_origem = session.exec(
            select(CronogramaSanitarioAnimal)
            .where(CronogramaSanitarioAnimal.cronograma_id == origem.id)
            .where(CronogramaSanitarioAnimal.status == "sugerido")
        ).all()
        if origem.status == "aberto" and {l.numero_matriz for l in sugeridos_da_origem} <= set(janela):
            reaproveita = origem
    devida = (
        next(iter(origens.values())).data_evento if len(origens) == 1
        else (min(c.data_evento for c in origens.values()) if origens else data_evento)
    )
    agora = datetime.utcnow()
    if reaproveita is not None:
        cron = reaproveita
        if cron.data_original is None and cron.data_evento != data_evento:
            cron.data_original = cron.data_evento
        cron.data_evento = data_evento
    else:
        cron = CronogramaSanitario(
            calendario_sanitario_id=calendario.id, data_evento=data_evento,
            data_original=devida if devida != data_evento else None, fazenda_id=calendario.fazenda_id,
        )
        session.add(cron)
        session.flush()
    cron.hora = hora or None
    cron.modo_execucao = modo
    cron.veterinario_pessoa_id = veterinario_pessoa_id if modo == "veterinario" else None
    cron.status = "em_montagem" if rascunho else "agendado"
    if observacao and observacao.strip():
        cron.observacao = observacao.strip()
    cron.atualizado_em = agora
    session.add(cron)
    session.flush()

    for numero in janela:
        linha = espera[numero][0]
        if linha.cronograma_id != cron.id:
            linha.cronograma_id = cron.id
        linha.status = "incluido"
        linha.origem = "janela"
        linha.data_decisao = hoje
        session.add(linha)
    for numero, motivo in fora.items():
        _upsert_linha(
            session, cron.id, numero, calendario.fazenda_id, status="incluido", origem="fora_janela", motivo=motivo,
            data_sugestao=hoje, data_decisao=hoje, data_aplicacao=None,
        )
    session.commit()
    session.refresh(cron)
    evento = session.get(EventoSanitario, calendario.evento_sanitario_id)
    if evento is not None:
        materializar_checklist(session, cron, evento)
    return cron


def cancelar(
    session: Session, cronograma: CronogramaSanitario, motivo: str | None, hoje: date, destino_animais: str = "espera",
) -> int:
    """Cancela um agendamento (R9): os animais que vieram da janela voltam à
    lista de espera como "sugerido"; os que foram incluídos fora da janela não
    têm lista para onde voltar e ficam só no histórico do agendamento cancelado.
    Devolve quantos animais voltaram para a lista de espera."""
    if not (motivo or "").strip():
        raise CronogramaError("Informe o motivo do cancelamento")
    if destino_animais not in ("espera", "naoSeAplica"):
        raise CronogramaError("Destino dos animais inválido — use espera ou naoSeAplica")
    if cronograma.status == "concluido":
        raise CronogramaError("Este agendamento já foi aplicado — não é possível cancelar")
    if cronograma.status == "cancelado":
        raise CronogramaError("Este agendamento já foi cancelado")
    if cronograma.status == "aberto":
        raise CronogramaError("Só um agendamento pode ser cancelado (a lista de espera não é cancelada)")
    calendario = session.get(CalendarioSanitario, cronograma.calendario_sanitario_id)
    incluidos = [
        l for l in animais_por_status(session, cronograma.id, "incluido") if l.origem != "fora_janela"
    ]
    cronograma.status = "cancelado"
    cronograma.motivo_cancelamento = motivo.strip()
    cronograma.atualizado_em = datetime.utcnow()
    session.add(cronograma)
    session.flush()
    if destino_animais == "naoSeAplica":
        # "Desconsiderar": ninguém volta para a lista de espera; todos ficam
        # marcados como excluídos, com o motivo do cancelamento.
        for l in animais_por_status(session, cronograma.id, "incluido"):
            l.status = "excluido"
            l.motivo = motivo.strip()
            l.data_decisao = hoje
            session.add(l)
        session.commit()
        return 0
    if incluidos and calendario is not None:
        espera = cronograma_aberto_ou_novo(session, calendario, _data_devida(cronograma))
        for l in incluidos:
            _upsert_linha(
                session, espera.id, l.numero_matriz, cronograma.fazenda_id, status="sugerido", origem="janela",
                motivo=None, data_sugestao=l.data_sugestao, data_decisao=None,
            )
    session.commit()
    return len(incluidos)


def confirmar_rascunho(
    session: Session, cronograma: CronogramaSanitario, data_evento: date, hora: str | None,
    modo_execucao: str | None, veterinario_pessoa_id: int | None,
) -> CronogramaSanitario:
    """"Continuar montando": confirma um rascunho (em_montagem) como agendamento —
    a partir daqui ele entra na Agenda no dia."""
    if cronograma.status != "em_montagem":
        raise CronogramaError("Só um agendamento em montagem pode ser confirmado")
    if hora and not _HORA_RE.match(hora):
        raise CronogramaError("Hora inválida — use HH:MM")
    modo = modo_execucao or "propria"
    if modo not in ("veterinario", "propria"):
        raise CronogramaError("Modo inválido — use veterinario ou propria")
    if modo == "veterinario":
        pessoa = session.get(Pessoa, veterinario_pessoa_id) if veterinario_pessoa_id else None
        if not pessoa or not pessoa.ativo:
            raise CronogramaError("Selecione o veterinário")
    if cronograma.data_original is None and cronograma.data_evento != data_evento:
        cronograma.data_original = cronograma.data_evento
    cronograma.data_evento = data_evento
    cronograma.hora = hora or None
    cronograma.modo_execucao = modo
    cronograma.veterinario_pessoa_id = veterinario_pessoa_id if modo == "veterinario" else None
    cronograma.status = "agendado"
    cronograma.atualizado_em = datetime.utcnow()
    session.add(cronograma)
    session.commit()
    session.refresh(cronograma)
    return cronograma


MOTIVOS_TIRAR_ANIMAL = ("Vendido", "Doente", "Não localizado", "Outro")


def _tem_aplicacao_ativa(session: Session, cronograma_id: int) -> bool:
    from fazenda.models import CronogramaSanitarioAplicacao
    return session.exec(
        select(CronogramaSanitarioAplicacao.id).where(CronogramaSanitarioAplicacao.cronograma_id == cronograma_id)
        .where(CronogramaSanitarioAplicacao.estado == "aplicada")
    ).first() is not None


def reabrir_para_editar(session: Session, cronograma: CronogramaSanitario) -> CronogramaSanitario:
    """"Reabrir para editar" (mockup, fatia 9b): um agendamento confirmado volta a "em montagem" — sai da Agenda, e os
    animais, o checklist e a data ficam como estavam; ao confirmar de novo (Continuar montando) volta para a Agenda.
    Não vale para o que já foi aplicado/cancelado nem para exame já inoculado (o registro em andamento não se desmonta)."""
    if cronograma.status == "em_montagem":
        raise CronogramaError("Este agendamento já está em montagem")
    if cronograma.status == "concluido":
        raise CronogramaError("Este agendamento já foi aplicado — não é possível reabrir")
    if cronograma.status == "cancelado":
        raise CronogramaError("Este agendamento foi cancelado — não é possível reabrir")
    if cronograma.status != "agendado":
        raise CronogramaError("Só um agendamento confirmado pode ser reaberto para editar")
    if _tem_aplicacao_ativa(session, cronograma.id):
        raise CronogramaError("Este exame já foi inoculado — não é possível reabrir: registre a leitura (ou estorne a inoculação)")
    cronograma.status = "em_montagem"
    cronograma.atualizado_em = datetime.utcnow()
    session.add(cronograma)
    session.commit()
    session.refresh(cronograma)
    return cronograma


def tirar_animal(
    session: Session, cronograma: CronogramaSanitario, numero: str, motivo: str | None, motivo_outro: str | None, hoje: date,
) -> tuple[CronogramaSanitarioAnimal, str]:
    """Tira um animal de um agendamento já criado (motivo em chips). Devolve (linha, destino):
      "espera"  — animal da janela volta para a lista de espera do protocolo;
      "baixado" — vendido (ou já fora do rebanho): fica só no histórico do agendamento, não volta para a lista;
      "saiu"    — animal incluído fora da janela: não há lista para onde voltar, só sai.
    Nunca o último animal (cancele o agendamento) nem em exame já inoculado/agendamento aplicado."""
    if cronograma.status not in ("agendado", "em_montagem"):
        raise CronogramaError("Só dá para tirar animal de um agendamento em montagem ou agendado")
    if _tem_aplicacao_ativa(session, cronograma.id):
        raise CronogramaError("Este exame já foi inoculado: o animal inoculado não sai do agendamento — registre o resultado da leitura")
    motivo = (motivo or "").strip()
    if motivo not in MOTIVOS_TIRAR_ANIMAL:
        raise CronogramaError("Escolha o motivo para tirar o animal: " + ", ".join(MOTIVOS_TIRAR_ANIMAL))
    texto = motivo
    if motivo == "Outro":
        texto = (motivo_outro or "").strip()
        if not texto:
            raise CronogramaError("Descreva o motivo (Outro)")
    numero = (numero or "").strip()
    linhas = animais_por_status(session, cronograma.id, "incluido")
    linha = next((l for l in linhas if l.numero_matriz == numero), None)
    if linha is None:
        raise CronogramaError(f"Animal {numero} não está neste agendamento")
    if len(linhas) <= 1:
        raise CronogramaError("Este é o último animal do agendamento: cancele o agendamento em vez de tirá-lo")
    calendario = session.get(CalendarioSanitario, cronograma.calendario_sanitario_id)
    animal = session.exec(select(Animal).where(Animal.numero == numero).where(Animal.fazenda_id == cronograma.fazenda_id)).first()
    baixado = motivo == "Vendido" or animal is None or not animal.ativo
    if baixado:
        linha.status = "excluido"
        linha.motivo = f"Baixado: {texto}" if motivo != "Vendido" else "Baixado: vendido"
        linha.data_decisao = hoje
        destino = "baixado"
    elif linha.origem == "fora_janela" or calendario is None:
        linha.status = "excluido"
        linha.motivo = texto
        linha.data_decisao = hoje
        destino = "saiu"
    else:
        espera = cronograma_aberto_ou_novo(session, calendario, _data_devida(cronograma))
        ja = session.exec(
            select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == espera.id)
            .where(CronogramaSanitarioAnimal.numero_matriz == numero)
        ).first()
        if ja is not None and ja.id != linha.id:
            session.delete(ja)
            session.flush()
        linha.cronograma_id = espera.id
        linha.status = "sugerido"
        linha.origem = "janela"
        linha.motivo = None
        linha.data_decisao = None
        linha.motivo_entrada = f"Saiu do agendamento de {cronograma.data_evento.strftime('%d/%m/%Y')}: {texto}"
        destino = "espera"
    cronograma.atualizado_em = datetime.utcnow()
    session.add(linha)
    session.add(cronograma)
    session.commit()
    session.refresh(linha)
    session.refresh(cronograma)
    return linha, destino


def cronograma_aberto_ou_novo(session: Session, calendario: CalendarioSanitario, data_devida: date) -> CronogramaSanitario:
    """Cronograma "aberto" (lista de espera) da regra; se não houver, cria um na
    data devida informada (e não na próxima ocorrência projetada)."""
    existente = session.exec(
        select(CronogramaSanitario)
        .where(CronogramaSanitario.calendario_sanitario_id == calendario.id)
        .where(CronogramaSanitario.status == "aberto")
        .order_by(CronogramaSanitario.data_evento)
    ).first()
    if existente:
        return existente
    novo = CronogramaSanitario(
        calendario_sanitario_id=calendario.id, data_evento=data_devida, fazenda_id=calendario.fazenda_id,
    )
    session.add(novo)
    session.flush()
    return novo


def desconsiderar(
    session: Session, calendario: CalendarioSanitario, numeros: list[str], motivo: str | None, hoje: date,
) -> int:
    """"Desconsiderar" animais da lista de espera (não se aplica), com motivo
    obrigatório. Não os re-sugere no mesmo ciclo. Devolve quantos saíram."""
    if not (motivo or "").strip():
        raise CronogramaError("Informe o motivo para desconsiderar")
    alvo = list(dict.fromkeys(n.strip() for n in numeros if (n or "").strip()))
    if not alvo:
        raise CronogramaError("Escolha pelo menos um animal")
    sugeridos = {l.numero_matriz: l for l, _ in _linhas_da_regra(session, calendario.id, alvo) if l.status == "sugerido"}
    ausentes = [n for n in alvo if n not in sugeridos]
    if ausentes:
        raise CronogramaError(f"Animal {ausentes[0]} não está na lista de espera deste protocolo")
    for numero, linha in sugeridos.items():
        linha.status = "excluido"
        linha.motivo = motivo.strip()
        linha.data_decisao = hoje
        session.add(linha)
    session.commit()
    return len(sugeridos)
