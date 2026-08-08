"""Bloco B — Consumo de Matéria Seca (CMS), as 7 equações da Fase 1.

Referências: NASEM (2021), Cap. 2 ("Prediction of Feed Intake").
"""
from __future__ import annotations

from dataclasses import dataclass

from . import constantes as k
from .alimentos import ConcentracoesDieta
from .tipos import AnimalEntrada, ValorInvalidoError
from .utilitarios import divisao_segura, limitar


@dataclass
class ResultadoConsumo:
    cms_kg_dia: float
    equacao_usada: int
    cms_pct_pv: float
    cms_g_kg_pv075: float


def _energia_liquida_leite_alvo_mcal_kg(animal: AnimalEntrada) -> float:
    """NASEM 2021, Cap. 2 — energia líquida do leite-alvo, usada como
    insumo das equações de CMS de vaca lactante. Cai para a estimativa de
    Tyrrell & Reid (1965), baseada só na produção, quando gordura/proteína
    não estão disponíveis (a validação de entrada já torna esses dois
    campos obrigatórios quando há produção > 0 — este é só um resguardo
    extra)."""
    if animal.gordura_leite_pct is not None and animal.proteina_leite_pct is not None:
        return (
            9.29 * animal.gordura_leite_pct / 100.0
            + 5.85 * animal.proteina_leite_pct / 100.0
            + 3.95 * animal.lactose_leite_pct / 100.0
        )
    gordura = animal.gordura_leite_pct if animal.gordura_leite_pct is not None else 3.8
    return k.TYRRELL_REID_INTERCEPTO + k.TYRRELL_REID_COEF_GORDURA * gordura / 100.0


def _cms_novilha_animal(animal: AnimalEntrada) -> float:
    """NASEM 2021, Cap. 2, eq. 2-3 — novilha, só fatores animais."""
    return (
        k.CMS_NOVILHA_ANIMAL_COEF_PVMADURO
        * animal.peso_maturo_kg
        * (1 - pow(2.718281828459045, k.CMS_NOVILHA_ANIMAL_EXP * animal.peso_vivo_kg / animal.peso_maturo_kg))
    )


def _cms_novilha_dieta(animal: AnimalEntrada, dieta: ConcentracoesDieta) -> float:
    """NASEM 2021, Cap. 2, eq. 2-4 — novilha, fatores animais + FDN da dieta."""
    desvio_fdn = dieta.fdn_pct - (
        23.1 + 56.0 * animal.peso_vivo_kg / animal.peso_maturo_kg
        - 30.6 * (animal.peso_vivo_kg / animal.peso_maturo_kg) ** 2
    )
    base = k.CMS_NOVILHA_DIETA_COEF_PVMADURO * animal.peso_maturo_kg * (
        1 - pow(2.718281828459045, k.CMS_NOVILHA_DIETA_EXP * animal.peso_vivo_kg / animal.peso_maturo_kg)
    )
    return base - k.CMS_NOVILHA_DIETA_COEF_DESVIO_FDN * desvio_fdn


def _cms_lactante_animal(animal: AnimalEntrada) -> float:
    """NASEM 2021, Cap. 2, eq. 2-1 — vaca lactante, só fatores animais
    (equação-padrão da Fase 1)."""
    nel_leite = _energia_liquida_leite_alvo_mcal_kg(animal)
    nel_leite_saida = nel_leite * (animal.producao_leite_kg_dia or 0.0)
    paridade_ajustada = animal.paridade - 1.0
    del_dias = animal.del_dias or 0

    termo1 = (
        k.CMS_LACT1_INTERCEPTO
        + k.CMS_LACT1_COEF_PARIDADE * paridade_ajustada
        + k.CMS_LACT1_COEF_ELLEITE * nel_leite_saida
        + k.CMS_LACT1_COEF_PV * animal.peso_vivo_kg
        + (k.CMS_LACT1_ECC_INTERCEPTO + k.CMS_LACT1_ECC_COEF_PARIDADE * paridade_ajustada) * animal.ecc
    )
    curva = 1 - (
        k.CMS_LACT1_CURVA_INTERCEPTO + k.CMS_LACT1_CURVA_COEF_PARIDADE * paridade_ajustada
    ) * pow(2.718281828459045, k.CMS_LACT1_CURVA_DECAIMENTO * del_dias)
    return termo1 * curva


def _cms_lactante_dieta(animal: AnimalEntrada, dieta: ConcentracoesDieta) -> float:
    """NASEM 2021, Cap. 2, eq. 2-2 — vaca lactante, fatores animais + dieta
    (usa a concentração de DNDF48 da fração de volumoso da dieta)."""
    dndf48_fornndf = dieta.forragem_dndf48_sobre_forragem_ndf_pct
    producao = animal.producao_leite_kg_dia or 0.0

    return (
        k.CMS_LACT2_INTERCEPTO
        + k.CMS_LACT2_COEF_FDN_FOR * dieta.forragem_ndf_pct_dm
        + k.CMS_LACT2_COEF_RAZAO_FDA_FDN * dieta.adf_ndf
        + k.CMS_LACT2_COEF_DNDF48_FORNDF * dndf48_fornndf
        - k.CMS_LACT2_COEF_INTERACAO_FDA
        * (dieta.adf_ndf - k.CMS_LACT2_FDA_NDF_CENTRO)
        * (dndf48_fornndf - k.CMS_LACT2_DNDF48_CENTRO)
        + k.CMS_LACT2_COEF_PRODUCAO * producao
        + k.CMS_LACT2_COEF_INTERACAO_PROD
        * (dndf48_fornndf - k.CMS_LACT2_DNDF48_CENTRO)
        * (producao - k.CMS_LACT2_PRODUCAO_CENTRO)
    )


def _semana_pre_parto(animal: AnimalEntrada) -> float:
    dias_gestacao = animal.dias_gestacao or 0
    dias_pre_parto = dias_gestacao - animal.duracao_gestacao_dias
    semana = dias_pre_parto / 7.0
    return limitar(semana, -3.0, 0.0)


def _cms_transicao(animal: AnimalEntrada, dieta: ConcentracoesDieta) -> float:
    """NASEM 2021, Cap. 2 — equação de transição para vaca seca."""
    fdn_limitada = limitar(dieta.fdn_pct, 30.0, 55.0)
    semana = _semana_pre_parto(animal)
    duracao_semanas = semana * 2.0  # duração estimada da fase de transição

    ka = k.CMS_TRANSICAO_KA_PCT_PV
    kb = -(k.CMS_TRANSICAO_KB_INTERCEPTO - k.CMS_TRANSICAO_KB_COEF_FDN * fdn_limitada)
    kc = k.CMS_TRANSICAO_KC_PCT_PV

    individual_pct_pv = ka + kb * semana + kc * semana**2
    cms_individual = k.CMS_TRANSICAO_FATOR_PV * animal.peso_vivo_kg * individual_pct_pv / 100.0

    if semana >= 0.0:
        # Parto já ocorreu ou é hoje: duracao_semanas é 0, a integral do
        # período de transição é indefinida (0/0) — usa só o termo
        # individual, sem essa parcela, nunca NaN (divisao_segura abaixo
        # devolveria 0 e zeraria o CMS por engano se não tratássemos aqui).
        return cms_individual

    # Média do curral/pen para o intervalo [0, duracao_semanas]
    media_pen_pct_pv = divisao_segura(
        ka * duracao_semanas
        + kb / 2.0 * duracao_semanas**2
        + kc / 3.0 * duracao_semanas**3,
        duracao_semanas,
        0.0,
    )
    cms_pen = k.CMS_TRANSICAO_FATOR_PV * animal.peso_vivo_kg * media_pen_pct_pv / 100.0
    return min(cms_individual, cms_pen)


def _cms_hayirli(animal: AnimalEntrada) -> float:
    """NASEM 2021, Cap. 2 — vaca seca, equação de Hayirli et al. (2003)."""
    dias_gestacao = animal.dias_gestacao or 0
    diferenca = dias_gestacao - animal.duracao_gestacao_dias
    if diferenca < -21:
        ajuste_gestacao = 0.0
    else:
        # `diferenca` limitada antes do exp() — entradas absurdas (dias de
        # gestação muito além da duração normal) não devem estourar o
        # float; o ajuste tende a 0 ou satura, nunca lança OverflowError.
        expoente = k.CMS_HAYIRLI_GEST_EXP * limitar(diferenca, -700.0, 50.0)
        ajuste_gestacao = animal.peso_vivo_kg * (
            k.CMS_HAYIRLI_GEST_COEF * pow(2.718281828459045, expoente)
        ) / 100.0
    return animal.peso_vivo_kg * k.CMS_HAYIRLI_INTERCEPTO_PCT_PV / 100.0 + ajuste_gestacao


def calcular_cms(animal: AnimalEntrada, dieta: ConcentracoesDieta) -> ResultadoConsumo:
    """Bloco B — calcula o CMS segundo `animal.eq_cms`. Assume que a
    entrada já foi validada por `tipos.validar_entrada`."""
    eq = animal.eq_cms

    if eq == 0:
        cms = animal.cms_informado_kg_dia or 0.0
    elif eq == 2:
        cms = _cms_novilha_animal(animal)
    elif eq == 3:
        cms = _cms_novilha_dieta(animal, dieta)
    elif eq == 8:
        cms = _cms_lactante_animal(animal)
    elif eq == 9:
        cms = _cms_lactante_dieta(animal, dieta)
    elif eq == 10:
        cms = _cms_transicao(animal, dieta)
    elif eq == 11:
        cms = _cms_hayirli(animal)
    else:  # pragma: no cover — já validado em tipos.validar_entrada
        raise ValorInvalidoError(f"eq_cms não suportado na Fase 1: {eq}")

    cms = max(cms, 0.01)  # piso técnico: nunca zero/negativo, evita cascata de NaN

    peso_metabolico = animal.peso_vivo_kg ** 0.75
    return ResultadoConsumo(
        cms_kg_dia=cms,
        equacao_usada=eq,
        cms_pct_pv=divisao_segura(cms, animal.peso_vivo_kg, 0.0) * 100.0,
        cms_g_kg_pv075=divisao_segura(cms * 1000.0, peso_metabolico, 0.0),
    )


__all__ = ["ResultadoConsumo", "calcular_cms"]
