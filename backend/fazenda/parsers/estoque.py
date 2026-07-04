"""
Parser do ESTOQUE.csv — inventário de insumos.
9 colunas:
  1 CATEGORIA
  2 Número (código Ideagri)
  3 Nome
  4 Quantidade
  5 Estoque mínimo
  6 Unidade
  7 Valor médio unitário
  8 Valor total
  9 LOCALARMAZENAMENTO (campo "ABAIXO" no contexto → sim/não abaixo do mínimo)
"""
from __future__ import annotations

from fazenda.models import Estoque
from fazenda.parsers.utils import iter_csv_rows, parse_float

# Categorias que indicam hormônio para protocolo IATF
_HORMONIO_CATEGORIAS = frozenset([
    "produtos veterinários - hormônios/similares",
    "produtos veterinarios - hormonios/similares",
])

# Nomes padronizados dos hormônios do protocolo IATF (para referência interna)
HORMONIO_NOMES = {
    "sincrogest": "Sincrogest",
    "cidr": "CIDR",
    "sincrodiol": "Sincrodiol",
    "sincroforte": "Sincroforte",
    "estron": "Estron",
    "sincrocp": "SincroCP",
    "lactotropin": "Lactotropin",
    "boostin": "Lactotropin",
}


def parse_estoque(content: bytes) -> list[Estoque]:
    items: list[Estoque] = []

    for row in iter_csv_rows(content):
        nome = (
            row.get("Nome", "")
            or row.get("PRODUTO", "")
            or row.get("Produto", "")
            or ""
        ).strip()
        if not nome:
            continue

        categoria = (row.get("Categoria", "") or row.get("CATEGORIA", "")).strip()
        qtd_raw = row.get("Quantidade", row.get("QTD", ""))
        est_min_raw = row.get("Estoque mínimo", row.get("Estoque minimo", row.get("EST MÍN", "")))
        vlr_unit_raw = row.get("Valor médio unitário", row.get("Valor unitario", row.get("VLR UNIT", "")))
        vlr_total_raw = row.get("Valor total", row.get("VLR TOTAL", ""))
        abaixo_raw = (row.get("LOCALARMAZENAMENTO", "") or row.get("ABAIXO", "")).strip()

        qtd = parse_float(qtd_raw)
        est_min = parse_float(est_min_raw)
        abaixo = None
        if qtd is not None and est_min is not None:
            abaixo = qtd < est_min
        elif abaixo_raw.lower() in ("sim", "yes", "1", "true"):
            abaixo = True

        item = Estoque(
            categoria=categoria or None,
            numero_produto=row.get("Número", row.get("Numero", row.get("N°", ""))) or None,
            nome=nome,
            quantidade=qtd,
            estoque_minimo=est_min,
            unidade=row.get("Unidade", row.get("UN", "")) or None,
            valor_unitario=parse_float(vlr_unit_raw),
            valor_total=parse_float(vlr_total_raw),
            abaixo_minimo=abaixo,
            local_armazenamento=row.get("LOCALARMAZENAMENTO", "") or None,
        )
        items.append(item)

    return items


def is_hormonio(item: Estoque) -> bool:
    """Retorna True se o item é um hormônio usado no protocolo IATF/BST."""
    cat = (item.categoria or "").lower()
    return cat in _HORMONIO_CATEGORIAS
