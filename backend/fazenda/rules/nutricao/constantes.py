"""Constantes fisiológicas e energéticas nomeadas por significado.

Cada constante cita o capítulo/equação do livro NASEM, *Nutrient Requirements
of Dairy Cattle*, 8th revised edition (2021), onde ela é publicada. Esta é
uma reimplementação independente: os valores numéricos publicados no livro
são fatos científicos de domínio público, e os nomes/organização abaixo são
próprios — não derivam de nenhum código-fonte de referência.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Energia bruta de combustão dos nutrientes, Mcal/kg de nutriente puro
# (NASEM 2021, Cap. 3)
# ---------------------------------------------------------------------------
ENERGIA_BRUTA_ACIDOS_GRAXOS = 9.4
ENERGIA_BRUTA_PROTEINA_BRUTA = 5.65  # exclui NNP
ENERGIA_BRUTA_CARBOIDRATO_NAO_FIBROSO = 4.2
ENERGIA_BRUTA_FDN = 4.2
ENERGIA_BRUTA_NNP = 0.89  # por kg de PB equivalente (base ureia, 2,5 kcal/g)
ENERGIA_BRUTA_MATERIA_ORGANICA_RESIDUAL = 4.0
ENERGIA_BRUTA_AMIDO = 4.23

# ---------------------------------------------------------------------------
# Fracionamento proteico e passagem ruminal (NASEM 2021, Cap. 6)
# ---------------------------------------------------------------------------
TAXA_PASSAGEM_CONCENTRADO_PCT_H = 5.28
TAXA_PASSAGEM_VOLUMOSO_PCT_H = 4.87
FRACAO_A_QUE_ESCAPA_DEGRADACAO = 0.064  # kg de CPA passante / kg de CPA
INTERCEPTO_PNDR_KG_DIA = -0.086
PB_REFERENCIA_INTERCEPTO_PNDR_KG_DIA = 3.39  # média do conjunto de dados original
FATOR_HIDRATACAO_TRIACILGLICEROL = 1 / 1.06  # =1,0 para suplemento de ácido graxo puro

# ---------------------------------------------------------------------------
# Preenchimento-padrão de DNDF48 quando não informado (NASEM 2021, Cap. 2/3)
# ---------------------------------------------------------------------------
DNDF48_PADRAO_VOLUMOSO_PCT_FDN = 48.3
DNDF48_PADRAO_CONCENTRADO_PCT_FDN = 65.0

# ---------------------------------------------------------------------------
# Proteína microbiana — Michaelis-Menten dupla (NASEM 2021, Cap. 6)
# ---------------------------------------------------------------------------
MICROBIANA_INTERCEPTO_VMAX_G = 100.8
MICROBIANA_INCLINACAO_PDR_VMAX_G_POR_KG = 81.56
MICROBIANA_PDR_TETO_PCT_MS = 12.0
MICROBIANA_KM_FDN_DEGRADADA = 0.0939
MICROBIANA_KM_AMIDO_DEGRADADO = 0.0274
MICROBIANA_EFICIENCIA_PDR_TETO = 1.0
MICROBIANA_N_PARA_PB = 6.25
MICROBIANA_FRACAO_PROTEINA_VERDADEIRA = 0.824
MICROBIANA_DIGESTIBILIDADE_INTESTINAL_PCT = 80.0
MICROBIANA_PISO_NITROGENIO_G_DIA = 10.0

# ---------------------------------------------------------------------------
# Proteína metabolizável — exigências de manutenção (NASEM 2021, Cap. 6)
# ---------------------------------------------------------------------------
DESCAMACAO_COEFICIENTE = 0.20
DESCAMACAO_EXPOENTE_PV = 0.60
NP_PARA_CP_CORPORAL = 0.86  # fração de proteína verdadeira na PB corporal/descamação
FECAL_ENDOGENA_INTERCEPTO_G_POR_KG_CMS = 12.0
FECAL_ENDOGENA_INCLINACAO_FDN = 0.12
FECAL_ENDOGENA_FRACAO_PROTEINA_VERDADEIRA = 0.73
URINARIA_ENDOGENA_COEFICIENTE = 0.053
URINARIA_ENDOGENA_N_PARA_PB = 6.25

# ---------------------------------------------------------------------------
# Eficiências-alvo (fixas) de conversão PM -> proteína líquida
# (NASEM 2021, Cap. 6, Tabela 6-6)
# ---------------------------------------------------------------------------
EFICIENCIA_PM_NP_GERAL = 0.69
EFICIENCIA_PM_NP_MANTENCA_ADULTO = 0.69
EFICIENCIA_PM_NP_MANTENCA_JOVEM = 0.66
EFICIENCIA_PM_NP_GESTACAO = 0.33
EFICIENCIA_PM_NP_GANHO_VACA_ADULTA = 0.69
EFICIENCIA_PM_NP_GANHO_PISO = 0.394 * NP_PARA_CP_CORPORAL

# ---------------------------------------------------------------------------
# Energia — perdas urinárias e gasosas (NASEM 2021, Cap. 3)
# ---------------------------------------------------------------------------
ENERGIA_PERDIDA_URINA_MCAL_POR_G_N = 0.0143
MONENSINA_FATOR_REDUCAO_METANO = 0.95
MONENSINA_FATOR_AUMENTO_ED = 1.02

# Efeito da monensina sobre o CONSUMO de matéria seca (distinto dos dois
# fatores acima, que agem sobre a energia). A monensina reduz o CMS e, ao
# mesmo tempo, melhora a eficiência alimentar — por isso o desconto entra no
# CMS sem mexer na produção-alvo.
#
# Duas parametrizações à escolha do usuário (ver `monensina_modo` em
# tipos.AnimalEntrada), porque a literatura reporta o efeito das duas formas
# e nenhuma serve bem para todo rebanho:
#   - absoluta, em kg/dia: meta-análise de Duffield et al. (2008), J. Anim.
#     Sci. 86:4583 — queda média de ~0,3 kg de MS/dia em vacas leiteiras;
#   - relativa, em % do CMS: desconto proporcional, que escala com o
#     tamanho/consumo do animal em vez de descontar o mesmo peso de uma
#     novilha e de uma vaca de alta produção.
MONENSINA_CMS_REDUCAO_KG_DIA = 0.30
MONENSINA_CMS_REDUCAO_PCT = 2.0

# Perda gasosa (metano), Mcal/d — parametrização usada no balanço de EM
# (a que efetivamente entra em EM = ED - gases - urina no software de
# referência; a literatura publica uma segunda parametrização, usada só
# para exibição em algumas telas, que não entra neste balanço).
GASES_NOVILHA_INTERCEPTO = -0.038
GASES_NOVILHA_COEF_EB = 0.051
GASES_NOVILHA_COEF_FDN = 0.0091
GASES_VACA_SECA_INTERCEPTO = 0.69
GASES_VACA_SECA_COEF_EB = 0.053
GASES_VACA_SECA_COEF_GORDURA = -0.07
GASES_LACTANTE_COEF_CMS = 0.294
GASES_LACTANTE_COEF_AG = -0.347
GASES_LACTANTE_COEF_FDN_DIGERIDA = 0.0409

# ---------------------------------------------------------------------------
# Energia — mantença, eficiências EM->EL (NASEM 2021, Cap. 3)
# ---------------------------------------------------------------------------
MANTENCA_NEL_COEFICIENTE = 0.10
MANTENCA_NEL_EXPOENTE_PV = 0.75
EFICIENCIA_EM_EL_MANTENCA_VACA = 0.66
EFICIENCIA_EM_EL_MANTENCA_NOVILHA = 0.63
EFICIENCIA_EM_EL_LACTACAO = 0.66

# ---------------------------------------------------------------------------
# Energia — gestação (NASEM 2021, Cap. 3; curva de crescimento uterino
# derivada de Bell, 1995 / House & Bell, 1993)
# ---------------------------------------------------------------------------
PESO_UTERO_GRAVIDO_POR_PESO_BEZERRO = 1.816
PESO_UTERO_NAO_GRAVIDO_POR_PESO_BEZERRO = 0.2311
ENERGIA_LIQUIDA_POR_KG_UTERO_GRAVIDO_MCAL = 0.950
PROTEINA_BRUTA_POR_KG_UTERO_GRAVIDO_KG = 0.123
UTERO_GRAVIDO_KSYN = 2.43e-2
UTERO_GRAVIDO_KSYN_DECAY = 2.45e-5
UTERO_NAO_GRAVIDO_KSYN = 2.42e-2
UTERO_NAO_GRAVIDO_KSYN_DECAY = 3.53e-5
UTERO_NAO_GRAVIDO_KDEG_INVOLUCAO = 0.20
UTERO_PESO_BASE_NAO_GESTANTE_KG = 0.204
EFICIENCIA_EM_ENERGIA_GESTACAO = 0.89  # eficiência marginal por regressão (ver docstring de gestacao.py)

# ---------------------------------------------------------------------------
# Energia — composição corporal e ganho (NASEM 2021, Cap. 3)
# ---------------------------------------------------------------------------
GORDURA_FRACAO_EBW_INTERCEPTO = 0.067
GORDURA_FRACAO_EBW_INCLINACAO_PV_PVMADURO = 0.188
PROTEINA_BRUTA_FRACAO_MASSA_MAGRA_EBW = 0.215
GORDURA_GANHO_ESTRUTURA_INTERCEPTO = 0.067
GORDURA_GANHO_ESTRUTURA_INCLINACAO = 0.375
GORDURA_GANHO_RESERVA_FRACAO = 0.622
PROTEINA_GANHO_ESTRUTURA_INTERCEPTO = 0.201
PROTEINA_GANHO_ESTRUTURA_INCLINACAO_PV_PVMADURO = 0.081
PROTEINA_GANHO_RESERVA_FRACAO_CP = 0.068
ENERGIA_RETIDA_COEF_GORDURA_MCAL_KG = 9.4
ENERGIA_RETIDA_COEF_PROTEINA_MCAL_KG = 5.55
EFICIENCIA_EM_GANHO_ESTRUTURA = 0.40
EFICIENCIA_EM_GANHO_RESERVA_PADRAO = 0.60
EFICIENCIA_EM_GANHO_RESERVA_LACTANTE_GANHANDO = 0.75
EFICIENCIA_EM_GANHO_RESERVA_PERDENDO = 0.89

# ---------------------------------------------------------------------------
# Energia — lactação (NASEM 2021, Cap. 3)
# ---------------------------------------------------------------------------
NEL_LEITE_COEF_GORDURA = 9.29
NEL_LEITE_COEF_PROTEINA = 5.85
NEL_LEITE_COEF_LACTOSE = 3.95
TYRRELL_REID_INTERCEPTO = 0.36
TYRRELL_REID_COEF_GORDURA = 9.69

# ---------------------------------------------------------------------------
# Ganho de peso permitido por ECC (NASEM 2021, Cap. 3)
# ---------------------------------------------------------------------------
FRACAO_PV_POR_PONTO_ECC = 0.094

# ---------------------------------------------------------------------------
# CMS — constantes das 7 equações (NASEM 2021, Cap. 2)
# ---------------------------------------------------------------------------
CMS_NOVILHA_ANIMAL_COEF_PVMADURO = 0.022
CMS_NOVILHA_ANIMAL_EXP = -1.54
CMS_NOVILHA_DIETA_COEF_PVMADURO = 0.0226
CMS_NOVILHA_DIETA_EXP = -1.47
CMS_NOVILHA_DIETA_COEF_DESVIO_FDN = 0.082
CMS_LACT1_INTERCEPTO = 3.7
CMS_LACT1_COEF_PARIDADE = 5.7
CMS_LACT1_COEF_ELLEITE = 0.305
CMS_LACT1_COEF_PV = 0.022
CMS_LACT1_ECC_INTERCEPTO = -0.689
CMS_LACT1_ECC_COEF_PARIDADE = -1.87
CMS_LACT1_CURVA_INTERCEPTO = 0.212
CMS_LACT1_CURVA_COEF_PARIDADE = 0.136
CMS_LACT1_CURVA_DECAIMENTO = -0.053
CMS_LACT2_INTERCEPTO = 12.0
CMS_LACT2_COEF_FDN_FOR = -0.107
CMS_LACT2_COEF_RAZAO_FDA_FDN = 8.17
CMS_LACT2_COEF_DNDF48_FORNDF = 0.0253
CMS_LACT2_COEF_INTERACAO_FDA = -0.328
CMS_LACT2_FDA_NDF_CENTRO = 0.602
CMS_LACT2_DNDF48_CENTRO = 48.3
CMS_LACT2_COEF_PRODUCAO = 0.225
CMS_LACT2_COEF_INTERACAO_PROD = 0.00390
CMS_LACT2_PRODUCAO_CENTRO = 33.1
CMS_TRANSICAO_KA_PCT_PV = 1.47
CMS_TRANSICAO_KB_INTERCEPTO = 0.365
CMS_TRANSICAO_KB_COEF_FDN = 0.0028
CMS_TRANSICAO_KC_PCT_PV = -0.035
CMS_TRANSICAO_FATOR_PV = 0.88
CMS_HAYIRLI_INTERCEPTO_PCT_PV = 1.979
CMS_HAYIRLI_GEST_COEF = -0.756
CMS_HAYIRLI_GEST_EXP = 0.154

# ---------------------------------------------------------------------------
# Macrominerais — mantença, ganho, gestação, leite (NASEM 2021, Cap. 7)
# ---------------------------------------------------------------------------
CALCIO_LEITE_G_POR_L_JERSEY = 1.17
CALCIO_LEITE_G_POR_L_DEMAIS = 1.03
CALCIO_MANTENCA_FECAL_G_POR_KG_CMS = 0.9
FOSFORO_MANTENCA_URINARIA_G_POR_KG_PV = 0.0006
FOSFORO_MANTENCA_FECAL_NOVILHA_G_POR_KG_CMS = 0.8
FOSFORO_MANTENCA_FECAL_VACA_G_POR_KG_CMS = 1.0
MAGNESIO_MANTENCA_URINARIA_G_POR_KG_PV = 0.0007
MAGNESIO_MANTENCA_FECAL_G_POR_KG_CMS = 0.3
MAGNESIO_GANHO_G_POR_KG = 0.45
MAGNESIO_LEITE_G_POR_KG = 0.11
SODIO_MANTENCA_FECAL_G_POR_KG_CMS = 1.45
SODIO_GANHO_G_POR_KG = 1.4
SODIO_LEITE_G_POR_KG = 0.4
CLORO_MANTENCA_FECAL_G_POR_KG_CMS = 1.11
CLORO_GANHO_G_POR_KG = 1.0
CLORO_LEITE_G_POR_KG = 1.0
POTASSIO_MANTENCA_FECAL_G_POR_KG_CMS = 2.5
POTASSIO_MANTENCA_URINARIA_LACTANTE_G_POR_KG_PV = 0.20
POTASSIO_MANTENCA_URINARIA_SECA_G_POR_KG_PV = 0.07
POTASSIO_GANHO_G_POR_KG = 2.5
POTASSIO_LEITE_G_POR_KG = 1.5
ENXOFRE_EXIGENCIA_G_POR_KG_CMS = 2.0

# Absorção de fósforo a partir das frações inorgânica/orgânica (fração, não %)
FOSFORO_ABS_COEF_INORGANICO = 0.0084
FOSFORO_ABS_COEF_ORGANICO = 0.0068

# Absorção de magnésio — equação logarítmica dependente do K dietético
MAGNESIO_ABS_INTERCEPTO_PCT = 44.1
MAGNESIO_ABS_COEF_LN_K = 5.42
POTASSIO_PISO_PCT_MS_PARA_LN = 0.01

# DCAD (NASEM 2021, Cap. 7), meq/kg de MS
DCAD_PESO_EQUIVALENTE_K = 0.039
DCAD_PESO_EQUIVALENTE_NA = 0.023
DCAD_PESO_EQUIVALENTE_CL = 0.0355
DCAD_PESO_EQUIVALENTE_S = 0.016
