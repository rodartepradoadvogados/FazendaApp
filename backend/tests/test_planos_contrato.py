"""
Fase 2A — planos comerciais + contrato por fazenda: garante que nada (nem
Rebanho) libera antes da aprovação/fechamento do contrato, que cada módulo
comercial só libera o que foi contratado, que só o dono gerencia o contrato,
e que a fazenda #1 (grandfathered) nunca fica bloqueada por esta trava nova.
"""
from __future__ import annotations

import io
import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS

EMAIL_DONO = "jairodarte@gmail.com"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Nova"))
        s.commit()
        # Fazenda #1 — grandfathered, exatamente como o backfill da migração faz.
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        # Fazenda #2 — recém-criada, como provisionar_fazenda_nova deixa (sem módulo nenhum).
        s.add(ContratoFazenda(fazenda_id=2, status="aguardando_aprovacao"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
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


class TestTravaDeContrato:
    def test_fazenda_pendente_bloqueia_modulo_ja_de_rebanho(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.get("/reproducao/servicos")
        assert r.status_code == 403

    def test_fazenda_1_grandfathered_acessa_tudo(self, client):
        c, engine = client
        _como_fazenda(1)
        assert c.get("/reproducao/servicos").status_code == 200
        assert c.get("/financeiro/opcoes").status_code == 200
        assert c.get("/estoque/").status_code == 200

    def test_sem_fazenda_no_token_pula_a_trava(self, client):
        """Token emitido antes do piloto (sem 'fid') — comportamento idêntico
        ao de sempre, sem checagem de contrato nenhuma."""
        c, engine = client
        _como_fazenda(None)
        assert c.get("/reproducao/servicos").status_code == 200

    def test_definir_contrato_standard_e_aprovar_libera_so_os_modulos_do_plano(self, client):
        c, engine = client
        _como_dono()
        _como_fazenda(2)

        # Antes de aprovar, mesmo com módulos definidos, continua bloqueado.
        r = c.put("/fazendas/2/contrato", json={"plano": "standard", "modulos": []})
        assert r.status_code == 200, r.text
        assert {m["modulo"] for m in r.json()["modulos"]} == {"rebanho", "reprodutivo"}
        assert c.get("/reproducao/servicos").status_code == 403

        r = c.post("/fazendas/2/contrato/aprovar")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ativo"

        assert c.get("/reproducao/servicos").status_code == 200
        # Financeiro não está no plano Standard.
        assert c.get("/financeiro/opcoes").status_code == 403

    def test_suspender_contrato_bloqueia_de_novo(self, client):
        c, engine = client
        _como_dono()
        _como_fazenda(2)
        c.put("/fazendas/2/contrato", json={"plano": "gold", "modulos": []})
        c.post("/fazendas/2/contrato/aprovar")
        assert c.get("/financeiro/opcoes").status_code == 200

        r = c.post("/fazendas/2/contrato/suspender")
        assert r.status_code == 200
        assert c.get("/financeiro/opcoes").status_code == 403

    def test_contrato_sob_medida_exige_rebanho(self, client):
        c, engine = client
        _como_dono()
        r = c.put("/fazendas/2/contrato", json={"plano": None, "modulos": [{"modulo": "financeiro", "preco": 50.0}]})
        assert r.status_code == 400

    def test_apenas_dono_gerencia_contrato(self, client):
        c, engine = client
        # _FakeAdmin (não-dono) já é o usuário padrão da fixture.
        r = c.put("/fazendas/2/contrato", json={"plano": "standard", "modulos": []})
        assert r.status_code == 403


class TestAnexoContrato:
    def test_upload_lista_baixa_e_exclui_anexo(self, client):
        c, engine = client
        _como_dono()
        arquivo = ("contrato.pdf", io.BytesIO(b"%PDF-1.4 conteudo de teste"), "application/pdf")
        r = c.post("/fazendas/2/contrato/anexos", files={"file": arquivo})
        assert r.status_code == 201, r.text
        anexo_id = r.json()["id"]

        r = c.get("/fazendas/2/contrato/anexos")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["nome_arquivo"] == "contrato.pdf"

        r = c.get(f"/fazendas/contrato/anexos/{anexo_id}")
        assert r.status_code == 200
        assert r.content == b"%PDF-1.4 conteudo de teste"

        r = c.delete(f"/fazendas/contrato/anexos/{anexo_id}")
        assert r.status_code == 200
        assert c.get("/fazendas/2/contrato/anexos").json() == []

    def test_apenas_dono_anexa_contrato(self, client):
        c, engine = client
        arquivo = ("contrato.pdf", io.BytesIO(b"conteudo"), "application/pdf")
        r = c.post("/fazendas/2/contrato/anexos", files={"file": arquivo})
        assert r.status_code == 403


class TestProvisionamentoContratoPendente:
    def test_criar_fazenda_nasce_com_contrato_aguardando_aprovacao(self, client):
        c, engine = client
        _como_dono()
        r = c.post("/fazendas/", json={"nome": "Outra Fazenda"})
        assert r.status_code == 200, r.text
        nova_id = r.json()["id"]

        r = c.get(f"/fazendas/{nova_id}/contrato")
        assert r.status_code == 200
        assert r.json()["status"] == "aguardando_aprovacao"
        assert r.json()["modulos"] == []
