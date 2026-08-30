"""
Testes do tipo `secagem` do motor genérico de exclusões (G5 — fechamento dos
17 gaps de editar/excluir). Cobre: localização por heurística (matriz + data
+ atividade/observação, sem FK) da Sanidade/AplicacaoAgendada geradas por
`registrar_secagem`, o estorno de estoque "de graça" via `_ORIGENS_POR_CLASSE`,
e a correção do vazamento entre fazendas em `GET /reproducao/secagens`.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    AplicacaoAgendada,
    ContratoFazenda,
    ContratoFazendaModulo,
    Estoque,
    Fazenda,
    Lactacao,
    Sanidade,
    Secagem,
    SolicitacaoExclusao,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    from fazenda.auth import exigir_admin, get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin-teste"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _como_admin():
    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin-teste"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()


def _como_operador():
    import main
    from fazenda.auth import get_current_user

    class _FakeOperador:
        id = 2
        papel = "operador"
        ativo = True
        username = "operador-teste"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()


class TestExclusaoSecagemFunciona:
    def test_excluir_secagem_com_produto_devolve_estoque_e_remove_sanidade(self, client):
        c, engine = client
        _como_fazenda(1)
        with _sessao(engine) as s:
            s.add(Estoque(nome="Cefalexina LA", unidade="ml", quantidade=1000, fazenda_id=1))
            s.add(Lactacao(numero_matriz="9001", data_inicio=date(2020, 1, 1), fazenda_id=1))
            s.commit()

        r = c.post("/producao/secagem", json={
            "numero_matriz": "9001",
            "data_secagem": "2026-01-10",
            "motivo": "rotina",
            "aplicado": True,
            "produtos": [{"produto": "Cefalexina LA", "via": "Intramamária", "quantidade": 10, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        assert r.json()["criado"] is True

        with _sessao(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Cefalexina LA")).first()
            assert item.quantidade == 990
            secagem = s.exec(select(Secagem).where(Secagem.numero_matriz == "9001")).first()
            secagem_id = secagem.id
            assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "9001")).first() is not None

        r = c.post("/exclusoes/impacto", json={"tipo": "secagem", "id": str(secagem_id)})
        assert r.status_code == 200
        impacto = r.json()["impacto"]
        assert any("Secagem de 9001" in i for i in impacto)
        # Impacto lista os produtos nominalmente (não só a contagem).
        assert any("Cefalexina LA" in i for i in impacto)

        # A prévia não altera nada.
        with _sessao(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Cefalexina LA")).first()
            assert item.quantidade == 990

        r = c.post("/exclusoes/confirmar", json={"tipo": "secagem", "id": str(secagem_id)})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Cefalexina LA")).first()
            assert item.quantidade == 1000
            assert s.exec(select(Secagem).where(Secagem.numero_matriz == "9001")).first() is None
            assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "9001")).first() is None

        # Estorno não duplica: rodar a exclusão de novo não é possível (a
        # secagem já não existe) — regressão coberta pelo 404 abaixo.
        r = c.post("/exclusoes/impacto", json={"tipo": "secagem", "id": str(secagem_id)})
        assert r.status_code == 404

    def test_excluir_secagem_programada_remove_agendada_sem_mexer_em_estoque(self, client):
        c, engine = client
        _como_fazenda(1)
        with _sessao(engine) as s:
            s.add(Estoque(nome="Vacina Pré-parto X", unidade="dose", quantidade=50, fazenda_id=1))
            s.add(Lactacao(numero_matriz="9002", data_inicio=date(2020, 1, 1), fazenda_id=1))
            s.commit()

        data_futura = (date.today() + timedelta(days=5)).isoformat()
        r = c.post("/producao/secagem", json={
            "numero_matriz": "9002",
            "data_secagem": data_futura,
            "motivo": "rotina",
            "aplicado": True,
            "produtos": [{"produto": "Vacina Pré-parto X", "via": "Intramuscular", "quantidade": 1, "unidade": "dose"}],
        })
        assert r.status_code == 200, r.text
        assert r.json()["programado"] is True

        with _sessao(engine) as s:
            secagem = s.exec(select(Secagem).where(Secagem.numero_matriz == "9002")).first()
            secagem_id = secagem.id
            assert s.exec(select(AplicacaoAgendada).where(AplicacaoAgendada.numero_matriz == "9002")).first() is not None
            assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "9002")).first() is None

        r = c.post("/exclusoes/impacto", json={"tipo": "secagem", "id": str(secagem_id)})
        assert r.status_code == 200
        assert any("programada" in i for i in r.json()["impacto"])

        r = c.post("/exclusoes/confirmar", json={"tipo": "secagem", "id": str(secagem_id)})
        assert r.status_code == 200

        with _sessao(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Vacina Pré-parto X")).first()
            # Nunca baixou (era só programado) — não sofre nenhum estorno.
            assert item.quantidade == 50
            assert s.exec(select(AplicacaoAgendada).where(AplicacaoAgendada.numero_matriz == "9002")).first() is None
            assert s.exec(select(Secagem).where(Secagem.numero_matriz == "9002")).first() is None


class TestExclusaoSecagemIsolamento:
    def test_regressao_vazamento_entre_fazendas(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Secagem(numero_matriz="9003", data_secagem=date(2026, 1, 1), motivo="rotina", fazenda_id=1))
            s.add(Secagem(numero_matriz="9004", data_secagem=date(2026, 1, 1), motivo="rotina", fazenda_id=2))
            s.commit()
            secagem_f1_id = s.exec(select(Secagem).where(Secagem.numero_matriz == "9003")).first().id

        _como_fazenda(2)
        r = c.get("/reproducao/secagens")
        assert r.status_code == 200
        numeros = {reg["numero"] for reg in r.json()["secagens"]}
        assert "9003" not in numeros
        assert "9004" in numeros

        r = c.get("/exclusoes/buscar", params={"tipo": "secagem", "termo": ""})
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert secagem_f1_id not in ids

        r = c.post("/exclusoes/impacto", json={"tipo": "secagem", "id": str(secagem_f1_id)})
        assert r.status_code == 404

        _como_fazenda(1)
        r = c.get("/reproducao/secagens")
        numeros = {reg["numero"] for reg in r.json()["secagens"]}
        assert "9003" in numeros
        assert "9004" not in numeros


class TestExclusaoSecagemAprovacao:
    def test_operador_solicita_e_admin_aprova_executa_reversao_de_estoque(self, client):
        c, engine = client
        _como_fazenda(1)
        with _sessao(engine) as s:
            s.add(Estoque(nome="Cefalexina LA", unidade="ml", quantidade=1000, fazenda_id=1))
            s.add(Lactacao(numero_matriz="9005", data_inicio=date(2020, 1, 1), fazenda_id=1))
            s.commit()

        r = c.post("/producao/secagem", json={
            "numero_matriz": "9005",
            "data_secagem": "2026-01-10",
            "motivo": "rotina",
            "aplicado": True,
            "produtos": [{"produto": "Cefalexina LA", "via": "Intramamária", "quantidade": 10, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        with _sessao(engine) as s:
            secagem_id = s.exec(select(Secagem).where(Secagem.numero_matriz == "9005")).first().id

        _como_operador()
        r = c.post("/exclusoes/confirmar", json={"tipo": "secagem", "id": str(secagem_id)})
        assert r.status_code == 200
        assert r.json()["status"] == "solicitado"

        with _sessao(engine) as s:
            sol = s.exec(select(SolicitacaoExclusao).where(SolicitacaoExclusao.tipo == "secagem")).first()
            sol_id = sol.id
            item = s.exec(select(Estoque).where(Estoque.nome == "Cefalexina LA")).first()
            assert item.quantidade == 990  # ainda não estornado

        _como_admin()
        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 200
        assert r.json()["aprovado"] is True

        with _sessao(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Cefalexina LA")).first()
            assert item.quantidade == 1000
            assert s.exec(select(Secagem).where(Secagem.numero_matriz == "9005")).first() is None
