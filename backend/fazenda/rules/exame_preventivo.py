"""
Exame preventivo no aplicar unico (fatia 9b do planejamento unificado — docs/agents/
auditoria-preventivo-agenda/planejamento/06-planejamento-unificado.md; decisoes clinicas em
08-correcoes-fluxo-R5.md e 09-correcoes-R6.md).

`aplicacao_preventiva.aplicar` entrega aqui o agendamento cujo protocolo e um EXAME
(`EventoSanitario.categoria_preventiva == "exame"`). O exame tem fases:

  * tuberculina (TB): "inoculacao" (data/hora, veterinario habilitado, frasco, baixa de estoque;
    NAO e um registro concluido: marca a leitura para 72 h depois, na Agenda) e "leitura"
    (resultado por animal — negativo / reagente / inconclusivo —, espessura da pele em mm, tipo de
    teste, laudo; janela de 72-96 h sinalizada e leitura antes de 72 h so com justificativa).
    A leitura e o registro concluido ("Exame realizado");
  * exame sem leitura (brucelose e outros): "coleta", uma etapa so, com laudo.

Reagente: o animal sai dos demais agendamentos/listas de espera e nao entra em novos, fica "a
descartar", o banner persiste (com o registro da notificacao: quem/quando) e o comprovante e
bloqueado so para ele. Inconclusivo: reteste 60 dias depois, na lista de espera do proprio
protocolo ("Reteste atrasado" quando passa da data).

Nada e apagado: desfazer/estornar revertem estoque, resultado, marcas e o agendamento e a
aplicacao original fica como "estornada".
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta

from sqlmodel import Session, select

from fazenda.models import (
    Animal, CalendarioSanitario, CronogramaSanitario, CronogramaSanitarioAnimal, CronogramaSanitarioAplicacao,
    CronogramaSanitarioAplicacaoAnimal, EventoSanitario, ExameResultado, Fazenda, MovimentoEstoque,
)
from fazenda.rules import aplicacao_preventiva as ap_rules
from fazenda.rules.aplicacao_preventiva import AplicacaoError, registrar_log
from fazenda.rules.estoque_baixa import devolver as _estoque_devolver

TIPOS_TESTE = ["Cervical simples", "Cervical comparativo", "Prega caudal"]
RESULTADOS = ("negativo", "reagente", "inconclusivo")
# vocabulario do exame na fazenda (relatorios de Sanidade > Exames) <-> o do fluxo
_RESULTADO_EXAME = {"negativo": "negativo", "reagente": "positivo", "inconclusivo": "indefinido"}
RETESTE_DIAS = 60
LEITURA_HORAS = 72
LEITURA_LIMITE_HORAS = 96
ORIGEM_ESTOQUE = "exame_preventivo"
_RE_TB = re.compile(r"(tubercul|\bppd\b|\btb\b)")
_RE_BRUCELOSE = re.compile(r"brucel")
_ATIVOS = ("aberto", "agendado", "em_montagem")


# ───────────────────────────── classificacao ─────────────────────────────
def tipo_exame(evento: EventoSanitario | None, produto: str | None = None, doenca_nome: str | None = None) -> str:
    """'tuberculina' | 'brucelose' | 'outro' (pelo nome do protocolo, produto e doenca)."""
    texto = ap_rules._norm(" ".join(filter(None, [evento.nome if evento else None, produto, doenca_nome])))
    if _RE_TB.search(texto):
        return "tuberculina"
    if _RE_BRUCELOSE.search(texto):
        return "brucelose"
    return "outro"


def horas_ate_leitura(tipo: str) -> int:
    return LEITURA_HORAS if tipo == "tuberculina" else 0


def eh_exame(evento: EventoSanitario | None) -> bool:
    return bool(evento is not None and evento.categoria_preventiva == "exame")


def contexto_do_evento(session: Session, cal: CalendarioSanitario | None, evento: EventoSanitario | None) -> tuple[str, str | None, str]:
    """(produto, nome da doenca, tipo de exame) do protocolo."""
    produto = ((cal.produto if cal else None) or (evento.produto_padrao if evento else None) or "").strip() or None
    doenca_nome = None
    if evento is not None and evento.doenca_id:
        from fazenda.models import Doenca
        d = session.get(Doenca, evento.doenca_id)
        doenca_nome = d.nome if d else None
    return produto, doenca_nome, tipo_exame(evento, produto, doenca_nome)


def _hora_texto(hora: str | None) -> str:
    return hora if hora else "00:00"


def _dt(d: date, hora: str | None) -> datetime:
    h, m = _hora_texto(hora).split(":")
    return datetime.combine(d, time(int(h), int(m)))


def _iso(v) -> str | None:
    return v.isoformat() if v else None


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def inoculacao_ativa(session: Session, cron_id: int) -> CronogramaSanitarioAplicacao | None:
    return session.exec(
        select(CronogramaSanitarioAplicacao).where(CronogramaSanitarioAplicacao.cronograma_id == cron_id)
        .where(CronogramaSanitarioAplicacao.fase == "inoculacao").where(CronogramaSanitarioAplicacao.estado == "aplicada")
        .order_by(CronogramaSanitarioAplicacao.id.desc())
    ).first()


def fase_atual(session: Session, cron: CronogramaSanitario, tipo: str) -> str:
    """'coleta' (exame sem leitura) | 'inoculacao' | 'leitura' (ja inoculado, falta ler)."""
    if horas_ate_leitura(tipo) == 0:
        return "coleta"
    return "leitura" if inoculacao_ativa(session, cron.id) is not None else "inoculacao"


def fase_do_agendamento(session: Session, cron: CronogramaSanitario) -> str | None:
    """Fase do exame do agendamento (None para vacina/vermifugo)."""
    cal = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    ev = session.get(EventoSanitario, cal.evento_sanitario_id) if cal else None
    if not eh_exame(ev):
        return None
    return fase_atual(session, cron, contexto_do_evento(session, cal, ev)[2])


# ───────────────────────────── reagentes ─────────────────────────────
def animais_reagentes(session: Session, fazenda_id: int | None, numeros: list[str] | None = None) -> dict[str, dict]:
    """Animais com resultado REAGENTE em uma aplicacao de exame nao estornada."""
    query = (
        select(CronogramaSanitarioAplicacaoAnimal, CronogramaSanitarioAplicacao)
        .join(CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacao.id == CronogramaSanitarioAplicacaoAnimal.aplicacao_id)
        .where(CronogramaSanitarioAplicacaoAnimal.exame_resultado == "reagente")
        .where(CronogramaSanitarioAplicacao.estado == "aplicada")
    )
    if fazenda_id is not None:
        query = query.where(CronogramaSanitarioAplicacao.fazenda_id == fazenda_id)
    if numeros is not None:
        if not numeros:
            return {}
        query = query.where(CronogramaSanitarioAplicacaoAnimal.numero_matriz.in_(list(numeros)))
    saida: dict[str, dict] = {}
    for linha, ap in session.exec(query.order_by(CronogramaSanitarioAplicacao.data_aplicacao.desc())).all():
        saida.setdefault(linha.numero_matriz, {"aplicacao_id": ap.id, "data": ap.data_aplicacao})
    return saida


def recusar_reagentes(session: Session, fazenda_id: int | None, numeros: list[str], o_que: str) -> None:
    """Levanta AplicacaoError se algum dos animais e reagente."""
    reag = animais_reagentes(session, fazenda_id, list(numeros))
    if reag:
        n = sorted(reag, key=lambda x: (len(x), x))[0]
        raise AplicacaoError(f"Animal {n} é reagente em exame ({_br(reag[n]['data'])}): não entra em {o_que}")


def _retirar_reagente_dos_agendamentos(
    session: Session, numero: str, ap: CronogramaSanitarioAplicacao, cron_atual: CronogramaSanitario, evento_nome: str,
    user, agora: datetime,
) -> None:
    """O reagente sai de qualquer outro agendamento/lista de espera (aftosa, etc.), com log em cada um."""
    query = (
        select(CronogramaSanitarioAnimal, CronogramaSanitario)
        .join(CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAnimal.cronograma_id)
        .where(CronogramaSanitarioAnimal.numero_matriz == numero)
        .where(CronogramaSanitario.status.in_(_ATIVOS))
        .where(CronogramaSanitarioAnimal.status.in_(("sugerido", "incluido")))
        .where(CronogramaSanitario.id != cron_atual.id)
    )
    if cron_atual.fazenda_id is not None:
        query = query.where(CronogramaSanitario.fazenda_id == cron_atual.fazenda_id)
    for linha, cron in session.exec(query).all():
        antes = linha.status
        linha.status = "excluido"
        linha.motivo = "Reagente no exame — sai dos agendamentos"
        linha.motivo_entrada = f"reagente:{ap.id}:{antes}"
        linha.data_decisao = ap.data_aplicacao
        session.add(linha)
        registrar_log(
            session, cron, "Retirou animal reagente", user=user, canal=ap.canal, motivo="Reagente", aplicacao_id=None, agora=agora,
            detalhe=f"Animal {numero} saiu deste agendamento: reagente em {evento_nome} ({_br(ap.data_aplicacao)})",
        )


def _restaurar_reagente_nos_agendamentos(session: Session, numero: str, ap: CronogramaSanitarioAplicacao, user, agora: datetime) -> None:
    marca = f"reagente:{ap.id}:"
    query = (
        select(CronogramaSanitarioAnimal, CronogramaSanitario)
        .join(CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAnimal.cronograma_id)
        .where(CronogramaSanitarioAnimal.numero_matriz == numero)
        .where(CronogramaSanitarioAnimal.status == "excluido")
        .where(CronogramaSanitarioAnimal.motivo_entrada.like(marca + "%"))
    )
    for linha, cron in session.exec(query).all():
        antes = (linha.motivo_entrada or "").split(":")[-1] or "sugerido"
        linha.status = antes if antes in ("sugerido", "incluido") else "sugerido"
        linha.motivo = None
        linha.motivo_entrada = None
        linha.data_decisao = None
        session.add(linha)
        registrar_log(
            session, cron, "Devolveu animal (exame estornado)", user=user, canal=ap.canal, aplicacao_id=None, agora=agora,
            detalhe=f"Animal {numero} voltou a este agendamento: o resultado reagente foi estornado",
        )


def _marcar_a_descartar(animal: Animal | None, data_leitura: date) -> None:
    if animal is None:
        return
    if not animal.a_descartar:
        animal.a_descartar = True
        animal.a_descartar_em = data_leitura
        animal.descarte_previsto_em = None
    animal.atualizado_em = datetime.utcnow()


def _desmarcar_a_descartar(session: Session, animal: Animal | None, ap: CronogramaSanitarioAplicacao, fazenda_id: int | None) -> None:
    """So desfaz a marca se foi este exame que a colocou (mesma data) e nao ha outro reagente ativo."""
    if animal is None or not animal.a_descartar or animal.a_descartar_em != ap.data_aplicacao:
        return
    outros = [n for n, info in animais_reagentes(session, fazenda_id, [animal.numero]).items() if info["aplicacao_id"] != ap.id]
    if outros:
        return
    animal.a_descartar = False
    animal.a_descartar_em = None
    animal.descarte_previsto_em = None
    animal.atualizado_em = datetime.utcnow()


# ───────────────────────────── reteste ─────────────────────────────
def _agendar_reteste(
    session: Session, calendario: CalendarioSanitario, numero: str, reteste_em: date, data_leitura: date, fazenda_id: int | None,
) -> None:
    """Inconclusivo: o animal volta para a lista de espera do proprio protocolo, devido 60 dias depois."""
    from fazenda.rules.cronograma_sanitario import cronograma_aberto_ou_novo
    espera = cronograma_aberto_ou_novo(session, calendario, reteste_em)
    texto = f"Reteste: inconclusivo em {_br(data_leitura)}"
    linha = session.exec(
        select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == espera.id)
        .where(CronogramaSanitarioAnimal.numero_matriz == numero)
    ).first()
    if linha is None:
        linha = CronogramaSanitarioAnimal(cronograma_id=espera.id, numero_matriz=numero, data_sugestao=data_leitura, fazenda_id=fazenda_id)
    linha.status = "sugerido"
    linha.origem = "janela"
    linha.motivo = None
    linha.data_decisao = None
    linha.data_aplicacao = None
    linha.reteste = True
    linha.data_devida = reteste_em
    linha.motivo_entrada = texto
    session.add(linha)


def _remover_reteste(session: Session, calendario_id: int, numero: str, reteste_em: date | None) -> None:
    query = (
        select(CronogramaSanitarioAnimal)
        .join(CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAnimal.cronograma_id)
        .where(CronogramaSanitario.calendario_sanitario_id == calendario_id)
        .where(CronogramaSanitarioAnimal.numero_matriz == numero)
        .where(CronogramaSanitarioAnimal.reteste == True)  # noqa: E712
        .where(CronogramaSanitarioAnimal.status == "sugerido")
    )
    for linha in session.exec(query).all():
        if reteste_em is None or linha.data_devida == reteste_em:
            session.delete(linha)


def retestes(session: Session, fazenda_id: int | None, hoje: date | None = None) -> dict:
    """Inconclusivos com reteste pendente: 'aguardando' (ainda nao venceu), 'no_dia' ou 'atrasado' ("Reteste atrasado")."""
    hoje = hoje or date.today()
    query = (
        select(CronogramaSanitarioAplicacaoAnimal, CronogramaSanitarioAplicacao)
        .join(CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacao.id == CronogramaSanitarioAplicacaoAnimal.aplicacao_id)
        .where(CronogramaSanitarioAplicacaoAnimal.exame_resultado == "inconclusivo")
        .where(CronogramaSanitarioAplicacaoAnimal.reteste_em.is_not(None))
        .where(CronogramaSanitarioAplicacao.estado == "aplicada")
    )
    if fazenda_id is not None:
        query = query.where(CronogramaSanitarioAplicacao.fazenda_id == fazenda_id)
    pares = session.exec(query.order_by(CronogramaSanitarioAplicacaoAnimal.reteste_em)).all()
    if not pares:
        return {"total": 0, "atrasados": 0, "itens": []}
    numeros = [l.numero_matriz for l, _ in pares]
    animais = {a.numero: a for a in session.exec(select(Animal).where(Animal.numero.in_(numeros))).all()
               if fazenda_id is None or a.fazenda_id == fazenda_id}
    crons = {c.id: c for c in session.exec(select(CronogramaSanitario).where(
        CronogramaSanitario.id.in_([a.cronograma_id for _, a in pares]))).all()}
    cals = {c.id: c for c in session.exec(select(CalendarioSanitario)).all()}
    eventos = {e.id: e for e in session.exec(select(EventoSanitario)).all()}
    itens = []
    for linha, ap in pares:
        animal = animais.get(linha.numero_matriz)
        if animal is None or not animal.ativo:
            continue
        cron = crons.get(ap.cronograma_id)
        cal = cals.get(cron.calendario_sanitario_id) if cron else None
        # ja repetido? (outra leitura/coleta do mesmo animal e protocolo depois desta)
        posterior = session.exec(
            select(CronogramaSanitarioAplicacaoAnimal.id)
            .join(CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacao.id == CronogramaSanitarioAplicacaoAnimal.aplicacao_id)
            .join(CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAplicacao.cronograma_id)
            .where(CronogramaSanitarioAplicacaoAnimal.numero_matriz == linha.numero_matriz)
            .where(CronogramaSanitarioAplicacaoAnimal.exame_resultado.is_not(None))
            .where(CronogramaSanitarioAplicacao.estado == "aplicada")
            .where(CronogramaSanitarioAplicacao.id > ap.id)
            .where(CronogramaSanitario.calendario_sanitario_id == (cal.id if cal else -1))
        ).first()
        if posterior is not None:
            continue
        dias = (hoje - linha.reteste_em).days
        situacao = "atrasado" if dias > 0 else ("no_dia" if dias == 0 else "aguardando")
        ev = eventos.get(cal.evento_sanitario_id) if cal else None
        itens.append({
            "numero_matriz": linha.numero_matriz, "nome": animal.nome, "lote": animal.grupo_primario,
            "aplicacao_id": ap.id, "cronograma_id": ap.cronograma_id, "calendario_sanitario_id": cal.id if cal else None,
            "protocolo_nome": ev.nome if ev else "Exame", "data_leitura": ap.data_aplicacao.isoformat(),
            "reteste_em": linha.reteste_em.isoformat(), "situacao": situacao, "dias_atraso": max(0, dias),
            "rotulo": "Reteste atrasado" if situacao == "atrasado" else ("Reteste hoje" if situacao == "no_dia" else "Reteste previsto"),
        })
    return {"total": len(itens), "atrasados": sum(1 for i in itens if i["situacao"] == "atrasado"), "itens": itens}


# ───────────────────────────── contexto da gaveta ─────────────────────────────
def _resumo_inoculacao(ino: CronogramaSanitarioAplicacao | None) -> dict | None:
    if ino is None:
        return None
    return {
        "aplicacao_id": ino.id, "data": ino.data_aplicacao.isoformat(), "hora": ino.hora, "aplicador_nome": ino.aplicador_nome,
        "aplicador_crmv": ino.aplicador_crmv, "lote_texto": ino.lote_texto, "validade": _iso(ino.validade),
        "estoque_desconsiderado": ino.estoque_desconsiderado, "tipo_teste": ino.tipo_teste, "dose_total": ino.dose_total,
        "unidade": ino.unidade, "custo": ino.custo, "pode_desfazer": ap_rules.pode_desfazer(ino),
        "desfazer_restante_s": max(0, ap_rules.DESFAZER_SEGUNDOS - int((datetime.utcnow() - ino.registrado_em).total_seconds()))
        if ap_rules.pode_desfazer(ino) else 0,
    }


def contexto(session: Session, cron: CronogramaSanitario, cal: CalendarioSanitario | None, evento: EventoSanitario | None) -> dict | None:
    """Bloco `exame` do contexto da gaveta Aplicar (None para vacina/vermifugo)."""
    if not eh_exame(evento):
        return None
    _, _, tipo = contexto_do_evento(session, cal, evento)
    fase = fase_atual(session, cron, tipo)
    ino = inoculacao_ativa(session, cron.id) if fase == "leitura" else None
    return {
        "fase": fase, "tipo_exame": tipo, "leitura_horas": horas_ate_leitura(tipo),
        "janela_leitura_horas": [LEITURA_HORAS, LEITURA_LIMITE_HORAS] if tipo == "tuberculina" else None,
        "tipos_teste": list(TIPOS_TESTE) if tipo == "tuberculina" else [], "resultados": list(RESULTADOS),
        "reteste_dias": RETESTE_DIAS if tipo == "tuberculina" else None,
        "inoculacao": _resumo_inoculacao(ino), "leitura_prevista_em": _iso(ino.leitura_prevista_em) if ino else None,
        "leitura_limite_em": _iso(ino.leitura_limite_em) if ino else None,
        "notifica_reagente": True,
    }


# ───────────────────────────── aplicar (dispatch) ─────────────────────────────
def _normalizar_resultados(bruto: dict | None) -> dict[str, str]:
    saida: dict[str, str] = {}
    for k, v in (bruto or {}).items():
        chave = (str(k) or "").strip()
        valor = ap_rules._norm(str(v or "")).strip()
        if valor in ("positivo", "reagente"):
            valor = "reagente"
        elif valor in ("indefinido", "inconclusivo"):
            valor = "inconclusivo"
        if chave:
            saida[chave] = valor
    return saida


def _numero_positivo(v) -> float | None:
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return x if x >= 0 else None


def aplicar_exame(
    session: Session, cron: CronogramaSanitario, calendario: CalendarioSanitario, evento: EventoSanitario, dados: dict,
    *, user, fazenda_id: int | None, canal: str, chave: str | None,
) -> dict:
    """Inoculacao, leitura ou coleta do agendamento de exame — tudo ou nada, mesmas regras do aplicar da vacina."""
    hoje = date.today()
    agora = datetime.utcnow()
    aplicador = ap_rules._pessoa_da_fazenda(session, dados.get("aplicador_pessoa_id"), fazenda_id)
    if aplicador is None:
        raise AplicacaoError("Escolha quem aplicou (aplicador não encontrado)")
    produto, doenca_nome, tipo = contexto_do_evento(session, calendario, evento)
    if ap_rules.exige_veterinario(evento, produto, doenca_nome) and not ap_rules.eh_veterinario(aplicador):
        raise AplicacaoError(f"{evento.nome}: só veterinário habilitado (CRMV) aplica. Escolha o veterinário em “Quem aplicou”.")

    data_ap = dados.get("data_aplicacao") or hoje
    if isinstance(data_ap, str):
        data_ap = date.fromisoformat(data_ap)
    if data_ap > hoje:
        raise AplicacaoError("A data real da aplicação não pode ser futura")
    hora = (dados.get("hora") or "").strip() or None
    if hora and not ap_rules._HORA_RE.match(hora):
        raise AplicacaoError("Hora inválida — use HH:MM")
    if hora is None and data_ap == hoje:
        hora = datetime.now().strftime("%H:%M")

    fase = fase_atual(session, cron, tipo)
    ctx = dict(session=session, cron=cron, calendario=calendario, evento=evento, dados=dados, user=user, fazenda_id=fazenda_id,
               canal=canal, chave=chave, hoje=hoje, agora=agora, aplicador=aplicador, produto=produto, tipo=tipo,
               data_ap=data_ap, hora=hora)
    if fase == "leitura":
        return _leitura(**ctx)
    return _inoculacao_ou_coleta(fase=fase, **ctx)


def _linhas_incluidas(session: Session, cron: CronogramaSanitario) -> dict[str, CronogramaSanitarioAnimal]:
    linhas = session.exec(
        select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron.id)
        .where(CronogramaSanitarioAnimal.status == "incluido")
    ).all()
    return {l.numero_matriz: l for l in linhas}


def _resposta(session: Session, cron: CronogramaSanitario, ap: CronogramaSanitarioAplicacao, avisos: list[str], fazenda_id: int | None) -> dict:
    session.refresh(cron)
    session.refresh(ap)
    return {
        "aplicacao": ap_rules.serializar_aplicacao(session, ap), "agendamento": cron, "avisos": avisos, "idempotente": False,
        "financeiro": ap_rules._financeiro_da_aplicacao(session, cron, ap, fazenda_id),
    }


def _inoculacao_ou_coleta(
    *, fase: str, session: Session, cron: CronogramaSanitario, calendario: CalendarioSanitario, evento: EventoSanitario, dados: dict,
    user, fazenda_id: int | None, canal: str, chave: str | None, hoje: date, agora: datetime, aplicador, produto: str | None,
    tipo: str, data_ap: date, hora: str | None,
) -> dict:
    por_numero = _linhas_incluidas(session, cron)
    aplicados = list(dict.fromkeys((n or "").strip() for n in (dados.get("animais_aplicados") or []) if (n or "").strip()))
    if not aplicados:
        raise AplicacaoError("Marque pelo menos 1 animal " + ("inoculado" if fase == "inoculacao" else "coletado"))
    for n in aplicados:
        if n not in por_numero:
            raise AplicacaoError(f"Animal {n} não está neste agendamento")
    nao_in = {(x.get("numero_matriz") or "").strip(): x for x in (dados.get("nao_aplicados") or [])}
    restantes = sorted((n for n in por_numero if n not in aplicados), key=lambda n: (len(n), n))
    for n in restantes:
        x = nao_in.get(n)
        if not x or not (x.get("motivo") or "").strip():
            raise AplicacaoError(f"Informe o motivo do animal {n} que não foi aplicado")
        if (x.get("destino") or "espera") not in ap_rules.DESTINOS:
            raise AplicacaoError(f"Destino inválido para o animal {n} — use espera ou naoSeAplica")
    for n in nao_in:
        if n not in restantes:
            raise AplicacaoError(f"Animal {n} não pode constar como não aplicado")
    recusar_reagentes(session, fazenda_id, aplicados, "novo exame")

    tipo_teste = (dados.get("tipo_teste") or "").strip() or None
    if tipo_teste and tipo == "tuberculina" and tipo_teste not in TIPOS_TESTE:
        raise AplicacaoError("Escolha o tipo de teste da tuberculina: " + ", ".join(TIPOS_TESTE))
    resultados = _normalizar_resultados(dados.get("resultados")) if fase == "coleta" else {}
    if resultados:
        if set(resultados) != set(aplicados):
            raise AplicacaoError("Informe o resultado de cada animal coletado (ou nenhum: o resultado vem depois do laboratório)")
        invalido = next((n for n, v in resultados.items() if v not in RESULTADOS), None)
        if invalido:
            raise AplicacaoError(f"Resultado inválido para o animal {invalido} — use negativo, reagente ou inconclusivo")

    # ── produto (tuberculina) e frasco; exame sem produto (brucelose sorologia) nao mexe no estoque ──
    desconsiderar = bool(dados.get("desconsiderar_estoque")) and bool(produto)
    motivo_estoque = (dados.get("motivo_desconsiderar_estoque") or "").strip()
    item = marca = modo = None
    doses = {n: {"dose": None, "peso_kg": None, "peso_estimado": False} for n in aplicados}
    lote = lote_texto = validade = None
    ciente_vencido = bool(dados.get("ciente_vencido"))
    if produto:
        if desconsiderar and not motivo_estoque:
            raise AplicacaoError("Informe o motivo para desconsiderar o estoque")
        item, marca = ap_rules._marca_e_item(session, produto, fazenda_id, dados.get("estoque_id"))
        if item is None and not desconsiderar:
            raise AplicacaoError(
                f'"{produto}" não está no estoque desta fazenda: escolha o frasco ou desconsidere o estoque informando o motivo'
            )
        modo = ap_rules._modo_dose(evento, marca)
        if modo.get("unidade") is None or (not modo["por_peso"] and modo.get("dose") is None):
            raise AplicacaoError(f'Informe a dose e a unidade no protocolo "{evento.nome}" (cadastro do protocolo)')
        if item is not None and not desconsiderar:
            from fazenda.rules.unidades import unidades_compativeis
            if modo["unidade"] not in unidades_compativeis(item.unidade):
                raise AplicacaoError(f'Unidade "{modo["unidade"]}" não é compatível com o produto "{item.nome}"')
        doses = ap_rules.calcular_doses(session, aplicados, modo, fazenda_id, hoje, dados.get("pesos"))
        sem_peso = [n for n in aplicados if doses[n]["dose"] is None]
        if sem_peso:
            raise AplicacaoError("Sem peso para calcular a dose de: " + ", ".join(sem_peso) + ". Informe o peso desses animais.")
        if desconsiderar:
            lote_texto = (dados.get("lote_veterinario") or "").strip() or None
            validade = dados.get("validade_veterinario")
            if isinstance(validade, str):
                validade = date.fromisoformat(validade)
        elif item is not None:
            lote = ap_rules._escolher_lote(item, dados.get("lote_id"), session, data_ap)
            if lote is not None:
                lote_texto, validade = lote.numero_lote, lote.validade
                if ap_rules._vencido(lote, data_ap) and not ciente_vencido:
                    raise AplicacaoError(
                        f"Frasco vencido: o lote {lote.numero_lote or lote.id} venceu em {lote.validade.strftime('%d/%m/%Y')}. "
                        "Marque a ciência para usar assim mesmo."
                    )

    resumo = ap_rules.checklist_resumo(session, cron)
    pendentes = resumo["pendentes"]
    if pendentes and not bool(dados.get("ciencia_pendentes")):
        raise AplicacaoError(
            f"Marque a ciência dos {len(pendentes)} {'item pendente' if len(pendentes) == 1 else 'itens pendentes'} "
            f"do checklist ({', '.join(p['nome'] for p in pendentes)}). Aplicar não é bloqueado."
        )

    # ── tudo validado: grava ──
    total = round(sum(d["dose"] for d in doses.values() if d["dose"] is not None), 4) if produto else None
    custo = dados.get("custo")
    if custo is None and item is not None and not desconsiderar and item.valor_unitario is not None and total is not None:
        custo = round(total * item.valor_unitario, 2)
    fora = sum(1 for n in aplicados if por_numero[n].origem == "fora_janela")
    excecoes: list[str] = []
    if fora:
        excecoes.append(f"{fora} {'animal' if fora == 1 else 'animais'} fora da janela de aplicação")
    if desconsiderar:
        excecoes.append("Frasco do veterinário (sem baixa de estoque)" if motivo_estoque.lower() == "frasco do veterinário"
                        else f"Estoque desconsiderado (sem baixa): {motivo_estoque}")
    if lote is not None and ap_rules._vencido(lote, data_ap):
        excecoes.append(f"Frasco vencido usado com ciência (lote {lote_texto or lote.id})")
    if pendentes:
        excecoes.append(f"Ciência de {len(pendentes)} {'item pendente' if len(pendentes) == 1 else 'itens pendentes'} do checklist")
    if data_ap < hoje:
        excecoes.append("Lançamento retroativo")
    if data_ap < cron.data_evento and fase == "coleta":
        excecoes.append(f"Aplicado antes da data agendada ({cron.data_evento.strftime('%d/%m/%Y')})")

    inoc_em = _dt(data_ap, hora)
    ap = CronogramaSanitarioAplicacao(
        fazenda_id=cron.fazenda_id, cronograma_id=cron.id, estado="aplicada", canal=canal, fase=fase,
        aplicador_pessoa_id=aplicador.id, aplicador_nome=aplicador.nome, aplicador_crmv=getattr(aplicador, "crmv", None),
        data_aplicacao=data_ap, hora=hora, produto=produto, unidade=modo["unidade"] if modo else None, via=evento.via_padrao,
        dose_total=total, estoque_id=None if desconsiderar else (item.id if item else None), lote_id=lote.id if lote else None,
        lote_texto=lote_texto, validade=validade,
        frasco_vencido_ciente=bool(lote is not None and ap_rules._vencido(lote, data_ap) and ciente_vencido),
        estoque_desconsiderado=desconsiderar, estoque_motivo=motivo_estoque or None, custo=custo,
        ciencia_itens=json.dumps([{"chave": p["chave"], "nome": p["nome"]} for p in pendentes]) if pendentes else None,
        ciencia_motivo=(dados.get("ciencia_motivo") or None) if pendentes else None,
        ciencia_usuario_id=ap_rules._uid(user) if pendentes else None, ciencia_em=agora if pendentes else None,
        retroativo=data_ap < hoje, excecoes=json.dumps(excecoes) if excecoes else None,
        observacao=(dados.get("observacao") or None), chave_idempotencia=chave,
        registrado_por_usuario_id=ap_rules._uid(user), registrado_em=agora,
        tipo_teste=tipo_teste, laudo=(dados.get("laudo") or "").strip() or None,
    )
    if fase == "inoculacao":
        ap.leitura_prevista_em = inoc_em + timedelta(hours=LEITURA_HORAS)
        ap.leitura_limite_em = inoc_em + timedelta(hours=LEITURA_LIMITE_HORAS)
        ap.data_evento_antes = cron.data_evento
        ap.hora_antes = cron.hora
    avisos: list[str] = []
    try:
        session.add(ap)
        session.flush()
        for n in aplicados:
            linha = por_numero[n]
            d = doses[n]
            res = resultados.get(n)
            reg = CronogramaSanitarioAplicacaoAnimal(
                aplicacao_id=ap.id, fazenda_id=cron.fazenda_id, numero_matriz=n, resultado="aplicado", origem=linha.origem,
                motivo_origem=linha.motivo if linha.origem == "fora_janela" else None, dose=d["dose"],
                unidade=modo["unidade"] if modo else None, peso_kg=d["peso_kg"], peso_estimado=d["peso_estimado"],
                exame_resultado=(res or "coletado") if fase == "coleta" else None,
            )
            session.add(reg)
            session.flush()
            if item is not None and not desconsiderar and d["dose"] is not None:
                avisos.extend(ap_rules._estoque_baixar(
                    session, item=item, quantidade=d["dose"], unidade=modo["unidade"], data=data_ap, fazenda_id=cron.fazenda_id,
                    observacao=f"Exame em {n} — {evento.nome} (agendamento #{cron.id})", usuario_id=ap_rules._uid(user),
                    origem_tipo=ORIGEM_ESTOQUE, origem_id=reg.id, produto=produto, lote_id=lote.id if lote else None,
                ))
            if fase == "coleta":
                _gravar_resultado(session, cron, calendario, evento, ap, reg, res, aplicador, data_ap, user, agora, None)
                linha.status = "aplicado"
                linha.data_aplicacao = data_ap
                session.add(linha)
        _tratar_nao_aplicados(session, cron, calendario, por_numero, restantes, nao_in, ap, data_ap)
        if fase == "coleta":
            cron.status = "concluido"
            cron.concluido_em = agora
            acao = "Aplicou (coleta)"
        else:
            cron.data_evento = ap.leitura_prevista_em.date()
            cron.hora = hora
            acao = "Aplicou (inoculação)"
        cron.atualizado_em = agora
        session.add(cron)
        txt = f"{len(aplicados)} {'animal' if len(aplicados) == 1 else 'animais'}{f' · lote {lote_texto}' if lote_texto else ''} · aplicador {aplicador.nome}"
        if fase == "inoculacao":
            txt += f" · leitura prevista {ap.leitura_prevista_em.strftime('%d/%m/%Y %H:%M')} (72 h)"
        registrar_log(session, cron, acao, user=user, canal=canal, aplicacao_id=ap.id, agora=agora, detalhe=txt)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _resposta(session, cron, ap, avisos, fazenda_id)


def _tratar_nao_aplicados(session, cron, calendario, por_numero, restantes, nao_in, ap, data_ap) -> None:
    """Quem ficou de fora volta a lista de espera (com aviso) ou e desconsiderado — sempre com motivo."""
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


def _gravar_resultado(
    session: Session, cron: CronogramaSanitario, calendario: CalendarioSanitario, evento: EventoSanitario,
    ap: CronogramaSanitarioAplicacao, reg: CronogramaSanitarioAplicacaoAnimal, resultado: str | None, aplicador, data_ap: date,
    user, agora: datetime, mm: float | None,
) -> None:
    """ExameResultado (relatorios de Sanidade) + efeitos do reagente/inconclusivo. `resultado` None = so coletado."""
    if resultado is None:
        return
    obs = f"Exame preventivo (agendamento #{cron.id})" + (f" · laudo {ap.laudo}" if ap.laudo else "")
    er = ExameResultado(
        numero_matriz=reg.numero_matriz, evento_sanitario_id=evento.id, exame_definicao_id=evento.exame_definicao_id,
        data_exame=data_ap, resultado=_RESULTADO_EXAME[resultado], veterinario=aplicador.nome, observacao=obs,
        fazenda_id=cron.fazenda_id,
    )
    session.add(er)
    session.flush()
    reg.exame_resultado = resultado
    reg.exame_resultado_id = er.id
    reg.espessura_mm = mm
    session.add(reg)
    if resultado == "reagente":
        animal = session.exec(select(Animal).where(Animal.numero == reg.numero_matriz)
                              .where(Animal.fazenda_id == cron.fazenda_id)).first()
        _marcar_a_descartar(animal, data_ap)
        if animal is not None:
            session.add(animal)
        _retirar_reagente_dos_agendamentos(session, reg.numero_matriz, ap, cron, evento.nome, user, agora)
    elif resultado == "inconclusivo":
        reg.reteste_em = data_ap + timedelta(days=RETESTE_DIAS)
        session.add(reg)
        _agendar_reteste(session, calendario, reg.numero_matriz, reg.reteste_em, data_ap, cron.fazenda_id)


def _leitura(
    *, session: Session, cron: CronogramaSanitario, calendario: CalendarioSanitario, evento: EventoSanitario, dados: dict,
    user, fazenda_id: int | None, canal: str, chave: str | None, hoje: date, agora: datetime, aplicador, produto: str | None,
    tipo: str, data_ap: date, hora: str | None,
) -> dict:
    ino = inoculacao_ativa(session, cron.id)
    if ino is None:
        raise AplicacaoError("Este exame ainda não foi inoculado")
    por_numero = _linhas_incluidas(session, cron)
    if not por_numero:
        raise AplicacaoError("Este agendamento não tem animais para ler")
    resultados = _normalizar_resultados(dados.get("resultados"))
    if set(resultados) != set(por_numero):
        raise AplicacaoError("Informe o resultado de cada animal (negativo, reagente ou inconclusivo)")
    invalido = next((n for n, v in resultados.items() if v not in RESULTADOS), None)
    if invalido:
        raise AplicacaoError(f"Resultado inválido para o animal {invalido} — use negativo, reagente ou inconclusivo")
    mm_bruto = dados.get("espessuras_mm") or {}
    mm: dict[str, float] = {}
    for n in por_numero:
        v = _numero_positivo(mm_bruto.get(n))
        if v is None:
            raise AplicacaoError("Informe a espessura da pele (mm) de cada animal")
        mm[n] = v
    tipo_teste = ((dados.get("tipo_teste") or "").strip() or (ino.tipo_teste or ""))
    if tipo_teste not in TIPOS_TESTE:
        raise AplicacaoError("Escolha o tipo de teste da tuberculina: " + ", ".join(TIPOS_TESTE))

    inoc_em = _dt(ino.data_aplicacao, ino.hora)
    lido_em = _dt(data_ap, hora)
    horas = (lido_em - inoc_em).total_seconds() / 3600
    if horas < 0:
        raise AplicacaoError("A leitura não pode ser anterior à inoculação")
    justificativa = (dados.get("justificativa_leitura") or "").strip() or None
    antes = lido_em < ino.leitura_prevista_em
    depois = lido_em > ino.leitura_limite_em
    if antes and not justificativa:
        raise AplicacaoError("Leitura antes de 72 h da inoculação: escreva a justificativa")
    excecoes: list[str] = []
    if antes:
        excecoes.append(f"Leitura antes de 72 h da inoculação ({round(horas)} h): {justificativa}")
    if depois:
        excecoes.append(f"Leitura fora da janela de 72–96 h ({round(horas)} h após a inoculação)")
    if data_ap < hoje:
        excecoes.append("Lançamento retroativo")
    fora = sum(1 for n in por_numero if por_numero[n].origem == "fora_janela")
    if fora:
        excecoes.append(f"{fora} {'animal' if fora == 1 else 'animais'} fora da janela de aplicação")

    ap = CronogramaSanitarioAplicacao(
        fazenda_id=cron.fazenda_id, cronograma_id=cron.id, estado="aplicada", canal=canal, fase="leitura",
        inoculacao_aplicacao_id=ino.id, aplicador_pessoa_id=aplicador.id, aplicador_nome=aplicador.nome,
        aplicador_crmv=getattr(aplicador, "crmv", None), data_aplicacao=data_ap, hora=hora, produto=produto or ino.produto,
        unidade=ino.unidade, via=ino.via, dose_total=None, estoque_id=ino.estoque_id, lote_id=ino.lote_id,
        lote_texto=ino.lote_texto, validade=ino.validade, estoque_desconsiderado=ino.estoque_desconsiderado,
        estoque_motivo=ino.estoque_motivo, custo=ino.custo, retroativo=data_ap < hoje,
        excecoes=json.dumps(excecoes) if excecoes else None, observacao=(dados.get("observacao") or None),
        chave_idempotencia=chave, registrado_por_usuario_id=ap_rules._uid(user), registrado_em=agora,
        tipo_teste=tipo_teste, laudo=(dados.get("laudo") or "").strip() or None, leitura_horas=round(horas, 2),
        leitura_fora_janela=bool(antes or depois), leitura_justificativa=justificativa,
    )
    try:
        session.add(ap)
        session.flush()
        for n in sorted(por_numero, key=lambda x: (len(x), x)):
            linha = por_numero[n]
            reg = CronogramaSanitarioAplicacaoAnimal(
                aplicacao_id=ap.id, fazenda_id=cron.fazenda_id, numero_matriz=n, resultado="aplicado", origem=linha.origem,
                motivo_origem=linha.motivo if linha.origem == "fora_janela" else None, exame_resultado=resultados[n],
                espessura_mm=mm[n],
            )
            session.add(reg)
            session.flush()
            _gravar_resultado(session, cron, calendario, evento, ap, reg, resultados[n], aplicador, data_ap, user, agora, mm[n])
            linha.status = "aplicado"
            linha.data_aplicacao = data_ap
            session.add(linha)
        cron.status = "concluido"
        cron.concluido_em = agora
        cron.atualizado_em = agora
        session.add(cron)
        cont = {r: sum(1 for v in resultados.values() if v == r) for r in RESULTADOS}
        registrar_log(
            session, cron, "Registrou a leitura do exame", user=user, canal=canal, aplicacao_id=ap.id, agora=agora,
            motivo=justificativa,
            detalhe=(f"{len(por_numero)} animais · {cont['negativo']} negativos, {cont['reagente']} reagentes, "
                     f"{cont['inconclusivo']} inconclusivos · {round(horas)} h após a inoculação · leitura por {aplicador.nome}"),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _resposta(session, cron, ap, [], fazenda_id)


# ───────────────────────────── desfazer / estornar ─────────────────────────────
def validar_estorno(session: Session, ap: CronogramaSanitarioAplicacao) -> None:
    """A inoculacao so pode ser estornada quando nao ha leitura ativa dela."""
    if ap.fase != "inoculacao":
        return
    leitura = session.exec(
        select(CronogramaSanitarioAplicacao).where(CronogramaSanitarioAplicacao.inoculacao_aplicacao_id == ap.id)
        .where(CronogramaSanitarioAplicacao.estado == "aplicada")
    ).first()
    if leitura is not None:
        raise AplicacaoError("Este exame já tem a leitura registrada: estorne primeiro a leitura, depois a inoculação")


def reverter(session: Session, ap: CronogramaSanitarioAplicacao, cron: CronogramaSanitario, user, agora: datetime) -> None:
    """Desfaz os efeitos proprios do exame (estoque da inoculacao/coleta, resultado, reagente, reteste, data do agendamento)."""
    if ap.fase is None:
        return
    calendario = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    for a in ap_rules._animais_da_aplicacao(session, ap.id):
        if a.resultado != "aplicado":
            continue
        mov = session.exec(
            select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == ORIGEM_ESTOQUE).where(MovimentoEstoque.origem_id == a.id)
            .where(MovimentoEstoque.movimento == "Aplicação").order_by(MovimentoEstoque.id.desc())
        ).first()
        if mov is not None and mov.estoque_id is not None and not ap.estoque_desconsiderado:
            from fazenda.models import Estoque
            _estoque_devolver(
                session, item=session.get(Estoque, mov.estoque_id), quantidade=mov.quantidade, unidade=mov.unidade,
                data=agora.date(), fazenda_id=cron.fazenda_id, observacao=f"Estorno do exame em {a.numero_matriz} (agendamento #{cron.id})",
                usuario_id=ap_rules._uid(user), origem_tipo=ORIGEM_ESTOQUE, origem_id=a.id, produto=ap.produto, lote_id=mov.lote_id,
            )
        if a.exame_resultado_id is not None:
            er = session.get(ExameResultado, a.exame_resultado_id)
            if er is not None:
                session.delete(er)
        if a.exame_resultado == "reagente":
            animal = session.exec(select(Animal).where(Animal.numero == a.numero_matriz).where(Animal.fazenda_id == cron.fazenda_id)).first()
            _desmarcar_a_descartar(session, animal, ap, cron.fazenda_id)
            _restaurar_reagente_nos_agendamentos(session, a.numero_matriz, ap, user, agora)
        elif a.exame_resultado == "inconclusivo" and calendario is not None:
            _remover_reteste(session, calendario.id, a.numero_matriz, a.reteste_em)
    if ap.fase == "inoculacao":
        if ap.data_evento_antes is not None:
            cron.data_evento = ap.data_evento_antes
        cron.hora = ap.hora_antes


# ───────────────────────────── notificacao do reagente ─────────────────────────────
def _nomes_animais(session: Session, numeros: list[str], fazenda_id: int | None) -> dict[str, Animal]:
    if not numeros:
        return {}
    return {a.numero: a for a in session.exec(select(Animal).where(Animal.numero.in_(numeros))).all()
            if fazenda_id is None or a.fazenda_id == fazenda_id}


def reagentes(session: Session, fazenda_id: int | None) -> dict:
    """Banner persistente: todo reagente de exame ainda no rebanho, com o registro da notificacao (quem/quando)."""
    pares = list(animais_reagentes(session, fazenda_id).items())
    if not pares:
        return {"total": 0, "pendentes_notificacao": 0, "itens": []}
    ap_ids = {info["aplicacao_id"] for _, info in pares}
    aps = {a.id: a for a in session.exec(select(CronogramaSanitarioAplicacao).where(CronogramaSanitarioAplicacao.id.in_(ap_ids))).all()}
    linhas = session.exec(
        select(CronogramaSanitarioAplicacaoAnimal).where(CronogramaSanitarioAplicacaoAnimal.aplicacao_id.in_(ap_ids))
        .where(CronogramaSanitarioAplicacaoAnimal.exame_resultado == "reagente")
    ).all()
    animais = _nomes_animais(session, [l.numero_matriz for l in linhas], fazenda_id)
    crons = {c.id: c for c in session.exec(select(CronogramaSanitario).where(CronogramaSanitario.id.in_({a.cronograma_id for a in aps.values()}))).all()}
    cals = {c.id: c for c in session.exec(select(CalendarioSanitario)).all()}
    eventos = {e.id: e for e in session.exec(select(EventoSanitario)).all()}
    itens = []
    for l in linhas:
        ap = aps.get(l.aplicacao_id)
        animal = animais.get(l.numero_matriz)
        if ap is None or ap.estado != "aplicada" or (animal is not None and not animal.ativo):
            continue
        cron = crons.get(ap.cronograma_id)
        cal = cals.get(cron.calendario_sanitario_id) if cron else None
        ev = eventos.get(cal.evento_sanitario_id) if cal else None
        itens.append({
            "numero_matriz": l.numero_matriz, "nome": animal.nome if animal else None, "lote": animal.grupo_primario if animal else None,
            "aplicacao_id": ap.id, "cronograma_id": ap.cronograma_id, "protocolo_nome": ev.nome if ev else "Exame",
            "data": ap.data_aplicacao.isoformat(), "hora": ap.hora, "laudo": ap.laudo, "tipo_teste": ap.tipo_teste,
            "espessura_mm": l.espessura_mm, "aplicador_nome": ap.aplicador_nome,
            "notificado_em": _iso(l.notificado_em), "notificado_por": l.notificado_por_nome, "notificacao_ref": l.notificacao_ref,
            "pendente_notificacao": l.notificado_em is None,
        })
    itens.sort(key=lambda i: i["data"], reverse=True)               # mais recente primeiro ...
    itens.sort(key=lambda i: not i["pendente_notificacao"])         # ... e quem falta notificar no topo (sort estavel)
    return {"total": len(itens), "pendentes_notificacao": sum(1 for i in itens if i["pendente_notificacao"]), "itens": itens}


def notificar(
    session: Session, aplicacao_id: int, numeros: list[str] | None, referencia: str | None, *, user, fazenda_id: int | None,
) -> dict:
    """Registra a notificacao ao servico veterinario oficial (quem/quando) dos reagentes da aplicacao."""
    ap, cron = ap_rules._carregar(session, aplicacao_id, fazenda_id)
    if ap.estado != "aplicada":
        raise AplicacaoError("Este registro foi estornado: não há reagente a notificar")
    linhas = {l.numero_matriz: l for l in ap_rules._animais_da_aplicacao(session, ap.id) if l.exame_resultado == "reagente"}
    if not linhas:
        raise AplicacaoError("Este registro não tem animal reagente")
    alvo = list(dict.fromkeys((n or "").strip() for n in (numeros or []) if (n or "").strip()))
    if alvo:
        for n in alvo:
            if n not in linhas:
                raise AplicacaoError(f"Animal {n} não é reagente neste exame")
    else:
        alvo = [n for n, l in linhas.items() if l.notificado_em is None]
        if not alvo:
            raise AplicacaoError("A notificação dos reagentes deste exame já foi registrada")
    for n in alvo:
        l = linhas[n]
        if l.notificado_em is not None:
            raise AplicacaoError(
                f"Animal {n}: a notificação já foi registrada por {l.notificado_por_nome or '—'} em {l.notificado_em.strftime('%d/%m/%Y')}"
            )
    agora = datetime.utcnow()
    nome = ap_rules._nome_usuario(user)
    ref = (referencia or "").strip() or None
    try:
        for n in alvo:
            l = linhas[n]
            l.notificado_em = agora
            l.notificado_por_usuario_id = ap_rules._uid(user)
            l.notificado_por_nome = nome
            l.notificacao_ref = ref
            session.add(l)
        registrar_log(
            session, cron, "Registrou a notificação ao serviço veterinário oficial", user=user, canal=ap.canal, aplicacao_id=ap.id,
            agora=agora, detalhe=f"Reagente(s): {', '.join(sorted(alvo, key=lambda x: (len(x), x)))}" + (f" · {ref}" if ref else ""),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"aplicacao": ap_rules.serializar_aplicacao(session, ap), "notificados": alvo}


# ───────────────────────────── resumos (Concluidos, detalhe, comprovante) ─────────────────────────────
def resumo_do_registro(session: Session, ap: CronogramaSanitarioAplicacao, animais: list[CronogramaSanitarioAplicacaoAnimal]) -> dict | None:
    """Bloco `exame` de um item de Concluidos (leitura ou coleta)."""
    if ap.fase not in ("leitura", "coleta"):
        return None
    lidos = [a for a in animais if a.resultado == "aplicado"]
    conta = {r: sum(1 for a in lidos if a.exame_resultado == r) for r in RESULTADOS}
    ino = session.get(CronogramaSanitarioAplicacao, ap.inoculacao_aplicacao_id) if ap.inoculacao_aplicacao_id else None
    reag = [a for a in lidos if a.exame_resultado == "reagente"]
    retestes_em = sorted(a.reteste_em for a in lidos if a.reteste_em)
    return {
        "fase": ap.fase, "tipo_teste": ap.tipo_teste, "laudo": ap.laudo,
        "inoculacao_data": _iso(ino.data_aplicacao) if ino else None, "inoculacao_hora": ino.hora if ino else None,
        "leitura_data": ap.data_aplicacao.isoformat(), "leitura_hora": ap.hora, "leitura_horas": ap.leitura_horas,
        "leitura_fora_janela": ap.leitura_fora_janela, "leitura_justificativa": ap.leitura_justificativa,
        "negativos": conta["negativo"], "reagentes": conta["reagente"], "inconclusivos": conta["inconclusivo"],
        "coletados": sum(1 for a in lidos if a.exame_resultado == "coletado"),
        "reagentes_pendentes_notificacao": sum(1 for a in reag if a.notificado_em is None),
        "reagentes_notificados": sum(1 for a in reag if a.notificado_em is not None),
        "reteste_em": _iso(retestes_em[0]) if retestes_em else None,
        "espessura_max_mm": max((a.espessura_mm for a in lidos if a.espessura_mm is not None), default=None),
    }


def comprovante(session: Session, aplicacao_id: int, fazenda_id: int | None) -> dict:
    """Dados do comprovante de vacina/exame. Bloqueado so para animal REAGENTE (negativos emitem)."""
    ap, cron = ap_rules._carregar(session, aplicacao_id, fazenda_id)
    if ap.estado != "aplicada":
        raise AplicacaoError("Este registro foi estornado: não há comprovante", 409)
    if ap.fase == "inoculacao":
        raise AplicacaoError("A inoculação ainda não é um resultado: o comprovante sai depois da leitura", 409)
    cal = session.get(CalendarioSanitario, cron.calendario_sanitario_id)
    ev = session.get(EventoSanitario, cal.evento_sanitario_id) if cal else None
    fazenda = session.get(Fazenda, ap.fazenda_id) if ap.fazenda_id else None
    linhas = [l for l in ap_rules._animais_da_aplicacao(session, ap.id) if l.resultado == "aplicado"]
    animais = _nomes_animais(session, [l.numero_matriz for l in linhas], fazenda_id)
    emitem, bloqueados = [], []
    for l in linhas:
        a = animais.get(l.numero_matriz)
        base = {"numero_matriz": l.numero_matriz, "nome": a.nome if a else None, "lote": a.grupo_primario if a else None}
        if l.exame_resultado == "reagente":
            bloqueados.append({**base, "motivo": "Reagente: sem comprovante “animal em dia” para este animal"})
            continue
        emitem.append({
            **base, "resultado": l.exame_resultado, "espessura_mm": l.espessura_mm, "dose": l.dose, "unidade": l.unidade,
            "origem": l.origem, "reteste_em": _iso(l.reteste_em),
        })
    if linhas and not emitem:
        raise AplicacaoError("Comprovante bloqueado: todos os animais deste exame são reagentes", 409)
    ino = session.get(CronogramaSanitarioAplicacao, ap.inoculacao_aplicacao_id) if ap.inoculacao_aplicacao_id else None
    usuarios = ap_rules._nomes_usuarios(session, {ap.registrado_por_usuario_id})
    exame = ev is not None and ev.categoria_preventiva == "exame"
    return {
        "aplicacao_id": ap.id, "tipo": "exame" if exame else "vacina", "fase": ap.fase, "fazenda_nome": fazenda.nome if fazenda else None,
        "protocolo_nome": ev.nome if ev else "Protocolo", "produto": ap.produto, "via": ap.via, "unidade": ap.unidade, "dose_total": ap.dose_total,
        "data": ap.data_aplicacao.isoformat(), "hora": ap.hora, "aplicador_nome": ap.aplicador_nome, "aplicador_crmv": ap.aplicador_crmv,
        "registrado_por": usuarios.get(ap.registrado_por_usuario_id), "canal": ap.canal, "retroativo": ap.retroativo,
        "agendamento": f"{ev.nome if ev else 'Protocolo'} · {_br(cron.data_original or cron.data_evento)}",
        "lote_texto": ap.lote_texto, "validade": _iso(ap.validade), "estoque_desconsiderado": ap.estoque_desconsiderado,
        "fornecido_pelo_veterinario": bool(ap.estoque_desconsiderado and (ap.estoque_motivo or "").lower() == "frasco do veterinário"),
        "custo": ap.custo, "laudo": ap.laudo, "tipo_teste": ap.tipo_teste,
        "inoculacao": ({"data": ino.data_aplicacao.isoformat(), "hora": ino.hora, "aplicador_nome": ino.aplicador_nome,
                        "lote_texto": ino.lote_texto, "validade": _iso(ino.validade)} if ino else None),
        "leitura": ({"data": ap.data_aplicacao.isoformat(), "hora": ap.hora, "horas": ap.leitura_horas,
                     "fora_janela": ap.leitura_fora_janela, "justificativa": ap.leitura_justificativa} if ap.fase == "leitura" else None),
        "carencia_leite_ate": _iso(ap.carencia_leite_ate), "carencia_carne_ate": _iso(ap.carencia_carne_ate),
        "excecoes": ap_rules._json_lista(ap.excecoes), "animais": emitem, "bloqueados": bloqueados,
        "bloqueado_total": False, "emitido_em": datetime.utcnow().isoformat(),
    }
