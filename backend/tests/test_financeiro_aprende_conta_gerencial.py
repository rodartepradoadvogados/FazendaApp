"""
Item de estoque sem conta gerencial padrão: a conta escolhida no PRIMEIRO
lançamento daquele produto vira o padrão dele — do próximo lançamento em
diante, o formulário já pré-preenche essa conta sozinho (ver
FormFinanceiro.tsx::contaGerencialPadrao e
financeiro.py::_aprender_conta_gerencial_padrao).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.add(Estoque(nome="Sal mineral", quantidade=100, unidade="kg", fazenda_id=1))
        s.add(Estoque(nome="Sal mineral", quantidade=50, unidade="kg", fazenda_id=2))
        s.add(Estoque(nome="Ração premium", quantidade=10, unidade="kg", fazenda_id=1,
                       conta_gerencial_despesa_padrao="3.01.01.99"))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _lancar(c, **overrides):
    payload = {
        "tipo": "despesa",
        "itens": [{"produto": "Sal mineral", "tipo_item": "produto", "codigo_conta_gerencial": "3.01.01.05", "valor_total": 500.0}],
        "data_emissao": "2026-07-31",
    }
    payload.update(overrides)
    return c.post("/financeiro/lancamentos", json=payload)


class TestAprendeContaGerencialPadrao:
    def test_primeira_ocorrencia_grava_o_padrao(self, client):
        c, engine = client
        r = _lancar(c)
        assert r.status_code == 201, r.text
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sal mineral", Estoque.fazenda_id == 1)).first()
            assert item.conta_gerencial_despesa_padrao == "3.01.01.05"

    def test_segunda_ocorrencia_nao_sobrescreve_o_padrao_ja_aprendido(self, client):
        c, engine = client
        _lancar(c)
        _lancar(c, itens=[{"produto": "Sal mineral", "tipo_item": "produto", "codigo_conta_gerencial": "3.01.01.09", "valor_total": 200.0}])
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sal mineral", Estoque.fazenda_id == 1)).first()
            assert item.conta_gerencial_despesa_padrao == "3.01.01.05", "não pode trocar um padrão já aprendido"

    def test_nao_sobrescreve_padrao_ja_cadastrado_manualmente(self, client):
        c, engine = client
        _lancar(c, itens=[{"produto": "Ração premium", "tipo_item": "produto", "codigo_conta_gerencial": "3.01.01.05", "valor_total": 300.0}])
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração premium", Estoque.fazenda_id == 1)).first()
            assert item.conta_gerencial_despesa_padrao == "3.01.01.99", "não pode sobrescrever o padrão cadastrado manualmente"

    def test_item_de_servico_nao_aprende_padrao(self, client):
        c, engine = client
        _lancar(c, itens=[{"produto": "Consultoria veterinária", "tipo_item": "servico", "codigo_conta_gerencial": "3.02.01.01", "valor_total": 300.0}])
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Consultoria veterinária")).first()
            assert item is None, "serviço não é item de estoque — não deveria criar/alterar nenhum"

    def test_sem_codigo_conta_gerencial_nao_aprende_nada(self, client):
        c, engine = client
        _lancar(c, itens=[{"produto": "Sal mineral", "tipo_item": "produto", "valor_total": 500.0}])
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sal mineral", Estoque.fazenda_id == 1)).first()
            assert item.conta_gerencial_despesa_padrao is None

    def test_receita_grava_no_campo_de_receita_nao_no_de_despesa(self, client):
        c, engine = client
        r = _lancar(c, tipo="receita", itens=[{"produto": "Sal mineral", "tipo_item": "produto", "codigo_conta_gerencial": "4.01.01.01", "valor_total": 500.0}])
        assert r.status_code == 201, r.text
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sal mineral", Estoque.fazenda_id == 1)).first()
            assert item.conta_gerencial_receita_padrao == "4.01.01.01"
            assert item.conta_gerencial_despesa_padrao is None

    def test_isolamento_por_fazenda(self, client):
        """Aprender o padrão numa fazenda não pode vazar pra outra fazenda
        que tem um item de estoque com o mesmo nome."""
        c, engine = client
        _lancar(c)
        with Session(engine) as s:
            item_f2 = s.exec(select(Estoque).where(Estoque.nome == "Sal mineral", Estoque.fazenda_id == 2)).first()
            assert item_f2.conta_gerencial_despesa_padrao is None
