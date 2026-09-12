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

from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from fazenda.models import CalendarioSanitario, CronogramaSanitario, CronogramaSanitarioAnimal, Pessoa
from fazenda.rules.calendario_sanitario import proxima_ocorrencia
from fazenda.rules.checklist_sanitario import materializar_checklist
from fazenda.rules.parametros import cronograma_sanitario_dias_aviso, usar_ocorrencia_universal
from fazenda.rules.projecao_categoria import animais_projetados_na_categoria

PREFIXO_CRONOGRAMA = "cronograma_sanitario_"

_ABERTOS = ("aberto", "agendado")


class CronogramaError(Exception):
    """Erro de uso do workflow — o router converte em HTTP 400."""


def cronograma_aberto(session: Session, calendario: CalendarioSanitario) -> CronogramaSanitario:
    """Devolve o cronograma em aberto da regra, criando um novo (com a
    próxima data projetada) se não houver nenhum."""
    existente = session.exec(
        select(CronogramaSanitario)
        .where(CronogramaSanitario.calendario_sanitario_id == calendario.id)
        .where(CronogramaSanitario.status.in_(_ABERTOS))
        .order_by(CronogramaSanitario.data_evento)
    ).first()
    if existente:
        return existente

    ultimo = session.exec(
        select(CronogramaSanitario)
        .where(CronogramaSanitario.calendario_sanitario_id == calendario.id)
        .order_by(CronogramaSanitario.criado_em.desc())
    ).first()
    # Sem cronograma anterior: a 1ª ocorrência é a própria data_evento da
    # regra (mesma referência usada por _ocorrencias_recorrentes). Com um
    # anterior (concluído/cancelado), projeta a próxima a partir dele.
    proxima = (
        proxima_ocorrencia(ultimo.data_evento, calendario.frequencia_valor, calendario.frequencia_unidade)
        if ultimo else calendario.data_evento
    )
    novo = CronogramaSanitario(
        calendario_sanitario_id=calendario.id, data_evento=proxima, fazenda_id=calendario.fazenda_id,
    )
    session.add(novo)
    session.commit()
    session.refresh(novo)
    return novo


def sugerir_animal(session: Session, calendario: CalendarioSanitario, numero_matriz: str, hoje: date) -> CronogramaSanitarioAnimal | None:
    """Garante uma linha "sugerido" para o animal no cronograma aberto da
    regra. Idempotente: devolve None (não gera pendência de novo) se o
    animal já tem linha nesse cronograma, em qualquer status."""
    cron = cronograma_aberto(session, calendario)
    existente = session.exec(
        select(CronogramaSanitarioAnimal)
        .where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
        .where(CronogramaSanitarioAnimal.numero_matriz == numero_matriz)
    ).first()
    if existente:
        return None
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
    cron = cronograma_aberto(session, calendario)
    existentes = set(session.exec(
        select(CronogramaSanitarioAnimal.numero_matriz)
        .where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
        .where(CronogramaSanitarioAnimal.numero_matriz.in_(numeros_matriz))
    ).all())
    novos = [
        CronogramaSanitarioAnimal(cronograma_id=cron.id, numero_matriz=n, data_sugestao=hoje, fazenda_id=calendario.fazenda_id)
        for n in dict.fromkeys(numeros_matriz)  # preserva ordem e remove duplicata, por segurança
        if n not in existentes
    ]
    if not novos:
        return
    session.add_all(novos)
    session.commit()


def incluir_animal_manual(
    session: Session, cronograma: CronogramaSanitario, numero_matriz: str, hoje: date,
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


def adiar(session: Session, cronograma: CronogramaSanitario, nova_data: date, motivo: str | None) -> CronogramaSanitario:
    """Reabre o ciclo de decisão com uma nova data — usado tanto a partir do
    aviso obrigatório de N dias antes quanto, por conveniência, a qualquer
    momento em que o cronograma ainda não tenha sido aplicado."""
    if cronograma.status == "concluido":
        raise CronogramaError("Este cronograma já foi aplicado — não é possível adiar")
    if cronograma.data_original is None:
        cronograma.data_original = cronograma.data_evento
    cronograma.data_evento = nova_data
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
def eventos_agenda(session: Session, hoje: date, realizados: set[str], fazenda_id: int | None = None) -> list[dict]:
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
    for calendario_id, calendario in regras.items():
        if calendario_id not in regras_com_cronograma:
            cronogramas.append(cronograma_aberto(session, calendario))

    # Checklist da Ocorrência (Fase 1, passo 7) — materializa (idempotente,
    # nunca duplica/reseta) assim que o cronograma existe, no mesmo espírito
    # de "nasce no ato" do comentário acima. Puramente aditivo: só cria linha
    # numa tabela nova que ninguém lê ainda fora deste redesenho — sem flag.
    for cron in cronogramas:
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
    if usar_ocorrencia_universal():
        cronogramas_epoca = [
            c for c in cronogramas
            if _regra_e_por_epoca(regras[c.calendario_sanitario_id], eventos_por_id)
        ]
        if cronogramas_epoca:
            from fazenda.api.routers.lotes import coletar_dados_criterios
            dados_criterios = coletar_dados_criterios(session, fazenda_id)
            for cron in cronogramas_epoca:
                calendario = regras[cron.calendario_sanitario_id]
                numeros = animais_projetados_na_categoria(calendario.categoria_alvo or "", cron.data_evento, dados_criterios)
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
    sugeridos_por_cronograma: dict[int, list[CronogramaSanitarioAnimal]] = {}
    incluidos_por_cronograma: dict[int, list[CronogramaSanitarioAnimal]] = {}
    for linha in animais_cronograma:
        if linha.status == "sugerido":
            sugeridos_por_cronograma.setdefault(linha.cronograma_id, []).append(linha)
        elif linha.status == "incluido":
            incluidos_por_cronograma.setdefault(linha.cronograma_id, []).append(linha)

    saida: list[dict] = []
    for cron in cronogramas:
        calendario = regras[cron.calendario_sanitario_id]
        ev = eventos_por_id.get(calendario.evento_sanitario_id)
        nome = ev.nome if ev else "Evento sanitário"
        alvo = calendario.categoria_alvo or "rebanho"

        # (1) Trilha do animal — um card por animal "sugerido" ainda sem decisão.
        for linha in sugeridos_por_cronograma.get(cron.id, []):
            eid = f"{PREFIXO_CRONOGRAMA}animal_{linha.id}"
            if eid in realizados:
                continue
            saida.append({
                "id": eid, "data": linha.data_sugestao.isoformat(), "categoria": "sanidade",
                "descricao": f"Matriz {linha.numero_matriz} entrou na janela — {nome}",
                "numero_animal": linha.numero_matriz,
                "observacao": "Incluir no cronograma (aguarda a próxima aplicação) ou excluir?",
                "fonte": "auto", "cor": "var(--dourado)", "ref": None,
                "tipo": "cronograma_sanitario_animal",
                "cronograma_animal_id": linha.id, "cronograma_id": cron.id,
                "evento_sanitario_id": calendario.evento_sanitario_id,
            })

        # (2) Trilha do agendamento — 1 card por cronograma aberto, com
        # urgência crescente conforme a data se aproxima sem decisão.
        if cron.status == "aberto":
            urgente = hoje >= (cron.data_evento - timedelta(days=dias_aviso))
            eid = f"{PREFIXO_CRONOGRAMA}modo_{cron.id}"
            if eid not in realizados:
                if urgente:
                    desc = f"{nome} previsto para {cron.data_evento.strftime('%d/%m/%Y')} — ainda sem veterinário nem aplicação própria confirmada"
                    obs = "Confirme como vai ser aplicado ou adie a data — obrigatório antes do dia previsto."
                else:
                    desc = f"{nome} — cronograma criado para {cron.data_evento.strftime('%d/%m/%Y')}"
                    obs = "Como vai ser aplicado: veterinário agendado, equipe própria, ou decide depois?"
                saida.append({
                    "id": eid, "data": (cron.data_evento - timedelta(days=dias_aviso) if urgente else cron.criado_em.date()).isoformat(),
                    "categoria": "sanidade", "descricao": desc, "numero_animal": None,
                    "observacao": obs, "fonte": "auto",
                    "cor": "var(--red)" if urgente else "var(--dourado)", "ref": None,
                    "tipo": "cronograma_sanitario_urgente" if urgente else "cronograma_sanitario_modo",
                    "cronograma_id": cron.id, "evento_sanitario_id": calendario.evento_sanitario_id,
                    "categoria_alvo": alvo, "data_evento": cron.data_evento.isoformat(),
                })

        # (3) Dia do evento chegou, com modo já definido — aplicar.
        elif cron.status == "agendado" and hoje >= cron.data_evento:
            eid = f"{PREFIXO_CRONOGRAMA}aplicar_{cron.id}"
            if eid in realizados:
                continue
            incluidos = incluidos_por_cronograma.get(cron.id, [])
            vet = pessoas_por_id.get(cron.veterinario_pessoa_id) if cron.veterinario_pessoa_id else None
            quem = f"com {vet.nome}" if vet else "pela equipe própria"
            saida.append({
                "id": eid, "data": cron.data_evento.isoformat(), "categoria": "sanidade",
                "descricao": f"Aplicar {nome} hoje — {quem}",
                "numero_animal": None,
                "observacao": f"{len(incluidos)} animal(is) incluído(s) — aplicar em lote ou individualizado.",
                "fonte": "auto", "cor": "var(--dourado)", "ref": None,
                "tipo": "cronograma_sanitario_aplicar",
                "cronograma_id": cron.id, "evento_sanitario_id": calendario.evento_sanitario_id,
                "animais": [l.numero_matriz for l in incluidos],
                "modo_execucao": cron.modo_execucao, "veterinario": vet.nome if vet else None,
            })

    return saida
