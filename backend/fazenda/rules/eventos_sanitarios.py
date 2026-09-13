"""
Geração dos eventos da Agenda a partir do cadastro de EVENTO SANITÁRIO.

Cada evento sanitário pode ser agendado de dois jeitos:
  • por ÉPOCA  — recorrência fixa (ex.: vermífugo a cada 6 meses), a partir de
    uma data de referência (data_primeiro);
  • por EVENTO — disparado por um acontecimento da vida do animal
    (nascimento, entrada num lote — ex.: pré-parto —, aptidão de novilha,
    secagem, parto).

Os eventos carregam o MEDICAMENTO PADRÃO (produto/dose/unidade/via), que a
Agenda usa para pré-preencher a tela de Aplicação — editável na hora. Ao dar
baixa (aplicar), a saída de estoque e o registro de Sanidade acontecem pelo
fluxo normal de /sanidade/aplicacoes.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from fazenda.models import (
    Animal, CalendarioSanitario, CategoriaManejo, Estoque, EventoSanitario, MovimentoLote, Parto, Sanidade, Secagem, Servico,
)
from fazenda.rules.calendario_sanitario import _somar_meses, proxima_ocorrencia
from fazenda.rules.gestation import calcular_parto_provavel
from fazenda.rules.parametros import janela_eventos_sanitarios_futuro, janela_eventos_sanitarios_passado, pre_parto_max

# Eventos de vida (gatilhos) que o calendário sanitário e o cadastro de evento
# sanitário podem usar em vez de uma frequência periódica — cada um corresponde
# a uma mudança de categoria/fase do animal. Mantido em sincronia com
# GATILHOS_EVENTO (fazenda.api.routers.cadastro).
ROTULOS_GATILHO = {
    "nascimento": "Nascimento",
    "desmama": "Desmama",
    "mudanca_recria": "Mudança para recria",
    # "atingir certa idade", não "apta" — o gatilho usa a idade-alvo do
    # cadastro do evento, não os parâmetros de aptidão reprodutiva (ver
    # `_datas_gatilho`). Mesmo texto do seletor da tela
    # (CadastroSanitario.tsx), para os dois não sugerirem coisas diferentes.
    "novilha_apta": "Aptidão (novilha atingir certa idade)",
    "inseminacao": "Inseminação",
    "gestacao_confirmada": "Gestação confirmada",
    "secagem": "Secagem",
    "parto": "Parto",
    "mudanca_pre_parto": "Mudança para pré-parto",
    "entrada_lote": "Entrada em lote",
}


def _ocorrencias_recorrentes(
    base: date, valor: int | None, unidade: str | None, hoje: date,
    janela_passado: int | None = None, janela_futuro: int | None = None,
) -> list[date]:
    """Datas da recorrência dentro da janela [hoje-janela_passado, hoje+janela_futuro]
    (editável em Configurações > Parâmetros, padrão 120/180 dias).

    `janela_passado`/`janela_futuro` são opcionais — quando o chamador está
    num loop por evento/regra (ver `eventos_agenda`/`_eventos_calendario_agenda`
    abaixo), calcula os dois UMA vez fora do loop e passa aqui, evitando reler
    o mesmo parâmetro (via `_linha`, que abre uma sessão de banco própria a
    cada chamada) uma vez por evento cadastrado. Sem eles, consulta como
    sempre — mantém quem chama isolado (fora deste arquivo, hoje ninguém)."""
    if not (base and valor and unidade):
        return []
    if janela_passado is None:
        janela_passado = janela_eventos_sanitarios_passado()
    if janela_futuro is None:
        janela_futuro = janela_eventos_sanitarios_futuro()
    minimo = hoje - timedelta(days=janela_passado)
    limite = hoje + timedelta(days=janela_futuro)
    saida: list[date] = []
    d = base
    guarda = 0
    while d <= limite and guarda < 3000:
        if d >= minimo:
            saida.append(d)
        d = proxima_ocorrencia(d, valor, unidade)
        guarda += 1
    return saida


def _ocorrencias_epoca(
    ev: EventoSanitario, hoje: date, janela_passado: int | None = None, janela_futuro: int | None = None,
) -> list[date]:
    return _ocorrencias_recorrentes(ev.data_primeiro, ev.frequencia_valor, ev.frequencia_unidade, hoje, janela_passado, janela_futuro)


def _limiares_categoria(session: Session, fazenda_id: int | None) -> tuple[int, int]:
    """Dia de desmama (fim da 1ª categoria cadastrada) e dia de entrada em
    recria (início da 2ª) — lidos do cadastro de Categorias (Configurações >
    Cadastro > Categorias), na ordem cadastrada (`CategoriaManejo.ordem`).
    Sem cadastro suficiente, cai no padrão histórico de 90/91 dias (mesmo
    usado no aviso fixo de desmama da Agenda)."""
    query = select(CategoriaManejo).where(CategoriaManejo.ativo == True).order_by(CategoriaManejo.ordem)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(CategoriaManejo.fazenda_id == fazenda_id)
    cats = session.exec(query).all()
    if len(cats) >= 2 and cats[1].dia_min is not None:
        dia_desmama = cats[0].dia_max if cats[0].dia_max is not None else 90
        return dia_desmama, cats[1].dia_min
    return 90, 91


def _datas_gatilho(
    session: Session, gatilho: str, gatilho_lote: str | None = None, gatilho_idade_meses: int | None = None,
    offset_dias: int = 0, sexo_alvo: str | None = None, fazenda_id: int | None = None,
    animais_cache: dict[str, Animal] | None = None,
    offset_unidade: str = "dias",
) -> list[tuple[str, date]]:
    """Datas (por animal) em que um gatilho de evento de vida ocorre ou vai
    ocorrer — usado tanto para gerar a pendência na Agenda (`eventos_agenda`)
    quanto para o relatório de "quais animais entrarão em determinado
    calendário" (rota /sanidade/calendario/relatorio-eventos-vida).

    `animais_cache` (numero -> Animal) é opcional — quando o chamador já tem
    a tabela Animal carregada (ver `eventos_agenda` abaixo, que chama esta
    função uma vez por EVENTO SANITÁRIO "por evento" cadastrado), evita reler
    a tabela inteira de novo só para o filtro de elegibilidade no fim desta
    função; sem cache (demais chamadores, uma chamada isolada cada), consulta
    como sempre.

    `offset_unidade` deixa o deslocamento ser em dias OU meses (calendário
    de verdade, via `proxima_ocorrencia` — não uma aproximação de 30 dias).
    Com o padrão "dias", `_aplicar_offset` é idêntico a `data + timedelta`
    de antes: nenhum chamador existente muda de comportamento."""
    def _aplicar_offset(d: date) -> date:
        if not offset_dias:
            return d
        return proxima_ocorrencia(d, offset_dias, offset_unidade or "dias")

    saida: list[tuple[str, date]] = []

    def _da_fazenda(query, modelo):
        if fazenda_id is None:
            return query
        return query.where(modelo.fazenda_id == fazenda_id)

    if gatilho == "nascimento":
        for a in session.exec(_da_fazenda(select(Animal).where(Animal.data_nasc != None), Animal)).all():  # noqa: E711
            saida.append((a.numero, _aplicar_offset(a.data_nasc)))
    elif gatilho == "secagem":
        for s in session.exec(_da_fazenda(select(Secagem), Secagem)).all():
            saida.append((s.numero_matriz, _aplicar_offset(s.data_secagem)))
    elif gatilho == "parto":
        for p in session.exec(_da_fazenda(select(Parto).where(Parto.data_parto != None), Parto)).all():  # noqa: E711
            saida.append((p.numero_matriz, _aplicar_offset(p.data_parto)))
    elif gatilho == "entrada_lote" and gatilho_lote:
        for m in session.exec(_da_fazenda(select(MovimentoLote).where(MovimentoLote.lote_destino == gatilho_lote), MovimentoLote)).all():
            saida.append((m.numero_matriz, _aplicar_offset(m.data_movimento)))
    elif gatilho == "novilha_apta" and gatilho_idade_meses:
        # Este gatilho NÃO é a aptidão reprodutiva da regra 7
        # (`estado_reprodutivo.classificar_animal`, idade_apta_min_meses ∧
        # peso_apta_min). É "a novilha atingiu a idade-alvo que VOCÊ
        # configurou" — o rótulo da tela é literalmente "Aptidão (novilha
        # atingir certa idade)" (`CadastroSanitario.tsx`), o cadastro EXIGE
        # `gatilho_idade_meses` (`cadastro/sanitario.py`) e a semente do
        # sistema traz Brucelose RB51 e a Primovacinação reprodutiva em 13
        # meses — abaixo do `idade_apta_min_meses()` padrão de 15. Amarrar
        # este gatilho aos parâmetros de aptidão sobrescreveria a idade
        # configurada pelo produtor e faria os dois eventos semeados nunca
        # serem agendados. Peso também não entra: fazenda que não pesa
        # perderia o gatilho inteiro, e a vacina de brucelose é obrigatória.
        #
        # O que É defeito e está corrigido aqui: o filtro antigo era só
        # "fêmea ativa com data de nascimento", então agendava manejo de
        # NOVILHA para vaca que já pariu, e para animal marcado a descartar
        # (que `models/animais.py` promete tirar das ações de manejo).
        matriz_com_parto = {
            p.numero_matriz
            for p in session.exec(_da_fazenda(select(Parto).where(Parto.numero_matriz != None), Parto)).all()  # noqa: E711
        }
        for a in session.exec(
            _da_fazenda(select(Animal).where(Animal.sexo == "F", Animal.ativo == True, Animal.data_nasc != None), Animal)  # noqa: E711,E712
        ).all():
            if a.numero in matriz_com_parto or a.a_descartar:
                continue
            saida.append((a.numero, _aplicar_offset(_somar_meses(a.data_nasc, gatilho_idade_meses))))
    elif gatilho == "desmama":
        dia_desmama, _ = _limiares_categoria(session, fazenda_id)
        for a in session.exec(_da_fazenda(select(Animal).where(Animal.data_nasc != None), Animal)).all():  # noqa: E711
            saida.append((a.numero, _aplicar_offset(a.data_nasc + timedelta(days=dia_desmama))))
    elif gatilho == "mudanca_recria":
        _, dia_recria = _limiares_categoria(session, fazenda_id)
        for a in session.exec(_da_fazenda(select(Animal).where(Animal.data_nasc != None), Animal)).all():  # noqa: E711
            saida.append((a.numero, _aplicar_offset(a.data_nasc + timedelta(days=dia_recria))))
    elif gatilho == "inseminacao":
        for s in session.exec(_da_fazenda(select(Servico).where(Servico.data_servico != None), Servico)).all():  # noqa: E711
            saida.append((s.numero_matriz, _aplicar_offset(s.data_servico)))
    elif gatilho == "gestacao_confirmada":
        # `data_perda_prenhez.is_(None)` — uma prenhez que já se perdeu (manual
        # ou automática por reinseminação, ver fazenda.rules.perda_prenhez)
        # não confirma gestação nenhuma; sem o filtro, o evento (ex.: uma
        # vacina de gestante) continuava sendo sugerido para uma vaca que já
        # não está mais prenha.
        for s in session.exec(
            _da_fazenda(
                select(Servico).where(Servico.diagnostico == "POSITIVO", Servico.data_perda_prenhez.is_(None)),
                Servico,
            )
        ).all():
            base = s.data_diagnostico or s.data_servico
            if base:
                saida.append((s.numero_matriz, _aplicar_offset(base)))
    elif gatilho == "mudanca_pre_parto":
        limite = pre_parto_max()
        # Mesmo filtro de perda de prenhez do gatilho acima — sem ele, uma
        # vaca que perdeu a prenhez (com ou sem nova IA já lançada) continuava
        # recebendo a sugestão de mudar para o lote de pré-parto, o pedido
        # específico do produtor que este módulo existe para atender.
        for s in session.exec(
            _da_fazenda(
                select(Servico).where(
                    Servico.diagnostico == "POSITIVO", Servico.data_servico != None,  # noqa: E711
                    Servico.data_perda_prenhez.is_(None),
                ),
                Servico,
            )
        ).all():
            prevista = calcular_parto_provavel(s.data_servico, s.raca_matriz).data_parto_provavel
            saida.append((s.numero_matriz, _aplicar_offset(prevista - timedelta(days=limite))))

    # Filtro único no fim (não em cada ramo, pra cobrir gatilho novo por
    # igual): nunca sugere animal já baixado (vendido/morto/etc.) — pendência
    # de vacina pra quem não está mais no rebanho não faz sentido — nem fora
    # do sexo-alvo do evento, quando um está definido (ex.: Brucelose B19 só
    # em fêmeas; macho não recebe).
    animais = (
        animais_cache if animais_cache is not None
        else {a.numero: a for a in session.exec(_da_fazenda(select(Animal), Animal)).all()}
    )

    def elegivel(numero: str) -> bool:
        a = animais.get(numero)
        if not a or not a.ativo:
            return False
        if sexo_alvo and a.sexo != sexo_alvo:
            return False
        return True

    return [(n, d) for n, d in saida if elegivel(n)]


def _eventos_calendario_agenda(session: Session, hoje: date, realizados: set[str], fazenda_id: int | None) -> list[dict]:
    """
    Eventos da Agenda vindos das REGRAS do calendário sanitário (preventivo).
    Antes, essas regras só apareciam na tela de calendário e nunca na Agenda —
    então um exame lançado "para hoje" não gerava pendência nem permitia baixa.
    Aqui cada regra ativa projeta suas ocorrências na janela e vira pendência.
    Exame (categoria_preventiva == "exame") não tem produto/baixa de estoque:
    a baixa apenas marca como realizado (e permite lançar o financeiro).
    """
    query_regras = (
        # usa_cronograma=True fica de fora daqui — essas regras geram suas
        # próprias pendências pelo workflow do cronograma (ver
        # rules.cronograma_sanitario.eventos_agenda), nunca as duas ao mesmo
        # tempo para a mesma regra.
        select(CalendarioSanitario).where(CalendarioSanitario.ativo == True).where(CalendarioSanitario.usa_cronograma == False)  # noqa: E712
    )
    if fazenda_id is not None:
        query_regras = query_regras.where(CalendarioSanitario.fazenda_id == fazenda_id)
    regras = session.exec(query_regras).all()
    if not regras:
        return []
    query_eventos = select(EventoSanitario)
    if fazenda_id is not None:
        query_eventos = query_eventos.where(EventoSanitario.fazenda_id == fazenda_id)
    eventos = {e.id: e for e in session.exec(query_eventos).all()}
    # Calculado uma vez para todas as regras do loop abaixo — ver o
    # comentário de `_ocorrencias_recorrentes`: sem isso, cada regra ativa
    # relia numa nova leitura do parâmetro (sessão de banco própria).
    janela_passado = janela_eventos_sanitarios_passado()
    janela_futuro = janela_eventos_sanitarios_futuro()
    saida: list[dict] = []
    for c in regras:
        ev = eventos.get(c.evento_sanitario_id)
        nome = ev.nome if ev else "Evento sanitário"
        categoria = (ev.categoria_preventiva if ev else None) or None
        eh_exame = categoria == "exame"
        alvo = c.categoria_alvo or "rebanho"
        for d in _ocorrencias_recorrentes(c.data_evento, c.frequencia_valor, c.frequencia_unidade, hoje, janela_passado, janela_futuro):
            eid = f"calendario_sanitario_{c.id}__{d.isoformat()}"
            if eid in realizados:
                continue
            desc = f"{nome} — {alvo}"
            if c.produto and not eh_exame:
                desc += f" — {c.produto}"
            saida.append({
                "id": eid,
                "data": d.isoformat(),
                "categoria": "sanidade",
                "descricao": desc,
                "numero_animal": None,
                "observacao": (
                    "Exame preventivo — dê baixa quando realizado (e lance o financeiro, se houver custo)."
                    if eh_exame else "Dê baixa para gerar a aplicação e a saída de estoque."
                ),
                "fonte": "auto",
                "cor": "var(--dourado)",
                "ref": None,
                "tipo": "calendario_sanitario",
                "produto": None if eh_exame else c.produto,
                "dose": None,
                "unidade": None if eh_exame else c.unidade,
                "via": None,
                "categoria_alvo": c.categoria_alvo,
                "categoria_preventiva": categoria,
                "principio_ativo_id": None if eh_exame else c.principio_ativo_id,
                "veterinario": c.veterinario,
                "calendario_id": c.id,
                "evento_sanitario_id": c.evento_sanitario_id,
            })
            # Exame: aviso à parte N dias antes, para confirmar com o veterinário
            # (distinto da pendência do próprio dia do exame).
            if eh_exame and ev and ev.agenda_dias_antes:
                d_aviso = d - timedelta(days=ev.agenda_dias_antes)
                eid_aviso = f"calendario_sanitario_{c.id}__{d.isoformat()}__aviso"
                if eid_aviso in realizados:
                    continue
                saida.append({
                    "id": eid_aviso,
                    "data": d_aviso.isoformat(),
                    "categoria": "sanidade",
                    "descricao": f"Confirmar com o veterinário — {nome} previsto para {d.strftime('%d/%m/%Y')} ({alvo})",
                    "numero_animal": None,
                    "observacao": f"Aviso {ev.agenda_dias_antes} dias antes do exame — combine a visita do veterinário.",
                    "fonte": "auto", "cor": "var(--amber)", "ref": None,
                    "tipo": "aviso_exame_veterinario",
                    "categoria_alvo": c.categoria_alvo, "veterinario": c.veterinario,
                    "calendario_id": c.id, "evento_sanitario_id": c.evento_sanitario_id,
                })
    return saida


def _base(
    ev: EventoSanitario, quando: date, numero: str | None, sufixo: str, principio_ativo_id: int | None,
    hoje: date | None = None, janela_fim: date | None = None,
) -> dict:
    alvo = f"matriz {numero}" if numero else (ev.categoria_alvo or "rebanho")
    observacao = "Dê baixa para gerar a aplicação e a saída de estoque."
    # "Notificar urgência" — mesmo texto de alerta em ambos os lugares que
    # mostram esta pendência (Agenda e o relatório de exploração em
    # sanidade.py), pra não descrever o mesmo prazo de dois jeitos.
    dias_para_fechar = None
    if janela_fim is not None and hoje is not None:
        dias_para_fechar = (janela_fim - hoje).days
        if ev.acao_fora_janela == "notificar" and dias_para_fechar <= 7:
            observacao = f"Janela de aplicação fecha em {dias_para_fechar} dia(s) ({janela_fim.isoformat()}) — dê baixa logo. " + observacao
    return {
        "id": f"evento_sanitario_{ev.id}__{numero or 'rebanho'}__{sufixo}",
        "data": quando.isoformat(),
        "categoria": "sanidade",
        "descricao": f"{ev.nome} — {alvo}" + (f" — {ev.produto_padrao}" if ev.produto_padrao else ""),
        "numero_animal": numero,
        "observacao": observacao,
        "fonte": "auto",
        "cor": "var(--dourado)",
        "ref": None,
        "tipo": "evento_sanitario",
        "produto": ev.produto_padrao,
        "dose": ev.dose_padrao,
        "unidade": ev.unidade_padrao,
        "via": ev.via_padrao,
        "categoria_alvo": ev.categoria_alvo,
        "principio_ativo_id": principio_ativo_id,
        "evento_sanitario_id": ev.id,
        "janela_fim": janela_fim.isoformat() if janela_fim else None,
        "dias_para_fechar_janela": dias_para_fechar,
        "acao_fora_janela": ev.acao_fora_janela if janela_fim else None,
    }


def eventos_agenda(session: Session, hoje: date, realizados: set[str], fazenda_id: int | None = None) -> list[dict]:
    """Todos os eventos da Agenda vindos dos eventos sanitários agendados."""
    query_todos_eventos = select(EventoSanitario)
    if fazenda_id is not None:
        query_todos_eventos = query_todos_eventos.where(EventoSanitario.fazenda_id == fazenda_id)
    todos_eventos = {e.id: e for e in session.exec(query_todos_eventos).all()}
    eventos = [
        e for e in todos_eventos.values()
        if e.ativo and e.tipo_agendamento != "nenhum"
    ]

    # Eventos ligados a uma regra do calendário sanitário com
    # usa_cronograma=True não geram mais a pendência antiga de "aplicar
    # agora" — o animal entra na trilha do cronograma (ver
    # rules.cronograma_sanitario), que pergunta se ele entra na lista de
    # espera em vez de cobrar aplicação imediata (ver eventos_agenda_cronograma
    # em routers/agenda.py). Um evento sem regra vinculada (ou com regra
    # usa_cronograma=False) continua exatamente como sempre.
    query_calendarios_cron = select(CalendarioSanitario).where(CalendarioSanitario.usa_cronograma == True)  # noqa: E712
    if fazenda_id is not None:
        query_calendarios_cron = query_calendarios_cron.where(CalendarioSanitario.fazenda_id == fazenda_id)
    calendarios_cronograma = {c.evento_sanitario_id: c for c in session.exec(query_calendarios_cron).all()}

    # Duplicidade real de produção (verificação E2E de 12/09/2026): o wizard
    # de cadastro (FormCalendarioSanitario.tsx::salvar) grava a periodicidade
    # em DOIS lugares ao mesmo tempo para a mesma regra — tipo_agendamento=
    # "epoca" + data_primeiro/frequencia_* no próprio EventoSanitario, E um
    # CalendarioSanitario com as mesmas frequencia_valor/unidade. O branch
    # "epoca" abaixo materializava por EventoSanitario (id "evento_sanitario_
    # …", sem saber de categoria_alvo, sempre "— rebanho") AO MESMO TEMPO que
    # `_eventos_calendario_agenda` materializava pela regra (id "calendario_
    # sanitario_…", com a categoria_alvo certa) — duas pendências, mesmo dia,
    # textos diferentes, para o mesmo evento. Mesmo raciocínio já aplicado
    # acima para usa_cronograma=True: existindo QUALQUER regra ativa para este
    # evento, ela é a única fonte de periodicidade — o "epoca" aqui materializa
    # só os eventos legados sem regra nenhuma (nunca migrados para o calendário).
    query_calendarios_ativos = select(CalendarioSanitario).where(CalendarioSanitario.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_calendarios_ativos = query_calendarios_ativos.where(CalendarioSanitario.fazenda_id == fazenda_id)
    eventos_com_regra_ativa = {c.evento_sanitario_id for c in session.exec(query_calendarios_ativos).all()}

    # Resolve o princípio ativo do produto padrão (nome do item de estoque) —
    # alimenta o seletor "Princípio ativo" já pré-preenchido na Agenda, do
    # mesmo jeito que as regras do calendário sanitário já fazem.
    query_estoque = select(Estoque)
    if fazenda_id is not None:
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)
    principio_por_nome = {
        e.nome: e.principio_ativo_id for e in session.exec(query_estoque).all()
    }

    # Pré-carrega Sanidade por animal (produto minúsculo, data) para deduplicar:
    # se já foi aplicado depois do gatilho, o evento some da Agenda.
    query_sanidade = select(Sanidade)
    if fazenda_id is not None:
        query_sanidade = query_sanidade.where(Sanidade.fazenda_id == fazenda_id)
    aplic_por_animal: dict[str, list[tuple[str, date | None]]] = {}
    for s in session.exec(query_sanidade).all():
        aplic_por_animal.setdefault(s.numero_matriz, []).append(((s.produto or "").strip().lower(), s.data_aplicacao))

    def ja_aplicado(numero: str, produto: str | None, desde: date) -> bool:
        if not produto:
            return False
        alvo = produto.strip().lower()
        return any(p == alvo and dt and dt >= desde for p, dt in aplic_por_animal.get(numero, []))

    def ja_aplicado_alguma_vez(numero: str, produto: str | None) -> bool:
        if not produto:
            return False
        alvo = produto.strip().lower()
        return any(p == alvo and dt for p, dt in aplic_por_animal.get(numero, []))

    def bloqueado_pela_condicao(ev: EventoSanitario, numero: str) -> bool:
        """Alternativas mutuamente exclusivas (ex.: Brucelose B19 × RB51): não
        agenda ESTE evento se o animal já recebeu o evento apontado em
        condicao_evento_id, em qualquer data (não só desde o gatilho atual)."""
        if not ev.condicao_evento_id:
            return False
        condicao = todos_eventos.get(ev.condicao_evento_id)
        if not condicao:
            return False
        return ja_aplicado_alguma_vez(numero, condicao.produto_padrao)

    # Cache único de Animal (numero -> objeto), reaproveitado em toda chamada
    # de _datas_gatilho abaixo. Sem isso, CADA evento sanitário "por evento"
    # (nascimento, desmama, entrada em lote, novilha apta…) relia numa leitura
    # nova da tabela Animal inteira só para o filtro final de elegibilidade —
    # numa fazenda com uma dúzia de eventos cadastrados (comum: uma vacina por
    # doença), isso multiplicava a mesma consulta pesada uma dúzia de vezes a
    # cada carregamento da Agenda.
    query_animais_gatilho = select(Animal)
    if fazenda_id is not None:
        query_animais_gatilho = query_animais_gatilho.where(Animal.fazenda_id == fazenda_id)
    animais_cache = {a.numero: a for a in session.exec(query_animais_gatilho).all()}

    # Mesmo raciocínio do cache de Animal acima, para os dois parâmetros de
    # janela — ver o comentário de `_ocorrencias_recorrentes`. Calculados uma
    # vez para todos os eventos deste loop (época e por evento), em vez de
    # reler `janela_eventos_sanitarios_passado/futuro` (cada leitura abre uma
    # sessão de banco própria — ver `_linha` em rules/parametros.py) a cada
    # evento sanitário cadastrado.
    janela_passado = janela_eventos_sanitarios_passado()
    janela_futuro = janela_eventos_sanitarios_futuro()

    saida: list[dict] = []

    for ev in eventos:
        # A janela de aplicação (quando cadastrada) É a fonte real de quando
        # o item entra na Agenda — substitui "offset_dias" (mantido só como
        # fallback pros eventos antigos que nunca configuraram janela, sem
        # quebrar nada já cadastrado). Ver conversa com o usuário 2026-09-10:
        # antes os dois campos pareciam duplicados na tela porque de fato
        # calculavam a mesma coisa por dois caminhos diferentes — "Dias após
        # o gatilho" nunca soube de meses, só de dias.
        tem_janela_de = ev.janela_de_valor is not None and ev.janela_de_unidade is not None
        if tem_janela_de:
            offset_valor, offset_unidade = ev.janela_de_valor, ev.janela_de_unidade
        else:
            offset_valor, offset_unidade = (ev.offset_dias or 0), "dias"
        principio_ativo_id = principio_por_nome.get(ev.produto_padrao) if ev.produto_padrao else None

        if ev.tipo_agendamento == "epoca":
            if ev.id in eventos_com_regra_ativa:
                continue
            for d in _ocorrencias_epoca(ev, hoje, janela_passado, janela_futuro):
                evt = _base(ev, d, None, d.isoformat(), principio_ativo_id)
                if evt["id"] not in realizados:
                    saida.append(evt)
            continue

        if ev.tipo_agendamento != "evento" or not ev.gatilho:
            continue

        minimo = hoje - timedelta(days=janela_passado)
        limite = hoje + timedelta(days=janela_futuro)
        gatilhos = _datas_gatilho(
            session, ev.gatilho, ev.gatilho_lote, ev.gatilho_idade_meses, offset_valor, ev.sexo_alvo, fazenda_id,
            animais_cache=animais_cache, offset_unidade=offset_unidade,
        )

        # Fim da janela por animal — só calculado quando a janela está
        # completa (de E até cadastrados). Usado tanto pra "sair" (encerra a
        # pendência passado o fim, vira lacuna permanente) quanto pra
        # "notificar" (aviso de urgência perto de fechar) — "manter" não
        # precisa disto, é o comportamento de sempre (nunca expira sozinho).
        fins_janela: dict[str, date] = {}
        tem_janela_completa = tem_janela_de and ev.janela_ate_valor is not None and ev.janela_ate_unidade is not None
        if tem_janela_completa:
            fins_janela = dict(_datas_gatilho(
                session, ev.gatilho, ev.gatilho_lote, ev.gatilho_idade_meses, ev.janela_ate_valor, ev.sexo_alvo, fazenda_id,
                animais_cache=animais_cache, offset_unidade=ev.janela_ate_unidade,
            ))

        calendario_cron = calendarios_cronograma.get(ev.id)

        vistos: set[str] = set()
        numeros_para_cronograma: list[str] = []
        for numero, quando in gatilhos:
            if not (minimo <= quando <= limite):
                continue
            if numero in vistos:  # um gatilho por animal por evento
                continue
            if ja_aplicado(numero, ev.produto_padrao, quando):
                continue
            if bloqueado_pela_condicao(ev, numero):
                continue
            janela_fim = fins_janela.get(numero) if fins_janela else None
            if janela_fim is not None and ev.acao_fora_janela == "sair" and hoje > janela_fim:
                vistos.add(numero)
                continue
            if calendario_cron:
                # Trilha do cronograma: só sugere quando o animal JÁ bateu o
                # critério (não antecipa animais que ainda vão chegar lá) —
                # o funcionário decide incluir/excluir pela Agenda.
                if quando <= hoje:
                    vistos.add(numero)
                    numeros_para_cronograma.append(numero)
                continue
            evt = _base(ev, quando, numero, quando.isoformat(), principio_ativo_id, hoje=hoje, janela_fim=janela_fim)
            if evt["id"] in realizados:
                continue
            vistos.add(numero)
            saida.append(evt)

        # Um SELECT+INSERT em lote por evento sanitário em vez de um por
        # animal — ver fazenda.rules.cronograma_sanitario.sugerir_animais_em_lote.
        if calendario_cron and numeros_para_cronograma:
            from fazenda.rules.cronograma_sanitario import sugerir_animais_em_lote
            sugerir_animais_em_lote(session, calendario_cron, numeros_para_cronograma, hoje)

    # Regras do calendário sanitário (preventivo) também viram pendências.
    saida.extend(_eventos_calendario_agenda(session, hoje, realizados, fazenda_id))

    return saida
