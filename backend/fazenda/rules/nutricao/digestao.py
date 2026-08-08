"""Bloco D — digestão ruminal e de trato total, e ingestões (kg/d).

Depende do CMS: os níveis de ingestão (kg/d, ou proporção do peso vivo)
afetam a taxa de passagem e, por consequência, a fração de FDN e amido
degradada no rúmen — é isso que a proteína microbiana (Bloco E) usa a
seguir.

Referências: NASEM (2021), Cap. 3 — digestão ruminal de FDN (White et al.,
2016) e de amido (Roman-Garcia et al., 2016), e ajuste de digestibilidade de
trato total pelo nível de ingestão (Vandehaar/Weiss).
"""
from __future__ import annotations

from dataclasses import dataclass

from .alimentos import ConcentracoesDieta
from .tipos import AnimalEntrada
from .utilitarios import divisao_segura, limitar


@dataclass
class IngestoesDieta:
    """Ingestões da dieta em kg/d (Etapa 5: proporção × CMS)."""

    cms_kg_dia: float
    pb_kg: float
    fdn_kg: float
    fda_kg: float
    amido_kg: float
    ag_kg: float
    cinzas_kg: float
    rup_kg: float
    rdp_kg: float
    rup_digestivel_kg: float
    for_ndf_kg: float
    ge_mcal: float
    de_base_mcal: float


@dataclass
class ResultadoDigestao:
    ingestoes: IngestoesDieta

    rum_dc_ndf_pct: float
    rum_dc_st_pct: float
    rum_dig_ndf_kg: float
    rum_dig_st_kg: float

    tt_dc_ndf_base_pct: float
    tt_dc_st_base_pct: float
    tt_dc_ndf_pct: float
    tt_dc_st_pct: float
    ndf_digerida_kg: float
    amido_digerido_kg: float
    ndf_digerida_pct_dieta: float  # % da MS da dieta, usado no balanço


def ingestoes_dieta(dieta: ConcentracoesDieta, cms_kg_dia: float) -> IngestoesDieta:
    """Etapa 5 — ingestões por ingrediente e da dieta (kg/d) = proporção ×
    CMS. Aqui, como as concentrações já são % da MS da dieta, cada ingestão
    é simplesmente concentração/100 × CMS."""
    return IngestoesDieta(
        cms_kg_dia=cms_kg_dia,
        pb_kg=dieta.pb_pct / 100.0 * cms_kg_dia,
        fdn_kg=dieta.fdn_pct / 100.0 * cms_kg_dia,
        fda_kg=dieta.fda_pct / 100.0 * cms_kg_dia,
        amido_kg=dieta.amido_pct / 100.0 * cms_kg_dia,
        ag_kg=dieta.ag_pct / 100.0 * cms_kg_dia,
        cinzas_kg=dieta.cinzas_pct / 100.0 * cms_kg_dia,
        rup_kg=max(0.0, dieta.rup_pct_dm / 100.0 * cms_kg_dia),
        rdp_kg=max(0.0, dieta.rdp_pct_dm / 100.0 * cms_kg_dia),
        rup_digestivel_kg=max(0.0, dieta.rup_digestivel_pct_dm / 100.0 * cms_kg_dia),
        for_ndf_kg=dieta.forragem_ndf_pct_dm / 100.0 * cms_kg_dia,
        ge_mcal=dieta.ge_mcal_kg * cms_kg_dia,
        de_base_mcal=dieta.de_base_mcal_kg * cms_kg_dia,
    )


def _digestibilidade_ruminal_ndf(
    dieta: ConcentracoesDieta, ing: IngestoesDieta
) -> float:
    """White et al. (2016) — digestibilidade ruminal da FDN, % da FDN."""
    valor = (
        -31.9
        + 0.721 * dieta.fdn_pct
        - 0.247 * dieta.amido_pct
        + 6.63 * dieta.pb_pct
        - 0.211 * dieta.pb_pct ** 2
        - 0.387 * dieta.adf_ndf * 100.0
        - 0.121 * dieta.forragem_umida_pct_dm
        + 1.51 * ing.cms_kg_dia
    )
    return max(valor, 0.1)


def _digestibilidade_ruminal_amido(
    dieta: ConcentracoesDieta, ing: IngestoesDieta
) -> float:
    """Roman-Garcia et al. (2016) — digestibilidade ruminal do amido, %
    do amido."""
    valor = (
        70.6
        - 1.45 * ing.cms_kg_dia
        + 0.424 * dieta.forragem_ndf_pct_dm
        + 1.39 * dieta.amido_pct
        - 0.0219 * dieta.amido_pct ** 2
        - 0.154 * dieta.forragem_umida_pct_dm
    )
    return limitar(valor, 0.1, 100.0)


def calcular_digestao(
    dieta: ConcentracoesDieta, animal: AnimalEntrada, cms_kg_dia: float
) -> ResultadoDigestao:
    """Bloco D completo: digestão ruminal (White/Roman-Garcia) e ajuste da
    digestibilidade de trato total pelo nível de ingestão (Vandehaar/Weiss)."""
    ing = ingestoes_dieta(dieta, cms_kg_dia)

    rum_dc_ndf = _digestibilidade_ruminal_ndf(dieta, ing)
    rum_dc_st = _digestibilidade_ruminal_amido(dieta, ing)
    rum_dig_ndf_kg = rum_dc_ndf / 100.0 * ing.fdn_kg
    rum_dig_st_kg = rum_dc_st / 100.0 * ing.amido_kg

    tt_dc_ndf_base = divisao_segura(dieta.ndf_digerida_base_pct_dm, dieta.fdn_pct, 0.0) * 100.0
    tt_dc_st_base = divisao_segura(dieta.amido_digerido_base_pct_dm, dieta.amido_pct, 0.0) * 100.0

    dmi_pv = divisao_segura(cms_kg_dia, animal.peso_vivo_kg, 0.0)
    tt_dc_ndf = tt_dc_ndf_base
    if tt_dc_ndf_base != 0.0:
        tt_dc_ndf = tt_dc_ndf_base - (1.1 * (dmi_pv - 0.035)) * 100.0
    tt_dc_ndf = limitar(tt_dc_ndf, 0.0, 100.0)

    tt_dc_st = tt_dc_st_base
    if tt_dc_st_base != 0.0:
        tt_dc_st = tt_dc_st_base - (1.0 * (dmi_pv - 0.035)) * 100.0
    tt_dc_st = limitar(tt_dc_st, 0.0, 100.0)

    ndf_digerida_kg = tt_dc_ndf / 100.0 * ing.fdn_kg
    amido_digerido_kg = tt_dc_st / 100.0 * ing.amido_kg

    return ResultadoDigestao(
        ingestoes=ing,
        rum_dc_ndf_pct=rum_dc_ndf,
        rum_dc_st_pct=rum_dc_st,
        rum_dig_ndf_kg=rum_dig_ndf_kg,
        rum_dig_st_kg=rum_dig_st_kg,
        tt_dc_ndf_base_pct=tt_dc_ndf_base,
        tt_dc_st_base_pct=tt_dc_st_base,
        tt_dc_ndf_pct=tt_dc_ndf,
        tt_dc_st_pct=tt_dc_st,
        ndf_digerida_kg=ndf_digerida_kg,
        amido_digerido_kg=amido_digerido_kg,
        ndf_digerida_pct_dieta=divisao_segura(ndf_digerida_kg * 100.0, cms_kg_dia, 0.0),
    )


__all__ = ["IngestoesDieta", "ResultadoDigestao", "ingestoes_dieta", "calcular_digestao"]
