"""
Alimentação — cruza o plano de dieta (por cabeça/dia) com o efetivo de cada lote
para estimar o consumo diário total de cada ingrediente.

Lote N (DIETA) ↔ grupo cujo código de 2 dígitos é N (ex.: lote 1 ↔ '01 - NOV. ALTA').
"""
from __future__ import annotations

import math
import re
from typing import Optional

DIAS_MES = 30

_RE_SACA_KG = re.compile(r"saca\D*(\d+(?:[.,]\d+)?)\s*kg", re.IGNORECASE)


def _kg_por_saca_de_unidade(unidade: Optional[str]) -> Optional[float]:
    """Extrai o peso da saca em kg direto da própria `unidade` do item de
    Estoque (ex.: "saca 30kg", "saca 60kg") — o campo que quem cadastra o
    produto realmente preenche. Serve de alternativa ao trio
    unidade_embalagem/medida_embalagem/quantidade_embalagem (usado quando o
    peso da saca precisa ser diferente do que a própria unidade já diz)."""
    if not unidade:
        return None
    m = _RE_SACA_KG.search(unidade)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def resolver_kg_por_unidade(estoque_item: Optional[dict]) -> Optional[float]:
    """Quantos kg equivalem a 1 unidade de estoque do item informado — None
    quando a unidade não é embalada (kg/L direto) ou quando não há como
    resolver. Mesma prioridade usada em `calcular_necessidade_mensal`: (1) o
    trio unidade_embalagem/medida_embalagem/quantidade_embalagem, sempre que
    `medida_embalagem` for "kg/&lt;o que for&gt;" — cobre saca, tonelada, bag,
    fardo etc. igual, em vez de reconhecer só o texto exato "Saca"/"kg/saca"
    (bug real: um item cadastrado em Tonelada, com medida_embalagem="kg/ton"
    e quantidade_embalagem=1000, caía direto no fallback de baixo e tinha o
    consumo diário em kg debitado 1:1 como se fosse Tonelada — erro de
    escala 1000x); (2) senão, peso extraído da própria `unidade` (ex.: "saca
    30kg", "saca 60kg"). Compartilhado com a baixa automática de estoque (ver
    `_dar_baixa_automatica` em routers/alimentacao.py) — sem isso, um item
    embalado tinha seu saldo debitado como se 1 unidade de estoque valesse 1
    kg."""
    if not estoque_item:
        return None
    medida = (estoque_item.get("medida_embalagem") or "").strip().lower()
    fator = estoque_item.get("quantidade_embalagem")
    if fator and medida.split("/", 1)[0].strip() == "kg":
        return fator
    return _kg_por_saca_de_unidade(estoque_item.get("unidade"))


def _codigo_grupo(grupo: Optional[str]) -> Optional[str]:
    if not grupo:
        return None
    g = grupo.strip()
    return g[:2] if len(g) >= 2 and g[:2].isdigit() else None


def _efetivo_por_lote(animais: list[dict]) -> dict[int, int]:
    """Conta animais ativos por código de lote (1..14)."""
    contagem: dict[int, int] = {}
    for a in animais:
        cod = _codigo_grupo(a.get("grupo_primario"))
        if cod:
            n = int(cod)
            contagem[n] = contagem.get(n, 0) + 1
    return contagem


def _remapear_lote_pela_categoria(dieta_lote: int, categoria: str | None, lotes_cadastro: list[dict]) -> int:
    """
    `Dieta.lote` vem congelado do DIETA.csv importado uma vez. Se o cadastro de
    lotes (Configurações > Cadastro > Lotes) foi renumerado/renomeado depois —
    ex.: qual nº de lote é "Secas" mudou —, o nº congelado fica desatualizado
    e o efetivo soma o grupo de animais errado. Para as categorias com
    identidade clara no cadastro (Secas via `status_lactacao`, Pré-parto via
    o flag `pre_parto`), re-associa ao lote ATUAL do cadastro; do contrário
    mantém o nº congelado.
    """
    cat = (categoria or "").strip().lower()
    atual = None
    if "seca" in cat:
        atual = next((l for l in lotes_cadastro if l.get("status_lactacao") == "seca"), None)
    elif "pré-parto" in cat or "pre-parto" in cat or "pre_parto" in cat or "preparto" in cat:
        atual = next((l for l in lotes_cadastro if l.get("pre_parto")), None)
    codigo = atual.get("codigo") if atual else None
    return int(codigo) if codigo and codigo.isdigit() else dieta_lote


def calcular_consumo(dietas: list[dict], animais: list[dict], lotes_cadastro: list[dict] | None = None) -> dict:
    """
    Retorna:
      - por_lote: plano de cada lote com efetivo e consumo do lote por ingrediente
      - consumo_total: soma por ingrediente (kg ou L/dia) no rebanho inteiro

    `lotes_cadastro` (dicts do cadastro de Lote — `codigo`, `nome`,
    `status_lactacao`, `pre_parto`) mantém o nº de lote e o nome exibido
    sincronizados com Configurações > Cadastro > Lotes, mesmo que o cadastro
    tenha sido renumerado/renomeado depois do DIETA.csv importado.
    """
    lotes_cadastro = lotes_cadastro or []
    nome_por_codigo = {l["codigo"]: l["nome"] for l in lotes_cadastro if l.get("codigo")}
    efetivo = _efetivo_por_lote(animais)

    # Agrupa dietas por lote
    lotes: dict[int, dict] = {}
    for d in dietas:
        lote_original = d.get("lote")
        if lote_original is None:
            continue
        lote = _remapear_lote_pela_categoria(lote_original, d.get("categoria"), lotes_cadastro)
        categoria_atual = nome_por_codigo.get(f"{lote:02d}", d.get("categoria"))
        info = lotes.setdefault(lote, {"lote": lote, "categoria": categoria_atual, "ingredientes": []})
        info["ingredientes"].append({
            "ingrediente": d.get("ingrediente"),
            "por_cabeca": d.get("quantidade"),
            "unidade": d.get("unidade"),
        })

    consumo_total: dict[str, dict] = {}
    por_lote = []
    for lote in sorted(lotes):
        info = lotes[lote]
        n = efetivo.get(lote, 0)
        itens = []
        for ing in info["ingredientes"]:
            por_cab = ing["por_cabeca"] or 0
            total = round(por_cab * n, 2)
            itens.append({**ing, "efetivo": n, "consumo_dia": total})
            chave = ing["ingrediente"]
            acc = consumo_total.setdefault(chave, {"ingrediente": chave, "unidade": ing["unidade"], "consumo_dia": 0.0})
            acc["consumo_dia"] = round(acc["consumo_dia"] + total, 2)
        por_lote.append({
            "lote": lote,
            "categoria": info["categoria"],
            "efetivo": n,
            "itens": itens,
        })

    return {
        "por_lote": por_lote,
        "consumo_total": sorted(consumo_total.values(), key=lambda x: -x["consumo_dia"]),
    }


def calcular_necessidade_mensal(
    consumo_total: list[dict],
    estoque_por_nome: dict[str, dict],
    estoque_por_alimento: dict[str, list[dict]] | None = None,
    alimentos_cadastrados: set[str] | None = None,
) -> list[dict]:
    """
    Projeta o consumo diário para uma janela de 30 dias. Quando o ingrediente
    tem um item de estoque vinculado embalado (qualquer embalagem cujo
    `medida_embalagem` seja "kg/<algo>" — saca, tonelada, bag, fardo...) com
    peso conhecido, converte kg em unidades de embalagem (arredondando para
    cima — não dá pra comprar meia unidade). O fator vem de duas fontes
    possíveis, nesta ordem, via `resolver_kg_por_unidade`: (1) o trio
    unidade_embalagem/medida_embalagem/quantidade_embalagem, quando alguém
    preencheu esse cadastro específico; (2) senão, extraído direto da
    própria `unidade` do item de Estoque (ex.: "saca 30kg", "saca 60kg") — o
    campo que normalmente já é preenchido ao cadastrar o produto, sem
    precisar duplicar a informação em outro lugar.

    O vínculo com o Estoque é resolvido em duas etapas: (1) nome idêntico ao
    de um item de Estoque (comportamento histórico, mantido para não quebrar
    quem já tem os nomes casando); (2) se não achar, casa o nome do
    ingrediente com o cadastro de `Alimento` (Configurações > Cadastro >
    Alimentação > Alimentos) e usa o(s) item(ns) de Estoque vinculados a ele
    (`Estoque.alimento_id`) — a via correta para ingredientes cujo nome no
    plano de dieta não é igual ao nome do produto no Estoque.
    """
    estoque_por_alimento = estoque_por_alimento or {}
    alimentos_cadastrados = alimentos_cadastrados or set()
    saida = []
    for item in consumo_total:
        kg_mes = round(item["consumo_dia"] * DIAS_MES, 2)
        nome_normalizado = (item["ingrediente"] or "").strip().lower()
        estoque_item = estoque_por_nome.get(item["ingrediente"])
        alimento_sem_vinculo = False
        if estoque_item is None:
            candidatos = estoque_por_alimento.get(nome_normalizado)
            if candidatos:
                estoque_item = candidatos[0]
            elif nome_normalizado in alimentos_cadastrados:
                alimento_sem_vinculo = True
        kg_por_saco = resolver_kg_por_unidade(estoque_item)
        ensacado = kg_por_saco is not None
        sacos = math.ceil(kg_mes / kg_por_saco) if ensacado else None
        saida.append({
            "ingrediente": item["ingrediente"],
            "unidade": item["unidade"],
            "consumo_dia": item["consumo_dia"],
            "necessidade_mes": kg_mes,
            "ensacado": ensacado,
            "kg_por_saco": kg_por_saco,
            "sacos_mes": sacos,
            "item_estoque_vinculado": estoque_item is not None,
            # Alimento já está cadastrado (Configurações > Cadastro > Alimentação
            # > Alimentos), mas ainda sem nenhum item de Estoque vinculado —
            # distinto de "nome desconhecido" (nem o Estoque nem o Alimento
            # reconhecem esse ingrediente).
            "alimento_sem_vinculo": alimento_sem_vinculo,
        })
    return saida
