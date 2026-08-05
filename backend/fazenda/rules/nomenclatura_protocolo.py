"""
Nome automático de um lançamento de protocolo (IATF, Indução de Lactação,
Sanitário, Customizado) — o usuário não digita mais nome na hora de lançar; o
sistema monta a partir do nome cadastrado (molde) + a data do primeiro dia +
a data do último dia:

    {NOME CADASTRADO} - {D0} A {último dia} (D{inicial} A D{final} - {n} DIAS)

Ex.: "PROTOCOLO DE MASTITE 1 - 05/08/26 A 09/08/26 (D0 A D4 - 5 DIAS)"
"""
from __future__ import annotations

from datetime import date, timedelta


def gerar_nome_lancamento(nome_base: str, data_d0: date, dia_inicial: int, dia_final: int) -> str:
    data_ultimo = data_d0 + timedelta(days=(dia_final - dia_inicial))
    n_dias = dia_final - dia_inicial + 1
    base = (nome_base or "").strip().upper()
    return (
        f"{base} - {data_d0.strftime('%d/%m/%y')} A {data_ultimo.strftime('%d/%m/%y')} "
        f"(D{dia_inicial} A D{dia_final} - {n_dias} DIAS)"
    )
