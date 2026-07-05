"""
Parser da Lista de controles leiteiros — histórico de pesagens de leite por vaca.

Formato de origem (uma linha por pesagem):
  NUMERO;NOME_RESUMIDO;RGD;RACA;DATA_LEITE;PESO_TOTAL_LEITE;DATA_ULTIMO_PARTO;DATA_BAIXA

Cada vaca tem N linhas (uma por controle). DEL no controle é calculado a partir
da data do último parto. Alimenta a curva de lactação e o histórico produtivo.
"""
from __future__ import annotations

from fazenda.models import ControleLeiteiro
from fazenda.parsers.utils import iter_csv_rows, parse_date, parse_float


def parse_controle_leiteiro(content: bytes) -> list[ControleLeiteiro]:
    registros: list[ControleLeiteiro] = []

    for row in iter_csv_rows(content):
        numero = (row.get("NUMERO", "") or "").strip()
        data_controle = parse_date(row.get("DATA_LEITE", ""))
        if not numero or not data_controle:
            continue

        producao = parse_float(row.get("PESO_TOTAL_LEITE", ""))
        data_parto = parse_date(row.get("DATA_ULTIMO_PARTO", ""))

        del_controle = None
        if data_parto and data_controle >= data_parto:
            del_controle = (data_controle - data_parto).days

        registros.append(
            ControleLeiteiro(
                numero_matriz=numero,
                data_controle=data_controle,
                producao_kg=producao,
                del_no_controle=del_controle,
                data_ult_parto=data_parto,
            )
        )

    return registros
