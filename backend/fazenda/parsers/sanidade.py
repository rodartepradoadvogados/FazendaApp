"""
Parser do SANIDADE.csv — lista de medicamentos aplicados nos animais (Ideagri).

Colunas: Nº animal · Nome · Dt. nasc. · Sx · Raça · Dt. aplic. · Produto aplic. ·
         Dose · Lote · Atividade · Obs. aplic.

Cada linha é uma aplicação. O produto é classificado numa categoria (Vacina,
Antiparasitário, Antibiótico/Mastite, Hormônio, Reprodutivo, Outros) por
palavras-chave, para os dashboards.
"""
from __future__ import annotations

from fazenda.models import Sanidade
from fazenda.parsers.utils import iter_csv_rows, parse_date

# Classificação por palavra-chave no nome do produto (ordem importa).
_CATEGORIAS: list[tuple[str, tuple[str, ...]]] = [
    ("Vacina", ("vacina", "rb 51", "bovigen", "lepto", "brucel", "aftosa", "clostr")),
    ("Antiparasitário", ("ivermectina", "vermíf", "vermif", "closantel", "abamectina", "doramectina", "carrapaticida", "mosca")),
    ("Antibiótico/Mastite", ("spectramast", "borgal", "micotil", "mastite", "penicilina", "oxitetraciclina", "ceftiofur", "tulatromicina", "florfenicol", "terramicina")),
    ("Hormônio", ("lactotropin", "boostin", "sincro", "cidr", "estron", "gonadotrof", "cipionato", "prostaglandina", "cloprostenol")),
    ("Reprodutivo", ("scratch", "adesivo", "iatf")),
    ("Anti-inflamatório", ("flunixin", "meloxicam", "banamine", "diclofenaco", "dexametasona")),
    ("Suplemento/Vitamina", ("ade", "vitamina", "cálcio", "calcio", "glicose", "ferro", "energético", "energetico")),
]


def classificar_produto(produto: str) -> str:
    p = (produto or "").lower()
    for categoria, chaves in _CATEGORIAS:
        if any(c in p for c in chaves):
            return categoria
    return "Outros"


def _dose(valor: str) -> float | None:
    """Dose pode vir '0,5', '2', '40.00' — normaliza vírgula/ponto."""
    v = (valor or "").strip()
    if not v:
        return None
    v = v.replace(",", ".")
    if v.count(".") > 1:  # ex.: '1.234.50' → mantém só o último ponto como decimal
        parts = v.split(".")
        v = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(v)
    except ValueError:
        return None


def _get(row: dict[str, str], *nomes: str) -> str:
    for n in nomes:
        if n in row and row[n].strip():
            return row[n].strip()
    return ""


def parse_sanidade(content: bytes) -> list[Sanidade]:
    registros: list[Sanidade] = []
    for row in iter_csv_rows(content):
        numero = _get(row, "Nº animal", "N° animal", "No animal", "Numero animal")
        produto = _get(row, "Produto aplic.", "Produto aplicado", "Produto")
        if not numero or not produto:
            continue
        registros.append(
            Sanidade(
                numero_matriz=numero,
                nome=_get(row, "Nome") or None,
                data_nasc=parse_date(_get(row, "Dt. nasc.", "Dt nasc", "Data nasc")),
                sexo=_get(row, "Sx", "Sexo") or None,
                raca=_get(row, "Raça", "Raca") or None,
                data_aplicacao=parse_date(_get(row, "Dt. aplic.", "Dt aplic", "Data aplic")),
                produto=produto,
                categoria=classificar_produto(produto),
                dose=_dose(_get(row, "Dose")),
                lote=_get(row, "Lote") or None,
                atividade=_get(row, "Atividade") or None,
                obs=_get(row, "Obs. aplic.", "Obs aplic", "Obs") or None,
            )
        )
    return registros
