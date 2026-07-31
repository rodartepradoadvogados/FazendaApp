"""
Motor de casamento (fuzzy match) entre um texto vindo de nota fiscal/NFS-e
(nome de fornecedor, descrição de produto ou de serviço) e uma lista de
candidatos já cadastrados no sistema — para uma futura UI de confirmação
sugerir (ou não) o item do cadastro que corresponde ao que veio na nota.

Funções puras, sem acesso a banco nem a rede: quem busca os candidatos no
cadastro (fornecedores, produtos de estoque, serviços) é a camada de cima —
este módulo só recebe a string da nota e a lista de candidatos e devolve o
melhor casamento, com um score e um nível de confiança.

Sem dependência nova: usa só `difflib.SequenceMatcher` (stdlib) mais uma
normalização própria (minúsculas, sem acento, sem pontuação, espaços
colapsados, sem palavras-ruído de razão social).
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Palavras "ruído" comuns em razão social — tipo societário ou ramo genérico
# — que não ajudam a diferenciar um fornecedor de outro e frequentemente
# aparecem só de um lado da comparação (a nota fiscal escreve por extenso
# "LTDA", o cadastro do usuário às vezes omite). Removidas antes de comparar,
# senão "AGROPECUARIA SAO JOSE LTDA" nunca bateria com "Agropecuária São
# José" — mesma empresa, só que sem o sufixo societário.
PALAVRAS_RUIDO = {
    "ltda", "me", "eireli", "sa", "s/a",
    "comercio", "com", "industria", "ind",
    "cia", "companhia",
    "importacao", "exportacao",
    "distribuidora", "distribuicao",
}

_PONTUACAO = re.compile(r"[.,;:/\\\-_()\[\]{}'\"!?]")
_ESPACOS = re.compile(r"\s+")

# Níveis de confiança que `melhor_candidato` devolve.
EXATO = "exato"
PROVAVEL = "provavel"
INCERTO = "incerto"

# Limiar de score (SequenceMatcher.ratio(), 0.0–1.0) acima do qual um match
# não-idêntico já é "provável" o suficiente para sugerir preenchido (mas
# ainda pedindo confirmação do usuário, nunca preenchendo sozinho sem
# revisão). Escolhido observando o padrão de diferenças reais entre nota e
# cadastro: variações de sufixo/abreviação/embalagem (ex.: "Ração
# Concentrada 25kg" vs "Ração Concentrada" cadastrado sem o peso) tendem a
# cair na faixa 0.80–0.95, enquanto nomes de itens genuinamente diferentes
# (fornecedores distintos, produtos de categorias diferentes) ficam bem
# abaixo de 0.80 mesmo compartilhando alguma palavra comum. 0.80 dá uma
# margem seguindo esse padrão sem exigir cada caractere igual (o que já é
# coberto por EXATO, que não usa este limiar).
LIMIAR_PROVAVEL = 0.80


def normalizar(texto: str | None) -> str:
    """Minúsculas, sem acento, sem pontuação, espaços colapsados, sem
    palavras-ruído de razão social. Usada tanto para fornecedor quanto para
    produto/serviço — as palavras-ruído removidas são específicas de razão
    social e praticamente nunca aparecem em nome de produto/serviço, então
    aplicá-las nos três casos não causa falso positivo."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    sem_pontuacao = _PONTUACAO.sub(" ", sem_acento.lower())
    palavras = [p for p in sem_pontuacao.split() if p not in PALAVRAS_RUIDO]
    return _ESPACOS.sub(" ", " ".join(palavras)).strip()


def _score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def melhor_candidato(texto: str | None, candidatos: list[str]) -> dict:
    """
    Compara `texto` (vindo da nota — nome de fornecedor, descrição de
    produto ou de serviço) contra cada string em `candidatos` (vindos do
    cadastro) e devolve o de maior score, junto do nível de confiança:

    - "exato": os textos normalizados são idênticos — pode preencher direto.
    - "provavel": score alto (>= LIMIAR_PROVAVEL) mas não idêntico — a UI
      deve sugerir o candidato já preenchido, mas pedindo confirmação.
    - "incerto": score baixo — não preenche nada, deixa em branco para o
      usuário escolher ou cadastrar um novo.

    Serve igualmente para fornecedor, produto de estoque e serviço — a
    função não sabe (nem precisa saber) qual dos três está comparando.

    `texto` vazio/None ou `candidatos` vazia devolvem confiança "incerto"
    com `candidato=None`, nunca lançam erro.
    """
    texto_norm = normalizar(texto)
    if not texto_norm or not candidatos:
        return {"candidato": None, "score": 0.0, "confianca": INCERTO}

    melhor: str | None = None
    melhor_score = -1.0
    for candidato in candidatos:
        candidato_norm = normalizar(candidato)
        if not candidato_norm:
            continue
        score = _score(texto_norm, candidato_norm)
        if score > melhor_score:
            melhor_score = score
            melhor = candidato

    if melhor is None:
        return {"candidato": None, "score": 0.0, "confianca": INCERTO}

    if melhor_score >= 1.0:
        confianca = EXATO
    elif melhor_score >= LIMIAR_PROVAVEL:
        confianca = PROVAVEL
    else:
        confianca = INCERTO

    return {"candidato": melhor, "score": round(melhor_score, 4), "confianca": confianca}
