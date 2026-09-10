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
        # Raça não mapeada cai no ponto médio (arredondado) da faixa editável
        # gestacao_dias_min/max (280-295, ver fazenda.rules.parametros) = 288.
        assert dias_gestacao("Angus") == 288
        assert dias_gestacao(None) == 288

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
    """Candidata a IATF sai do ESTADO AO VIVO, não mais do `sit_rep` congelado.

    O `sit_rep` continua chegando na entrada porque a tela ainda o exibe, mas
    ele não decide nada — vários testes abaixo o deixam de propósito
    contradizendo o estado, que é exatamente a situação que a migração
    resolve."""

    def _animal(self, numero, sit_rep=None, diag=None):
        return {"numero_matriz": numero, "sit_rep": sit_rep, "diagnostico_ultimo": diag}

    def _estado(self, numero, estado, del_dias=100):
        return {numero: {"estado": estado, "del_dias": del_dias}}

    def test_apta_e_candidata(self):
        candidatas = selecionar_candidatas_iatf(
            [self._animal("001")], self._estado("001", "apta"),
        )
        assert len(candidatas) == 1
        assert candidatas[0].numero_matriz == "001"
        assert candidatas[0].motivo == "Vazia apta"
        assert candidatas[0].estado_rotulo == "Apta"

    def test_atrasada_e_candidata(self):
        candidatas = selecionar_candidatas_iatf(
            [self._animal("002")], self._estado("002", "atrasada"),
        )
        assert len(candidatas) == 1
        assert candidatas[0].motivo == "Vazia em atraso"

    def test_diagnostico_negativo_refina_o_motivo(self):
        """Deixou de ser critério paralelo. Quem teve DG negativo e já passou do
        PEV cai em apta/atrasada como qualquer outra; o negativo só troca o
        texto que o produtor lê."""
        candidatas = selecionar_candidatas_iatf(
            [self._animal("003", diag="NEGATIVO")], self._estado("003", "apta"),
        )
        assert len(candidatas) == 1
        assert candidatas[0].motivo == "Diagnóstico negativo"

    def test_del_dias_vem_do_estado_calculado(self):
        candidatas = selecionar_candidatas_iatf(
            [self._animal("003")], self._estado("003", "apta", del_dias=87),
        )
        assert candidatas[0].del_dias == 87

    def test_gestante_nao_e_candidata(self):
        candidatas = selecionar_candidatas_iatf(
            [self._animal("004", diag="POSITIVO")], self._estado("004", "gestante"),
        )
        assert candidatas == []

    def test_dentro_do_pev_nao_e_candidata_mesmo_com_dg_negativo(self):
        """O furo mais caro do critério antigo: o ramo do diagnóstico negativo
        não testava PEV, então vaca recém-parida com DG negativo do ciclo
        anterior entrava na lista do curral."""
        candidatas = selecionar_candidatas_iatf(
            [self._animal("005", diag="NEGATIVO")], self._estado("005", "pev", del_dias=20),
        )
        assert candidatas == []

    def test_em_protocolo_nao_e_candidata(self):
        """Vaca com D0 implantado hoje não pode ser oferecida de novo."""
        candidatas = selecionar_candidatas_iatf(
            [self._animal("006")], self._estado("006", "em_protocolo"),
        )
        assert candidatas == []

    def test_inseminada_aguardando_dg_nao_e_candidata(self):
        candidatas = selecionar_candidatas_iatf(
            [self._animal("007")], self._estado("007", "inseminada"),
        )
        assert candidatas == []

    def test_novilha_sem_idade_ou_peso_nao_e_candidata(self):
        candidatas = selecionar_candidatas_iatf(
            [self._animal("008")], self._estado("008", "nao_apta"),
        )
        assert candidatas == []

    def test_animal_fora_do_mapa_de_estados_nao_e_candidata(self):
        """É assim que a regra R1 chega aqui: quem chamou tira do mapa o animal
        marcado a descartar ou baixado, e ele simplesmente não tem estado."""
        candidatas = selecionar_candidatas_iatf([self._animal("009")], {})
        assert candidatas == []

    def test_sit_rep_congelado_nao_manda_mais(self):
        """Os dois lados do defeito, num teste só: o CSV diz que a vaca 010 está
        prenhe (e ela entra, porque os registros dizem que está apta) e que a
        011 está vazia apta (e ela sai, porque engravidou pelo app)."""
        candidatas = selecionar_candidatas_iatf(
            [self._animal("010", sit_rep="Ges."), self._animal("011", sit_rep="Vaz. apt.")],
            {**self._estado("010", "apta"), **self._estado("011", "gestante")},
        )
        assert [c.numero_matriz for c in candidatas] == ["010"]

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

    def test_lote_novo_fora_do_01_02_03_fica_de_fora_sem_cadastro(self):
        """Sem `codigos_lactacao`, cai no padrão histórico 01/02/03 — um lote
        novo (ex.: "04 — pós-parto imediato") não é reconhecido como
        lactação, mesmo com DEL/secagem que qualificariam."""
        res = avaliar_bst(
            numero_matriz="005",
            grupo_primario="04 - POS PARTO IMEDIATO",
            del_dias=90,
            data_secagem=date.today() + timedelta(days=30),
            data_referencia=date.today(),
        )
        assert res.elegivel is False
        assert "lactação" in res.motivo_exclusao.lower()

    def test_codigos_lactacao_customizado_reconhece_lote_novo(self):
        """Bug real reportado pelo usuário 2026-09-10: fazenda reorganizou os
        lotes e criou um "04" de lactação (pós-parto imediato) — o chamador
        (agenda_engine, a partir do cadastro real de Lote) agora pode passar
        o conjunto de códigos que valem como lactação, em vez de ficar preso
        em 01/02/03."""
        res = avaliar_bst(
            numero_matriz="005",
            grupo_primario="04 - POS PARTO IMEDIATO",
            del_dias=90,
            data_secagem=date.today() + timedelta(days=30),
            data_referencia=date.today(),
            codigos_lactacao={"01", "02", "03", "04"},
        )
        assert res.elegivel is True


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
        """`taxa_concepcao_pct` passou a ser a conta do MOTOR DE CICLOS de 21
        dias (alias de `benchmark["taxa_concepcao"]`), e não mais o acumulado
        legado "positivos ÷ diagnosticados do período".

        Era esse acumulado que fazia a Capa mostrar dois números diferentes
        com o mesmo nome: o card "Concepção / serviço" (conta legada) e o
        medidor "Taxa de Concepção" (motor de ciclos). Agora existe UMA
        definição só — a do motor, que pondera os ciclos de 21 dias e aplica a
        regra dos 28 dias para a janela de diagnóstico.

        Nesta fixture os serviços não têm matriz (nem, portanto, ciclo
        atribuível), então o motor não fecha janela nenhuma e a taxa é `None`.
        A conta antiga devolvia 50,0% aqui — número que não correspondia a
        nada que o resto do sistema mostrasse. `servicos_positivos`/
        `servicos_negativos` continuam de pé: são contagens brutas do período,
        só não são mais os termos da taxa.
        """
        animais, servicos, partos = self._dados()
        r = calcular_indicadores(animais, servicos, partos, data_ref=date(2026, 7, 5))
        assert r["rebanho"]["total"] == 4
        assert r["rebanho"]["vacas_lactacao"] == 2  # grupos 01 e 02
        assert r["rebanho"]["codigos_lactacao"] == ["01", "02", "03"]  # padrão sem cadastro de Lote
        assert r["rebanho"]["vacas_secas"] == 1
        assert r["reproducao"]["prenhes"] == 2
        assert r["reproducao"]["vazias"] == 1
        assert r["reproducao"]["inseminadas"] == 1
        assert r["reproducao"]["taxa_prenhez_pct"] == 50.0  # 2/4
        # Sem ciclo fechado, o motor não tem o que ponderar.
        assert r["reproducao"]["taxa_concepcao_pct"] is None
        # E o campo é literalmente o valor do benchmark — mesma fonte, sempre.
        do_benchmark = next(b["valor"] for b in r["benchmark"] if b["chave"] == "taxa_concepcao")
        assert r["reproducao"]["taxa_concepcao_pct"] == do_benchmark
        # Contagens brutas do período seguem existindo (1 POSITIVO, 1 NEGATIVO).
        assert r["reproducao"]["servicos_positivos"] == 1
        assert r["reproducao"]["servicos_negativos"] == 1

    def test_iep_e_producao(self):
        """`producao.producao_total_dia_kg`/`vacas_com_producao` MUDARAM DE
        PREMISSA (decisão do dono do produto, ver rules/indicadores.py::
        calcular_indicadores): o card "Produção do dia" passa a ser O
        CONTROLE DO DIA — a soma das linhas de `ControleLeiteiro` do dia mais
        recente —, não mais o último `ult_cl_kg` congelado de cada animal em
        qualquer data. Esta fixture não passa `controles`, então não há "dia"
        nenhum para o card somar (0.0/0 vacas) — o valor antigo (55.0/2,
        vindo de `ult_cl_kg`) agora mora em `producao.ultimo_por_animal`,
        que continua exatamente igual a antes. `del_medio` não muda aqui: os
        animais desta fixture não têm `numero`, então a DEL AO VIVO (que
        depende de casar `numero` com `numero_matriz` de `partos`) não acha
        nenhum parto e cai no `del_dias` congelado — o mesmo (120+80)/2 de
        sempre. Ver test_indicador_producao_le_controle_leiteiro.py para a
        cobertura completa do novo contrato."""
        animais, servicos, partos = self._dados()
        r = calcular_indicadores(animais, servicos, partos, data_ref=date(2026, 7, 5))
        assert r["reproducao"]["iep_dias"] == 366
        assert r["producao"]["vacas_com_producao"] == 0
        assert r["producao"]["producao_total_dia_kg"] == 0.0
        assert r["producao"]["ultimo_por_animal"]["vacas_com_producao"] == 2
        assert r["producao"]["ultimo_por_animal"]["producao_total_kg"] == 55.0

    def test_vacas_lactacao_reconhece_lote_novo_via_cadastro(self):
        """Bug real reportado pelo usuário 2026-09-10: reorganizou os lotes e
        criou um "04" (pós-parto imediato) com Parto/Lactação reais abertos —
        "vacas em lactação" continuava presa a 01/02/03 porque a conta nunca
        olhava o cadastro de Lote (só olhava codigos_secas/codigos_pre_parto).
        Com o cadastro passando status_lactacao="lactacao" pro lote 04, ele
        entra na soma — mesmo padrão já usado por codigos_secas/pre_parto."""
        animais, servicos, partos = self._dados()
        animais = animais + [{"grupo_primario": "04 - POS PARTO IMEDIATO", "sit_rep": "Ges.", "del_dias": 5, "ult_cl_kg": 20.0}]
        lotes = [
            {"codigo": "01", "status_lactacao": None, "pre_parto": False},
            {"codigo": "04", "status_lactacao": "lactacao", "pre_parto": False},
            {"codigo": "05", "status_lactacao": "seca", "pre_parto": False},
        ]
        r = calcular_indicadores(animais, servicos, partos, data_ref=date(2026, 7, 5), lotes=lotes)
        # Com `lotes` fornecido, a soma passa a seguir só o que está marcado
        # `status_lactacao="lactacao"` no cadastro — aqui, só o 04 (01/02 têm
        # `status_lactacao=None` no cadastro desta fixture, então ficam de
        # fora da soma, mesmo sem terem mudado de significado de verdade).
        assert r["rebanho"]["vacas_lactacao"] == 1  # só o animal do lote 04
        assert r["rebanho"]["codigos_lactacao"] == ["04"]
        assert r["rebanho"]["vacas_secas"] == 1  # lote 05, via cadastro

    def test_vacas_lactacao_cai_no_padrao_sem_nenhum_lote_marcado(self):
        """Cadastro de Lote existe mas nenhum tem status_lactacao="lactacao"
        — não esvazia a contagem, cai no padrão histórico 01/02/03 (mesma
        rede de segurança já usada por codigos_secas/codigos_pre_parto)."""
        animais, servicos, partos = self._dados()
        lotes = [{"codigo": "05", "status_lactacao": "seca", "pre_parto": False}]
        r = calcular_indicadores(animais, servicos, partos, data_ref=date(2026, 7, 5), lotes=lotes)
        assert r["rebanho"]["vacas_lactacao"] == 2  # grupos 01 e 02, padrão
        assert r["rebanho"]["codigos_lactacao"] == ["01", "02", "03"]
        assert r["producao"]["del_medio"] == 100.0  # (120 + 80) / 2 — sem `numero`, cai no congelado

    def test_rebanho_vazio_nao_quebra(self):
        r = calcular_indicadores([], [], [], data_ref=date(2026, 7, 5))
        assert r["rebanho"]["total"] == 0
        assert r["reproducao"]["taxa_prenhez_pct"] is None
        assert r["reproducao"]["iep_dias"] is None

    def test_reproducao_categorias_4_grupos_padrao(self):
        # Situação Reprodutiva da Capa: Prenhas/Inseminadas/PEV/A inseminar são
        # o padrão; Vaz. atr. entra em "a_inseminar" (mesmo critério do IATF);
        # qualquer sit_rep fora do padrão (aqui, em branco) vira "nao_classificadas".
        animais = [
            {"numero": "1", "grupo_primario": "01 - VACAS", "sit_rep": "Ges."},
            {"numero": "2", "grupo_primario": "01 - VACAS", "sit_rep": "Ins."},
            {"numero": "3", "grupo_primario": "01 - VACAS", "sit_rep": "Vaz. pev"},
            {"numero": "4", "grupo_primario": "01 - VACAS", "sit_rep": "Vaz. apt."},
            {"numero": "5", "grupo_primario": "01 - VACAS", "sit_rep": "Vaz. atr."},
            {"numero": "6", "grupo_primario": "01 - VACAS", "sit_rep": ""},
        ]
        r = calcular_indicadores(animais, [], [], data_ref=date(2026, 7, 5))
        cat = r["reproducao_categorias"]["todas"]
        assert cat["prenhes"] == 1
        assert cat["inseminadas"] == 1
        assert cat["pev"] == 1
        assert cat["a_inseminar"] == 2  # Vaz. apt. + Vaz. atr.
        assert cat["nao_classificadas"] == 1

    def test_iep_ignora_partos_duplicados(self):
        # Registros de parto separados por menos que uma gestação são o mesmo
        # evento (duplicidade) e não podem contar como intervalo entre partos.
        animais = [{"grupo_primario": "01 - VACAS", "sit_rep": "Ges."}]
        partos = [
            {"numero_matriz": "100", "data_parto": date(2024, 1, 1)},
            {"numero_matriz": "100", "data_parto": date(2024, 1, 15)},  # duplicidade
            {"numero_matriz": "100", "data_parto": date(2025, 1, 1)},   # 366d do 1º
        ]
        r = calcular_indicadores(animais, [], partos, data_ref=date(2026, 7, 5))
        # Sem o filtro, a média cairia para ~190d (366 e 14). Com o filtro: 366d.
        assert r["reproducao"]["iep_dias"] == 366

    def test_iep_por_matriz_drill_down(self):
        # Drill-down do card "IEP médio": uma linha por matriz com >=2 partos
        # distintos, usando o intervalo mais recente. Matriz com 1 único parto
        # (110) não entra (ainda não tem intervalo).
        animais = [{"grupo_primario": "01 - VACAS", "sit_rep": "Ges."}]
        partos = [
            {"numero_matriz": "100", "data_parto": date(2024, 1, 1)},
            {"numero_matriz": "100", "data_parto": date(2024, 1, 15)},  # duplicidade, ignorada
            {"numero_matriz": "100", "data_parto": date(2025, 1, 1)},   # 366d do 1º
            {"numero_matriz": "110", "data_parto": date(2025, 6, 1)},
        ]
        r = calcular_indicadores(animais, [], partos, data_ref=date(2026, 7, 5))
        lista = r["reproducao"]["iep_por_matriz"]
        assert len(lista) == 1
        assert lista[0]["numero"] == "100"
        assert lista[0]["iep_dias"] == 366
        assert lista[0]["data_parto_anterior"] == date(2024, 1, 1).isoformat()
        assert lista[0]["data_ultimo_parto"] == date(2025, 1, 1).isoformat()

    def test_partos_previstos_so_prenhes_gestacao_280(self):
        hoje = date(2026, 7, 7)
        animais = [
            # prenhe, serviço positivo há 260 dias -> parto em ~20 dias (em_30)
            {"numero": "10", "grupo_primario": "02 - VACAS", "sit_rep": "Ges."},
            # vazia no PEV: perdeu a prenhez (diagnóstico NEGATIVO mais recente
            # que o POSITIVO) e não pode entrar em partos previstos. Precisa do
            # 2º serviço para o estado AO VIVO (não só o sit_rep congelado)
            # também dar vazia — ver comentário de numeros_gestantes_vivo em
            # rules/indicadores.py.
            {"numero": "20", "grupo_primario": "03 - MÉDIA", "sit_rep": "Vaz. pev"},
        ]
        servicos = [
            {"numero_matriz": "10", "data_servico": hoje - timedelta(days=260), "diagnostico": "POSITIVO", "raca_matriz": "Girolando"},
            {"numero_matriz": "20", "data_servico": hoje - timedelta(days=260), "diagnostico": "POSITIVO", "raca_matriz": "Girolando"},
            {"numero_matriz": "20", "data_servico": hoje - timedelta(days=200), "diagnostico": "NEGATIVO", "raca_matriz": "Girolando"},
        ]
        r = calcular_indicadores(animais, servicos, [], data_ref=hoje)
        rep = r["reproducao"]
        # só a 10 (prenhe) entra; a 20 (vazia) fica de fora
        assert rep["partos_previstos"]["em_30_dias"] == 1
        assert rep["partos_previstos_nums"]["em_30_dias"] == ["10"]
        # contagem bate com a lista (bug 6x5)
        assert rep["partos_previstos"]["em_90_dias"] == len(rep["partos_previstos_nums"]["em_90_dias"])
        # gestação de referência (ponto médio de gestacao_dias_min/max, 288 dias): parto ~ serviço + 288
        assert rep["partos_previstos_datas"]["10"] == (hoje - timedelta(days=260) + timedelta(days=288)).isoformat()

    def test_gestantes_detalhe_drill_down(self):
        # Drill-down do card "Gestantes": TODA gestante com serviço positivo
        # conhecido entra (mesmo fora da janela de 90 dias de partos_previstos).
        hoje = date(2026, 7, 7)
        animais = [
            {"numero": "10", "grupo_primario": "02 - VACAS", "sit_rep": "Ges."},
            {"numero": "30", "grupo_primario": "02 - VACAS", "sit_rep": "Ges."},  # bem longe do parto
        ]
        servicos = [
            {"numero_matriz": "10", "data_servico": hoje - timedelta(days=260), "diagnostico": "POSITIVO"},
            {"numero_matriz": "30", "data_servico": hoje - timedelta(days=20), "diagnostico": "POSITIVO"},
        ]
        r = calcular_indicadores(animais, servicos, [], data_ref=hoje)
        detalhe = {d["numero"]: d for d in r["reproducao"]["gestantes_detalhe"]}
        assert set(detalhe) == {"10", "30"}
        assert detalhe["10"]["dias_gestacao"] == 260
        assert detalhe["30"]["dias_gestacao"] == 20
        # "30" não aparece em partos_previstos (fora dos 90 dias) mas está no detalhe
        assert "30" not in r["reproducao"]["partos_previstos_nums"]["em_90_dias"]

    def test_gestantes_detalhe_bate_com_card_apos_parto(self):
        # B7 da auditoria: o card "Gestantes" (rep["prenhes"], estado AO VIVO)
        # e a lista que abre ao clicar nele (gestantes_detalhe) usavam
        # critérios diferentes — uma matriz cujo sit_rep ainda dizia "Ges."
        # (não atualizado desde o último import do CSV) mas que JÁ PARIU
        # (há Parto lançado depois do serviço) sumia do card mas continuava
        # aparecendo na lista, porque a lista só olhava o texto sit_rep.
        hoje = date(2026, 7, 7)
        animais = [
            {"numero": "10", "grupo_primario": "02 - VACAS", "sit_rep": "Ges."},  # prenhe de verdade
            # sit_rep desatualizado ("Ges." de antes do parto), mas já pariu há 20 dias
            {"numero": "40", "grupo_primario": "02 - VACAS", "sit_rep": "Ges."},
        ]
        servicos = [
            {"numero_matriz": "10", "data_servico": hoje - timedelta(days=260), "diagnostico": "POSITIVO"},
            {"numero_matriz": "40", "data_servico": hoje - timedelta(days=300), "diagnostico": "POSITIVO"},
        ]
        partos = [{"numero_matriz": "40", "data_parto": hoje - timedelta(days=20), "ordem_parto": 2}]
        r = calcular_indicadores(animais, servicos, partos, data_ref=hoje)
        rep = r["reproducao"]
        detalhe_numeros = {d["numero"] for d in rep["gestantes_detalhe"]}
        assert detalhe_numeros == {"10"}
        # Card ("prenhes") e lista (gestantes_detalhe) concordam: só "10" é
        # gestante de verdade — "40" já pariu e não entra em nenhum dos dois.
        assert rep["prenhes"] == 1

    def test_iep_so_duplicidades_fica_none(self):
        animais = [{"grupo_primario": "01 - VACAS", "sit_rep": "Ges."}]
        partos = [
            {"numero_matriz": "100", "data_parto": date(2025, 1, 1)},
            {"numero_matriz": "100", "data_parto": date(2025, 1, 10)},  # só duplicidade
        ]
        r = calcular_indicadores(animais, [], partos, data_ref=date(2026, 7, 5))
        assert r["reproducao"]["iep_dias"] is None

    def test_taxa_prenhez_e_vazias_usam_rebanho_no_programa(self):
        """Denominador de taxa_prenhez_pct/perc_vazias_pct: ERA o rebanho
        fêmeo INTEIRO (prenhes+vazias+inseminadas — no caminho ao vivo,
        `vazias` é um `else` que absorve tudo que não é gestante nem
        inseminada, inclusive a bezerra impúbere, que nunca poderia estar
        prenhe). Agora é o rebanho no PROGRAMA reprodutivo (R1): fora a
        impúbere, a descartada (a menos que esteja gestante — aí é
        inventário, ela vai parir do mesmo jeito) e a baixada.

        Rebanho de exemplo (7 fêmeas): "1" gestante; "2" vaca vazia (no
        programa); "3" bezerra impúbere (fora — nunca entrou no programa);
        "4" novilha apta (no programa); "5" vaca a_descartar vazia (fora —
        só a exceção da gestante entra); "6" vaca gestante a_descartar (fica
        — inventário); "7" vaca baixada/ativo=False (fora, mesmo "vazia").

        ANTES (denominador = 7, o rebanho inteiro):
          taxa_prenhez_pct = 100*2/7 = 28.6%
          perc_vazias_pct  = 100*5/7 = 71.4%
        DEPOIS (denominador = 4, o programa: "1","2","4","6"):
          taxa_prenhez_pct = 100*2/4 = 50.0%  (sobe, como esperado — o
            numerador `prenhes` não muda, o denominador encolhe)
          perc_vazias_pct  = 100*2/4 = 50.0%  (o numerador de vazias
            também precisou ficar restrito ao programa — "2" e "4" — senão
            o 5 antigo sobre o 4 novo daria 125%, pior que o bug original;
            por isso este percentual pode CAIR em vez de subir quando a
            população excluída é majoritariamente "vazia", como aqui)
        """
        hoje = date(2026, 8, 19)
        animais = [
            {"numero": "1"},                                          # gestante, no programa
            {"numero": "2"},                                          # vazia, no programa
            {"numero": "3", "data_nasc": hoje - timedelta(days=200)},  # bezerra impúbere
            {"numero": "4", "data_nasc": hoje - timedelta(days=600)},  # novilha apta
            {"numero": "5", "a_descartar": True},                     # vazia + descarte: fora
            {"numero": "6", "a_descartar": True},                     # gestante + descarte: fica
            {"numero": "7", "ativo": False},                          # baixada: fora
        ]
        servicos = [
            {"numero_matriz": "1", "data_servico": hoje - timedelta(days=60), "diagnostico": "POSITIVO"},
            {"numero_matriz": "6", "data_servico": hoje - timedelta(days=50), "diagnostico": "POSITIVO"},
        ]
        partos = [
            {"numero_matriz": "1", "data_parto": hoje - timedelta(days=200)},
            {"numero_matriz": "2", "data_parto": hoje - timedelta(days=200)},
            {"numero_matriz": "5", "data_parto": hoje - timedelta(days=200)},
            {"numero_matriz": "6", "data_parto": hoje - timedelta(days=250)},
            {"numero_matriz": "7", "data_parto": hoje - timedelta(days=200)},
        ]
        peso_por_animal = {"4": 350.0}
        r = calcular_indicadores(animais, servicos, partos, data_ref=hoje, peso_por_animal=peso_por_animal)
        rep = r["reproducao"]
        # Contagens cruas (fora de escopo desta correção — continuam sobre o
        # rebanho inteiro, é o que outras telas ainda consomem):
        assert rep["prenhes"] == 2   # "1" e "6" — gestante conta mesmo descartada
        assert rep["vazias"] == 5    # "2","3","4","5","7" — inclui a bezerra
        # O que este teste prova: os PERCENTUAIS usam o programa (4 fêmeas),
        # não o rebanho inteiro (7).
        assert rep["taxa_prenhez_pct"] == 50.0
        assert rep["perc_vazias_pct"] == 50.0

    def test_inseminada_entra_no_denominador_mas_nao_conta_como_vazia(self):
        """A inseminada está no programa (denominador), mas NÃO é "vazia".

        `perc_vazias_pct` alimenta o card rotulado "Vazias", cujo drill-down
        abre a lista filtrada por `sit_rep` começando em "Vaz." — que não
        inclui as inseminadas. Se o card contasse a inseminada, o número
        divergiria da lista que abre ao clicar nele: exatamente o defeito
        que `numeros_gestantes_vivo` já corrigiu do lado das gestantes.

        Rebanho de exemplo (4 vacas, todas paridas e no programa): "1"
        gestante; "2" e "4" vazias; "3" inseminada (serviço recente, ainda
        sem diagnóstico).

        Denominador = 4 nos dois percentuais — a inseminada CONTA, ela está
        no programa e pode emprenhar. Numeradores: 1 gestante e 2 vazias.
        Os baldes de propósito não somam o denominador; a diferença é
        justamente a inseminada.
        """
        hoje = date(2026, 8, 19)
        animais = [{"numero": "1"}, {"numero": "2"}, {"numero": "3"}, {"numero": "4"}]
        servicos = [
            {"numero_matriz": "1", "data_servico": hoje - timedelta(days=60), "diagnostico": "POSITIVO"},
            {"numero_matriz": "3", "data_servico": hoje - timedelta(days=20)},  # sem DG: inseminada
        ]
        partos = [
            {"numero_matriz": n, "data_parto": hoje - timedelta(days=200)}
            for n in ("1", "2", "3", "4")
        ]
        r = calcular_indicadores(animais, servicos, partos, data_ref=hoje)
        rep = r["reproducao"]
        assert rep["inseminadas"] == 1
        assert rep["taxa_prenhez_pct"] == 25.0   # 1 gestante / 4 no programa
        assert rep["perc_vazias_pct"] == 50.0    # 2 vazias / 4 — NÃO 75.0


class TestBaldesDrillDown:
    """Cada contador de `reproducao_categorias` (e os dois do programa
    reprodutivo) passa a devolver TAMBÉM a lista de números que o gerou, para
    o card e a lista que ele abre nunca divergirem — o padrão que
    `aptas_nums`/`partos_previstos_nums` já provavam e que os outros doze
    drill-downs da web não seguiam (filtravam o `sit_rep` congelado do CSV
    enquanto o número vinha do estado ao vivo).

    Inclui o balde novo `em_protocolo`, que antes não entrava em fatia nenhuma
    do donut da Capa — nem em `vazias`, que o exclui de propósito — e por isso
    as fatias não fechavam o rebanho.
    """

    HOJE = date(2026, 7, 5)
    BALDES = ("prenhes", "vazias", "inseminadas", "pev", "a_inseminar", "nao_classificadas", "em_protocolo")
    # As 6 que particionam a categoria (vazias é catch-all e se sobrepõe às demais).
    FATIAS = ("prenhes", "inseminadas", "em_protocolo", "pev", "a_inseminar", "nao_classificadas")

    def _dados(self):
        hoje = self.HOJE
        animais = [
            # vacas (têm parto)
            {"numero": "10", "grupo_primario": "02 - VACAS", "sit_rep": "Ges."},    # gestante
            {"numero": "20", "grupo_primario": "02 - VACAS", "sit_rep": "Ins."},    # inseminada
            {"numero": "30", "grupo_primario": "02 - VACAS", "sit_rep": ""},        # PEV (parto recente)
            {"numero": "40", "grupo_primario": "02 - VACAS", "sit_rep": ""},        # atrasada -> a_inseminar
            {"numero": "60", "grupo_primario": "02 - VACAS", "sit_rep": ""},        # em protocolo (D0-D11)
            # novilhas nulíparas
            {"numero": "50", "grupo_primario": "12 - NOVILHAS", "data_nasc": hoje - timedelta(days=200)},   # não apta
            {"numero": "70", "grupo_primario": "12 - NOVILHAS", "data_nasc": hoje - timedelta(days=600)},   # apta
        ]
        servicos = [
            {"numero_matriz": "10", "data_servico": hoje - timedelta(days=100), "diagnostico": "POSITIVO", "raca_matriz": "Girolando"},
            {"numero_matriz": "20", "data_servico": hoje - timedelta(days=10)},  # aguardando diagnóstico
        ]
        partos = [
            {"numero_matriz": "10", "data_parto": hoje - timedelta(days=400)},
            {"numero_matriz": "20", "data_parto": hoje - timedelta(days=200)},
            {"numero_matriz": "30", "data_parto": hoje - timedelta(days=10)},   # DEL 10 < pev_dias (45)
            {"numero_matriz": "40", "data_parto": hoje - timedelta(days=300)},  # DEL 300 > DEL máx 1º serviço
            {"numero_matriz": "60", "data_parto": hoje - timedelta(days=200)},
        ]
        aplicacoes_iatf = [
            {"numero_matriz": "60", "lancamento_id": 1, "dia": 0, "data_prevista": hoje - timedelta(days=3)},
            {"numero_matriz": "60", "lancamento_id": 1, "dia": 11, "data_prevista": hoje + timedelta(days=8)},
        ]
        return animais, servicos, partos, aplicacoes_iatf

    def _calcular(self):
        animais, servicos, partos, aplicacoes_iatf = self._dados()
        return calcular_indicadores(
            animais, servicos, partos, data_ref=self.HOJE,
            peso_por_animal={"70": 420.0, "50": 150.0},
            aplicacoes_iatf=aplicacoes_iatf,
        )

    def test_estados_esperados_por_balde(self):
        cats = self._calcular()["reproducao_categorias"]
        todas = cats["todas"]
        assert set(todas["prenhes_nums"]) == {"10"}
        assert set(todas["inseminadas_nums"]) == {"20"}
        assert set(todas["pev_nums"]) == {"30"}
        assert set(todas["a_inseminar_nums"]) == {"40", "70"}   # atrasada + novilha apta
        assert set(todas["nao_classificadas_nums"]) == {"50"}   # novilha impúbere
        assert set(todas["em_protocolo_nums"]) == {"60"}
        # `vazias` é o guarda-chuva de 5 estados e NÃO inclui "em protocolo".
        assert set(todas["vazias_nums"]) == {"30", "40", "50", "70"}
        # Recorte vaca/novilha vem do registro de Parto, não de `data_ult_parto`.
        assert set(cats["vaca"]["em_protocolo_nums"]) == {"60"}
        assert cats["novilha"]["em_protocolo_nums"] == []
        assert set(cats["novilha"]["a_inseminar_nums"]) == {"70"}

    def test_contagem_bate_com_a_lista_em_toda_categoria(self):
        # É o defeito que o drill-down tinha: número do card e lista aberta
        # saíam de contas diferentes.
        cats = self._calcular()["reproducao_categorias"]
        for categoria in ("todas", "vaca", "novilha"):
            dados = cats[categoria]
            for balde in self.BALDES:
                assert dados[balde] == len(dados[f"{balde}_nums"]), f"{categoria}.{balde}"
            assert dados["aptas"] == len(dados["aptas_nums"]), f"{categoria}.aptas"

    def test_fatias_do_donut_cobrem_o_rebanho_sem_sobreposicao(self):
        # É o que faz o donut da Capa somar o rebanho da categoria.
        r = self._calcular()
        cats = r["reproducao_categorias"]
        esperado = {"todas": 7, "vaca": 5, "novilha": 2}
        for categoria, total in esperado.items():
            dados = cats[categoria]
            assert sum(dados[b] for b in self.FATIAS) == total, categoria
            numeros = [n for b in self.FATIAS for n in dados[f"{b}_nums"]]
            assert len(numeros) == total, categoria          # nenhum animal em duas fatias
            assert len(set(numeros)) == total, categoria     # e nenhum repetido
        # todas = vaca + novilha, fatia a fatia.
        for balde in self.FATIAS:
            assert cats["todas"][balde] == cats["vaca"][balde] + cats["novilha"][balde], balde

    def test_nums_do_programa_batem_com_os_numeradores_das_taxas(self):
        """`prenhes_programa_nums`/`vazias_programa_nums` são exatamente os
        numeradores de `taxa_prenhez_pct`/`perc_vazias_pct` — os dois cards de
        Indicadores abrem a lista que gerou o próprio percentual.

        Denominador (rebanho no programa reprodutivo, R1) = 6: os 7 animais
        menos a novilha impúbere (50). Note que é ele, e não "fêmeas aptas",
        o denominador dos dois percentuais.
        """
        rep = self._calcular()["reproducao"]
        assert set(rep["prenhes_programa_nums"]) == {"10"}
        # Em protocolo (60) entra em "vazias" do programa: não está gestante
        # nem inseminada. Impúbere (50) fica fora do programa inteiro.
        assert set(rep["vazias_programa_nums"]) == {"30", "40", "60", "70"}
        rebanho_programa = 6
        assert rep["taxa_prenhez_pct"] == round(100 * len(rep["prenhes_programa_nums"]) / rebanho_programa, 1)
        assert rep["perc_vazias_pct"] == round(100 * len(rep["vazias_programa_nums"]) / rebanho_programa, 1)


class TestReproducaoCategoriasFallback:
    """`_reproducao_categorias` no caminho de FALLBACK (sem `estados` ao
    vivo — ativa só quando `calcular_indicadores` não tem nenhum Parto/
    Servico carregado, ver `_estados_ao_vivo`). Risco baixo (só ativa sem
    registros), mas divergia da matriz canônica em dois pontos: DEL mínimo
    de aptidão da vaca era uma constante fixa (45) paralela e independente
    de `pev_dias()`, e a novilha apta não checava idade — só peso."""

    def test_vaca_apta_usa_pev_dias_nao_constante_fixa(self):
        from fazenda.rules.indicadores import _reproducao_categorias
        # pev_dias() padrão = 45 — DEL de 50 dias já é apta a novo serviço.
        animais = [{"numero": "1", "del_dias": 50, "sit_rep": ""}]
        r = _reproducao_categorias(
            animais, numeros_com_servico=set(), peso_por_animal={}, vacas_nums={"1"},
            hoje=date(2026, 7, 5),
        )
        assert "1" in r["todas"]["aptas_nums"]

    def test_vaca_dentro_do_pev_nao_e_apta(self):
        from fazenda.rules.indicadores import _reproducao_categorias
        animais = [{"numero": "1", "del_dias": 20, "sit_rep": ""}]
        r = _reproducao_categorias(
            animais, numeros_com_servico=set(), peso_por_animal={}, vacas_nums={"1"},
            hoje=date(2026, 7, 5),
        )
        assert "1" not in r["todas"]["aptas_nums"]

    def test_novilha_com_peso_mas_sem_idade_nao_e_apta(self):
        """Peso acima do mínimo (peso_apta_min padrão 300 kg) não basta
        sozinho — a matriz canônica (estado_reprodutivo.classificar_animal,
        regra 7) exige idade E peso. 300 dias (~9,9 meses) fica abaixo de
        idade_apta_min_meses padrão (15 meses)."""
        from fazenda.rules.indicadores import _reproducao_categorias
        hoje = date(2026, 7, 5)
        animais = [{"numero": "2", "data_nasc": hoje - timedelta(days=300), "sit_rep": ""}]
        r = _reproducao_categorias(
            animais, numeros_com_servico=set(), peso_por_animal={"2": 320}, vacas_nums=set(),
            hoje=hoje,
        )
        assert "2" not in r["todas"]["aptas_nums"]

    def test_novilha_com_idade_e_peso_e_apta(self):
        from fazenda.rules.indicadores import _reproducao_categorias
        hoje = date(2026, 7, 5)
        animais = [{"numero": "3", "data_nasc": hoje - timedelta(days=470), "sit_rep": ""}]
        r = _reproducao_categorias(
            animais, numeros_com_servico=set(), peso_por_animal={"3": 320}, vacas_nums=set(),
            hoje=hoje,
        )
        assert "3" in r["todas"]["aptas_nums"]

    def test_sem_hoje_cai_no_criterio_antigo_so_peso(self):
        """Retrocompatibilidade: chamador que não informa `hoje` (nenhum
        hoje, dentro do repositório, chama assim hoje — mas a função
        continua aceitando) mantém o critério de só peso, sem quebrar."""
        from fazenda.rules.indicadores import _reproducao_categorias
        animais = [{"numero": "4", "data_nasc": date(2026, 7, 5) - timedelta(days=300), "sit_rep": ""}]
        r = _reproducao_categorias(
            animais, numeros_com_servico=set(), peso_por_animal={"4": 320}, vacas_nums=set(),
        )
        assert "4" in r["todas"]["aptas_nums"]


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


# ============================================================
# ANÁLISE REPRODUTIVA
# ============================================================

class TestAnaliseReprodutiva:
    def test_achata_servicos_com_dimensoes(self):
        from fazenda.rules.reproducao_analise import analisar_servicos
        servicos = [
            {"numero_matriz": "1", "raca_matriz": "Girolando", "data_servico": date(2026, 3, 10),
             "data_ult_parto": date(2026, 1, 1), "diagnostico": "POSITIVO", "reprodutor": "ROBO",
             "tipo_servico": "Inseminação Artificial", "ordem_parto": 2, "ordem_tentativa": 1,
             "data_perda_prenhez": None},
            {"numero_matriz": "2", "raca_matriz": "Holandês", "data_servico": date(2026, 3, 20),
             "data_ult_parto": None, "diagnostico": "NEGATIVO", "reprodutor": "TOURO",
             "tipo_servico": "Cobertura", "ordem_parto": 0, "ordem_tentativa": 2,
             "data_perda_prenhez": date(2026, 5, 1)},
            {"numero_matriz": "3", "raca_matriz": "Girolando", "data_servico": date(2026, 4, 1),
             "data_ult_parto": None, "diagnostico": "ABERTO", "reprodutor": None,
             "tipo_servico": None, "ordem_parto": None, "ordem_tentativa": 1,
             "data_perda_prenhez": None},
        ]
        r = analisar_servicos(servicos)
        assert len(r) == 3
        r0 = r[0]
        assert r0["ano"] == 2026 and r0["mes"] == "2026-03"
        assert r0["del_servico"] == (date(2026, 3, 10) - date(2026, 1, 1)).days
        assert r0["diagnosticado"] and r0["positivo"]
        # ABERTO não conta como diagnosticado
        assert r[2]["diagnosticado"] is False and r[2]["positivo"] is False
        # perda de prenhez detectada pela data
        assert r[1]["perda"] is True
        # touro (reprodutor) vazio vira rótulo
        assert r[2]["touro"] == "(sem touro)"
        # método de IA: IA sem protocolo = cio natural; cobertura = monta
        assert r0["metodo_ia"] == "IA em cio natural"
        assert r[1]["metodo_ia"] == "Monta natural"

    def test_taxa_concepcao_aplica_r7_servico_antigo_sem_diagnostico_conta_como_fracasso(self):
        """Regra dos 28 dias (R7): serviço com 28+ dias e ninguém diagnosticou
        entra no denominador da concepção como fracasso — antes (denominador
        = só "diagnosticado") ele simplesmente sumia da conta."""
        from fazenda.rules.reproducao_analise import agregar_mensal, analisar_servicos

        hoje = date(2026, 8, 19)
        servicos = [
            # Maio: 1 positivo diagnosticado + 1 sem diagnóstico algum, mas já
            # com bem mais de 28 dias — antes do fix sumia do denominador
            # (taxa = 100%); com R7 entra como fracasso (taxa = 50%).
            {"numero_matriz": "1", "data_servico": date(2026, 5, 3), "diagnostico": "POSITIVO", "data_perda_prenhez": None},
            {"numero_matriz": "2", "data_servico": date(2026, 5, 10), "diagnostico": None, "data_perda_prenhez": None},
        ]
        regs = analisar_servicos(servicos)
        agregado = agregar_mensal(regs, [], [], hoje=hoje)
        i = agregado["meses"].index("2026-05")
        assert agregado["series"]["taxa_concepcao"][i] == 50.0

    def test_janela_dg_completa_marca_mes_corrente_como_incompleto(self):
        """Mês cujos serviços ainda não completaram os `dias_resultado` dias
        vem marcado com `janela_dg_completa=False`; mês antigo, maduro, vem
        `True` — mesmo vocabulário/contrato de `ResultadoCiclo.janela_dg_completa`
        nos ciclos de 21 dias."""
        from fazenda.rules.reproducao_analise import agregar_mensal, analisar_servicos

        hoje = date(2026, 8, 19)
        servicos = [
            {"numero_matriz": "1", "data_servico": date(2026, 5, 3), "diagnostico": "POSITIVO", "data_perda_prenhez": None},
            {"numero_matriz": "2", "data_servico": date(2026, 8, 15), "diagnostico": None, "data_perda_prenhez": None},
        ]
        regs = analisar_servicos(servicos)
        agregado = agregar_mensal(regs, [], [], hoje=hoje)
        completo_por_mes = dict(zip(agregado["meses"], agregado["janela_dg_completa"]))
        assert completo_por_mes["2026-05"] is True
        assert completo_por_mes["2026-08"] is False
        # E o mês em apuração sai do denominador de concepção enquanto ninguém
        # o diagnostica (nenhum serviço ali tem 28 dias nem DG) — fica None,
        # não zero, para não parecer "concepção zero" quando é só falta de tempo.
        i = agregado["meses"].index("2026-08")
        assert agregado["series"]["taxa_concepcao"][i] is None


# ============================================================
# BENCHMARK POR CATEGORIA (vaca / novilha)
# ============================================================

class TestBenchmarkCategorias:
    # As três taxas do painel saem do motor de ciclos de 21 dias, que só conta
    # quem ENTROU no programa reprodutivo (R1): a novilha precisa de idade e
    # peso de puberdade para existir em qualquer denominador. Por isso as
    # novilhas aqui têm `data_nasc` e peso (ver `_peso` abaixo) — sem eles não
    # há rebanho novilha nenhum para medir.
    def _dados(self):
        # Vaca = já pariu (tem parto); novilha = nunca pariu.
        animais = [
            {"numero": "10", "grupo_primario": "02 - VACAS ALTA", "sit_rep": "Ges."},
            {"numero": "11", "grupo_primario": "02 - VACAS ALTA", "sit_rep": "Vaz. apt."},
            {"numero": "20", "grupo_primario": "12 - NOVILHAS", "sit_rep": "Ins.", "data_nasc": date(2024, 1, 1)},
            {"numero": "21", "grupo_primario": "12 - NOVILHAS", "sit_rep": "Vaz. apt.", "data_nasc": date(2024, 1, 1)},
        ]
        servicos = [
            # vacas (ordem_parto >= 1)
            {"numero_matriz": "10", "data_servico": date(2026, 2, 1), "diagnostico": "POSITIVO", "ordem_parto": 2, "ordem_tentativa": 1},
            {"numero_matriz": "11", "data_servico": date(2026, 2, 5), "diagnostico": "NEGATIVO", "ordem_parto": 1, "ordem_tentativa": 1},
            # novilhas (ordem_parto 0/None) — ambas positivas
            {"numero_matriz": "20", "data_servico": date(2026, 3, 1), "diagnostico": "POSITIVO", "ordem_parto": 0, "ordem_tentativa": 1},
            {"numero_matriz": "21", "data_servico": date(2026, 3, 3), "diagnostico": "POSITIVO", "ordem_parto": None, "ordem_tentativa": 1},
        ]
        partos = [
            {"numero_matriz": "10", "data_parto": date(2025, 12, 1), "ordem_parto": 2},
            {"numero_matriz": "11", "data_parto": date(2025, 11, 1), "ordem_parto": 1},
        ]
        return animais, servicos, partos

    _peso = {"20": 400.0, "21": 400.0}

    def test_separa_vaca_e_novilha(self):
        animais, servicos, partos = self._dados()
        r = calcular_indicadores(
            animais, servicos, partos, data_ref=date(2026, 7, 7), peso_por_animal=self._peso,
        )
        cats = r["benchmark_categorias"]
        assert set(cats) == {"todas", "vaca", "novilha"}

        def val(lista, chave):
            return next(b["valor"] for b in lista if b["chave"] == chave)

        # Vacas: 1 prenhez / 2 serviços com resultado = 50% concepção.
        assert val(cats["vaca"], "taxa_concepcao") == 50.0
        # Novilhas: 2 prenhezes / 2 serviços com resultado → 100% concepção.
        assert val(cats["novilha"], "taxa_concepcao") == 100.0
        # Novilhas não têm parto → IEP fica indefinido.
        assert val(cats["novilha"], "iep_meses") is None

    def test_taxa_concepcao_pct_e_alias_do_motor_de_ciclos(self):
        """`reproducao.taxa_concepcao_pct` é o MESMO número de
        `benchmark["taxa_concepcao"]` (categoria "todas") — uma definição só
        de taxa de concepção no sistema inteiro.

        Aqui o motor de ciclos devolve valor (há serviços com matriz e ciclo
        fechado) — ao contrário de `TestIndicadores::test_composicao_e_reproducao`,
        onde ele não fecha janela nenhuma e o acumulado legado devolveria 50,0%.
        """
        animais, servicos, partos = self._dados()
        r = calcular_indicadores(
            animais, servicos, partos, data_ref=date(2026, 7, 7), peso_por_animal=self._peso,
        )
        do_benchmark = next(
            b["valor"] for b in r["benchmark_categorias"]["todas"] if b["chave"] == "taxa_concepcao"
        )
        assert do_benchmark is not None
        assert r["reproducao"]["taxa_concepcao_pct"] == do_benchmark
        # Contagens brutas do período continuam existindo lado a lado, sem
        # serem os termos da taxa (3 POSITIVO / 1 NEGATIVO nesta fixture).
        rep = r["reproducao"]
        assert (rep["servicos_positivos"], rep["servicos_negativos"]) == (3, 1)

    def test_metas_vem_dos_parametros_e_novilha_tem_meta_propria(self):
        """taxa_servico/taxa_prenhez_ciclo/taxa_concepcao passam a ler
        Configurações > Parâmetros (meta_taxa_servico/meta_taxa_prenhez/
        meta_taxa_concepcao/meta_concepcao_novilha) em vez do valor fixo de
        BENCHMARK_METAS — e novilha usa sua própria meta de concepção,
        diferente da meta de vacas."""
        animais, servicos, partos = self._dados()
        r = calcular_indicadores(animais, servicos, partos, data_ref=date(2026, 7, 7))
        cats = r["benchmark_categorias"]

        def meta(lista, chave):
            return next(b["meta"] for b in lista if b["chave"] == chave)

        assert meta(cats["todas"], "taxa_servico") == 50.0
        assert meta(cats["todas"], "taxa_prenhez_ciclo") == 18.0
        assert meta(cats["vaca"], "taxa_concepcao") == 35.0
        assert meta(cats["todas"], "taxa_concepcao") == 35.0
        assert meta(cats["novilha"], "taxa_concepcao") == 60.0


# ============================================================
# MOTOR DA AGENDA — pendências de parto provável
# ============================================================

class TestAgendaEngine:
    def _base(self, partos):
        from fazenda.rules.agenda_engine import AgendaEngine
        animais = [{"numero": "500", "ativo": True, "sit_rep": "Ges.", "raca": "Girolando",
                    "del_dias": 60, "grupo_primario": "02 - VACAS ALTA"}]
        servicos = [{"numero_matriz": "500", "data_servico": date(2024, 11, 1),
                     "diagnostico": "POSITIVO", "ult_ocorrencia": 1, "ordem_parto": 1}]
        return AgendaEngine().calcular(date(2026, 7, 7), animais, servicos, partos, [], [], [])

    def test_parto_provavel_suprimido_se_ja_pariu(self):
        # Serviço 2024-11-01 → parto provável ~2025-08; se já há parto após o
        # serviço, a prenhez se resolveu e não deve virar pendência.
        res = self._base([{"numero_matriz": "500", "data_parto": date(2025, 8, 15), "ordem_parto": 1}])
        partos_prov = [e for e in res.eventos if e.descricao.startswith("Parto provável")]
        assert partos_prov == []

    def test_parto_provavel_gerado_se_ainda_prenhe(self):
        # Sem parto após o serviço → a prenhez segue em aberto e o parto
        # provável deve ser gerado (mesmo que vencido).
        res = self._base([])
        partos_prov = [e for e in res.eventos if e.descricao.startswith("Parto provável")]
        assert len(partos_prov) == 1
        assert partos_prov[0].numero_animal == "500"


class TestNecessidadeDeCompra:
    def _calcular(self, estoque):
        from fazenda.rules.agenda_engine import AgendaEngine
        return AgendaEngine().calcular(date(2026, 7, 7), [], [], [], estoque, [], [])

    def test_gera_evento_quando_marcado_e_abaixo_do_minimo(self):
        estoque = [{"nome": "Sal mineral", "quantidade": 2, "estoque_minimo": 10,
                    "unidade": "kg", "exibir_necessidade_compra_agenda": True}]
        res = self._calcular(estoque)
        compras = [e for e in res.eventos if e.descricao.startswith("Comprar")]
        assert len(compras) == 1
        assert "Sal mineral" in compras[0].descricao
        assert compras[0].categoria == "Gestão/Financeiro"

    def test_nao_gera_se_nao_marcado(self):
        estoque = [{"nome": "Sal mineral", "quantidade": 2, "estoque_minimo": 10, "unidade": "kg"}]
        res = self._calcular(estoque)
        assert not [e for e in res.eventos if e.descricao.startswith("Comprar")]

    def test_nao_gera_se_acima_do_minimo(self):
        estoque = [{"nome": "Sal mineral", "quantidade": 20, "estoque_minimo": 10,
                    "unidade": "kg", "exibir_necessidade_compra_agenda": True}]
        res = self._calcular(estoque)
        assert not [e for e in res.eventos if e.descricao.startswith("Comprar")]
