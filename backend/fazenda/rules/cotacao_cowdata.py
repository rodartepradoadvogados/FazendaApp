"""
Regras puras (sem acesso a banco) do catálogo/cotação de preços do Painel
CowData — ver fazenda/models/catalogo_cowdata.py para o desenho das tabelas.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from fazenda.rules.casamento_cadastro import normalizar

STATUS_COTACAO_COWDATA_ABERTOS = ("rascunho", "em_andamento")

# Um pouco mais permissivo que o LIMIAR_PROVAVEL (0.80) de
# casamento_cadastro — aqui o objetivo é só AVISAR de uma possível duplicata
# pro cadastrador olhar, nunca preencher nada sozinho, então vale mostrar
# candidatos com uma correspondência mais frouxa também.
LIMIAR_SUGESTAO_DUPLICATA = 0.68


def sugestoes_duplicata(nome: str, candidatos: list[tuple[int, str]], limite: int = 5) -> list[dict]:
    """Compara `nome` (produto-padrão sendo cadastrado) contra cada
    `(id, nome)` já existente e devolve os mais parecidos, do maior score pro
    menor, cortados no `limiar`. Não decide nada sozinho — é só o aviso ativo
    de possível duplicata citado na proposta (granularidade do produto-padrão
    fora de medicamento não tem trava automática; depende de curadoria
    humana contínua)."""
    nome_norm = normalizar(nome)
    if not nome_norm:
        return []
    pontuados = []
    for cid, cnome in candidatos:
        cnome_norm = normalizar(cnome)
        if not cnome_norm:
            continue
        score = SequenceMatcher(None, nome_norm, cnome_norm).ratio()
        if score >= LIMIAR_SUGESTAO_DUPLICATA:
            pontuados.append({"id": cid, "nome": cnome, "score": round(score, 3)})
    pontuados.sort(key=lambda p: p["score"], reverse=True)
    return pontuados[:limite]


def rotulo_item_cotacao_cowdata(
    modo: str, *, produto_nome: str | None = None, classificacao_nome: str | None = None,
    finalidade_nome: str | None = None,
) -> str:
    """Rótulo humano e NEUTRO de um item de cotação — nunca expõe o nome do
    campo interno ("classificação"/"finalidade") no texto de saída, pedido
    explícito do usuário: sai "Cotação de: Medicamentos", nunca "finalidade:
    Medicamentos"."""
    if modo == "produto":
        return produto_nome or "produto"
    if modo == "classificacao":
        return classificacao_nome or "categoria"
    if modo == "finalidade":
        return finalidade_nome or "finalidade"
    return "item"


def montar_mensagem_cotacao_cowdata(rotulos: list[str], descricao_livre: str | None = None) -> str:
    """Texto de referência para a equipe CowData usar ao contatar o
    fornecedor (telefone/e-mail/WhatsApp, fora do sistema — não há disparo
    automático aqui, diferente da Cotação de uma fazenda). Só rótulos
    neutros, nunca o nome do campo interno."""
    corpo = f"Cotação de: {', '.join(rotulos)}" if rotulos else "Cotação"
    if descricao_livre:
        corpo += f" — {descricao_livre}"
    return corpo
