"""Produção de 305 dias pelo Test Interval Method (`rules/producao_305.py`) —
substitui a "média aritmética × 305" de `frontend/producao/page.tsx`.

Os casos degenerados importam tanto quanto a conta em si: 0 ou 1 controle não
dá para integrar, e a função tem de dizer isso em vez de inventar um número."""
from __future__ import annotations

from datetime import date

from fazenda.rules.producao_305 import PontoControle, Producao305, producao_305_dias

PARTO = date(2024, 1, 1)
DOIS_PONTOS = [PontoControle(date(2024, 1, 11), 30.0), PontoControle(date(2024, 1, 21), 26.0)]


class TestIntegracaoTrapezoidal:
    def test_duas_pontas_por_extrapolacao_do_ritmo_conhecido(self):
        """I0·M1 (ponta inicial, ritmo do 1º controle desde o parto) +
        I1·(M1+M2)/2 (trapézio do meio) + In·Mn (ponta final, ritmo do
        último controle até o fim da janela)."""
        r = producao_305_dias(DOIS_PONTOS, PARTO, dias=40)
        # I0=10*30=300; I1=10*(30+26)/2=280; In=20*26=520 (limite=parto+40=11/fev)
        assert r.producao_kg == 1100.0
        assert r.n_controles == 2
        assert r.dias_cobertos == 20
        assert r.estimada is True  # lactação em andamento, sem secagem/fim conhecido

    def test_fim_de_lactacao_conhecido_trunca_a_janela_e_nao_e_estimada(self):
        """Com secagem conhecida antes do fim dos 305 dias, a ponta final
        extrapola só até lá — pouco trecho, e não é mais 'em andamento'."""
        r = producao_305_dias(DOIS_PONTOS, PARTO, data_fim=date(2024, 1, 25), dias=40)
        # In agora vai só até 25/jan: (25-21)=4 dias * 26 = 104
        assert r.producao_kg == 684.0
        assert r.estimada is False

    def test_controles_fora_de_ordem_dao_o_mesmo_resultado(self):
        embaralhado = list(reversed(DOIS_PONTOS))
        assert producao_305_dias(embaralhado, PARTO, dias=40).producao_kg == 1100.0

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
        # I0=10*32=320; I1=10*(32+26)/2=290; In=20*26=520
        assert r.producao_kg == 1130.0


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
