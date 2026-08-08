"""Bloco E — proteína microbiana, Michaelis-Menten dupla (NASEM 2021, Cap. 6).

Depende da FDN e do amido degradados no rúmen (Bloco D) e da PDR ingerida.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import constantes as k
from .digestao import IngestoesDieta, ResultadoDigestao
from .utilitarios import divisao_segura, piso, teto


@dataclass
class ResultadoMicrobiana:
    pdr_para_microbiana_kg: float  # PDR ingerida, limitada a 12% da MS
    capacidade_maxima_g_dia: float  # Vmax
    nitrogenio_microbiano_g_dia: float
    proteina_microbiana_bruta_g_dia: float
    proteina_microbiana_verdadeira_g_dia: float
    proteina_microbiana_verdadeira_digestivel_g_dia: float


def calcular_microbiana(
    dieta_pdr_pct_dm: float,
    ingestoes: IngestoesDieta,
    digestao: ResultadoDigestao,
) -> ResultadoMicrobiana:
    """Michaelis-Menten dupla (NASEM 2021, Cap. 6): capacidade máxima de
    síntese microbiana em função da PDR ingerida (limitada a 12% da MS),
    saturada pela FDN e pelo amido efetivamente degradados no rúmen."""
    pdr_teto_kg = ingestoes.cms_kg_dia * k.MICROBIANA_PDR_TETO_PCT_MS / 100.0
    pdr_para_microbiana_kg = ingestoes.rdp_kg
    if dieta_pdr_pct_dm > k.MICROBIANA_PDR_TETO_PCT_MS:
        pdr_para_microbiana_kg = pdr_teto_kg

    capacidade_maxima_g = (
        k.MICROBIANA_INTERCEPTO_VMAX_G
        + k.MICROBIANA_INCLINACAO_PDR_VMAX_G_POR_KG * pdr_para_microbiana_kg
    )

    # Quando não há FDN ou amido degradados no rúmen (dieta 100% mineral,
    # por exemplo), o termo de saturação de Michaelis-Menten correspondente
    # tende a infinito (não a zero) — é isso que torna a síntese microbiana
    # desprezível na ausência de substrato fermentável. `quando_zero` grande
    # (não 0.0) preserva esse sentido biológico; o piso de 10 g/d mais
    # abaixo garante que o resultado final nunca fique indefinido.
    _SEM_SUBSTRATO = 1.0e9
    denominador = 1.0 + divisao_segura(
        k.MICROBIANA_KM_FDN_DEGRADADA, digestao.rum_dig_ndf_kg, _SEM_SUBSTRATO
    ) + divisao_segura(k.MICROBIANA_KM_AMIDO_DEGRADADO, digestao.rum_dig_st_kg, _SEM_SUBSTRATO)

    nitrogenio_g = divisao_segura(capacidade_maxima_g, denominador, 0.0)

    # Eficiência de uso de PDR com teto de 100%: o N microbiano nunca pode
    # superar o N realmente disponível na PDR ingerida.
    n_disponivel_pdr_g = ingestoes.rdp_kg * 1000.0 / 6.25
    nitrogenio_g = teto(nitrogenio_g, n_disponivel_pdr_g) if n_disponivel_pdr_g > 0 else nitrogenio_g

    # Piso de 10 g/d — nunca abaixo disso, mesmo com dieta muito pobre em PDR
    # (correção de auditoria: o piso é aplicado diretamente ao nitrogênio
    # microbiano, não à proteína bruta microbiana).
    nitrogenio_g = piso(nitrogenio_g, k.MICROBIANA_PISO_NITROGENIO_G_DIA)

    proteina_bruta_g = nitrogenio_g * k.MICROBIANA_N_PARA_PB
    proteina_verdadeira_g = proteina_bruta_g * k.MICROBIANA_FRACAO_PROTEINA_VERDADEIRA
    proteina_verdadeira_digestivel_g = (
        proteina_verdadeira_g * k.MICROBIANA_DIGESTIBILIDADE_INTESTINAL_PCT / 100.0
    )

    return ResultadoMicrobiana(
        pdr_para_microbiana_kg=pdr_para_microbiana_kg,
        capacidade_maxima_g_dia=capacidade_maxima_g,
        nitrogenio_microbiano_g_dia=nitrogenio_g,
        proteina_microbiana_bruta_g_dia=proteina_bruta_g,
        proteina_microbiana_verdadeira_g_dia=proteina_verdadeira_g,
        proteina_microbiana_verdadeira_digestivel_g_dia=proteina_verdadeira_digestivel_g,
    )


__all__ = ["ResultadoMicrobiana", "calcular_microbiana"]
