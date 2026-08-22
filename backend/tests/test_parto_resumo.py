"""Quadro "por parto" da Ficha do Animal — fazenda.rules.parto_resumo."""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.parto_resumo import resumo_por_parto

HOJE = date(2026, 8, 22)


def _parto(d: date) -> dict:
    return {"data_parto": d}


def _controle(d: date, kg: float) -> dict:
    return {"data_controle": d, "producao_kg": kg}


def _secagem(d: date) -> dict:
    return {"data_secagem": d}


def _servico(d: date, diagnostico: str | None = None, ordem_tentativa: int | None = None) -> dict:
    return {"data_servico": d, "diagnostico": diagnostico, "ordem_tentativa": ordem_tentativa}


class TestJanelaDaLactacao:
    def test_proximo_parto_encerra_a_lactacao(self):
        p1, p2 = date(2025, 1, 1), date(2025, 12, 1)
        r = resumo_por_parto([_parto(p1), _parto(p2)], [], [], [], hoje=HOJE)
        assert r[0]["lactacao_encerrada"] is True
        assert r[0]["dias_em_lactacao"] == (p2 - p1).days

    def test_secagem_encerra_quando_nao_ha_proximo_parto(self):
        p1 = date(2025, 1, 1)
        secagem = p1 + timedelta(days=280)
        r = resumo_por_parto([_parto(p1)], [], [_secagem(secagem)], [], hoje=HOJE)
        assert r[0]["lactacao_encerrada"] is True
        assert r[0]["dias_em_lactacao"] == 280

    def test_sem_proximo_parto_nem_secagem_fica_em_andamento(self):
        p1 = HOJE - timedelta(days=100)
        r = resumo_por_parto([_parto(p1)], [], [], [], hoje=HOJE)
        assert r[0]["lactacao_encerrada"] is False
        assert r[0]["dias_em_lactacao"] == 100

    def test_ordem_de_parto_e_1_indexada_do_mais_antigo(self):
        p1, p2, p3 = date(2024, 1, 1), date(2025, 1, 1), date(2026, 1, 1)
        r = resumo_por_parto([_parto(p1), _parto(p2), _parto(p3)], [], [], [], hoje=HOJE)
        assert [x["ordem_parto"] for x in r] == [1, 2, 3]


class TestProducao:
    def test_soma_so_controles_dentro_da_janela(self):
        p1, p2 = date(2025, 1, 1), date(2025, 6, 1)
        controles = [
            _controle(date(2024, 12, 20), 30.0),  # antes do parto — fora
            _controle(date(2025, 2, 1), 25.0),
            _controle(date(2025, 3, 1), 20.0),
            _controle(date(2025, 6, 15), 15.0),  # depois do próximo parto — fora
        ]
        r = resumo_por_parto([_parto(p1), _parto(p2)], controles, [], [], hoje=HOJE)
        assert r[0]["producao_total_kg"] == 45.0
        dias = (p2 - p1).days
        assert r[0]["producao_media_dia_kg"] == round(45.0 / dias, 2)

    def test_sem_controle_leiteiro_produtos_ficam_none(self):
        r = resumo_por_parto([_parto(date(2025, 1, 1))], [], [], [], hoje=HOJE)
        assert r[0]["producao_total_kg"] is None
        assert r[0]["producao_media_dia_kg"] is None


class TestProjecao305Dias:
    def test_lactacao_curta_estima_a_partir_da_media_real(self):
        p1 = date(2025, 1, 1)
        p2 = p1 + timedelta(days=100)
        controles = [_controle(p1 + timedelta(days=d), 20.0) for d in range(0, 100, 10)]
        r = resumo_por_parto([_parto(p1), _parto(p2)], controles, [], [], hoje=HOJE)
        assert r[0]["producao_305_dias_estimada"] is True
        assert r[0]["producao_305_dias_kg"] == round(r[0]["producao_media_dia_kg"] * 305, 1)

    def test_lactacao_longa_usa_soma_real_dos_primeiros_305_dias(self):
        p1 = date(2024, 1, 1)
        p2 = p1 + timedelta(days=400)
        controles = [_controle(p1 + timedelta(days=d), 10.0) for d in range(0, 400, 50)]
        r = resumo_por_parto([_parto(p1), _parto(p2)], controles, [], [], hoje=HOJE)
        assert r[0]["producao_305_dias_estimada"] is False
        dentro_305 = [c for c in controles if c["data_controle"] < p1 + timedelta(days=305)]
        assert r[0]["producao_305_dias_kg"] == round(sum(c["producao_kg"] for c in dentro_305), 1)


class TestReproducaoNaLactacao:
    def test_tentativas_usa_o_maior_ordem_tentativa_da_janela(self):
        p1, p2 = date(2025, 1, 1), date(2025, 12, 1)
        servicos = [
            _servico(date(2025, 2, 1), diagnostico="NEGATIVO", ordem_tentativa=1),
            _servico(date(2025, 3, 15), diagnostico="POSITIVO", ordem_tentativa=2),
        ]
        r = resumo_por_parto([_parto(p1), _parto(p2)], [], [], servicos, hoje=HOJE)
        assert r[0]["tentativas_emprenhar"] == 2

    def test_tentativas_cai_para_contagem_sem_ordem_tentativa(self):
        p1, p2 = date(2025, 1, 1), date(2025, 12, 1)
        servicos = [
            _servico(date(2025, 2, 1), diagnostico="NEGATIVO"),
            _servico(date(2025, 3, 1), diagnostico="NEGATIVO"),
            _servico(date(2025, 4, 1), diagnostico="POSITIVO"),
        ]
        r = resumo_por_parto([_parto(p1), _parto(p2)], [], [], servicos, hoje=HOJE)
        assert r[0]["tentativas_emprenhar"] == 3

    def test_sem_servico_na_janela_tentativas_e_none(self):
        r = resumo_por_parto([_parto(date(2025, 1, 1))], [], [], [], hoje=HOJE)
        assert r[0]["tentativas_emprenhar"] is None

    def test_del_concepcao_e_o_primeiro_positivo_da_janela(self):
        p1, p2 = date(2025, 1, 1), date(2025, 12, 1)
        servicos = [
            _servico(date(2025, 2, 1), diagnostico="NEGATIVO", ordem_tentativa=1),
            _servico(date(2025, 3, 15), diagnostico="POSITIVO", ordem_tentativa=2),
            _servico(date(2025, 6, 1), diagnostico="POSITIVO", ordem_tentativa=3),  # não deveria acontecer, mas não conta
        ]
        r = resumo_por_parto([_parto(p1), _parto(p2)], [], [], servicos, hoje=HOJE)
        assert r[0]["del_concepcao"] == (date(2025, 3, 15) - p1).days

    def test_sem_positivo_na_janela_del_concepcao_e_none(self):
        p1, p2 = date(2025, 1, 1), date(2025, 12, 1)
        servicos = [_servico(date(2025, 2, 1), diagnostico="NEGATIVO", ordem_tentativa=1)]
        r = resumo_por_parto([_parto(p1), _parto(p2)], [], [], servicos, hoje=HOJE)
        assert r[0]["del_concepcao"] is None

    def test_servico_de_outra_lactacao_nao_conta(self):
        p1, p2 = date(2025, 1, 1), date(2025, 12, 1)
        servicos = [_servico(date(2026, 1, 1), diagnostico="POSITIVO", ordem_tentativa=1)]  # depois do parto seguinte
        r = resumo_por_parto([_parto(p1), _parto(p2)], [], [], servicos, hoje=HOJE)
        assert r[0]["tentativas_emprenhar"] is None
        assert r[0]["del_concepcao"] is None
