"""
Isolamento por fazenda em Patrimônio/Manutenção de Patrimônio (Fase 3D).
Garante que uma fazenda não vê/edita item de patrimônio de outra fazenda, que
o registro de manutenção nasce com o fazenda_id correto (inclusive o
lançamento financeiro gerado), e que token legado (sem fazenda) continua
vendo tudo, exatamente como antes do retrofit multi-tenant.

Curva ABC não tem endpoint de leitura (só é escrita via CSV/upload) — cobrir
só o backfill/coluna aditiva já é verificado pelo teste de migração; não há
comportamento de API a testar aqui.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, Patrimonio
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Teste"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        # Patrimônio só nasce via importação de CSV — semeado direto no banco
        # para o teste, como qualquer outra fixture de dados pré-existentes.
        s.add(Patrimonio(id=1, nome="Trator fazenda 1", fazenda_id=1, valor_total=100000.0))
        s.add(Patrimonio(id=2, nome="Ordenhadeira fazenda 2", fazenda_id=2, valor_total=50000.0))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "outroadmin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestIsolamentoPatrimonio:
    def test_fazenda_1_nao_ve_patrimonio_da_fazenda_2_na_listagem(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.get("/financeiro/patrimonio")
        assert r.status_code == 200
        nomes = {i["nome"] for i in r.json()["itens"]}
        assert "Trator fazenda 1" in nomes
        assert "Ordenhadeira fazenda 2" not in nomes

    def test_token_legado_ve_patrimonio_de_todas_as_fazendas(self, client):
        c, _ = client
        _como_fazenda(None)
        r = c.get("/financeiro/patrimonio")
        assert r.status_code == 200
        nomes = {i["nome"] for i in r.json()["itens"]}
        assert "Trator fazenda 1" in nomes
        assert "Ordenhadeira fazenda 2" in nomes

    def test_fazenda_1_nao_edita_plano_de_manutencao_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.put("/financeiro/patrimonio/2/manutencao-plano", json={
            "frequencia_manutencao_meses": 6,
        })
        assert r.status_code == 404

    def test_fazenda_2_edita_seu_proprio_plano_de_manutencao(self, client):
        c, _ = client
        _como_fazenda(2)
        r = c.put("/financeiro/patrimonio/2/manutencao-plano", json={
            "frequencia_manutencao_meses": 6,
        })
        assert r.status_code == 200, r.text

    def test_fazenda_1_nao_ve_nem_registra_manutencao_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(1)
        assert c.get("/financeiro/patrimonio/2/manutencoes").status_code == 404
        r = c.post("/financeiro/patrimonio/2/manutencao", json={
            "data_realizacao": "2026-07-01", "valor": 500.0, "gerar_conta_a_pagar": False,
        })
        assert r.status_code == 404

    def test_fazenda_2_registra_manutencao_com_fazenda_id_correto(self, client):
        c, _ = client
        _como_fazenda(2)
        r = c.post("/financeiro/patrimonio/2/manutencao", json={
            "data_realizacao": "2026-07-01", "valor": 500.0, "gerar_conta_a_pagar": True,
            "centro_custo": "Pecuária Leiteira",
        })
        assert r.status_code == 201, r.text
        assert r.json()["manutencao"]["fazenda_id"] == 2

        # O lançamento financeiro gerado junto também nasce da fazenda 2 —
        # não deve aparecer para a fazenda 1.
        _como_fazenda(1)
        lancamentos_f1 = c.get("/financeiro/lancamentos").json()["lancamentos"]
        assert not any("Ordenhadeira fazenda 2" in (l.get("descricao") or "") for l in lancamentos_f1)

        _como_fazenda(2)
        lancamentos_f2 = c.get("/financeiro/lancamentos").json()["lancamentos"]
        assert any("Ordenhadeira fazenda 2" in (l.get("descricao") or "") for l in lancamentos_f2)
