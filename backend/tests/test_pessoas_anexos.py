"""
Anexos de Pessoa — RG, CPF, carteira de trabalho, contratos, holerite,
comprovantes, com validade opcional (ver PessoaAnexo, POST /cadastro/pessoas/
{id}/anexos e o alerta correspondente na Agenda em
test_agenda_pessoa_documento_vencendo.py).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

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

    import fazenda.api.routers.cadastro.pessoas as pessoas_mod
    _bucket: dict[str, bytes] = {}
    monkeypatch.setattr(pessoas_mod, "enviar_arquivo", lambda caminho, conteudo, *a, **k: _bucket.__setitem__(caminho, conteudo))
    monkeypatch.setattr(pessoas_mod, "baixar_arquivo", lambda caminho, *a, **k: _bucket[caminho])
    monkeypatch.setattr(pessoas_mod, "excluir_arquivo", lambda caminho, *a, **k: _bucket.pop(caminho, None))

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _criar_pessoa(client, **overrides):
    dados = {"nome": "Maria Funcionária", "tipos": ["Funcionário"]}
    dados.update(overrides)
    return client.post("/cadastro/pessoas", json=dados).json()["id"]


def _pdf(nome="contrato.pdf"):
    return {"file": (nome, b"%PDF-1.4 contrato", "application/pdf")}


class TestAnexarDocumentoPessoa:
    def test_anexa_contrato_determinado_com_validade(self, client):
        pessoa_id = _criar_pessoa(client)
        r = client.post(
            f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf(),
            data={"categoria": "Contrato de trabalho por prazo determinado", "data_validade": "2026-12-31"},
        )
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["categoria"] == "Contrato de trabalho por prazo determinado"
        assert corpo["data_validade"] == "2026-12-31"
        assert corpo["nome_arquivo"] == "contrato.pdf"

    def test_anexa_sem_validade(self, client):
        pessoa_id = _criar_pessoa(client)
        r = client.post(f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf("rg.pdf"), data={"categoria": "RG"})
        assert r.status_code == 201, r.text
        assert r.json()["data_validade"] is None

    def test_categoria_invalida_e_rejeitada(self, client):
        pessoa_id = _criar_pessoa(client)
        r = client.post(f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf(), data={"categoria": "Boleto"})
        assert r.status_code == 400

    def test_pessoa_inexistente_da_404(self, client):
        r = client.post("/cadastro/pessoas/999999/anexos", files=_pdf(), data={"categoria": "RG"})
        assert r.status_code == 404

    def test_todas_as_categorias_sao_aceitas(self, client):
        pessoa_id = _criar_pessoa(client)
        from fazenda.models import CATEGORIAS_PESSOA_ANEXO
        for categoria in CATEGORIAS_PESSOA_ANEXO:
            r = client.post(f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf(f"{categoria}.pdf"), data={"categoria": categoria})
            assert r.status_code == 201, f"{categoria}: {r.text}"

    def test_listar_anexos_da_pessoa(self, client):
        pessoa_id = _criar_pessoa(client)
        client.post(f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf("rg.pdf"), data={"categoria": "RG"})
        client.post(f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf("cpf.pdf"), data={"categoria": "CPF"})
        anexos = client.get(f"/cadastro/pessoas/{pessoa_id}/anexos").json()
        assert sorted(a["nome_arquivo"] for a in anexos) == ["cpf.pdf", "rg.pdf"]

    def test_conteudo_anexado_pode_ser_baixado(self, client):
        pessoa_id = _criar_pessoa(client)
        anexo_id = client.post(f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf(), data={"categoria": "RG"}).json()["id"]
        r = client.get(f"/cadastro/pessoas/anexos/{anexo_id}")
        assert r.status_code == 200
        assert r.content == b"%PDF-1.4 contrato"

    def test_excluir_anexo(self, client):
        pessoa_id = _criar_pessoa(client)
        anexo_id = client.post(f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf(), data={"categoria": "RG"}).json()["id"]
        r = client.delete(f"/cadastro/pessoas/anexos/{anexo_id}")
        assert r.status_code == 200
        assert client.get(f"/cadastro/pessoas/{pessoa_id}/anexos").json() == []
        assert client.get(f"/cadastro/pessoas/anexos/{anexo_id}").status_code == 404

    def test_excluir_pessoa_remove_anexos_junto(self, client):
        pessoa_id = _criar_pessoa(client)
        anexo_id = client.post(f"/cadastro/pessoas/{pessoa_id}/anexos", files=_pdf(), data={"categoria": "RG"}).json()["id"]
        assert client.delete(f"/cadastro/pessoas/{pessoa_id}").status_code == 200
        assert client.get(f"/cadastro/pessoas/anexos/{anexo_id}").status_code == 404
