"""Quadro "por parto" da Ficha do Animal — fazenda.rules.parto_resumo."""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.parto import eh_natimorto
from fazenda.rules.parto_resumo import resumo_por_parto

HOJE = date(2026, 8, 22)


def _parto(
    d: date,
    *,
    tipo_parto: str | None = "Parto normal",
    numero_cria_1: str | None = None,
    numero_cria_2: str | None = None,
    gemelar: bool | None = None,
) -> dict:
    return {
        "data_parto": d,
        "tipo_parto": tipo_parto,
        "numero_cria_1": numero_cria_1,
        "numero_cria_2": numero_cria_2,
        "gemelar": gemelar,
    }


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
    def test_media_dia_e_soma_dos_controles_a_dividir_pela_quantidade_deles(self):
        """Média/dia = SOMA dos controles daquele parto ÷ QUANTIDADE de
        controles daquele parto — NÃO soma ÷ dias em lactação (regressão: essa
        conta antiga subestimava a média sempre que há poucos controles
        pontuais espalhados por uma lactação longa)."""
        p1, p2 = date(2025, 1, 1), date(2025, 6, 1)
        controles = [
            _controle(date(2024, 12, 20), 30.0),  # antes do parto — fora
            _controle(date(2025, 2, 1), 25.0),
            _controle(date(2025, 3, 1), 20.0),
            _controle(date(2025, 6, 15), 15.0),  # depois do próximo parto — fora
        ]
        r = resumo_por_parto([_parto(p1), _parto(p2)], controles, [], [], hoje=HOJE)
        # Só os dois controles dentro da janela (25.0 e 20.0) entram na conta.
        assert r[0]["producao_media_dia_kg"] == round((25.0 + 20.0) / 2, 2)

    def test_producao_total_e_media_dia_vezes_del(self):
        """Produção total = média/dia × DEL (dias em lactação) — uma
        estimativa a partir da média real, não a soma bruta dos controles
        lançados (regressão do bug de fórmula do Resumo por parto)."""
        p1, p2 = date(2025, 1, 1), date(2025, 6, 1)
        controles = [_controle(date(2025, 2, 1), 25.0), _controle(date(2025, 3, 1), 20.0)]
        r = resumo_por_parto([_parto(p1), _parto(p2)], controles, [], [], hoje=HOJE)
        dias = (p2 - p1).days
        media = round((25.0 + 20.0) / 2, 2)
        assert r[0]["dias_em_lactacao"] == dias
        assert r[0]["producao_media_dia_kg"] == media
        assert r[0]["producao_total_kg"] == round(media * dias, 1)
        # Não é mais a soma bruta dos controles lançados.
        assert r[0]["producao_total_kg"] != 45.0

    def test_sem_controle_leiteiro_produtos_ficam_none(self):
        r = resumo_por_parto([_parto(date(2025, 1, 1))], [], [], [], hoje=HOJE)
        assert r[0]["producao_total_kg"] is None
        assert r[0]["producao_media_dia_kg"] is None
        assert r[0]["producao_305_dias_kg"] is None


class TestProjecao305Dias:
    def test_305_dias_e_sempre_media_dia_vezes_305(self):
        """305 dias = média/dia × 305, sempre — mesmo quando a lactação já
        rodou mais de 305 dias (regressão: a fórmula antiga somava os
        controles reais dentro da janela de 305 dias nesse caso, uma segunda
        fonte de verdade divergente da média/dia)."""
        p1 = date(2024, 1, 1)
        p2 = p1 + timedelta(days=400)
        controles = [_controle(p1 + timedelta(days=d), 10.0) for d in range(0, 400, 50)]
        r = resumo_por_parto([_parto(p1), _parto(p2)], controles, [], [], hoje=HOJE)
        assert r[0]["producao_305_dias_kg"] == round(r[0]["producao_media_dia_kg"] * 305, 1)

    def test_lactacao_curta_tambem_usa_media_dia_vezes_305(self):
        p1 = date(2025, 1, 1)
        p2 = p1 + timedelta(days=100)
        controles = [_controle(p1 + timedelta(days=d), 20.0) for d in range(0, 100, 10)]
        r = resumo_por_parto([_parto(p1), _parto(p2)], controles, [], [], hoje=HOJE)
        assert r[0]["producao_305_dias_kg"] == round(r[0]["producao_media_dia_kg"] * 305, 1)


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


class TestEhNatimorto:
    def test_reconhece_natimorto(self):
        assert eh_natimorto({"tipo_parto": "Natimorto"}) is True

    def test_ignora_caixa_e_acento(self):
        assert eh_natimorto({"tipo_parto": "  NATIMORTO  "}) is True

    def test_parto_normal_nao_e_natimorto(self):
        assert eh_natimorto({"tipo_parto": "Parto normal"}) is False

    def test_aborto_nao_e_natimorto(self):
        assert eh_natimorto({"tipo_parto": "Aborto"}) is False

    def test_sem_tipo_parto_nao_e_natimorto(self):
        assert eh_natimorto({"tipo_parto": None}) is False


class TestCriaDoParto:
    """Campo `cria` de `resumo_por_parto` — número da cria daquele parto
    específico (não só do último). Aborto nunca aparece aqui: já é filtrado
    antes de `resumo_por_parto` receber a lista (ver `eh_parto_produtivo`,
    aplicado pelo chamador em `animais.py`), então não há cenário de aborto
    a testar nesta função."""

    def test_parto_normal_com_cria_numerada(self):
        p1 = date(2025, 1, 1)
        r = resumo_por_parto([_parto(p1, numero_cria_1="1234")], [], [], [], hoje=HOJE)
        assert r[0]["cria"] == "1234"

    def test_parto_normal_sem_numero_lancado_mostra_sn(self):
        p1 = date(2025, 1, 1)
        r = resumo_por_parto([_parto(p1, numero_cria_1=None)], [], [], [], hoje=HOJE)
        assert r[0]["cria"] == "S/N"

    def test_natimorto_fica_vazio_mesmo_sem_numero(self):
        p1 = date(2025, 1, 1)
        r = resumo_por_parto([_parto(p1, tipo_parto="Natimorto")], [], [], [], hoje=HOJE)
        assert r[0]["cria"] == ""

    def test_natimorto_fica_vazio_mesmo_com_numero_lancado_por_engano(self):
        p1 = date(2025, 1, 1)
        r = resumo_por_parto(
            [_parto(p1, tipo_parto="Natimorto", numero_cria_1="9999")], [], [], [], hoje=HOJE,
        )
        assert r[0]["cria"] == ""

    def test_gemelar_com_as_duas_crias_numeradas(self):
        p1 = date(2025, 1, 1)
        r = resumo_por_parto(
            [_parto(p1, gemelar=True, numero_cria_1="111", numero_cria_2="222")], [], [], [], hoje=HOJE,
        )
        assert r[0]["cria"] == "111 / 222"

    def test_gemelar_com_uma_cria_numerada_e_outra_nao(self):
        p1 = date(2025, 1, 1)
        r = resumo_por_parto(
            [_parto(p1, gemelar=True, numero_cria_1="111", numero_cria_2=None)], [], [], [], hoje=HOJE,
        )
        assert r[0]["cria"] == "111 / S/N"

    def test_ultimo_item_da_lista_e_o_ultimo_parto_para_ultima_cria(self):
        """`ultima_cria` da Ficha (em animais.py) é derivado do último item
        desta lista — aqui confirmamos que o último item corresponde mesmo ao
        parto mais recente, já que a lista preserva a ordem de entrada
        (mais antigo primeiro)."""
        p1, p2 = date(2024, 1, 1), date(2025, 1, 1)
        r = resumo_por_parto(
            [_parto(p1, numero_cria_1="111"), _parto(p2, numero_cria_1="222")], [], [], [], hoje=HOJE,
        )
        assert r[-1]["cria"] == "222"
