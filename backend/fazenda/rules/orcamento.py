"""
Orçado × realizado com as regras v2 (Fase A, PR 8) — motor puro, sem Session.

Recebe as linhas ORÇADAS (uma por código de conta, já somadas no período) e
os registros da DRE de competência (`financeiro.registros_competencia_v2`: a
mesma fonte da cascata — vale descontado, desconto da nota rateado, receita
bruta + dedução, folha pelo bruto, cartão por item, natureza resolvida) e
devolve as linhas do comparativo e os TOTAIS SEPARADOS por grupo.

Regras (decisões do dono, SOLUCOES §3 "Solução do orçamento"):

1. Grupos, nunca misturados num total só:
   - `receita` (registro de receita operacional);
   - `deducao` (desconto/Funrural da nota de venda, PR 4);
   - `despesa_operacional` (despesa operacional; o item redutor da folha
     abate);
   - `fora_do_resultado` (natureza ≠ operacional — investimento,
     financiamento, capital, adiantamento, obrigação — ou conta
     NAO_ENTRA_NA_DRE): mostrado, sem desvio.
2. Herança por prefixo (Q8): o realizado de uma conta SEM orçamento próprio
   vai para o ancestral orçado mais próximo DO MESMO TIPO (receita/despesa) —
   o orçamento do grupo cobre só as filhas sem orçamento próprio; a filha com
   orçamento próprio fica na linha dela. A filha coberta aparece também como
   linha informativa (`coberta_por`), sem desvio e fora dos totais (o valor
   dela já está no grupo). Fora do resultado e deduções nunca sobem para um
   orçamento de despesa/receita.
3. Desvio só existe com orçado: linha sem orçamento fica `sem_orcamento`
   (neutra). Receita acima do orçado é favorável; despesa acima,
   desfavorável.
"""
from __future__ import annotations

from fazenda.rules.dre import NAO_ENTRA_NA_DRE, resolver_linha_dre
from fazenda.rules.juros_descontos import ORIGEM_DEDUCAO_NOTA
from fazenda.rules.natureza import OPERACIONAL

GRUPOS = ("receita", "deducao", "despesa_operacional", "fora_do_resultado")
ROTULOS_GRUPO = {
    "receita": "Receitas",
    "deducao": "Deduções da receita",
    "despesa_operacional": "Despesas operacionais",
    "fora_do_resultado": "Fora do resultado (investimento, financiamento, capital…)",
}
SEM_CONTA = "(sem conta)"


def _grupo_do_registro(registro: dict, mapa_linha: dict[str, str]) -> tuple[str, str]:
    """(grupo, tipo efetivo) — o tipo do item redutor é o da nota (abate)."""
    tipo = (registro.get("tipo_nota") if registro.get("redutor") else registro.get("tipo")) or registro.get("tipo_nota") or "despesa"
    natureza = registro.get("natureza") or OPERACIONAL
    if natureza != OPERACIONAL or resolver_linha_dre(registro.get("codigo_conta"), mapa_linha) == NAO_ENTRA_NA_DRE:
        return "fora_do_resultado", tipo
    if registro.get("origem") == ORIGEM_DEDUCAO_NOTA:
        return "deducao", "despesa"
    return ("receita" if tipo == "receita" else "despesa_operacional"), tipo


def _grupo_do_tipo(tipo: str) -> str:
    return "receita" if tipo == "receita" else "despesa_operacional"


def _ancestral_orcado(codigo: str, tipo: str, orcadas: dict[str, dict]) -> str | None:
    """O código orçado mais específico que é o próprio `codigo` ou um
    ancestral dele (herança por prefixo: "8.2.1" → "8.2" → "8"), do mesmo tipo."""
    if codigo.startswith("("):
        return codigo if codigo in orcadas and orcadas[codigo]["tipo"] == tipo else None
    partes = codigo.split(".")
    for fim in range(len(partes), 0, -1):
        prefixo = ".".join(partes[:fim])
        linha = orcadas.get(prefixo)
        if linha is not None and linha["tipo"] == tipo:
            return prefixo
    return None


def _situacao(grupo: str, orcado: float, realizado: float) -> str:
    if grupo == "fora_do_resultado":
        return "fora_do_resultado"
    if not orcado:
        return "sem_orcamento"
    desvio = round(realizado - orcado, 2)
    if desvio == 0:
        return "no_orcado"
    favoravel = desvio > 0 if grupo == "receita" else desvio < 0
    return "favoravel" if favoravel else "desfavoravel"


def _desvios(grupo: str, orcado: float, realizado: float) -> dict:
    if grupo == "fora_do_resultado" or not orcado:
        return {"desvio": None, "desvio_pct": None, "situacao": _situacao(grupo, orcado, realizado)}
    desvio = round(realizado - orcado, 2)
    return {"desvio": desvio, "desvio_pct": round(desvio / orcado * 100, 1), "situacao": _situacao(grupo, orcado, realizado)}


def comparar_orcado_realizado(
    orcadas: dict[str, dict], registros: list[dict], mapa_linha: dict[str, str], nomes: dict[str, str],
) -> dict:
    """`orcadas`: {codigo: {"codigo_conta_gerencial", "nome_conta_gerencial",
    "tipo", "orcado", "realizado"}} (o realizado chega zerado). Devolve
    {"linhas": [...], "totais": {grupo: {orcado, realizado, desvio,
    desvio_pct, situacao}}}."""
    linhas: dict[str, dict] = {}
    for codigo, l in orcadas.items():
        linhas[codigo] = {**l, "realizado": 0.0, "grupo": _grupo_do_tipo(l["tipo"]), "coberta_por": None, "cobre": []}
    filhas: dict[str, dict] = {}

    for r in registros:
        valor = r.get("valor") or 0.0
        if not valor:
            continue
        valor = -valor if r.get("redutor") else valor
        grupo, tipo = _grupo_do_registro(r, mapa_linha)
        codigo = r.get("codigo_conta") or SEM_CONTA
        nome = nomes.get(codigo, r.get("descricao") or codigo)

        if codigo in linhas and (grupo != "fora_do_resultado" or codigo in orcadas):
            # Linha da própria conta (orçada ou já criada). Orçamento numa conta
            # que só tem movimento fora do resultado passa a ser lida como tal.
            alvo = linhas[codigo]
            if grupo in ("fora_do_resultado", "deducao") and alvo["grupo"] != grupo:
                alvo["grupo"] = grupo
            alvo["realizado"] = round(alvo["realizado"] + valor, 2)
            continue

        destino = _ancestral_orcado(codigo, tipo, orcadas) if grupo in ("receita", "despesa_operacional") else None
        if destino is not None and destino != codigo:
            pai = linhas[destino]
            pai["realizado"] = round(pai["realizado"] + valor, 2)
            filha = filhas.setdefault(codigo, {
                "codigo_conta_gerencial": codigo, "nome_conta_gerencial": nome, "tipo": tipo,
                "orcado": 0.0, "realizado": 0.0, "grupo": grupo, "coberta_por": destino, "cobre": [],
            })
            filha["realizado"] = round(filha["realizado"] + valor, 2)
            if codigo not in pai["cobre"]:
                pai["cobre"].append(codigo)
            continue

        alvo = linhas.setdefault(codigo, {
            "codigo_conta_gerencial": codigo, "nome_conta_gerencial": nome, "tipo": tipo,
            "orcado": 0.0, "realizado": 0.0, "grupo": grupo, "coberta_por": None, "cobre": [],
        })
        alvo["realizado"] = round(alvo["realizado"] + valor, 2)

    ordem_grupo = {g: i for i, g in enumerate(GRUPOS)}
    resultado: list[dict] = []
    for l in sorted(linhas.values(), key=lambda x: (ordem_grupo[x["grupo"]], x["codigo_conta_gerencial"])):
        l["cobre"] = sorted(l["cobre"])
        resultado.append({**l, **_desvios(l["grupo"], l["orcado"], l["realizado"])})
        for codigo_filha in l["cobre"]:
            filha = filhas[codigo_filha]
            resultado.append({**filha, "desvio": None, "desvio_pct": None, "situacao": "coberta_pelo_grupo"})

    totais: dict[str, dict] = {}
    for grupo in GRUPOS:
        do_grupo = [l for l in resultado if l["grupo"] == grupo and l["coberta_por"] is None]
        orcado = round(sum(l["orcado"] for l in do_grupo), 2)
        realizado = round(sum(l["realizado"] for l in do_grupo), 2)
        totais[grupo] = {"rotulo": ROTULOS_GRUPO[grupo], "orcado": orcado, "realizado": realizado,
                         **_desvios(grupo, orcado, realizado)}
    return {"linhas": resultado, "totais": totais}
