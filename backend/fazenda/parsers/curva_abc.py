"""
Parser da CURVA_ABC.csv — classificação A/B/C de produtos/serviços por valor de
compra (análise de Pareto). Arquivo Ideagri: Windows-1252, separador ';'.
Colunas: Item; Classificação; Produto/Serviço; UN; Preço unitário; Qtde;
Vlr. da compra; Valor da compra acumulado; % sobre valor total acumulado;
% sobre valor total.
"""
from __future__ import annotations

from fazenda.models import CurvaABC
from fazenda.parsers.utils import iter_csv_rows, parse_float, parse_int


def _get(row: dict, *chaves: str) -> str:
    for c in chaves:
        for k, v in row.items():
            if k.strip().lower().startswith(c.lower()):
                return v
    return ""


def parse_curva_abc(content: bytes) -> list[CurvaABC]:
    linhas: list[CurvaABC] = []
    for row in iter_csv_rows(content):
        produto = _get(row, "Produto").strip()
        classif = _get(row, "Classifica").strip()
        if not produto and not classif:
            continue
        linhas.append(CurvaABC(
            item=parse_int(_get(row, "Item")),
            classificacao=classif or None,
            produto=produto or None,
            unidade=(_get(row, "UN").strip() or None),
            preco_unitario=parse_float(_get(row, "Preço unit", "Preco unit")),
            quantidade=parse_float(_get(row, "Qtde")),
            valor_compra=parse_float(_get(row, "Vlr. da compra", "Vlr da compra")),
            valor_acumulado=parse_float(_get(row, "Valor da compra acumulado")),
            perc_acumulado=parse_float(_perc(row, acumulado=True)),
            perc_total=parse_float(_perc(row, acumulado=False)),
        ))
    return linhas


def _perc(row: dict, acumulado: bool) -> str:
    """Distingue as duas colunas de '%': a acumulada e a do valor total."""
    for k, v in row.items():
        kl = k.strip().lower()
        if kl.startswith("% sobre valor total") and ("acumulado" in kl) == acumulado:
            return v
    return ""
