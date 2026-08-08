"""Bloco G — energia (GE→ED→EM→EL), mantença, gestação, ganho, lactação e
balanço energético. Também expõe a composição corporal do ganho (usada por
`proteina.py` para as exigências de proteína líquida de ganho, que precisam
ser calculadas antes do balanço de nitrogênio urinário — ver a ordem de
`__init__.avaliar_dieta`) e a curva de crescimento do útero gravídico (usada
tanto pela proteína quanto pela energia de gestação).

Referências: NASEM (2021), Cap. 3.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from . import constantes as k
from .tipos import AnimalEntrada
from .utilitarios import divisao_segura

# ---------------------------------------------------------------------------
# Composição corporal (peso de vazio, gut fill) — usada por gestação, ganho
# e pela exigência de proteína metabolizável da novilha.
# ---------------------------------------------------------------------------


@dataclass
class ComposicaoCorporal:
    fracao_conteudo_gastrintestinal: float
    peso_vazio_kg: float
    peso_maturo_vazio_kg: float
    razao_peso_vazio: float  # peso_vazio / peso_maturo_vazio


def composicao_corporal(animal: AnimalEntrada) -> ComposicaoCorporal:
    """NASEM 2021, Cap. 11 — fração do peso vivo ocupada pelo conteúdo
    gastrintestinal (gut fill), usada para converter peso vivo em peso de
    corpo vazio (EBW)."""
    if animal.estado_fisiologico == "novilha":
        fracao = 0.15
    else:  # vaca_lactante / vaca_seca, paridade > 0
        fracao = 0.18
    peso_vazio = animal.peso_vivo_kg * (1.0 - fracao)
    peso_maturo_vazio = animal.peso_maturo_kg * (1.0 - 0.18)
    return ComposicaoCorporal(
        fracao_conteudo_gastrintestinal=fracao,
        peso_vazio_kg=peso_vazio,
        peso_maturo_vazio_kg=peso_maturo_vazio,
        razao_peso_vazio=divisao_segura(peso_vazio, peso_maturo_vazio, 0.0),
    )


# ---------------------------------------------------------------------------
# Composição do ganho (estrutura + reserva) — gordura/proteína, energia
# retida e as eficiências ME->RE usadas tanto no balanço de PM quanto no de
# energia.
# ---------------------------------------------------------------------------


@dataclass
class ComposicaoGanho:
    gordura_estrutura_kg: float
    proteina_liquida_estrutura_kg: float
    gordura_reserva_kg: float
    proteina_liquida_reserva_kg: float
    gordura_total_kg: float
    proteina_liquida_total_kg: float
    proteina_liquida_estrutura_g: float
    proteina_liquida_reserva_g: float
    proteina_liquida_total_g: float
    energia_retida_estrutura_mcal: float
    energia_retida_reserva_mcal: float
    energia_retida_total_mcal: float
    eficiencia_em_estrutura: float
    eficiencia_em_reserva: float
    em_para_ganho_mcal: float
    ganho_alvo_total_kg: float


def composicao_ganho(animal: AnimalEntrada) -> ComposicaoGanho:
    """NASEM 2021, Cap. 3 — composição do ganho de peso vivo (estrutura e
    reserva corporal) por maturidade, e energia retida no ganho."""
    razao_pv = divisao_segura(animal.peso_vivo_kg, animal.peso_maturo_kg, 0.0)

    frm_gain = animal.ganho_estrutura_kg_dia
    rsrv_gain = animal.ganho_reserva_kg_dia
    ganho_total = frm_gain + rsrv_gain

    fracao_gordura_estrutura = k.GORDURA_GANHO_ESTRUTURA_INTERCEPTO + k.GORDURA_GANHO_ESTRUTURA_INCLINACAO * razao_pv
    fracao_proteina_estrutura = (
        k.PROTEINA_GANHO_ESTRUTURA_INTERCEPTO
        - k.PROTEINA_GANHO_ESTRUTURA_INCLINACAO_PV_PVMADURO * razao_pv
    ) * k.NP_PARA_CP_CORPORAL

    gordura_estrutura_kg = fracao_gordura_estrutura * frm_gain
    proteina_estrutura_kg = fracao_proteina_estrutura * frm_gain

    gordura_reserva_kg = k.GORDURA_GANHO_RESERVA_FRACAO * rsrv_gain
    fracao_proteina_reserva = k.PROTEINA_GANHO_RESERVA_FRACAO_CP * k.NP_PARA_CP_CORPORAL
    proteina_reserva_kg = fracao_proteina_reserva * rsrv_gain

    gordura_total = gordura_estrutura_kg + gordura_reserva_kg
    proteina_total = proteina_estrutura_kg + proteina_reserva_kg

    re_estrutura = (
        k.ENERGIA_RETIDA_COEF_GORDURA_MCAL_KG * gordura_estrutura_kg
        + k.ENERGIA_RETIDA_COEF_PROTEINA_MCAL_KG * divisao_segura(proteina_estrutura_kg, k.NP_PARA_CP_CORPORAL, 0.0)
    )
    re_reserva = (
        k.ENERGIA_RETIDA_COEF_GORDURA_MCAL_KG * gordura_reserva_kg
        + k.ENERGIA_RETIDA_COEF_PROTEINA_MCAL_KG * divisao_segura(proteina_reserva_kg, k.NP_PARA_CP_CORPORAL, 0.0)
    )
    re_total = re_estrutura + re_reserva

    eficiencia_reserva = k.EFICIENCIA_EM_GANHO_RESERVA_PADRAO
    if (animal.producao_leite_kg_dia or 0.0) > 0 and rsrv_gain > 0:
        eficiencia_reserva = k.EFICIENCIA_EM_GANHO_RESERVA_LACTANTE_GANHANDO
    elif rsrv_gain <= 0:
        eficiencia_reserva = k.EFICIENCIA_EM_GANHO_RESERVA_PERDENDO

    eficiencia_estrutura = k.EFICIENCIA_EM_GANHO_ESTRUTURA

    em_estrutura = divisao_segura(re_estrutura, eficiencia_estrutura, 0.0)
    em_reserva = divisao_segura(re_reserva, eficiencia_reserva, 0.0)

    return ComposicaoGanho(
        gordura_estrutura_kg=gordura_estrutura_kg,
        proteina_liquida_estrutura_kg=proteina_estrutura_kg,
        gordura_reserva_kg=gordura_reserva_kg,
        proteina_liquida_reserva_kg=proteina_reserva_kg,
        gordura_total_kg=gordura_total,
        proteina_liquida_total_kg=proteina_total,
        proteina_liquida_estrutura_g=proteina_estrutura_kg * 1000.0,
        proteina_liquida_reserva_g=proteina_reserva_kg * 1000.0,
        proteina_liquida_total_g=proteina_total * 1000.0,
        energia_retida_estrutura_mcal=re_estrutura,
        energia_retida_reserva_mcal=re_reserva,
        energia_retida_total_mcal=re_total,
        eficiencia_em_estrutura=eficiencia_estrutura,
        eficiencia_em_reserva=eficiencia_reserva,
        em_para_ganho_mcal=em_estrutura + em_reserva,
        ganho_alvo_total_kg=ganho_total,
    )


# ---------------------------------------------------------------------------
# Gestação — curva de crescimento do útero gravídico
# ---------------------------------------------------------------------------


@dataclass
class ResultadoGestacao:
    gestando: bool
    peso_utero_gravido_kg: float
    ganho_peso_utero_kg_dia: float
    energia_retida_mcal_dia: float
    proteina_liquida_g_dia: float
    proteina_bruta_g_dia: float


def calcular_gestacao(animal: AnimalEntrada) -> ResultadoGestacao:
    """NASEM 2021, Cap. 3 — peso do útero gravídico por função de
    crescimento exponencial com decaimento ao longo da gestação (modelo de
    Koong et al., 1975, ajustado por Bell, 1995 / House & Bell, 1993)."""
    dias_gestacao = animal.dias_gestacao or 0
    duracao = animal.duracao_gestacao_dias
    gestando = 0 < dias_gestacao <= duracao
    del_dias = animal.del_dias or 0
    involuindo = (not gestando) and 0 < del_dias < 100

    uter_wtpart = animal.peso_bezerro_nascer_kg * k.PESO_UTERO_NAO_GRAVIDO_POR_PESO_BEZERRO
    gruter_wtpart = animal.peso_bezerro_nascer_kg * k.PESO_UTERO_GRAVIDO_POR_PESO_BEZERRO

    idade_dias = animal.idade_dias if animal.idade_dias is not None else 900
    uter_wt = 0.0 if idade_dias < 240 else k.UTERO_PESO_BASE_NAO_GESTANTE_KG

    if gestando:
        expoente = -(
            k.UTERO_NAO_GRAVIDO_KSYN - k.UTERO_NAO_GRAVIDO_KSYN_DECAY * dias_gestacao
        ) * (duracao - dias_gestacao)
        uter_wt = uter_wtpart * math.exp(expoente)
    elif involuindo:
        uter_wt = (
            (uter_wtpart - k.UTERO_PESO_BASE_NAO_GESTANTE_KG)
            * math.exp(-k.UTERO_NAO_GRAVIDO_KDEG_INVOLUCAO * del_dias)
        ) + k.UTERO_PESO_BASE_NAO_GESTANTE_KG

    if animal.paridade > 0 and uter_wt < k.UTERO_PESO_BASE_NAO_GESTANTE_KG:
        uter_wt = k.UTERO_PESO_BASE_NAO_GESTANTE_KG

    gruter_wt = uter_wt
    if gestando:
        expoente2 = -(
            k.UTERO_GRAVIDO_KSYN - k.UTERO_GRAVIDO_KSYN_DECAY * dias_gestacao
        ) * (duracao - dias_gestacao)
        gruter_wt = max(gruter_wtpart * math.exp(expoente2), uter_wt)

    uter_bwgain = 0.0
    if gestando:
        uter_bwgain = (
            k.UTERO_NAO_GRAVIDO_KSYN - k.UTERO_NAO_GRAVIDO_KSYN_DECAY * dias_gestacao
        ) * uter_wt
    elif involuindo:
        uter_bwgain = -k.UTERO_NAO_GRAVIDO_KDEG_INVOLUCAO * uter_wt

    gruter_bwgain = 0.0
    if gestando:
        gruter_bwgain = (
            k.UTERO_GRAVIDO_KSYN - k.UTERO_GRAVIDO_KSYN_DECAY * dias_gestacao
        ) * gruter_wt
    elif involuindo:
        gruter_bwgain = uter_bwgain

    energia_retida = gruter_bwgain * k.ENERGIA_LIQUIDA_POR_KG_UTERO_GRAVIDO_MCAL
    proteina_bruta_g = gruter_bwgain * k.PROTEINA_BRUTA_POR_KG_UTERO_GRAVIDO_KG * 1000.0
    proteina_liquida_g = proteina_bruta_g * k.NP_PARA_CP_CORPORAL

    return ResultadoGestacao(
        gestando=gestando,
        peso_utero_gravido_kg=gruter_wt,
        ganho_peso_utero_kg_dia=gruter_bwgain,
        energia_retida_mcal_dia=energia_retida,
        proteina_liquida_g_dia=proteina_liquida_g,
        proteina_bruta_g_dia=proteina_bruta_g,
    )


# ---------------------------------------------------------------------------
# Perda de energia em gases (metano)
# ---------------------------------------------------------------------------


@dataclass
class ResultadoPerdaGases:
    perda_mcal_dia: float
    usa_parametrizacao_alternativa: bool  # True para novilha/vaca seca


def perda_energia_gases(
    *,
    estado_fisiologico: str,
    ge_mcal_dia: float,
    cms_kg_dia: float,
    fdn_pct_dieta: float,
    ag_pct_dieta: float,
    ndf_digerida_pct_dieta: float,
    usa_monensina: bool,
) -> ResultadoPerdaGases:
    """Perda de energia em gases (metano) — a parametrização que entra no
    balanço de energia metabolizável do software de referência (a
    literatura publica uma segunda parametrização, usada só para exibição
    em outras telas do software original, com sinais e um coeficiente
    diferentes; não a implementamos aqui pois não entra neste balanço)."""
    usa_alternativa = False
    if estado_fisiologico == "novilha":
        valor = (
            k.GASES_NOVILHA_INTERCEPTO
            + k.GASES_NOVILHA_COEF_EB * ge_mcal_dia
            + k.GASES_NOVILHA_COEF_FDN * fdn_pct_dieta
        )
        usa_alternativa = True
    elif estado_fisiologico == "vaca_seca":
        valor = (
            k.GASES_VACA_SECA_INTERCEPTO
            + k.GASES_VACA_SECA_COEF_EB * ge_mcal_dia
            + k.GASES_VACA_SECA_COEF_GORDURA * ag_pct_dieta
        )
        usa_alternativa = True
    else:  # vaca_lactante
        valor = (
            k.GASES_LACTANTE_COEF_CMS * cms_kg_dia
            + k.GASES_LACTANTE_COEF_AG * ag_pct_dieta
            + k.GASES_LACTANTE_COEF_FDN_DIGERIDA * ndf_digerida_pct_dieta
        )

    if usa_monensina:
        valor *= k.MONENSINA_FATOR_REDUCAO_METANO

    return ResultadoPerdaGases(perda_mcal_dia=max(valor, 0.0), usa_parametrizacao_alternativa=usa_alternativa)


# ---------------------------------------------------------------------------
# Bloco G completo
# ---------------------------------------------------------------------------


@dataclass
class ResultadoEnergia:
    energia_bruta_mcal: float
    energia_digestivel_mcal: float
    energia_metabolizavel_mcal: float
    energia_liquida_mcal: float
    energia_digestivel_concentracao_mcal_kg: float
    energia_metabolizavel_concentracao_mcal_kg: float
    energia_liquida_concentracao_mcal_kg: float

    perda_gases_mcal: float
    perda_urina_mcal: float

    nel_mantenca_mcal: float
    em_mantenca_mcal: float
    eficiencia_em_el_mantenca: float

    em_gestacao_mcal: float
    nel_gestacao_mcal: float

    em_ganho_mcal: float
    nel_ganho_mcal: float

    nel_leite_concentracao_mcal_kg: float
    nel_leite_mcal: float
    em_leite_mcal: float

    em_uso_total_mcal: float
    nel_uso_total_mcal: float
    balanco_em_mcal: float
    balanco_nel_mcal: float

    leite_permitido_por_el_kg_dia: float
    ganho_permitido_por_el_kg_dia: Optional[float]
    dias_para_1_ponto_ecc: Optional[float]

    aviso_metano_alternativo: bool


def calcular_energia(
    *,
    animal: AnimalEntrada,
    ge_mcal_dia: float,
    de_base_mcal_dia: float,
    cms_kg_dia: float,
    fdn_pct_dieta: float,
    ag_pct_dieta: float,
    ndf_digerida_pct_dieta: float,
    nitrogenio_urinario_g_dia: float,
    ganho: ComposicaoGanho,
    gestacao: ResultadoGestacao,
) -> ResultadoEnergia:
    """Bloco G completo — ED->EM->EL, mantença, gestação, ganho, lactação e
    balanço (NASEM 2021, Cap. 3)."""
    is_novilha = animal.estado_fisiologico == "novilha"

    de_mcal = de_base_mcal_dia
    if animal.usa_monensina:
        de_mcal *= k.MONENSINA_FATOR_AUMENTO_ED

    gases = perda_energia_gases(
        estado_fisiologico=animal.estado_fisiologico,
        ge_mcal_dia=ge_mcal_dia,
        cms_kg_dia=cms_kg_dia,
        fdn_pct_dieta=fdn_pct_dieta,
        ag_pct_dieta=ag_pct_dieta,
        ndf_digerida_pct_dieta=ndf_digerida_pct_dieta,
        usa_monensina=animal.usa_monensina,
    )
    perda_urina_mcal = k.ENERGIA_PERDIDA_URINA_MCAL_POR_G_N * nitrogenio_urinario_g_dia

    em_mcal = de_mcal - gases.perda_mcal_dia - perda_urina_mcal
    el_mcal = em_mcal * k.EFICIENCIA_EM_EL_LACTACAO  # energia líquida total = EM × 0,66, base única de referência

    # Mantença — NASEM 2021 soma ao NEm de base parcelas de estresse
    # térmico e custo de locomoção (deslocamento até a sala de ordenha,
    # desnível), mas essas parcelas só têm efeito não-nulo para animais
    # muito jovens (bezerro/novilha em condições extremas), fora do escopo
    # de vaca/novilha adulta da Fase 1 — por isso omitidas aqui (equivalem
    # a 0 para os estados fisiológicos cobertos nesta fase).
    km = k.EFICIENCIA_EM_EL_MANTENCA_NOVILHA if is_novilha else k.EFICIENCIA_EM_EL_MANTENCA_VACA
    nel_mantenca = k.MANTENCA_NEL_COEFICIENTE * animal.peso_vivo_kg ** k.MANTENCA_NEL_EXPOENTE_PV
    em_mantenca = divisao_segura(nel_mantenca, km, 0.0)

    # Gestação
    em_gestacao = divisao_segura(
        gestacao.energia_retida_mcal_dia, k.EFICIENCIA_EM_ENERGIA_GESTACAO, 0.0
    )
    nel_gestacao = em_gestacao * k.EFICIENCIA_EM_EL_LACTACAO

    # Ganho
    em_ganho = ganho.em_para_ganho_mcal
    nel_ganho = ganho.energia_retida_total_mcal

    # Lactação
    producao = animal.producao_leite_kg_dia or 0.0
    if animal.gordura_leite_pct is not None and animal.proteina_leite_pct is not None:
        nel_leite_conc = (
            k.NEL_LEITE_COEF_GORDURA * animal.gordura_leite_pct / 100.0
            + k.NEL_LEITE_COEF_PROTEINA * animal.proteina_leite_pct / 100.0
            + k.NEL_LEITE_COEF_LACTOSE * animal.lactose_leite_pct / 100.0
        )
    else:
        gordura = animal.gordura_leite_pct if animal.gordura_leite_pct is not None else 3.8
        nel_leite_conc = k.TYRRELL_REID_INTERCEPTO + k.TYRRELL_REID_COEF_GORDURA * gordura / 100.0
    nel_leite_mcal = nel_leite_conc * producao
    em_leite_mcal = divisao_segura(nel_leite_mcal, k.EFICIENCIA_EM_EL_LACTACAO, 0.0)

    em_uso_total = em_mantenca + em_ganho + em_gestacao + em_leite_mcal
    nel_uso_total = nel_mantenca + nel_ganho + gestacao.energia_retida_mcal_dia + nel_leite_mcal

    balanco_em = em_mcal - em_uso_total
    balanco_nel = balanco_em * k.EFICIENCIA_EM_EL_LACTACAO

    # Leite permitido por EL (energia alocável à lactação após mantença,
    # gestação e ganho)
    em_disponivel_leite = em_mcal - em_mantenca - em_gestacao - em_ganho
    leite_permitido = divisao_segura(
        em_disponivel_leite * k.EFICIENCIA_EM_EL_LACTACAO, nel_leite_conc, 0.0
    )
    leite_permitido = max(leite_permitido, 0.0)

    # Ganho permitido por EL e dias para variar 1 ponto de ECC — indefinidos
    # (None) quando não há ganho-alvo nenhum (estrutura + reserva == 0):
    # a mistura estrutura/reserva usada para ponderar a eficiência marginal
    # de conversão não está definida nesse caso (seria uma divisão 0/0).
    ganho_permitido: Optional[float] = None
    dias_1_ecc: Optional[float] = None
    if ganho.ganho_alvo_total_kg != 0.0:
        soma_ne_ganho = ganho.energia_retida_estrutura_mcal + ganho.energia_retida_reserva_mcal
        kg_medio = divisao_segura(
            ganho.eficiencia_em_estrutura * ganho.energia_retida_estrutura_mcal
            + ganho.eficiencia_em_reserva * ganho.energia_retida_reserva_mcal,
            soma_ne_ganho,
            None,
        )
        em_disponivel_ganho = em_mcal - em_mantenca - em_gestacao - em_leite_mcal
        ne_por_kg_ganho = divisao_segura(
            ganho.energia_retida_total_mcal, ganho.ganho_alvo_total_kg, None
        )
        if kg_medio is not None and ne_por_kg_ganho is not None:
            ganho_permitido = divisao_segura(
                em_disponivel_ganho * kg_medio, ne_por_kg_ganho, None
            )
        peso_por_ponto_ecc = k.FRACAO_PV_POR_PONTO_ECC * animal.peso_vivo_kg
        dias_1_ecc = divisao_segura(peso_por_ponto_ecc, ganho_permitido, None)

    return ResultadoEnergia(
        energia_bruta_mcal=ge_mcal_dia,
        energia_digestivel_mcal=de_mcal,
        energia_metabolizavel_mcal=em_mcal,
        energia_liquida_mcal=el_mcal,
        energia_digestivel_concentracao_mcal_kg=divisao_segura(de_mcal, cms_kg_dia, 0.0),
        energia_metabolizavel_concentracao_mcal_kg=divisao_segura(em_mcal, cms_kg_dia, 0.0),
        energia_liquida_concentracao_mcal_kg=divisao_segura(el_mcal, cms_kg_dia, 0.0),
        perda_gases_mcal=gases.perda_mcal_dia,
        perda_urina_mcal=perda_urina_mcal,
        nel_mantenca_mcal=nel_mantenca,
        em_mantenca_mcal=em_mantenca,
        eficiencia_em_el_mantenca=km,
        em_gestacao_mcal=em_gestacao,
        nel_gestacao_mcal=nel_gestacao,
        em_ganho_mcal=em_ganho,
        nel_ganho_mcal=nel_ganho,
        nel_leite_concentracao_mcal_kg=nel_leite_conc,
        nel_leite_mcal=nel_leite_mcal,
        em_leite_mcal=em_leite_mcal,
        em_uso_total_mcal=em_uso_total,
        nel_uso_total_mcal=nel_uso_total,
        balanco_em_mcal=balanco_em,
        balanco_nel_mcal=balanco_nel,
        leite_permitido_por_el_kg_dia=leite_permitido,
        ganho_permitido_por_el_kg_dia=ganho_permitido,
        dias_para_1_ponto_ecc=dias_1_ecc,
        aviso_metano_alternativo=gases.usa_parametrizacao_alternativa,
    )


__all__ = [
    "ComposicaoCorporal",
    "ComposicaoGanho",
    "ResultadoGestacao",
    "ResultadoPerdaGases",
    "ResultadoEnergia",
    "composicao_corporal",
    "composicao_ganho",
    "calcular_gestacao",
    "perda_energia_gases",
    "calcular_energia",
]
