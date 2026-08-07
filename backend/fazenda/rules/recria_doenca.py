"""
Vínculo de OcorrenciaClinica/JanelaPontoCritico (texto livre `doenca`) com o
catálogo `Doenca` (fazenda/models/sanidade.py).

Decisão do dono do produto: o que bater por nome (sem acento/caixa) com uma
doença já cadastrada (catálogo global ou o da própria fazenda) vira FK; o que
não bater vira uma `Doenca` NOVA no catálogo DA FAZENDA dona do registro, com
o nome exato que estava no texto livre — nada se perde, nada é renomeado.
`doenca` (texto) nunca é apagado nem sobrescrito: continua sendo o
histórico/fallback de exibição de quem nunca teve o vínculo resolvido.
"""
from __future__ import annotations

import re
import unicodedata

from sqlmodel import Session, select

from fazenda.models import Doenca, JanelaPontoCritico, OcorrenciaClinica, SeedFlag
from fazenda.rules.visibilidade import visivel


def _norm(s: str | None) -> str:
    """Normaliza para casar nomes: sem acento, minúsculo, sem pontuação/
    espaços extras — mesmo critério de fazenda.rules.farmacia._norm."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def resolver_ou_criar_doenca(session: Session, nome: str | None, fazenda_id: int | None) -> int | None:
    """Vincula `nome` (texto livre) a uma linha do catálogo `Doenca`: casa por
    nome normalizado entre o catálogo visível pela fazenda (global + a
    própria, ver rules.visibilidade.visivel); se não achar, CRIA uma Doenca
    nova NA FAZENDA (fazenda_id do registro), com o nome exato informado —
    nunca renomeia, nunca funde com o catálogo de outra fazenda.
    `None` se `nome` vier vazio."""
    nome = (nome or "").strip()
    if not nome:
        return None
    alvo = _norm(nome)
    for d in session.exec(visivel(select(Doenca), Doenca, fazenda_id)).all():
        if _norm(d.nome) == alvo:
            return d.id
    nova = Doenca(nome=nome, fazenda_id=fazenda_id)
    session.add(nova)
    session.commit()
    session.refresh(nova)
    return nova.id


def backfill_doenca_catalogo(session: Session) -> None:
    """Vincula ao catálogo toda linha existente de JanelaPontoCritico/
    OcorrenciaClinica que ainda não tem `doenca_id` (ver
    `resolver_ou_criar_doenca` acima). Roda uma única vez (SeedFlag), mesmo
    padrão das demais rotinas de backfill do boot (ver, por exemplo,
    fazenda.api.routers.estoque.backfill_estoque_semen_generico)."""
    chave = "recria_doenca_catalogo_backfill_v1"
    if session.get(SeedFlag, chave):
        return

    for j in session.exec(select(JanelaPontoCritico).where(JanelaPontoCritico.doenca_id.is_(None))).all():
        j.doenca_id = resolver_ou_criar_doenca(session, j.doenca, j.fazenda_id)
        session.add(j)

    for o in session.exec(select(OcorrenciaClinica).where(OcorrenciaClinica.doenca_id.is_(None))).all():
        o.doenca_id = resolver_ou_criar_doenca(session, o.doenca, o.fazenda_id)
        session.add(o)

    session.add(SeedFlag(chave=chave))
    session.commit()
