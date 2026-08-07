"""
G8 — DELETE /cadastro/protocolos-inducao-lactacao/{protocolo_id}: cópia
estrutural de excluir_protocolo_sanitario/excluir_protocolo_iatf_cadastrado
(mesmo router). Bloqueia com 409 se já houve lançamento; 404 se inexistente
ou de outra fazenda.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda,
    ProtocoloInducaoLactacao,
    ProtocoloInducaoLactacaoEtapa,
    ProtocoloInducaoLancamento,
)


@pytest.fixture
def client():
    """Sem Authorization header — get_fazenda_atual_id() devolve None, o que
    também dispensa ContratoFazenda (exigir_contrato_ativo/exigir_modulo só
    checam contrato quando fazenda_id não é None) — mesmo padrão de
    tests/test_exclusoes.py."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


@pytest.fixture
def client_fazenda():
    """Com get_fazenda_atual_id fixado em 1 (fazenda real) — para o teste de
    isolamento entre fazendas. Precisa de ContratoFazenda ativo (a rota passa
    por cadastro.router, que exige módulo "parametros" + contrato ativo)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _criar_protocolo(engine, *, fazenda_id=None, nome="Indução teste"):
    with Session(engine) as s:
        p = ProtocoloInducaoLactacao(nome=nome, dia_inicial=0, ativo=True, fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        s.add(ProtocoloInducaoLactacaoEtapa(protocolo_id=p.id, dia=0, tipo="manejo", produto="Adaptação"))
        s.add(ProtocoloInducaoLactacaoEtapa(protocolo_id=p.id, dia=1, tipo="manejo", produto="Ordenha"))
        s.commit()
        return p.id


class TestExcluirProtocoloInducao:
    def test_exclui_protocolo_sem_lancamento(self, client):
        c, engine = client
        pid = _criar_protocolo(engine)

        r = c.delete(f"/cadastro/protocolos-inducao-lactacao/{pid}")
        assert r.status_code == 200
        assert r.json() == {"excluido": True}

        with Session(engine) as s:
            assert s.get(ProtocoloInducaoLactacao, pid) is None
            etapas = s.exec(
                select(ProtocoloInducaoLactacaoEtapa).where(ProtocoloInducaoLactacaoEtapa.protocolo_id == pid)
            ).all()
            assert etapas == []

    def test_bloqueia_com_lancamento_existente(self, client):
        c, engine = client
        pid = _criar_protocolo(engine, nome="Indução já lançada")
        with Session(engine) as s:
            s.add(ProtocoloInducaoLancamento(
                protocolo_id=pid, nome_protocolo="Indução já lançada - lote 1", data_d0=date(2026, 1, 1),
            ))
            s.commit()

        r = c.delete(f"/cadastro/protocolos-inducao-lactacao/{pid}")
        assert r.status_code == 409
        assert "desative" in r.json()["detail"].lower()

        # Protocolo continua existindo — o bloqueio não apagou nada.
        with Session(engine) as s:
            assert s.get(ProtocoloInducaoLactacao, pid) is not None

    def test_protocolo_inexistente_da_404(self, client):
        c, _ = client
        r = c.delete("/cadastro/protocolos-inducao-lactacao/999999")
        assert r.status_code == 404

    def test_isolamento_entre_fazendas(self, client_fazenda):
        c, engine = client_fazenda
        # Protocolo de OUTRA fazenda (2) — a fazenda atual do request é 1.
        pid_outra = _criar_protocolo(engine, fazenda_id=2, nome="Indução da fazenda 2")

        r = c.delete(f"/cadastro/protocolos-inducao-lactacao/{pid_outra}")
        assert r.status_code == 404

        with Session(engine) as s:
            assert s.get(ProtocoloInducaoLactacao, pid_outra) is not None
