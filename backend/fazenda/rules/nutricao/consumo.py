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
    # --- Par "sem fibra" × "com fibra" (ago/2026) ---------------------------
    # Toda categoria tem DUAS equações de CMS no NASEM: uma só com fatores do
    # animal (peso, produção, ECC, DEL) e outra que também olha a fibra da
    # dieta. Antes o usuário escolhia UMA delas e via um número; agora as duas
    # são sempre calculadas e mostradas lado a lado, porque a pergunta que o
    # nutricionista faz não é "qual equação usar" e sim "a fibra desta dieta
    # está limitando o consumo desta vaca?". A diferença entre os dois números
    # É a resposta: vaca que comeria 22 kg pela genética/produção mas 21 kg
    # pela fibra tem 1 kg de consumo travado pelo volumoso.
    cms_sem_fibra_kg_dia: float = 0.0
    cms_com_fibra_kg_dia: float = 0.0
    equacao_sem_fibra: int = 0
    equacao_com_fibra: int = 0
    # Positivo quando a fibra derruba o consumo (sem_fibra - com_fibra).
    fibra_limita_kg_dia: float = 0.0
    fibra_e_limitante: bool = False
    # Quanto a monensina descontou do CMS, em kg/dia (0 quando não usa).
    monensina_reducao_kg_dia: float = 0.0


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


def _par_de_equacoes(animal: AnimalEntrada) -> tuple[int, int]:
    """Devolve (equação SEM fibra, equação COM fibra) da categoria do animal.

    O NASEM traz o mesmo par em três categorias — a equação "com fibra" é
    sempre a que lê a dieta, e a "sem fibra" a que só olha o animal:
      - vaca lactante ... 8 (animal) × 9 (animal + FDN/DNDF da dieta)
      - novilha ........ 2 (animal) × 3 (animal + FDN)
      - vaca seca ...... 11 Hayirli (animal) × 10 transição (usa FDN)
    A escolha do par vem de `eq_cms`, que continua sendo o que o usuário
    salvou; ele só não decide mais QUAL número aparece — decide a categoria.
    """
    eq = animal.eq_cms
    if eq in (2, 3):
        return 2, 3
    if eq in (10, 11):
        return 11, 10
    return 8, 9


def _cms_por_equacao(eq: int, animal: AnimalEntrada, dieta: ConcentracoesDieta) -> float:
    if eq == 0:
        return animal.cms_informado_kg_dia or 0.0
    if eq == 2:
        return _cms_novilha_animal(animal)
    if eq == 3:
        return _cms_novilha_dieta(animal, dieta)
    if eq == 8:
        return _cms_lactante_animal(animal)
    if eq == 9:
        return _cms_lactante_dieta(animal, dieta)
    if eq == 10:
        return _cms_transicao(animal, dieta)
    if eq == 11:
        return _cms_hayirli(animal)
    raise ValorInvalidoError(f"eq_cms não suportado na Fase 1: {eq}")  # pragma: no cover


def _reducao_monensina(animal: AnimalEntrada, cms: float) -> float:
    """Quanto a monensina desconta deste CMS, em kg/dia. Ver constantes.

    Nunca desconta mais que o próprio CMS (uma redução manual absurda não
    pode virar consumo negativo)."""
    if not animal.usa_monensina:
        return 0.0
    modo = (animal.monensina_modo or "kg").lower()
    if modo == "manual":
        reducao = animal.monensina_reducao_manual or 0.0
    elif modo == "pct":
        reducao = cms * k.MONENSINA_CMS_REDUCAO_PCT / 100.0
    else:
        reducao = k.MONENSINA_CMS_REDUCAO_KG_DIA
    return limitar(reducao, 0.0, max(cms - 0.01, 0.0))


def calcular_cms(animal: AnimalEntrada, dieta: ConcentracoesDieta) -> ResultadoConsumo:
    """Bloco B — CMS da categoria do animal, calculado nas DUAS equações
    (sem fibra e com fibra) e descontado o efeito da monensina.

    Qual dos dois vale para o balanço: o COM FIBRA, por ser o limite físico
    real — de nada adianta a vaca ter potencial para 22 kg se o volumoso
    desta dieta só deixa ela comer 21. O número sem fibra fica ao lado como
    diagnóstico ("quanto a fibra está custando"). CMS informado manualmente
    (eq_cms=0) vence os dois: é medição, não estimativa.

    Assume entrada já validada por `tipos.validar_entrada`.
    """
    eq_sem_fibra, eq_com_fibra = _par_de_equacoes(animal)

    bruto_sem_fibra = max(_cms_por_equacao(eq_sem_fibra, animal, dieta), 0.01)
    bruto_com_fibra = max(_cms_por_equacao(eq_com_fibra, animal, dieta), 0.01)

    cms_sem_fibra = max(bruto_sem_fibra - _reducao_monensina(animal, bruto_sem_fibra), 0.01)
    cms_com_fibra = max(bruto_com_fibra - _reducao_monensina(animal, bruto_com_fibra), 0.01)

    if animal.eq_cms == 0:
        cms = max(animal.cms_informado_kg_dia or 0.0, 0.01)
        equacao_usada = 0
        reducao = 0.0
    else:
        cms = cms_com_fibra
        equacao_usada = eq_com_fibra
        reducao = _reducao_monensina(animal, bruto_com_fibra)

    limita = cms_sem_fibra - cms_com_fibra
    peso_metabolico = animal.peso_vivo_kg ** 0.75
    return ResultadoConsumo(
        cms_kg_dia=cms,
        equacao_usada=equacao_usada,
        cms_pct_pv=divisao_segura(cms, animal.peso_vivo_kg, 0.0) * 100.0,
        cms_g_kg_pv075=divisao_segura(cms * 1000.0, peso_metabolico, 0.0),
        cms_sem_fibra_kg_dia=cms_sem_fibra,
        cms_com_fibra_kg_dia=cms_com_fibra,
        equacao_sem_fibra=eq_sem_fibra,
        equacao_com_fibra=eq_com_fibra,
        fibra_limita_kg_dia=limita,
        # 0,1 kg de folga: diferença menor que isso é ruído de arredondamento
        # das equações, não fibra travando consumo de verdade.
        fibra_e_limitante=limita > 0.1,
        monensina_reducao_kg_dia=reducao,
    )


__all__ = ["ResultadoConsumo", "calcular_cms"]
