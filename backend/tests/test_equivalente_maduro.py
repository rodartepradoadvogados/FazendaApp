"""Equivalente maduro — fatores fixos de tabela (Holandês), confiança por
medição (não mais amostra do rebanho) e o trio de apresentação
(`rules/equivalente_maduro.py`). A calibração no rebanho (`calcular_fatores`)
continua existindo, mas só alimenta o painel de aferição — não bloqueia nem
muda o trio principal."""
from __future__ import annotations

from fazenda.rules.equivalente_maduro import (
    CLASSE_MADURA,
    FATOR_HOLANDES,
    AmostraLactacao,
    calcular_fatores,
    classe_de_ordem,
    contagem_lactacoes_por_classe,
    montar_painel_afericao,
    montar_trio,
    nivel_confianca,
)
from fazenda.rules.producao_305 import Producao305


def _amostras(classe: int, valores: list[float]) -> list[AmostraLactacao]:
    return [AmostraLactacao(classe, v) for v in valores]


def _producao(hoje_kg: float, medida_kg: float, n_controles: int = 4, estimada: bool = True) -> Producao305:
    return Producao305(hoje_kg, n_controles, dias_cobertos=100, estimada=estimada, producao_medida_kg=medida_kg)


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


class TestFatoresFixosDeTabela:
    def test_fatores_sao_exatamente_os_aprovados(self):
        assert FATOR_HOLANDES[1] == 1.22
        assert FATOR_HOLANDES[2] == 1.08
        assert FATOR_HOLANDES[CLASSE_MADURA] == 1.00


class TestNivelConfianca:
    """Pontos de corte calibrados para bater com os 7 exemplos do mockup
    aprovado: 23%->baixa, 7%->muito baixa, 66%->média, 81%->alta, 89%->alta,
    42%->baixa, 58%->média."""

    def test_exemplos_do_mockup_aprovado(self):
        assert nivel_confianca(0.23) == "baixa"
        assert nivel_confianca(0.07) == "muito baixa"
        assert nivel_confianca(0.66) == "média"
        assert nivel_confianca(0.81) == "alta"
        assert nivel_confianca(0.89) == "alta"
        assert nivel_confianca(0.42) == "baixa"
        assert nivel_confianca(0.58) == "média"

    def test_fronteiras_redondas(self):
        assert nivel_confianca(0.149) == "muito baixa"
        assert nivel_confianca(0.15) == "baixa"
        assert nivel_confianca(0.449) == "baixa"
        assert nivel_confianca(0.45) == "média"
        assert nivel_confianca(0.749) == "média"
        assert nivel_confianca(0.75) == "alta"

    def test_none_quando_fracao_nao_calculavel(self):
        assert nivel_confianca(None) is None


class TestMontarTrio:
    def test_vaca_madura_ja_chegou_la(self):
        hoje = _producao(28.0, medida_kg=20.0, estimada=False)
        trio = montar_trio(hoje, ordem_parto=4)
        assert trio.ja_maduro is True
        assert trio.producao_maturidade_kg == 28.0
        assert trio.diferenca_kg == 0.0
        assert trio.sem_base is False
        assert trio.confianca_nivel is not None  # madura também recebe confiança

    def test_primeira_cria_recebe_fator_1_22_mesmo_sem_nenhum_historico_de_rebanho(self):
        """O ponto central da mudança: nenhum mínimo de lactações do rebanho
        — o fator vem direto da tabela fixa."""
        hoje = _producao(20.0, medida_kg=5.0)
        trio = montar_trio(hoje, ordem_parto=1)
        assert trio.sem_base is False
        assert trio.producao_maturidade_kg == 24.4  # 20 * 1.22
        assert trio.diferenca_kg == 4.4

    def test_segunda_cria_recebe_fator_1_08(self):
        hoje = _producao(20.0, medida_kg=5.0)
        trio = montar_trio(hoje, ordem_parto=2)
        assert trio.producao_maturidade_kg == 21.6  # 20 * 1.08
        assert trio.diferenca_kg == 1.6

    def test_novilha_de_del_alto_sem_base_alguma_de_rebanho_ainda_recebe_numero(self):
        """Uma primípara de DEL 100 num rebanho que não tem NENHUMA lactação
        encerrada ainda recebe o trio completo — é exatamente o que a
        remoção do mínimo de 20 lactações por classe permite."""
        hoje = _producao(25.0, medida_kg=22.0)
        trio = montar_trio(hoje, ordem_parto=1)
        assert trio.sem_base is False
        assert trio.producao_maturidade_kg is not None

    def test_confianca_e_a_razao_medido_sobre_projetado(self):
        hoje = _producao(100.0, medida_kg=75.0)
        trio = montar_trio(hoje, ordem_parto=1)
        assert trio.confianca_fracao == 0.75
        assert trio.confianca_nivel == "alta"  # >= 75% é alta

    def test_confianca_baixa_quando_a_maior_parte_e_projecao(self):
        hoje = _producao(8510.0, medida_kg=596.0)  # ~7% medido, DEL baixo com controle antigo
        trio = montar_trio(hoje, ordem_parto=1)
        assert trio.confianca_nivel == "muito baixa"

    def test_sem_producao_de_hoje_calculavel_fica_sem_base(self):
        hoje = Producao305(None, n_controles=1, dias_cobertos=None, estimada=False, motivo="só um controle")
        trio = montar_trio(hoje, ordem_parto=1)
        assert trio.sem_base is True
        assert trio.motivo == "só um controle"
        assert trio.producao_maturidade_kg is None
        assert trio.confianca_nivel is None

    def test_ordem_de_parto_desconhecida_fica_sem_base(self):
        """Único motivo de 'sem base' que sobrou além da produção não
        calculável — não é mais 'classe sem lactações suficientes'."""
        hoje = _producao(20.0, medida_kg=15.0)
        trio = montar_trio(hoje, ordem_parto=None)
        assert trio.sem_base is True
        assert trio.classe is None
        assert "ordem de parto desconhecida" in trio.motivo

    def test_producao_hoje_continua_disponivel_mesmo_sem_base(self):
        """Mesmo sem base para projetar (ordem desconhecida), a produção
        real de hoje continua disponível — o front mostra a produção real,
        não nada."""
        hoje = _producao(22.0, medida_kg=18.0)
        trio = montar_trio(hoje, ordem_parto=None)
        assert trio.producao_hoje_kg == 22.0


class TestCalcularFatoresAgoraSoAlimentaAfericao:
    def test_menos_de_20_na_madura_deixa_sem_fator_observado(self):
        amostras = _amostras(1, [20.0] * 30) + _amostras(CLASSE_MADURA, [30.0] * 10)
        fatores = calcular_fatores(amostras)
        assert fatores.por_classe == {}
        assert fatores.sem_base_geral is not None

    def test_fator_da_madura_e_sempre_1_por_construcao(self):
        amostras = _amostras(CLASSE_MADURA, [30.0] * 25) + _amostras(1, [20.0] * 25)
        fatores = calcular_fatores(amostras)
        assert fatores.por_classe[CLASSE_MADURA].fator == 1.0

    def test_fator_observado_nao_afeta_o_trio(self):
        """Mesmo com um fator observado no rebanho bem diferente da tabela
        fixa, o trio usa a tabela — o observado só aparece no painel de
        aferição."""
        hoje = _producao(20.0, medida_kg=15.0)
        trio = montar_trio(hoje, ordem_parto=1)
        assert trio.producao_maturidade_kg == 20.0 * FATOR_HOLANDES[1]


class TestPainelDeAfericao:
    def test_compara_fator_observado_com_fator_de_tabela(self):
        # Observado: madura 32 (média), 1ª cria 20*... -> fator observado ~1.31 (aprox. mockup)
        amostras = (
            _amostras(CLASSE_MADURA, [30.0] * 25)
            + _amostras(1, [22.9] * 26)  # media_madura/media_classe1 ~ 1.31
            + _amostras(2, [27.0] * 31)
        )
        painel = montar_painel_afericao(amostras)
        linha1 = next(l for l in painel if l.classe == 1)
        assert linha1.n_lactacoes == 26
        assert linha1.fator_tabela == 1.22
        assert linha1.fator_observado is not None
        assert linha1.divergencia_pct is not None

    def test_classe_sem_base_observada_mostra_none_mas_nao_trava(self):
        amostras = _amostras(1, [20.0] * 5)  # bem abaixo do mínimo, madura nem aparece
        painel = montar_painel_afericao(amostras)
        linha1 = next(l for l in painel if l.classe == 1)
        assert linha1.fator_observado is None
        assert linha1.divergencia_pct is None
        assert linha1.n_lactacoes == 5
        assert linha1.fator_tabela == 1.22

    def test_sempre_devolve_as_tres_classes(self):
        painel = montar_painel_afericao([])
        assert {l.classe for l in painel} == {1, 2, CLASSE_MADURA}
        for l in painel:
            assert l.n_lactacoes == 0
            assert l.fator_observado is None


class TestContagemLactacoesPorClasse:
    def test_sempre_devolve_as_tres_classes_mesmo_zeradas(self):
        contagem = contagem_lactacoes_por_classe([])
        assert contagem == {1: 0, 2: 0, CLASSE_MADURA: 0}

    def test_conta_corretamente_mesmo_com_classe_abaixo_do_minimo_publicavel(self):
        amostras = _amostras(1, [20.0] * 7) + _amostras(2, [22.0] * 25) + _amostras(CLASSE_MADURA, [30.0] * 50)
        contagem = contagem_lactacoes_por_classe(amostras)
        assert contagem == {1: 7, 2: 25, CLASSE_MADURA: 50}
