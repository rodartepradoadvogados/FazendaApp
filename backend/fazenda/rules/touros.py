"""
Importação do catálogo genético de touros (provas do fornecedor / NAAB-CDCB).

Os catálogos exportados pelo ABS BullSearch, Alta, Select Sires, CRV etc. têm
nomes de coluna variados (inglês/português). Aqui mapeamos por APELIDOS: cada
campo do modelo Touro aceita vários nomes de coluna possíveis, casados sem
acento e em minúsculas. O que não casar é ignorado sem quebrar o import.
"""
from __future__ import annotations

import io
import re
import unicodedata

from sqlmodel import Session, select

from fazenda.models import Touro
from fazenda.parsers.utils import parse_float
from fazenda.rules.naab import central_por_codigo_naab


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

    criados = atualizados = 0
    erros: list[str] = []
    for i, row in enumerate(linhas, start=2):
        naab = (row.get(mapa["naab"]) or "").strip().upper()
        if not naab:
            continue
        touro = session.exec(select(Touro).where(Touro.naab == naab)).first()
        novo = touro is None
        if novo:
            touro = Touro(naab=naab)
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
    return {"criados": criados, "atualizados": atualizados, "erros": erros}
