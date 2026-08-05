"""
Fonte de tarefas da Agenda vinda dos protocolos personalizados do usuário
(Configurações > Cadastro > Protocolos personalizados).

Fonte ADITIVA: `eventos_agenda` devolve uma lista de dicts no mesmo formato
dos outros blocos de calcular_agenda (ver fazenda/api/routers/agenda.py) e é
apenas concatenada em `eventos_visiveis`. Não toca no AgendaEngine nem em
nenhuma regra existente — mesmo espírito de fazenda/rules/eventos_sanitarios.py,
a única outra fonte da Agenda já externalizada num módulo de regras próprio.

Ao contrário do protocolo sanitário/indução de lactação, marcar um evento
como realizado aqui NÃO gera Sanidade nem baixa de estoque — o insumo do
protocolo personalizado é texto livre, informativo (quem precisa de baixa
automática com rastreio usa o Protocolo sanitário)."""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from fazenda.rules.nomenclatura_protocolo import nome_curto
from fazenda.models import ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento
from fazenda.ordenacao import chave_numero

# Etapas vencidas ainda aparecem como pendência por até 30 dias — o produtor
# precisa saber que perdeu o dia, mas um lançamento abandonado não pode
# poluir a Agenda para sempre. Mesma ordem de grandeza das janelas de
# colostragem (30) e confirmação de cura (60) já usadas em calcular_agenda.
JANELA_ATRASO_DIAS = 30

PREFIXO_EVENTO = "protocolo_customizado_"


def chave_evento(lancamento_id: int, dia: int) -> str:
    """Chave estável do evento — um evento por (lançamento, dia), agrupando
    todos os animais daquele passo (mesmo agrupamento de IATF/indução)."""
    return f"{PREFIXO_EVENTO}{lancamento_id}_{dia}"


def eventos_agenda(
    session: Session, data: date, realizados: set[str], fazenda_id: int | None = None,
) -> list[dict]:
    """Eventos da Agenda dos protocolos personalizados ativos, agrupados por
    (lançamento, dia). `fazenda_id` já deve vir resolvido por
    fazenda_id_seguro() — None escopa para todas (token legado)."""
    limite = data - timedelta(days=JANELA_ATRASO_DIAS)

    query_lanc = select(ProtocoloCustomizadoLancamento).where(ProtocoloCustomizadoLancamento.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_lanc = query_lanc.where(ProtocoloCustomizadoLancamento.fazenda_id == fazenda_id)
    lancamentos_por_id = {l.id: l for l in session.exec(query_lanc).all()}
    if not lancamentos_por_id:
        return []

    aplicacoes = session.exec(
        select(ProtocoloCustomizadoAplicacao).where(
            ProtocoloCustomizadoAplicacao.realizada == False,  # noqa: E712
            ProtocoloCustomizadoAplicacao.data_prevista >= limite,
            ProtocoloCustomizadoAplicacao.lancamento_id.in_(tuple(lancamentos_por_id)),
        )
    ).all()

    grupos: dict[tuple[int, int], list[ProtocoloCustomizadoAplicacao]] = {}
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

        observacao_partes = []
        if aps[0].insumo:
            observacao_partes.append(aps[0].insumo)
        if aps[0].observacao:
            observacao_partes.append(aps[0].observacao)
        observacao = " — ".join(observacao_partes) or None

        saida.append({
            "id": chave,
            "data": aps[0].data_prevista.isoformat(),
            "categoria": lancamento.categoria,
            "descricao": f"{nome_curto(lancamento.nome_protocolo)} — D{dia - lancamento.dia_inicial} — {aps[0].descricao}",
            "numero_animal": animais_grupo[0] if len(animais_grupo) == 1 else None,
            "observacao": observacao,
            "fonte": "manual",
            "cor": "var(--dourado)",
            "ref": None,
            "tipo": "protocolo_customizado",
            "dia": dia - lancamento.dia_inicial,
            "animais": animais_grupo,
            "protocolo": lancamento.nome_protocolo,
            "insumo": aps[0].insumo,
            "lote": lancamento.lote,
        })
    return saida


def marcar_realizado(session: Session, evento_id: str, animais: list[str] | None = None) -> None:
    """Marca as aplicações de um grupo (lançamento, dia) como realizadas.
    Sem `animais`, marca o grupo inteiro; com `animais`, só esse subconjunto."""
    resto = evento_id.removeprefix(PREFIXO_EVENTO)
    lancamento_id_str, dia_str = resto.rsplit("_", 1)
    lancamento_id, dia = int(lancamento_id_str), int(dia_str)

    aplicacoes = session.exec(
        select(ProtocoloCustomizadoAplicacao).where(
            ProtocoloCustomizadoAplicacao.lancamento_id == lancamento_id,
            ProtocoloCustomizadoAplicacao.dia == dia,
            ProtocoloCustomizadoAplicacao.realizada == False,  # noqa: E712
        )
    ).all()
    if animais is not None:
        alvo = set(animais)
        aplicacoes = [a for a in aplicacoes if a.numero_matriz in alvo]

    hoje = date.today()
    for ap in aplicacoes:
        ap.realizada = True
        ap.data_realizacao = hoje
        session.add(ap)
    session.commit()


def desmarcar_realizado(session: Session, evento_id: str) -> None:
    """Reverte o grupo inteiro (sem registro de qual subconjunto foi
    confirmado, reverter tudo é o único comportamento coerente) — mesma
    justificativa de _desmarcar_protocolo_iatf_realizado."""
    resto = evento_id.removeprefix(PREFIXO_EVENTO)
    lancamento_id_str, dia_str = resto.rsplit("_", 1)
    lancamento_id, dia = int(lancamento_id_str), int(dia_str)

    aplicacoes = session.exec(
        select(ProtocoloCustomizadoAplicacao).where(
            ProtocoloCustomizadoAplicacao.lancamento_id == lancamento_id,
            ProtocoloCustomizadoAplicacao.dia == dia,
            ProtocoloCustomizadoAplicacao.realizada == True,  # noqa: E712
        )
    ).all()
    for ap in aplicacoes:
        ap.realizada = False
        ap.data_realizacao = None
        session.add(ap)
    session.commit()
