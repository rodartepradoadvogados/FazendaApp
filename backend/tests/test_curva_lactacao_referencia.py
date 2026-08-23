"""Curva de referência do trecho final projetado (`rules/
curva_lactacao_referencia.py`) — substitui o platô que `producao_305_dias`
usava para a ponta final de uma lactação EM ANDAMENTO. Cobertura direta do
módulo; `test_producao_305.py::TestPontaFinalEmAndamentoSegueACurva` cobre a
integração com o TIM."""
from __future__ import annotations

from fazenda.rules.curva_lactacao_referencia import (
    DEL_MINIMO_ANCORAGEM,
    producao_projetada_no_trecho_final,
    ritmo_projetado,
)


class TestRitmoProjetado:
    def test_no_proprio_del_do_ultimo_controle_e_o_ritmo_observado(self):
        assert ritmo_projetado(del_ultimo_controle=100, del_alvo=100, ritmo_ultimo_controle=25.0) == 25.0

    def test_antes_do_ultimo_controle_nao_extrapola_para_tras(self):
        """`del_alvo` anterior ao último controle é território medido, não
        projeção — devolve o próprio ritmo observado, sem inventar."""
        assert ritmo_projetado(del_ultimo_controle=100, del_alvo=50, ritmo_ultimo_controle=25.0) == 25.0

    def test_ritmo_zero_ou_negativo_nao_projeta(self):
        assert ritmo_projetado(del_ultimo_controle=50, del_alvo=200, ritmo_ultimo_controle=0.0) == 0.0
        assert ritmo_projetado(del_ultimo_controle=50, del_alvo=200, ritmo_ultimo_controle=-5.0) == -5.0

    def test_ritmo_projetado_declina_com_o_avanco_do_del(self):
        """Depois do pico da curva de referência (~57 DEL), o ritmo projetado
        cai à medida que o DEL alvo avança — não fica constante."""
        r_100 = ritmo_projetado(del_ultimo_controle=80, del_alvo=100, ritmo_ultimo_controle=27.0)
        r_200 = ritmo_projetado(del_ultimo_controle=80, del_alvo=200, ritmo_ultimo_controle=27.0)
        r_300 = ritmo_projetado(del_ultimo_controle=80, del_alvo=300, ritmo_ultimo_controle=27.0)
        assert r_100 > r_200 > r_300

    def test_piso_de_ancoragem_evita_explosao_perto_de_del_zero(self):
        """Sem o piso, ancorar num controle bem cedo (DEL 2) faria a escala
        implícita explodir (t^b → 0) e o ritmo projetado mais adiante ficaria
        absurdo. Com o piso, o resultado fica em ordem de grandeza razoável."""
        ritmo_bem_cedo = ritmo_projetado(del_ultimo_controle=2, del_alvo=250, ritmo_ultimo_controle=20.0)
        assert 0 < ritmo_bem_cedo < 60.0  # nada de explosão numérica

    def test_del_ultimo_controle_abaixo_do_piso_se_comporta_como_no_piso(self):
        """DEL 2 e DEL bem menor que o piso (15) ancoram no mesmo ponto —
        resultado idêntico, não dois comportamentos diferentes por acaso."""
        a = ritmo_projetado(del_ultimo_controle=2, del_alvo=250, ritmo_ultimo_controle=20.0)
        b = ritmo_projetado(del_ultimo_controle=DEL_MINIMO_ANCORAGEM, del_alvo=250, ritmo_ultimo_controle=20.0)
        assert a == b


class TestProducaoProjetadaNoTrechoFinal:
    def test_sem_trecho_para_projetar_e_zero(self):
        assert producao_projetada_no_trecho_final(200, 200, 25.0) == 0.0
        assert producao_projetada_no_trecho_final(250, 200, 25.0) == 0.0

    def test_janela_curta_perto_do_fim_fica_perto_do_plato(self):
        """Pouco trecho para projetar (5 dias) — a troca de método não deve
        mexer muito no total em relação ao platô simples."""
        projetado = producao_projetada_no_trecho_final(300, 305, 27.0)
        plato = 5 * 27.0
        assert abs(projetado - plato) / plato < 0.05

    def test_janela_longa_em_del_baixo_fica_bem_abaixo_do_plato(self):
        """O caso de maior dependência da projeção (DEL baixo, quase toda a
        janela de 305 dias pela frente): o total da curva fica claramente
        abaixo do platô — é o viés que esta reforma corrige."""
        projetado = producao_projetada_no_trecho_final(28, 305, 27.4)
        plato = (305 - 28) * 27.4
        assert projetado < plato * 0.9

    def test_total_cresce_com_o_tamanho_da_janela(self):
        """Sanidade básica: mais dias para projetar, mais leite total — a
        curva declina em RITMO, mas o total acumulado não pode diminuir
        conforme a janela cresce."""
        curto = producao_projetada_no_trecho_final(28, 100, 27.4)
        longo = producao_projetada_no_trecho_final(28, 305, 27.4)
        assert longo > curto
