"""Onda 4 — Caixa Real (projeção de liquidez).

O ponto que estes testes protegem, além da aritmética: o Caixa Real e a DRE
respondem perguntas diferentes e NÃO devem bater (ver o ADR no topo de
rules/caixa_real.py). Depreciação entra na DRE e não no caixa; principal de
financiamento entra no caixa e não na DRE.
"""
from datetime import date

import pytest

from fazenda.rules.caixa_real import projetar_caixa, sugerir_fundo_reserva


def compromisso(dia: int, valor: float, tipo: str = "despesa", mes: int = 9, descricao: str = "x"):
    return {"data": date(2026, mes, dia), "valor": valor, "tipo": tipo, "descricao": descricao}


class TestProjecao:
    def test_saldo_evolui_dia_a_dia(self):
        r = projetar_caixa(100000.0, [
            compromisso(5, 30000),
            compromisso(10, 80000, "receita"),
        ], date(2026, 9, 1), 30)
        assert r["serie"][0]["saldo"] == 100000.0          # dia 1: nada acontece
        assert r["serie"][4]["saldo"] == 70000.0           # dia 5: -30.000
        assert r["serie"][9]["saldo"] == 150000.0          # dia 10: +80.000
        assert r["saldo_final"] == 150000.0

    def test_receita_soma_e_despesa_subtrai_pelo_tipo(self):
        """O sinal vem do TIPO, nunca de um valor negativo escondido — mesma
        regra do operador de linha na DRE."""
        r = projetar_caixa(0.0, [compromisso(2, 500, "receita"), compromisso(3, 200, "despesa")],
                           date(2026, 9, 1), 10)
        assert r["total_entradas"] == 500.0
        assert r["total_saidas"] == 200.0
        assert r["saldo_final"] == 300.0

    def test_conta_vencida_entra_no_primeiro_dia(self):
        """Conta que venceu e não foi paga é dívida real, pesando no caixa
        hoje. Descartá-la faria a projeção parecer mais saudável do que é —
        o erro mais perigoso possível nesta tela."""
        r = projetar_caixa(10000.0, [compromisso(15, 4000, mes=7)], date(2026, 9, 1), 30)
        assert r["serie"][0]["saidas"] == 4000.0
        assert r["serie"][0]["saldo"] == 6000.0
        assert r["serie"][0]["itens"][0]["vencido"] is True

    def test_compromisso_alem_do_horizonte_fica_de_fora(self):
        r = projetar_caixa(1000.0, [compromisso(1, 500, mes=12)], date(2026, 9, 1), 30)
        assert r["saldo_final"] == 1000.0

    def test_dois_compromissos_no_mesmo_dia_somam(self):
        r = projetar_caixa(1000.0, [compromisso(5, 100), compromisso(5, 250)], date(2026, 9, 1), 10)
        assert r["serie"][4]["saidas"] == 350.0


class TestAlertas:
    def test_marca_o_primeiro_dia_abaixo_da_reserva(self):
        r = projetar_caixa(100000.0, [compromisso(5, 70000)], date(2026, 9, 1), 30,
                           fundo_reserva=40000.0)
        assert r["primeiro_dia_abaixo_da_reserva"] == "2026-09-05"
        assert r["primeiro_dia_negativo"] is None, "furar a reserva não é ficar negativo"

    def test_marca_o_primeiro_dia_negativo(self):
        r = projetar_caixa(10000.0, [compromisso(3, 25000)], date(2026, 9, 1), 30)
        assert r["primeiro_dia_negativo"] == "2026-09-03"

    def test_sem_fundo_definido_nao_alerta_de_reserva(self):
        """fundo_reserva=0 é "ainda não defini" — não pode gerar alerta de
        reserva furada em todo dia da projeção."""
        r = projetar_caixa(1000.0, [], date(2026, 9, 1), 30, fundo_reserva=0.0)
        assert r["primeiro_dia_abaixo_da_reserva"] is None

    def test_folga_minima_responde_posso_gastar_agora(self):
        """Folga = pior saldo da projeção menos a reserva. Negativa significa
        que em algum momento a reserva é furada, mesmo que o saldo final
        pareça confortável."""
        r = projetar_caixa(100000.0, [
            compromisso(5, 80000),               # vale do fundo por alguns dias
            compromisso(20, 90000, "receita"),   # e depois se recupera
        ], date(2026, 9, 1), 30, fundo_reserva=40000.0)
        assert r["saldo_final"] == 110000.0, "termina bem"
        assert r["folga_minima"] == -20000.0, "mas fura a reserva no meio do caminho"


class TestFundoReservaSugerido:
    def test_media_vezes_meses_de_folga(self):
        assert sugerir_fundo_reserva([30000, 40000, 50000], 3.0) == 120000.0

    def test_ignora_meses_sem_movimento(self):
        """Mês zerado é mês sem dado lançado, não mês sem custo — incluí-lo
        na média sugeriria um fundo menor do que o necessário."""
        assert sugerir_fundo_reserva([30000, 0, 30000], 2.0) == 60000.0

    def test_sem_historico_nao_inventa_numero(self):
        assert sugerir_fundo_reserva([], 3.0) == 0.0


class TestSeparacaoDaDRE:
    """O ADR de rules/caixa_real.py em forma de teste: as duas telas medem
    coisas diferentes, e o motor de caixa não conhece nada que seja só
    competência."""

    def test_motor_de_caixa_nao_recebe_depreciacao(self):
        """Depreciação é despesa que não é saída de caixa. Ela não tem data
        de vencimento nem vira ContaGerencial em aberto, então nunca chega
        aqui — e se um dia chegar, este teste documenta que não deveria."""
        r = projetar_caixa(100000.0, [], date(2026, 9, 1), 30)
        assert r["total_saidas"] == 0.0
        assert r["saldo_final"] == 100000.0

    def test_principal_de_financiamento_e_saida_de_caixa_normal(self):
        """O oposto: principal não entra na DRE em linha nenhuma, mas no
        caixa é saída como qualquer outra."""
        r = projetar_caixa(100000.0, [compromisso(10, 15000, descricao="Parcela do financiamento")],
                           date(2026, 9, 1), 30)
        assert r["saldo_final"] == 85000.0
