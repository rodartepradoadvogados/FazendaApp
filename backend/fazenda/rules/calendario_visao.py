"""
Card CALENDÁRIO (Sanidade > Preventiva > Calendário Sanitário) — projeta as
próximas ocorrências das regras do calendário sanitário (vacina/exame) num
intervalo de datas, com uma estimativa de quantos animais entram em cada uma,
e agrupa ocorrências próximas no tempo para sugerir quando vale a pena chamar
o veterinário (várias vacinas pequenas, juntas, viram uma leva grande).

Fonte da contagem de animais, por tipo de regra:
  • usa_cronograma=True — contagem REAL (sugerido+incluído) do cronograma em
    aberto, já rastreado por fazenda.rules.cronograma_sanitario.
  • por evento de vida (gatilho) — contagem REAL de animais que batem o
    gatilho na janela (mesma lógica do relatório de eventos de vida).
  • por época (recorrência de rebanho, sem rastreio por animal) — não há como
    saber ao certo quem vai entrar; em vez de adivinhar, usamos quantos
    animais entraram na ÚLTIMA aplicação real desse produto, como referência
    histórica (marcada como estimativa).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from fazenda.models import (
    CalendarioSanitario, CronogramaSanitario, CronogramaSanitarioAnimal, EventoSanitario, Pessoa, Sanidade,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.calendario_sanitario import proxima_ocorrencia
from fazenda.rules.cronograma_sanitario import cronograma_aberto
from fazenda.rules.eventos_sanitarios import _datas_gatilho
from fazenda.rules.parametros import cronograma_sanitario_janela_agrupamento_dias, cronograma_sanitario_min_animais_agrupamento


def _ocorrencias_no_intervalo(base: date, valor: int | None, unidade: str | None, ini: date, fim: date) -> list[date]:
    if not (base and valor and unidade):
        return []
    saida: list[date] = []
    d = base
    guarda = 0
    while d <= fim and guarda < 3000:
        if d >= ini:
            saida.append(d)
        d = proxima_ocorrencia(d, valor, unidade)
        guarda += 1
    return saida


def _ultima_aplicacao_por_produto(session: Session, fazenda_id: int | None) -> dict[str, int]:
    """produto (minúsculo) -> quantos animais distintos na aplicação mais
    recente desse produto (Sanidade natureza=preventivo)."""
    query = select(Sanidade).where(Sanidade.natureza == "preventivo", Sanidade.data_aplicacao.is_not(None))
    if fazenda_id is not None:
        query = query.where(Sanidade.fazenda_id == fazenda_id)
    ultima_data: dict[str, date] = {}
    animais_na_data: dict[tuple[str, date], set[str]] = {}
    for r in session.exec(query).all():
        chave = (r.produto or "").strip().lower()
        if not chave:
            continue
        if not ultima_data.get(chave) or r.data_aplicacao > ultima_data[chave]:
            ultima_data[chave] = r.data_aplicacao
        animais_na_data.setdefault((chave, r.data_aplicacao), set()).add(r.numero_matriz)
    return {chave: len(animais_na_data.get((chave, data), set())) for chave, data in ultima_data.items()}


def montar_calendario_visual(session: Session, fazenda_id: int | None, data_inicio: date, data_fim: date) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    min_animais = cronograma_sanitario_min_animais_agrupamento()
    janela_dias = cronograma_sanitario_janela_agrupamento_dias()

    query = select(CalendarioSanitario).where(CalendarioSanitario.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(CalendarioSanitario.fazenda_id == fazenda_id)
    regras = session.exec(query).all()
    eventos = {e.id: e for e in session.exec(select(EventoSanitario)).all()}
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    ultimas_aplicacoes = _ultima_aplicacao_por_produto(session, fazenda_id)

    def _cronograma_info(cron: CronogramaSanitario) -> tuple[dict, int]:
        animais = session.exec(
            select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
        ).all()
        contagem = {"sugerido": 0, "incluido": 0, "excluido": 0, "aplicado": 0}
        for a in animais:
            contagem[a.status] = contagem.get(a.status, 0) + 1
        info = {
            "id": cron.id, "status": cron.status, "modo_execucao": cron.modo_execucao,
            "veterinario_nome": pessoas.get(cron.veterinario_pessoa_id) if cron.veterinario_pessoa_id else None,
            "animais_contagem": contagem,
        }
        return info, contagem["sugerido"] + contagem["incluido"]

    ocorrencias: list[dict] = []
    for c in regras:
        ev = eventos.get(c.evento_sanitario_id)
        if not ev:
            continue
        base = {
            "calendario_sanitario_id": c.id, "evento_sanitario_id": ev.id, "evento_sanitario_nome": ev.nome,
            "categoria_alvo": c.categoria_alvo, "categoria_preventiva": ev.categoria_preventiva,
            "servico_financeiro": ev.servico_financeiro, "usa_cronograma": c.usa_cronograma,
        }

        if c.usa_cronograma:
            cron = cronograma_aberto(session, c)
            if not (data_inicio <= cron.data_evento <= data_fim):
                continue
            cron_info, animais = _cronograma_info(cron)
            ocorrencias.append({
                **base, "data": cron.data_evento.isoformat(), "animais": animais, "estimativa": False,
                "estimativa_base": None, "cronograma": cron_info,
            })
            continue

        if ev.tipo_agendamento == "evento" and ev.gatilho:
            gatilhos = _datas_gatilho(session, ev.gatilho, ev.gatilho_lote, ev.gatilho_idade_meses, ev.offset_dias or 0)
            por_data: dict[date, set[str]] = {}
            for numero, quando in gatilhos:
                if data_inicio <= quando <= data_fim:
                    por_data.setdefault(quando, set()).add(numero)
            for quando, numeros in por_data.items():
                ocorrencias.append({
                    **base, "data": quando.isoformat(), "animais": len(numeros), "estimativa": False,
                    "estimativa_base": None, "cronograma": None,
                })
            continue

        # Por época — recorrência de rebanho, sem rastreio por animal.
        for quando in _ocorrencias_no_intervalo(c.data_evento, c.frequencia_valor, c.frequencia_unidade, data_inicio, data_fim):
            animais = ultimas_aplicacoes.get((c.produto or "").strip().lower())
            ocorrencias.append({
                **base, "data": quando.isoformat(), "animais": animais, "estimativa": animais is not None,
                "estimativa_base": "ultima_aplicacao" if animais is not None else None, "cronograma": None,
            })

    ocorrencias.sort(key=lambda o: o["data"])

    janelas: list[dict] = []
    cluster: list[dict] | None = None
    ancora: date | None = None
    for o in ocorrencias:
        data_o = date.fromisoformat(o["data"])
        if cluster is not None and ancora is not None and (data_o - ancora).days <= janela_dias:
            cluster.append(o)
            continue
        if cluster is not None:
            janelas.append(cluster)
        cluster = [o]
        ancora = data_o
    if cluster:
        janelas.append(cluster)

    saida = []
    for eventos_cluster in janelas:
        datas = [date.fromisoformat(o["data"]) for o in eventos_cluster]
        animais_total = sum(o["animais"] for o in eventos_cluster if o["animais"] is not None)
        saida.append({
            "data_inicio": min(datas).isoformat(), "data_fim": max(datas).isoformat(),
            "animais_total": animais_total,
            "tem_estimativa": any(o["estimativa"] for o in eventos_cluster),
            "sugerir_veterinario": animais_total >= min_animais,
            "eventos": eventos_cluster,
        })
    return {"janelas": saida, "min_animais_agrupamento": min_animais, "janela_agrupamento_dias": janela_dias}
