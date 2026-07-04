"""
Utilitários compartilhados pelos parsers de CSV.
Todos os arquivos do Ideagri usam:
  - Encoding: Windows-1252 (Latin-1)
  - Separador: ponto-e-vírgula (;)
  - Decimal: vírgula
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Iterator


ENCODING = "windows-1252"
DELIMITER = ";"


def iter_csv_rows(content: bytes) -> Iterator[dict[str, str]]:
    """
    Lê bytes de um CSV Ideagri e itera sobre as linhas como dicionários.
    Ignora linhas completamente em branco.
    """
    text = content.decode(ENCODING, errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=DELIMITER)
    for row in reader:
        # Pula linhas onde todos os valores são vazios
        if all(v.strip() == "" for v in row.values()):
            continue
        yield {k.strip(): v.strip() for k, v in row.items()}


def parse_date(value: str) -> date | None:
    """Converte DD/MM/YYYY para date. Retorna None se vazio ou inválido."""
    if not value or value.strip() == "":
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return date.fromisoformat(value) if fmt == "%Y-%m-%d" else _parse_br_date(value)
        except ValueError:
            continue
    return None


def _parse_br_date(value: str) -> date:
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"Data inválida: {value}")
    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
    return date(year, month, day)


def parse_float(value: str) -> float | None:
    """Converte string decimal com vírgula para float. Retorna None se vazio."""
    if not value or value.strip() in ("", "-"):
        return None
    try:
        return float(value.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    """Converte string para int. Retorna None se vazio."""
    if not value or value.strip() in ("", "-"):
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def clean_grupo(grupo_raw: str) -> str:
    """
    Retorna o grupo primário de um animal.
    Campo pode conter múltiplos grupos separados por vírgula:
      '03 - Média,01 - NOV. ALTA' → '01 - NOV. ALTA' (menor número = principal)
    Heurística: toma o primeiro grupo (posição original no Ideagri é o principal).
    """
    if not grupo_raw:
        return ""
    grupos = [g.strip() for g in grupo_raw.split(",") if g.strip()]
    return grupos[0] if grupos else ""
