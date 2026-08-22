"""Equivalente maduro — fatores calibrados no rebanho e o trio de apresentação
(`rules/equivalente_maduro.py`). As quatro decisões da seção 6 do documento de
proposta estão travadas aqui: classe madura é sempre 3ª+, mínimo de 20
lactações para publicar um fator (50 para confiança alta), degradação total
quando a própria classe madura não tem base, e nunca um EM sozinho — sempre o
trio, com a vaca madura dizendo "já está na maturidade" via `ja_maduro`."""
from __future__ import annotations

from fazenda.rules.equivalente_maduro import (
    CLASSE_MADURA,
    AmostraLactacao,
    FatorClasse,
    FatoresRebanho,
    calcular_fatores,
    classe_de_ordem,
    montar_trio,
)
from fazenda.rules.producao_305 import Producao305


def _amostras(classe: int, valores: list[float]) -> list[AmostraLactacao]:
    return [AmostraLactacao(classe, v) for v in valores]


class TestClasseDeOrdem:
    def test_primeira_e_segunda_cria_tem_classe_propria(self):
        assert classe_de_ordem(1) == 1
        assert classe_de_ordem(2) == 2

    def test_terceira_ou_mais_e_sempre_classe_madura(self):
        assert classe_de_ordem(3) == CLASSE_MADURA
        assert classe_de_ordem(4) == CLASSE_MADURA
        assert classe_de_ordem(9) == CLASSE_MADURA

    def test_ordem_desconhecida_ou_invalida_nao_classifica(self):
        assert classe_de_ordem(None) is None
        assert classe_de_ordem(0) is None


class TestCalcularFatores:
    def test_menos_de_20_na_madura_degrada_o_indicador_inteiro(self):
        """30 lactações de 1ª cria não salvam o indicador se a classe madura
        (3+) só tem 10 — não se promove a 2ª cria a 'madura' por conveniência."""
        amostras = _amostras(1, [20.0] * 30) + _amostras(CLASSE_MADURA, [30.0] * 10)
        fatores = calcular_fatores(amostras)
        assert fatores.por_classe == {}
        assert fatores.sem_base_geral is not None
        assert "20" in fatores.sem_base_geral

    def test_classe_sem_20_fica_sem_fator_mas_nao_derruba_as_outras(self):
        """Madura e 1ª cria com base suficiente; 2ª cria com só 5 lactações
        — só a 2ª cria fica de fora."""
        amostras = _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [20.0] * 25) + _amostras(2, [25.0] * 5)
        fatores = calcular_fatores(amostras)
        assert set(fatores.por_classe) == {1, CLASSE_MADURA}
        assert fatores.sem_base_geral is None

    def test_fator_da_madura_e_sempre_1_por_construcao(self):
        amostras = _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [20.0] * 25)
        fatores = calcular_fatores(amostras)
        assert fatores.por_classe[CLASSE_MADURA].fator == 1.0
        assert fatores.por_classe[CLASSE_MADURA].desvio_fator == 0.0

    def test_fator_e_a_razao_das_medias(self):
        amostras = _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [20.0] * 25)
        fatores = calcular_fatores(amostras)
        assert fatores.por_classe[1].media_305_kg == 20.0
        assert fatores.por_classe[1].fator == 1.5  # 30/20

    def test_confianca_baixa_entre_20_e_49_lactacoes(self):
        amostras = _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [20.0] * 25)
        fatores = calcular_fatores(amostras)
        assert fatores.por_classe[1].confianca == "baixa"
        assert fatores.por_classe[CLASSE_MADURA].confianca == "baixa"

    def test_confianca_ok_a_partir_de_50_lactacoes(self):
        amostras = _amostras(CLASSE_MADURA, [30.0] * 55) + _amostras(1, [20.0] * 55)
        fatores = calcular_fatores(amostras)
        assert fatores.por_classe[1].confianca == "ok"
        assert fatores.por_classe[CLASSE_MADURA].confianca == "ok"

    def test_desvio_fator_e_zero_sem_variacao_e_positivo_com_variacao(self):
        sem_variacao = _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [20.0] * 25)
        assert calcular_fatores(sem_variacao).por_classe[1].desvio_fator == 0.0

        com_variacao = _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [18.0] * 12 + [22.0] * 13)
        assert calcular_fatores(com_variacao).por_classe[1].desvio_fator > 0.0


class TestMontarTrio:
    FATORES_COMPLETOS = calcular_fatores(
        _amostras(CLASSE_MADURA, [30.0] * 25)
        + _amostras(1, [20.0] * 25)
        + _amostras(2, [25.0] * 25)
    )

    def test_vaca_madura_ja_chegou_la(self):
        hoje = Producao305(28.0, n_controles=6, dias_cobertos=280, estimada=False)
        trio = montar_trio(hoje, ordem_parto=4, fatores=self.FATORES_COMPLETOS)
        assert trio.ja_maduro is True
        assert trio.producao_maturidade_kg == 28.0
        assert trio.diferenca_kg == 0.0
        assert trio.faixa_diferenca_kg is None
        assert trio.sem_base is False

    def test_vaca_madura_ja_chegou_la_mesmo_sem_fatores_calibrados(self):
        """Não precisa de fator nenhum para dizer 'já é madura' — o fator da
        própria classe madura é 1 por definição, então a falta de base no
        resto do rebanho não impede este caso trivial."""
        sem_fatores = FatoresRebanho(por_classe={}, sem_base_geral="menos de 20 na madura")
        hoje = Producao305(28.0, n_controles=6, dias_cobertos=280, estimada=False)
        trio = montar_trio(hoje, ordem_parto=5, fatores=sem_fatores)
        assert trio.ja_maduro is True
        assert trio.diferenca_kg == 0.0
        assert trio.sem_base is False
        assert trio.confianca_fator is None

    def test_segunda_cria_recebe_projecao_pontual_sem_faixa(self):
        hoje = Producao305(20.0, n_controles=5, dias_cobertos=200, estimada=True)
        trio = montar_trio(hoje, ordem_parto=2, fatores=self.FATORES_COMPLETOS)
        assert trio.sem_base is False
        assert trio.producao_maturidade_kg == 24.0  # 20 * (30/25)
        assert trio.diferenca_kg == 4.0
        assert trio.faixa_diferenca_kg is None  # faixa é só para 1ª cria

    def test_primeira_cria_recebe_faixa_quando_ha_dispersao(self):
        fatores_com_dispersao = calcular_fatores(
            _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [18.0] * 12 + [22.0] * 13)
        )
        hoje = Producao305(20.0, n_controles=4, dias_cobertos=150, estimada=True)
        trio = montar_trio(hoje, ordem_parto=1, fatores=fatores_com_dispersao)
        assert trio.faixa_diferenca_kg is not None
        baixo, alto = trio.faixa_diferenca_kg
        assert baixo < trio.diferenca_kg < alto

    def test_sem_producao_de_hoje_calculavel_fica_sem_base(self):
        hoje = Producao305(None, n_controles=1, dias_cobertos=None, estimada=False, motivo="só um controle")
        trio = montar_trio(hoje, ordem_parto=1, fatores=self.FATORES_COMPLETOS)
        assert trio.sem_base is True
        assert trio.motivo == "só um controle"
        assert trio.producao_maturidade_kg is None

    def test_ordem_de_parto_desconhecida_fica_sem_base(self):
        hoje = Producao305(20.0, n_controles=5, dias_cobertos=150, estimada=False)
        trio = montar_trio(hoje, ordem_parto=None, fatores=self.FATORES_COMPLETOS)
        assert trio.sem_base is True
        assert trio.classe is None

    def test_classe_sem_fator_fica_sem_base_mas_guarda_producao_real(self):
        """Mesmo sem base para projetar, a produção real de hoje continua
        disponível — o front mostra 'só a produção real', não nada."""
        fatores_sem_classe_2 = calcular_fatores(
            _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [20.0] * 25) + _amostras(2, [25.0] * 3)
        )
        hoje = Producao305(22.0, n_controles=5, dias_cobertos=200, estimada=False)
        trio = montar_trio(hoje, ordem_parto=2, fatores=fatores_sem_classe_2)
        assert trio.sem_base is True
        assert trio.producao_hoje_kg == 22.0
        assert trio.producao_maturidade_kg is None
        assert "20" in trio.motivo
