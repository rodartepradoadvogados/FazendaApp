"""Testes de compra de animal (Rebanho > Comprar animal) — efeito financeiro + comissão."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ComissaoCorretagem, CompraAnimal, ContaGerencial


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        c.engine = engine
        yield c

    main.app.dependency_overrides.clear()


class TestRegistrarCompra:
    def test_compra_por_animal_gera_conta_gerencial_despesa(self, client):
        r = client.post("/compras-animais/", json={
            "animais": ["950", "951"], "vendedor": "Fazenda Y", "valor": 4000.0,
            "tipo_valor": "por_animal", "data_compra": "2026-07-08",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["comprados"] == 2

        with Session(client.engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Compra de animal")).first()
            assert conta is not None
            assert conta.tipo == "despesa"
            assert conta.quantidade == 2
            assert conta.valor_unitario == 4000.0
            assert conta.valor_total == 8000.0

            registros = s.exec(select(CompraAnimal)).all()
            assert len(registros) == 2
            assert all(c.valor == 4000.0 and c.tipo_valor == "por_animal" for c in registros)

    def test_compra_valor_total_divide_entre_animais(self, client):
        client.post("/compras-animais/", json={
            "animais": ["950", "951"], "vendedor": "Fazenda Y", "valor": 9000.0,
            "tipo_valor": "total", "data_compra": "2026-07-08",
        })
        with Session(client.engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Compra de animal")).first()
            assert conta.valor_total == 9000.0
            assert conta.valor_unitario == 4500.0

    def test_compra_exige_vendedor_e_valor(self, client):
        r = client.post("/compras-animais/", json={
            "animais": ["950"], "vendedor": "", "valor": 4000.0,
            "tipo_valor": "por_animal", "data_compra": "2026-07-08",
        })
        assert r.status_code == 400

    def test_compra_exige_tipo_valor_valido(self, client):
        r = client.post("/compras-animais/", json={
            "animais": ["950"], "vendedor": "Fazenda Y", "valor": 4000.0,
            "tipo_valor": "invalido", "data_compra": "2026-07-08",
        })
        assert r.status_code == 400

    def test_compra_com_comissao_redirecionada_ja_marca_como_paga(self, client):
        client.post("/compras-animais/", json={
            "animais": ["950"], "vendedor": "Fazenda Y", "valor": 4000.0,
            "tipo_valor": "por_animal", "data_compra": "2026-07-08",
            "pagar_comissao": True, "corretor_nome": "Maria Corretora", "valor_comissao": 200.0,
            "forma_comissao": "redirecionado",
        })
        with Session(client.engine) as s:
            comissao = s.exec(select(ComissaoCorretagem)).first()
            assert comissao is not None
            assert comissao.origem_tipo == "compra_animal"
            compra = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Compra de animal")).first()
            assert compra.valor_total == 4000.0  # valor bruto da compra nunca é líquido da comissão
            despesa_comissao = s.exec(
                select(ContaGerencial).where(ContaGerencial.tipo_documento == "Comissão de corretagem")
            ).first()
            assert despesa_comissao.data_pagamento is not None
            assert despesa_comissao.valor_pago == 200.0

    def test_compra_com_comissao_separada_fica_em_aberto(self, client):
        client.post("/compras-animais/", json={
            "animais": ["950"], "vendedor": "Fazenda Y", "valor": 4000.0,
            "tipo_valor": "por_animal", "data_compra": "2026-07-08",
            "pagar_comissao": True, "corretor_nome": "Maria Corretora", "valor_comissao": 200.0,
            "forma_comissao": "separado",
        })
        with Session(client.engine) as s:
            despesa_comissao = s.exec(
                select(ContaGerencial).where(ContaGerencial.tipo_documento == "Comissão de corretagem")
            ).first()
            assert despesa_comissao.data_pagamento is None

    def test_lista_compras_registradas(self, client):
        client.post("/compras-animais/", json={
            "animais": ["950"], "vendedor": "Fazenda Y", "valor": 4000.0,
            "tipo_valor": "por_animal", "data_compra": "2026-07-08",
        })
        r = client.get("/compras-animais/")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["numero_animal"] == "950"
