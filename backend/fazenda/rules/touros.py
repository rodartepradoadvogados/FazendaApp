"""
Importação do catálogo genético de touros (provas do fornecedor / NAAB-CDCB).

Os catálogos exportados pelo ABS BullSearch, Alta, Select Sires, CRV etc. têm
nomes de coluna variados (inglês/português). Aqui mapeamos por APELIDOS: cada
campo do modelo Touro aceita vários nomes de coluna possíveis, casados sem
acento e em minúsculas. O que não casar é ignorado sem quebrar o import.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from fazenda.models import EstoqueSemen, SeedFlag, Touro
from fazenda.parsers.utils import parse_float
from fazenda.rules.naab import central_por_codigo_naab

logger = logging.getLogger(__name__)

SEED_TOUROS_NAAB_ALTA = "touros_naab_alta_2026_v1"


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# Cada campo → lista de apelidos de coluna (já normalizados na comparação).
APELIDOS: dict[str, list[str]] = {
    "naab": ["naab", "naab code", "codigo naab", "cod naab", "codigo", "code", "naab id"],
    "nome": ["nome", "name", "short name", "nome curto", "bull name", "touro", "nome do touro"],
    "raca": ["raca", "breed", "raca do touro"],
    "central": ["central", "stud", "company", "empresa", "marketing"],
    "leite_kg": ["leite", "milk", "ptam", "leite kg", "milk kg", "milk lbs", "leite lb"],
    "gordura_kg": ["gordura kg", "fat kg", "fat lbs", "gordura lb", "fat"],
    "gordura_pct": ["gordura", "gordura pct", "fat pct", "f", "gordura porcentagem"],
    "proteina_kg": ["proteina kg", "protein kg", "protein lbs", "proteina lb"],
    "proteina_pct": ["proteina", "proteina pct", "protein pct", "p", "proteina porcentagem"],
    "tpi": ["tpi", "gtpi"],
    "nm_dolar": ["nm", "nm dolar", "net merit", "merit", "liquido merito", "nm usd"],
    "tipo_composto": ["tipo", "ptat", "type", "conformacao", "tipo composto"],
    "ubere_composto": ["ubere", "udc", "udder", "composto ubere", "ubere composto"],
    "pernas_composto": ["pernas", "flc", "feet legs", "pes e pernas", "pernas e pes"],
    "ccs_score": ["ccs", "scs", "celulas somaticas", "somatic", "score ccs"],
    "fertilidade_filhas": ["dpr", "fertilidade", "fertility", "prenhez das filhas", "fertilidade filhas"],
    "facilidade_parto": ["facilidade de parto", "sce", "dce", "calving ease", "parto", "facilidade parto"],
}
CAMPOS_NUM = {
    "leite_kg", "gordura_kg", "gordura_pct", "proteina_kg", "proteina_pct", "tpi", "nm_dolar",
    "tipo_composto", "ubere_composto", "pernas_composto", "ccs_score", "fertilidade_filhas", "facilidade_parto",
}


def ler_planilha(content: bytes, filename: str | None) -> list[dict]:
    """Lê CSV (vírgula ou ';') ou XLSX e devolve linhas como dicts com o
    cabeçalho normalizado (sem acento, minúsculo)."""
    nome = (filename or "").lower()
    if nome.endswith((".xlsx", ".xlsm")):
        import openpyxl  # dependência declarada no requirements
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        linhas_iter = ws.iter_rows(values_only=True)
        try:
            cabecalho = [_norm(str(c)) if c is not None else "" for c in next(linhas_iter)]
        except StopIteration:
            return []
        out = []
        for row in linhas_iter:
            if row is None or all(c is None or str(c).strip() == "" for c in row):
                continue
            out.append({cabecalho[i]: ("" if v is None else str(v)) for i, v in enumerate(row) if i < len(cabecalho)})
        return out
    # CSV — detecta o separador pelo cabeçalho.
    import csv as _csv
    texto = content.decode("utf-8-sig", errors="replace")
    primeira = texto.splitlines()[0] if texto.strip() else ""
    delim = ";" if primeira.count(";") >= primeira.count(",") else ","
    return [
        {_norm(k): (v or "").strip() for k, v in r.items()}
        for r in _csv.DictReader(io.StringIO(texto), delimiter=delim)
    ]


def _mapear_colunas(cabecalhos: list[str]) -> dict[str, str]:
    """Para cada campo do Touro, encontra a coluna correspondente na planilha."""
    disponiveis = {c: c for c in cabecalhos if c}
    mapa: dict[str, str] = {}
    for campo, apelidos in APELIDOS.items():
        for ap in apelidos:
            if ap in disponiveis:
                mapa[campo] = ap
                break
    return mapa


# ---------------------------------------------------------------------------
# Importador de planilha "rica" (catálogo completo do fornecedor, dezenas de
# colunas de provas — ex.: exportação da Alta Genetics em PT-BR). O
# mapeamento por apelidos acima é frágil demais para esses arquivos (colunas
# como "Gordura" e "% Gordura", ou "Proteína" e "Prot%", normalizam para o
# mesmo apelido). Em vez de adivinhar, este importador lê a planilha inteira
# por posição de coluna: preenche os campos curados do modelo quando acha o
# cabeçalho esperado, e guarda TODAS as colunas (com o rótulo original) em
# `dados_extra`, para que nenhum dado da planilha se perca.
CURADOS_POR_CABECALHO: list[tuple[str, str, bool]] = [
    # (campo do modelo, cabeçalho esperado na planilha, é numérico?)
    ("naab", "Código NAAB", False),
    ("nome", "Nome", False),
    ("nome_completo", "Nome completo", False),
    ("raca", "Raça", False),
    ("tpi", "TPI", True),
    ("nm_dolar", "NM$", True),
    ("leite_kg", "Leite", True),
    ("proteina_kg", "Proteína", True),
    ("proteina_pct", "Prot%", True),
    ("gordura_kg", "Gordura", True),
    ("gordura_pct", "% Gordura", True),
    ("ccs_score", "SCS", True),
    ("tipo_composto", "PTAT", True),
]


def _indice_cabecalho(cabecalhos: list[str], alvo: str, usados: set[int]) -> int | None:
    """Primeiro índice cujo cabeçalho normalizado bate com o alvo, ignorando
    os já usados (protege contra cabeçalhos duplicados, ex.: "D / H")."""
    alvo_norm = _norm(alvo)
    for i, c in enumerate(cabecalhos):
        if i not in usados and _norm(c) == alvo_norm:
            return i
    return None


def eh_planilha_rica(cabecalhos: list[object]) -> bool:
    """Detecta o catálogo completo (dezenas de colunas de provas) vs. um CSV
    simples de poucas colunas — para escolher o importador certo."""
    if len(cabecalhos) < 30:
        return False
    primeiros = [_norm(str(c)) if c is not None else "" for c in cabecalhos[:3]]
    return any("naab" in c for c in primeiros)


def importar_touros_planilha_rica(session: Session, content: bytes, fonte: str | None, rodada: str | None) -> dict:
    """Importa o catálogo completo (ex.: exportação Alta Genetics) preservando
    TODAS as colunas por touro em `dados_extra`, além de preencher os campos
    curados (TPI, NM$, Leite, Gordura, Proteína, SCS, PTAT...) usados em
    outras telas do sistema. Upsert por código NAAB; nunca apaga touros
    existentes."""
    from datetime import datetime
    import json

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    linhas_iter = ws.iter_rows(values_only=True)
    try:
        cabecalhos_raw = list(next(linhas_iter))
    except StopIteration:
        return {"criados": 0, "atualizados": 0, "erros": ["Planilha vazia ou ilegível."]}
    cabecalhos = [str(c) if c is not None else "" for c in cabecalhos_raw]

    usados: set[int] = set()
    indices: dict[str, int] = {}
    for campo, cabecalho, _num in CURADOS_POR_CABECALHO:
        idx = _indice_cabecalho(cabecalhos, cabecalho, usados)
        if idx is not None:
            indices[campo] = idx
            usados.add(idx)
    if "naab" not in indices:
        return {"criados": 0, "atualizados": 0, "erros": [
            "Não encontrei a coluna 'Código NAAB'. Confirme que é o catálogo completo do fornecedor."
        ]}

    linhas = list(linhas_iter)
    logger.info("Importando catálogo de touros NAAB (planilha rica): %d linhas, fonte=%s", len(linhas), fonte)

    # Carrega todos os touros existentes de uma vez (uma única query) em vez de
    # um SELECT por linha — com autoflush=True, um SELECT por linha dentro do
    # loop força um flush de todos os objetos ainda não commitados a cada
    # iteração, virando milhares de round-trips ao banco (rápido em SQLite
    # local, mas caro o suficiente em Postgres de produção para estourar o
    # healthcheck do deploy).
    existentes: dict[str, Touro] = {t.naab: t for t in session.exec(select(Touro)).all()}

    criados = atualizados = 0
    erros: list[str] = []
    for linha in linhas:
        if linha is None or all(c is None or str(c).strip() == "" for c in linha):
            continue
        valores = list(linha) + [None] * (len(cabecalhos) - len(linha))
        naab = str(valores[indices["naab"]] or "").strip().upper()
        if not naab:
            continue
        touro = existentes.get(naab)
        novo = touro is None
        if novo:
            touro = Touro(naab=naab)
            existentes[naab] = touro  # protege contra NAAB duplicado na mesma planilha
        for campo, _cabecalho, num in CURADOS_POR_CABECALHO:
            if campo == "naab" or campo not in indices:
                continue
            v = valores[indices[campo]]
            if v is None or str(v).strip() == "":
                continue
            if num:
                # Valores da planilha já vêm como number nativo do openpyxl
                # (ponto decimal) — parse_float espera string BR (vírgula
                # decimal) e erraria a casa decimal se aplicado aqui.
                vf = float(v) if isinstance(v, (int, float)) else parse_float(str(v))
                if vf is not None:
                    setattr(touro, campo, vf)
            else:
                setattr(touro, campo, str(v).strip())
        # Todos os dados da planilha, na ordem original — nada se perde mesmo
        # para colunas sem campo curado equivalente.
        touro.dados_extra = json.dumps(
            [[cabecalhos[i], valores[i]] for i in range(len(cabecalhos)) if valores[i] is not None and str(valores[i]).strip() != ""],
            ensure_ascii=False,
        )
        if not touro.central:
            touro.central = central_por_codigo_naab(naab)
        if fonte:
            touro.fonte = fonte
        if rodada:
            touro.rodada_prova = rodada
        touro.atualizado_em = datetime.utcnow()
        session.add(touro)
        criados += 1 if novo else 0
        atualizados += 0 if novo else 1
    session.commit()
    logger.info("Catálogo de touros importado: %d criados, %d atualizados", criados, atualizados)
    return {"criados": criados, "atualizados": atualizados, "erros": erros}


def importar_touros(session: Session, linhas: list[dict], fonte: str | None, rodada: str | None) -> dict:
    """Upsert dos touros por código NAAB. Atualiza só os campos presentes na
    planilha; nunca apaga touros que já existem. Retorna resumo."""
    from datetime import datetime

    if not linhas:
        return {"criados": 0, "atualizados": 0, "erros": ["Planilha vazia ou ilegível."]}
    mapa = _mapear_colunas(list(linhas[0].keys()))
    if "naab" not in mapa:
        return {"criados": 0, "atualizados": 0, "erros": [
            "Não encontrei a coluna do código NAAB. Renomeie a coluna do código para 'NAAB' e tente de novo."
        ]}

    logger.info("Importando catálogo de touros (CSV/planilha simples): %d linhas, fonte=%s", len(linhas), fonte)

    # Mesmo motivo do importador de planilha rica: uma única query para
    # carregar todos os touros existentes evita um SELECT (+ flush) por linha.
    existentes: dict[str, Touro] = {t.naab: t for t in session.exec(select(Touro)).all()}

    criados = atualizados = 0
    erros: list[str] = []
    for i, row in enumerate(linhas, start=2):
        naab = (row.get(mapa["naab"]) or "").strip().upper()
        if not naab:
            continue
        touro = existentes.get(naab)
        novo = touro is None
        if novo:
            touro = Touro(naab=naab)
            existentes[naab] = touro  # protege contra NAAB duplicado na mesma planilha
        for campo, coluna in mapa.items():
            if campo == "naab":
                continue
            valor = (row.get(coluna) or "").strip()
            if valor == "":
                continue
            if campo in CAMPOS_NUM:
                v = parse_float(valor)
                if v is not None:
                    setattr(touro, campo, v)
            else:
                setattr(touro, campo, valor)
        # Central: usa a da planilha; se faltar, deriva do código NAAB.
        if not touro.central:
            touro.central = central_por_codigo_naab(naab)
        if fonte:
            touro.fonte = fonte
        if rodada:
            touro.rodada_prova = rodada
        touro.atualizado_em = datetime.utcnow()
        session.add(touro)
        criados += 1 if novo else 0
        atualizados += 0 if novo else 1
    session.commit()
    logger.info("Catálogo de touros importado: %d criados, %d atualizados", criados, atualizados)
    return {"criados": criados, "atualizados": atualizados, "erros": erros}


def bootstrap_touros_naab(session: Session, forcar: bool = False) -> None:
    """Carrega o catálogo NAAB completo (Alta Genetics) empacotado no
    repositório, uma única vez (idempotente via SeedFlag) — assim o banco de
    touros já vem pronto sem depender de o usuário fazer o upload manual.
    `forcar=True` reimporta mesmo com a flag já marcada (upsert por NAAB,
    nunca apaga touros existentes) — usado pelo botão de autoatendimento."""
    if not forcar and session.get(SeedFlag, SEED_TOUROS_NAAB_ALTA):
        # A flag só marca que o import já rodou uma vez — se a tabela estiver
        # vazia mesmo assim (ex.: perda de dados independente da flag), o
        # catálogo nunca voltaria sozinho; confere o dado real antes de confiar
        # na flag (upsert por NAAB é seguro, nunca apaga touros existentes).
        if session.exec(select(Touro)).first() is not None:
            return
    caminho = Path(__file__).resolve().parent.parent / "seed_data" / "touros_naab_alta.xlsx"
    if not caminho.exists():
        logger.error(
            "Bootstrap do catálogo de touros NAAB abortado: arquivo não encontrado em %s. "
            "O catálogo genético não será carregado automaticamente.",
            caminho,
        )
        return
    content = caminho.read_bytes()
    importar_touros_planilha_rica(session, content, "Alta Genetics", None)
    if not session.get(SeedFlag, SEED_TOUROS_NAAB_ALTA):
        session.add(SeedFlag(chave=SEED_TOUROS_NAAB_ALTA))
    session.commit()


# ---------------------------------------------------------------------------
# Prova média — média ponderada dos indicadores de prova genética (PTAs,
# índices econômicos e de tipo) de um conjunto de touros, ponderada por
# quantidade (doses em estoque, ou doses usadas em serviços/IA). Mesma lógica
# de "soma(indicador × peso) / soma(peso)" já usada em outros indicadores do
# sistema (ex.: PR média ponderada em rules/recria.py) — é também como o
# próprio setor de melting genético pondera índices compostos (ex.: o PTI
# combina produção e tipo numa razão fixa 2:1/1:2); aqui a ponderação é pela
# quantidade de sêmen, não por um peso fixo entre índices.
def calcular_prova_media(pares: list[tuple["Touro", int]]) -> dict[str, float | None]:
    """Recebe pares (touro, peso) — ex.: (touro, doses_em_estoque) — e devolve
    a média ponderada de cada campo numérico de prova (CAMPOS_NUM). Toca só
    nos touros que têm aquele campo preenchido (não zera a média por causa de
    um touro sem dado); se nenhum touro do grupo tiver o campo, o resultado é
    None. Peso <= 0 é ignorado."""
    resultado: dict[str, float | None] = {}
    for campo in CAMPOS_NUM:
        soma_ponderada = 0.0
        soma_pesos = 0.0
        for touro, peso in pares:
            if peso is None or peso <= 0:
                continue
            valor = getattr(touro, campo, None)
            if valor is None:
                continue
            soma_ponderada += valor * peso
            soma_pesos += peso
        resultado[campo] = round(soma_ponderada / soma_pesos, 2) if soma_pesos else None
    return resultado


def casar_touro(estoque_item: "EstoqueSemen", touro_por_naab: dict, touro_por_nome: dict) -> Optional[Touro]:
    """Casa um item do estoque de sêmen com o catálogo genético: por NAAB/código
    do estoque primeiro, senão pelo nome do touro. Usado tanto pela prova
    média (peso = doses em estoque) quanto pela prova ao vivo (peso = uso
    real, ver `calcular_prova_ao_vivo`)."""
    naab = (estoque_item.naab or estoque_item.codigo or "").strip().upper()
    if naab and naab in touro_por_naab:
        return touro_por_naab[naab]
    nome = (estoque_item.touro_nome or "").strip().lower()
    return touro_por_nome.get(nome)


def _touro_por_nome(
    nome: str, touro_por_naab: dict, touro_por_nome: dict, estoque_por_nome: dict[str, "EstoqueSemen"],
) -> Optional[Touro]:
    """Casa um NOME de touro/reprodutor (ex.: `Servico.reprodutor`, que não
    tem NAAB próprio) com o catálogo genético — via o estoque de sêmen
    cadastrado com esse nome (que pode ter NAAB) ou, na falta, pelo nome
    direto no catálogo."""
    chave = (nome or "").strip().lower()
    item = estoque_por_nome.get(chave)
    if item:
        touro = casar_touro(item, touro_por_naab, touro_por_nome)
        if touro:
            return touro
    return touro_por_nome.get(chave)


def eh_touro_fazenda(tipo_semen: str | None, nome: str | None, estoque_por_nome: dict[str, "EstoqueSemen"]) -> bool:
    """Um touro é "da fazenda" (monta natural, sêmen produzido/usado dentro de
    casa — não comprado de central de genética) quando `tipo_semen` (gravado
    no próprio serviço) ou, na falta dele, o `tipo` cadastrado no estoque de
    sêmen com esse nome, é "fazenda". Registros antigos sem nenhuma das duas
    informações são tratados como NÃO sendo da fazenda (não há como provar
    que são)."""
    if tipo_semen:
        return tipo_semen == "fazenda"
    item = estoque_por_nome.get((nome or "").strip().lower())
    return bool(item and item.tipo == "fazenda")


# ---------------------------------------------------------------------------
# Prova ao vivo — mesmos indicadores GENÉTICOS de `calcular_prova_media`
# acima (leite, gordura, proteína, TPI, NM$, tipo/úbere/pernas composto, CCS,
# fertilidade das filhas, facilidade de parto), mas ponderados pelo USO REAL
# do touro na fazenda (nº de serviços em que ele foi de fato usado), não
# pelas doses hoje em estoque. É essa ponderação por uso real — e não a
# métrica calculada — que faz esta prova ser "ao vivo": o mesmo índice
# genético do catálogo, só que pesado pelo que a fazenda realmente usou.
#
# ANTES este endpoint calculava algo bem diferente: taxa de concepção
# REALIZADA (positivos ÷ serviços com resultado conhecido) por touro — um
# indicador de RESULTADO REPRODUTIVO do rebanho, não de prova genética do
# touro. Ver fazenda.rules.reproducao_analise para essa métrica (ainda usada
# nos dashboards de Análise reprodutiva) — aqui ela foi substituída porque
# não é o que "prova de touro" significa: a prova é do touro (índice
# genético), o resultado reprodutivo é do cruzamento inteiro (touro + matriz
# + manejo), coisas diferentes.
# ---------------------------------------------------------------------------
def calcular_prova_ao_vivo(
    registros: list[dict],
    touro_por_naab: dict[str, Touro],
    touro_por_nome: dict[str, Touro],
    estoque_por_nome: dict[str, "EstoqueSemen"],
    *,
    categoria: str | None = None,
    ano_nascimento: int | None = None,
    periodo_de: date | None = None,
    periodo_ate: date | None = None,
    incluir_fazenda: bool = False,
) -> dict:
    """Recebe os registros achatados de `analisar_servicos` e devolve a prova
    ao vivo: os indicadores genéticos do catálogo, ponderados pelo nº de
    serviços de cada touro (que passam os filtros opcionais — categoria,
    ano de nascimento da matriz, período da inseminação — mesmos filtros da
    tela, só limitam o resultado). Por padrão EXCLUI touros da própria
    fazenda (`incluir_fazenda=False`): sêmen produzido/usado internamente
    não tem prova de central de genética para ponderar; ligue a flag para
    incluir mesmo assim (só conta se esse touro também estiver no catálogo
    NAAB). Touro sem casamento no catálogo (nenhuma prova genética
    encontrada) não entra no cálculo — não tem indicador nenhum para
    ponderar."""
    usos: dict[str, int] = defaultdict(int)
    for r in registros:
        nome = r.get("touro")
        if not nome or nome == "(sem touro)":
            continue
        if categoria and categoria != "todas" and (r.get("categoria") or "").strip().lower() != categoria.strip().lower():
            continue
        if ano_nascimento and r.get("ano_nascimento") != ano_nascimento:
            continue
        d = r.get("data_servico")
        if periodo_de and (d is None or d < periodo_de):
            continue
        if periodo_ate and (d is None or d > periodo_ate):
            continue
        if not incluir_fazenda and eh_touro_fazenda(r.get("tipo_semen"), nome, estoque_por_nome):
            continue
        usos[nome] += 1

    pares: list[tuple[Touro, int]] = []
    touros_saida: list[dict] = []
    for nome, qtd in usos.items():
        touro = _touro_por_nome(nome, touro_por_naab, touro_por_nome, estoque_por_nome)
        if not touro:
            continue
        pares.append((touro, qtd))
        touros_saida.append({"touro": nome, "servicos": qtd})
    touros_saida.sort(key=lambda t: -t["servicos"])

    return {
        "prova": calcular_prova_media(pares),
        "total_servicos": sum(qtd for _, qtd in pares),
        "touros_considerados": len(pares),
        "touros": touros_saida,
    }
