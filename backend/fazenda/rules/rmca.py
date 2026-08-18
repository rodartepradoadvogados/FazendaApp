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
    Entram no custo os itens cuja conta gerencial padrão de despesa (Configurações
    > Cadastro > Itens de estoque) é a "3.01.01 Alimentação do rebanho" ou
    qualquer conta registrada dentro dela (código começando com "3.01.01") —
    os demais itens (mesmo com baixa de "Saída de ajuste" no período) ficam
    de fora do físico."""
    itens: dict[str, dict] = {}
    for m in movimentos:
        estoque = estoque_por_nome.get(m["nome_item"])
        conta = (estoque or {}).get("conta_gerencial_despesa_padrao") or ""
        if not conta.startswith("3.01.01"):
            continue
        # Não conta movimentos anteriores ao início do controle de estoque do item
        # (o item passou a ser controlado só a partir dessa data).
        inicio = (estoque or {}).get("data_inicio_controle")
        if inicio and m.get("data_movimento") and m["data_movimento"] < inicio:
            continue
        # Preço da ÉPOCA (snapshot gravado no próprio MovimentoEstoque, ver
        # rules/estoque_baixa.py) — sem ele, todo o histórico era multiplicado
        # pelo preço ATUAL do item, reescrevendo retroativamente o custo de
        # meses cujo preço já mudou. `None` só em movimentos anteriores à
        # existência desta coluna; cai no preço atual como aproximação.
        preco = m.get("valor_unitario")
        if preco is None:
            preco = (estoque or {}).get("valor_unitario") or 0
        quantidade = m["quantidade"] or 0
        acc = itens.setdefault(m["nome_item"], {"ingrediente": m["nome_item"], "quantidade": 0.0, "valor_unitario": preco, "custo": 0.0})
        # Acumula em ponto flutuante cheio — arredondar a cada iteração
        # (round dentro do loop) compunha um erro pequeno a cada movimento
        # somado, que crescia com a quantidade de lançamentos no período.
        # Só arredonda o total final de cada ingrediente, uma vez.
        acc["quantidade"] += quantidade
        acc["custo"] += quantidade * preco
    for acc in itens.values():
        acc["quantidade"] = round(acc["quantidade"], 2)
        acc["custo"] = round(acc["custo"], 2)
    custo_total = round(sum(i["custo"] for i in itens.values()), 2)
    return {"custo_total": custo_total, "itens": sorted(itens.values(), key=lambda x: -x["custo"])}
