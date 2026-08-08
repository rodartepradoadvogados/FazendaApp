"""
Reprodução + verificação das 6 rotas de isolamento entre fazendas encontradas
na auditoria site-wide: uma fazenda conseguia LER ou SOBRESCREVER dado de
outra sabendo (ou adivinhando) o id, porque a rota nunca comparava
`registro.fazenda_id` com a fazenda autenticada — em alguns casos nem
declarava `fazenda_id` como dependência.

  B1 — GET  /financeiro/contas-a-pagar          (sem filtro nenhum)
  B2 — PUT  /financeiro/contas-correntes/{id}    (IDOR)
  B3 — PUT  /financeiro/plano-contas/{id}        (IDOR)
  B4 — PUT  /financeiro/centros-custo/{id}       (IDOR)
  B5 — PUT  /cadastro/estoque-itens/{id}         (IDOR)
  B6 — PUT/DELETE /alimentacao/alimentos/{id}    (IDOR)

Mesmo fixture/convenção de test_financeiro_fazenda_isolamento.py.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

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
    from fazenda.auth import get_current_user

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


class TestB1ContasAPagarFiltraPorFazenda:
    def test_fazenda_2_nao_ve_conta_a_pagar_da_fazenda_1(self, client):
        c, _ = client
        vencimento = str(date.today() + timedelta(days=5))
        _como_fazenda(1)
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração fazenda 1", "valor_total": 55000.0}],
            "centro_custo": "Pecuária Leiteira",
            "data_emissao": str(date.today()), "data_vencimento": vencimento,
            "parcelas": [], "data_pagamento": None,
        })
        assert r.status_code == 201, r.text

        _como_fazenda(2)
        resp = c.get("/financeiro/contas-a-pagar")
        assert resp.status_code == 200
        assert all(item["descricao"] != "Ração fazenda 1" for item in resp.json())


class TestB2ContaCorrenteIDOR:
    def test_editar_conta_corrente_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(1)
        criado = c.post("/financeiro/contas-correntes", json={
            "banco": "Banco do Brasil", "agencia": "0001", "numero_conta": "12345-6",
        })
        assert criado.status_code == 200, criado.text
        conta_id = criado.json()["id"]

        _como_fazenda(2)
        r = c.put(f"/financeiro/contas-correntes/{conta_id}", json={
            "banco": "INVADIDO", "agencia": "9999", "numero_conta": "0-0",
        })
        assert r.status_code == 404

        _como_fazenda(1)
        ainda = c.get("/financeiro/contas-correntes").json()
        assert any(x["banco"] == "Banco do Brasil" for x in ainda)
        assert all(x["banco"] != "INVADIDO" for x in ainda)


class TestB3PlanoContasIDOR:
    def test_editar_plano_de_contas_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(1)
        criado = c.post("/financeiro/plano-contas", json={"codigo": "8.88", "nome": "Original fazenda 1"})
        assert criado.status_code == 200, criado.text
        conta_id = criado.json()["id"]

        _como_fazenda(2)
        r = c.put(f"/financeiro/plano-contas/{conta_id}", json={"codigo": "8.88", "nome": "INVADIDO"})
        assert r.status_code == 404


class TestB4CentroCustoIDOR:
    def test_editar_centro_de_custo_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(1)
        criado = c.post("/financeiro/centros-custo", json={"nome": "Original fazenda 1"})
        assert criado.status_code == 200, criado.text
        centro_id = criado.json()["id"]

        _como_fazenda(2)
        r = c.put(f"/financeiro/centros-custo/{centro_id}", json={"nome": "INVADIDO"})
        assert r.status_code == 404


class TestB5EstoqueItensIDOR:
    def test_editar_metadados_de_item_de_estoque_de_outra_fazenda_devolve_404(self, client):
        c, engine = client
        _como_fazenda(1)
        # Item de estoque nasce pelo módulo de estoque, não pelo cadastro —
        # cria direto via sessão pra isolar só o comportamento do PUT.
        from fazenda.models import Estoque
        with Session(engine) as s:
            item = Estoque(nome="Sincrocp", quantidade=10, unidade="ml", fazenda_id=1, estocavel=True)
            s.add(item)
            s.commit()
            s.refresh(item)
            item_id = item.id

        _como_fazenda(2)
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"estocavel": False})
        assert r.status_code == 404

        with Session(engine) as s:
            ainda = s.get(Estoque, item_id)
            assert ainda.estocavel is True, "fazenda 2 não pode ter mudado o estocável do item da fazenda 1"


class TestB6AlimentosIDOR:
    def test_editar_alimento_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(1)
        criado = c.post("/alimentacao/alimentos", json={"nome": "Silagem de milho"})
        assert criado.status_code in (200, 201), criado.text
        alimento_id = criado.json()["id"]

        _como_fazenda(2)
        r = c.put(f"/alimentacao/alimentos/{alimento_id}", json={"nome": "INVADIDO"})
        assert r.status_code == 404

    def test_excluir_alimento_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(1)
        criado = c.post("/alimentacao/alimentos", json={"nome": "Feno"})
        assert criado.status_code in (200, 201), criado.text
        alimento_id = criado.json()["id"]

        _como_fazenda(2)
        r = c.delete(f"/alimentacao/alimentos/{alimento_id}")
        assert r.status_code == 404

        _como_fazenda(1)
        ainda = c.get("/alimentacao/alimentos").json()
        assert any(a["nome"] == "Feno" for a in ainda), "fazenda 2 não pode ter excluído o alimento da fazenda 1"
