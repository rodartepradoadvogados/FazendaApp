"""
Plano Financeiro §1.6 — Agenda por contrato:

- `MODULO_TECNICO_PARA_COMERCIAL` ganhou "reproducao"->"reprodutivo" e
  "rebanho"->"rebanho": fazenda sem esses módulos (plano Financeiro) não vê
  eventos de Reprodução/Rebanho, nem candidatas IATF/BST;
- nova chave ADITIVA `contas_a_receber` (item F do contrato de API), com o
  mesmo formato de `contas_a_pagar`, só com o módulo financeiro contratado, e
  SEM misturar com a pagar; a janela de vencidas continua 30 dias;
- Standard/Gold seguem iguais ao golden (nada some de quem tem os módulos).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import AgendaManual, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import PLANOS_CATALOGO

FAZENDAS = {
    1: ["financeiro", "pedidos"],                                  # plano Financeiro
    2: list(PLANOS_CATALOGO["standard"]["modulos"]),               # rebanho + reprodutivo
    3: list(PLANOS_CATALOGO["gold"]["modulos"]),                   # tudo
    4: ["rebanho", "financeiro"],                                  # base completa, sem reprodutivo
}


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    hoje = date.today()

    with Session(engine) as s:
        for fid, modulos in FAZENDAS.items():
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.commit()
        for fid, modulos in FAZENDAS.items():
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for m in modulos:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=m, preco=0.0, ativo=True))
            # Cenário idêntico em todas: 1 despesa e 3 receitas (1 vence em 3 dias,
            # 1 venceu há 5 dias, 1 venceu há 45 dias = fora da janela de vencidas) + 1 receita quitada.
            s.add(ContaGerencial(
                fazenda_id=fid, numero_lancamento=f"LC-{fid}-D1", descricao="Energia", tipo="despesa",
                data_vencimento=hoje + timedelta(days=2), valor_total=100.0, origem="manual",
            ))
            s.add(ContaGerencial(
                fazenda_id=fid, numero_lancamento=f"LC-{fid}-R1", descricao="Leite a vencer", tipo="receita",
                data_vencimento=hoje + timedelta(days=3), valor_total=900.0, origem="manual",
            ))
            s.add(ContaGerencial(
                fazenda_id=fid, numero_lancamento=f"LC-{fid}-R2", descricao="Leite vencido", tipo="receita",
                data_vencimento=hoje - timedelta(days=5), valor_total=700.0, valor_pago=200.0, origem="manual",
            ))
            s.add(ContaGerencial(
                fazenda_id=fid, numero_lancamento=f"LC-{fid}-R3", descricao="Leite muito antigo", tipo="receita",
                data_vencimento=hoje - timedelta(days=45), valor_total=500.0, origem="manual",
            ))
            s.add(ContaGerencial(
                fazenda_id=fid, numero_lancamento=f"LC-{fid}-R4", descricao="Leite quitado", tipo="receita",
                data_vencimento=hoje + timedelta(days=1), valor_total=300.0, valor_pago=300.0, origem="manual",
            ))
            s.add(AgendaManual(
                fazenda_id=fid, data_evento=hoje + timedelta(days=1), descricao="Visita do veterinário reprodutivo",
                categoria="Reprodutivo",
            ))
            s.add(AgendaManual(
                fazenda_id=fid, data_evento=hoje + timedelta(days=1), descricao="Conferir o rebanho", categoria="Rebanho",
            ))
            s.add(AgendaManual(
                fazenda_id=fid, data_evento=hoje + timedelta(days=1), descricao="Reunião com o contador",
                categoria="Atividades",
            ))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _descricoes(eventos: list[dict]) -> set[str]:
    return {e["descricao"] for e in eventos}


class TestContasAReceber:
    def test_so_financeiro_ve_a_receber_separado_da_pagar(self, client):
        _como_fazenda(1)
        r = client.get("/agenda/")
        assert r.status_code == 200, r.text
        d = r.json()
        # A pagar: só a despesa.
        assert [c["descricao"] for c in d["contas_a_pagar"]] == ["Energia"]
        # A receber: a vencer em 3 dias + vencida (há 5 dias, saldo em aberto), ordenadas por vencimento.
        # Fora: quitada, e a vencida há 45 dias (janela de vencidas continua 30).
        assert [c["descricao"] for c in d["contas_a_receber"]] == ["Leite vencido", "Leite a vencer"]
        assert d["totais"]["contas_a_receber"] == 2
        assert d["totais"]["contas_a_pagar"] == 1
        # Mesmo formato dos itens de contas_a_pagar.
        assert set(d["contas_a_pagar"][0]) == set(d["contas_a_receber"][0])

    def test_receita_continua_fora_dos_eventos_da_agenda(self, client):
        """A receber é chave própria: não vira evento 'Conta a pagar' (alarme falso, set/2026)."""
        _como_fazenda(1)
        d = client.get("/agenda/").json()
        assert not any("Leite" in e["descricao"] for e in d["eventos"])

    def test_painel_expoe_contas_a_receber(self, client):
        _como_fazenda(1)
        r = client.get("/agenda/painel")
        assert r.status_code == 200, r.text
        d = r.json()
        assert [c["descricao"] for c in d["contas_a_receber"]] == ["Leite vencido", "Leite a vencer"]
        assert [c["descricao"] for c in d["contas_a_pagar"]] == ["Energia"]

    def test_janela_dias_amplia_a_vencer_mas_nao_as_vencidas(self, client):
        _como_fazenda(1)
        d = client.get("/agenda/?dias=1").json()
        # 'dias=1' corta a receita que vence em 3 dias; a vencida há 5 dias segue.
        assert [c["descricao"] for c in d["contas_a_receber"]] == ["Leite vencido"]

    def test_fazenda_sem_financeiro_nao_recebe_nada_a_receber(self, client):
        _como_fazenda(2)  # Standard: rebanho + reprodutivo
        d = client.get("/agenda/").json()
        assert d["contas_a_receber"] == []
        assert d["contas_a_pagar"] == []
        assert d["totais"]["contas_a_receber"] == 0


class TestAgendaPorContrato:
    def test_so_financeiro_sem_eventos_nem_candidatas_de_rebanho(self, client):
        _como_fazenda(1)
        d = client.get("/agenda/").json()
        desc = _descricoes(d["eventos"])
        assert "Reunião com o contador" in desc            # Atividades segue
        assert "Visita do veterinário reprodutivo" not in desc
        assert "Conferir o rebanho" not in desc
        assert d["candidatas_iatf"] == []
        assert d["bst_elegiveis"] == [] and d["bst_nunca_aplicados"] == []
        assert d["proxima_visita_iatf"] is None and d["proxima_visita_bst"] is None
        assert d["hormonios_check"] == []
        assert d["estoque_negativo"] == [] and d["estoque_abaixo_minimo"] == []

    def test_painel_so_financeiro_nao_lista_modulos_de_rebanho(self, client):
        _como_fazenda(1)
        d = client.get("/agenda/painel").json()
        assert d["modulos"] == ["financeiro"]
        assert d["repasse"] is None

    def test_standard_continua_vendo_reproducao_e_rebanho(self, client):
        _como_fazenda(2)
        d = client.get("/agenda/").json()
        desc = _descricoes(d["eventos"])
        assert {"Visita do veterinário reprodutivo", "Conferir o rebanho", "Reunião com o contador"} <= desc
        painel = client.get("/agenda/painel").json()
        assert "reproducao" in painel["modulos"]

    def test_gold_ve_tudo_e_a_receber(self, client):
        _como_fazenda(3)
        d = client.get("/agenda/").json()
        desc = _descricoes(d["eventos"])
        assert {"Visita do veterinário reprodutivo", "Conferir o rebanho", "Reunião com o contador"} <= desc
        assert [c["descricao"] for c in d["contas_a_pagar"]] == ["Energia"]
        assert [c["descricao"] for c in d["contas_a_receber"]] == ["Leite vencido", "Leite a vencer"]

    def test_rebanho_financeiro_sem_reprodutivo_esconde_so_a_reproducao(self, client):
        _como_fazenda(4)
        d = client.get("/agenda/").json()
        desc = _descricoes(d["eventos"])
        assert "Visita do veterinário reprodutivo" not in desc
        assert "Conferir o rebanho" in desc
        assert d["candidatas_iatf"] == []

    def test_dia_a_dia_so_financeiro_nao_traz_reproducao(self, client):
        _como_fazenda(1)
        r = client.get("/agenda/dia")
        assert r.status_code == 200, r.text
        desc = _descricoes(r.json()["eventos"])
        assert "Visita do veterinário reprodutivo" not in desc
        assert "Reunião com o contador" in desc
