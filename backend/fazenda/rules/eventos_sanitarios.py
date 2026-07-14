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

from fazenda.models import Animal, CalendarioSanitario, EventoSanitario, MovimentoLote, Parto, Sanidade, Secagem
from fazenda.rules.calendario_sanitario import _somar_meses, proxima_ocorrencia

# Janela de geração: um gatilho recente (até 120 dias atrás) ainda pendura na
# Agenda; a projeção por época vai até 180 dias à frente.
JANELA_PASSADO = 120
HORIZONTE_FUTURO = 180


def _ocorrencias_recorrentes(base: date, valor: int | None, unidade: str | None, hoje: date) -> list[date]:
    """Datas da recorrência dentro da janela [hoje-120, hoje+180]."""
    if not (base and valor and unidade):
        return []
    minimo = hoje - timedelta(days=JANELA_PASSADO)
    limite = hoje + timedelta(days=HORIZONTE_FUTURO)
    saida: list[date] = []
    d = base
    guarda = 0
    while d <= limite and guarda < 3000:
        if d >= minimo:
            saida.append(d)
        d = proxima_ocorrencia(d, valor, unidade)
        guarda += 1
    return saida


def _ocorrencias_epoca(ev: EventoSanitario, hoje: date) -> list[date]:
    return _ocorrencias_recorrentes(ev.data_primeiro, ev.frequencia_valor, ev.frequencia_unidade, hoje)


def _eventos_calendario_agenda(session: Session, hoje: date, realizados: set[str]) -> list[dict]:
    """
    Eventos da Agenda vindos das REGRAS do calendário sanitário (preventivo).
    Antes, essas regras só apareciam na tela de calendário e nunca na Agenda —
    então um exame lançado "para hoje" não gerava pendência nem permitia baixa.
    Aqui cada regra ativa projeta suas ocorrências na janela e vira pendência.
    Exame (categoria_preventiva == "exame") não tem produto/baixa de estoque:
    a baixa apenas marca como realizado (e permite lançar o financeiro).
    """
    regras = session.exec(
        select(CalendarioSanitario).where(CalendarioSanitario.ativo == True)  # noqa: E712
    ).all()
    if not regras:
        return []
    eventos = {e.id: e for e in session.exec(select(EventoSanitario)).all()}
    saida: list[dict] = []
    for c in regras:
        ev = eventos.get(c.evento_sanitario_id)
        nome = ev.nome if ev else "Evento sanitário"
        categoria = (ev.categoria_preventiva if ev else None) or None
        eh_exame = categoria == "exame"
        alvo = c.categoria_alvo or "rebanho"
        for d in _ocorrencias_recorrentes(c.data_evento, c.frequencia_valor, c.frequencia_unidade, hoje):
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


def _base(ev: EventoSanitario, quando: date, numero: str | None, sufixo: str) -> dict:
    alvo = f"matriz {numero}" if numero else (ev.categoria_alvo or "rebanho")
    return {
        "id": f"evento_sanitario_{ev.id}__{numero or 'rebanho'}__{sufixo}",
        "data": quando.isoformat(),
        "categoria": "sanidade",
        "descricao": f"{ev.nome} — {alvo}" + (f" — {ev.produto_padrao}" if ev.produto_padrao else ""),
        "numero_animal": numero,
        "observacao": "Dê baixa para gerar a aplicação e a saída de estoque.",
        "fonte": "auto",
        "cor": "var(--dourado)",
        "ref": None,
        "tipo": "evento_sanitario",
        "produto": ev.produto_padrao,
        "dose": ev.dose_padrao,
        "unidade": ev.unidade_padrao,
        "via": ev.via_padrao,
        "categoria_alvo": ev.categoria_alvo,
        "evento_sanitario_id": ev.id,
    }


def eventos_agenda(session: Session, hoje: date, realizados: set[str]) -> list[dict]:
    """Todos os eventos da Agenda vindos dos eventos sanitários agendados."""
    eventos = session.exec(
        select(EventoSanitario).where(
            EventoSanitario.ativo == True,  # noqa: E712
            EventoSanitario.tipo_agendamento != "nenhum",
        )
    ).all()

    # Pré-carrega Sanidade por animal (produto minúsculo, data) para deduplicar:
    # se já foi aplicado depois do gatilho, o evento some da Agenda.
    aplic_por_animal: dict[str, list[tuple[str, date | None]]] = {}
    for s in session.exec(select(Sanidade)).all():
        aplic_por_animal.setdefault(s.numero_matriz, []).append(((s.produto or "").strip().lower(), s.data_aplicacao))

    def ja_aplicado(numero: str, produto: str | None, desde: date) -> bool:
        if not produto:
            return False
        alvo = produto.strip().lower()
        return any(p == alvo and dt and dt >= desde for p, dt in aplic_por_animal.get(numero, []))

    saida: list[dict] = []

    for ev in eventos:
        offset = ev.offset_dias or 0

        if ev.tipo_agendamento == "epoca":
            for d in _ocorrencias_epoca(ev, hoje):
                evt = _base(ev, d, None, d.isoformat())
                if evt["id"] not in realizados:
                    saida.append(evt)
            continue

        if ev.tipo_agendamento != "evento" or not ev.gatilho:
            continue

        minimo = hoje - timedelta(days=JANELA_PASSADO)
        limite = hoje + timedelta(days=HORIZONTE_FUTURO)
        # Lista de (numero, data_gatilho).
        gatilhos: list[tuple[str, date]] = []

        if ev.gatilho == "nascimento":
            for a in session.exec(select(Animal).where(Animal.data_nasc != None)).all():  # noqa: E711
                gatilhos.append((a.numero, a.data_nasc + timedelta(days=offset)))
        elif ev.gatilho == "secagem":
            for s in session.exec(select(Secagem)).all():
                gatilhos.append((s.numero_matriz, s.data_secagem + timedelta(days=offset)))
        elif ev.gatilho == "parto":
            for p in session.exec(select(Parto).where(Parto.data_parto != None)).all():  # noqa: E711
                gatilhos.append((p.numero_matriz, p.data_parto + timedelta(days=offset)))
        elif ev.gatilho == "entrada_lote" and ev.gatilho_lote:
            for m in session.exec(select(MovimentoLote).where(MovimentoLote.lote_destino == ev.gatilho_lote)).all():
                gatilhos.append((m.numero_matriz, m.data_movimento + timedelta(days=offset)))
        elif ev.gatilho == "novilha_apta" and ev.gatilho_idade_meses:
            for a in session.exec(
                select(Animal).where(Animal.sexo == "F", Animal.ativo == True, Animal.data_nasc != None)  # noqa: E711,E712
            ).all():
                apta = _somar_meses(a.data_nasc, ev.gatilho_idade_meses) + timedelta(days=offset)
                gatilhos.append((a.numero, apta))

        vistos: set[str] = set()
        for numero, quando in gatilhos:
            if not (minimo <= quando <= limite):
                continue
            if numero in vistos:  # um gatilho por animal por evento
                continue
            if ja_aplicado(numero, ev.produto_padrao, quando):
                continue
            evt = _base(ev, quando, numero, quando.isoformat())
            if evt["id"] in realizados:
                continue
            vistos.add(numero)
            saida.append(evt)

    # Regras do calendário sanitário (preventivo) também viram pendências.
    saida.extend(_eventos_calendario_agenda(session, hoje, realizados))

    return saida
