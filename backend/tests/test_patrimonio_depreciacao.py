"""
Matemática de depreciação do patrimônio (rules/patrimonio.py) — não havia
NENHUM teste da fórmula para bem depreciável antes desta onda. Cobre os
defeitos da Onda 1 do módulo de Patrimônio:
- A1: terra do CSV herdando `depreciavel=True` (o default do model);
- A2: reimportar o CSV preserva o que só existe no app;
- E3: baixa deprecia proporcionalmente até a data_baixa (não o bem inteiro);
- E4: vida útil em texto livre ("10 anos e 6 meses", "60 Meses", "60");
- E6: quantidade x valor por unidade;
- E7: mês cheio (convenção contábil) em vez de dias corridos / 365,25;
- E8: valor residual maior que o valor do bem;
- E9: KPI "valor atual" não soma itens inconsistentes junto com os normais;
- E10: frequência de atualização de valor de mercado "0 = nunca".

IMPORTANTE (contexto pedido pelo dono do produto): depreciação é despesa
CONTÁBIL — desgaste do bem ao longo da vida útil, nunca saída de caixa. Nada
aqui trata de financiamento (principal = saída de caixa, nunca despesa
contábil) — os dois não se misturam neste módulo.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, Patrimonio
from fazenda.parsers.patrimonio import parse_patrimonio
from fazenda.rules.patrimonio import (
    calcular_depreciacao, eh_tipo_nao_depreciavel, meses_cheios, valor_base_aquisicao,
)


# ---------------------------------------------------------------------------
# E7 — meses cheios: mês de entrada em operação conta inteiro; mês corrente
# só conta quando fecha (chega ao último dia do mês).
# ---------------------------------------------------------------------------
class TestMesesCheios:
    def test_mesmo_mes_da_imobilizacao_conta_como_1_mes_mesmo_sem_fechar(self):
        assert meses_cheios(date(2025, 1, 20), date(2025, 1, 20)) == 1
        assert meses_cheios(date(2025, 1, 1), date(2025, 1, 31)) == 1

    def test_mes_corrente_so_conta_quando_fecha(self):
        # 1º de fevereiro: fevereiro começou mas não fechou -> só janeiro conta.
        assert meses_cheios(date(2025, 1, 15), date(2025, 2, 1)) == 1
        # 28/fev/2025 (ano não bissexto) é o último dia do mês -> fevereiro fecha.
        assert meses_cheios(date(2025, 1, 15), date(2025, 2, 28)) == 2

    def test_referencia_antes_da_imobilizacao_e_zero(self):
        assert meses_cheios(date(2026, 1, 1), date(2025, 1, 1)) == 0

    def test_exemplo_trator_do_plano_18_meses(self):
        assert meses_cheios(date(2025, 1, 1), date(2026, 6, 30)) == 18


# ---------------------------------------------------------------------------
# E3 + E7 — exemplo numérico do plano: trator baixado no meio da vida útil.
# ---------------------------------------------------------------------------
def test_baixa_deprecia_proporcionalmente_ate_a_data_baixa():
    """Trator, valor 150.000, residual 5.000, vida útil 10 anos (120 meses),
    imobilizado 01/01/2025, baixado 30/06/2026.

    Cálculo (convenção de mês cheio — ver TestMesesCheios acima):
    - depreciável = 150.000 - 5.000 = 145.000
    - dep. mensal = 145.000 / 120 = 1.208,3333...
    - meses cheios até 30/06/2026 = 18
    - acumulada = 1.208,3333... x 18 = 21.750,00
    - valor contábil na baixa = 150.000 - 21.750 = 128.250,00

    O bug original (E3) devolvia acumulada = valor_total - residual =
    145.000 inteiro, como se o bem tivesse ficado os 10 anos todos em
    operação antes de ser baixado."""
    item = {
        "valor_total": 150000.0, "valor_residual": 5000.0, "vida_util": "10 Anos",
        "data_imobilizacao": date(2025, 1, 1), "data_baixa": date(2026, 6, 30),
        "depreciavel": True,
    }
    dep = calcular_depreciacao(item, hoje=date(2026, 8, 27))
    assert dep["depreciacao_acumulada"] == 21750.0
    assert dep["valor_atual"] == 128250.0
    assert dep["inconsistencia"] is None


def test_sem_baixa_deprecia_ate_hoje():
    item = {
        "valor_total": 120000.0, "valor_residual": 0.0, "vida_util": "10 Anos",
        "data_imobilizacao": date(2024, 1, 15), "depreciavel": True,
    }
    # Exatamente 1 ano depois, mesmo dia do mês -> 12 meses cheios de 120.
    dep = calcular_depreciacao(item, hoje=date(2025, 1, 15))
    assert dep["depreciacao_acumulada"] == 12000.0
    assert dep["valor_atual"] == 108000.0


def test_bem_baixado_com_cadastro_incompleto_nao_cobra_correcao():
    """Bem JÁ BAIXADO (vendido/sucateado) sem vida útil ou sem data de
    imobilização não pode gerar inconsistência: ele está fora do ativo (não
    entra em nenhum total) e cobrar cadastro de um trator já vendido só
    encheria de ruído a tela que existe para apontar o que ainda dá para
    consertar. É dado legado importado — a fazenda não vai voltar atrás para
    preencher a vida útil de um bem que não tem mais."""
    base = {
        "valor_total": 50000.0, "valor_residual": None, "depreciavel": True,
        "data_imobilizacao": date(2020, 1, 1), "data_baixa": date(2023, 6, 30),
    }
    assert calcular_depreciacao({**base, "vida_util": None}, hoje=date(2026, 8, 27))["inconsistencia"] is None
    assert calcular_depreciacao({**base, "vida_util": "10 Anos", "data_imobilizacao": None},
                                hoje=date(2026, 8, 27))["inconsistencia"] is None
    # Mas o MESMO cadastro incompleto num bem EM USO continua sendo cobrado —
    # nesse caso a correção é possível e muda o resultado do exercício.
    em_uso = {**base, "vida_util": None, "data_baixa": None}
    assert calcular_depreciacao(em_uso, hoje=date(2026, 8, 27))["inconsistencia"] is not None


def test_depreciacao_nunca_passa_do_valor_residual():
    item = {
        "valor_total": 50000.0, "valor_residual": 10000.0, "vida_util": "2 Anos",
        "data_imobilizacao": date(2015, 1, 1), "depreciavel": True,
    }
    dep = calcular_depreciacao(item, hoje=date(2026, 8, 27))
    assert dep["depreciacao_acumulada"] == 40000.0
    assert dep["valor_atual"] == 10000.0


# ---------------------------------------------------------------------------
# E4 — vida útil em texto livre.
# ---------------------------------------------------------------------------
class TestVidaUtilTextoLivre:
    def _anos(self, texto):
        item = {
            "valor_total": 1000.0, "valor_residual": 0.0, "vida_util": texto,
            "data_imobilizacao": date(2020, 1, 1),
        }
        return calcular_depreciacao(item, hoje=date(2020, 1, 1))["vida_util_anos"]

    def test_anos_e_meses(self):
        # Bug antigo: pegava só o "10" e via "meses" em algum lugar do texto
        # -> 10/12 = 0,83 ano, em vez de 10,5.
        assert self._anos("10 anos e 6 meses") == 10.5

    def test_so_anos(self):
        assert self._anos("7 Anos") == 7.0

    def test_so_meses(self):
        assert self._anos("60 Meses") == 5.0

    def test_numero_solto_assume_anos(self):
        assert self._anos("60") == 60.0

    def test_valor_implausivel_vira_inconsistencia_em_vez_de_aceito_em_silencio(self):
        item = {
            "valor_total": 1000.0, "valor_residual": 0.0, "vida_util": "500",
            "data_imobilizacao": date(2020, 1, 1),
        }
        dep = calcular_depreciacao(item, hoje=date(2020, 1, 1))
        assert dep["vida_util_anos"] is None
        assert dep["inconsistencia"] is not None

    def test_texto_nao_reconhecido_vira_inconsistencia(self):
        item = {
            "valor_total": 1000.0, "valor_residual": 0.0, "vida_util": "indefinida",
            "data_imobilizacao": date(2020, 1, 1),
        }
        dep = calcular_depreciacao(item, hoje=date(2020, 1, 1))
        assert dep["inconsistencia"] is not None


# ---------------------------------------------------------------------------
# E8 — valor residual maior que o valor do bem.
# ---------------------------------------------------------------------------
def test_valor_residual_maior_que_valor_total_gera_inconsistencia():
    item = {
        "valor_total": 15000.0, "valor_residual": 20000.0, "vida_util": "5 Anos",
        "data_imobilizacao": date(2020, 1, 1), "depreciavel": True,
    }
    dep = calcular_depreciacao(item, hoje=date(2026, 8, 27))
    # Bug antigo: base depreciável ia a 0, "acumulada"=0 e inconsistencia=None
    # — passava 100% silencioso.
    assert dep["depreciacao_acumulada"] is None
    assert dep["inconsistencia"] is not None
    assert dep["valor_atual"] == 15000.0


# ---------------------------------------------------------------------------
# E6 — quantidade x valor por unidade.
# ---------------------------------------------------------------------------
class TestValorBaseAquisicao:
    def test_padrao_valor_total_ja_e_o_lote_inteiro(self):
        assert valor_base_aquisicao({"valor_total": 150000.0, "quantidade": 50}) == 150000.0

    def test_valor_por_unidade_multiplica_pela_quantidade(self):
        assert valor_base_aquisicao(
            {"valor_total": 3000.0, "quantidade": 50, "valor_por_unidade": True}
        ) == 150000.0

    def test_valor_por_unidade_sem_quantidade_cai_no_valor_total(self):
        assert valor_base_aquisicao({"valor_total": 3000.0, "valor_por_unidade": True}) == 3000.0

    def test_calcular_depreciacao_usa_a_base_por_unidade(self):
        # 10 unidades a R$ 3.000 cada = base de R$ 30.000.
        item = {
            "valor_total": 3000.0, "quantidade": 10, "valor_por_unidade": True,
            "valor_residual": 0.0, "vida_util": "10 Anos", "data_imobilizacao": date(2025, 1, 1),
        }
        dep = calcular_depreciacao(item, hoje=date(2025, 1, 1))
        # 1 mês cheio (mesmo mês da imobilização) de 120 -> 30000/120 = 250.
        assert dep["depreciacao_acumulada"] == 250.0
        assert dep["valor_atual"] == 29750.0


# ---------------------------------------------------------------------------
# A1 — Terra do CSV real não entra depreciável nem gera inconsistência.
# ---------------------------------------------------------------------------
PATRIMONIO_CSV = (
    "Tipo patr.;Nome Patr.;N° patr.;Ativ. cul.;Placa;Dt. imob.;Mét. depr.;Vd. útil;Vlr. res.;Quant.;Uni.;Vlr. tot.;Dt. baixa pat.;\n"
    "Implemento;ENXADA ROTATIVA ERG 2000 - GELGÁS;7;;;01/05/2026;Linear;7 Anos;6875;1;un;27500;;\n"
    "Terra;Fazenda;1;;;01/01/2025;;;;1;ha;334215,56;;\n"
).encode("windows-1252")


def test_a1_terra_do_csv_nao_entra_depreciavel():
    itens = parse_patrimonio(PATRIMONIO_CSV)
    terra = next(i for i in itens if i.nome == "Fazenda")
    assert terra.depreciavel is False

    implemento = next(i for i in itens if i.nome != "Fazenda")
    assert implemento.depreciavel is True


def test_a1_terra_nao_gera_inconsistencia_de_vida_util():
    itens = parse_patrimonio(PATRIMONIO_CSV)
    terra = next(i for i in itens if i.nome == "Fazenda")
    dep = calcular_depreciacao(terra.model_dump(), hoje=date(2026, 8, 27))
    assert dep["inconsistencia"] is None
    assert dep["valor_atual"] == 334215.56


@pytest.mark.parametrize("tipo", ["Terra", "TERRA", "terra", "Terreno", "TERRENO", "Fazenda", "FAZENDA"])
def test_eh_tipo_nao_depreciavel_tolera_acento_e_caixa(tipo):
    assert eh_tipo_nao_depreciavel(tipo) is True


def test_eh_tipo_nao_depreciavel_outros_tipos_continuam_depreciaveis():
    assert eh_tipo_nao_depreciavel("Máquinas") is False
    assert eh_tipo_nao_depreciavel("Implemento") is False
    assert eh_tipo_nao_depreciavel(None) is False


# ---------------------------------------------------------------------------
# Testes de integração (via API) — A1 (backfill), A2 (upsert), E5, E8, E9, E10.
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin-teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        c._engine = engine  # type: ignore[attr-defined]
        yield c

    main.app.dependency_overrides.clear()


class TestA1BackfillDepreciavel:
    """GET .../depreciavel-divergencias / POST .../depreciavel-corrigir —
    corrige o dado legado (importado antes da correção do parser) sem tocar
    em nada até um admin confirmar (report-first, mesmo padrão das
    reconstruções de ordem de parto em producao.py)."""

    def _criar_terra_legada(self, engine) -> int:
        with Session(engine) as s:
            item = Patrimonio(nome="Fazenda Velha", tipo="Terra", valor_total=200000.0)  # depreciavel default True
            s.add(item)
            s.commit()
            s.refresh(item)
            return item.id

    def test_relatorio_lista_terra_marcada_depreciavel_por_engano(self, client):
        engine = client._engine
        self._criar_terra_legada(engine)
        r = client.get("/financeiro/patrimonio/depreciavel-divergencias")
        assert r.status_code == 200
        assert r.json()["muda"] == 1
        assert r.json()["itens"][0]["nome"] == "Fazenda Velha"

    def test_correcao_sem_confirmar_nao_grava_nada(self, client):
        engine = client._engine
        item_id = self._criar_terra_legada(engine)
        r = client.post("/financeiro/patrimonio/depreciavel-corrigir", json={})
        assert r.status_code == 400
        with Session(engine) as s:
            assert s.get(Patrimonio, item_id).depreciavel is True

    def test_correcao_com_confirmar_marca_nao_depreciavel(self, client):
        engine = client._engine
        item_id = self._criar_terra_legada(engine)
        r = client.post("/financeiro/patrimonio/depreciavel-corrigir", json={"confirmar": True})
        assert r.status_code == 200
        assert r.json()["corrigidos"] == 1
        with Session(engine) as s:
            item = s.get(Patrimonio, item_id)
            assert item.depreciavel is False
            assert item.valor_mercado_atual == 200000.0  # fallback igual ao de criar_patrimonio

        # relatório fica vazio depois de corrigido.
        assert client.get("/financeiro/patrimonio/depreciavel-divergencias").json()["muda"] == 0


class TestA2ReimportPreservaEstado:
    CSV_1 = (
        "Tipo patr.;Nome Patr.;N° patr.;Ativ. cul.;Placa;Dt. imob.;Mét. depr.;Vd. útil;Vlr. res.;Quant.;Uni.;Vlr. tot.;Dt. baixa pat.;\n"
        "Máquinas;Trator MF 265;10;;;01/01/2020;Linear;10 Anos;5000;1;un;100000;;\n"
        "Terra;Fazenda Sede;;;;01/01/2015;;;;1;ha;500000;;\n"
    ).encode("windows-1252")

    # Mesmo nº/nome+tipo do CSV_1, só o valor do trator corrigido (o CSV É a
    # fonte de verdade para os campos que ele traz).
    CSV_2 = (
        "Tipo patr.;Nome Patr.;N° patr.;Ativ. cul.;Placa;Dt. imob.;Mét. depr.;Vd. útil;Vlr. res.;Quant.;Uni.;Vlr. tot.;Dt. baixa pat.;\n"
        "Máquinas;Trator MF 265;10;;;01/01/2020;Linear;10 Anos;5000;1;un;105000;;\n"
        "Terra;Fazenda Sede;;;;01/01/2015;;;;1;ha;500000;;\n"
    ).encode("windows-1252")

    def test_reimport_preserva_campos_do_app_e_atualiza_campos_do_csv(self, client):
        engine = client._engine
        r1 = client.post("/upload/patrimonio", files={"file": ("p.csv", self.CSV_1, "text/csv")})
        assert r1.status_code == 200
        assert r1.json()["inseridos"] == 2

        with Session(engine) as s:
            trator = s.exec(select(Patrimonio).where(Patrimonio.numero == "10")).one()
            terra = s.exec(select(Patrimonio).where(Patrimonio.nome == "Fazenda Sede")).one()
            trator_id, terra_id = trator.id, terra.id

            # Correções manuais feitas pelo app entre um upload e outro.
            trator.frequencia_manutencao_meses = 6
            trator.data_ultima_manutencao = date(2026, 1, 1)
            trator.data_proxima_manutencao = date(2026, 7, 1)
            trator.observacao_manutencao = "Revisão geral"
            trator.valor_por_unidade = True
            s.add(trator)

            terra.depreciavel = False  # já deveria ter vindo assim (A1), mas simula a correção manual
            terra.valor_mercado_atual = 550000.0
            terra.data_ultima_atualizacao_valor_mercado = date(2026, 6, 1)
            terra.atualizacao_valor_mercado_frequencia_meses = 24
            s.add(terra)

            # Item cadastrado pelo app, que ainda não está no Ideagri.
            avulso = Patrimonio(nome="Ordenhadeira nova", tipo="Equipamento", valor_total=40000.0)
            s.add(avulso)
            s.commit()
            avulso_id = avulso.id

            # Vínculo real (FK) com um lançamento financeiro.
            conta = ContaGerencial(
                numero_lancamento="1", descricao="Compra trator", data_vencimento=date(2020, 1, 1),
                data_competencia=date(2020, 1, 1), tipo_documento="NF", centro_custo="Geral",
                valor_total=100000.0, parcela_num=1, parcela_total=1, tipo="despesa", origem="manual",
                patrimonio_id=trator_id,
            )
            s.add(conta)
            s.commit()

        r2 = client.post("/upload/patrimonio", files={"file": ("p.csv", self.CSV_2, "text/csv")})
        assert r2.status_code == 200
        assert r2.json()["atualizados"] == 2
        assert r2.json()["inseridos"] == 0

        with Session(engine) as s:
            trator = s.get(Patrimonio, trator_id)
            # Campo que vem do CSV foi atualizado.
            assert trator.valor_total == 105000.0
            # Campos que só existem no app foram preservados.
            assert trator.frequencia_manutencao_meses == 6
            assert trator.data_ultima_manutencao == date(2026, 1, 1)
            assert trator.data_proxima_manutencao == date(2026, 7, 1)
            assert trator.observacao_manutencao == "Revisão geral"
            assert trator.valor_por_unidade is True

            terra = s.get(Patrimonio, terra_id)
            assert terra.depreciavel is False
            assert terra.valor_mercado_atual == 550000.0
            assert terra.data_ultima_atualizacao_valor_mercado == date(2026, 6, 1)
            assert terra.atualizacao_valor_mercado_frequencia_meses == 24

            # Item cadastrado pelo app (fora do CSV) não foi apagado.
            assert s.get(Patrimonio, avulso_id) is not None

            # A FK continua apontando pro MESMO registro (não recriado).
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == "1")).one()
            assert conta.patrimonio_id == trator_id

            assert s.exec(select(Patrimonio)).all().__len__() == 3  # trator + terra + avulso, nada duplicado


class TestE5EdicaoNaoApagaCamposNaoEnviados:
    def test_editar_patrimonio_depreciavel_preserva_atividade_cultura(self, client):
        item_id = client.post("/financeiro/patrimonio", json={
            "nome": "Trator", "valor_total": 100000, "atividade_cultura": "Soja",
        }).json()["id"]
        r = client.put(f"/financeiro/patrimonio/{item_id}", json={"nome": "Trator novo", "valor_total": 100000})
        assert r.status_code == 200
        assert r.json()["atividade_cultura"] == "Soja"

    def test_editar_patrimonio_nao_depreciavel_preserva_valor_de_mercado(self, client):
        item_id = client.post("/financeiro/patrimonio", json={
            "nome": "Terreno", "valor_total": 500000, "depreciavel": False,
        }).json()["id"]
        client.put(f"/financeiro/patrimonio/{item_id}/valor-mercado", json={"valor_mercado_atual": 560000})

        # Edição comum (form do app não manda valor_mercado_atual).
        r = client.put(f"/financeiro/patrimonio/{item_id}", json={
            "nome": "Terreno da sede", "valor_total": 500000, "depreciavel": False,
        })
        assert r.status_code == 200
        assert r.json()["valor_mercado_atual"] == 560000


class TestE8ValidacaoValorResidual:
    def test_criar_com_residual_maior_que_total_da_erro(self, client):
        r = client.post("/financeiro/patrimonio", json={
            "nome": "Trator", "valor_total": 15000, "valor_residual": 20000,
        })
        assert r.status_code == 400

    def test_editar_com_residual_maior_que_total_da_erro(self, client):
        item_id = client.post("/financeiro/patrimonio", json={"nome": "Trator", "valor_total": 15000}).json()["id"]
        r = client.put(f"/financeiro/patrimonio/{item_id}", json={
            "nome": "Trator", "valor_total": 15000, "valor_residual": 20000,
        })
        assert r.status_code == 400


class TestE9TotalNaoMisturaInconsistentes:
    def test_item_inconsistente_fica_fora_do_valor_atual_total(self, client):
        engine = client._engine
        with Session(engine) as s:
            # Consistente: deprecia normalmente.
            s.add(Patrimonio(
                nome="Trator OK", valor_total=100000.0, valor_residual=0.0, vida_util="10 Anos",
                data_imobilizacao=date(2020, 1, 1),
            ))
            # Inconsistente: sem vida útil reconhecível.
            s.add(Patrimonio(
                nome="Trator sem vida útil", valor_total=50000.0, data_imobilizacao=date(2020, 1, 1),
            ))
            s.commit()

        r = client.get("/financeiro/patrimonio")
        assert r.status_code == 200
        d = r.json()
        assert d["itens_inconsistentes"] == 1
        assert d["valor_atual_total_inconsistentes"] == 50000.0
        # O total consistente não inclui os 50.000 do item com problema.
        assert d["valor_atual_total"] < 100000.0


def test_e10_frequencia_zero_e_respeitada(monkeypatch):
    """0 = "nunca" precisa continuar 0 — `0 or 12` (bug antigo) convertia
    silenciosamente em 12."""
    import fazenda.rules.parametros as parametros_mod

    monkeypatch.setattr(parametros_mod, "get_param", lambda chave, padrao=None: 0)
    assert parametros_mod.patrimonio_atualizacao_valor_mercado_meses() == 0
