"""
Router de notificações — agrega, para o dia atual, tudo que é relevante para
o usuário logado (eventos da agenda, contas a pagar, pendências de exclusão),
filtrando por módulo/permissão. Alimenta o sininho fixo do topo.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.api.routers.agenda import calcular_agenda
from fazenda.api.routers.alertas_indicador import condicao_atendida, descricao_alerta, valor_indicador
from fazenda.api.routers.indicadores import calcular_indicadores_fazenda
from fazenda.api.routers.push import notificar_push_para_itens
from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import AlertaIndicador, PortalMensagem, SolicitacaoExclusao, Usuario

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notificacoes", tags=["notificacoes"])


def montar_itens_notificacoes(user: Usuario, session: Session, fazenda_id: int | None = None) -> list[dict]:
    """A lógica de "quando avisar" do sininho — inalterada. Extraída para
    função própria só para ser reaproveitada também pela varredura periódica
    de push (fazenda/api/routers/push.py:despachar_push_pendentes), sem
    duplicar nada: o endpoint /notificacoes/ abaixo chama exatamente esta
    mesma função.

    `fazenda_id` PRECISA vir explícito do chamador: como esta função nunca é
    invocada como rota HTTP (é chamada como função Python comum, direto ou
    via despachar_push_pendentes), o `Depends(get_fazenda_atual_id)" de
    calcular_agenda nunca é resolvido pelo FastAPI aqui — sem passar o valor
    de propósito, ele fica com o próprio marcador Depends(...) como "valor",
    que fazenda_id_seguro() trata como None (sem filtro), misturando dados de
    TODAS as fazendas no sino/push (bug real encontrado em produção)."""
    hoje = date.today()
    itens: list[dict] = []

    # calcular_agenda já filtra os eventos pela permissão do usuário (ver
    # MODULO_POR_CATEGORIA em agenda.py) — não precisa repetir o filtro aqui.
    agenda = calcular_agenda(data=hoje, dias=0, session=session, usuario=user, fazenda_id=fazenda_id)
    for e in agenda["eventos"]:
        if e["data"] != hoje.isoformat():
            continue
        itens.append({
            "tipo": "agenda",
            "categoria": e["categoria"],
            "descricao": e["descricao"],
            "numero_animal": e["numero_animal"],
            "cor": e["cor"],
            # nº do lançamento (ex.: conta a pagar) — quando presente, o sino
            # leva direto pra ele em vez de só abrir a tela genérica do módulo
            # (mesmo "ref" que a Agenda já usa no link "Ir para Financeiro").
            "ref": e.get("ref"),
            # id/tipo do evento de agenda por trás deste item — "tipo" acima
            # fica fixo em "agenda" de propósito (título do push por canal,
            # ver push.py::_categoria_push); estes dois campos são o que
            # permite ao sino/push abrir a AÇÃO certa (ex.: a janela de
            # "Ver sugestão" de mudança de lote), em vez de só cair na tela
            # genérica do módulo sem achar o item — ver #sugestão-de-lote-presa.
            "evento_id": e.get("id"),
            "evento_tipo": e.get("tipo"),
        })

    if user.papel == "admin":
        query_pendentes = select(SolicitacaoExclusao).where(SolicitacaoExclusao.status == "pendente")
        if fazenda_id is not None:
            query_pendentes = query_pendentes.where(SolicitacaoExclusao.fazenda_id == fazenda_id)
        pendentes = session.exec(query_pendentes).all()
        for p in pendentes:
            itens.append({
                "tipo": "exclusao_pendente",
                "categoria": "Aprovação pendente",
                "descricao": f"Exclusão de {p.titulo or f'{p.tipo} #{p.id_alvo}'} — solicitada por {p.solicitado_por or '—'}",
                "numero_animal": None,
                "cor": "var(--amber)",
            })

    # Portal > Comunicação: mensagens/tarefas recebidas que ainda não
    # desapareceram (ver regra de permanência em PortalMensagem).
    portal_pendentes = session.exec(
        select(PortalMensagem).where(
            PortalMensagem.destinatario_usuario_id == user.id,
            PortalMensagem.resolvida == False,  # noqa: E712
        )
    ).all()
    for m in portal_pendentes:
        if m.lida and not m.pede_retorno:
            continue
        remetente = session.get(Usuario, m.remetente_usuario_id)
        remetente_nome = (remetente.nome or remetente.username) if remetente else "—"
        if m.tipo == "tarefa":
            descricao = f"Tarefa de {remetente_nome}: {m.corpo}"
            cor = "var(--mob-vinho-fixo)"
        elif m.tipo == "foto":
            descricao = f"Foto de {remetente_nome}: {m.corpo}"
            cor = "var(--verde)"
        else:
            descricao = f"Mensagem de {remetente_nome}" + (f" ({m.aba})" if m.aba else "") + f": {m.corpo}"
            cor = "var(--blue)"
        itens.append({
            # tipo continua "portal_mensagem" (não "foto") propositalmente:
            # push.py::_categoria_push e url_destino já tratam esse tipo
            # ("Comunicados" → /portal) sem precisar de nenhuma alteração lá.
            "tipo": "portal_mensagem",
            "categoria": "Portal",
            "descricao": descricao,
            "numero_animal": None,
            "cor": cor,
            "portal_mensagem_id": m.id,
            "pede_retorno": m.pede_retorno,
            "foto_campo_id": m.foto_campo_id,
        })

    # Alertas de indicador (Configurações > Indicadores > Meus alertas) —
    # cada alerta guarda a fazenda em que foi criado; calcula-se o indicador
    # daquela fazenda especificamente (não da fazenda "atual" da sessão, que
    # pode ter mudado desde a criação do alerta).
    alertas = session.exec(
        select(AlertaIndicador).where(AlertaIndicador.usuario_id == user.id, AlertaIndicador.ativo == True)  # noqa: E712
    ).all()
    cache_resultados: dict[int | None, dict] = {}
    for alerta in alertas:
        if alerta.fazenda_id not in cache_resultados:
            cache_resultados[alerta.fazenda_id] = calcular_indicadores_fazenda(session, alerta.fazenda_id)
        valor = valor_indicador(cache_resultados[alerta.fazenda_id], alerta.indicador_chave)
        if valor is None or not condicao_atendida(valor, alerta.operador, alerta.valor_limite):
            continue
        itens.append({
            "tipo": "alerta_indicador",
            "categoria": "Indicadores",
            "descricao": descricao_alerta(alerta, valor),
            "numero_animal": None,
            "cor": "var(--amber)",
        })

    return itens


@router.get("/")
def notificacoes_hoje(
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    itens = montar_itens_notificacoes(user, session, fazenda_id)

    # Rewire do push (#web-push): MESMOS itens que o sino já decidiu mostrar
    # — só adiciona o canal de entrega novo (notificação nativa do
    # navegador), deduplicado por dia, para quem tiver subscription ativa.
    # Nunca deixa uma falha aqui derrubar o carregamento do sino.
    try:
        notificar_push_para_itens(user.id, itens, session)
    except Exception:
        logger.exception("Falha ao despachar push a partir de /notificacoes/")

    return {"itens": itens, "total": len(itens)}
