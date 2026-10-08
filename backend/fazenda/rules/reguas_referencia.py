"""
Réguas de referência (Financeiro > Relatórios): faixas de mercado para comparar os
indicadores da fazenda, com fonte, selo de fidedignidade e prazo de validade.

Os dados ficam em `seed_data/reguas_referencia.json`, versionado no git e atualizado
por pull request pela rotina mensal (docs/agents/reguas-referencia-mensal.md). O
arquivo é igual para todas as fazendas: não há dado de cliente aqui, e o cliente não
edita a faixa (a "meta própria" mora nos parâmetros da fazenda).

Regras que o validador faz valer (e o CI testa):
- uma régua só é VALIDADA com pelo menos uma fonte nacional e uma internacional;
- selo "alta" exige duas nacionais, duas internacionais e fontes de no máximo 3 anos;
- régua NAO_VALIDADA nunca exibe faixa;
- fonte com licença que não permite uso comercial (AHDB, IFCN, Cepea) não entra;
- passou da validade: a faixa some e a tela mostra "sem referência atualizada".
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

ARQUIVO = Path(__file__).resolve().parent.parent / "seed_data" / "reguas_referencia.json"

CLASSES = {"VALIDADA", "VALIDADA_COM_RESSALVA", "PARCIAL", "NAO_VALIDADA"}
SELOS = {"alta", "media", "baixa", None}
ORIGENS = {"nacional", "internacional"}
LICENCAS = {"reproducao_com_fonte", "citar_com_link", "nao_verificada"}
# Fontes cuja licença não permite uso comercial num SaaS pago: o validador recusa.
HOSTS_VETADOS = ("ahdb.org.uk", "ifcndairy.org", "dairyreport.online", "cepea.org.br", "cepea.esalq.usp.br")
IDADE_MAXIMA_SELO_ALTO = 3  # anos


def carregar() -> dict[str, Any]:
    with open(ARQUIVO, encoding="utf-8") as f:
        return json.load(f)


def _data(txt: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(txt))
    except (TypeError, ValueError):
        return None


def validar(dados: dict[str, Any], hoje: Optional[date] = None) -> list[str]:
    """Devolve a lista de problemas (vazia = arquivo válido)."""
    hoje = hoje or date.today()
    erros: list[str] = []

    datas = {k: _data(dados.get(k)) for k in ("revisado_em", "conferida_em", "valido_ate", "proxima_conferencia")}
    for k, v in datas.items():
        if v is None:
            erros.append(f"{k}: data inválida ou ausente")
    if not erros:
        if datas["revisado_em"] > hoje or datas["conferida_em"] > hoje:
            erros.append("revisado_em/conferida_em estão no futuro")
        if datas["conferida_em"] < datas["revisado_em"]:
            erros.append("conferida_em anterior a revisado_em")
        if datas["valido_ate"] <= datas["revisado_em"]:
            erros.append("valido_ate deve ser posterior a revisado_em")
        if datas["proxima_conferencia"] <= datas["conferida_em"]:
            erros.append("proxima_conferencia deve ser posterior a conferida_em")

    fontes: dict[str, dict] = {}
    for f in dados.get("fontes", []):
        fid = f.get("id")
        if not fid or fid in fontes:
            erros.append(f"fonte com id ausente ou repetido: {fid!r}")
            continue
        fontes[fid] = f
        if f.get("origem") not in ORIGENS:
            erros.append(f"fonte {fid}: origem inválida")
        if f.get("licenca") not in LICENCAS:
            erros.append(f"fonte {fid}: licença inválida")
        url = str(f.get("url", ""))
        if not url.startswith("https://"):
            erros.append(f"fonte {fid}: url deve ser https")
        host = url.split("/")[2] if url.count("/") >= 2 else ""
        if any(host == h or host.endswith("." + h) for h in HOSTS_VETADOS):
            erros.append(f"fonte {fid}: {host} tem licença que não permite uso comercial")
        if not isinstance(f.get("ano"), int) or f["ano"] > hoje.year:
            erros.append(f"fonte {fid}: ano inválido")

    codigos: set[str] = set()
    for r in dados.get("reguas", []):
        cod = r.get("codigo")
        if not cod or cod in codigos:
            erros.append(f"régua com código ausente ou repetido: {cod!r}")
            continue
        codigos.add(cod)
        refs = r.get("fontes", [])
        faltando = [x for x in refs if x not in fontes]
        if faltando:
            erros.append(f"{cod}: fontes inexistentes {faltando}")
        usadas = [fontes[x] for x in refs if x in fontes]
        nac = [f for f in usadas if f["origem"] == "nacional"]
        intl = [f for f in usadas if f["origem"] == "internacional"]
        classe, selo = r.get("classe"), r.get("fidedignidade")
        if classe not in CLASSES:
            erros.append(f"{cod}: classe inválida")
        if selo not in SELOS:
            erros.append(f"{cod}: fidedignidade inválida")
        if classe in ("VALIDADA", "VALIDADA_COM_RESSALVA") and not (nac and intl):
            erros.append(f"{cod}: {classe} exige ao menos uma fonte nacional e uma internacional")
        if selo == "alta":
            if classe != "VALIDADA" or len(nac) < 2 or len(intl) < 2:
                erros.append(f"{cod}: selo alta exige VALIDADA com 2 fontes nacionais e 2 internacionais")
            if any(f["ano"] < hoje.year - IDADE_MAXIMA_SELO_ALTO for f in usadas):
                erros.append(f"{cod}: selo alta com fonte de mais de {IDADE_MAXIMA_SELO_ALTO} anos")
        if classe == "NAO_VALIDADA" and (r.get("exibir_faixa") or selo is not None):
            erros.append(f"{cod}: NAO_VALIDADA não pode ter faixa nem selo")
        if r.get("exibir_faixa"):
            if not r.get("faixa"):
                erros.append(f"{cod}: exibir_faixa sem faixa")
            if r.get("condicao_para_exibir"):
                erros.append(f"{cod}: exibir_faixa com condição pendente")
            if classe == "NAO_VALIDADA":
                erros.append(f"{cod}: faixa exibida em régua NAO_VALIDADA")
        if not str(r.get("ressalva", "")).strip():
            erros.append(f"{cod}: ressalva obrigatória")
    return erros


def publico(dados: Optional[dict[str, Any]] = None, hoje: Optional[date] = None) -> dict[str, Any]:
    """Carga que a tela consome. Vencida = nenhuma faixa é exibida."""
    dados = dados or carregar()
    hoje = hoje or date.today()
    vence = _data(dados["valido_ate"])
    vencida = vence is None or hoje > vence
    fontes = {f["id"]: f for f in dados["fontes"]}
    reguas = []
    for r in dados["reguas"]:
        exibir = bool(r.get("exibir_faixa")) and not vencida
        reguas.append({
            **{k: r.get(k) for k in ("codigo", "nome", "unidade", "classe", "fidedignidade", "definicao_cowdata", "ressalva", "condicao_para_exibir")},
            "exibir_faixa": exibir,
            "faixa": r.get("faixa") if exibir else None,
            "fontes": [fontes[x] for x in r.get("fontes", []) if x in fontes],
        })
    return {
        "versao": dados["versao"],
        "revisado_em": dados["revisado_em"],
        "conferida_em": dados["conferida_em"],
        "valido_ate": dados["valido_ate"],
        "proxima_conferencia": dados["proxima_conferencia"],
        "vencida": vencida,
        "aviso": dados["aviso"],
        "fontes": dados["fontes"],
        "reguas": reguas,
    }
