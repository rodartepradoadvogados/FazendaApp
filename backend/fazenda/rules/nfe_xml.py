"""
Leitura de XML de nota fiscal para pré-preencher o lançamento financeiro —
NF-e de mercadoria (modelo 55, schema nacional único) e NFS-e de serviço
(municipal, schema varia de prefeitura para prefeitura). O usuário pode
arrastar/colar/selecionar o arquivo; os campos extraídos ficam editáveis
antes de salvar.

NF-e é padronizada nacionalmente — busca por caminho fixo de tags. NFS-e não
tem schema único: cada município usa seus próprios nomes de tag, prefixos e
namespaces. Por isso a leitura de NFS-e busca por *nome local* de tag em
qualquer profundidade da árvore (ignorando namespace/prefixo), em vez de
descer por um caminho fixo — quando não encontra um campo, ele fica `None`
(nunca inventa um valor, nunca explode).
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET


def _sem_namespace(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _texto(no: ET.Element | None) -> str | None:
    if no is None or no.text is None:
        return None
    t = no.text.strip()
    return t or None


def _achar(raiz: ET.Element | None, caminho: list[str]) -> ET.Element | None:
    """Desce por uma lista de tag-names (sem namespace) a partir da raiz —
    usado na NF-e, cujo schema é fixo e nacional."""
    atual: ET.Element | None = raiz
    for nome in caminho:
        if atual is None:
            return None
        atual = next((f for f in atual if _sem_namespace(f.tag) == nome), None)
    return atual


def _no_por_nome(raiz: ET.Element, nome: str) -> ET.Element | None:
    """Primeiro nó, em qualquer profundidade a partir de (e incluindo)
    `raiz`, cujo nome local de tag bate exatamente com `nome`."""
    for no in raiz.iter():
        if _sem_namespace(no.tag) == nome:
            return no
    return None


def _no_qualquer(raiz: ET.Element | None, nomes: set[str]) -> ET.Element | None:
    """Como `_no_por_nome`, mas tolerante a variação de nome/caixa — usado na
    leitura de NFS-e, cujo schema muda de prefeitura para prefeitura. Casa o
    nome local da tag (em minúsculas) contra qualquer um dos nomes em
    `nomes`, buscando em toda a subárvore de `raiz` (`raiz` incluído)."""
    if raiz is None:
        return None
    alvo = {n.lower() for n in nomes}
    for no in raiz.iter():
        if _sem_namespace(no.tag).lower() in alvo:
            return no
    return None


def _texto_qualquer(raiz: ET.Element | None, nomes: list[str]) -> str | None:
    """Texto do primeiro nó (em qualquer profundidade) cujo nome local bate
    com algum dos `nomes` — mesma tolerância de `_no_qualquer`."""
    return _texto(_no_qualquer(raiz, set(nomes)))


def parse_nfe_xml(xml_texto: str) -> dict:
    """
    Extrai os campos relevantes de um XML de nota fiscal para o lançamento
    financeiro — reconhece tanto NF-e de mercadoria (modelo 55, tag
    `infNFe`) quanto NFS-e de serviço (municipal, tag `InfNfse`/`Nfse`).
    Retorna um dicionário parcial — só preenche o que encontrar; o front
    trata o resto como edição manual.
    """
    if not xml_texto or not xml_texto.strip():
        raise ValueError("Arquivo XML vazio — nada para ler.")

    # Remove DOCTYPE, incluindo subset interno com colchetes (mitiga expansão
    # de entidade externa em XML colado por usuário).
    limpo = re.sub(r"<!DOCTYPE[^>\[]*(\[.*?\])?\s*>", "", xml_texto, flags=re.IGNORECASE | re.DOTALL).lstrip()
    try:
        raiz = ET.fromstring(limpo)
    except ET.ParseError as e:
        raise ValueError(f"XML inválido — não foi possível interpretar o arquivo ({e}).")

    # A raiz pode ser <nfeProc><NFe><infNFe>... ou já <NFe><infNFe>...
    inf_nfe = _no_por_nome(raiz, "infNFe")
    if inf_nfe is not None:
        return _parse_nfe_mercadoria(inf_nfe)

    # NFS-e: procura a tag mais específica (InfNfse) e, se não achar, a mais
    # genérica (Nfse) — schemas municipais variam bastante entre si.
    inf_nfse = _no_qualquer(raiz, {"infnfse", "nfse"})
    if inf_nfse is not None:
        return _parse_nfse(inf_nfse)

    raise ValueError(
        "XML não parece ser uma NF-e de mercadoria nem uma NFS-e de serviço reconhecida "
        "(tags infNFe / InfNfse / Nfse não encontradas)."
    )


def _parse_nfe_mercadoria(inf_nfe: ET.Element) -> dict:
    """NF-e modelo 55/65 (mercadoria) — schema nacional único, tags fixas."""
    ide = _achar(inf_nfe, ["ide"])
    emit = _achar(inf_nfe, ["emit"])
    total = _achar(inf_nfe, ["total", "ICMSTot"])

    numero_documento = _texto(_achar(ide, ["nNF"])) if ide is not None else None
    dh_emi = _texto(_achar(ide, ["dhEmi"])) if ide is not None else None
    if not dh_emi and ide is not None:
        dh_emi = _texto(_achar(ide, ["dEmi"]))
    data_emissao = dh_emi[:10] if dh_emi else None

    modelo = _texto(_achar(ide, ["mod"])) if ide is not None else None
    tipo_documento = {"55": "NF-e", "65": "NFC-e"}.get(modelo or "", "NF-e")

    fornecedor = _texto(_achar(emit, ["xNome"])) if emit is not None else None
    valor_total = _texto(_achar(total, ["vNF"])) if total is not None else None
    desconto = _texto(_achar(total, ["vDesc"])) if total is not None else None
    acrescimo = _texto(_achar(total, ["vOutro"])) if total is not None else None

    produtos = []
    for det in inf_nfe:
        if _sem_namespace(det.tag) != "det":
            continue
        prod = _achar(det, ["prod"])
        if prod is None:
            continue
        produtos.append({
            "descricao": _texto(_achar(prod, ["xProd"])),
            "quantidade": _texto(_achar(prod, ["qCom"])),
            "valor_unitario": _texto(_achar(prod, ["vUnCom"])),
            "valor_total": _texto(_achar(prod, ["vProd"])),
        })

    parcelas = []
    cobr = _achar(inf_nfe, ["cobr"])
    if cobr is not None:
        for dup in cobr:
            if _sem_namespace(dup.tag) != "dup":
                continue
            parcelas.append({
                # nDup — número da duplicata (ex.: "001", "002"...); mantido
                # tal como consta no XML, sem conversão para inteiro.
                "numero": _texto(_achar(dup, ["nDup"])),
                "data_vencimento": _texto(_achar(dup, ["dVenc"])),
                "valor": _texto(_achar(dup, ["vDup"])),
            })

    return {
        "tipo_documento": tipo_documento,
        "numero_documento": numero_documento,
        "data_emissao": data_emissao,
        "fornecedor_cliente": fornecedor,
        "valor_total": float(valor_total) if valor_total else None,
        "desconto": float(desconto) if desconto else None,
        "acrescimo": float(acrescimo) if acrescimo else None,
        "itens": [
            {
                "produto": p["descricao"],
                "quantidade": float(p["quantidade"]) if p["quantidade"] else None,
                "valor_unitario": float(p["valor_unitario"]) if p["valor_unitario"] else None,
                "valor_total": float(p["valor_total"]) if p["valor_total"] else None,
            }
            for p in produtos
        ],
        "parcelas": [
            {
                "numero": p["numero"],
                "data_vencimento": p["data_vencimento"],
                "valor": float(p["valor"]) if p["valor"] else None,
            }
            for p in parcelas
        ],
    }


def _parse_nfse(inf_nfse: ET.Element) -> dict:
    """
    NFS-e (nota fiscal de serviço eletrônica) — schema municipal, varia de
    prefeitura para prefeitura (nomes de tag, prefixos e namespaces
    diferentes). Busca cada campo pelo nome local da tag em qualquer
    profundidade (`_texto_qualquer`/`_no_qualquer`), tolerando as variações
    mais comuns entre municípios; quando não acha um campo, ele fica `None`
    — nunca inventa, nunca lança erro por campo ausente.
    """
    numero = _texto_qualquer(inf_nfse, ["Numero", "NumeroNfse"])
    data_emissao_bruta = _texto_qualquer(inf_nfse, ["DataEmissao"])
    data_emissao = data_emissao_bruta[:10] if data_emissao_bruta else None

    # Prestador de serviço (quem emite) — busca um nó "PrestadorServico" (ou
    # variações) primeiro, para não confundir com a razão social do Tomador;
    # se o schema não tiver essa subárvore, cai para a busca ampla.
    prestador = _no_qualquer(inf_nfse, {"prestadorservico", "identificacaoprestador", "prestador"})
    fornecedor = _texto_qualquer(prestador, ["RazaoSocial", "NomeFantasia"]) if prestador is not None else None
    if not fornecedor:
        fornecedor = _texto_qualquer(inf_nfse, ["RazaoSocial", "NomeFantasia"])

    # Os valores aparecem em posições bem diferentes conforme o município
    # (soltos direto em InfNfse, agrupados em <ValoresNfse>, ou dentro de
    # <Servico><Valores> no bloco de declaração) — por isso a busca é ampla,
    # em toda a árvore de InfNfse, em vez de escopada a um nó específico.
    valor_servicos = _texto_qualquer(inf_nfse, ["ValorServicos"])
    valor_liquido = _texto_qualquer(inf_nfse, ["ValorLiquidoNfse"])
    desconto = _texto_qualquer(inf_nfse, ["ValorDeducoes", "DescontoIncondicionado"])

    # Discriminação do serviço — texto livre e costuma ser longo; devolvida
    # como descrição do (único) item, para a camada de cima usar como tal.
    discriminacao = _texto_qualquer(inf_nfse, ["Discriminacao"])

    valor_total_bruto = valor_liquido or valor_servicos

    return {
        "tipo_documento": "NFS-e",
        "numero_documento": numero,
        "data_emissao": data_emissao,
        "fornecedor_cliente": fornecedor,
        "valor_total": float(valor_total_bruto) if valor_total_bruto else None,
        "valor_servicos": float(valor_servicos) if valor_servicos else None,
        "valor_liquido": float(valor_liquido) if valor_liquido else None,
        "desconto": float(desconto) if desconto else None,
        "acrescimo": None,  # NFS-e não tem um equivalente direto a vOutro da NF-e.
        "itens": (
            [{
                "produto": discriminacao,
                "quantidade": None,
                "valor_unitario": None,
                "valor_total": float(valor_total_bruto) if valor_total_bruto else None,
            }]
            if discriminacao else []
        ),
        "parcelas": [],
    }
