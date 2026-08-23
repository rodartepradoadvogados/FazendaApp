"""Produção de 305 dias pelo Test Interval Method (`rules/producao_305.py`) —
substitui a "média aritmética × 305" que `frontend/producao/page.tsx` fazia
antes desta camada.

Os casos degenerados importam tanto quanto a conta em si: 0 ou 1 controle não
dá para integrar, e a função tem de dizer isso em vez de inventar um número.

A ponta final da lactação EM ANDAMENTO (sem secagem/próximo parto conhecido)
não é mais um platô — segue a curva de referência declinante de
`rules/curva_lactacao_referencia.py`, ancorada no ritmo do último controle
(ver `TestPontaFinalEmAndamentoSegueACurva`). A ponta final da lactação JÁ
ENCERRADA continua no platô de sempre (trecho curto, real, até a secagem)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from fazenda.rules.curva_lactacao_referencia import producao_projetada_no_trecho_final
from fazenda.rules.producao_305 import PontoControle, Producao305, producao_305_dias

PARTO = date(2024, 1, 1)
DOIS_PONTOS = [PontoControle(date(2024, 1, 11), 30.0), PontoControle(date(2024, 1, 21), 26.0)]


class TestIntegracaoTrapezoidal:
    def test_duas_pontas_ponta_inicial_pelo_ritmo_conhecido_final_pela_curva(self):
        """I0·M1 (ponta inicial, ritmo do 1º controle desde o parto) +
        I1·(M1+M2)/2 (trapézio do meio, "medido") + ponta final projetada
        pela curva de referência (não mais um platô) a partir do ritmo do
        último controle."""
        r = producao_305_dias(DOIS_PONTOS, PARTO, dias=40)
        # I0=10*30=300; I1(medido)=10*(30+26)/2=280;
        # ponta final = curva(del=20 -> 40, ritmo=26) — ver módulo da curva.
        ponta_final_esperada = producao_projetada_no_trecho_final(20, 40, 26.0)
        assert r.producao_kg == round(300 + 280 + ponta_final_esperada, 1)
        assert r.n_controles == 2
        assert r.dias_cobertos == 20
        assert r.estimada is True  # lactação em andamento, sem secagem/fim conhecido
        assert r.producao_medida_kg == 280.0  # só o trapézio do meio, nenhuma das pontas

    def test_fim_de_lactacao_conhecido_trunca_a_janela_e_nao_e_estimada(self):
        """Com secagem conhecida antes do fim dos 305 dias, a ponta final
        continua no platô de sempre (trecho curto e real, não projeção para
        o futuro) — só até a data de secagem."""
        r = producao_305_dias(DOIS_PONTOS, PARTO, data_fim=date(2024, 1, 25), dias=40)
        # In agora vai só até 25/jan: (25-21)=4 dias * 26 = 104
        assert r.producao_kg == 684.0
        assert r.estimada is False

    def test_controles_fora_de_ordem_dao_o_mesmo_resultado(self):
        embaralhado = list(reversed(DOIS_PONTOS))
        r1 = producao_305_dias(DOIS_PONTOS, PARTO, dias=40)
        r2 = producao_305_dias(embaralhado, PARTO, dias=40)
        assert r2.producao_kg == r1.producao_kg

    def test_datas_duplicadas_sao_fundidas_pela_media(self):
        """Dois lançamentos no mesmo dia (reenvio, conflito de importação)
        viram um só ponto — a média dos dois, não a soma nem um descarte
        arbitrário."""
        com_duplicata = [
            PontoControle(date(2024, 1, 11), 30.0),
            PontoControle(date(2024, 1, 11), 34.0),  # funde com o de cima -> 32.0
            PontoControle(date(2024, 1, 21), 26.0),
        ]
        r = producao_305_dias(com_duplicata, PARTO, dias=40)
        assert r.n_controles == 2
        # I0=10*32=320; I1(medido)=10*(32+26)/2=290; ponta final igual à do caso acima
        ponta_final_esperada = producao_projetada_no_trecho_final(20, 40, 26.0)
        assert r.producao_kg == round(320 + 290 + ponta_final_esperada, 1)
        assert r.producao_medida_kg == 290.0


class TestPontaFinalEmAndamentoSegueACurva:
    """O núcleo desta reforma: a ponta final de uma lactação EM ANDAMENTO
    deixa de manter o ritmo do último controle constante (platô) e passa a
    declinar segundo a curva de referência — o platô superestimava, e o viés
    crescia quanto menor o DEL do último controle (levantamento anterior:
    até +30% em DEL baixo)."""

    def test_ultimo_controle_cedo_produz_total_menor_que_o_platô_antigo(self):
        """Último controle no DEL 28 (bem antes do fim da janela de 305) —
        o caso de maior dependência da projeção. O platô antigo (ritmo ×
        dias restantes) teria dado um total maior do que a curva dá."""
        pontos = [PontoControle(date(2024, 1, 8), 30.0), PontoControle(date(2024, 1, 29), 27.4)]
        r = producao_305_dias(pontos, PARTO)  # dias=305 padrão, sem secagem
        assert r.estimada is True
        assert r.dias_cobertos == 28

        platô_antigo = (
            (date(2024, 1, 8) - PARTO).days * 30.0
            + r.producao_medida_kg
            + (305 - 28) * 27.4
        )
        assert r.producao_kg < platô_antigo

    def test_ultimo_controle_perto_do_fim_da_janela_fica_perto_do_platô(self):
        """Último controle quase no fim dos 305 dias — pouco trecho para
        projetar, então a troca de método não deve mexer muito no total."""
        pontos = [PontoControle(date(2024, 1, 8), 30.0), PontoControle(PARTO + timedelta(days=300), 27.4)]
        r = producao_305_dias(pontos, PARTO)
        assert r.estimada is True

        platô_antigo = (
            (date(2024, 1, 8) - PARTO).days * 30.0 + r.producao_medida_kg + (305 - 300) * 27.4
        )
        assert r.producao_kg == pytest.approx(platô_antigo, rel=0.03)

    def test_projecao_declina_partir_do_ultimo_controle_nao_fica_constante(self):
        """O ritmo projetado no meio do trecho final é diferente do ritmo do
        último controle — não é mais platô. E o total do trecho final é
        menor que ritmo_constante × dias_restantes para um DEL baixo (bem
        antes do pico da curva de referência)."""
        from fazenda.rules.curva_lactacao_referencia import producao_projetada_no_trecho_final, ritmo_projetado

        ritmo_meio_do_trecho = ritmo_projetado(del_ultimo_controle=28, del_alvo=200, ritmo_ultimo_controle=27.4)
        assert ritmo_meio_do_trecho != 27.4

        projetado = producao_projetada_no_trecho_final(28, 305, 27.4)
        platô = (305 - 28) * 27.4
        assert projetado < platô


class TestCasosDegenerados:
    def test_sem_controle_nenhum_nao_inventa(self):
        r = producao_305_dias([], PARTO)
        assert r == Producao305(
            None, 0, None, False,
            motivo=(
                "menos de dois controles dentro da janela (parto até 305 dias ou até secagem/"
                "próximo parto) — o Test Interval Method exige ao menos dois pontos para integrar"
            ),
        )

    def test_um_controle_so_nao_da_para_integrar(self):
        r = producao_305_dias([PontoControle(date(2024, 1, 11), 30.0)], PARTO)
        assert r.producao_kg is None
        assert r.n_controles == 1
        assert r.motivo is not None

    def test_sem_data_de_parto_nao_inventa(self):
        r = producao_305_dias(DOIS_PONTOS, None)
        assert r == Producao305(None, 0, None, False, motivo="sem data de parto")

    def test_controle_antes_do_parto_e_descartado(self):
        """Não pode pertencer a esta lactação — se sobra só um dentro da
        janela, o resultado é o mesmo de 'um controle só'."""
        com_intruso = [PontoControle(date(2023, 6, 1), 99.0), PontoControle(date(2024, 1, 11), 30.0)]
        r = producao_305_dias(com_intruso, PARTO, dias=40)
        assert r.producao_kg is None
        assert r.n_controles == 1

    def test_controle_depois_da_janela_e_descartado(self):
        fora_da_janela = [PontoControle(date(2024, 1, 11), 30.0), PontoControle(date(2025, 1, 1), 20.0)]
        r = producao_305_dias(fora_da_janela, PARTO, dias=40)
        assert r.producao_kg is None
        assert r.n_controles == 1
