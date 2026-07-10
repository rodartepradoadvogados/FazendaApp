"""
Leitura automática de nota fiscal ou recibo (PDF/JPEG/PNG) via IA (Claude
Vision), para pré-preencher o lançamento financeiro — mesmo espírito do
`parse_nfe_xml`, mas para documento escaneado/fotografado em vez de XML
estruturado. O front trata o resultado como um rascunho: tudo fica editável
antes de salvar.

Requer a variável de ambiente ANTHROPIC_API_KEY configurada (Railway >
Variables). Sem ela, `ler_documento` levanta RuntimeError com uma mensagem
clara para o administrador configurar.
"""
from __future__ import annotations

import base64
import json
import os

NOME_FAZENDA = "Fazenda Estreito Ponte de Pedra"

MIME_ACEITOS = {"application/pdf", "image/jpeg", "image/png"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "tipo_documento": {
            "type": "string",
            "enum": ["nota_fiscal", "recibo"],
            "description": (
                "'nota_fiscal' quando for uma nota fiscal eletrônica/DANFE (compra ou venda ainda não paga). "
                "'recibo' quando for um comprovante de pagamento/transferência já efetivado (recibo, comprovante bancário, PIX)."
            ),
        },
        "fornecedor_cliente": {
            "type": ["string", "null"],
            "description": f"Nome do fornecedor (se {NOME_FAZENDA} for quem paga/compra) ou do cliente (se for quem recebe/vende).",
        },
        "numero_documento": {"type": ["string", "null"], "description": "Número da nota fiscal ou do comprovante, se houver."},
        "data_emissao": {"type": ["string", "null"], "description": "Data de emissão da nota fiscal, formato YYYY-MM-DD."},
        "data_pagamento": {
            "type": ["string", "null"],
            "description": "Data em que o pagamento/transferência do recibo foi efetivado, formato YYYY-MM-DD. Só se aplica a recibo.",
        },
        "valor_total": {"type": ["number", "null"], "description": "Valor total do documento em reais."},
        "conta_bancaria": {
            "type": ["string", "null"],
            "description": "Banco/agência/conta de origem ou destino identificável no comprovante (ex.: 'Banco do Brasil ag 3775-3 cc 3.615-3'). Só se aplica a recibo.",
        },
        "itens": {
            "type": "array",
            "description": "Produtos/serviços discriminados na nota fiscal, se houver mais de um.",
            "items": {
                "type": "object",
                "properties": {
                    "produto": {"type": "string"},
                    "quantidade": {"type": ["number", "null"]},
                    "valor_unitario": {"type": ["number", "null"]},
                    "valor_total": {"type": ["number", "null"]},
                },
                "required": ["produto"],
                "additionalProperties": False,
            },
        },
        "observacao": {"type": ["string", "null"], "description": "Qualquer informação relevante que não caiba nos campos acima."},
    },
    "required": ["tipo_documento", "fornecedor_cliente", "numero_documento", "data_emissao", "data_pagamento", "valor_total", "conta_bancaria", "itens", "observacao"],
    "additionalProperties": False,
}

_PROMPT = f"""Você está lendo um documento financeiro anexado no sistema da {NOME_FAZENDA} (fazenda leiteira).
Identifique se é uma NOTA FISCAL (compra ou venda ainda não paga) ou um RECIBO/COMPROVANTE (pagamento ou \
transferência já realizado — recibo em papel, comprovante bancário, print de PIX/TED).

Se for nota fiscal: extraia fornecedor/cliente, número, data de emissão, valor total e os produtos/serviços \
discriminados (se houver mais de um item).

Se for recibo/comprovante: identifique, pelo próprio comprovante, de onde saiu o dinheiro e para onde foi — \
isso te diz se é uma despesa (saiu de conta da fazenda) ou receita (entrou numa conta da fazenda) — e preencha \
fornecedor_cliente com a contraparte (quem recebeu ou quem pagou), data_pagamento com a data da operação, e \
conta_bancaria com o banco/agência/conta identificável.

Responda só com os campos do schema — não invente valores que não conseguir ler; deixe null."""


def _client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Leitura automática de documentos não está configurada — falta a variável de ambiente "
            "ANTHROPIC_API_KEY. Configure-a nas variáveis do serviço (Railway > Variables) para habilitar."
        )
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def ler_documento(conteudo: bytes, mime_type: str) -> dict:
    """Envia o PDF/imagem para a Claude Vision e devolve os campos extraídos,
    já no formato esperado pelo formulário de lançamento financeiro."""
    if mime_type not in MIME_ACEITOS:
        raise ValueError(f"Tipo de arquivo não suportado: {mime_type} (aceitos: PDF, JPEG, PNG)")

    dados_b64 = base64.standard_b64encode(conteudo).decode("utf-8")
    bloco = (
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": dados_b64}}
        if mime_type == "application/pdf"
        else {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": dados_b64}}
    )

    resposta = _client().messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        messages=[{"role": "user", "content": [bloco, {"type": "text", "text": _PROMPT}]}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )

    if resposta.stop_reason == "refusal":
        raise ValueError("A leitura automática recusou processar este documento.")

    texto = next((b.text for b in resposta.content if b.type == "text"), None)
    if not texto:
        raise ValueError("A leitura automática não retornou dados legíveis para este documento.")
    return json.loads(texto)
