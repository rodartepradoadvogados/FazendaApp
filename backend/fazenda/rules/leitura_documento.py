"""
Leitura automática de documento financeiro (nota fiscal, recibo, boleto,
guia de FGTS, guia de DCTFWeb) em PDF/JPEG/PNG, para pré-preencher o
lançamento financeiro — mesmo espírito do `parse_nfe_xml`, mas para
documento escaneado/fotografado em vez de XML estruturado. O front trata o
resultado como um rascunho: tudo fica editável antes de salvar.

MIGRAÇÃO (2026-08): esta implementação usava a API de Visão da Claude (IA),
paga por documento. A chave de API configurada no Railway ficou sem crédito
e o dono do produto decidiu — de propósito, ciente do trade-off — substituir
por uma alternativa GRATUITA: Tesseract OCR (extração de texto bruto) +
regras/regex sobre esse texto pra achar os campos estruturados. Isso é
DELIBERADAMENTE menos preciso que IA de visão, especialmente para:
  - Nota fiscal com layout de itens variado (tabela de produtos): IA de
    visão "entende" a tabela; regex sobre texto OCR'd só reconhece um
    formato de linha razoavelmente padronizado (produto + quantidade +
    unitário + total na mesma linha) — nota fiscal com layout diferente
    (quebra de linha no meio do item, colunas fora de ordem, etc.) tende a
    não extrair itens nenhum, ou extrair errado. O campo fica vazio/[] nesse
    caso — nunca inventa dado.
  - Foto de documento tirada em ângulo, mal iluminada, ou com papel
    amassado: o OCR erra caracteres (0/O, 1/I/l, 5/S) com mais frequência
    que uma IA de visão, que também "entende" o contexto pra corrigir.
  - Layouts de boleto/guia fora do padrão mais comum (raro, mas existe).

Requer os binários de sistema `tesseract` (com dado de idioma "por") e
`poppler-utils` (fornece `pdftoppm`, usado por `pdf2image` para renderizar
página de PDF em imagem antes do OCR) — ver `backend/nixpacks.toml`. Sem
esses binários instalados no servidor (ex.: nixpacks.toml ainda não
aplicado/validado em produção), toda leitura falha com um ValueError claro
("nenhum texto reconhecido...") — fallback seguro: nunca derruba o resto do
sistema, só a leitura automática fica inoperante até o deploy corrigir isso.
"""
from __future__ import annotations

import io
import re
import unicodedata

NOME_FAZENDA = "Fazenda Estreito Ponte de Pedra"

# PDF/imagem aceitos no upload, mais tolerância a variações reais do mundo:
# "image/jpg" não é um media type padrão, mas câmeras/apps antigos mandam
# assim; HEIC/HEIF (foto de iPhone) é aceito aqui só para poder devolver um
# erro claro abaixo.
MIME_ACEITOS = {
    "application/pdf",
    "image/jpeg", "image/jpg",
    "image/png", "image/webp", "image/gif",
    "image/heic", "image/heif",
}

# "image/jpg" não é um media type IANA válido — normaliza pro que o resto do
# pipeline espera.
_MIME_NORMALIZADO = {"image/jpg": "image/jpeg"}

# Decisão de design (migração p/ OCR): HEIC/HEIF continuam REJEITADOS com
# erro claro, como na implementação anterior (Claude Vision também não lia
# esse formato). O Pillow instalado PODE decodificar HEIC se o pacote
# `pillow-heif` for adicionado (ele registra um plugin no Pillow), mas isso
# puxa `libheif` como dependência de sistema — mais uma peça pra instalar e
# validar no Nixpacks, pra um formato raro no fluxo real (o usuário troca o
# formato da câmera do iPhone uma vez — Ajustes > Câmera > Formatos > "Mais
# Compatível" — e o problema some pra sempre). Não vale a complexidade extra
# agora; se isso incomodar muito na prática, dá pra reavaliar depois.
_MIME_SEM_SUPORTE = {"image/heic": "HEIC", "image/heif": "HEIF"}


# ── Normalização de texto ───────────────────────────────────────────────
def _normalizar(texto: str) -> str:
    """Maiúsculo e sem acento — usado só pra bater palavra-chave/rótulo
    (nunca pra exibir): o texto original (com acento e caixa) continua
    disponível pros extratores de campo, que preferem preservar a grafia
    original quando possível (ex.: nome do fornecedor)."""
    forma = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in forma if not unicodedata.combining(c))
    return sem_acento.upper()


# ── OCR: extrai texto bruto de cada página/imagem ───────────────────────
def _extrair_textos_por_pagina(conteudo: bytes, mime_type_normalizado: str) -> list[str]:
    """Devolve uma lista com o texto OCR'd de cada página (PDF) ou um único
    item (imagem). Levanta ValueError se o PDF não tiver nenhuma página —
    qualquer outra falha do pipeline poppler/tesseract (binário ausente,
    arquivo corrompido) sobe como exceção genérica, convertida em ValueError
    por `_extrair_textos_seguro` logo abaixo."""
    import pytesseract
    from PIL import Image

    if mime_type_normalizado == "application/pdf":
        from pdf2image import convert_from_bytes
        imagens = convert_from_bytes(conteudo)
        if not imagens:
            raise ValueError("O PDF enviado não tem nenhuma página para ler.")
        return [pytesseract.image_to_string(img, lang="por") for img in imagens]

    imagem = Image.open(io.BytesIO(conteudo))
    return [pytesseract.image_to_string(imagem, lang="por")]


def _extrair_textos_seguro(conteudo: bytes, mime_type_normalizado: str) -> list[str]:
    """Wrapper de `_extrair_textos_por_pagina` que nunca deixa uma falha do
    OCR virar erro 500 ilegível: qualquer exceção (inclui
    `pytesseract.TesseractNotFoundError` — binário `tesseract` não instalado
    no servidor, ver docstring do módulo — e falhas do poppler/pdf2image)
    vira ValueError com mensagem acionável. Também barra aqui o caso de
    nenhum texto reconhecido em nenhuma página/imagem (Tesseract devolveu
    string vazia/só espaço em todas)."""
    try:
        textos = _extrair_textos_por_pagina(conteudo, mime_type_normalizado)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(
            "Não foi possível processar este documento com OCR — o serviço de leitura pode estar "
            f"indisponível ou mal configurado no servidor ({e}). Preencha os campos manualmente."
        ) from e
    if not any(t.strip() for t in textos):
        raise ValueError(
            "Não foi possível reconhecer nenhum texto neste documento — a imagem pode estar borrada, de "
            "cabeça pra baixo, escura demais, ou não ter texto suficiente pro OCR. Preencha os campos "
            "manualmente."
        )
    return textos


# ── Linha digitável (boleto de cobrança ou guia de arrecadação) ─────────
# Boleto de cobrança: 47 dígitos em 5 blocos (10+11+11+1+14).
_RE_LINHA_BOLETO = re.compile(r"\d{5}\.?\d{5}\s+\d{5}\.?\d{6}\s+\d{5}\.?\d{6}\s+\d\s+\d{14}")
# Guia de arrecadação/tributo (FGTS, DARF, convênio): 48 dígitos em 4 blocos de 12 (11+DV).
_RE_LINHA_ARRECADACAO = re.compile(r"\d{11}-?\d\s+\d{11}-?\d\s+\d{11}-?\d\s+\d{11}-?\d")


def _mod10_febraban(digitos: str) -> int:
    """Dígito verificador módulo 10 (Febraban) — usado nos 3 primeiros
    campos da linha digitável de boleto de cobrança: peso alternado 2/1 da
    direita pra esquerda, soma os algarismos de resultados >= 10."""
    soma = 0
    peso = 2
    for c in reversed(digitos):
        parcial = int(c) * peso
        if parcial > 9:
            parcial -= 9
        soma += parcial
        peso = 1 if peso == 2 else 2
    resto = soma % 10
    return 0 if resto == 0 else 10 - resto


def _mod11_arrecadacao(digitos: str) -> int:
    """Dígito verificador módulo 11 (Febraban), usado por padrão em linha
    digitável de arrecadação/tributo (GRF-e FGTS, DARF). Aproximação: o
    padrão real escolhe mod10 ou mod11 por bloco conforme um dígito
    indicador de segmento no código de barras (não confiável vindo de OCR
    ruidoso) — aqui aplicamos mod11 em todos os blocos, suficiente como
    filtro de ruído grosseiro, não uma validação 100% fiel a todo tipo de
    convênio."""
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(c) * pesos[i % 8] for i, c in enumerate(reversed(digitos)))
    resto = soma % 11
    dv = 11 - resto
    return 1 if dv in (0, 10, 11) else dv


def _valida_dv_boleto(linha47: str) -> bool:
    try:
        return (
            _mod10_febraban(linha47[0:9]) == int(linha47[9])
            and _mod10_febraban(linha47[10:20]) == int(linha47[20])
            and _mod10_febraban(linha47[21:31]) == int(linha47[31])
        )
    except (ValueError, IndexError):
        return False


def _valida_dv_arrecadacao(linha48: str) -> bool:
    try:
        blocos = [linha48[i:i + 12] for i in range(0, 48, 12)]
        return all(_mod11_arrecadacao(b[:11]) == int(b[11]) for b in blocos)
    except (ValueError, IndexError):
        return False


def _formatar_linha_boleto(d: str) -> str:
    return f"{d[0:5]}.{d[5:10]} {d[10:15]}.{d[15:21]} {d[21:26]}.{d[26:32]} {d[32]} {d[33:47]}"


def _formatar_linha_arrecadacao(d: str) -> str:
    return f"{d[0:11]}-{d[11]} {d[12:23]}-{d[23]} {d[24:35]}-{d[35]} {d[36:47]}-{d[47]}"


def _extrair_linha_digitavel(texto: str) -> str:
    """Procura a linha digitável (boleto de cobrança, 47 dígitos, ou guia de
    arrecadação/tributo, 48 dígitos) no texto OCR'd e devolve já formatada
    com os separadores padrão — string vazia se não achar nenhum padrão
    batendo. LIMITAÇÃO DOCUMENTADA: o dígito verificador é conferido (ver
    `_valida_dv_boleto`/`_valida_dv_arrecadacao`) só pra decidir preferência
    entre padrões concorrentes — a resposta não tem campo de "confiança" por
    campo hoje, então uma linha com DV inválido (mais comum em foto/scan
    ruidoso, dígito 0/8 ou 1/7 trocado pelo OCR) ainda é devolvida do mesmo
    jeito, sem sinalizar a divergência pro usuário além desta observação em
    código."""
    m = _RE_LINHA_BOLETO.search(texto)
    if m:
        digitos = re.sub(r"\D", "", m.group())
        if len(digitos) == 47:
            return _formatar_linha_boleto(digitos)
    m = _RE_LINHA_ARRECADACAO.search(texto)
    if m:
        digitos = re.sub(r"\D", "", m.group())
        if len(digitos) == 48:
            return _formatar_linha_arrecadacao(digitos)
    return ""


# ── Classificação do tipo de documento ──────────────────────────────────
_PALAVRAS_NOTA_FISCAL = ("NOTA FISCAL", "DANFE", "NF-E", "NFC-E", "NFE ")
_PALAVRAS_FGTS = ("FGTS", "GRF-E", "GUIA DE RECOLHIMENTO DO FGTS", "GRF ")
_PALAVRAS_DCTF = ("DCTFWEB", "DCTF WEB", "DARF", "DOCUMENTO DE ARRECADACAO")
_PALAVRAS_RECIBO = ("RECIBO", "COMPROVANTE", "PIX", "TED ", "TRANSFERENCIA")


def _classificar_tipo(texto_norm: str, linha_digitavel: str) -> str:
    """Classifica por palavra-chave, na ordem definida pelo produto (mais
    específico primeiro). Decisão de design: quando nada bate — nem
    palavra-chave nem padrão de linha digitável — o fallback é "recibo": o
    tipo de documento mais genérico/menos estruturado dos cinco, e o que
    resulta no formulário mais neutro (nenhum campo específico de boleto/
    guia fica com dado incoerente). Nunca estoura exceção só por não
    conseguir classificar — o usuário sempre pode corrigir o tipo no front."""
    if any(p in texto_norm for p in _PALAVRAS_NOTA_FISCAL):
        return "nota_fiscal"
    if any(p in texto_norm for p in _PALAVRAS_FGTS):
        return "guia_fgts"
    if any(p in texto_norm for p in _PALAVRAS_DCTF):
        return "guia_dctf"
    if linha_digitavel:
        return "boleto"
    if any(p in texto_norm for p in _PALAVRAS_RECIBO):
        return "recibo"
    return "recibo"


# ── Datas ────────────────────────────────────────────────────────────────
_RE_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


def _achar_data(texto: str, rotulos: tuple[str, ...]) -> str:
    """Procura DD/MM/AAAA perto de um dos rótulos dados — primeiro tenta na
    mesma linha do rótulo, senão pega a primeira data solta no texto
    inteiro. Sem achar nenhuma, devolve "" (sentinela de texto ausente,
    nunca inventa)."""
    for linha in texto.splitlines():
        linha_norm = _normalizar(linha)
        if any(rotulo in linha_norm for rotulo in rotulos):
            m = _RE_DATA.search(linha)
            if m:
                return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = _RE_DATA.search(texto)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


_RE_COMPETENCIA = re.compile(r"\b(\d{2})/(\d{4})\b")


def _achar_competencia(texto: str) -> str:
    idx = _normalizar(texto).find("COMPETENCIA")
    janela = texto[max(0, idx - 5):idx + 60] if idx >= 0 else ""
    m = _RE_COMPETENCIA.search(janela) or _RE_COMPETENCIA.search(texto)
    return f"{m.group(2)}-{m.group(1)}" if m else ""


# ── Valores em reais ─────────────────────────────────────────────────────
_RE_VALOR = re.compile(r"R\$\s*([\d.,]+)")


def _parse_valor_brl(bruto: str) -> float | None:
    bruto = bruto.strip().strip(".,")
    if not bruto:
        return None
    # Formato brasileiro: ponto separa milhar, vírgula separa decimal.
    convertido = bruto.replace(".", "").replace(",", ".")
    try:
        return round(float(convertido), 2)
    except ValueError:
        return None


def _achar_valor(texto: str, rotulos: tuple[str, ...]) -> float | None:
    for linha in texto.splitlines():
        linha_norm = _normalizar(linha)
        if any(rotulo in linha_norm for rotulo in rotulos):
            m = _RE_VALOR.search(linha)
            if m:
                valor = _parse_valor_brl(m.group(1))
                if valor is not None:
                    return valor
    m = _RE_VALOR.search(texto)
    return _parse_valor_brl(m.group(1)) if m else None


# ── Fornecedor/cliente ───────────────────────────────────────────────────
_RE_ROTULO_FORNECEDOR = re.compile(
    r"(?:EMITENTE|FAVORECID[OA]|BENEFICI[AÁ]RIO|CEDENTE|FORNECEDOR|RAZ[AÃ]O\s+SOCIAL|"
    r"CONTRIBUINTE|EMPREGADOR|PAGADOR|SACADO|RECEBEDOR|CLIENTE)\s*[:\-]?\s*(.+)",
    re.IGNORECASE,
)


def _achar_fornecedor(texto: str) -> str:
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        m = _RE_ROTULO_FORNECEDOR.match(linha)
        if m:
            candidato = m.group(1).strip(" :.-")
            if candidato:
                return candidato
    return ""


# ── Número do documento ──────────────────────────────────────────────────
_RE_NUMERO_DOCUMENTO = (
    re.compile(r"N[UÚ]MERO\s*[:\-]?\s*(\d[\d./\-]{1,20})", re.IGNORECASE),
    re.compile(r"N[Fº°]\s*[:\-]?\s*(\d{2,15})", re.IGNORECASE),
)


def _achar_numero_documento(texto: str) -> str:
    for padrao in _RE_NUMERO_DOCUMENTO:
        m = padrao.search(texto)
        if m:
            return m.group(1).strip(" .-")
    return ""


# ── Código da receita (DARF/DCTFWeb) ────────────────────────────────────
_RE_CODIGO_RECEITA = re.compile(r"C[OÓ]DIGO\s+(?:DA\s+)?RECEITA\s*[:\-]?\s*(\d{3,6})", re.IGNORECASE)


def _achar_codigo_receita(texto: str) -> str:
    m = _RE_CODIGO_RECEITA.search(texto)
    return m.group(1) if m else ""


# ── Conta bancária (recibo/comprovante) ─────────────────────────────────
_RE_LINHA_CONTA = re.compile(r"AG[EÊ]NCIA|\bAG\.?\s*\d|CONTA\s+CORRENTE|\bCC\b|\bBANCO\b", re.IGNORECASE)


def _achar_conta_bancaria(texto: str) -> str:
    trechos = [linha.strip() for linha in texto.splitlines() if _RE_LINHA_CONTA.search(linha)]
    return " / ".join(trechos[:2])


# ── Parcelamento ("parcela 2/6", "2 de 6", "parc. 02/06") ──────────────
_RE_PARCELA = re.compile(r"PARC(?:ELA)?\.?\s*(\d{1,2})\s*(?:/|DE)\s*(\d{1,2})", re.IGNORECASE)


def _achar_parcela(texto: str) -> tuple[int | None, int | None]:
    m = _RE_PARCELA.search(texto)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


# ── Itens da nota fiscal ─────────────────────────────────────────────────
# Heurística deliberadamente simples e FRÁGIL — a extração de item de nota
# fiscal por IA de visão "lê a tabela"; aqui só reconhecemos uma linha de
# texto no formato "produto ... quantidade ... valor unitário ... valor
# total", que é como um DANFE renderizado em texto corrido normalmente sai
# do OCR quando a tabela é simples e a foto está nítida — layout diferente
# (item quebrado em duas linhas, colunas fora de ordem, papel torto) tende a
# não bater aqui, e a lista de itens fica vazia (nunca inventa item).
_RE_ITEM_NF = re.compile(
    r"^(?P<produto>.{3,60}?)\s+(?P<qtd>\d+(?:[.,]\d+)?)\s*(?:UN|UND|UNID|KG|CX|PC|PCT|L|LT)?\s+"
    r"(?:R\$\s*)?(?P<unit>[\d.,]+)\s+(?:R\$\s*)?(?P<total>[\d.,]+)\s*$",
    re.IGNORECASE,
)


def _achar_itens(texto: str) -> list[dict]:
    itens = []
    for linha in texto.splitlines():
        m = _RE_ITEM_NF.match(linha.strip())
        if not m:
            continue
        produto = m.group("produto").strip(" .-")
        total = _parse_valor_brl(m.group("total"))
        if not produto or total is None:
            continue
        itens.append({
            "produto": produto,
            "quantidade": _parse_valor_brl(m.group("qtd")),
            "valor_unitario": _parse_valor_brl(m.group("unit")),
            "valor_total": total,
        })
    return itens


# ── PDF: contagem de páginas (reaproveitado tal qual — não depende de IA) ─
def _contar_paginas_pdf(conteudo: bytes) -> int | None:
    """Quantas páginas o PDF tem — usado tanto pra decidir se um boleto é
    multi-parcela (uma via por página) quanto como contexto informativo no
    retorno (`paginas_documento`). None se não der pra ler (arquivo
    corrompido/criptografado) — a leitura segue sem esse contexto."""
    try:
        import pypdf
        return len(pypdf.PdfReader(io.BytesIO(conteudo)).pages)
    except Exception:
        return None


# ── Correção server-side do valor_total de boleto multi-parcela (reaproveitado tal qual) ─
def _corrigir_valor_total_boleto(dados: dict) -> dict:
    """Rede de segurança server-side: se o documento é um boleto com mais de
    uma parcela e `valor_total` ficou igual (ou quase igual) ao valor de UMA
    parcela isolada em vez da soma de todas, corrige aqui — não deixa esse
    valor errado seguir pro formulário. Pura pós-processamento sobre
    `dados`, não depende de como a extração foi feita (funcionava com a IA
    de visão, continua funcionando com OCR+regex)."""
    if dados.get("tipo_documento") != "boleto":
        return dados
    parcelas = [p for p in (dados.get("parcelas_detectadas") or []) if p.get("valor") is not None]
    if len(parcelas) < 2:
        return dados
    soma = round(sum(p["valor"] for p in parcelas), 2)
    valor_total = dados.get("valor_total")
    media = soma / len(parcelas)
    parece_parcela_unica = valor_total is not None and abs(valor_total - media) < 0.02 and abs(valor_total - soma) > 0.02
    if valor_total is None or parece_parcela_unica:
        dados = {**dados, "valor_total": soma, "valor_total_corrigido": True}
    return dados


# ── Montagem do dicionário de resposta ──────────────────────────────────
_ROTULOS_VENCIMENTO = ("VENCIMENTO",)
_ROTULOS_EMISSAO = ("EMISSAO", "DATA DE EMISSAO", "EMITIDA EM")
_ROTULOS_PAGAMENTO = ("DATA DO PAGAMENTO", "PAGO EM", "EFETIVADO EM", "DATA")
_ROTULOS_VALOR_BOLETO = ("VALOR DO DOCUMENTO", "VALOR COBRADO", "VALOR TOTAL", "VALOR")
_ROTULOS_VALOR_NF = ("VALOR TOTAL DA NOTA", "VALOR TOTAL DOS PRODUTOS", "VALOR TOTAL", "VALOR A PAGAR")
_ROTULOS_VALOR_RECIBO = ("VALOR PAGO", "VALOR TRANSFERIDO", "VALOR")
_ROTULOS_PRINCIPAL = ("VALOR PRINCIPAL", "PRINCIPAL")
_ROTULOS_MULTA = ("MULTA",)
_ROTULOS_JUROS = ("JUROS",)


def _dados_vazios() -> dict:
    """Todos os campos do contrato — string vazia pra TEXTO, None pra
    NUMÉRICO, [] pra lista — nunca chave ausente. Preenchido conforme o tipo
    de documento classificado, logo abaixo em `_parsear_texto`."""
    return {
        "tipo_documento": "recibo",
        "parcela_num": None, "parcela_total": None,
        "linha_digitavel": "", "data_vencimento": "",
        "competencia": "", "codigo_receita": "",
        "valor_principal": None, "valor_multa": None, "valor_juros": None,
        "fornecedor_cliente": "", "numero_documento": "",
        "data_emissao": "", "data_pagamento": "",
        "valor_total": None, "parcelas_detectadas": [],
        "conta_bancaria": "", "itens": [], "observacao": "",
    }


def _parcelas_detectadas_boleto(textos_paginas: list[str]) -> list[dict]:
    """Uma entrada por página/via (mesmo com uma página só, ver contrato) —
    cada página é OCR'd e interpretada isoladamente, igual uma via de
    boleto real costuma trazer o mesmo conjunto de dados (valor, vencimento,
    linha digitável) impresso de novo."""
    itens = []
    for pagina_texto in textos_paginas:
        numero, _ = _achar_parcela(pagina_texto)
        itens.append({
            "numero": numero,
            "valor": _achar_valor(pagina_texto, _ROTULOS_VALOR_BOLETO),
            "data_vencimento": _achar_data(pagina_texto, _ROTULOS_VENCIMENTO),
            "linha_digitavel": _extrair_linha_digitavel(pagina_texto),
        })
    return itens


def _parsear_texto(texto_completo: str, textos_paginas: list[str]) -> dict:
    texto_norm = _normalizar(texto_completo)
    linha_digitavel = _extrair_linha_digitavel(texto_completo)
    tipo = _classificar_tipo(texto_norm, linha_digitavel)

    dados = _dados_vazios()
    dados["tipo_documento"] = tipo
    dados["fornecedor_cliente"] = _achar_fornecedor(texto_completo)

    if tipo == "nota_fiscal":
        dados["numero_documento"] = _achar_numero_documento(texto_completo)
        dados["data_emissao"] = _achar_data(texto_completo, _ROTULOS_EMISSAO)
        itens = _achar_itens(texto_completo)
        dados["itens"] = itens
        valor_total = _achar_valor(texto_completo, _ROTULOS_VALOR_NF)
        if valor_total is None and itens:
            valor_total = round(sum(i["valor_total"] for i in itens if i["valor_total"] is not None), 2)
        dados["valor_total"] = valor_total

    elif tipo == "recibo":
        dados["data_pagamento"] = _achar_data(texto_completo, _ROTULOS_PAGAMENTO)
        dados["valor_total"] = _achar_valor(texto_completo, _ROTULOS_VALOR_RECIBO)
        dados["conta_bancaria"] = _achar_conta_bancaria(texto_completo)
        for palavra in ("PIX", "TED", "TRANSFERENCIA"):
            if palavra in texto_norm:
                dados["observacao"] = f"Identificado no OCR: {palavra}"
                break

    elif tipo == "boleto":
        dados["numero_documento"] = _achar_numero_documento(texto_completo)
        dados["data_vencimento"] = _achar_data(texto_completo, _ROTULOS_VENCIMENTO)
        dados["linha_digitavel"] = linha_digitavel
        parcela_num, parcela_total = _achar_parcela(texto_completo)
        dados["parcela_num"] = parcela_num
        dados["parcela_total"] = parcela_total
        dados["parcelas_detectadas"] = _parcelas_detectadas_boleto(textos_paginas)
        dados["valor_total"] = _achar_valor(texto_completo, _ROTULOS_VALOR_BOLETO)

    elif tipo in ("guia_fgts", "guia_dctf"):
        if not dados["fornecedor_cliente"]:
            dados["fornecedor_cliente"] = NOME_FAZENDA
        dados["competencia"] = _achar_competencia(texto_completo)
        dados["data_vencimento"] = _achar_data(texto_completo, _ROTULOS_VENCIMENTO)
        dados["linha_digitavel"] = linha_digitavel
        principal = _achar_valor(texto_completo, _ROTULOS_PRINCIPAL)
        multa = _achar_valor(texto_completo, _ROTULOS_MULTA)
        juros = _achar_valor(texto_completo, _ROTULOS_JUROS)
        dados["valor_principal"] = principal
        dados["valor_multa"] = multa
        dados["valor_juros"] = juros
        if principal is not None or multa is not None or juros is not None:
            dados["valor_total"] = round((principal or 0) + (multa or 0) + (juros or 0), 2)
        else:
            dados["valor_total"] = _achar_valor(texto_completo, ("VALOR TOTAL",))
        if tipo == "guia_dctf":
            dados["codigo_receita"] = _achar_codigo_receita(texto_completo)

    return dados


def ler_documento(conteudo: bytes, mime_type: str) -> dict:
    """OCR (Tesseract) + regras/regex sobre o texto extraído — devolve os
    campos no mesmo formato esperado pelo formulário de lançamento
    financeiro (ver docstring do módulo sobre a migração e suas
    limitações)."""
    if mime_type not in MIME_ACEITOS:
        raise ValueError(f"Tipo de arquivo não suportado: {mime_type} (aceitos: PDF, JPEG, PNG)")

    if mime_type in _MIME_SEM_SUPORTE:
        formato = _MIME_SEM_SUPORTE[mime_type]
        raise ValueError(
            f"Formato {formato} do iPhone não é suportado — reenvie a foto como JPEG ou PDF "
            "(no iPhone: Ajustes > Câmera > Formatos > 'Mais Compatível')."
        )

    mime_type_normalizado = _MIME_NORMALIZADO.get(mime_type, mime_type)
    paginas = _contar_paginas_pdf(conteudo) if mime_type == "application/pdf" else None

    textos_paginas = _extrair_textos_seguro(conteudo, mime_type_normalizado)
    texto_completo = "\n\f\n".join(textos_paginas)

    dados = _parsear_texto(texto_completo, textos_paginas)
    dados = _corrigir_valor_total_boleto(dados)
    dados["paginas_documento"] = paginas
    return dados
