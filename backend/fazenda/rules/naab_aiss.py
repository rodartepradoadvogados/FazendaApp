"""
Catálogo AISS da NAAB — arquivo bulk oficial com o catálogo genético COMPLETO
de touros de IA ativamente comercializados nos EUA ("Complete List of All
Active (A), Foreign (F) and Genomic (G) AI Bulls"), publicado em
https://www.naab-css.org/database-files.

Contexto (Fase 1 do catálogo NAAB — ver docs/agents/naab-catalogo-firecrawl.md,
seção 4): uma investigação anterior confirmou, contra as páginas oficiais ao
vivo, que esse ZIP é lido por HTTP comum (`httpx`, sem Firecrawl e sem bloqueio
de bot) e que dentro dele há um único arquivo `.txt` que, apesar do nome, é um
CSV comum (vírgula, texto entre aspas, número sem aspas). A ordem dos 143
primeiros campos de cada linha (`CAMPOS_AISS` abaixo) foi validada contra a
documentação oficial da NAAB e contra duas linhas reais do arquivo, cruzadas
com as páginas públicas de dois touros (TIMETRAVELER/200HO13678 e
SABOTAGE/796HO10329) — ver `backend/tests/test_naab_aiss.py`, que usa essas
duas linhas como fixture.

Este módulo:
  - baixa e faz o parsing do catálogo (`baixar_catalogo_aiss`,
    `ler_catalogo_aiss`, `mapear_para_touro`);
  - compara o catálogo contra o banco (`comparar_catalogo`) — LEITURA PURA,
    nunca grava nada;
  - guarda a decisão "mantido por decisão do dono" de um touro que saiu do
    catálogo (`marcar_mantido`) — a ÚNICA escrita daqui, e só quando o dono
    pede no chat.

A gravação de verdade do catálogo (upsert por NAAB dos touros que o dono
confirmou) mora em `fazenda.rules.touros.aplicar_atualizacoes_confirmadas`,
que reaproveita o núcleo de upsert de `importar_touros` — nada aqui chama
`session.commit()` de dados de touro, exceto `marcar_mantido`.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urljoin

import httpx
from sqlmodel import Session, select

from fazenda.models import Touro
from fazenda.rules.naab import central_por_codigo_naab

logger = logging.getLogger(__name__)

URL_DATABASE_FILES = "https://www.naab-css.org/database-files"
# Texto do link, na página de arquivos, para o ZIP do catálogo completo —
# comparação por substring (case-insensitive), não por igualdade exata,
# porque o texto real pode ter espaços/quebras de linha em volta.
TEXTO_LINK_CATALOGO = "Complete List of All Active"

# Marca gravada em `Touro.observacao` por `marcar_mantido` — usada por
# `comparar_catalogo` para NÃO repetir, toda semana, um touro que "saiu" do
# catálogo AISS mas que o dono já decidiu manter cadastrado.
MARCA_MANTIDO = "[NAAB] mantido por decisão do dono"

LB_PARA_KG = 0.453592

# Tolerância de comparação (arredondamento) — diferenças menores que isso não
# contam como "touro alterado".
TOLERANCIA_COMPARACAO = 0.01

# Ordem EXATA dos 143 primeiros campos de cada linha do arquivo AISS da NAAB
# (o 144º campo, sempre vazio/sem documentação oficial, é ignorado). NÃO
# reordenar sem revalidar contra a documentação oficial e linhas reais — ver
# o cabeçalho deste arquivo.
CAMPOS_AISS: list[str] = [
    'Breed', 'Country', 'ID Number', 'Current Controller Number', 'Primary Stud Code',
    'Primary Breed Code', 'Primary NAAB Bull Number', 'Full NAAB Code', 'Name',
    'Registry Status', 'RHA Indicator', '% US Daughters', 'Number of Herds in Milk PTA',
    'Number of Daughters in Milk PTA', 'Sampling Code', 'Sampler Controller Number',
    'Yield Reliability', 'Production Proof Origin', 'PTA Milk', 'PTA Fat Pounds',
    'PTA Fat %', 'PTA Protein Pounds', 'PTA Protein %', 'Fluid Merit Dollars (FM$)',
    'Cheese Merit Dollars (CM$)', 'Grazing Merit Dollars (GM$)', 'PTA Somatic Cell Score',
    'SCS Reliability', 'PTA Productive Life', 'PL Reliability',
    'PTA Daughter Pregnancy Rate', 'DPR Reliability', 'SCR', 'SCR Reliability',
    'SCR Breedings', 'HCR', 'HCR Reliability', 'HCR Daughters', 'CCR', 'CCR Reliability',
    'CCR Daughters', 'LIV', 'LIV Reliability', 'LIV Daughters', 'Net Merit',
    'Net Merit Reliability', 'Percentile Ranking for Net Merit',
    'SCE Expected % Difficult Births', 'SCE Reliability', 'SCE Observed Calvings',
    'DCE Expected % Difficult Births', 'DCE Reliability', 'DCE Number of daughters',
    'SSB Expected % stillborn calves', 'SSB Reliability',
    'SSB Number of observed calvings', 'DSB Expected % stillborn calves',
    'DSB Reliability', 'DSB Number of daughters', 'Type Proof Origin', 'PTA Type',
    'Reliability for PTAT', 'TPI or PTI', 'Udder Composite/Udder Index',
    'Feet & Legs Composite', 'PTA or STA Stature', 'PTA or STA Strength',
    'PTA or STA Body Depth', 'PTA or STA Dairy Form', 'PTA or STA Rump Angle',
    'PTA or STA Thurl Width', 'PTA or STA Rear Legs, Side View',
    'PTA or STA Rear Legs, Rear View', 'PTA or STA Foot Angle',
    'PTA or STA Foot & Leg Score', 'PTA or STA Fore Udder Attachment',
    'PTA or STA Rear Udder Height', 'PTA or STA Rear Udder Width',
    'PTA or STA Udder Cleft', 'PTA or STA Udder Depth',
    'PTA or STA Front Teat Placement', 'PTA or STA Rear Teat Placement',
    'PTA or STA Teat Length', 'PTA of Mobility', 'Reliability of Mobility',
    'Number of Daughters used Mobility', 'aAa Rating', 'DMS Scores', 'Semen Price',
    'Date of Birth (YYYYMMDD)', 'Short Name', 'Sire Country/ID Number',
    'Maternal Grand Sire Country/ID Number', 'Recessives', 'Status', 'Gestation Length',
    'GL reliability', 'GL number of daughters', 'Milk Fever', 'MF reliability',
    'MF number of daughters', 'Displaced Abomasum', 'DA reliability',
    'DA number of daughters', 'Ketosis', 'Ketosis reliability',
    'Ketosis number of daughters', 'Mastitis', 'Mastitis reliability',
    'Mastitis number of daughters', 'Metritis', 'Metritis reliability',
    'Metritis number of daughters', 'Retained Placenta', 'RP reliability',
    'RP number of daughters', 'Early First Calving', 'EFC reliability',
    'EFC number of daughters', 'Heifer livability', 'HL reliability',
    'HL number of daughters', 'Feed Saved', 'FS reliability', 'FS number of daughters',
    'Beta Casein', 'Kappa Casein', 'Beta Lactoglobulin', 'PTA Milking Speed',
    'Reliability of PTA Milking Speed', 'Number of daughters (Milking Speed)',
    'Body Composite', 'Expected Future Inbreeding',
    'Genomic Future Inbreeding Coefficient',
    'Rear Teat Placement Side View (Jersey)', 'Rear Teat Placement Rear View (Jersey)',
    'PTA Resistance to Diarrhea', 'Reliabilty of Resistance to Diarrhea',
    'PTA Resistance to Respiratory disease',
    'Reliabilty Resistance to Respiratory disease', 'PTA First Service to Conception',
    'Reliabilty of First Service to Conception', 'Holstein Conformation Composite',
]

# Campos curados do modelo Touro que entram na comparação semanal — os
# mesmos indicadores que `fazenda.rules.touros.CAMPOS_NUM` já trata como
# "prova curada" (mantidos como lista literal aqui, e não importados de
# touros.py, para não criar import circular: touros.py importa deste módulo).
CAMPOS_CURADOS_COMPARACAO: tuple[str, ...] = (
    "leite_kg", "gordura_kg", "gordura_pct", "proteina_kg", "proteina_pct",
    "tpi", "nm_dolar", "tipo_composto", "ubere_composto", "pernas_composto",
    "ccs_score", "fertilidade_filhas", "facilidade_parto",
)

_MESES_EN_PARA_PT = {
    "jan": "Jan", "feb": "Fev", "mar": "Mar", "apr": "Abr", "may": "Mai", "jun": "Jun",
    "jul": "Jul", "aug": "Ago", "sep": "Set", "oct": "Out", "nov": "Nov", "dec": "Dez",
}

_RE_LINK_HTML = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_RE_NOME_ARQUIVO_RODADA = re.compile(r"^([A-Za-z]{3})(\d{1,2})(\d{4})")


# ---------------------------------------------------------------------------
# Download + parsing
# ---------------------------------------------------------------------------
def _achar_link_catalogo(html: str) -> str | None:
    """Acha o `href` do primeiro `<a>` cujo texto (sem as tags internas)
    contém `TEXTO_LINK_CATALOGO` — sem depender de um parser HTML completo,
    porque o layout da página de arquivos da NAAB é simples (uma lista de
    links)."""
    for href, texto_link in _RE_LINK_HTML.findall(html or ""):
        texto_limpo = re.sub(r"<[^>]+>", " ", texto_link)
        texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()
        if TEXTO_LINK_CATALOGO.lower() in texto_limpo.lower():
            return href
    return None


def baixar_catalogo_aiss(timeout: float = 90) -> tuple[str, str]:
    """Baixa a página oficial de arquivos da NAAB, acha o ZIP do catálogo
    AISS completo ("Complete List of All Active (A), Foreign (F) and Genomic
    (G) AI Bulls"), baixa e extrai o único `.txt` de dentro dele — tudo em
    memória, nada gravado em disco. Devolve `(texto_do_arquivo, nome_do_arquivo)`.

    Fail-closed: qualquer problema de rede, de layout de página ou de
    formato de arquivo levanta `RuntimeError` com mensagem clara (sem stack
    trace exposta). Não há segredo nenhum envolvido — é página e arquivo
    públicos, sem chave de API."""
    try:
        resp_pagina = httpx.get(URL_DATABASE_FILES, timeout=timeout, follow_redirects=True)
        resp_pagina.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Falha ao baixar a página de arquivos da NAAB ({URL_DATABASE_FILES}): {e}") from e

    href = _achar_link_catalogo(resp_pagina.text)
    if not href:
        raise RuntimeError(
            f'Não encontrei, na página {URL_DATABASE_FILES}, nenhum link cujo texto contenha '
            f'"{TEXTO_LINK_CATALOGO}" — a NAAB pode ter mudado o layout da página de arquivos.'
        )
    url_zip = urljoin(URL_DATABASE_FILES, href)

    try:
        resp_zip = httpx.get(url_zip, timeout=timeout, follow_redirects=True)
        resp_zip.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Falha ao baixar o catálogo AISS ({url_zip}): {e}") from e

    try:
        with zipfile.ZipFile(io.BytesIO(resp_zip.content)) as zf:
            nomes_txt = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if not nomes_txt:
                raise RuntimeError(f"O ZIP baixado de {url_zip} não contém nenhum arquivo .txt.")
            nome = nomes_txt[0]
            conteudo_bytes = zf.read(nome)
    except zipfile.BadZipFile as e:
        raise RuntimeError(f"O arquivo baixado de {url_zip} não é um ZIP válido: {e}") from e

    try:
        texto = conteudo_bytes.decode("latin-1")
    except UnicodeDecodeError as e:
        raise RuntimeError(f"Não consegui decodificar {nome} (esperava latin-1): {e}") from e

    return texto, nome


def parse_valor_americano(texto: str | None) -> float | None:
    """Converte um campo numérico no formato americano do arquivo AISS:
    espaços de preenchimento (`"  589"`), sinal `+`/`-` explícito, decimal
    sem zero à esquerda (`"+.46"` → 0.46, `"-.07"` → -0.07) e string vazia
    (campo ausente) → `None` — NUNCA 0.0. Não usar `fazenda.parsers.utils.
    parse_float` aqui: aquele é para CSV brasileiro (vírgula decimal), este
    formato é ponto decimal."""
    if texto is None:
        return None
    t = texto.strip()
    if t == "":
        return None
    sinal = ""
    if t[0] in "+-":
        sinal = "-" if t[0] == "-" else ""
        t = t[1:].strip()
    if t.startswith("."):
        t = "0" + t
    if t == "":
        return None
    try:
        return float(f"{sinal}{t}")
    except ValueError:
        return None


def ler_catalogo_aiss(texto: str) -> list[dict]:
    """Lê o texto do arquivo AISS (na verdade um CSV comum, ver cabeçalho do
    módulo) linha a linha com `csv.reader` e devolve uma lista de dicts
    `{nome_do_campo: valor_str_bruto}` usando `CAMPOS_AISS` como chaves (via
    `zip`). Linha em branco é pulada silenciosamente; linha com menos campos
    que `CAMPOS_AISS` (malformada) é registrada em log e pulada — sem
    derrubar o processamento das demais."""
    linhas: list[dict] = []
    n_esperado = len(CAMPOS_AISS)
    leitor = csv.reader(io.StringIO(texto))
    for i, row in enumerate(leitor, start=1):
        if not row or all((c or "").strip() == "" for c in row):
            continue
        if len(row) < n_esperado:
            logger.warning(
                "Linha %d do catálogo AISS da NAAB ignorada: %d campo(s), esperava pelo menos %d.",
                i, len(row), n_esperado,
            )
            continue
        linhas.append(dict(zip(CAMPOS_AISS, row)))
    return linhas


def mapear_para_touro(linha: dict) -> dict:
    """Converte uma linha crua do catálogo AISS (chaves = `CAMPOS_AISS`,
    valores = string bruta) para os nomes de campo do modelo `Touro`, já
    convertendo libra → kg (1 lb = 0,453592 kg, arredondado a 2 casas) para
    `leite_kg`/`gordura_kg`/`proteina_kg`. Campo ausente na linha de origem
    (vazio após `parse_valor_americano`) NÃO entra no dict de saída — mesmo
    espírito de "só grava o que está presente" de `touros.importar_touros`."""

    def _texto(chave: str) -> str:
        return (linha.get(chave) or "").strip()

    def _num(chave: str) -> float | None:
        return parse_valor_americano(linha.get(chave))

    saida: dict = {}

    naab = _texto("Full NAAB Code").upper()
    if naab:
        saida["naab"] = naab
    nome = _texto("Short Name")
    if nome:
        saida["nome"] = nome
    nome_completo = _texto("Name")
    if nome_completo:
        saida["nome_completo"] = nome_completo
    raca = _texto("Breed")
    if raca:
        saida["raca"] = raca

    leite_lb = _num("PTA Milk")
    if leite_lb is not None:
        saida["leite_kg"] = round(leite_lb * LB_PARA_KG, 2)
    gordura_lb = _num("PTA Fat Pounds")
    if gordura_lb is not None:
        saida["gordura_kg"] = round(gordura_lb * LB_PARA_KG, 2)
    gordura_pct = _num("PTA Fat %")
    if gordura_pct is not None:
        saida["gordura_pct"] = gordura_pct
    proteina_lb = _num("PTA Protein Pounds")
    if proteina_lb is not None:
        saida["proteina_kg"] = round(proteina_lb * LB_PARA_KG, 2)
    proteina_pct = _num("PTA Protein %")
    if proteina_pct is not None:
        saida["proteina_pct"] = proteina_pct
    tpi = _num("TPI or PTI")
    if tpi is not None:
        saida["tpi"] = tpi
    nm_dolar = _num("Net Merit")
    if nm_dolar is not None:
        saida["nm_dolar"] = nm_dolar
    tipo_composto = _num("PTA Type")
    if tipo_composto is not None:
        saida["tipo_composto"] = tipo_composto
    ubere_composto = _num("Udder Composite/Udder Index")
    if ubere_composto is not None:
        saida["ubere_composto"] = ubere_composto
    pernas_composto = _num("Feet & Legs Composite")
    if pernas_composto is not None:
        saida["pernas_composto"] = pernas_composto
    ccs_score = _num("PTA Somatic Cell Score")
    if ccs_score is not None:
        saida["ccs_score"] = ccs_score
    fertilidade_filhas = _num("PTA Daughter Pregnancy Rate")
    if fertilidade_filhas is not None:
        saida["fertilidade_filhas"] = fertilidade_filhas
    facilidade_parto = _num("SCE Expected % Difficult Births")
    if facilidade_parto is not None:
        saida["facilidade_parto"] = facilidade_parto

    if naab:
        central = central_por_codigo_naab(naab)
        if central:
            saida["central"] = central

    return saida


def _extrair_rodada(nome_arquivo: str | None) -> str:
    """Tenta extrair `"Mmm/AAAA"` de um nome de arquivo como
    `"Aug122026-CompleteAISS.txt"` (mês em inglês de 3 letras + dia + ano).
    Se não conseguir reconhecer o padrão, devolve o próprio nome do arquivo —
    quem chama decide o que fazer com um nome bruto (ver docstring de
    `comparar_catalogo`)."""
    nome = nome_arquivo or ""
    m = _RE_NOME_ARQUIVO_RODADA.match(nome)
    if not m:
        return nome
    mes_en, _dia, ano = m.group(1), m.group(2), m.group(3)
    mes_pt = _MESES_EN_PARA_PT.get(mes_en.lower())
    if not mes_pt:
        return nome
    return f"{mes_pt}/{ano}"


# ---------------------------------------------------------------------------
# Comparação semanal (SÓ LEITURA — nunca grava no banco)
# ---------------------------------------------------------------------------
@dataclass
class RelatorioNaab:
    """Resultado de `comparar_catalogo` — puramente informativo, para o
    relatório mandado ao dono no chat. Nada aqui já foi gravado no banco."""

    rodada: str
    total_comparados: int
    alterados: list[dict] = field(default_factory=list)
    saidos: list[dict] = field(default_factory=list)
    novos: list[dict] = field(default_factory=list)


def _comparar_campos_curados(touro: Touro, mapa: dict) -> dict:
    """Compara os campos curados de UM touro do banco contra a linha
    mapeada do AISS, com tolerância de arredondamento
    (`TOLERANCIA_COMPARACAO`). Devolve só os campos que de fato mudaram, no
    formato `{"campo": {"antes": x, "depois": y}}`."""
    mudancas: dict = {}
    for campo in CAMPOS_CURADOS_COMPARACAO:
        if campo not in mapa:
            continue
        novo = mapa[campo]
        antigo = getattr(touro, campo, None)
        if antigo is None:
            mudancas[campo] = {"antes": antigo, "depois": novo}
            continue
        if abs(float(antigo) - float(novo)) > TOLERANCIA_COMPARACAO:
            mudancas[campo] = {"antes": antigo, "depois": novo}
    return mudancas


def comparar_catalogo(session: Session, linhas_aiss: list[dict], nome_arquivo: str | None = None) -> RelatorioNaab:
    """Compara o catálogo AISS baixado contra os touros já cadastrados no
    banco — LEITURA PURA, nunca chama `session.add`/`session.commit`.

    - `linhas_aiss`: as linhas cruas devolvidas por `ler_catalogo_aiss`
      (chaves = `CAMPOS_AISS`) — mapeadas aqui, uma a uma, por
      `mapear_para_touro`.
    - **Alterados**: touro do banco cujo NAAB aparece no AISS e cujos campos
      curados (`CAMPOS_CURADOS_COMPARACAO`) mudaram além da tolerância —
      formato `{"naab", "nome", "mudancas": {...}}`.
    - **Saídos**: touro do banco cujo NAAB NÃO aparece no AISS baixado —
      formato `{"naab", "nome"}`, SEM dados de prova. Pulado se
      `Touro.observacao` já tiver a marca `MARCA_MANTIDO` (ver
      `marcar_mantido`) — decisão já tomada, não repete toda semana.
    - **Novos**: linha do AISS cujo NAAB não existe em nenhum touro do banco
      — TODOS os campos mapeados por `mapear_para_touro`, de TODAS as
      centrais (sem filtro). Quem exibe o relatório decide como resumir uma
      lista grande; os dados aqui nunca são truncados.
    """
    mapeadas: dict[str, dict] = {}
    for linha in linhas_aiss:
        mapa = mapear_para_touro(linha)
        naab = mapa.get("naab")
        if naab:
            mapeadas[naab] = mapa

    existentes = session.exec(select(Touro)).all()
    existentes_por_naab = {t.naab: t for t in existentes}

    alterados: list[dict] = []
    saidos: list[dict] = []
    for naab, touro in existentes_por_naab.items():
        mapa = mapeadas.get(naab)
        if mapa is not None:
            mudancas = _comparar_campos_curados(touro, mapa)
            if mudancas:
                alterados.append({"naab": naab, "nome": touro.nome, "mudancas": mudancas})
        else:
            if MARCA_MANTIDO in (touro.observacao or ""):
                continue
            saidos.append({"naab": naab, "nome": touro.nome})

    novos: list[dict] = [mapa for naab, mapa in mapeadas.items() if naab not in existentes_por_naab]

    rodada = _extrair_rodada(nome_arquivo)
    return RelatorioNaab(
        rodada=rodada,
        total_comparados=len(existentes_por_naab),
        alterados=alterados,
        saidos=saidos,
        novos=novos,
    )


# ---------------------------------------------------------------------------
# Escrita (só usada depois que o dono aprova no chat)
# ---------------------------------------------------------------------------
def marcar_mantido(session: Session, naab: str, motivo: str | None = None) -> None:
    """Marca UM touro como "mantido por decisão do dono" — a nota vai para
    `Touro.observacao` (concatenada com `\\n`, nunca sobrescrevendo o que já
    tinha lá) para `comparar_catalogo` não voltar a listá-lo em "saídos" toda
    semana. Levanta `ValueError` se o NAAB não existir no banco."""
    naab_norm = (naab or "").strip().upper()
    touro = session.exec(select(Touro).where(Touro.naab == naab_norm)).first()
    if touro is None:
        raise ValueError(f"Touro com código NAAB {naab_norm!r} não encontrado — não é possível marcar como mantido.")

    hoje = date.today().strftime("%d/%m/%Y")
    linha_nova = f"{MARCA_MANTIDO} em {hoje}: {motivo or 'sem motivo registrado'}"
    obs_atual = (touro.observacao or "").strip()
    touro.observacao = f"{obs_atual}\n{linha_nova}" if obs_atual else linha_nova
    session.add(touro)
    session.commit()
