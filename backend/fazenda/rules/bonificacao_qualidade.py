"""
Cálculo do valor estimado de bonificação/penalização por qualidade do leite
(#548) — compara CCS/CBT/gordura/proteína de um lançamento de Qualidade do
leite contra as faixas cadastradas pelo usuário (Configurações > Parâmetros,
modelo `FaixaBonificacaoQualidade`) e soma o ajuste (R$/litro) de cada
indicador cuja medição caiu em alguma faixa.

Não existe uma tabela nacional única de bonificação de leite no Brasil — cada
laticínio define a sua — por isso as faixas são 100% configuráveis pelo
usuário, e esta função nunca hardcoda valores. Sem nenhuma faixa cadastrada
(ou nenhuma faixa ativa), devolve `total_por_litro=None` — distinto de 0 —
para a tela conseguir mostrar "não configurado" em vez de um valor incorreto.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

# Indicadores de Qualidade do leite (fazenda.models.QualidadeLeite) que podem
# ter uma faixa de bonificação cadastrada — os mais comuns na prática dos
# laticínios brasileiros dentre os já registrados pelo sistema.
INDICADORES_BONIFICAVEIS = ("ccs", "cbt", "gordura_pct", "proteina_pct")


def _valor_min_ordenacao(faixa: Any) -> float:
    return faixa.valor_min if faixa.valor_min is not None else float("-inf")


def _faixa_bate(valor: float, faixa: Any) -> bool:
    if faixa.valor_min is not None and valor < faixa.valor_min:
        return False
    if faixa.valor_max is not None and valor > faixa.valor_max:
        return False
    return True


def calcular_bonificacao(registro: Mapping[str, Any], faixas: Iterable[Any]) -> dict:
    """`registro` é um dict com (pelo menos) os campos de INDICADORES_BONIFICAVEIS;
    `faixas` é a lista de `FaixaBonificacaoQualidade` (ativas ou não — o filtro
    de `ativo` é feito aqui dentro).

    Devolve:
      {"total_por_litro": float | None, "detalhe": [{"indicador", "valor", "ajuste_por_litro"}]}

    `total_por_litro` só é `None` quando não há nenhuma faixa ativa cadastrada
    no sistema inteiro — se há faixas mas nenhuma bateu com os valores deste
    lançamento específico, o total é 0.0 (nenhum ajuste se aplica a ele).
    """
    faixas_ativas = [f for f in faixas if f.ativo]
    if not faixas_ativas:
        return {"total_por_litro": None, "detalhe": []}

    por_indicador: dict[str, list] = {}
    for f in faixas_ativas:
        por_indicador.setdefault(f.indicador, []).append(f)
    for lista in por_indicador.values():
        lista.sort(key=_valor_min_ordenacao)

    detalhe: list[dict] = []
    total = 0.0
    for indicador in INDICADORES_BONIFICAVEIS:
        valor = registro.get(indicador)
        if valor is None or indicador not in por_indicador:
            continue
        for faixa in por_indicador[indicador]:
            if _faixa_bate(valor, faixa):
                detalhe.append({"indicador": indicador, "valor": valor, "ajuste_por_litro": faixa.ajuste_por_litro})
                total += faixa.ajuste_por_litro
                break

    return {"total_por_litro": round(total, 4), "detalhe": detalhe}
