"""
RMCA — Receita Menos Custo com Alimentação. Duas versões lado a lado:
gerencial (a partir dos lançamentos financeiros, pelas contas do plano de
contas marcadas em Configurações > Parâmetros financeiros) e físico (a
partir do consumo real registrado pela Alimentação em MovimentoEstoque,
multiplicado pelo valor unitário do item no Estoque).
"""
from __future__ import annotations


def calcular_rmca_gerencial(itens: list[dict], codigos_receita: set[str], codigos_custo: set[str]) -> dict:
    receita = round(sum(i["valor_total"] or 0 for i in itens if i["codigo_conta_gerencial"] in codigos_receita), 2)
    custo = round(sum(i["valor_total"] or 0 for i in itens if i["codigo_conta_gerencial"] in codigos_custo), 2)
    return {"receita_leite": receita, "custo_alimentacao": custo, "rmca": round(receita - custo, 2)}


def calcular_custo_fisico(movimentos: list[dict], estoque_por_nome: dict[str, dict]) -> dict:
    """Soma o consumo real (MovimentoEstoque da baixa automática da Alimentação),
    por ingrediente, multiplicado pelo valor unitário do item no Estoque.
    Itens marcados com considerar_rmca=False (Configurações > Cadastro > Itens de
    estoque) ficam de fora mesmo tendo baixa de "Saída de ajuste" no período —
    sem marcação nenhuma (None/True), o item entra normalmente."""
    itens: dict[str, dict] = {}
    for m in movimentos:
        estoque = estoque_por_nome.get(m["nome_item"])
        if estoque is not None and estoque.get("considerar_rmca") is False:
            continue
        preco = (estoque or {}).get("valor_unitario") or 0
        quantidade = m["quantidade"] or 0
        acc = itens.setdefault(m["nome_item"], {"ingrediente": m["nome_item"], "quantidade": 0.0, "valor_unitario": preco, "custo": 0.0})
        acc["quantidade"] = round(acc["quantidade"] + quantidade, 2)
        acc["custo"] = round(acc["custo"] + quantidade * preco, 2)
    custo_total = round(sum(i["custo"] for i in itens.values()), 2)
    return {"custo_total": custo_total, "itens": sorted(itens.values(), key=lambda x: -x["custo"])}
