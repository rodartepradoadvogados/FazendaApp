"""Testes de compra de sêmen (Lançamentos > Compra/Venda > Comprar sêmen) —
efeito financeiro + soma de doses ao estoque de sêmen (existente ou novo, via NAAB)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import CompraSemen, ContaGerencial, EstoqueSemen, Touro


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


def _criar_estoque_semen(engine, **kwargs) -> int:
    with Session(engine) as s:
        item = EstoqueSemen(touro_nome="Touro da Fazenda", doses=10, tipo="convencional", **kwargs)
        s.add(item)
        s.commit()
        s.refresh(item)
        return item.id


def _criar_touro_naab(engine, naab="7HO12345", nome="Supersire") -> None:
    with Session(engine) as s:
        s.add(Touro(naab=naab, nome=nome, central="ABS"))
        s.commit()


class TestRegistrarCompraSemen:
    def test_compra_de_touro_ja_em_estoque_soma_doses(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        r = client.post("/compras-semen/", json={
            "origem": "estoque", "estoque_semen_id": estoque_id,
            "vendedor": "Central Genética", "valor": 50.0, "tipo_valor": "por_dose", "doses": 20,
            "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["doses_compradas"] == 20
        assert corpo["estoque_semen_id"] == estoque_id

        with Session(client.engine) as s:
            estoque = s.get(EstoqueSemen, estoque_id)
            assert estoque.doses == 30  # 10 iniciais + 20 compradas
            assert estoque.valor_unitario == 50.0

            conta = s.exec(select(ContaGerencial).where(ContaGerencial.codigo_conta == "3.01.02.01")).first()
            assert conta is not None
            assert conta.tipo == "despesa"
            assert conta.valor_total == 1000.0  # 20 x 50

            registro = s.exec(select(CompraSemen)).first()
            assert registro.origem == "estoque"
            assert registro.doses == 20
            assert registro.estoque_semen_id == estoque_id

    def test_compra_valor_total_calcula_valor_por_dose(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        client.post("/compras-semen/", json={
            "origem": "estoque", "estoque_semen_id": estoque_id,
            "vendedor": "Central Genética", "valor": 900.0, "tipo_valor": "total", "doses": 18,
            "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        with Session(client.engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.codigo_conta == "3.01.02.01")).first()
            assert conta.valor_unitario == 50.0
            assert conta.valor_total == 900.0

    def test_compra_de_touro_naab_novo_cria_linha_de_estoque(self, client):
        _criar_touro_naab(client.engine)
        r = client.post("/compras-semen/", json={
            "origem": "naab", "naab": "7HO12345", "touro_nome": "Supersire",
            "vendedor": "ABS Brasil", "valor": 80.0, "tipo_valor": "por_dose", "doses": 10,
            "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 200
        with Session(client.engine) as s:
            estoque = s.exec(select(EstoqueSemen).where(EstoqueSemen.naab == "7HO12345")).first()
            assert estoque is not None
            assert estoque.doses == 10
            assert estoque.touro_nome == "Supersire"
            assert estoque.central == "ABS"

    def test_compra_de_touro_naab_ja_no_estoque_soma_doses_sem_duplicar(self, client):
        _criar_touro_naab(client.engine)
        estoque_id = _criar_estoque_semen(client.engine, naab="7HO12345")
        client.post("/compras-semen/", json={
            "origem": "naab", "naab": "7HO12345", "touro_nome": "Supersire",
            "vendedor": "ABS Brasil", "valor": 80.0, "tipo_valor": "por_dose", "doses": 10,
            "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        with Session(client.engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.naab == "7HO12345")).all()
            assert len(linhas) == 1
            assert linhas[0].id == estoque_id
            assert linhas[0].doses == 20

    def test_compra_exige_conta_gerencial_de_semen(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        r = client.post("/compras-semen/", json={
            "origem": "estoque", "estoque_semen_id": estoque_id,
            "vendedor": "Central Genética", "valor": 50.0, "tipo_valor": "por_dose", "doses": 10,
            "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.10.06",
        })
        assert r.status_code == 400

    def test_compra_naab_inexistente_da_404(self, client):
        r = client.post("/compras-semen/", json={
            "origem": "naab", "naab": "NAOEXISTE", "touro_nome": "Fantasma",
            "vendedor": "ABS Brasil", "valor": 80.0, "tipo_valor": "por_dose", "doses": 10,
            "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 404

    def test_compra_exige_doses_positivas(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        r = client.post("/compras-semen/", json={
            "origem": "estoque", "estoque_semen_id": estoque_id,
            "vendedor": "Central Genética", "valor": 50.0, "tipo_valor": "por_dose", "doses": 0,
            "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 400

    def test_lista_compras_registradas(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        client.post("/compras-semen/", json={
            "origem": "estoque", "estoque_semen_id": estoque_id,
            "vendedor": "Central Genética", "valor": 50.0, "tipo_valor": "por_dose", "doses": 10,
            "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        r = client.get("/compras-semen/")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["doses"] == 10
