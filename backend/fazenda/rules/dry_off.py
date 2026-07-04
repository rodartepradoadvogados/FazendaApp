"""
Regra de Secagem — 60 dias antes do parto provável.

Restrições (Seção 5):
  - SOMENTE vacas que já pariram (ordem_parto > 0 OU já tem lactação)
  - Novilhas de 1ª cria (nunca pariram) NÃO secam
  - Animal que não está em lactação também não precisa de secagem
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


DIAS_ANTECEDENCIA_SECAGEM = 60


@dataclass
class ResultadoSecagem:
    data_secagem: date
    data_parto_provavel: date
    numero_matriz: str
    deve_secar: bool
    motivo_exclusao: str | None = None


def calcular_secagem(
    numero_matriz: str,
    data_parto_provavel: date,
    ordem_parto: int | None,
    em_lactacao: bool,
) -> ResultadoSecagem:
    """
    Calcula a data de secagem de um animal.

    Args:
        numero_matriz: Identificador do animal.
        data_parto_provavel: Data calculada de parto (por GestationCalc).
        ordem_parto: Ordem de parto atual (0 = nunca pariu = novilha 1ª cria).
        em_lactacao: True se o animal está atualmente produzindo leite.

    Returns:
        ResultadoSecagem — se deve_secar=False, não gerar evento de secagem.
    """
    # Novilha de 1ª cria nunca seca
    if ordem_parto is not None and ordem_parto == 0:
        return ResultadoSecagem(
            data_secagem=data_parto_provavel - timedelta(days=DIAS_ANTECEDENCIA_SECAGEM),
            data_parto_provavel=data_parto_provavel,
            numero_matriz=numero_matriz,
            deve_secar=False,
            motivo_exclusao="Novilha de 1ª cria — não seca",
        )

    # Animal não está em lactação (já está seca ou nunca produziu)
    if not em_lactacao:
        return ResultadoSecagem(
            data_secagem=data_parto_provavel - timedelta(days=DIAS_ANTECEDENCIA_SECAGEM),
            data_parto_provavel=data_parto_provavel,
            numero_matriz=numero_matriz,
            deve_secar=False,
            motivo_exclusao="Não está em lactação — não precisa de secagem",
        )

    data_secagem = data_parto_provavel - timedelta(days=DIAS_ANTECEDENCIA_SECAGEM)
    return ResultadoSecagem(
        data_secagem=data_secagem,
        data_parto_provavel=data_parto_provavel,
        numero_matriz=numero_matriz,
        deve_secar=True,
    )
