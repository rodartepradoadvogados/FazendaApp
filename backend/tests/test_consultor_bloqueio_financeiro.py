"""
Consultor (vínculo externo, ver UsuarioFazenda.consultor) tem o mesmo acesso
de um funcionário comum dentro da fazenda, mas fica de fora de pontos
sensíveis específicos — hoje só o link para o banco de dados externo
(Supabase) em Relatórios financeiros — ver fazenda.auth.exigir_nao_consultor.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import hash_senha
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, Usuario, UsuarioFazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


class _FakeUser:
    id = 42
    papel = "operador"
    ativo = True
    username = "consultor.teste"
    email = "consultor@example.com"
    permissoes = "financeiro"
    senha_hash = hash_senha("senha-do-consultor-123")


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(Usuario(
            id=42, username=_FakeUser.username, senha_hash=_FakeUser.senha_hash, papel="operador",
            ativo=True, permissoes="financeiro",
        ))
        s.add(UsuarioFazenda(usuario_id=42, fazenda_id=1, consultor=True))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


def test_consultor_e_bloqueado_do_link_supabase(client):
    r = client.get("/financeiro/supabase-dashboard-url")
    assert r.status_code == 403


def test_consultor_continua_lendo_financeiro_normalmente(client):
    r = client.get("/financeiro/opcoes")
    assert r.status_code == 200
