"""
Conciliação bancária — sugestão de pareamento entre as linhas do extrato e o
que passou pelo banco no sistema (lançamentos pagos e transferências entre
contas). Funções PURAS: recebem dicionários já lidos e devolvem sugestões; o
router grava só quando a pessoa confirma.

Regra do casamento (nunca por texto livre sozinho — o texto só desempata):
  • mesmo SINAL (entrada × entrada, saída × saída);
  • VALOR igual ao centavo (|Δ| < R$ 0,01) — "exata";
    ou até 10% de diferença (juros de mora, tarifa embutida) — "valor
    diferente", só como alternativa, nunca confirmada em lote;
  • DATA dentro da tolerância (padrão: 3 dias corridos para os dois lados —
    compensação de boleto, TED no dia seguinte);
  • pontuação = 100 − 10 × dias de distância + 20 × semelhança do texto
    (palavras em comum entre o histórico do banco e fornecedor/descrição).
Cada movimento do sistema casa com UMA linha só: a atribuição é gulosa pela
maior pontuação, e o que sobra continua pendente.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

TOLERANCIA_DIAS = 3
TOLERANCIA_VALOR_PCT = 0.10
_PALAVRAS_VAZIAS = {
    "pix", "ted", "doc", "pag", "pagto", "pagamento", "pagamentos", "transf", "transferencia", "enviado",
    "enviada", "recebido", "recebida", "compra", "cartao", "debito", "credito", "boleto", "tit", "titulo",
    "ltda", "eireli", "s/a", "com", "dos", "das", "para", "por", "via", "conta", "deb", "aut",
}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def palavras(texto: str | None) -> set[str]:
    t = _sem_acento((texto or "").lower())
    return {p for p in re.findall(r"[a-z0-9]{3,}", t) if p not in _PALAVRAS_VAZIAS and not p.isdigit()}


def semelhanca(a: str | None, b: str | None) -> float:
    pa, pb = palavras(a), palavras(b)
    if not pa or not pb:
        return 0.0
    return round(len(pa & pb) / len(pa | pb), 3)


def _dias(a: date, b: date) -> int:
    return abs((a - b).days)


def pontuar(linha: dict, cand: dict, tolerancia_dias: int = TOLERANCIA_DIAS) -> dict | None:
    """Pontua um candidato para a linha. None quando não serve (sinal, data ou valor)."""
    vl, vc = float(linha["valor"]), float(cand["valor"])
    if vl == 0 or vc == 0 or (vl > 0) != (vc > 0):
        return None
    d = _dias(linha["data"], cand["data"])
    if d > tolerancia_dias:
        return None
    dif = round(abs(vl) - abs(vc), 2)
    exata = abs(dif) < 0.01
    if not exata and abs(dif) > abs(vl) * TOLERANCIA_VALOR_PCT:
        return None
    sim = semelhanca(linha.get("historico"), f"{cand.get('fornecedor') or ''} {cand.get('descricao') or ''}")
    score = 100 - 10 * d + 20 * sim - (0 if exata else 40)
    return {
        "tipo": cand["tipo"], "id": cand["id"], "data": cand["data"], "valor": vc,
        "descricao": cand.get("descricao"), "fornecedor": cand.get("fornecedor"),
        "numero_lancamento": cand.get("numero_lancamento"),
        "exata": exata, "diferenca": round(abs(vl) - abs(vc), 2) * (1 if vl > 0 else -1) if not exata else 0.0,
        "dias": d, "semelhanca": sim, "pontuacao": round(score, 1),
    }


def sugerir(linhas: list[dict], candidatos: list[dict], tolerancia_dias: int = TOLERANCIA_DIAS) -> dict[int, dict]:
    """Para cada linha PENDENTE do extrato: {"sugestao": melhor exata única ou None,
    "alternativas": até 3 outras (inclusive valor diferente)}.

    `linhas`: [{"id", "data", "valor", "historico"}]; `candidatos`:
    [{"tipo": "lancamento"|"transferencia", "id", "data", "valor" (com sinal),
    "descricao", "fornecedor", "numero_lancamento"}] — só os ainda NÃO pareados."""
    por_linha: dict[int, list[dict]] = {}
    pares: list[tuple[float, int, str]] = []
    for l in linhas:
        opcoes = []
        for c in candidatos:
            p = pontuar(l, c, tolerancia_dias)
            if p is not None:
                opcoes.append(p)
                if p["exata"]:
                    pares.append((p["pontuacao"], l["id"], f"{c['tipo']}:{c['id']}"))
        opcoes.sort(key=lambda p: -p["pontuacao"])
        por_linha[l["id"]] = opcoes
    # Atribuição gulosa: maior pontuação primeiro; cada lado usado uma vez.
    usados_linha: set[int] = set()
    usados_cand: set[str] = set()
    escolhida: dict[int, str] = {}
    for _score, lid, cid in sorted(pares, key=lambda x: (-x[0], x[1])):
        if lid in usados_linha or cid in usados_cand:
            continue
        usados_linha.add(lid)
        usados_cand.add(cid)
        escolhida[lid] = cid
    saida: dict[int, dict] = {}
    for l in linhas:
        opcoes = por_linha.get(l["id"], [])
        cid = escolhida.get(l["id"])
        sug = next((o for o in opcoes if f"{o['tipo']}:{o['id']}" == cid), None)
        alternativas = [o for o in opcoes if o is not sug][:3]
        saida[l["id"]] = {"sugestao": sug, "alternativas": alternativas}
    return saida


def resumo_saldos(saldo_extrato: float | None, saldo_sistema: float | None) -> dict:
    """Diferença extrato × sistema (None quando falta um dos lados)."""
    if saldo_extrato is None or saldo_sistema is None:
        return {"saldo_extrato": saldo_extrato, "saldo_sistema": saldo_sistema, "diferenca": None, "bate": None}
    dif = round(saldo_extrato - saldo_sistema, 2)
    return {"saldo_extrato": round(saldo_extrato, 2), "saldo_sistema": round(saldo_sistema, 2), "diferenca": dif, "bate": abs(dif) < 0.01}
