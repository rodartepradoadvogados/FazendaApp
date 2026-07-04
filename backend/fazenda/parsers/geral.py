"""
Parser do GERAL.csv — foto atual por animal (17 colunas).
Colunas (1-based):
  1  Nº animal
  2  Dt. nasc.
  3  Idade em meses
  4  Grupos atuais       ← pode ter vírgula (múltiplos grupos)
  5  Categoria completa
  6  Categoria abreviada
  7  Sit. rep.
  8  DEL
  9  Dt. últ. leite
  10 Últ. CL (kg)
  11 Dt. penúlt. CL
  12 Penúlt. CL (kg)
  13 Dt. antepenúlt. CL
  14 Antepenúlt. CL (kg)
  15 Dias após últ. CL
  16 Dt. últ. diag.
  17 Diag.
"""
from __future__ import annotations

from fazenda.models import Animal
from fazenda.parsers.utils import (
    clean_grupo,
    iter_csv_rows,
    parse_date,
    parse_float,
    parse_int,
)


def parse_geral(content: bytes) -> list[Animal]:
    """
    Recebe bytes do GERAL.csv e retorna lista de objetos Animal prontos para upsert.
    """
    animais: list[Animal] = []

    for row in iter_csv_rows(content):
        numero = row.get("Nº animal", "").strip()
        if not numero:
            continue

        grupo_raw = row.get("Grupos atuais", "")
        del_raw = row.get("DEL", "")

        animal = Animal(
            numero=numero,
            data_nasc=parse_date(row.get("Dt. nasc.", "")),
            idade_meses=parse_float(row.get("Idade em meses", "")),
            grupo_raw=grupo_raw,
            grupo_primario=clean_grupo(grupo_raw),
            categoria_completa=row.get("Categoria completa", "") or None,
            categoria_abrev=row.get("Categoria abreviada", "") or None,
            sit_rep=row.get("Sit. rep.", "") or None,
            del_dias=parse_int(del_raw) if del_raw else None,
            data_ult_leite=parse_date(row.get("Dt. últ. leite", "")),
            ult_cl_kg=parse_float(row.get("Últ. CL (kg)", "")),
            data_ult_diag=parse_date(row.get("Dt. últ. diag.", "")),
            diagnostico=row.get("Diag.", "") or None,
            ativo=True,
        )
        animais.append(animal)

    return animais
