"""
Relatório de compra de sêmen (Lançamentos > Compra/Venda > Relatório de
compra de sêmen) — espelho dos testes de relatorio_compra_venda_animal.py:
consulta CompraSemen enriquecida com a nota fiscal/centro de custo/conta
gerencial da ContaGerencial vinculada, filtrável por período, documento,
touro e vendedor — e, principalmente, isolada por fazenda (o relatório de
animais já teve esse vazamento e foi corrigido; este nasce já corrigido).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda A"))
        s.add(Fazenda(id=2, nome="Fazenda B"))
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


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _criar_estoque_semen(engine, fazenda_id: int, **kwargs) -> int:
    from fazenda.models import EstoqueSemen
    with Session(engine) as s:
        campos = dict(touro_nome="Touro Fazenda", doses=10, tipo="convencional", fazenda_id=fazenda_id)
        campos.update(kwargs)
        item = EstoqueSemen(**campos)
        s.add(item)
        s.commit()
        s.refresh(item)
        return item.id


def _comprar_semen(c, estoque_id: int, **overrides) -> dict:
    payload = {
        "itens": [{"origem": "estoque", "estoque_semen_id": estoque_id, "valor": 50.0, "tipo_valor": "por_dose", "doses": 20}],
        "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        "numero_documento": "NF-1001",
    }
    payload.update(overrides)
    r = c.post("/compras-semen/", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


class TestRelatorioCompraSemen:
    def test_lista_compra_com_nota_fiscal_e_centro_de_custo(self, client):
        _como_fazenda(1)
        estoque_id = _criar_estoque_semen(client.engine, fazenda_id=1)
        _comprar_semen(client, estoque_id)

        r = client.get("/relatorio-compra-semen/")
        assert r.status_code == 200
        linhas = r.json()
        assert len(linhas) == 1
        linha = linhas[0]
        assert linha["touro_nome"] == "Touro Fazenda"
        assert linha["doses"] == 20
        assert linha["valor_unitario"] == 50.0
        assert linha["valor_total"] == 1000.0
        assert linha["numero_documento"] == "NF-1001"
        assert linha["centro_custo"] == "Pecuária Leiteira"
        assert linha["codigo_conta"] == "3.01.02.01"
        assert linha["vendedor"] == "Central Genética"

    def test_filtro_por_touro(self, client):
        _como_fazenda(1)
        estoque_id_1 = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Coors")
        estoque_id_2 = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Titan")
        _comprar_semen(client, estoque_id_1)
        _comprar_semen(client, estoque_id_2)

        r = client.get("/relatorio-compra-semen/", params={"touro": "coors"})
        assert r.status_code == 200
        linhas = r.json()
        assert len(linhas) == 1
        assert linhas[0]["touro_nome"] == "Coors"

    def test_filtro_por_vendedor(self, client):
        _como_fazenda(1)
        estoque_id_1 = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Coors")
        estoque_id_2 = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Titan")
        _comprar_semen(client, estoque_id_1, vendedor="ABS Brasil")
        _comprar_semen(client, estoque_id_2, vendedor="Central Genética")

        r = client.get("/relatorio-compra-semen/", params={"vendedor": "abs"})
        assert r.status_code == 200
        linhas = r.json()
        assert len(linhas) == 1
        assert linhas[0]["vendedor"] == "ABS Brasil"

    def test_filtro_por_numero_documento(self, client):
        _como_fazenda(1)
        estoque_id_1 = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Coors")
        estoque_id_2 = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Titan")
        _comprar_semen(client, estoque_id_1, numero_documento="NF-2001")
        _comprar_semen(client, estoque_id_2, numero_documento="NF-2002")

        r = client.get("/relatorio-compra-semen/", params={"numero_documento": "NF-2002"})
        assert r.status_code == 200
        linhas = r.json()
        assert len(linhas) == 1
        assert linhas[0]["touro_nome"] == "Titan"

    def test_filtro_por_periodo(self, client):
        _como_fazenda(1)
        estoque_id_1 = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Coors")
        estoque_id_2 = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Titan")
        _comprar_semen(client, estoque_id_1, data_compra="2026-01-05")
        _comprar_semen(client, estoque_id_2, data_compra="2026-07-10")

        r = client.get("/relatorio-compra-semen/", params={"data_de": "2026-06-01", "data_ate": "2026-08-01"})
        assert r.status_code == 200
        linhas = r.json()
        assert len(linhas) == 1
        assert linhas[0]["touro_nome"] == "Titan"


class TestIsolamentoRelatorioCompraSemen:
    def test_fazenda_b_nao_ve_compra_de_semen_da_fazenda_a(self, client):
        _como_fazenda(1)
        estoque_id_a = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Touro A")
        _comprar_semen(client, estoque_id_a)

        _como_fazenda(2)
        r = client.get("/relatorio-compra-semen/")
        assert r.status_code == 200
        assert r.json() == []

    def test_fazenda_a_continua_vendo_sua_propria_compra(self, client):
        _como_fazenda(1)
        estoque_id_a = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Touro A")
        _comprar_semen(client, estoque_id_a)

        r = client.get("/relatorio-compra-semen/")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["touro_nome"] == "Touro A"

    def test_numero_documento_de_outra_fazenda_nao_vaza_a_conta_gerencial(self, client):
        """Mesmo bug corrigido no relatório de animais: casar
        `numero_lancamento_gerado` sem filtrar `ContaGerencial` por fazenda
        poderia expor nota fiscal/centro de custo de uma compra de sêmen de
        OUTRA fazenda, caso os números de lançamento colidissem entre
        fazendas distintas (contadores independentes)."""
        _como_fazenda(1)
        estoque_id_a = _criar_estoque_semen(client.engine, fazenda_id=1, touro_nome="Touro A")
        _comprar_semen(client, estoque_id_a, numero_documento="NF-SIGILOSA-A")

        _como_fazenda(2)
        estoque_id_b = _criar_estoque_semen(client.engine, fazenda_id=2, touro_nome="Touro B")
        _comprar_semen(client, estoque_id_b, numero_documento="NF-B")

        r = client.get("/relatorio-compra-semen/")
        assert r.status_code == 200
        linhas = r.json()
        assert len(linhas) == 1
        assert linhas[0]["numero_documento"] == "NF-B"
        assert "NF-SIGILOSA-A" not in [l["numero_documento"] for l in linhas]
