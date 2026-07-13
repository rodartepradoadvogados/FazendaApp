"""
Códigos oficiais de central (stud) da NAAB. O número inicial de um código NAAB
identifica a central que comercializa o touro (ex.: "7HO12345" → central 7 =
Select Sires). Lista oficial: https://www.naab-css.org/naab-icar-stud-codes
(a NAAB não tem API pública; esta tabela reproduz os códigos das principais
centrais). Espelha frontend/lib/constants.ts → NAAB_STUDS.
"""
from __future__ import annotations

import re

NAAB_STUDS: dict[str, str] = {
    "1": "GENEX Cooperative",
    "7": "Select Sires",
    "9": "Select Sires",
    "11": "Alta Genetics",
    "14": "Select Sires",
    "29": "ABS Global",
    "94": "ABS Global",
    "97": "CRV",
    "200": "Semex",
    "250": "Select Sires",
    "288": "ASCOL",
    "507": "Select Sires",
    "509": "Select Sires",
    "523": "STgenetics",
    "551": "STgenetics",
    "596": "United Sires",
    "599": "Blondin Sires",
    "646": "STgenetics",
    "719": "RuAnn Genetics",
    "777": "Semex",
    "796": "United Sires",
    "799": "Blondin Sires",
}


def central_por_codigo_naab(codigo: str | None) -> str | None:
    """Central oficial a partir do prefixo numérico de um código NAAB."""
    m = re.match(r"\s*(\d{1,3})", codigo or "")
    return NAAB_STUDS.get(m.group(1)) if m else None
