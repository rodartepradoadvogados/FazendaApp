"""
Fonte de tarefas da Agenda vinda das Lidas (tarefas gerais da fazenda que não
são protocolo de animal — ver fazenda/models/lida.py). Mesma arquitetura de
fazenda/rules/protocolo_customizado.py (fonte ADITIVA, um evento por
(lançamento, dia) — ver eventos_agenda), com uma diferença: marcar realizado
aqui PODE dar baixa de estoque de verdade (Lida.dar_baixa_estoque), não só
registrar o insumo como informativo — o insumo de uma Lida tem dose/unidade
justamente para isso (o do Protocolo Customizado não tem, de propósito).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from fazenda.models import Lida, LidaAplicacao, LidaLancamento
from fazenda.ordenacao import chave_numero
from fazenda.rules import estoque_baixa
from fazenda.rules.nomenclatura_protocolo import nome_curto

# Mesma janela das demais famílias com cronograma — ver JANELA_ATRASO_DIAS em
# fazenda/rules/protocolo_customizado.py.
JANELA_ATRASO_DIAS = 30

PREFIXO_EVENTO = "lida_"


def chave_evento(lancamento_id: int, dia: int) -> str:
    return f"{PREFIXO_EVENTO}{lancamento_id}_{dia}"


def eventos_agenda(
    session: Session, data: date, realizados: set[str], fazenda_id: int | None = None,
) -> list[dict]:
    """Eventos da Agenda das lidas ativas, agrupados por (lançamento, dia)."""
    limite = data - timedelta(days=JANELA_ATRASO_DIAS)

    query_lanc = select(LidaLancamento).where(
        LidaLancamento.ativo == True,  # noqa: E712
        LidaLancamento.encerrado_em.is_(None),
    )
    if fazenda_id is not None:
        query_lanc = query_lanc.where(LidaLancamento.fazenda_id == fazenda_id)
    lancamentos_por_id = {l.id: l for l in session.exec(query_lanc).all()}
    if not lancamentos_por_id:
        return []

    aplicacoes = session.exec(
        select(LidaAplicacao).where(
            LidaAplicacao.realizada == False,  # noqa: E712
            LidaAplicacao.data_prevista >= limite,
            LidaAplicacao.lancamento_id.in_(tuple(lancamentos_por_id)),
        )
    ).all()

    grupos: dict[tuple[int, int], list[LidaAplicacao]] = {}
    for ap in aplicacoes:
        grupos.setdefault((ap.lancamento_id, ap.dia), []).append(ap)

    saida: list[dict] = []
    for (lancamento_id, dia), aps in grupos.items():
        chave = chave_evento(lancamento_id, dia)
        if chave in realizados:
            continue
        lancamento = lancamentos_por_id.get(lancamento_id)
        if not lancamento:
            continue
        animais_grupo = sorted((a.numero_matriz for a in aps if a.numero_matriz), key=chave_numero)

        saida.append({
            "id": chave,
            "data": aps[0].data_prevista.isoformat(),
            "categoria": "Atividades",
            "descricao": f"{nome_curto(lancamento.nome_protocolo)} — {aps[0].descricao}",
            "numero_animal": animais_grupo[0] if len(animais_grupo) == 1 else None,
            "observacao": aps[0].insumo,
            "fonte": "manual",
            "cor": "var(--dourado)",
            "ref": None,
            "tipo": "lida",
            "dia": dia - lancamento.dia_inicial,
            "animais": animais_grupo,
            "protocolo": lancamento.nome_protocolo,
            "insumo": aps[0].insumo,
            "lote": lancamento.lote,
            "foto_obrigatoria": aps[0].foto_obrigatoria,
            "foto_url": aps[0].foto_url,
        })
    return saida


def marcar_realizado(
    session: Session, evento_id: str, animais: list[str] | None = None,
    data_realizacao: date | None = None, fazenda_id: int | None = None, usuario_id: int | None = None,
) -> list[str]:
    """Marca as aplicações de um grupo (lançamento, dia) como realizadas —
    mesmo contrato de fazenda.rules.protocolo_customizado.marcar_realizado.
    Se a Lida tem dar_baixa_estoque=True e o insumo tem dose/unidade, dá
    baixa de estoque de verdade: dose × nº de aplicações confirmadas AGORA
    (mesmo princípio de _marcar_protocolo_iatf_realizado — dose × nº de
    vacas — generalizado pra quando não há animal nenhum envolvido)."""
    resto = evento_id.removeprefix(PREFIXO_EVENTO)
    lancamento_id_str, dia_str = resto.rsplit("_", 1)
    lancamento_id, dia = int(lancamento_id_str), int(dia_str)

    query = select(LidaAplicacao).where(
        LidaAplicacao.lancamento_id == lancamento_id,
        LidaAplicacao.dia == dia,
        LidaAplicacao.realizada == False,  # noqa: E712
    )
    # BUG DE SEGURANÇA CORRIGIDO: sem este filtro, qualquer fazenda-cliente
    # podia confirmar a lida de outro tenant (e consumir o próprio estoque
    # numa tarefa que não é dela) só adivinhando o lancamento_id.
    if fazenda_id is not None:
        query = query.where(LidaAplicacao.fazenda_id == fazenda_id)
    aplicacoes = session.exec(query).all()
    if animais is not None:
        alvo = set(animais)
        aplicacoes = [a for a in aplicacoes if a.numero_matriz in alvo]
    if not aplicacoes:
        return []

    quando = data_realizacao or date.today()
    for ap in aplicacoes:
        ap.realizada = True
        ap.data_realizacao = quando
        session.add(ap)

    avisos: list[str] = []
    lancamento = session.get(LidaLancamento, lancamento_id)
    lida = session.get(Lida, lancamento.lida_id) if lancamento else None
    primeira = aplicacoes[0]
    if lida and lida.dar_baixa_estoque and primeira.insumo and primeira.insumo_dose:
        estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=primeira.insumo)
        total = primeira.insumo_dose * len(aplicacoes)
        avisos.extend(estoque_baixa.baixar(
            session, item=estoque_item, quantidade=total, unidade=primeira.insumo_unidade, data=quando,
            fazenda_id=fazenda_id, observacao=f"{lancamento.nome_protocolo} — D{dia - lancamento.dia_inicial}",
            usuario_id=usuario_id, origem_tipo="lida", origem_id=lancamento_id, produto=primeira.insumo,
        ))
    session.commit()
    return avisos


def desmarcar_realizado(session: Session, evento_id: str, fazenda_id: int | None = None) -> None:
    """Reverte o grupo inteiro — mesma justificativa de
    _desmarcar_protocolo_iatf_realizado. NÃO estorna estoque: essa é a mesma
    convenção da Central de Protocolos (o estorno mora só em cancelar(), que
    usa o rastro origem_tipo/origem_id — desmarcar um único dia pela Agenda é
    uma correção pontual, não um cancelamento do lançamento inteiro)."""
    resto = evento_id.removeprefix(PREFIXO_EVENTO)
    lancamento_id_str, dia_str = resto.rsplit("_", 1)
    lancamento_id, dia = int(lancamento_id_str), int(dia_str)

    query = select(LidaAplicacao).where(
        LidaAplicacao.lancamento_id == lancamento_id,
        LidaAplicacao.dia == dia,
        LidaAplicacao.realizada == True,  # noqa: E712
    )
    if fazenda_id is not None:
        query = query.where(LidaAplicacao.fazenda_id == fazenda_id)
    aplicacoes = session.exec(query).all()
    for ap in aplicacoes:
        ap.realizada = False
        ap.data_realizacao = None
        session.add(ap)
    session.commit()
