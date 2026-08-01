"""
Liga o motor puro de casamento (fazenda.rules.casamento_cadastro) ao cadastro
real da fazenda — busca fornecedores, produtos de estoque e serviços já
cadastrados e devolve, para o fornecedor e cada item extraídos de uma nota
fiscal/documento (ver fazenda.rules.nfe_xml e fazenda.rules.leitura_documento),
o melhor candidato do cadastro quando houver alguma semelhança mas não
certeza — para a UI de confirmação (Financeiro) exibir um quadro comparando
"o que veio na nota" com "o que existe parecido no cadastro" antes de salvar
o lançamento, com opção de confirmar, editar ou ignorar a sugestão.

Só participam do resultado matches com confiança "provavel": "exato" já bate
sozinho (nada para confirmar) e "incerto" não tem nada parecido o bastante
para sugerir (ver LIMIAR_PROVAVEL em casamento_cadastro).
"""
from __future__ import annotations

from sqlmodel import Session, select

from fazenda.models import Estoque, Fornecedor, ServicoCadastro
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.casamento_cadastro import PROVAVEL, melhor_candidato


def _nomes(session: Session, model, fazenda_id: int | None) -> list[str]:
    query = select(model)
    if fazenda_id is not None:
        query = query.where(model.fazenda_id == fazenda_id)
    return [obj.nome for obj in session.exec(query).all() if obj.nome]


def sugestoes_cadastro(session: Session, fazenda_id_bruto: int | None, dados: dict) -> dict:
    """`dados` é o dict já extraído (parse_nfe_xml ou ler_documento) — usa só
    `fornecedor_cliente` e `itens[].produto`, nunca lança erro por campo
    ausente. Devolve `{"fornecedor": {...} | None, "itens": [...]}`."""
    fazenda_id = fazenda_id_seguro(fazenda_id_bruto)
    fornecedores = _nomes(session, Fornecedor, fazenda_id)
    produtos = _nomes(session, Estoque, fazenda_id)
    servicos = _nomes(session, ServicoCadastro, fazenda_id)
    produtos_set = set(produtos)

    fornecedor_texto = dados.get("fornecedor_cliente")
    fornecedor_sugestao = None
    if fornecedor_texto:
        m = melhor_candidato(fornecedor_texto, fornecedores)
        if m["confianca"] == PROVAVEL:
            fornecedor_sugestao = {"texto": fornecedor_texto, **m}

    itens_sugestoes = []
    for indice, item in enumerate(dados.get("itens") or []):
        texto = item.get("produto")
        if not texto:
            continue
        m = melhor_candidato(texto, produtos + servicos)
        if m["confianca"] != PROVAVEL:
            continue
        tipo = "produto" if m["candidato"] in produtos_set else "servico"
        # `indice` é a posição do item em `dados["itens"]` (não em
        # `itens_sugestoes`, que pula os sem sugestão) — é assim que o front
        # (FormFinanceiro.tsx) sabe em qual item da lista aplicar a sugestão,
        # já que nem todo item tem uma.
        itens_sugestoes.append({"texto": texto, "tipo": tipo, "indice": indice, **m})

    return {"fornecedor": fornecedor_sugestao, "itens": itens_sugestoes}
