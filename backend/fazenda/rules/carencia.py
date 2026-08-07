"""
Carência de leite e de carne — guardada SEPARADA, exibida JUNTA.

Configuração (Farmácia) tem dois campos independentes, porque são dois prazos
diferentes e vêm de linhas diferentes da bula. Mas em lançamento, consulta e
relatório o operador precisa ver UMA informação só, no formato:

    Carência: leite — 3 dias
    Carência: carne — 28 dias
    Carência: leite — 3 dias / carne — 28 dias

Nulo NUNCA vira zero. "Não informada" é uma resposta honesta; "0 dias" é uma
liberação que ninguém deu — e num rebanho leiteiro essa diferença é o tanque
inteiro condenado. Por isso o texto de fallback é explícito.
"""
from __future__ import annotations

from datetime import date, timedelta

SEM_INFORMACAO = "Carência: não informada"


def formatar_carencia(
    leite_dias: int | None,
    carne_dias: int | None,
    proibido_lactacao: bool | None = False,
) -> str:
    """Monta o campo único de carência a partir dos dois prazos configurados.

    `proibido_lactacao` ganha do prazo de leite: produto vetado em vaca em
    ordenha não tem "carência", tem proibição — e escrever um número ali faria
    o operador achar que basta esperar.
    """
    partes: list[str] = []
    if proibido_lactacao:
        partes.append("leite — NÃO USAR em lactação")
    elif leite_dias is not None:
        partes.append(f"leite — {leite_dias} dias")
    if carne_dias is not None:
        partes.append(f"carne — {carne_dias} dias")
    if not partes:
        return SEM_INFORMACAO
    return "Carência: " + " / ".join(partes)


def carencia_dict(
    leite_dias: int | None,
    carne_dias: int | None,
    proibido_lactacao: bool | None = False,
    data_aplicacao: date | None = None,
) -> dict:
    """Bloco pronto para qualquer endpoint que exponha carência — os dois
    prazos crus (para a UI fazer o que quiser) mais o texto já formatado, para
    não espalhar a regra de formatação por dez telas.

    Com `data_aplicacao`, calcula também até quando descartar — que é o que o
    ordenhador realmente precisa saber, mais do que o número de dias.
    """
    dados = {
        "leite_dias": leite_dias,
        "carne_dias": carne_dias,
        "proibido_lactacao": bool(proibido_lactacao),
        "texto": formatar_carencia(leite_dias, carne_dias, proibido_lactacao),
        "liberacao_leite": None,
        "liberacao_carne": None,
    }
    if data_aplicacao is not None:
        if leite_dias is not None and not proibido_lactacao:
            dados["liberacao_leite"] = (data_aplicacao + timedelta(days=leite_dias)).isoformat()
        if carne_dias is not None:
            dados["liberacao_carne"] = (data_aplicacao + timedelta(days=carne_dias)).isoformat()
    return dados
