"""Bloco A (perfil de cada ingrediente) e Bloco C (concentrações da dieta).

Nenhuma função deste módulo depende do consumo de matéria seca (CMS): tudo
aqui é expresso como percentual da matéria seca do próprio ingrediente (Bloco
A) ou como média ponderada pelas proporções normalizadas da dieta (Bloco C).
Isso é o que evita a aparente circularidade CMS↔FDN — a concentração de FDN
da dieta não depende de quanto o animal come, só da mistura de ingredientes.

Referências: NASEM (2021), Cap. 3 (energia bruta e digestível de base) e
Cap. 6 (fracionamento de proteína em frações A/B/C e PDR/PNDR).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import constantes as k
from .tipos import IngredienteEntrada
from .utilitarios import divisao_segura, limitar


@dataclass
class PerfilIngrediente:
    """Perfil de um ingrediente, tudo em % da MS do próprio ingrediente
    (ou Mcal/kg de MS do ingrediente), calculado sem depender do CMS."""

    nome: str
    categoria_nasem: str
    conc_pct: float
    proporcao_normalizada: float

    ms_pct: float
    pb_pct: float
    fdn_pct: float
    fda_pct: float
    lignina_pct: float
    amido_pct: float
    acucares_pct: float
    ee_pct: float
    ag_pct: float
    cinzas_pct: float
    dndf48_fdn_pct: float

    npncp_pct_dm: float  # NNP expresso como equivalente-PB, % da MS
    proteina_verdadeira_pct_dm: float
    fa_hidratada_pct_dm: float
    cnf_pct_dm: float
    materia_organica_residual_pct_dm: float

    rup_pct_cp: float
    rdp_pct_cp: float
    rup_pct_dm: float
    rdp_pct_dm: float
    rup_digestivel_pct_dm: float  # PNDR intestinalmente digestível, % da MS

    ge_mcal_kg: float
    de_base_mcal_kg: float

    ndf_dc_lignina_pct: float  # digestibilidade de trato total da FDN, base lignina
    ndf_digerida_base_pct_dm: float  # FDN digerida (base), % da MS do ingrediente
    amido_digerido_base_pct_dm: float  # amido digerido (base), % da MS do ingrediente

    forragem_pct: float  # 100 - conc_pct
    forragem_ndf_pct_dm: float
    forragem_umida_pct_dm: float  # % de forragem úmida, quando aplicável

    ca_pct: float
    p_pct: float
    p_inorg_p_pct: float
    p_org_p_pct: float
    mg_pct: float
    k_pct: float
    na_pct: float
    cl_pct: float
    s_pct: float

    abs_ca: float
    abs_p_total: float
    abs_mg: float
    abs_na: float
    abs_cl: float
    abs_k: float

    ca_absorvido_pct_dm: float
    p_absorvido_pct_dm: float
    na_absorvido_pct_dm: float
    cl_absorvido_pct_dm: float
    k_absorvido_pct_dm: float

    custo_kg_mn: float
    ms_fracao: float = field(init=False)

    def __post_init__(self) -> None:
        self.ms_fracao = self.ms_pct / 100.0


def _dndf48_padrao(conc_pct: float) -> float:
    """Preenchimento-padrão de DNDF48 quando não informado (NASEM 2021,
    Cap. 2/3) — 48,3% da FDN para volumoso (conc_pct < 100), 65% para
    concentrado puro (conc_pct == 100). Sempre roda na Fase 1; o que fica de
    fora é o ajuste de digestibilidade por DNDF48 medido (Fase 3)."""
    if conc_pct >= 100:
        return k.DNDF48_PADRAO_CONCENTRADO_PCT_FDN
    return k.DNDF48_PADRAO_VOLUMOSO_PCT_FDN


def _rup_pct_cp(
    pb_a_pct: float,
    pb_b_pct: float,
    pb_c_pct: float,
    nnp_pb_pct: float,
    kd_pb_b_pct_h: float,
    conc_pct: float,
) -> float:
    """PNDR como % da PB do ingrediente (NASEM 2021, Cap. 6) — fracionamento
    A/B/C com passagem ruminal dependente do balanço volumoso/concentrado do
    próprio ingrediente."""
    fracao_for = (100.0 - conc_pct) / 100.0
    fracao_conc = conc_pct / 100.0
    kp_for = k.TAXA_PASSAGEM_VOLUMOSO_PCT_H
    kp_conc = k.TAXA_PASSAGEM_CONCENTRADO_PCT_H
    kd = kd_pb_b_pct_h

    rupb_pct_cp = pb_b_pct * (
        fracao_for * divisao_segura(kp_for, kd + kp_for, 0.0)
        + fracao_conc * divisao_segura(kp_conc, kd + kp_conc, 0.0)
    )
    parte_a = (pb_a_pct - nnp_pb_pct) * k.FRACAO_A_QUE_ESCAPA_DEGRADACAO
    intercepto_pct = (
        k.INTERCEPTO_PNDR_KG_DIA / k.PB_REFERENCIA_INTERCEPTO_PNDR_KG_DIA * 100.0
    )
    return parte_a + rupb_pct_cp + pb_c_pct + intercepto_pct


def _digestibilidade_ndf_base_lignina(fdn_pct: float, lignina_pct: float) -> float:
    """Digestibilidade de trato total da FDN estimada a partir da lignina
    (NASEM 2021, Cap. 3) — usada como base sempre na Fase 1 (o ajuste por
    DNDF48 medido in vitro é Fase 3, ver `usa_dndf48`)."""
    if fdn_pct <= 0:
        return 0.0
    razao_lig = limitar(divisao_segura(lignina_pct, fdn_pct, 0.0), 0.0, 1.0)
    valor = 0.75 * (fdn_pct - lignina_pct) * (1 - razao_lig ** 0.667) / fdn_pct * 100.0
    return valor if valor == valor else 0.0  # guarda extra contra nan


def _energia_bruta_mcal_kg(
    pb_pct: float, ag_pct: float, amido_pct: float, fdn_pct: float, cinzas_pct: float
) -> float:
    resto_pct = 100.0 - pb_pct - ag_pct - amido_pct - fdn_pct - cinzas_pct
    return (
        pb_pct / 100.0 * k.ENERGIA_BRUTA_PROTEINA_BRUTA
        + ag_pct / 100.0 * k.ENERGIA_BRUTA_ACIDOS_GRAXOS
        + amido_pct / 100.0 * k.ENERGIA_BRUTA_AMIDO
        + fdn_pct / 100.0 * k.ENERGIA_BRUTA_FDN
        + resto_pct / 100.0 * k.ENERGIA_BRUTA_MATERIA_ORGANICA_RESIDUAL
    )


def _energia_digestivel_base_mcal_kg(
    *,
    categoria_nasem: str,
    pb_pct: float,
    fdn_pct: float,
    lignina_pct: float,
    amido_pct: float,
    ag_pct: float,
    cinzas_pct: float,
    npncp_pct_dm: float,
    dig_amido_pct: float,
    dig_ag_pct: float,
    dig_pndr_pct: float,
    rup_pct_dm: float,
    rdp_pct_dm: float,
    fator_hidratacao: float,
) -> float:
    """Energia digestível de base (NASEM 2021, Cap. 3, eq. 3-XX de composição
    padrão) — só a exceção de categoria muda a forma da equação."""
    del fator_hidratacao  # reservado para exceções futuras (Fase 2/3); não usado nesta equação

    if categoria_nasem == "Vitaminico/mineral":
        if npncp_pct_dm > 0:
            return pb_pct * 0.089 - 0.318
        return 0.0

    if categoria_nasem == "Suplemento de gordura":
        return (
            ag_pct * dig_ag_pct / 100.0 * 0.094
            + (100.0 - cinzas_pct - (ag_pct / 1.06) * 0.96) * 0.043
            - 0.318
        )

    if categoria_nasem == "Suplemento de acido graxo":
        return ag_pct * dig_ag_pct / 100.0 * 0.094 - 0.318

    if categoria_nasem == "Acucar/alcool de acucar":
        return (100.0 - cinzas_pct) * 0.04 * 0.96 - 0.318

    if categoria_nasem == "Proteina animal":
        resto = max(0.0, 100.0 - ag_pct - pb_pct - cinzas_pct)
        return (
            0.73 * ag_pct / 100.0 * k.ENERGIA_BRUTA_ACIDOS_GRAXOS
            + (rdp_pct_dm + rup_pct_dm * dig_pndr_pct / 100.0) * 0.056
            + resto / 100.0 * k.ENERGIA_BRUTA_MATERIA_ORGANICA_RESIDUAL * 0.96
            - 0.318
        )

    # Equação padrão (Forragem, Pastagem, Concentrado energetico/proteico,
    # Leite/sucedaneo, Outros)
    termo_fdn = 0.75 * (fdn_pct - lignina_pct) * (
        1 - limitar(divisao_segura(lignina_pct, fdn_pct, 0.0), 0.0, 1.0) ** 0.667
    ) * 0.042 if fdn_pct > 0 else 0.0
    termo_amido = amido_pct * dig_amido_pct / 100.0 * 0.0423
    termo_ag = ag_pct * dig_ag_pct / 100.0 * 0.094
    proteina_verdadeira_dm = pb_pct - (npncp_pct_dm - npncp_pct_dm / 2.81)
    termo_rom = (
        100.0 - (ag_pct / 1.06) - cinzas_pct - fdn_pct - amido_pct - proteina_verdadeira_dm
    ) * 0.96 * 0.04
    termo_proteina = (
        (pb_pct - rup_pct_dm) + rup_pct_dm * dig_pndr_pct / 100.0 - npncp_pct_dm
    ) * 0.0565
    termo_npn = npncp_pct_dm * 0.0089
    return termo_fdn + termo_amido + termo_ag + termo_rom + termo_proteina + termo_npn - 0.318


def perfil_ingrediente(ingrediente: IngredienteEntrada, proporcao_normalizada: float) -> PerfilIngrediente:
    """Calcula o Bloco A completo para um ingrediente já preenchido com o
    template da categoria (ver `biblioteca.preencher_com_template`)."""
    pb_pct = ingrediente.pb_pct or 0.0
    fdn_pct = ingrediente.fdn_pct or 0.0
    fda_pct = ingrediente.fda_pct or 0.0
    lignina_pct = ingrediente.lignina_pct or 0.0
    amido_pct = ingrediente.amido_pct or 0.0
    acucares_pct = ingrediente.acucares_pct or 0.0
    ee_pct = ingrediente.ee_pct or 0.0
    ag_pct = ingrediente.ag_pct or 0.0
    cinzas_pct = ingrediente.cinzas_pct or 0.0
    ms_pct = ingrediente.ms_pct or 100.0
    conc_pct = ingrediente.conc_pct or 0.0

    dndf48 = ingrediente.dndf48_fdn_pct
    if not dndf48:
        dndf48 = _dndf48_padrao(conc_pct)

    fator_hidratacao = (
        1.0 if ingrediente.categoria_nasem == "Suplemento de acido graxo"
        else k.FATOR_HIDRATACAO_TRIACILGLICEROL
    )

    nnp_pb_pct = ingrediente.nnp_pb_pct or 0.0
    npncp_pct_dm = pb_pct * nnp_pb_pct / 100.0
    proteina_verdadeira_pct_dm = pb_pct - npncp_pct_dm
    fa_hidratada_pct_dm = ag_pct * fator_hidratacao
    npn_massa_pct_dm = npncp_pct_dm / 2.81

    cnf_pct_dm = max(
        0.0,
        100.0
        - cinzas_pct
        - fdn_pct
        - proteina_verdadeira_pct_dm
        - npn_massa_pct_dm
        - fa_hidratada_pct_dm,
    )
    rom_pct_dm = (
        100.0
        - cinzas_pct
        - fdn_pct
        - amido_pct
        - fa_hidratada_pct_dm
        - proteina_verdadeira_pct_dm
        - npn_massa_pct_dm
    )

    pb_a_pct = ingrediente.pb_a_pct if ingrediente.pb_a_pct is not None else 0.0
    pb_b_pct = ingrediente.pb_b_pct if ingrediente.pb_b_pct is not None else 0.0
    pb_c_pct = ingrediente.pb_c_pct if ingrediente.pb_c_pct is not None else 0.0
    kd_pb_b = ingrediente.kd_pb_b_pct_h if ingrediente.kd_pb_b_pct_h else 0.0

    rup_pct_cp = _rup_pct_cp(pb_a_pct, pb_b_pct, pb_c_pct, nnp_pb_pct, kd_pb_b, conc_pct)
    rup_pct_cp = limitar(rup_pct_cp, 0.0, 100.0)
    rdp_pct_cp = 100.0 - rup_pct_cp
    rup_pct_dm = rup_pct_cp / 100.0 * pb_pct
    rdp_pct_dm = pb_pct - rup_pct_dm

    dig_pndr_pct = ingrediente.dig_pndr_pct if ingrediente.dig_pndr_pct is not None else 0.0
    rup_digestivel_pct_dm = rup_pct_dm * dig_pndr_pct / 100.0

    dig_amido_pct = ingrediente.dig_amido_pct if ingrediente.dig_amido_pct is not None else 0.0
    dig_ag_pct = ingrediente.dig_ag_pct if ingrediente.dig_ag_pct is not None else 0.0

    ge_mcal_kg = _energia_bruta_mcal_kg(pb_pct, ag_pct, amido_pct, fdn_pct, cinzas_pct)
    de_base_mcal_kg = _energia_digestivel_base_mcal_kg(
        categoria_nasem=ingrediente.categoria_nasem,
        pb_pct=pb_pct,
        fdn_pct=fdn_pct,
        lignina_pct=lignina_pct,
        amido_pct=amido_pct,
        ag_pct=ag_pct,
        cinzas_pct=cinzas_pct,
        npncp_pct_dm=npncp_pct_dm,
        dig_amido_pct=dig_amido_pct,
        dig_ag_pct=dig_ag_pct,
        dig_pndr_pct=dig_pndr_pct,
        rup_pct_dm=rup_pct_dm,
        rdp_pct_dm=rdp_pct_dm,
        fator_hidratacao=fator_hidratacao,
    )

    ndf_dc_lignina_pct = _digestibilidade_ndf_base_lignina(fdn_pct, lignina_pct)
    ndf_digerida_base_pct_dm = ndf_dc_lignina_pct / 100.0 * fdn_pct

    forragem_pct = 100.0 - conc_pct
    forragem_ndf_pct_dm = forragem_pct / 100.0 * fdn_pct
    forragem_umida_pct_dm = forragem_pct if (forragem_pct > 50.0 and ms_pct < 71.0) else 0.0

    p_pct = ingrediente.p_pct or 0.0
    p_inorg_p_pct = ingrediente.p_inorg_p_pct if ingrediente.p_inorg_p_pct is not None else 50.0
    p_org_p_pct = ingrediente.p_org_p_pct if ingrediente.p_org_p_pct is not None else (100.0 - p_inorg_p_pct)

    if ingrediente.categoria_nasem == "Vitaminico/mineral":
        abs_p_total = ingrediente.abs_p_total if ingrediente.abs_p_total is not None else 0.75
    else:
        calculado = (
            p_inorg_p_pct * k.FOSFORO_ABS_COEF_INORGANICO
            + p_org_p_pct * k.FOSFORO_ABS_COEF_ORGANICO
        )
        abs_p_total = ingrediente.abs_p_total if ingrediente.abs_p_total is not None else calculado
    abs_p_total = limitar(abs_p_total, 0.0, 1.0)

    ca_pct_valor = ingrediente.ca_pct or 0.0
    na_pct_valor = ingrediente.na_pct or 0.0
    cl_pct_valor = ingrediente.cl_pct or 0.0
    k_pct_valor = ingrediente.k_pct or 0.0
    abs_ca_valor = ingrediente.abs_ca if ingrediente.abs_ca is not None else 0.5
    abs_na_valor = ingrediente.abs_na if ingrediente.abs_na is not None else 0.9
    abs_cl_valor = ingrediente.abs_cl if ingrediente.abs_cl is not None else 0.92
    abs_k_valor = ingrediente.abs_k if ingrediente.abs_k is not None else 0.9

    return PerfilIngrediente(
        nome=ingrediente.nome,
        categoria_nasem=ingrediente.categoria_nasem,
        conc_pct=conc_pct,
        proporcao_normalizada=proporcao_normalizada,
        ms_pct=ms_pct,
        pb_pct=pb_pct,
        fdn_pct=fdn_pct,
        fda_pct=fda_pct,
        lignina_pct=lignina_pct,
        amido_pct=amido_pct,
        acucares_pct=acucares_pct,
        ee_pct=ee_pct,
        ag_pct=ag_pct,
        cinzas_pct=cinzas_pct,
        dndf48_fdn_pct=dndf48,
        npncp_pct_dm=npncp_pct_dm,
        proteina_verdadeira_pct_dm=proteina_verdadeira_pct_dm,
        fa_hidratada_pct_dm=fa_hidratada_pct_dm,
        cnf_pct_dm=cnf_pct_dm,
        materia_organica_residual_pct_dm=rom_pct_dm,
        rup_pct_cp=rup_pct_cp,
        rdp_pct_cp=rdp_pct_cp,
        rup_pct_dm=rup_pct_dm,
        rdp_pct_dm=rdp_pct_dm,
        rup_digestivel_pct_dm=rup_digestivel_pct_dm,
        ge_mcal_kg=ge_mcal_kg,
        de_base_mcal_kg=de_base_mcal_kg,
        ndf_dc_lignina_pct=ndf_dc_lignina_pct,
        ndf_digerida_base_pct_dm=ndf_digerida_base_pct_dm,
        amido_digerido_base_pct_dm=amido_pct * dig_amido_pct / 100.0,
        forragem_pct=forragem_pct,
        forragem_ndf_pct_dm=forragem_ndf_pct_dm,
        forragem_umida_pct_dm=forragem_umida_pct_dm,
        ca_pct=ca_pct_valor,
        p_pct=p_pct,
        p_inorg_p_pct=p_inorg_p_pct,
        p_org_p_pct=p_org_p_pct,
        mg_pct=ingrediente.mg_pct or 0.0,
        k_pct=k_pct_valor,
        na_pct=na_pct_valor,
        cl_pct=cl_pct_valor,
        s_pct=ingrediente.s_pct or 0.0,
        abs_ca=abs_ca_valor,
        abs_p_total=abs_p_total,
        abs_mg=ingrediente.abs_mg if ingrediente.abs_mg is not None else 0.2,
        abs_na=abs_na_valor,
        abs_cl=abs_cl_valor,
        abs_k=abs_k_valor,
        ca_absorvido_pct_dm=ca_pct_valor * abs_ca_valor,
        p_absorvido_pct_dm=p_pct * abs_p_total,
        na_absorvido_pct_dm=na_pct_valor * abs_na_valor,
        cl_absorvido_pct_dm=cl_pct_valor * abs_cl_valor,
        k_absorvido_pct_dm=k_pct_valor * abs_k_valor,
        custo_kg_mn=ingrediente.custo_kg_mn or 0.0,
    )


@dataclass
class ConcentracoesDieta:
    """Bloco C — concentrações da dieta (% da MS, salvo indicado), médias
    ponderadas pelas proporções normalizadas. Não depende do CMS."""

    pb_pct: float
    fdn_pct: float
    fda_pct: float
    lignina_pct: float
    amido_pct: float
    acucares_pct: float
    ee_pct: float
    ag_pct: float
    cinzas_pct: float

    npncp_pct_dm: float
    cnf_pct_dm: float
    materia_organica_residual_pct_dm: float

    rup_pct_dm: float
    rdp_pct_dm: float
    rup_pct_cp: float
    rup_digestivel_pct_dm: float

    ge_mcal_kg: float
    de_base_mcal_kg: float

    ndf_digerida_base_pct_dm: float  # entra na digestibilidade total de FDN ajustada por nível de ingestão (ver digestao.py)
    amido_digerido_base_pct_dm: float

    forragem_pct: float
    forragem_ndf_pct_dm: float
    forragem_umida_pct_dm: float
    adf_ndf: float
    forragem_ndf_sobre_ndf_pct: float
    forragem_dndf48_sobre_forragem_ndf_pct: float

    ca_pct: float
    p_pct: float
    mg_pct: float
    k_pct: float
    na_pct: float
    cl_pct: float
    s_pct: float

    ca_absorvido_pct_dm: float
    p_absorvido_pct_dm: float
    na_absorvido_pct_dm: float
    cl_absorvido_pct_dm: float
    k_absorvido_pct_dm: float

    custo_kg_ms: float

    perfis: list[PerfilIngrediente]


def _media_ponderada(perfis: list[PerfilIngrediente], atributo: str) -> float:
    return sum(getattr(p, atributo) * p.proporcao_normalizada for p in perfis)


def normalizar_proporcoes(ingredientes: list[IngredienteEntrada]) -> list[float]:
    """Normaliza `proporcao_ms_pct` de todos os ingredientes para somar 1,0
    (fração). Assume que a soma já foi validada como > 0."""
    soma = sum(i.proporcao_ms_pct for i in ingredientes)
    return [i.proporcao_ms_pct / soma for i in ingredientes]


def concentracoes_dieta(perfis: list[PerfilIngrediente]) -> ConcentracoesDieta:
    """Bloco C — agrega os perfis de ingrediente em concentrações da dieta,
    puramente por média ponderada das proporções normalizadas (não usa CMS)."""
    fdn_pct = _media_ponderada(perfis, "fdn_pct")
    fda_pct = _media_ponderada(perfis, "fda_pct")
    forragem_ndf_pct_dm = _media_ponderada(perfis, "forragem_ndf_pct_dm")
    forragem_umida_pct_dm = _media_ponderada(perfis, "forragem_umida_pct_dm")

    forragem_dndf48_pct_dm = sum(
        p.forragem_ndf_pct_dm * p.dndf48_fdn_pct / 100.0 * p.proporcao_normalizada
        for p in perfis
    )
    forragem_dndf48_sobre_forragem_ndf_pct = divisao_segura(
        forragem_dndf48_pct_dm, forragem_ndf_pct_dm,
        k.DNDF48_PADRAO_VOLUMOSO_PCT_FDN,
    )

    rup_pct_dm = _media_ponderada(perfis, "rup_pct_dm")
    pb_pct = _media_ponderada(perfis, "pb_pct")

    return ConcentracoesDieta(
        pb_pct=pb_pct,
        fdn_pct=fdn_pct,
        fda_pct=fda_pct,
        lignina_pct=_media_ponderada(perfis, "lignina_pct"),
        amido_pct=_media_ponderada(perfis, "amido_pct"),
        acucares_pct=_media_ponderada(perfis, "acucares_pct"),
        ee_pct=_media_ponderada(perfis, "ee_pct"),
        ag_pct=_media_ponderada(perfis, "ag_pct"),
        cinzas_pct=_media_ponderada(perfis, "cinzas_pct"),
        npncp_pct_dm=_media_ponderada(perfis, "npncp_pct_dm"),
        cnf_pct_dm=_media_ponderada(perfis, "cnf_pct_dm"),
        materia_organica_residual_pct_dm=max(
            0.0, _media_ponderada(perfis, "materia_organica_residual_pct_dm")
        ),
        rup_pct_dm=rup_pct_dm,
        rdp_pct_dm=_media_ponderada(perfis, "rdp_pct_dm"),
        rup_pct_cp=divisao_segura(rup_pct_dm, pb_pct, 0.0),
        rup_digestivel_pct_dm=_media_ponderada(perfis, "rup_digestivel_pct_dm"),
        ge_mcal_kg=_media_ponderada(perfis, "ge_mcal_kg"),
        de_base_mcal_kg=_media_ponderada(perfis, "de_base_mcal_kg"),
        ndf_digerida_base_pct_dm=_media_ponderada(perfis, "ndf_digerida_base_pct_dm"),
        amido_digerido_base_pct_dm=_media_ponderada(perfis, "amido_digerido_base_pct_dm"),
        forragem_pct=_media_ponderada(perfis, "forragem_pct"),
        forragem_ndf_pct_dm=forragem_ndf_pct_dm,
        forragem_umida_pct_dm=forragem_umida_pct_dm,
        adf_ndf=divisao_segura(fda_pct, fdn_pct, 0.0),
        forragem_ndf_sobre_ndf_pct=divisao_segura(forragem_ndf_pct_dm, fdn_pct, 0.0) * 100.0,
        forragem_dndf48_sobre_forragem_ndf_pct=forragem_dndf48_sobre_forragem_ndf_pct,
        ca_pct=_media_ponderada(perfis, "ca_pct"),
        p_pct=_media_ponderada(perfis, "p_pct"),
        mg_pct=_media_ponderada(perfis, "mg_pct"),
        k_pct=_media_ponderada(perfis, "k_pct"),
        na_pct=_media_ponderada(perfis, "na_pct"),
        cl_pct=_media_ponderada(perfis, "cl_pct"),
        s_pct=_media_ponderada(perfis, "s_pct"),
        ca_absorvido_pct_dm=_media_ponderada(perfis, "ca_absorvido_pct_dm"),
        p_absorvido_pct_dm=_media_ponderada(perfis, "p_absorvido_pct_dm"),
        na_absorvido_pct_dm=_media_ponderada(perfis, "na_absorvido_pct_dm"),
        cl_absorvido_pct_dm=_media_ponderada(perfis, "cl_absorvido_pct_dm"),
        k_absorvido_pct_dm=_media_ponderada(perfis, "k_absorvido_pct_dm"),
        custo_kg_ms=sum(
            p.proporcao_normalizada * divisao_segura(p.custo_kg_mn, p.ms_fracao, 0.0)
            for p in perfis
        ),
        perfis=perfis,
    )


__all__ = [
    "PerfilIngrediente",
    "ConcentracoesDieta",
    "perfil_ingrediente",
    "concentracoes_dieta",
    "normalizar_proporcoes",
]
