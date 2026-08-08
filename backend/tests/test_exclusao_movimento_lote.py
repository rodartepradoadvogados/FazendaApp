"""
Testes do tipo `movimento_lote` do motor genérico de exclusões (G4 — fechamento
dos 17 gaps de editar/excluir). Cobre: exclusão reverte o lote do animal SÓ
quando é o movimento mais recente daquele animal; isolamento por fazenda;
fluxo de aprovação (operador solicita, admin aprova executa de fato).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal,
    ContratoFazenda,
    ContratoFazendaModulo,
    Fazenda,
    MovimentoLote,
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


class TestExclusaoMovimentoLoteFunciona:
    def test_excluir_ultimo_movimento_reverte_lote_do_animal(self, client):
        c, engine = client
        _como_fazenda(1)
        with _sessao(engine) as s:
            s.add(Animal(numero="9001", sexo="F", ativo=True, fazenda_id=1, grupo_primario="LOTE-B - Novilhas"))
            s.add(MovimentoLote(
                numero_matriz="9001", lote_origem="LOTE-A - Bezerras", lote_destino="LOTE-B - Novilhas",
                data_movimento=date(2026, 1, 10), motivo="Crescimento", fazenda_id=1, origem="manual",
            ))
            s.commit()
            mov_id = s.exec(select(MovimentoLote)).first().id

        r = c.post("/exclusoes/impacto", json={"tipo": "movimento_lote", "id": str(mov_id)})
        assert r.status_code == 200
        impacto = r.json()["impacto"]
        assert any("volta para o lote LOTE-A - Bezerras" in i for i in impacto)

        # A prévia (impacto) não altera nada.
        with _sessao(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "9001")).first()
            assert animal.grupo_primario == "LOTE-B - Novilhas"

        r = c.post("/exclusoes/confirmar", json={"tipo": "movimento_lote", "id": str(mov_id)})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "9001")).first()
            assert animal.grupo_primario == "LOTE-A - Bezerras"
            assert animal.grupo_raw == "LOTE-A - Bezerras"
            assert animal.grupo_manual is True
            assert s.exec(select(MovimentoLote)).all() == []

    def test_excluir_movimento_com_posterior_nao_altera_lote(self, client):
        c, engine = client
        _como_fazenda(1)
        with _sessao(engine) as s:
            s.add(Animal(numero="9002", sexo="F", ativo=True, fazenda_id=1, grupo_primario="LOTE-C - Vacas"))
            mov_antigo = MovimentoLote(
                numero_matriz="9002", lote_origem="LOTE-A - Bezerras", lote_destino="LOTE-B - Novilhas",
                data_movimento=date(2026, 1, 1), motivo="Crescimento", fazenda_id=1, origem="manual",
            )
            mov_recente = MovimentoLote(
                numero_matriz="9002", lote_origem="LOTE-B - Novilhas", lote_destino="LOTE-C - Vacas",
                data_movimento=date(2026, 2, 1), motivo="Pós-parto", fazenda_id=1, origem="manual",
            )
            s.add(mov_antigo)
            s.add(mov_recente)
            s.commit()
            s.refresh(mov_antigo)
            mov_antigo_id = mov_antigo.id

        r = c.post("/exclusoes/impacto", json={"tipo": "movimento_lote", "id": str(mov_antigo_id)})
        assert r.status_code == 200
        impacto = r.json()["impacto"]
        assert any("posterior" in i and "NÃO será alterado" in i for i in impacto)

        r = c.post("/exclusoes/confirmar", json={"tipo": "movimento_lote", "id": str(mov_antigo_id)})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "9002")).first()
            # Lote atual não foi tocado — segue o de destino do movimento mais recente.
            assert animal.grupo_primario == "LOTE-C - Vacas"
            # Só o movimento antigo foi apagado, o mais recente continua no histórico.
            restantes = s.exec(select(MovimentoLote)).all()
            assert len(restantes) == 1
            assert restantes[0].lote_destino == "LOTE-C - Vacas"

    def test_excluir_movimento_sem_lote_origem_nao_zera_lote_do_animal(self, client):
        c, engine = client
        _como_fazenda(1)
        with _sessao(engine) as s:
            s.add(Animal(numero="9003", sexo="F", ativo=True, fazenda_id=1, grupo_primario="LOTE-A - Bezerras"))
            s.add(MovimentoLote(
                numero_matriz="9003", lote_origem=None, lote_destino="LOTE-A - Bezerras",
                data_movimento=date(2026, 1, 5), motivo="Nascimento", fazenda_id=1, origem="manual",
            ))
            s.commit()
            mov_id = s.exec(select(MovimentoLote)).first().id

        r = c.post("/exclusoes/impacto", json={"tipo": "movimento_lote", "id": str(mov_id)})
        assert r.status_code == 200
        assert any("não tinha lote registrado" in i for i in r.json()["impacto"])

        r = c.post("/exclusoes/confirmar", json={"tipo": "movimento_lote", "id": str(mov_id)})
        assert r.status_code == 200

        with _sessao(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "9003")).first()
            # Lote não foi zerado/alterado.
            assert animal.grupo_primario == "LOTE-A - Bezerras"


class TestExclusaoMovimentoLoteIsolamento:
    def test_isolamento_por_fazenda_busca_e_impacto(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Animal(numero="9004", sexo="F", ativo=True, fazenda_id=1, grupo_primario="LOTE-B"))
            s.add(Animal(numero="9005", sexo="F", ativo=True, fazenda_id=2, grupo_primario="LOTE-B"))
            mov1 = MovimentoLote(
                numero_matriz="9004", lote_origem="LOTE-A", lote_destino="LOTE-B",
                data_movimento=date(2026, 1, 1), fazenda_id=1, origem="manual",
            )
            mov2 = MovimentoLote(
                numero_matriz="9005", lote_origem="LOTE-A", lote_destino="LOTE-B",
                data_movimento=date(2026, 1, 1), fazenda_id=2, origem="manual",
            )
            s.add(mov1)
            s.add(mov2)
            s.commit()
            s.refresh(mov1)
            mov1_id = mov1.id

        _como_fazenda(2)
        r = c.get("/exclusoes/buscar", params={"tipo": "movimento_lote", "termo": ""})
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert mov1_id not in ids

        r = c.post("/exclusoes/impacto", json={"tipo": "movimento_lote", "id": str(mov1_id)})
        assert r.status_code == 404


class TestExclusaoMovimentoLoteAprovacao:
    def test_operador_solicita_e_admin_aprova_executa_reversao(self, client):
        c, engine = client
        _como_fazenda(1)
        with _sessao(engine) as s:
            s.add(Animal(numero="9006", sexo="F", ativo=True, fazenda_id=1, grupo_primario="LOTE-B"))
            s.add(MovimentoLote(
                numero_matriz="9006", lote_origem="LOTE-A", lote_destino="LOTE-B",
                data_movimento=date(2026, 1, 1), fazenda_id=1, origem="manual",
            ))
            s.commit()
            mov_id = s.exec(select(MovimentoLote)).first().id

        _como_operador()
        r = c.post("/exclusoes/confirmar", json={"tipo": "movimento_lote", "id": str(mov_id)})
        assert r.status_code == 200
        assert r.json()["status"] == "solicitado"

        with _sessao(engine) as s:
            sol = s.exec(select(SolicitacaoExclusao).where(SolicitacaoExclusao.tipo == "movimento_lote")).first()
            assert sol is not None
            sol_id = sol.id
            # `confirmar()` (exclusoes.py) chama `_alvos` ANTES de checar o
            # papel do usuário — o efeito colateral de `_alvos_movimento_lote`
            # (mudar o lote do animal) já é commitado mesmo na solicitação de
            # um operador; só o DELETE do MovimentoLote em si fica pendente de
            # aprovação. Mesmo comportamento (não específico deste tipo) que
            # os demais tipos com efeito colateral em `_alvos` (compra_semen,
            # fornecedor, ...) já têm hoje — ver comentário em exclusoes.py.
            animal = s.exec(select(Animal).where(Animal.numero == "9006")).first()
            assert animal.grupo_primario == "LOTE-A"
            # O movimento em si ainda existe — só a solicitação foi criada.
            assert s.exec(select(MovimentoLote)).first() is not None

        _como_admin()
        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 200
        assert r.json()["aprovado"] is True

        with _sessao(engine) as s:
            # `_alvos` roda de novo na aprovação — é idempotente: o animal já
            # estava em LOTE-A, continua em LOTE-A.
            animal = s.exec(select(Animal).where(Animal.numero == "9006")).first()
            assert animal.grupo_primario == "LOTE-A"
            assert s.exec(select(MovimentoLote)).all() == []
