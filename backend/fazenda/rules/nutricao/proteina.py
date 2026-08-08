"""Bloco F — proteína metabolizável: suprimento, exigências de manutenção
(usadas para fechar o nitrogênio urinário ANTES do balanço de energia — ver
`__init__.avaliar_dieta`) e, na segunda parte, exigências finais com as
eficiências-alvo fixas e o balanço/leite permitido por PM.

Referências: NASEM (2021), Cap. 6.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import constantes as k
from .alimentos import ConcentracoesDieta
from .digestao import IngestoesDieta
from .energia import ComposicaoCorporal, ComposicaoGanho, ResultadoGestacao, perda_energia_gases
from .microbiana import ResultadoMicrobiana
from .tipos import AnimalEntrada
from .utilitarios import divisao_segura


@dataclass
class ExigenciasManutencao:
    """Exigências de proteína líquida de manutenção — descamação, endógena
    fecal e urinária (NASEM 2021, Cap. 6)."""

    descamacao_cp_g: float
    descamacao_np_g: float
    fecal_endogena_cp_g: float
    fecal_endogena_np_g: float
    urinaria_endogena_np_g: float


def calcular_exigencias_manutencao(
    animal: AnimalEntrada, dieta: ConcentracoesDieta, cms_kg_dia: float
) -> ExigenciasManutencao:
    descamacao_cp_g = k.DESCAMACAO_COEFICIENTE * animal.peso_vivo_kg ** k.DESCAMACAO_EXPOENTE_PV
    descamacao_np_g = descamacao_cp_g * k.NP_PARA_CP_CORPORAL

    fecal_endogena_cp_g = (
        k.FECAL_ENDOGENA_INTERCEPTO_G_POR_KG_CMS + k.FECAL_ENDOGENA_INCLINACAO_FDN * dieta.fdn_pct
    ) * cms_kg_dia
    fecal_endogena_np_g = fecal_endogena_cp_g * k.FECAL_ENDOGENA_FRACAO_PROTEINA_VERDADEIRA

    urinaria_endogena_np_g = (
        k.URINARIA_ENDOGENA_COEFICIENTE * animal.peso_vivo_kg * k.URINARIA_ENDOGENA_N_PARA_PB
    )

    return ExigenciasManutencao(
        descamacao_cp_g=descamacao_cp_g,
        descamacao_np_g=descamacao_np_g,
        fecal_endogena_cp_g=fecal_endogena_cp_g,
        fecal_endogena_np_g=fecal_endogena_np_g,
        urinaria_endogena_np_g=urinaria_endogena_np_g,
    )


@dataclass
class SuprimentoPM:
    pndr_digestivel_g: float
    proteina_microbiana_verdadeira_digestivel_g: float
    pm_fornecida_g: float


def calcular_suprimento_pm(
    ingestoes: IngestoesDieta, microbiana: ResultadoMicrobiana
) -> SuprimentoPM:
    pndr_digestivel_g = ingestoes.rup_digestivel_kg * 1000.0
    pm_microbiana_g = microbiana.proteina_microbiana_verdadeira_digestivel_g_dia
    return SuprimentoPM(
        pndr_digestivel_g=pndr_digestivel_g,
        proteina_microbiana_verdadeira_digestivel_g=pm_microbiana_g,
        pm_fornecida_g=pndr_digestivel_g + pm_microbiana_g,
    )


def nitrogenio_urinario_g_dia(
    *,
    ingestoes: IngestoesDieta,
    microbiana: ResultadoMicrobiana,
    manutencao: ExigenciasManutencao,
    leite_np_g: float,
    ganho_np_g: float,
    gestacao_cp_g: float,
) -> float:
    """Fecha o balanço de nitrogênio (fecal + retido + urinário = ingerido)
    para obter o N urinário — precisa vir ANTES da energia porque a energia
    perdida na urina depende dele (NASEM 2021, Cap. 3)."""
    rup_indigestivel_kg = max(0.0, ingestoes.rup_kg - ingestoes.rup_digestivel_kg)
    micp_bruta_kg = microbiana.proteina_microbiana_bruta_g_dia / 1000.0
    micp_digestivel_kg = micp_bruta_kg * k.MICROBIANA_DIGESTIBILIDADE_INTESTINAL_PCT / 100.0
    micp_indigestivel_kg = max(0.0, micp_bruta_kg - micp_digestivel_kg)

    fecal_cp_g = (
        rup_indigestivel_kg * 1000.0
        + micp_indigestivel_kg * 1000.0
        + manutencao.fecal_endogena_cp_g
    )

    leite_cp_g = divisao_segura(leite_np_g, 0.95, 0.0)
    ganho_cp_g = divisao_segura(ganho_np_g, k.NP_PARA_CP_CORPORAL, 0.0)

    cp_ingerida_g = ingestoes.pb_kg * 1000.0

    n_urinario_g = divisao_segura(
        cp_ingerida_g
        - fecal_cp_g
        - manutencao.descamacao_cp_g
        - manutencao.fecal_endogena_cp_g
        - leite_cp_g
        - ganho_cp_g
        - gestacao_cp_g,
        k.URINARIA_ENDOGENA_N_PARA_PB,
        0.0,
    )
    return max(n_urinario_g, 0.0)


@dataclass
class ExigenciasPM:
    eficiencia_mantenca: float
    eficiencia_gestacao: float
    eficiencia_ganho_estrutura: float
    eficiencia_ganho_reserva: float
    eficiencia_lactacao: float

    manutencao_g: float
    gestacao_g: float
    ganho_g: float
    leite_g: float
    total_g: float

    ajuste_novilha_aplicado: bool


def _eficiencia_ganho_novilha(razao_peso_vazio: float) -> float:
    """NASEM 2021, Cap. 6 — eficiência PM->PL de ganho para novilha em
    função da maturidade, com piso corrigido (o R tem esse piso invertido
    por engano — a fórmula original eleva o piso ao quadrado por engano de
    digitação; aqui o piso é aplicado corretamente: sempre > 0 e < o valor
    sem piso, nunca podendo ultrapassá-lo)."""
    valor = (0.64 - 0.3 * razao_peso_vazio) * k.NP_PARA_CP_CORPORAL
    return max(valor, k.EFICIENCIA_PM_NP_GANHO_PISO)


def calcular_exigencias_pm(
    *,
    animal: AnimalEntrada,
    manutencao: ExigenciasManutencao,
    ganho: ComposicaoGanho,
    gestacao: ResultadoGestacao,
    corpo: ComposicaoCorporal,
    leite_np_g: float,
    dieta: ConcentracoesDieta,
    ingestoes: IngestoesDieta,
    suprimento: SuprimentoPM,
) -> ExigenciasPM:
    """Bloco F, exigências finais — eficiências-alvo FIXAS (não a eficiência
    aparente calculada a partir do fornecimento real, o que zeraria o
    balanço por construção matemática)."""
    is_novilha = animal.estado_fisiologico == "novilha"

    eficiencia_mantenca = (
        k.EFICIENCIA_PM_NP_MANTENCA_JOVEM if is_novilha else k.EFICIENCIA_PM_NP_MANTENCA_ADULTO
    )
    eficiencia_gestacao = k.EFICIENCIA_PM_NP_GESTACAO
    eficiencia_lactacao = k.EFICIENCIA_PM_NP_GERAL

    if is_novilha and 0.12 < corpo.razao_peso_vazio < 1.0:
        eficiencia_ganho = _eficiencia_ganho_novilha(corpo.razao_peso_vazio)
    elif is_novilha:
        eficiencia_ganho = 0.60 * k.NP_PARA_CP_CORPORAL
    else:
        eficiencia_ganho = k.EFICIENCIA_PM_NP_GANHO_VACA_ADULTA

    manutencao_g = (
        divisao_segura(manutencao.fecal_endogena_np_g, eficiencia_mantenca, 0.0)
        + divisao_segura(manutencao.descamacao_np_g, eficiencia_mantenca, 0.0)
        + manutencao.urinaria_endogena_np_g
    )
    gestacao_g = divisao_segura(gestacao.proteina_liquida_g_dia, eficiencia_gestacao, 0.0)
    estrutura_g = divisao_segura(ganho.proteina_liquida_estrutura_g, eficiencia_ganho, 0.0)
    reserva_g = divisao_segura(ganho.proteina_liquida_reserva_g, eficiencia_ganho, 0.0)
    ganho_g = estrutura_g + reserva_g
    leite_g = divisao_segura(leite_np_g, eficiencia_lactacao, 0.0)

    total_g = manutencao_g + gestacao_g + ganho_g + leite_g

    ajuste_aplicado = False
    if is_novilha:
        razao_pv = divisao_segura(animal.peso_vivo_kg, animal.peso_maturo_kg, 0.0)
        gases = perda_energia_gases(
            estado_fisiologico=animal.estado_fisiologico,
            ge_mcal_dia=dieta.ge_mcal_kg * ingestoes.cms_kg_dia,
            cms_kg_dia=ingestoes.cms_kg_dia,
            fdn_pct_dieta=dieta.fdn_pct,
            ag_pct_dieta=dieta.ag_pct,
            ndf_digerida_pct_dieta=0.0,
            usa_monensina=animal.usa_monensina,
        )
        # EM aproximada — calculada só a partir da energia digestível de
        # base (ajustada por monensina se aplicável) e do desconto de
        # gases, SEM o desconto de energia perdida na urina: a este ponto
        # do cálculo o nitrogênio urinário (e portanto a EM final) ainda
        # não existe. Reproduzir essa aproximação é fidelidade ao método
        # publicado, não descuido — a EM final e completa só é usada no
        # Bloco G, depois.
        de_aprox = ingestoes.de_base_mcal
        if animal.usa_monensina:
            de_aprox *= k.MONENSINA_FATOR_AUMENTO_ED
        em_aproximada = de_aprox - gases.perda_mcal_dia

        minimo_pm_me = (53.0 - 25.0 * razao_pv) * em_aproximada
        if total_g < minimo_pm_me:
            diferenca_g = minimo_pm_me - total_g
            estrutura_g += diferenca_g
            eficiencia_ganho = divisao_segura(
                ganho.proteina_liquida_estrutura_g, estrutura_g, eficiencia_ganho
            )
            reserva_g = divisao_segura(ganho.proteina_liquida_reserva_g, eficiencia_ganho, 0.0)
            ganho_g = estrutura_g + reserva_g
            total_g = manutencao_g + gestacao_g + ganho_g + leite_g
            ajuste_aplicado = True

    return ExigenciasPM(
        eficiencia_mantenca=eficiencia_mantenca,
        eficiencia_gestacao=eficiencia_gestacao,
        eficiencia_ganho_estrutura=eficiencia_ganho,
        eficiencia_ganho_reserva=eficiencia_ganho,
        eficiencia_lactacao=eficiencia_lactacao,
        manutencao_g=manutencao_g,
        gestacao_g=gestacao_g,
        ganho_g=ganho_g,
        leite_g=leite_g,
        total_g=total_g,
        ajuste_novilha_aplicado=ajuste_aplicado,
    )


@dataclass
class ResultadoProteina:
    manutencao: ExigenciasManutencao
    suprimento: SuprimentoPM
    exigencias: ExigenciasPM
    balanco_g: float
    leite_permitido_por_pm_kg_dia: Optional[float]
    nitrogenio_urinario_g_dia: float


def calcular_proteina(
    *,
    animal: AnimalEntrada,
    dieta: ConcentracoesDieta,
    ingestoes: IngestoesDieta,
    microbiana: ResultadoMicrobiana,
    ganho: ComposicaoGanho,
    gestacao: ResultadoGestacao,
    corpo: ComposicaoCorporal,
    manutencao: ExigenciasManutencao,
    leite_np_g: float,
    n_urinario_g: float,
) -> ResultadoProteina:
    suprimento = calcular_suprimento_pm(ingestoes, microbiana)
    exigencias = calcular_exigencias_pm(
        animal=animal,
        manutencao=manutencao,
        ganho=ganho,
        gestacao=gestacao,
        corpo=corpo,
        leite_np_g=leite_np_g,
        dieta=dieta,
        ingestoes=ingestoes,
        suprimento=suprimento,
    )
    balanco_g = suprimento.pm_fornecida_g - exigencias.total_g

    leite_permitido: Optional[float] = None
    proteina_leite_pct = animal.proteina_leite_pct if animal.proteina_leite_pct else 3.2
    disponivel_para_leite_g = (
        suprimento.pm_fornecida_g - exigencias.total_g + exigencias.leite_g
    )
    np_leite_alow_g = disponivel_para_leite_g * exigencias.eficiencia_lactacao
    leite_permitido = divisao_segura(
        divisao_segura(np_leite_alow_g, proteina_leite_pct / 100.0, 0.0), 1000.0, 0.0
    )
    leite_permitido = max(leite_permitido, 0.0)

    return ResultadoProteina(
        manutencao=manutencao,
        suprimento=suprimento,
        exigencias=exigencias,
        balanco_g=balanco_g,
        leite_permitido_por_pm_kg_dia=leite_permitido,
        nitrogenio_urinario_g_dia=n_urinario_g,
    )


__all__ = [
    "ExigenciasManutencao",
    "SuprimentoPM",
    "ExigenciasPM",
    "ResultadoProteina",
    "calcular_exigencias_manutencao",
    "calcular_suprimento_pm",
    "nitrogenio_urinario_g_dia",
    "calcular_exigencias_pm",
    "calcular_proteina",
]
