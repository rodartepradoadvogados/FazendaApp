"""
Leitura de XML de Nota Fiscal Eletrônica (NF-e) para pré-preencher o
lançamento financeiro. O usuário pode arrastar/colar/selecionar o arquivo;
os campos extraídos ficam editáveis antes de salvar.
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


def _achar(raiz: ET.Element, caminho: list[str]) -> ET.Element | None:
    """Desce por uma lista de tag-names (sem namespace) a partir da raiz."""
    atual: ET.Element | None = raiz
    for nome in caminho:
        if atual is None:
            return None
        atual = next((f for f in atual if _sem_namespace(f.tag) == nome), None)
    return atual


def parse_nfe_xml(xml_texto: str) -> dict:
    """
    Extrai os campos relevantes de um XML de NF-e (modelo 55) para o
    lançamento financeiro. Retorna um dicionário parcial — só preenche o que
    encontrar; o front trata o resto como edição manual.
    """
    # Remove DOCTYPE, incluindo subset interno com colchetes (mitiga expansão
    # de entidade externa em XML colado por usuário).
    limpo = re.sub(r"<!DOCTYPE[^>\[]*(\[.*?\])?\s*>", "", xml_texto, flags=re.IGNORECASE | re.DOTALL).lstrip()
    raiz = ET.fromstring(limpo)

    # A raiz pode ser <nfeProc><NFe><infNFe>... ou já <NFe><infNFe>...
    inf_nfe = None
    for no in raiz.iter():
        if _sem_namespace(no.tag) == "infNFe":
            inf_nfe = no
            break
    if inf_nfe is None:
        raise ValueError("XML não parece ser uma NF-e (tag infNFe não encontrada)")

    ide = _achar(inf_nfe, ["ide"])
    emit = _achar(inf_nfe, ["emit"])
    total = _achar(inf_nfe, ["total", "ICMSTot"])

    numero_documento = _texto(_achar(ide, ["nNF"])) if ide is not None else None
    dh_emi = _texto(_achar(ide, ["dhEmi"])) if ide is not None else None
    if not dh_emi and ide is not None:
        dh_emi = _texto(_achar(ide, ["dEmi"]))
    data_emissao = dh_emi[:10] if dh_emi else None

    fornecedor = _texto(_achar(emit, ["xNome"])) if emit is not None else None
    valor_total = _texto(_achar(total, ["vNF"])) if total is not None else None

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
                "numero": _texto(_achar(dup, ["nDup"])),
                "data_vencimento": _texto(_achar(dup, ["dVenc"])),
                "valor": _texto(_achar(dup, ["vDup"])),
            })

    resultado = {
        "numero_documento": numero_documento,
        "data_emissao": data_emissao,
        "fornecedor_cliente": fornecedor,
        "valor_total": float(valor_total) if valor_total else None,
        "parcelas": [
            {
                "numero": p["numero"],
                "data_vencimento": p["data_vencimento"],
                "valor": float(p["valor"]) if p["valor"] else None,
            }
            for p in parcelas
        ],
    }

    if len(produtos) == 1:
        p = produtos[0]
        resultado["descricao"] = p["descricao"]
        resultado["quantidade"] = float(p["quantidade"]) if p["quantidade"] else None
        resultado["valor_unitario"] = float(p["valor_unitario"]) if p["valor_unitario"] else None
    elif len(produtos) > 1:
        resultado["descricao"] = ", ".join(p["descricao"] for p in produtos if p["descricao"])[:500]

    return resultado
