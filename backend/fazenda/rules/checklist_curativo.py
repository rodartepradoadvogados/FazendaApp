"""
Checklist do protocolo CURATIVO (tratamento de um animal ou lote — mastite,
vermifugação curativa etc.). Ponto de partida em código, que vale enquanto a
fazenda não tem linhas próprias `tipo="curativo"` em `ChecklistTemplateItem`.

Comportamento por `chave`:
  - "estoque": aviso — nunca bloqueia.
  - "carencia": aviso — nunca bloqueia; o prazo de leite/carne vem do
    catálogo do medicamento (`rules.carencia`), a UI só mostra e pede ciência.
  - "lotes": "cumprido" é só "revisei a tela".

(Extraído de rules/checklist_sanitario.py, que era do sanitário preventivo
antigo e saiu em 2026 — só a parte do curativo ficou.)
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, or_, select

from fazenda.models import ChecklistTemplateItem

TIPO_CURATIVO = "curativo"
CHAVE_CARENCIA = "carencia"

TEMPLATE_PADRAO_CURATIVO: tuple[tuple[str, str, int], ...] = (
    ("estoque", "Estoque suficiente?", 1),
    (CHAVE_CARENCIA, "Carência de leite e carne conferida", 2),
    ("lotes", "Lotes de manejo atuais", 3),
)


@dataclass(frozen=True)
class ItemChecklist:
    chave: str
    nome: str
    ordem: int


def template_curativo(session: Session, fazenda_id: int | None) -> list[ItemChecklist]:
    """Itens ativos do template curativo: globais + os que a fazenda
    personalizou, mesclados por `chave` (a linha da fazenda vence a global).
    Sem nenhuma linha, devolve o padrão em código."""
    query = (
        select(ChecklistTemplateItem)
        .where(ChecklistTemplateItem.tipo == TIPO_CURATIVO)
        .where(ChecklistTemplateItem.ativo == True)  # noqa: E712
        .where(or_(ChecklistTemplateItem.fazenda_id == fazenda_id, ChecklistTemplateItem.fazenda_id.is_(None)))
        .order_by(ChecklistTemplateItem.ordem)
    )
    por_chave: dict[str, ChecklistTemplateItem] = {}
    for item in session.exec(query).all():
        atual = por_chave.get(item.chave)
        if atual is None or (atual.fazenda_id is None and item.fazenda_id is not None):
            por_chave[item.chave] = item
    ordenados = sorted(por_chave.values(), key=lambda i: i.ordem)
    if not ordenados:
        return [ItemChecklist(c, n, o) for c, n, o in TEMPLATE_PADRAO_CURATIVO]
    return [ItemChecklist(i.chave, i.nome, i.ordem) for i in ordenados]
