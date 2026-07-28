"""
Fase 2B — vínculo de consultor externo (veterinário, contador, agrônomo) a
uma fazenda no plano Diamond: mesmo acesso de um funcionário comum dentro
dela (não administra a fazenda), mas o vínculo só é aceito se a fazenda
tiver o módulo comercial "consultor" contratado e ativo.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, Usuario, UsuarioFazenda
from fazenda.models.planos import MODULOS_COMERCIAIS

EMAIL_DONO = "jairodarte@gmail.com"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Diamond"))
        s.add(Fazenda(id=2, nome="Fazenda Standard"))
        s.commit()
        # Fazenda #1: plano Diamond (todos os módulos, incluindo "consultor").
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        # Fazenda #2: plano Standard (sem "consultor").
        s.add(ContratoFazenda(fazenda_id=2, status="ativo"))
        s.add(ContratoFazendaModulo(fazenda_id=2, modulo="rebanho", preco=150.0, ativo=True))
        s.add(ContratoFazendaModulo(fazenda_id=2, modulo="reprodutivo", preco=0.0, ativo=True))
        # Usuário que será convidado como consultor.
        s.add(Usuario(username="vet_externo", senha_hash="x", papel="operador", permissoes="reproducao,sanidade"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin_comum"
        email = "admin_comum@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _como_dono():
    import main
    from fazenda.auth import get_current_user

    class _FakeDono:
        id = 1
        papel = "admin"
        ativo = True
        username = "dono"
        email = EMAIL_DONO
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeDono()


class TestVinculoConsultor:
    def test_vincula_consultor_em_fazenda_diamond(self, client):
        c, engine = client
        _como_dono()
        _como_fazenda(1)
        r = c.post("/fazendas/1/vincular-usuario", json={"username": "vet_externo", "consultor": True})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            v = s.exec(select(UsuarioFazenda).where(UsuarioFazenda.fazenda_id == 1)).first()
            assert v.consultor is True
            assert v.contratante is False

    def test_rejeita_consultor_em_fazenda_sem_modulo_consultor(self, client):
        c, engine = client
        _como_dono()
        _como_fazenda(2)
        r = c.post("/fazendas/2/vincular-usuario", json={"username": "vet_externo", "consultor": True})
        assert r.status_code == 403
        assert "Diamond" in r.json()["detail"]

    def test_contratante_e_consultor_sao_mutuamente_exclusivos(self, client):
        c, engine = client
        _como_dono()
        _como_fazenda(1)
        r = c.post("/fazendas/1/vincular-usuario", json={"username": "vet_externo", "consultor": True, "contratante": True})
        assert r.status_code == 400

    def test_vincula_por_username_sem_saber_o_id(self, client):
        c, engine = client
        _como_dono()
        _como_fazenda(1)
        r = c.post("/fazendas/1/vincular-usuario", json={"username": "vet_externo"})
        assert r.status_code == 200, r.text
        assert r.json()["username"] == "vet_externo"

    def test_listar_usuarios_vinculados_traz_flags(self, client):
        c, engine = client
        _como_dono()
        _como_fazenda(1)
        c.post("/fazendas/1/vincular-usuario", json={"username": "vet_externo", "consultor": True})
        r = c.get("/fazendas/1/usuarios")
        assert r.status_code == 200
        assert r.json() == [{"usuario_id": 1, "username": "vet_externo", "nome": None, "contratante": False, "consultor": True, "contador": False}]

    def test_desvincula_consultor(self, client):
        c, engine = client
        _como_dono()
        _como_fazenda(1)
        c.post("/fazendas/1/vincular-usuario", json={"username": "vet_externo", "consultor": True})
        r = c.delete("/fazendas/1/vincular-usuario/1")
        assert r.status_code == 200
        assert c.get("/fazendas/1/usuarios").json() == []
