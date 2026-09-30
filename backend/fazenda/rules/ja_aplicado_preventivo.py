"""Animal que JÁ recebeu o produto da regra dentro do ciclo/frequência dela.

Relato do dono (teste no ar): "no momento da aplicação não se detectou que eu já
tinha aplicado a vacina nesses animais, e continuam na lista de espera / no
agendamento". A aplicação pode ter sido lançada por OUTRO caminho — Lançamentos
(antigo), Sanidade legada/importada, protocolo agrupado, curral — e todos eles
terminam numa linha de `Sanidade`; é ela a fonte da verdade aqui (o registro do
próprio agendamento também grava `Sanidade`, e o estorno a apaga).

Janela ("ciclo/frequência"):
  * regra por ÉPOCA (e por frequência): da data devida da ocorrência menos UMA
    frequência da regra até hoje/data da aplicação (o mesmo critério do dedupe
    da rotina — `cronograma_sanitario._inicio_do_ciclo`);
  * regra por EVENTO DE VIDA: da data do gatilho daquele animal (nascimento,
    parto, secagem…) até hoje; sem gatilho computável, uma frequência para trás.

"Mesmo produto/protocolo": nome do produto da regra (ou o padrão do protocolo),
os itens de estoque do mesmo princípio ativo, ou a observação de uma aplicação
preventiva deste mesmo protocolo. Exame fica de fora (fluxo próprio, com reteste).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from sqlmodel import Session, select

from fazenda.models import CalendarioSanitario, Estoque, EventoSanitario, Sanidade
from fazenda.rules.calendario_sanitario import _somar_meses

_AGENDAMENTO_OBS = re.compile(r"\(agendamento #\d+, ([^)]+)\)")


def _norm(s: str | None) -> str:
    t = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def fmt_data(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _menos_uma_frequencia(ref: date, calendario: CalendarioSanitario) -> date:
    n, un = calendario.frequencia_valor or 0, calendario.frequencia_unidade or "dias"
    if not n:
        return ref
    if un == "dias":
        return ref - timedelta(days=n)
    return _somar_meses(ref, -(n * 12 if un == "anos" else n))


def _nomes_do_produto(session: Session, calendario: CalendarioSanitario, evento: EventoSanitario | None) -> set[str]:
    nomes = {_norm(calendario.produto), _norm(evento.produto_padrao if evento else None)} - {""}
    if not nomes:
        return set()
    # Outras marcas/itens do MESMO princípio ativo (ex.: lançamento antigo com o nome comercial).
    query = select(Estoque)
    if calendario.fazenda_id is not None:
        query = query.where(Estoque.fazenda_id == calendario.fazenda_id)
    itens = session.exec(query).all()
    pas = {i.principio_ativo_id for i in itens if _norm(i.nome) in nomes and i.principio_ativo_id}
    if pas:
        nomes |= {_norm(i.nome) for i in itens if i.principio_ativo_id in pas}
    return nomes


def _fonte(s: Sanidade) -> str:
    m = _AGENDAMENTO_OBS.search(s.obs or "")
    if m:
        return f"Protocolo preventivo · {m.group(1)}"
    if s.protocolo_sanitario_lancamento_id:
        return "Protocolo sanitário"
    if s.natureza == "preventivo":
        return "Lançamento preventivo"
    if s.usuario_id:
        return "Lançamento em Sanidade"
    return "Histórico de Sanidade"


def _desde_por_animal(
    session: Session, calendario: CalendarioSanitario, evento: EventoSanitario | None, numeros: list[str],
    hoje: date, desde_epoca: date | None,
) -> dict[str, date]:
    """Início da janela de cada animal."""
    fallback = desde_epoca or _menos_uma_frequencia(hoje, calendario)
    if evento is not None and evento.tipo_agendamento == "evento" and evento.gatilho:
        from fazenda.rules.eventos_sanitarios import _datas_gatilho
        gat: dict[str, date] = {}
        for numero, quando in _datas_gatilho(
            session, evento.gatilho, evento.gatilho_lote, evento.gatilho_idade_meses, 0, evento.sexo_alvo,
            calendario.fazenda_id,
        ):
            atual = gat.get(numero)
            if atual is None or (quando <= hoje and (atual > hoje or quando > atual)):
                gat[numero] = quando   # ocorrência mais recente que já passou
        return {n: gat.get(n, fallback) for n in numeros}
    return {n: fallback for n in numeros}


def aplicacoes_no_ciclo(
    session: Session, calendario: CalendarioSanitario, numeros: list[str], *, hoje: date,
    devida: date | None = None, ate: date | None = None, evento: EventoSanitario | None = None,
) -> dict[str, dict]:
    """{numero: {data, produto, sanidade_id, fonte}} com a aplicação MAIS RECENTE
    do produto/protocolo da regra dentro da janela de cada animal. `devida` =
    data devida da ocorrência (regra por época). Vazio para exame."""
    if not numeros:
        return {}
    if evento is None:
        evento = session.get(EventoSanitario, calendario.evento_sanitario_id)
    if evento is not None and evento.categoria_preventiva == "exame":
        return {}
    nomes = _nomes_do_produto(session, calendario, evento)
    marca_protocolo = f"preventivo: {_norm(evento.nome)}" if evento is not None else None
    if not nomes and not marca_protocolo:
        return {}
    ate = ate or hoje
    desde_epoca = _menos_uma_frequencia(devida, calendario) if devida is not None else None
    desde = _desde_por_animal(session, calendario, evento, list(numeros), hoje, desde_epoca)
    minimo = min(desde.values())
    query = (
        select(Sanidade)
        .where(Sanidade.numero_matriz.in_(list(numeros)))
        .where(Sanidade.data_aplicacao >= minimo)
        .where(Sanidade.data_aplicacao <= ate)
    )
    if calendario.fazenda_id is not None:
        query = query.where(Sanidade.fazenda_id == calendario.fazenda_id)
    achados: dict[str, dict] = {}
    for s in session.exec(query.order_by(Sanidade.data_aplicacao.desc(), Sanidade.id.desc())).all():
        if s.data_aplicacao is None or s.data_aplicacao < desde.get(s.numero_matriz, minimo):
            continue
        casa = _norm(s.produto) in nomes or bool(marca_protocolo and marca_protocolo in _norm(s.obs))
        if not casa or s.numero_matriz in achados:
            continue
        achados[s.numero_matriz] = {
            "data": s.data_aplicacao, "produto": s.produto, "sanidade_id": s.id, "fonte": _fonte(s),
        }
    return achados


def texto_ja_aplicado(info: dict) -> str:
    return f"Já aplicado em {fmt_data(info['data'])} ({info['produto']}) — {info['fonte']}"
