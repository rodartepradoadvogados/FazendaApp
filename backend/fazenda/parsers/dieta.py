"""
Parser do DIETA.csv — plano alimentar por lote (formato largo → longo).

Formato de origem (uma linha por lote):
  Lote;Categoria;Qtde Silagem (kg);Qtde de Teck Milk 24% (kg);...;Qtde de Leite (L)

Saída: uma linha Dieta por (lote, ingrediente) com quantidade > 0.
A unidade (kg ou L) é extraída do próprio cabeçalho da coluna.
"""
from __future__ import annotations

import re

from fazenda.models import Dieta
from fazenda.parsers.utils import iter_csv_rows, parse_float, parse_int

# Colunas que não são ingredientes.
_NAO_INGREDIENTE = {"lote", "categoria"}


def _nome_ingrediente(coluna: str) -> tuple[str, str | None]:
    """
    'Qtde de Teck Milk 24% (kg)' -> ('Teck Milk 24%', 'kg')
    'Qtde Silagem (kg)'          -> ('Silagem', 'kg')
    'Qtde de Leite (L)'          -> ('Leite', 'L')
    """
    unidade = None
    m = re.search(r"\(([^)]+)\)\s*$", coluna)
    if m:
        unidade = m.group(1).strip()
    nome = re.sub(r"\([^)]*\)\s*$", "", coluna).strip()
    nome = re.sub(r"^Qtde\s+(de\s+)?", "", nome, flags=re.IGNORECASE).strip()
    return nome, unidade


def parse_dieta(content: bytes) -> list[Dieta]:
    itens: list[Dieta] = []

    for row in iter_csv_rows(content):
        lote = parse_int(row.get("Lote", ""))
        categoria = (row.get("Categoria", "") or "").strip() or None

        for coluna, valor in row.items():
            if coluna.strip().lower() in _NAO_INGREDIENTE:
                continue
            qtd = parse_float(valor)
            if not qtd or qtd <= 0:
                continue  # ingrediente não usado nesse lote
            nome, unidade = _nome_ingrediente(coluna)
            if not nome:
                continue
            itens.append(
                Dieta(
                    lote=lote,
                    categoria=categoria,
                    ingrediente=nome,
                    quantidade=qtd,
                    unidade=unidade,
                )
            )

    return itens
