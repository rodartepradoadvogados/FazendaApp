"""
Depreciação e manutenção preventiva do patrimônio.

Depreciação: linha reta (linear), a partir da vida útil cadastrada (texto
livre, ex. "7 Anos" ou "60 Meses"), da data de imobilização e do valor
residual. Quando a vida útil não pode ser interpretada (ou falta a data de
imobilização), o item entra na resposta sem depreciação e com um aviso — não
trava o cálculo dos demais itens.

Manutenção preventiva: plano OPCIONAL por item, só por periodicidade de DATA
(ex.: "a cada 6 meses"). Avaliamos cadastrar também por horas/uso, mas o
sistema não rastreia horímetro nem horas de uso de nenhum equipamento hoje —
não há de onde puxar esse dado sem inventar um cadastro novo inteiro (sensor,
lançamento manual de horas etc.), o que é escopo maior do que "manutenção
preventiva" pede agora. Por isso o plano por data cobre o caso de uso
imediato (troca de óleo semestral, revisão anual...) e fica mais simples e
viável; manutenção por uso pode ser adicionada depois como um campo a mais
sem quebrar o que já existe.
"""
from __future__ import annotations

import re
from datetime import date


def _vida_util_em_anos(texto: str | None) -> float | None:
    if not texto:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", texto)
    if not m:
        return None
    valor = float(m.group(1).replace(",", "."))
    return valor / 12 if re.search(r"m[eê]s", texto, re.IGNORECASE) else valor


def calcular_depreciacao(item: dict, hoje: date | None = None) -> dict:
    """Recebe um dict com os campos do Patrimonio (model_dump()) e devolve
    depreciacao_acumulada, valor_atual, vida_util_anos e uma eventual
    inconsistência (vida útil não reconhecida ou sem data de imobilização)."""
    hoje = hoje or date.today()
    valor_total = item.get("valor_total") or 0.0
    valor_residual = item.get("valor_residual") or 0.0
    data_imob = item.get("data_imobilizacao")
    vida_util_anos = _vida_util_em_anos(item.get("vida_util"))

    if item.get("depreciavel") is False:
        # Só valoriza (ex.: terra/fazenda) — nunca deprecia; o "valor atual" é
        # o valor de mercado mais recente informado, ou o valor de aquisição
        # enquanto nenhuma atualização foi feita ainda. Nunca gera inconsistência
        # por falta de vida útil/data de imobilização — não se aplica aqui.
        valor_mercado = item.get("valor_mercado_atual")
        return {
            "depreciacao_acumulada": None,
            "valor_atual": round(valor_mercado if valor_mercado is not None else valor_total, 2),
            "vida_util_anos": None,
            "inconsistencia": None,
        }
    if item.get("data_baixa"):
        # Já baixado — parou de depreciar; o valor atual é o residual cadastrado.
        return {
            "depreciacao_acumulada": round(max(valor_total - valor_residual, 0.0), 2),
            "valor_atual": round(valor_residual, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": None,
        }
    if not data_imob:
        return {
            "depreciacao_acumulada": None, "valor_atual": round(valor_total, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": "Sem data de imobilização — não é possível calcular a depreciação.",
        }
    if not vida_util_anos or vida_util_anos <= 0:
        return {
            "depreciacao_acumulada": None, "valor_atual": round(valor_total, 2),
            "vida_util_anos": None,
            "inconsistencia": f'Vida útil "{item.get("vida_util") or "—"}" não reconhecida — cadastre um número (ex.: "7 anos").',
        }

    idade_anos = max((hoje - data_imob).days / 365.25, 0.0)
    depreciavel = max(valor_total - valor_residual, 0.0)
    dep_anual = depreciavel / vida_util_anos
    acumulada = min(dep_anual * idade_anos, depreciavel)
    return {
        "depreciacao_acumulada": round(acumulada, 2),
        "valor_atual": round(valor_total - acumulada, 2),
        "vida_util_anos": vida_util_anos,
        "inconsistencia": None,
    }


DIAS_ALERTA_MANUTENCAO_PROXIMA = 15  # "perto de vencer" — mesma janela usada no front para destacar


def somar_meses(base: date, meses: int) -> date:
    """Soma `meses` a `base`, ajustando o dia quando o mês de destino é mais
    curto (ex.: 31/01 + 1 mês = 28 ou 29/02) — mesma lógica de
    `agenda._proxima_ocorrencia`, duplicada aqui para manter esta regra sem
    depender do router de agenda."""
    import calendar as _calendar

    mes_total = base.month - 1 + meses
    ano = base.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(base.day, _calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def status_manutencao(item: dict, hoje: date | None = None) -> dict:
    """Recebe um dict com os campos de manutenção do Patrimonio (model_dump())
    e devolve a situação do plano preventivo: None quando não há plano
    cadastrado (sem data_proxima_manutencao), ou "vencida"/"proxima"/"ok" a
    partir de quantos dias faltam para a próxima manutenção. Item já baixado
    nunca alerta — não faz sentido agendar manutenção de bem baixado."""
    hoje = hoje or date.today()
    prox = item.get("data_proxima_manutencao")
    if not prox or item.get("data_baixa"):
        return {"situacao_manutencao": None, "dias_para_manutencao": None}
    dias = (prox - hoje).days
    if dias < 0:
        situacao = "vencida"
    elif dias <= DIAS_ALERTA_MANUTENCAO_PROXIMA:
        situacao = "proxima"
    else:
        situacao = "ok"
    return {"situacao_manutencao": situacao, "dias_para_manutencao": dias}


def proxima_atualizacao_valor_mercado(item: dict, frequencia_padrao_meses: int) -> date | None:
    """Data da próxima pendência de "atualizar valor de mercado" (Agenda) —
    só para patrimônio não depreciável (ver Patrimonio.depreciavel). None =
    nunca gera pendência: item deprecia normalmente, já foi baixado, ou a
    frequência (própria do item ou o padrão do sistema) é 0 ("nunca").

    frequencia_meses do PRÓPRIO item, quando preenchida, vence a do sistema
    (override por item) — 0 é "nunca" mesmo que o padrão do sistema não seja."""
    if item.get("depreciavel") is not False or item.get("data_baixa"):
        return None
    frequencia = item.get("atualizacao_valor_mercado_frequencia_meses")
    if frequencia is None:
        frequencia = frequencia_padrao_meses
    if not frequencia:
        return None
    base = item.get("data_ultima_atualizacao_valor_mercado") or item.get("data_imobilizacao")
    if not base:
        return None
    return somar_meses(base, frequencia)
