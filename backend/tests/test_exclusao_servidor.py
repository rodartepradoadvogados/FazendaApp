"""Fase 1 do "Excluir lançamentos" — validação no servidor, trilha e pedidos.

Cobre o que é NOVO nesta fase e não existia nos testes antigos: motivo/confirmação
exigidos no servidor (422), bloqueio respondendo 409, trilha `exclusao_registro`
(com código EX-AAAA-NNNN), deduplicação de pedidos (ja_pedido/apoio) e rejeição
com motivo obrigatório.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, ExclusaoRegistro, Fazenda, SolicitacaoExclusao, Usuario
from fazenda.models.planos import MODULOS_COMERCIAIS


class _U:
    def __init__(self, id, username, papel):
        self.id = id
        self.username = username
        self.papel = papel
        self.ativo = True
        self.permissoes = ""


ADMIN = _U(1, "admin", "admin")
OPERADOR = _U(2, "operador", "operador")


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Usuario(id=1, username="admin", papel="admin", senha_hash="x", ativo=True))
        s.add(Usuario(id=2, username="operador", papel="operador", senha_hash="x", ativo=True))
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
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    holder = {"user": ADMIN}

    def _get_current_user():
        return holder["user"]

    main.app.dependency_overrides[get_current_user] = _get_current_user

    with TestClient(main.app) as c:
        yield c, engine, holder

    main.app.dependency_overrides.clear()


def _criar_animal(engine):
    with Session(engine) as s:
        s.add(Animal(numero="100", nome="Vaca", fazenda_id=1))
        s.commit()


class TestExigenciaMotivoConfirmacao:
    def test_admin_animal_alto_sem_motivo_422(self, client):
        c, engine, _ = client
        _criar_animal(engine)
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100"})
        assert r.status_code == 422
        assert r.json()["detail"]["codigo"] == "motivo_obrigatorio"

    def test_admin_animal_com_motivo_mas_confirmacao_faltando_422(self, client):
        c, engine, _ = client
        _criar_animal(engine)
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100", "motivo": "erro"})
        assert r.status_code == 422
        assert r.json()["detail"]["codigo"] == "confirmacao_invalida"

    def test_admin_animal_confirmacao_errada_422(self, client):
        c, engine, _ = client
        _criar_animal(engine)
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100", "motivo": "erro", "confirmacao": "999"})
        assert r.status_code == 422

    def test_admin_animal_correta_200_escreve_trilha(self, client):
        c, engine, _ = client
        _criar_animal(engine)
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100", "motivo": "erro de cadastro", "confirmacao": "100"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "excluido"
        comprovante = r.json()["comprovante"]
        assert comprovante.startswith("EX-"), comprovante

        with Session(engine) as s:
            reg = s.exec(select(ExclusaoRegistro)).first()
            assert reg is not None
            assert reg.codigo == comprovante
            assert reg.acao == "apagou"
            assert reg.snapshot_json is not None and "cpf" not in reg.snapshot_json.lower()


class TestOperadorPedidoDedup:
    def test_operador_sem_motivo_422(self, client):
        c, engine, holder = client
        _criar_animal(engine)
        holder["user"] = OPERADOR
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100"})
        assert r.status_code == 422
        holder["user"] = ADMIN

    def test_operador_requisita_e_repetindo_volta_ja_pedido(self, client):
        c, engine, holder = client
        _criar_animal(engine)
        holder["user"] = OPERADOR
        r1 = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100", "motivo": "erro"})
        assert r1.status_code == 200
        assert r1.json()["status"] == "solicitado"
        r2 = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100", "motivo": "erro"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "ja_pedido"
        assert r2.json()["id"] == r1.json()["id"]
        holder["user"] = ADMIN


class TestRejeitarMotivoObrigatorio:
    def test_rejeitar_sem_motivo_422(self, client):
        c, engine, holder = client
        _criar_animal(engine)
        holder["user"] = OPERADOR
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100", "motivo": "erro"})
        sol_id = r.json()["id"]
        holder["user"] = ADMIN
        rj = c.post(f"/exclusoes/pendentes/{sol_id}/rejeitar", json={})
        assert rj.status_code == 422
        assert rj.json()["detail"]["codigo"] == "motivo_rejeicao_obrigatorio"


class TestTrilhaEEndpoints:
    def test_trilha_e_comprovante(self, client):
        c, engine, _ = client
        _criar_animal(engine)
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "100", "motivo": "erro", "confirmacao": "100"})
        comprovante = r.json()["comprovante"]

        tr = c.get("/exclusoes/trilha")
        assert tr.status_code == 200
        assert any(x["codigo"] == comprovante for x in tr.json())

        cp = c.get(f"/exclusoes/comprovante/{comprovante}")
        assert cp.status_code == 200
        assert cp.json()["codigo"] == comprovante