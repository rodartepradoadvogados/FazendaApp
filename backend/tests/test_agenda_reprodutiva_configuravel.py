"""
Motor de filtro dos cards configuráveis da Agenda Reprodutiva
(`fazenda.rules.agenda_reprodutiva_configuravel`).

Função pura: monta os dois dicts (`animais`, `estados`) à mão, do mesmo jeito
que o endpoint faria a partir do banco, sem precisar de Session.
"""
from __future__ import annotations

from fazenda.rules.agenda_reprodutiva_configuravel import avaliar_card, dentro_de_algum_periodo
from fazenda.rules.estado_reprodutivo import APTA, ATRASADA, GESTANTE, INSEMINADA, PEV


def _animal(numero, categoria="novilha", lote="Lote 3", a_descartar=False):
    return {
        "numero": numero, "categoria_abrev": categoria, "grupo_primario": lote,
        "a_descartar": a_descartar,
    }


def _estado(estado, **extra):
    base = {"estado": estado, "del_dias": None, "dias_gestacao": None, "dias_desde_servico": None}
    base.update(extra)
    return base


class TestDentroDeAlgumPeriodo:
    def test_lista_vazia_sempre_casa(self):
        assert dentro_de_algum_periodo(999, []) is True
        assert dentro_de_algum_periodo(None, []) is True

    def test_dias_none_com_periodos_nao_casa(self):
        assert dentro_de_algum_periodo(None, [(1, 29)]) is False

    def test_um_periodo(self):
        assert dentro_de_algum_periodo(15, [(1, 29)]) is True
        assert dentro_de_algum_periodo(30, [(1, 29)]) is False

    def test_or_entre_varios_periodos(self):
        periodos = [(1, 29), (60, 90)]
        assert dentro_de_algum_periodo(10, periodos) is True
        assert dentro_de_algum_periodo(75, periodos) is True
        assert dentro_de_algum_periodo(45, periodos) is False

    def test_limites_inclusivos(self):
        assert dentro_de_algum_periodo(1, [(1, 29)]) is True
        assert dentro_de_algum_periodo(29, [(1, 29)]) is True


class TestEixoCategoria:
    def test_todas_inclui_vaca_e_novilha(self):
        animais = [_animal("1", "novilha"), _animal("2", "vaca")]
        estados = {"1": _estado(PEV, del_dias=10), "2": _estado(PEV, del_dias=10)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert {a["numero"] for a in r} == {"1", "2"}

    def test_vaca_exclui_novilha(self):
        animais = [_animal("1", "novilha"), _animal("2", "vaca")]
        estados = {"1": _estado(PEV, del_dias=10), "2": _estado(PEV, del_dias=10)}
        r = avaliar_card(
            categoria="vaca", lotes=[], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert [a["numero"] for a in r] == ["2"]

    def test_bezerra_nunca_entra(self):
        animais = [_animal("1", "bezerra")]
        estados = {"1": _estado(PEV, del_dias=10)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert r == []


class TestEixoLote:
    def test_lista_vazia_e_todos_os_lotes(self):
        animais = [_animal("1", lote="Lote 1"), _animal("2", lote="Lote 9")]
        estados = {"1": _estado(PEV, del_dias=5), "2": _estado(PEV, del_dias=5)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert len(r) == 2

    def test_filtra_por_um_lote(self):
        animais = [_animal("1", lote="Lote 1"), _animal("2", lote="Lote 9")]
        estados = {"1": _estado(PEV, del_dias=5), "2": _estado(PEV, del_dias=5)}
        r = avaliar_card(
            categoria="todas", lotes=["Lote 1"], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert [a["numero"] for a in r] == ["1"]

    def test_varios_lotes_e_case_insensitive(self):
        animais = [_animal("1", lote="lote 1"), _animal("2", lote="Lote 9"), _animal("3", lote="Lote 5")]
        estados = {n: _estado(PEV, del_dias=5) for n in ("1", "2", "3")}
        r = avaliar_card(
            categoria="todas", lotes=["LOTE 1", "lote 9"], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert {a["numero"] for a in r} == {"1", "2"}


class TestSituacaoPev:
    def test_so_pev_sem_periodo_mostra_todos(self):
        animais = [_animal("1"), _animal("2")]
        estados = {"1": _estado(PEV, del_dias=3), "2": _estado(PEV, del_dias=40)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert len(r) == 2

    def test_periodo_manual_filtra_por_dias_desde_o_parto(self):
        animais = [_animal("1"), _animal("2")]
        estados = {"1": _estado(PEV, del_dias=3), "2": _estado(PEV, del_dias=40)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="pev", periodos=[(0, 10)],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert [a["numero"] for a in r] == ["1"]

    def test_nao_pev_nao_entra(self):
        animais = [_animal("1")]
        estados = {"1": _estado(APTA)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert r == []


class TestSituacaoInseminada:
    def test_periodos_multiplos_substituem_os_3_cortes_fixos(self):
        """Um único card cobre o que antes eram 3 listas fixas (1-29/30-59/60+)."""
        animais = [_animal(str(i)) for i in range(4)]
        estados = {
            "0": _estado(INSEMINADA, dias_desde_servico=5),
            "1": _estado(INSEMINADA, dias_desde_servico=45),
            "2": _estado(INSEMINADA, dias_desde_servico=70),
            "3": _estado(INSEMINADA, dias_desde_servico=200),
        }
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="inseminada",
            periodos=[(1, 29), (30, 59), (60, 999)],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert {a["numero"] for a in r} == {"0", "1", "2", "3"}

    def test_gestante_ou_pev_nao_entram_em_inseminada(self):
        animais = [_animal("1"), _animal("2")]
        estados = {"1": _estado(GESTANTE, dias_gestacao=100), "2": _estado(PEV, del_dias=5)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="inseminada", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert r == []


class TestSituacaoGestante:
    def test_periodo_de_dias_de_gestacao(self):
        animais = [_animal("1"), _animal("2")]
        estados = {"1": _estado(GESTANTE, dias_gestacao=250), "2": _estado(GESTANTE, dias_gestacao=100)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="gestante", periodos=[(200, 295)],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert [a["numero"] for a in r] == ["1"]


class TestSituacaoVazia:
    def _duas_vazias(self):
        animais = [_animal("1"), _animal("2")]
        estados = {"1": _estado(APTA), "2": _estado(ATRASADA)}
        return animais, estados

    def test_sem_marcar_nenhum_checkbox_traz_as_duas(self):
        animais, estados = self._duas_vazias()
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="vazia", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert {a["numero"] for a in r} == {"1", "2"}

    def test_somente_atrasadas(self):
        animais, estados = self._duas_vazias()
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="vazia", periodos=[],
            somente_atrasadas=True, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert [a["numero"] for a in r] == ["2"]

    def test_exceto_atrasadas(self):
        animais, estados = self._duas_vazias()
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="vazia", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=True, animais=animais, estados=estados,
        )
        assert [a["numero"] for a in r] == ["1"]

    def test_inseminada_nao_e_vazia(self):
        animais = [_animal("1")]
        estados = {"1": _estado(INSEMINADA, dias_desde_servico=5)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="vazia", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert r == []


class TestSituacaoVaziaAtrasada:
    def test_atalho_equivale_a_vazia_mais_somente_atrasadas(self):
        animais = [_animal("1"), _animal("2")]
        estados = {"1": _estado(APTA), "2": _estado(ATRASADA)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="vazia_atrasada", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert [a["numero"] for a in r] == ["2"]


class TestSituacaoADescartar:
    def test_puxa_so_quem_esta_marcado(self):
        animais = [_animal("1", a_descartar=True), _animal("2", a_descartar=False)]
        estados = {"1": _estado(APTA), "2": _estado(APTA)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="a_descartar", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert [a["numero"] for a in r] == ["1"]

    def test_nao_precisa_de_estado_ao_vivo_calculado(self):
        """Animal marcado a_descartar sem entrada em `estados` (ex.: nunca
        classificado) ainda assim entra — a_descartar não depende do motor
        de situação reprodutiva."""
        animais = [_animal("1", a_descartar=True)]
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="a_descartar", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados={},
        )
        assert [a["numero"] for a in r] == ["1"]

    def test_marcado_a_descartar_some_das_outras_situacoes(self):
        """Mesma regra de agenda_veterinario.classificar_rebanho: marcado a
        descartar fica fora de qualquer situação reprodutiva."""
        animais = [_animal("1", a_descartar=True)]
        estados = {"1": _estado(PEV, del_dias=5)}
        r = avaliar_card(
            categoria="todas", lotes=[], situacao="pev", periodos=[],
            somente_atrasadas=False, exceto_atrasadas=False, animais=animais, estados=estados,
        )
        assert r == []
