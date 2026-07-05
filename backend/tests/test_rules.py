"""
Testes das regras de negócio da fazenda (Seção 5 do CONTEXTO_PROJETO_FAZENDA.md).
Rodados com: python -m pytest backend/tests/ -v
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from fazenda.rules.bst import avaliar_bst
from fazenda.rules.dry_off import calcular_secagem
from fazenda.rules.gestation import calcular_parto_provavel, dias_gestacao
from fazenda.rules.iatf import calcular_necessidade_hormonios, selecionar_candidatas_iatf
from fazenda.rules.indicadores import calcular_indicadores
from fazenda.rules.scratch_pev import calcular_pev, calcular_scratch


# ============================================================
# GESTAÇÃO
# ============================================================

class TestGestacao:
    def test_holandes_280_dias(self):
        assert dias_gestacao("Holandês") == 280
        assert dias_gestacao("holandes") == 280

    def test_girolando_287_dias(self):
        assert dias_gestacao("Girolando") == 287
        assert dias_gestacao("girolando") == 287

    def test_gir_zebu_295_dias(self):
        assert dias_gestacao("Gir") == 295
        assert dias_gestacao("Zebu") == 295
        assert dias_gestacao("Nelore") == 295

    def test_raca_desconhecida_usa_default(self):
        assert dias_gestacao("Angus") == 287
        assert dias_gestacao(None) == 287

    def test_parto_provavel_girolando(self):
        data_servico = date(2026, 3, 1)
        res = calcular_parto_provavel(data_servico, "Girolando")
        assert res.data_parto_provavel == date(2026, 3, 1) + timedelta(days=287)
        assert res.dias_gestacao == 287

    def test_parto_provavel_holandes(self):
        data_servico = date(2026, 1, 15)
        res = calcular_parto_provavel(data_servico, "Holandês")
        assert res.data_parto_provavel == date(2026, 1, 15) + timedelta(days=280)


# ============================================================
# SECAGEM
# ============================================================

class TestSecagem:
    def test_vaca_seca_60_dias_antes(self):
        parto = date(2026, 12, 1)
        res = calcular_secagem("001", parto, ordem_parto=2, em_lactacao=True)
        assert res.deve_secar is True
        assert res.data_secagem == parto - timedelta(days=60)

    def test_novilha_primeira_cria_nao_seca(self):
        parto = date(2026, 12, 1)
        res = calcular_secagem("002", parto, ordem_parto=0, em_lactacao=True)
        assert res.deve_secar is False
        assert "novilha" in res.motivo_exclusao.lower()

    def test_animal_nao_lactante_nao_seca(self):
        parto = date(2026, 12, 1)
        res = calcular_secagem("003", parto, ordem_parto=3, em_lactacao=False)
        assert res.deve_secar is False

    def test_ordem_parto_none_trata_como_vaca(self):
        """Quando não sabemos a ordem de parto e está em lactação, secamos."""
        parto = date(2026, 12, 1)
        res = calcular_secagem("004", parto, ordem_parto=None, em_lactacao=True)
        assert res.deve_secar is True


# ============================================================
# SCRATCH
# ============================================================

class TestScratch:
    def test_scratch_14_dias_apos_servico(self):
        data_servico = date(2026, 7, 1)
        res = calcular_scratch("001", data_servico, diagnostico_ultimo=None)
        assert res.ativo is True
        assert res.data_scratch == date(2026, 7, 1) + timedelta(days=14)

    def test_diagnostico_negativo_cancela_scratch(self):
        data_servico = date(2026, 7, 1)
        res = calcular_scratch("001", data_servico, diagnostico_ultimo="NEGATIVO")
        assert res.ativo is False
        assert "negativo" in res.motivo_cancelamento.lower()

    def test_diagnostico_positivo_nao_cancela(self):
        """Prenha confirmada: scratch não cancela (já não é candidata a novo serviço)."""
        data_servico = date(2026, 7, 1)
        res = calcular_scratch("001", data_servico, diagnostico_ultimo="POSITIVO")
        assert res.ativo is True

    def test_diagnostico_aberto_nao_cancela(self):
        data_servico = date(2026, 6, 20)
        res = calcular_scratch("001", data_servico, diagnostico_ultimo="ABERTO")
        assert res.ativo is True


# ============================================================
# PEV
# ============================================================

class TestPEV:
    def test_pev_45_dias_apos_parto(self):
        data_parto = date(2026, 5, 1)
        res = calcular_pev("001", data_parto, data_referencia=date(2026, 5, 20))
        assert not res.liberado
        assert res.data_pev == date(2026, 5, 1) + timedelta(days=45)
        assert res.dias_restantes == 26

    def test_pev_liberado_apos_45_dias(self):
        data_parto = date(2026, 5, 1)
        res = calcular_pev("001", data_parto, data_referencia=date(2026, 6, 20))
        assert res.liberado is True
        assert res.dias_restantes == 0

    def test_pev_exatamente_no_dia_45(self):
        data_parto = date(2026, 5, 1)
        data_pev_esperada = date(2026, 5, 1) + timedelta(days=45)
        res = calcular_pev("001", data_parto, data_referencia=data_pev_esperada)
        assert res.liberado is True


# ============================================================
# IATF
# ============================================================

class TestIATF:
    def _animal(self, numero, sit_rep, diag=None, del_dias=100):
        return {"numero_matriz": numero, "sit_rep": sit_rep, "del_dias": del_dias, "diagnostico_ultimo": diag}

    def test_vazia_apta_e_candidata(self):
        animais = [self._animal("001", "Vaz. apt.")]
        candidatas = selecionar_candidatas_iatf(animais)
        assert len(candidatas) == 1
        assert candidatas[0].numero_matriz == "001"

    def test_vazia_atraso_e_candidata(self):
        animais = [self._animal("002", "Vaz. atr.")]
        candidatas = selecionar_candidatas_iatf(animais)
        assert len(candidatas) == 1

    def test_diagnostico_negativo_e_candidata(self):
        animais = [self._animal("003", "Ins.", diag="NEGATIVO")]
        candidatas = selecionar_candidatas_iatf(animais)
        assert len(candidatas) == 1
        assert candidatas[0].motivo == "Diagnóstico negativo"

    def test_prenha_nao_e_candidata(self):
        animais = [self._animal("004", "Ges.", diag="POSITIVO")]
        candidatas = selecionar_candidatas_iatf(animais)
        assert len(candidatas) == 0

    def test_calcula_doses_10_candidatas(self):
        n = 10
        nec = calcular_necessidade_hormonios(n)
        assert nec.implantes == 10
        assert nec.sincrodiol_ml == 20.0  # 10 × 2ml
        assert nec.sincroforte_ml == 25.0  # 10 × 2.5ml
        assert nec.estron_ml == 40.0  # 10 × (2+2)ml
        assert nec.sincrocp_ml == 10.0  # 10 × 1ml

    def test_zero_candidatas(self):
        nec = calcular_necessidade_hormonios(0)
        assert nec.implantes == 0
        assert nec.estron_ml == 0.0


# ============================================================
# BST
# ============================================================

class TestBST:
    def test_elegivel(self):
        res = avaliar_bst(
            numero_matriz="001",
            grupo_primario="02 - VACAS ALTA",
            del_dias=90,
            data_secagem=date.today() + timedelta(days=30),
            data_referencia=date.today(),
        )
        assert res.elegivel is True

    def test_del_insuficiente(self):
        res = avaliar_bst(
            numero_matriz="002",
            grupo_primario="02 - VACAS ALTA",
            del_dias=45,
            data_secagem=date.today() + timedelta(days=60),
            data_referencia=date.today(),
        )
        assert res.elegivel is False
        assert "DEL" in res.motivo_exclusao

    def test_grupo_nao_lactacao(self):
        res = avaliar_bst(
            numero_matriz="003",
            grupo_primario="05 - SECAS",
            del_dias=100,
            data_secagem=None,
            data_referencia=date.today(),
        )
        assert res.elegivel is False

    def test_prox_secagem(self):
        """Animal em lactação mas secar em 10 dias — exclui."""
        res = avaliar_bst(
            numero_matriz="004",
            grupo_primario="01 - NOV. ALTA",
            del_dias=90,
            data_secagem=date.today() + timedelta(days=10),
            data_referencia=date.today(),
        )
        assert res.elegivel is False
        assert "secar" in res.motivo_exclusao.lower()


# ============================================================
# INDICADORES
# ============================================================

class TestIndicadores:
    def _dados(self):
        animais = [
            {"grupo_primario": "01 - NOV. ALTA", "sit_rep": "Ges.", "del_dias": 120, "ult_cl_kg": 25.0},
            {"grupo_primario": "02 - VACAS ALTA", "sit_rep": "Vaz. apt.", "del_dias": 80, "ult_cl_kg": 30.0},
            {"grupo_primario": "05 - SECAS", "sit_rep": "Ges.", "del_dias": None, "ult_cl_kg": None},
            {"grupo_primario": "12 - NOV. PRENHES", "sit_rep": "Ins.", "del_dias": None, "ult_cl_kg": None},
        ]
        servicos = [
            {"diagnostico": "POSITIVO", "data_servico": date(2026, 6, 1), "raca_matriz": "Holandês"},
            {"diagnostico": "NEGATIVO", "data_servico": date(2026, 5, 1), "raca_matriz": "Girolando"},
        ]
        partos = [
            {"numero_matriz": "100", "data_parto": date(2024, 1, 1)},
            {"numero_matriz": "100", "data_parto": date(2025, 1, 1)},  # intervalo 366d
        ]
        return animais, servicos, partos

    def test_composicao_e_reproducao(self):
        animais, servicos, partos = self._dados()
        r = calcular_indicadores(animais, servicos, partos, data_ref=date(2026, 7, 5))
        assert r["rebanho"]["total"] == 4
        assert r["rebanho"]["vacas_lactacao"] == 2  # grupos 01 e 02
        assert r["rebanho"]["vacas_secas"] == 1
        assert r["reproducao"]["prenhes"] == 2
        assert r["reproducao"]["vazias"] == 1
        assert r["reproducao"]["inseminadas"] == 1
        assert r["reproducao"]["taxa_prenhez_pct"] == 50.0  # 2/4
        assert r["reproducao"]["taxa_concepcao_pct"] == 50.0  # 1 pos / (1+1)

    def test_iep_e_producao(self):
        animais, servicos, partos = self._dados()
        r = calcular_indicadores(animais, servicos, partos, data_ref=date(2026, 7, 5))
        assert r["reproducao"]["iep_dias"] == 366
        assert r["producao"]["vacas_com_producao"] == 2
        assert r["producao"]["producao_total_dia_kg"] == 55.0
        assert r["producao"]["del_medio"] == 100.0  # (120 + 80) / 2

    def test_rebanho_vazio_nao_quebra(self):
        r = calcular_indicadores([], [], [], data_ref=date(2026, 7, 5))
        assert r["rebanho"]["total"] == 0
        assert r["reproducao"]["taxa_prenhez_pct"] is None
        assert r["reproducao"]["iep_dias"] is None


# ============================================================
# ALIMENTAÇÃO
# ============================================================

class TestAlimentacao:
    def test_consumo_total_cruza_dieta_com_efetivo(self):
        from fazenda.rules.alimentacao import calcular_consumo
        dietas = [
            {"lote": 1, "categoria": "Novilhas Alta", "ingrediente": "Silagem", "quantidade": 30.0, "unidade": "kg"},
            {"lote": 2, "categoria": "Vacas Alta", "ingrediente": "Silagem", "quantidade": 30.0, "unidade": "kg"},
        ]
        animais = [
            {"grupo_primario": "01 - NOV. ALTA"},
            {"grupo_primario": "01 - NOV. ALTA"},
            {"grupo_primario": "02 - VACAS ALTA"},
        ]
        r = calcular_consumo(dietas, animais)
        # lote 1 tem 2 animais, lote 2 tem 1 → 30*2 + 30*1 = 90 kg
        total = {x["ingrediente"]: x["consumo_dia"] for x in r["consumo_total"]}
        assert total["Silagem"] == 90.0
        lote1 = next(l for l in r["por_lote"] if l["lote"] == 1)
        assert lote1["efetivo"] == 2
        assert lote1["itens"][0]["consumo_dia"] == 60.0


# ============================================================
# PRODUÇÃO
# ============================================================

class TestProducao:
    def test_serie_curva_e_ranking(self):
        from fazenda.rules.producao import calcular_producao
        controles = [
            {"numero_matriz": "100", "data_controle": date(2026, 6, 1), "producao_kg": 20.0, "del_no_controle": 40},
            {"numero_matriz": "100", "data_controle": date(2026, 6, 8), "producao_kg": 24.0, "del_no_controle": 47},
            {"numero_matriz": "200", "data_controle": date(2026, 6, 1), "producao_kg": 30.0, "del_no_controle": 100},
        ]
        r = calcular_producao(controles)
        assert r["totais"]["vacas"] == 2
        assert r["totais"]["controles"] == 3
        # série: 2026-06-01 tem 2 vacas (20 e 30) média 25
        s0 = next(s for s in r["serie_temporal"] if s["data"] == "2026-06-01")
        assert s0["vacas"] == 2 and s0["media_kg"] == 25.0
        # curva: faixa 31-60 tem controle de 20; ranking encabeçado pela 200 (média 30)
        assert r["por_animal"][0]["numero_matriz"] == "200"
        assert r["por_animal"][0]["pico_kg"] == 30.0

    def test_sem_controles_nao_quebra(self):
        from fazenda.rules.producao import calcular_producao
        r = calcular_producao([])
        assert r["totais"]["vacas"] == 0
        assert r["serie_temporal"] == []
