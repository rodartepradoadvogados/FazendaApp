"""
Categoria (medicamento) e Classificação do medicamento — dois eixos de tag
multi-valor (cumulativos, sem "principal") sobre MedicamentoComercial
(catálogo do Painel CowData) e Estoque (item do tenant). Pedido do usuário
(01/09/2026): "tanto princípio ativo, categoria e classificação do
medicamento pode ser cumulativo, podendo cadastrar mais de 1."

Mesmo espírito de rules/farmacia_multi_principio.py, mas sem conceito de
"principal" — uma tag não é mais importante que outra, é só um rótulo a
mais. Implementado como um par de funções genéricas (recebem a classe da
tabela de junção e os nomes dos dois campos de FK) reaproveitado pelos dois
eixos, em vez de duplicar a lógica duas vezes.
"""
from __future__ import annotations

from sqlmodel import Session, select


def definir_tags(session: Session, junction_model, dono_campo: str, dono_id: int, tag_campo: str, tag_ids: list[int]) -> None:
    """Substitui as tags ligadas a `dono_id` (medicamento ou item de estoque)
    pela lista informada — idempotente, nunca duplica, remove o que não foi
    citado desta vez. Lista vazia é permitida (categoria/classificação são
    opcionais, ao contrário de princípio ativo)."""
    ids_unicos = list(dict.fromkeys(tag_ids))
    existentes = session.exec(
        select(junction_model).where(getattr(junction_model, dono_campo) == dono_id)
    ).all()
    existentes_por_tag = {getattr(v, tag_campo): v for v in existentes}
    for tid in ids_unicos:
        if existentes_por_tag.pop(tid, None) is not None:
            continue
        session.add(junction_model(**{dono_campo: dono_id, tag_campo: tid}))
    for sobra in existentes_por_tag.values():
        session.delete(sobra)


def tags_de(session: Session, junction_model, dono_campo: str, dono_id: int, tag_campo: str) -> list[int]:
    """Ids das tags ligadas a `dono_id`, na ordem em que foram cadastradas
    (a primeira é a que se espelha em campos escalares legados, quando existir)."""
    vinculos = session.exec(
        select(junction_model).where(getattr(junction_model, dono_campo) == dono_id).order_by(junction_model.id)
    ).all()
    return [getattr(v, tag_campo) for v in vinculos]
