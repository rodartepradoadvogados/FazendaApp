"""
Isolamento por fazenda no núcleo do Financeiro (Fase 3A) — garante que um
lançamento (ContaGerencial/LancamentoItem) criado por uma fazenda nunca
aparece para outra, e que ações de baixa/edição por id não vazam entre
fazendas mesmo sabendo o id exato do registro da outra fazenda.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
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


def _criar_lancamento(c, descricao: str, valor: float = 100.0):
    payload = {
        "tipo": "despesa",
        "itens": [{"produto": descricao, "valor_total": valor}],
        "centro_custo": "Pecuária Leiteira",
        "data_emissao": str(date.today()),
        "data_vencimento": str(date.today()),
        "parcelas": [],
        "data_pagamento": None,
    }
    r = c.post("/financeiro/lancamentos", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestIsolamentoFinanceiroFazenda:
    def test_lancamento_criado_por_fazenda_1_nao_aparece_para_fazenda_2(self, client):
        c, engine = client
        _como_fazenda(1)
        _criar_lancamento(c, "Ração fazenda 1")

        _como_fazenda(2)
        r = c.get("/financeiro/lancamentos")
        assert r.status_code == 200
        descricoes = {item["descricao"] for item in r.json()["lancamentos"]}
        assert "Ração fazenda 1" not in descricoes

    def test_fazenda_1_continua_vendo_seu_proprio_lancamento(self, client):
        c, engine = client
        _como_fazenda(1)
        _criar_lancamento(c, "Adubo fazenda 1")

        r = c.get("/financeiro/lancamentos")
        assert r.status_code == 200
        descricoes = {item["descricao"] for item in r.json()["lancamentos"]}
        assert "Adubo fazenda 1" in descricoes

    def test_pagar_lancamento_de_outra_fazenda_devolve_404(self, client):
        c, engine = client
        _como_fazenda(1)
        criado = _criar_lancamento(c, "Combustível fazenda 1")
        lancamento_id = criado["ids"][0]

        _como_fazenda(2)
        r = c.put(
            f"/financeiro/lancamentos/{lancamento_id}/pagar",
            json={"data_pagamento": str(date.today()), "valor_pago": 100.0},
        )
        assert r.status_code == 404

    def test_editar_lancamento_de_outra_fazenda_devolve_404(self, client):
        c, engine = client
        _como_fazenda(1)
        criado = _criar_lancamento(c, "Vacina fazenda 1")
        lancamento_id = criado["ids"][0]

        _como_fazenda(2)
        r = c.put(f"/financeiro/lancamentos/{lancamento_id}", json={"descricao": "Tentativa de invasão"})
        assert r.status_code == 404

    def test_lancamento_sem_fazenda_no_token_ve_tudo_como_antes(self, client):
        c, engine = client
        _como_fazenda(1)
        _criar_lancamento(c, "Lançamento fazenda 1 (legado)")
        _como_fazenda(2)
        _criar_lancamento(c, "Lançamento fazenda 2 (legado)")

        # Token legado (sem 'fid') não filtra por fazenda_id — vê tudo,
        # exatamente como antes do retrofit multi-tenant (sem retroatividade).
        _como_fazenda(None)
        r = c.get("/financeiro/lancamentos")
        assert r.status_code == 200
        descricoes = {item["descricao"] for item in r.json()["lancamentos"]}
        assert "Lançamento fazenda 1 (legado)" in descricoes
        assert "Lançamento fazenda 2 (legado)" in descricoes


def _criar_recorrente(c, descricao: str):
    payload = {"descricao": descricao, "tipo": "despesa", "centro_custo": "Pecuária Leiteira"}
    r = c.post("/financeiro/recorrentes", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestIsolamentoLancamentoRecorrenteFazenda:
    """Mesmo piloto conservador de multi-fazenda dos demais cadastros do
    módulo Financeiro — o modelo recorrente de uma fazenda nunca aparece,
    nem é editável/gerável, por outra fazenda."""

    def test_modelo_criado_por_fazenda_1_nao_aparece_para_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(1)
        _criar_recorrente(c, "Energia fazenda 1")

        _como_fazenda(2)
        r = c.get("/financeiro/recorrentes")
        assert r.status_code == 200
        assert "Energia fazenda 1" not in {m["descricao"] for m in r.json()}

    def test_atualizar_modelo_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(1)
        modelo_id = _criar_recorrente(c, "Internet fazenda 1")["id"]

        _como_fazenda(2)
        r = c.put(f"/financeiro/recorrentes/{modelo_id}", json={"descricao": "Invasão", "tipo": "despesa"})
        assert r.status_code == 404

    def test_gerar_a_partir_de_modelo_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(1)
        modelo_id = _criar_recorrente(c, "Telefone fazenda 1")["id"]

        _como_fazenda(2)
        r = c.post(f"/financeiro/recorrentes/{modelo_id}/gerar", json={"valor": 100.0})
        assert r.status_code == 404

    def test_lancamento_gerado_pela_fazenda_1_nao_aparece_para_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(1)
        modelo_id = _criar_recorrente(c, "Aluguel fazenda 1")["id"]
        gerado = c.post(f"/financeiro/recorrentes/{modelo_id}/gerar", json={"valor": 500.0})
        assert gerado.status_code == 201

        _como_fazenda(2)
        r = c.get("/financeiro/lancamentos")
        numeros = {item["numero_lancamento"] for item in r.json()["lancamentos"]}
        assert gerado.json()["numero_lancamento"] not in numeros
