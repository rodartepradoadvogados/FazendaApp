"""Bloco H — macrominerais (Ca, P, Mg, Na, Cl, K, S) e DCAD.

O balanço de cada mineral é calculado em ABSORVIDO (fornecido absorvido -
exigência), não em dietético total — uma exigência dietética bruta
superestimaria o que a vaca realmente tem disponível.

Referências: NASEM (2021), Cap. 7.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import constantes as k
from .alimentos import ConcentracoesDieta
from .digestao import IngestoesDieta
from .energia import ComposicaoGanho, ResultadoGestacao
from .tipos import AnimalEntrada


@dataclass
class ResultadoMineral:
    nome: str
    unidade: str
    fornecido_absorvido: float
    exigencia: float
    balanco: float


@dataclass
class ResultadoMinerais:
    calcio: ResultadoMineral
    fosforo: ResultadoMineral
    magnesio: ResultadoMineral
    sodio: ResultadoMineral
    cloro: ResultadoMineral
    potassio: ResultadoMineral
    enxofre: ResultadoMineral
    dcad_meq_kg: float


def _calcio_leite_g_por_l(raca: str) -> float:
    """Cálcio do leite, por raça — 1,17 g/L para Jersey, 1,03 g/L para as
    demais (usado só quando a proteína do leite não está disponível para o
    cálculo direto da exigência)."""
    if raca == "Jersey":
        return k.CALCIO_LEITE_G_POR_L_JERSEY
    return k.CALCIO_LEITE_G_POR_L_DEMAIS


def calcular_minerais(
    *,
    animal: AnimalEntrada,
    dieta: ConcentracoesDieta,
    ingestoes: IngestoesDieta,
    ganho: ComposicaoGanho,
    gestacao: ResultadoGestacao,
) -> ResultadoMinerais:
    cms = ingestoes.cms_kg_dia
    bw = animal.peso_vivo_kg
    bw_mature = animal.peso_maturo_kg
    ganho_total = ganho.ganho_alvo_total_kg
    producao = animal.producao_leite_kg_dia or 0.0
    gest_day = animal.dias_gestacao or 0

    def _absorvido_g(campo: str) -> float:
        return getattr(dieta, campo) / 100.0 * cms * 1000.0

    # ---- Cálcio -----------------------------------------------------
    fe_ca_m = k.CALCIO_MANTENCA_FECAL_G_POR_KG_CMS * cms
    ca_g = (
        9.83 * bw_mature ** 0.22 * bw ** -0.22 * ganho_total if bw > 0 else 0.0
    )
    ca_y = 0.0
    if gestacao.gestando:
        ca_y = (
            0.0245 * math.exp((0.05581 - 0.00007 * gest_day) * gest_day)
            - 0.0245 * math.exp((0.05581 - 0.00007 * (gest_day - 1)) * (gest_day - 1))
        ) * bw / 715.0
    ca_l = 0.0
    if producao > 0:
        if animal.proteina_leite_pct is not None:
            ca_l = (0.295 + 0.239 * animal.proteina_leite_pct) * producao
        else:
            ca_l = _calcio_leite_g_por_l(animal.raca) * producao
    ca_exigencia = fe_ca_m + ca_g + ca_y + ca_l
    ca_absorvido = _absorvido_g("ca_absorvido_pct_dm")
    calcio = ResultadoMineral(
        nome="Ca", unidade="g/d",
        fornecido_absorvido=ca_absorvido, exigencia=ca_exigencia,
        balanco=ca_absorvido - ca_exigencia,
    )

    # ---- Fosforo ------------------------------------------------------
    ur_p_m = k.FOSFORO_MANTENCA_URINARIA_G_POR_KG_PV * bw
    fe_p_m = (
        k.FOSFORO_MANTENCA_FECAL_NOVILHA_G_POR_KG_CMS
        if animal.paridade == 0
        else k.FOSFORO_MANTENCA_FECAL_VACA_G_POR_KG_CMS
    ) * cms
    p_m = ur_p_m + fe_p_m
    p_g = (1.2 + 4.635 * bw_mature ** 0.22 * bw ** -0.22) * ganho_total if bw > 0 else 0.0
    p_y = 0.0
    if gestacao.gestando:
        p_y = (
            0.02743 * math.exp((0.05527 - 0.000075 * gest_day) * gest_day)
            - 0.02743 * math.exp((0.05527 - 0.000075 * (gest_day - 1)) * (gest_day - 1))
        ) * bw / 715.0
    p_l = 0.0
    if producao > 0:
        mlk_np_pct = (animal.proteina_leite_pct or 3.2) / 100.0
        p_l = (0.48 + 0.13 * mlk_np_pct * 100.0) * producao
    p_exigencia = p_m + p_g + p_y + p_l
    p_absorvido = _absorvido_g("p_absorvido_pct_dm")
    fosforo = ResultadoMineral(
        nome="P", unidade="g/d",
        fornecido_absorvido=p_absorvido, exigencia=p_exigencia,
        balanco=p_absorvido - p_exigencia,
    )

    # ---- Magnesio -------------------------------------------------------
    ur_mg_m = k.MAGNESIO_MANTENCA_URINARIA_G_POR_KG_PV * bw
    fe_mg_m = k.MAGNESIO_MANTENCA_FECAL_G_POR_KG_CMS * cms
    mg_m = ur_mg_m + fe_mg_m
    mg_g = k.MAGNESIO_GANHO_G_POR_KG * ganho_total
    mg_y = 0.3 * (bw / 715.0) if gest_day > 190 else 0.0
    mg_l = k.MAGNESIO_LEITE_G_POR_KG * producao
    mg_exigencia = mg_m + mg_g + mg_y + mg_l

    k_pct_piso = max(dieta.k_pct, k.POTASSIO_PISO_PCT_MS_PARA_LN)
    coef_acmg = (
        k.MAGNESIO_ABS_INTERCEPTO_PCT - k.MAGNESIO_ABS_COEF_LN_K * math.log(k_pct_piso * 10.0)
    ) / 100.0
    coef_acmg = max(0.0, min(1.0, coef_acmg))
    mg_absorvido = dieta.mg_pct / 100.0 * cms * 1000.0 * coef_acmg
    magnesio = ResultadoMineral(
        nome="Mg", unidade="g/d",
        fornecido_absorvido=mg_absorvido, exigencia=mg_exigencia,
        balanco=mg_absorvido - mg_exigencia,
    )

    # ---- Sodio ------------------------------------------------------
    fe_na_m = k.SODIO_MANTENCA_FECAL_G_POR_KG_CMS * cms
    na_g = k.SODIO_GANHO_G_POR_KG * ganho_total
    na_y = 1.4 * (bw / 715.0) if gest_day > 190 else 0.0
    na_l = k.SODIO_LEITE_G_POR_KG * producao
    na_exigencia = fe_na_m + na_g + na_y + na_l
    na_absorvido = _absorvido_g("na_absorvido_pct_dm")
    sodio = ResultadoMineral(
        nome="Na", unidade="g/d",
        fornecido_absorvido=na_absorvido, exigencia=na_exigencia,
        balanco=na_absorvido - na_exigencia,
    )

    # ---- Cloro --------------------------------------------------------
    fe_cl_m = k.CLORO_MANTENCA_FECAL_G_POR_KG_CMS * cms
    cl_g = k.CLORO_GANHO_G_POR_KG * ganho_total
    cl_y = 1.0 * (bw / 715.0) if gest_day > 190 else 0.0
    cl_l = k.CLORO_LEITE_G_POR_KG * producao
    cl_exigencia = fe_cl_m + cl_g + cl_y + cl_l
    cl_absorvido = _absorvido_g("cl_absorvido_pct_dm")
    cloro = ResultadoMineral(
        nome="Cl", unidade="g/d",
        fornecido_absorvido=cl_absorvido, exigencia=cl_exigencia,
        balanco=cl_absorvido - cl_exigencia,
    )

    # ---- Potassio -------------------------------------------------------
    ur_k_m = (
        k.POTASSIO_MANTENCA_URINARIA_LACTANTE_G_POR_KG_PV
        if producao > 0
        else k.POTASSIO_MANTENCA_URINARIA_SECA_G_POR_KG_PV
    ) * bw
    fe_k_m = k.POTASSIO_MANTENCA_FECAL_G_POR_KG_CMS * cms
    k_m = ur_k_m + fe_k_m
    k_g = k.POTASSIO_GANHO_G_POR_KG * ganho_total
    k_y = 1.03 * (bw / 715.0) if gest_day > 190 else 0.0
    k_l = k.POTASSIO_LEITE_G_POR_KG * producao
    k_exigencia = k_m + k_g + k_y + k_l
    k_absorvido = _absorvido_g("k_absorvido_pct_dm")
    potassio = ResultadoMineral(
        nome="K", unidade="g/d",
        fornecido_absorvido=k_absorvido, exigencia=k_exigencia,
        balanco=k_absorvido - k_exigencia,
    )

    # ---- Enxofre (sem coeficiente de absorção próprio: dietético =
    # absorvido nesta implementação) --------------------------------
    s_exigencia = k.ENXOFRE_EXIGENCIA_G_POR_KG_CMS * cms
    s_fornecido = dieta.s_pct / 100.0 * cms * 1000.0
    enxofre = ResultadoMineral(
        nome="S", unidade="g/d",
        fornecido_absorvido=s_fornecido, exigencia=s_exigencia,
        balanco=s_fornecido - s_exigencia,
    )

    dcad = (
        dieta.k_pct / k.DCAD_PESO_EQUIVALENTE_K
        + dieta.na_pct / k.DCAD_PESO_EQUIVALENTE_NA
        - dieta.cl_pct / k.DCAD_PESO_EQUIVALENTE_CL
        - dieta.s_pct / k.DCAD_PESO_EQUIVALENTE_S
    ) * 10.0

    return ResultadoMinerais(
        calcio=calcio,
        fosforo=fosforo,
        magnesio=magnesio,
        sodio=sodio,
        cloro=cloro,
        potassio=potassio,
        enxofre=enxofre,
        dcad_meq_kg=dcad,
    )


__all__ = ["ResultadoMineral", "ResultadoMinerais", "calcular_minerais"]
