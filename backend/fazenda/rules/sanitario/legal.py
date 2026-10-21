"""
Prazos legais (puros). Atestado (ex.: Agrodefesa/SIDAGO para a B19): N dias
após a aplicação, N dias após a NF-e da compra da vacina, ou — o padrão
decidido — o que vencer PRIMEIRO. Comprovação periódica: a cada N dias
(ex.: 180) a partir da última cumprida, com aviso N dias antes.

A NF-e de compra usa `LoteEstoque.data_compra` como substituto (plano, "pontos
que ficam fora").
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional


def vencimento_atestado(atestado: Optional[dict], data_aplicacao: date, data_nfe: Optional[date] = None) -> Optional[date]:
    """None quando a caixa não tem atestado configurado."""
    if not atestado:
        return None
    dias = int(atestado.get("dias") or 30)
    quando = atestado.get("quando") or "primeiro"
    p_apl = data_aplicacao + timedelta(days=dias)
    p_nfe = data_nfe + timedelta(days=dias) if data_nfe else None
    if quando == "nfe" and p_nfe:
        return p_nfe
    if quando == "primeiro" and p_nfe:
        return min(p_apl, p_nfe)
    return p_apl


def vencimento_comprovacao(comprovacao: Optional[dict], ultima: date) -> Optional[date]:
    if not comprovacao:
        return None
    return ultima + timedelta(days=int(comprovacao.get("dias") or 180))


def deve_avisar(vence_em: date, hoje: date, aviso_dias: int) -> bool:
    return (vence_em - hoje).days <= int(aviso_dias)
