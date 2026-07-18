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
import io
import json
import os

NOME_FAZENDA = "Fazenda Estreito Ponte de Pedra"

MIME_ACEITOS = {"application/pdf", "image/jpeg", "image/png"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "tipo_documento": {
            "type": "string",
            "enum": ["nota_fiscal", "recibo", "boleto"],
            "description": (
                "'nota_fiscal' quando for uma nota fiscal eletrônica/DANFE (compra ou venda ainda não paga). "
                "'recibo' quando for um comprovante de pagamento/transferência já efetivado (recibo, comprovante bancário, PIX). "
                "'boleto' quando for um boleto bancário (código de barras/linha digitável, vencimento, ainda não pago)."
            ),
        },
        "parcela_num": {
            "type": ["integer", "null"],
            "description": "Se o boleto indicar 'parcela X/Y' ou 'X de Y', o número desta parcela (X). Só se aplica a boleto.",
        },
        "parcela_total": {
            "type": ["integer", "null"],
            "description": "Se o boleto indicar 'parcela X/Y' ou 'X de Y', o total de parcelas (Y). Só se aplica a boleto.",
        },
        "linha_digitavel": {
            "type": ["string", "null"],
            "description": "Linha digitável ou código de barras do boleto, se legível. Só se aplica a boleto.",
        },
        "data_vencimento": {
            "type": ["string", "null"],
            "description": "Data de vencimento do boleto, formato YYYY-MM-DD. Só se aplica a boleto.",
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
        "valor_total": {
            "type": ["number", "null"],
            "description": (
                "Valor TOTAL do documento inteiro, em reais. Se o documento tiver mais de uma parcela/página "
                "(boleto com várias vias, uma por parcela), este é a SOMA de todas as parcelas — NUNCA o valor "
                "de uma parcela isolada. Ex.: 8 parcelas de R$586,25 cada → valor_total = 4690.00, não 586.25."
            ),
        },
        "parcelas_detectadas": {
            "type": "array",
            "description": (
                "Quando o documento tiver mais de uma parcela/boleto (uma via por página, por exemplo), uma "
                "entrada AQUI para CADA parcela encontrada, com o valor e vencimento específicos daquela via e, "
                "se legível, a linha digitável daquele boleto especificamente. Preencha mesmo quando houver só "
                "uma parcela/página (um único item nesta lista)."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "numero": {"type": ["integer", "null"], "description": "Número desta parcela (1, 2, 3...)."},
                    "valor": {"type": ["number", "null"], "description": "Valor desta parcela/via, isoladamente."},
                    "data_vencimento": {"type": ["string", "null"], "description": "Vencimento desta parcela, YYYY-MM-DD."},
                    "linha_digitavel": {"type": ["string", "null"], "description": "Linha digitável/código de barras desta via, se legível."},
                },
                "required": ["numero", "valor", "data_vencimento", "linha_digitavel"],
                "additionalProperties": False,
            },
        },
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
    "required": [
        "tipo_documento", "fornecedor_cliente", "numero_documento", "data_emissao", "data_pagamento", "valor_total",
        "conta_bancaria", "itens", "observacao", "parcela_num", "parcela_total", "linha_digitavel", "data_vencimento",
        "parcelas_detectadas",
    ],
    "additionalProperties": False,
}

def _montar_prompt(paginas: int | None) -> str:
    contexto_paginas = (
        f"\nEste documento tem {paginas} página(s) — se for um boleto com mais de uma página, é bem provável que "
        f"cada página seja a via de UMA parcela diferente (uma parcela por página). Confira as {paginas} páginas "
        "uma a uma antes de responder.\n" if paginas and paginas > 1 else ""
    )
    return f"""Você está lendo um documento financeiro anexado no sistema da {NOME_FAZENDA} (fazenda leiteira).
Identifique se é uma NOTA FISCAL (compra ou venda ainda não paga), um RECIBO/COMPROVANTE (pagamento ou \
transferência já realizado — recibo em papel, comprovante bancário, print de PIX/TED) ou um BOLETO BANCÁRIO \
(código de barras/linha digitável, com vencimento, ainda não pago).
{contexto_paginas}
Se for nota fiscal: extraia fornecedor/cliente, número, data de emissão, valor total e os produtos/serviços \
discriminados (se houver mais de um item).

Se for recibo/comprovante: identifique, pelo próprio comprovante, de onde saiu o dinheiro e para onde foi — \
isso te diz se é uma despesa (saiu de conta da fazenda) ou receita (entrou numa conta da fazenda) — e preencha \
fornecedor_cliente com a contraparte (quem recebeu ou quem pagou), data_pagamento com a data da operação, e \
conta_bancaria com o banco/agência/conta identificável.

Se for boleto: extraia fornecedor (beneficiário) e número do documento/nosso número. Procure em CADA página/via \
por algum texto do tipo "parcela 2/6", "2 de 6" ou "parc. 02/06" — se encontrar, preencha parcela_num (o número \
desta via específica) e parcela_total (o total de parcelas); se não houver essa indicação em nenhuma página, \
deixe ambos null (não é necessariamente parcelado).

MUITO IMPORTANTE sobre valores em boleto com várias páginas/parcelas: preencha `parcelas_detectadas` com UMA \
entrada por página/via encontrada (número, valor, vencimento e linha digitável DAQUELA via isoladamente) — e só \
depois calcule `valor_total` como a SOMA de todas elas. Nunca copie o valor de uma única via para `valor_total` \
quando houver mais de uma parcela: por exemplo, 8 páginas de R$586,25 cada dão parcelas_detectadas com 8 itens \
de 586.25 e valor_total = 4690.00 (nunca 586.25). Se o documento tiver só uma parcela/página, `parcelas_detectadas` \
ainda assim recebe 1 item (com os mesmos dados dessa única via) e `valor_total` é igual ao valor dela.

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


def _contar_paginas_pdf(conteudo: bytes) -> int | None:
    """Quantas páginas o PDF tem — dá ao modelo um número concreto pra
    conferir contra `parcela_total`/`parcelas_detectadas`, em vez de ele ter
    que adivinhar sozinho quantas vias existem. None se não der pra ler
    (arquivo corrompido/criptografado) — a leitura segue sem esse contexto."""
    try:
        import pypdf
        return len(pypdf.PdfReader(io.BytesIO(conteudo)).pages)
    except Exception:
        return None


def _corrigir_valor_total_boleto(dados: dict) -> dict:
    """Rede de segurança server-side: se o documento é um boleto com mais de
    uma parcela e a IA devolveu `valor_total` igual (ou quase igual) ao valor
    de UMA parcela isolada em vez da soma de todas — o erro que gerou o bug
    relatado (8 parcelas de R$586,25 virando "total" R$586,25) — corrige aqui,
    não deixa esse valor errado seguir pro formulário."""
    if dados.get("tipo_documento") != "boleto":
        return dados
    parcelas = [p for p in (dados.get("parcelas_detectadas") or []) if p.get("valor") is not None]
    if len(parcelas) < 2:
        return dados
    soma = round(sum(p["valor"] for p in parcelas), 2)
    valor_total = dados.get("valor_total")
    media = soma / len(parcelas)
    # "Parece que devolveram o valor de 1 parcela como total" — perto da média
    # de UMA parcela e longe da soma de todas.
    parece_parcela_unica = valor_total is not None and abs(valor_total - media) < 0.02 and abs(valor_total - soma) > 0.02
    if valor_total is None or parece_parcela_unica:
        dados = {**dados, "valor_total": soma, "valor_total_corrigido": True}
    return dados


def ler_documento(conteudo: bytes, mime_type: str) -> dict:
    """Envia o PDF/imagem para a Claude Vision e devolve os campos extraídos,
    já no formato esperado pelo formulário de lançamento financeiro."""
    if mime_type not in MIME_ACEITOS:
        raise ValueError(f"Tipo de arquivo não suportado: {mime_type} (aceitos: PDF, JPEG, PNG)")

    paginas = _contar_paginas_pdf(conteudo) if mime_type == "application/pdf" else None

    dados_b64 = base64.standard_b64encode(conteudo).decode("utf-8")
    bloco = (
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": dados_b64}}
        if mime_type == "application/pdf"
        else {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": dados_b64}}
    )

    resposta = _client().messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        messages=[{"role": "user", "content": [bloco, {"type": "text", "text": _montar_prompt(paginas)}]}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )

    if resposta.stop_reason == "refusal":
        raise ValueError("A leitura automática recusou processar este documento.")

    texto = next((b.text for b in resposta.content if b.type == "text"), None)
    if not texto:
        raise ValueError("A leitura automática não retornou dados legíveis para este documento.")
    dados = json.loads(texto)
    dados = _corrigir_valor_total_boleto(dados)
    dados["paginas_documento"] = paginas
    return dados
