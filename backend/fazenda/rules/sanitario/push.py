"""
Push das notas do sanitário pela infraestrutura existente (Web Push + FCM,
`fazenda/api/routers/push.py::enviar_push`).

Destinatários (modelo_v1 §12/§13):
  - "aglomerou"                          -> administradores da fazenda (se a caixa
                                            tiver `push_admin`);
  - "véspera"                            -> todos os usuários do app da fazenda;
  - prazo legal / comprovação (180 d) e
    "celular offline 24 h"               -> administradores.

Cada nota sai UMA vez: `push_enviado_em` é carimbado (e comitado) ANTES do
envio — mesma razão de `push.notificar_push_para_itens`: se o envio cair no
meio, o pior caso é um aviso a menos, nunca a mesma nota repetida a cada
volta do loop. Nota resolvida não vai.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional

from sqlmodel import Session, select

logger = logging.getLogger(__name__)

TIPOS_PUSH = {
    "aglomerou": "admins",
    "vespera": "todos",
    "prazo_legal": "admins",
    "celular_offline": "admins",
}
# Central de Protocolos › Aplicar › Sanitário › Preventivo (esquema de URL em
# frontend/lib/protocolosNavegacao.ts; o antigo "?aba=vacinas" continua aceito
# pelo site como atalho, para push já entregue).
URL_APLICAR_PREVENTIVO = "/protocolos?aba=aplicar&area=sanitario&san=preventivo"
URL_POR_TIPO = {
    "aglomerou": URL_APLICAR_PREVENTIVO,  # com caixa: &caixas=<id> abre "Marcar" com ela (ver url_da_nota)
    "vespera": "/app/menu#vacinacao",  # com dia: /app/menu#vacinacao-<id> (ver url_da_nota)
    "prazo_legal": "/sanidade?aba=preventiva",
    "celular_offline": "/agenda",
}


def url_da_nota(n) -> str:
    """URL do push. A véspera abre o DIA direto no app (Menu › Vacinas e exames,
    "#vacinacao-<id do dia>", que o app já entende) — não depende do título.
    As notas de administrador seguem para as telas do site (/agenda etc.);
    "aglomerou" abre a Central já em "Marcar" com a caixa (o site descobre se
    é Vacina, Exame ou Outros pela própria caixa)."""
    if n.tipo == "vespera" and n.dia_id:
        return f"/app/menu#vacinacao-{n.dia_id}"
    if n.tipo == "aglomerou" and getattr(n, "caixa_id", None):
        return f"{URL_APLICAR_PREVENTIVO}&caixas={n.caixa_id}"
    return URL_POR_TIPO.get(n.tipo, "/agenda")


def _destinatarios(session: Session, fazenda_id: int, publico: str) -> set[int]:
    from fazenda.rules.sanitario.permissoes import admins_da_fazenda, usuarios_da_fazenda

    return usuarios_da_fazenda(session, fazenda_id) if publico == "todos" else admins_da_fazenda(session, fazenda_id)


def despachar_push_notas(session: Session, fazenda_id: int,
                         enviar: Optional[Callable[..., None]] = None) -> int:
    """Envia o push das notas novas desta fazenda. Faz o próprio commit da
    marca (rotina de fundo). Devolve quantas notas foram marcadas."""
    from fazenda.models import SanitarioCaixaVersao, SanitarioCaixa, SanitarioNotaAgenda

    if enviar is None:
        from fazenda.api.routers.push import enviar_push as enviar
    notas = session.exec(select(SanitarioNotaAgenda).where(
        SanitarioNotaAgenda.fazenda_id == fazenda_id, SanitarioNotaAgenda.push_enviado_em == None,  # noqa: E711
        SanitarioNotaAgenda.resolvida_em == None,  # noqa: E711
        SanitarioNotaAgenda.tipo.in_(tuple(TIPOS_PUSH)),
    ).order_by(SanitarioNotaAgenda.id)).all()
    envios: list[tuple] = []
    for n in notas:
        if n.tipo == "aglomerou" and n.caixa_id:
            cx = session.get(SanitarioCaixa, n.caixa_id)
            v = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx and cx.versao_atual_id else None
            if v is not None and not v.push_admin:
                n.push_enviado_em = datetime.utcnow()  # sem push por escolha da caixa: marca para não reavaliar
                session.add(n)
                continue
        n.push_enviado_em = datetime.utcnow()
        session.add(n)
        for uid in _destinatarios(session, fazenda_id, TIPOS_PUSH[n.tipo]):
            envios.append((uid, n.titulo, n.texto or n.titulo, url_da_nota(n)))
    session.commit()
    for uid, titulo, corpo, url in envios:
        try:
            enviar(usuario_id=uid, titulo=titulo, corpo=corpo, url=url, session=session, categoria="comunicado")
        except Exception:  # nunca derruba a rotina
            logger.exception("sanitario: push da nota falhou (usuário %s)", uid)
    return len(notas)
