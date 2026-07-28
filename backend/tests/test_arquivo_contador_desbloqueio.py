"""
Arquivo fiscal-contábil (Documentos), cadeado de desbloqueio do contador e
calculadora de juros/multa — ver fazenda/api/routers/documentos.py,
fazenda/api/routers/chamados.py, fazenda/auth.py::bloquear_escrita_contador e
POST /auth/desbloquear.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import hash_senha
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Fazenda, TipoDocumento, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

SENHA_CONTADOR = "senha-do-contador-123"


class _FakeUser:
    id = 42
    papel = "operador"
    ativo = True
    username = "contador.teste"
    email = "contador@example.com"
    permissoes = "financeiro"
    senha_hash = hash_senha(SENHA_CONTADOR)


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
        s.add(UsuarioFazenda(usuario_id=42, fazenda_id=1, contador=True))
        s.add(TipoDocumento(nome="Nota fiscal", fazenda_id=1, ativo=True))
        s.add(TipoDocumento(nome="CCIR", fazenda_id=1, ativo=True))
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

    import fazenda.api.routers.documentos as documentos_mod
    monkeypatch.setattr(documentos_mod, "enviar_arquivo", lambda *a, **k: None)
    monkeypatch.setattr(documentos_mod, "baixar_arquivo", lambda *a, **k: b"conteudo-fake")
    monkeypatch.setattr(documentos_mod, "excluir_arquivo", lambda *a, **k: None)

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


class TestDocumentosContadorSemDesbloqueio:
    def test_contador_faz_upload_sem_desbloqueio(self, client):
        r = client.post(
            "/documentos/upload",
            files={"file": ("nota.pdf", b"conteudo-pdf", "application/pdf")},
            data={"categoria": "Nota fiscal", "inserir_no_balanco": "false"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["categoria"] == "Nota fiscal"
        assert body["inserir_no_balanco"] is False

    def test_upload_categoria_invalida_e_rejeitado(self, client):
        r = client.post(
            "/documentos/upload",
            files={"file": ("x.pdf", b"abc", "application/pdf")},
            data={"categoria": "Categoria Inexistente"},
        )
        assert r.status_code == 400

    def test_listar_e_baixar_documento(self, client):
        r = client.post(
            "/documentos/upload",
            files={"file": ("ccir.pdf", b"conteudo", "application/pdf")},
            data={"categoria": "CCIR", "data_documento": "2026-01-15"},
        )
        doc_id = r.json()["id"]
        r_lista = client.get("/documentos")
        assert r_lista.status_code == 200
        assert any(d["id"] == doc_id for d in r_lista.json())
        r_download = client.get(f"/documentos/{doc_id}/download")
        assert r_download.status_code == 200
        assert r_download.content == b"conteudo-fake"


class TestCadeadoDesbloqueio:
    def test_chamado_bloqueado_sem_desbloqueio(self, client):
        r = client.post("/chamados", json={"assunto": "Dúvida", "descricao": "Preciso de ajuda"})
        assert r.status_code == 403

    def test_desbloquear_com_senha_errada_falha(self, client):
        r = client.post("/auth/desbloquear", json={"senha": "senha-errada"})
        assert r.status_code == 401

    def test_desbloquear_com_senha_certa_libera_escrita(self, client):
        r = client.post("/auth/desbloquear", json={"senha": SENHA_CONTADOR})
        assert r.status_code == 200
        token = r.json()["token_desbloqueio"]
        assert token

        r_bloqueado = client.post(
            "/chamados", json={"assunto": "Sem token", "descricao": "x"},
        )
        assert r_bloqueado.status_code == 403

        r_liberado = client.post(
            "/chamados", json={"assunto": "Guia de imposto atrasada", "descricao": "Pagamento de guia X"},
            headers={"X-Desbloqueio": token},
        )
        assert r_liberado.status_code == 201, r_liberado.text
        assert r_liberado.json()["status"] == "aberto"

    def test_token_de_outro_usuario_nao_funciona(self, client):
        from fazenda.auth import criar_token_desbloqueio
        token_de_outro = criar_token_desbloqueio("outro.usuario")
        r = client.post(
            "/chamados", json={"assunto": "x", "descricao": "y"},
            headers={"X-Desbloqueio": token_de_outro},
        )
        assert r.status_code == 403

    def test_leitura_nunca_precisa_de_desbloqueio(self, client):
        r = client.get("/chamados")
        assert r.status_code == 200


class TestCalculadoraJuros:
    def test_bloqueada_para_contador_sem_desbloqueio(self, client):
        r = client.post("/financeiro/calcular-juros", json={
            "valor_original": 1000.0, "data_vencimento": "2026-01-01", "data_referencia": "2026-02-01",
        })
        assert r.status_code == 403

    def test_calculo_correto_com_desbloqueio(self, client):
        token = client.post("/auth/desbloquear", json={"senha": SENHA_CONTADOR}).json()["token_desbloqueio"]
        r = client.post(
            "/financeiro/calcular-juros",
            json={
                "valor_original": 1000.0, "data_vencimento": "2026-01-01", "data_referencia": "2026-01-31",
                "percentual_multa": 2.0, "percentual_juros_mes": 1.0,
            },
            headers={"X-Desbloqueio": token},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dias_atraso"] == 30
        assert body["valor_multa"] == 20.0
        assert body["valor_juros"] == 10.0
        assert body["valor_atualizado"] == 1030.0

    def test_sem_atraso_nao_cobra_nada(self, client):
        token = client.post("/auth/desbloquear", json={"senha": SENHA_CONTADOR}).json()["token_desbloqueio"]
        r = client.post(
            "/financeiro/calcular-juros",
            json={"valor_original": 500.0, "data_vencimento": "2026-03-01", "data_referencia": "2026-03-01"},
            headers={"X-Desbloqueio": token},
        )
        assert r.status_code == 200
        assert r.json() == {"dias_atraso": 0, "valor_multa": 0.0, "valor_juros": 0.0, "valor_atualizado": 500.0}
