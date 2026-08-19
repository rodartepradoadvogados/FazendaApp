"""
Programa reprodutivo — um teste por regra do modelo lógico (R1 a R9) descrito
no topo de `fazenda/rules/programa_reprodutivo.py`.

O módulo é regra pura (sem banco), então estes testes também são: montam
dicionários de Animal/Parto/Servico e conferem o resultado direto. Rápidos de
propósito — são a rede de proteção do denominador de todos os indicadores
reprodutivos do sistema.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from fazenda.rules.programa_reprodutivo import (
    ATIVA,
    INATIVA,
    MOTIVO_A_DESCARTAR,
    MOTIVO_BAIXADA,
    MOTIVO_DENTRO_PEV,
    MOTIVO_GESTANTE,
    MOTIVO_IMPUBERE,
    SUSPENSA,
    Ciclo,
    calcular_ciclo,
    ciclos_21_dias,
    conta_em_taxa,
    dias_aptos,
    elegivel_ia,
    elegivel_prenhez,
    estado_no_dia,
    montar_perfil,
    resultado_conhecido,
)

PEV = 45
HOJE = date(2026, 3, 1)
CICLO = Ciclo(indice=1, inicio=date(2026, 1, 1), fim=date(2026, 1, 21))


def _animal(numero="100", **kw):
    base = {
        "numero": numero, "ativo": True, "a_descartar": False, "data_baixa": None,
        "categoria_abrev": "Vaca", "data_nasc": date(2022, 1, 1), "raca": "Holandês",
        "peso_kg": 600.0,
    }
    return {**base, **kw}


def _perfil(animal=None, partos=(), servicos=(), aplicacoes=()):
    return montar_perfil(
        animal or _animal(), partos=list(partos), servicos=list(servicos),
        aplicacoes_iatf=list(aplicacoes),
    )


def _parto(d: date, numero="100"):
    return {"numero_matriz": numero, "data_parto": d}


def _servico(d: date, diagnostico=None, numero="100", perda=None):
    return {
        "numero_matriz": numero, "data_servico": d, "diagnostico": diagnostico,
        "data_perda_prenhez": perda, "tipo_servico": "IA", "protocolo": None,
    }


def _estado(perfil, d):
    return estado_no_dia(perfil, d, pev_dias=PEV, del_max_1o_servico=None)


# ═══════════════════ R1 — entrada e saída do programa ═══════════════════════
class TestR1EntradaNoPrograma:
    """ATIVA_PROGRAMA ↔ atingiu aptidão ∧ ¬a_descartar ∧ ¬baixada.
    `a_descartar` e baixa são as ÚNICAS portas de saída."""

    def test_vaca_pos_pev_esta_ativa_no_programa(self):
        p = _perfil(partos=[_parto(date(2025, 11, 1))])
        e = _estado(p, date(2026, 1, 15))
        assert e.situacao == ATIVA
        assert e.apta is True

    def test_marcada_a_descartar_sai_do_programa(self):
        p = _perfil(_animal(a_descartar=True), partos=[_parto(date(2025, 11, 1))])
        e = _estado(p, date(2026, 1, 15))
        assert e.situacao == INATIVA
        assert e.apta is False
        assert e.motivo == MOTIVO_A_DESCARTAR

    def test_baixada_sai_do_programa_a_partir_da_data_da_baixa(self):
        p = _perfil(_animal(data_baixa=date(2026, 1, 10)), partos=[_parto(date(2025, 11, 1))])
        assert _estado(p, date(2026, 1, 9)).situacao == ATIVA, "antes da baixa ainda contava"
        depois = _estado(p, date(2026, 1, 10))
        assert depois.situacao == INATIVA
        assert depois.motivo == MOTIVO_BAIXADA

    def test_novilha_sem_idade_nem_peso_ainda_nao_entrou_no_programa(self):
        nova = _animal(categoria_abrev="Novilha", data_nasc=date(2025, 6, 1), peso_kg=200.0)
        p = _perfil(nova)
        e = estado_no_dia(
            p, date(2026, 1, 15), pev_dias=PEV, idade_apta_dias=450, peso_apta_kg=300.0,
        )
        assert e.situacao == INATIVA
        assert e.motivo == MOTIVO_IMPUBERE


# ═══════════════════ R2 — suspensão temporária ══════════════════════════════
class TestR2Suspensao:
    """Suspensa ≠ inativa: continua no programa, só não conta como apta."""

    def test_dentro_do_pev_fica_suspensa_e_nao_apta(self):
        p = _perfil(partos=[_parto(date(2026, 1, 1))])
        e = _estado(p, date(2026, 1, 20))  # DEL 19 < PEV 45
        assert e.situacao == SUSPENSA
        assert e.apta is False
        assert e.motivo == MOTIVO_DENTRO_PEV

    def test_gestante_fica_suspensa_e_nao_apta(self):
        p = _perfil(
            partos=[_parto(date(2025, 9, 1))],
            servicos=[_servico(date(2025, 11, 1), diagnostico="POSITIVO")],
        )
        e = _estado(p, date(2026, 1, 15))
        assert e.situacao == SUSPENSA
        assert e.apta is False
        assert e.motivo == MOTIVO_GESTANTE


# ═══════════════════ R3/R4 — disponibilidade e aptidão ══════════════════════
class TestR4Aptidao:
    """APTA ↔ disponível ∧ ¬gestante ∧ (vazia ⊻ inseminada-sem-DG)."""

    def test_vazia_pos_pev_e_apta(self):
        p = _perfil(partos=[_parto(date(2025, 11, 1))])
        assert _estado(p, date(2026, 1, 15)).apta is True

    def test_inseminada_aguardando_dg_e_apta(self):
        p = _perfil(
            partos=[_parto(date(2025, 10, 1))],
            servicos=[_servico(date(2026, 1, 10), diagnostico=None)],
        )
        e = _estado(p, date(2026, 1, 15))
        assert e.apta is True, "inseminada sem DG continua no denominador"

    def test_diagnostico_negativo_volta_a_ser_apta(self):
        p = _perfil(
            partos=[_parto(date(2025, 10, 1))],
            servicos=[_servico(date(2025, 12, 1), diagnostico="NEGATIVO")],
        )
        assert _estado(p, date(2026, 1, 15)).apta is True

    def test_perda_de_prenhez_volta_a_ser_apta(self):
        p = _perfil(
            partos=[_parto(date(2025, 9, 1))],
            servicos=[_servico(date(2025, 10, 1), diagnostico="POSITIVO", perda=date(2025, 12, 20))],
        )
        assert _estado(p, date(2026, 1, 15)).apta is True

    def test_gestante_nunca_e_apta(self):
        """O bug de `indicadores._repro_benchmark`: o denominador somava
        `prenhes + vazias + inseminadas`. Vaca prenhe não pode ser inseminada,
        logo não pode estar no denominador de uma taxa de serviço."""
        p = _perfil(
            partos=[_parto(date(2025, 9, 1))],
            servicos=[_servico(date(2025, 11, 1), diagnostico="POSITIVO")],
        )
        assert _estado(p, date(2026, 1, 15)).apta is False


# ═══════════════════ R5 — BR ELIG, os 11 de 21 dias ═════════════════════════
class TestR5ElegivelParaInseminacao:
    """Não precisa estar apta os 21 dias — precisa de pelo menos 11."""

    def test_exatamente_11_dias_aptos_entra(self):
        # PEV termina em 11/01 → apta de 11/01 a 21/01 = 11 dias.
        p = _perfil(partos=[_parto(date(2025, 11, 27))])
        assert dias_aptos(p, CICLO, pev_dias=PEV) == 11
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is True

    def test_apenas_10_dias_aptos_fica_de_fora(self):
        # PEV termina em 12/01 → apta de 12/01 a 21/01 = 10 dias.
        p = _perfil(partos=[_parto(date(2025, 11, 28))])
        assert dias_aptos(p, CICLO, pev_dias=PEV) == 10
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is False

    def test_gestante_o_ciclo_todo_tem_zero_dias_aptos(self):
        p = _perfil(
            partos=[_parto(date(2025, 8, 1))],
            servicos=[_servico(date(2025, 10, 1), diagnostico="POSITIVO")],
        )
        assert dias_aptos(p, CICLO, pev_dias=PEV) == 0
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is False


# ═══════════════════ R6 — PG ELIG < BR ELIG ═════════════════════════════════
class TestR6ElegivelParaPrenhez:
    def test_presente_ate_o_fim_da_janela_entra_nos_dois(self):
        p = _perfil(partos=[_parto(date(2025, 10, 1))])
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is True
        assert elegivel_prenhez(p, CICLO, pev_dias=PEV) is True

    def test_descartada_durante_a_janela_entra_em_br_elig_mas_sai_de_pg_elig(self):
        """É exatamente isto que faz PG ELIG ser menor que BR ELIG."""
        baixa_no_meio = _animal(data_baixa=date(2026, 2, 5))  # depois do ciclo, dentro da janela de DG
        p = _perfil(baixa_no_meio, partos=[_parto(date(2025, 10, 1))])
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is True, "esteve apta o ciclo inteiro"
        assert elegivel_prenhez(p, CICLO, pev_dias=PEV) is False, "saiu antes de dar para avaliar"


# ═══════════════════ R7 — a regra dos 28 dias ═══════════════════════════════
class TestR7ResultadoConhecido:
    def test_servico_antigo_sem_dg_conta(self):
        s = _servico(HOJE - timedelta(days=30))
        assert conta_em_taxa(s, HOJE) is True

    def test_servico_de_27_dias_sem_dg_nao_conta(self):
        s = _servico(HOJE - timedelta(days=27))
        assert conta_em_taxa(s, HOJE) is False, "ainda não deu tempo de saber se pegou"

    def test_servico_recente_com_dg_negativo_conta(self):
        s = _servico(HOJE - timedelta(days=5), diagnostico="NEGATIVO")
        assert resultado_conhecido(s) is True
        assert conta_em_taxa(s, HOJE) is True

    def test_servico_recente_com_dg_positivo_conta(self):
        s = _servico(HOJE - timedelta(days=5), diagnostico="POSITIVO")
        assert conta_em_taxa(s, HOJE) is True

    def test_servico_recente_com_perda_registrada_conta(self):
        s = _servico(HOJE - timedelta(days=10), perda=HOJE - timedelta(days=2))
        assert conta_em_taxa(s, HOJE) is True

    def test_reinseminada_em_cio_de_repasse_conta_mesmo_sem_dg(self):
        """A nova IA prova que a anterior não pegou — o desfecho É conhecido."""
        s = _servico(HOJE - timedelta(days=20))
        assert conta_em_taxa(s, HOJE) is False
        assert conta_em_taxa(s, HOJE, servico_posterior=True) is True


# ═══════════════════ Ciclos com âncora configurável ═════════════════════════
class TestCiclosAncora:
    def test_ancora_no_inicio_corre_para_frente(self):
        cs = ciclos_21_dias(date(2026, 1, 1), modo="inicio", n_ciclos=3)
        assert cs[0].inicio == date(2026, 1, 1)
        assert cs[0].fim == date(2026, 1, 21), "21 dias inclusivos"
        assert cs[1].inicio == date(2026, 1, 22)
        assert cs[-1].fim == date(2026, 3, 4)

    def test_ancora_no_fim_corre_para_tras(self):
        cs = ciclos_21_dias(date(2026, 3, 4), modo="fim", n_ciclos=3)
        assert cs[-1].fim == date(2026, 3, 4), "a âncora é o último dia"
        assert cs[0].inicio == date(2026, 1, 1)
        assert [c.indice for c in cs] == [1, 2, 3], "devolve em ordem cronológica"

    def test_as_duas_ancoras_produzem_a_mesma_serie(self):
        frente = ciclos_21_dias(date(2026, 1, 1), modo="inicio", n_ciclos=4)
        tras = ciclos_21_dias(frente[-1].fim, modo="fim", n_ciclos=4)
        assert [(c.inicio, c.fim) for c in frente] == [(c.inicio, c.fim) for c in tras]

    def test_todo_ciclo_tem_21_dias(self):
        for c in ciclos_21_dias(date(2026, 1, 1), n_ciclos=5):
            assert c.dias == 21
            assert len(c.datas()) == 21

    def test_modo_invalido_e_rejeitado(self):
        with pytest.raises(ValueError):
            ciclos_21_dias(date(2026, 1, 1), modo="meio")


# ═══════════════════ R8/R9 — as métricas do ciclo ═══════════════════════════
class TestR8R9Metricas:
    def _rebanho(self):
        """4 vacas aptas o ciclo todo:
          "1" inseminada e prenhe        → BR ELIG, BRED, PG ELIG, PREG
          "2" inseminada e vazia         → BR ELIG, BRED, PG ELIG
          "3" nunca inseminada           → BR ELIG, PG ELIG   (a que o antigo perdia)
          "4" nunca inseminada, descartada durante a janela de DG
                                         → BR ELIG, mas NÃO PG ELIG
        """
        return [
            _perfil(_animal("1"), partos=[_parto(date(2025, 10, 1), "1")],
                    servicos=[_servico(date(2026, 1, 5), diagnostico="POSITIVO", numero="1")]),
            _perfil(_animal("2"), partos=[_parto(date(2025, 10, 1), "2")],
                    servicos=[_servico(date(2026, 1, 5), diagnostico="NEGATIVO", numero="2")]),
            _perfil(_animal("3"), partos=[_parto(date(2025, 10, 1), "3")]),
            _perfil(_animal("4", data_baixa=date(2026, 2, 5)),
                    partos=[_parto(date(2025, 10, 1), "4")]),
        ]

    def test_vaca_nunca_inseminada_permanece_no_denominador(self):
        """O erro central do cálculo antigo: o universo eram os animais que
        TÊM serviço, então a vaca elegível que ninguém inseminou sumia do
        denominador — inflando a taxa de serviço exatamente onde o manejo foi
        pior."""
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert len(r.br_elig) == 4
        assert "3" in r.br_elig, "elegível e nunca inseminada continua no denominador"
        assert len(r.bred) == 2
        assert r.taxa_servico == 50.0

    def test_vaca_que_concebeu_no_proprio_ciclo_continua_no_denominador(self):
        """Ela vira gestante no dia 5 do ciclo. Se a prenhez do próprio ciclo
        a desqualificasse, ela sairia do denominador E do numerador — sumindo
        dos dois lados da conta justamente por ter dado certo."""
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert "1" in r.br_elig
        assert "1" in r.bred
        assert "1" in r.preg

    def test_taxa_de_prenhez_usa_pg_elig_como_denominador(self):
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert len(r.pg_elig) == 3, "a descartada na janela de DG saiu"
        assert r.preg == ["1"]
        assert r.taxa_prenhez == round(100 * 1 / 3, 1)

    def test_pg_elig_menor_que_br_elig_quando_ha_descarte_na_janela(self):
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert "4" in r.br_elig, "estava apta o ciclo inteiro"
        assert "4" not in r.pg_elig, "saiu antes de dar para avaliar a prenhez"
        assert len(r.pg_elig) < len(r.br_elig)

    def test_taxa_de_concepcao_usa_so_servicos_com_resultado_conhecido(self):
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert r.servicos_com_resultado == 2
        assert r.taxa_concepcao == 50.0

    def test_gestante_de_ciclo_anterior_nao_entra_no_denominador(self):
        rebanho = self._rebanho()
        rebanho.append(_perfil(
            _animal("9"), partos=[_parto(date(2025, 8, 1), "9")],
            servicos=[_servico(date(2025, 10, 1), diagnostico="POSITIVO", numero="9")],
        ))
        r = calcular_ciclo(rebanho, CICLO, HOJE, pev_dias=PEV)
        assert "9" not in r.br_elig, "prenhe não pode ser inseminada"
        assert len(r.br_elig) == 4

    def test_descartada_nao_entra_no_denominador(self):
        rebanho = self._rebanho()
        rebanho.append(_perfil(
            _animal("5", a_descartar=True), partos=[_parto(date(2025, 10, 1), "5")],
        ))
        r = calcular_ciclo(rebanho, CICLO, HOJE, pev_dias=PEV)
        assert "5" not in r.br_elig
        assert len(r.br_elig) == 4

    def test_R9_prenhez_nao_e_servico_vezes_concepcao(self):
        """Teste-sentinela. O cálculo antigo fazia `taxa_prenhez = SR × CR / 100`
        em DOIS lugares (`indicadores.py:210` e `reproducao_dossie.py:148`). Os
        denominadores são diferentes — PG ELIG e BR ELIG — e as populações são
        acompanhadas em janelas diferentes. Se alguém reintroduzir o atalho,
        este teste quebra."""
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        atalho = round(r.taxa_servico * r.taxa_concepcao / 100, 1)
        assert atalho == 25.0
        assert r.taxa_prenhez == 33.3
        assert r.taxa_prenhez != atalho, (
            f"taxa de prenhez ({r.taxa_prenhez}%) não pode ser o produto "
            f"serviço × concepção ({atalho}%)"
        )

    def test_ciclo_sem_animal_elegivel_devolve_none_em_vez_de_zero(self):
        r = calcular_ciclo([], CICLO, HOJE, pev_dias=PEV)
        assert r.taxa_servico is None
        assert r.taxa_prenhez is None
        assert r.taxa_concepcao is None

    def test_dict_de_saida_traz_o_drill_down_de_quem_entrou(self):
        d = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV).para_dict()
        assert d["br_elig"] == 4 and d["bred"] == 2 and d["pg_elig"] == 3 and d["preg"] == 1
        assert d["animais"]["br_elig"] == ["1", "2", "3", "4"]
        assert d["animais"]["preg"] == ["1"]


# ═══════════ Retrofit: o painel de benchmark da Capa (indicadores.py) ═══════
class TestRetrofitBenchmarkDaCapa:
    """`indicadores._repro_benchmark` alimenta a Capa, os Indicadores e o
    Manual da Fazenda. Tinha os mesmos três defeitos, agora corrigidos."""

    def _valores(self, animais, servicos, estados, desde=date(2026, 1, 1)):
        from fazenda.rules.indicadores import _repro_benchmark

        lista = _repro_benchmark(
            animais, servicos, [], desde, categoria="todas", estados=estados, hoje=HOJE,
        )
        return {x["chave"]: x["valor"] for x in lista}

    def test_gestante_saiu_do_denominador_da_taxa_de_servico(self):
        """Antes: `aptas = prenhes + vazias + inseminadas`, com a prenhe
        dentro. Uma vaca prenhe não pode ser inseminada — inflava o
        denominador e afundava a taxa de serviço."""
        animais = [{"numero": "1"}, {"numero": "2"}, {"numero": "3"}]
        estados = {"1": "apta", "2": "apta", "3": "gestante"}
        servicos = [{"numero_matriz": "1", "data_servico": date(2026, 1, 5), "diagnostico": "POSITIVO"}]
        v = self._valores(animais, servicos, estados)
        assert v["taxa_servico"] == 50.0, "1 servida de 2 APTAS — não de 3"

    def test_atrasada_continua_no_denominador(self):
        """A vaca que deveria ter sido inseminada e não foi é justamente a que
        o indicador precisa enxergar."""
        animais = [{"numero": "1"}, {"numero": "2"}]
        estados = {"1": "apta", "2": "atrasada"}
        servicos = [{"numero_matriz": "1", "data_servico": date(2026, 1, 5), "diagnostico": "POSITIVO"}]
        v = self._valores(animais, servicos, estados)
        assert v["taxa_servico"] == 50.0

    def test_servico_dos_ultimos_27_dias_sem_dg_nao_conta(self):
        """R7 — ainda não deu tempo de saber se pegou."""
        animais = [{"numero": "1"}, {"numero": "2"}]
        estados = {"1": "apta", "2": "apta"}
        recente = [{"numero_matriz": "1", "data_servico": HOJE - timedelta(days=5), "diagnostico": None}]
        assert self._valores(animais, recente, estados)["taxa_servico"] == 0.0

        com_dg = [{"numero_matriz": "1", "data_servico": HOJE - timedelta(days=5), "diagnostico": "NEGATIVO"}]
        assert self._valores(animais, com_dg, estados)["taxa_servico"] == 50.0, (
            "com DG negativo o desfecho é conhecido e o serviço volta a contar"
        )

    def test_prenhez_deixou_de_ser_servico_vezes_concepcao(self):
        """R9 no painel da Capa. Divergem quando um animal é inseminado mais de
        uma vez no período: `taxa_servico` conta ANIMAIS servidos e
        `taxa_concepcao` conta SERVIÇOS com resultado."""
        animais = [{"numero": "1"}, {"numero": "2"}]
        estados = {"1": "apta", "2": "apta"}
        servicos = [
            {"numero_matriz": "1", "data_servico": date(2026, 1, 5), "diagnostico": "NEGATIVO"},
            {"numero_matriz": "1", "data_servico": date(2026, 1, 20), "diagnostico": "POSITIVO"},
        ]
        v = self._valores(animais, servicos, estados)
        atalho = round(v["taxa_servico"] * v["taxa_concepcao"] / 100, 1)
        assert v["taxa_servico"] == 50.0 and v["taxa_concepcao"] == 50.0
        assert atalho == 25.0
        assert v["taxa_prenhez_ciclo"] == 50.0
        assert v["taxa_prenhez_ciclo"] != atalho

    def test_sem_estados_ao_vivo_cai_no_sit_rep_mas_ja_sem_as_prenhes(self):
        """Chamador legado (só a lista de animais, sem registros): continua
        lendo `sit_rep`, mas a prenhe já não entra no denominador."""
        animais = [
            {"numero": "1", "sit_rep": "Vaz."}, {"numero": "2", "sit_rep": "Ins."},
            {"numero": "3", "sit_rep": "Ges."},
        ]
        servicos = [{"numero_matriz": "1", "data_servico": date(2026, 1, 5), "diagnostico": "POSITIVO"}]
        v = self._valores(animais, servicos, estados=None)
        assert v["taxa_servico"] == 50.0, "denominador = vazia + inseminada, sem a gestante"


# ═══════════════ Janela de DG incompleta — o ciclo que ainda não fechou ══════
class TestJanelaDgIncompleta:
    """O denominador da prenhez (PG ELIG) não tem a porta dos 28 dias; o
    numerador (PREG) tem. Enquanto a janela não fecha, a taxa sai subestimada
    por construção — e a tela não pode comparar esse ciclo com a meta."""

    def _vaca(self, hoje: date, data_servico: date, diagnostico=None):
        return _perfil(
            partos=[_parto(hoje - timedelta(days=200))],
            servicos=[_servico(data_servico, diagnostico)],
        )

    def test_ciclo_recem_encerrado_marca_janela_aberta(self):
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=hoje - timedelta(days=21), fim=hoje - timedelta(days=1))
        r = calcular_ciclo([self._vaca(hoje, ciclo.inicio)], ciclo, hoje, pev_dias=PEV)
        assert r.janela_dg_completa is False
        assert r.para_dict()["janela_dg_completa"] is False

    def test_ciclo_antigo_marca_janela_fechada(self):
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=date(2026, 1, 1), fim=date(2026, 1, 21))
        r = calcular_ciclo([self._vaca(hoje, date(2026, 1, 5))], ciclo, hoje, pev_dias=PEV)
        assert r.janela_dg_completa is True

    def test_a_fronteira_e_exatamente_dias_resultado(self):
        hoje = date(2026, 3, 1)
        fecha = Ciclo(indice=1, inicio=hoje - timedelta(days=48), fim=hoje - timedelta(days=28))
        abre = Ciclo(indice=1, inicio=hoje - timedelta(days=47), fim=hoje - timedelta(days=27))
        assert calcular_ciclo([], fecha, hoje, pev_dias=PEV).janela_dg_completa is True
        assert calcular_ciclo([], abre, hoje, pev_dias=PEV).janela_dg_completa is False

    def test_a_flag_acompanha_dias_resultado_configurado(self):
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=hoje - timedelta(days=30), fim=hoje - timedelta(days=10))
        assert calcular_ciclo([], ciclo, hoje, pev_dias=PEV,
                              dias_resultado=28).janela_dg_completa is False
        assert calcular_ciclo([], ciclo, hoje, pev_dias=PEV,
                              dias_resultado=5).janela_dg_completa is True

    def test_a_prenhez_do_ciclo_aberto_e_subestimada_de_proposito(self):
        """A prova do problema. Duas vacas inseminadas no mesmo ciclo recém
        encerrado: a 100 já teve o DG lançado, a 200 ainda não — e nem poderia,
        porque não passaram 28 dias da IA. As duas estão no PG ELIG; só a 100
        está no PREG. A tela mostraria 50% de prenhez, quando o que se sabe até
        aqui é "1 de 1 diagnosticada". Não houve piora de manejo nenhuma: falta
        tempo. É para isso que serve `janela_dg_completa`."""
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=hoje - timedelta(days=21), fim=hoje - timedelta(days=1))
        diagnosticada = _perfil(
            _animal("100"),
            partos=[_parto(hoje - timedelta(days=200), "100")],
            servicos=[_servico(ciclo.inicio, "POSITIVO", "100")],
        )
        aguardando = _perfil(
            _animal("200"),
            partos=[_parto(hoje - timedelta(days=200), "200")],
            servicos=[_servico(ciclo.fim, None, "200")],
        )
        r = calcular_ciclo([diagnosticada, aguardando], ciclo, hoje, pev_dias=PEV)
        assert sorted(r.pg_elig) == ["100", "200"], "as duas no denominador"
        assert r.preg == ["100"], "só a diagnosticada no numerador"
        assert r.taxa_prenhez == 50.0
        assert r.janela_dg_completa is False, "o aviso que impede ler isso como fracasso"
