"""
Reprodução + verificação de vazamento cross-tenant no motor de exclusões
(`fazenda/api/routers/exclusoes.py`) — encontrado na auditoria site-wide de
18/08: `GET /exclusoes/buscar` e `POST /exclusoes/{impacto,confirmar}` liam
(e, para admin, excluíam) registros de QUALQUER fazenda sem checar
`fazenda_id`, para praticamente todos os tipos (financeiro, pessoa, animal,
serviço, sanidade, protocolos, fornecedor, estoque, doença, etc.).

Também cobre B7 — a mesma classe de IDOR de escrita (achado #3 da mesma
auditoria) em `PUT /financeiro/tipos-documento/{id}` (fábrica
`_crud_nome_ativo_financeiro`, compartilhada com formas-pagamento-cadastro e
classificações — um teste do trio já cobre a fábrica inteira).

Mesmo fixture/convenção de test_isolamento_rotas_criticas.py.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Teste"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "outroadmin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestFinanceiroNaoVazaEntreFazendas:
    def test_buscar_nao_lista_lancamento_de_outra_fazenda(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Pagamento sigiloso fazenda 1", "valor_total": 999999.99}],
            "centro_custo": "Pecuária Leiteira",
            "data_emissao": str(date.today()),
        })
        assert r.status_code == 201, r.text

        _como_fazenda(2)
        r = c.get("/exclusoes/buscar", params={"tipo": "financeiro", "termo": ""})
        assert r.status_code == 200
        assert all("sigiloso" not in (item.get("titulo") or "") for item in r.json())

    def test_confirmar_exclusao_de_lancamento_de_outra_fazenda_da_404(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Item fazenda 1", "valor_total": 100.0}],
            "centro_custo": "Pecuária Leiteira",
            "data_emissao": str(date.today()),
        })
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["parcelas"][0]["id"] if "parcelas" in r.json() else r.json().get("id")
        # A busca já garante o id real independentemente do formato de retorno.
        _como_fazenda(1)
        achado = c.get("/exclusoes/buscar", params={"tipo": "financeiro", "termo": "Item fazenda 1"}).json()
        assert achado, "setup falhou — não achou o lançamento recém-criado"
        lancamento_id = achado[0]["id"]

        _como_fazenda(2)
        r_impacto = c.post("/exclusoes/impacto", json={"tipo": "financeiro", "id": str(lancamento_id)})
        assert r_impacto.status_code == 404

        r_confirmar = c.post("/exclusoes/confirmar", json={"tipo": "financeiro", "id": str(lancamento_id)})
        assert r_confirmar.status_code == 404

        _como_fazenda(1)
        ainda_existe = c.get("/exclusoes/buscar", params={"tipo": "financeiro", "termo": "Item fazenda 1"}).json()
        assert ainda_existe, "o lançamento da fazenda 1 não pode ter sido apagado por um ataque da fazenda 2"


class TestPessoaNaoVazaEntreFazendas:
    def test_confirmar_exclusao_de_pessoa_de_outra_fazenda_da_404(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/cadastro/pessoas", json={"nome": "Funcionário Secreto Fazenda 1", "tipos": ["Funcionário"]})
        assert r.status_code == 200, r.text
        pessoa_id = r.json()["id"]

        _como_fazenda(2)
        r_busca = c.get("/exclusoes/buscar", params={"tipo": "pessoa", "termo": ""})
        assert all("Secreto Fazenda 1" not in (item.get("titulo") or "") for item in r_busca.json())

        r_confirmar = c.post("/exclusoes/confirmar", json={"tipo": "pessoa", "id": str(pessoa_id)})
        assert r_confirmar.status_code == 404

        _como_fazenda(1)
        r_get = c.get("/cadastro/pessoas")
        assert any(p["id"] == pessoa_id for p in r_get.json())


class TestB7TiposDocumentoFinanceiroIDOR:
    def test_editar_tipo_de_documento_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(1)
        criado = c.post("/financeiro/tipos-documento", json={"nome": "Nota fiscal fazenda 1"})
        assert criado.status_code == 200, criado.text
        item_id = criado.json()["id"]

        _como_fazenda(2)
        r = c.put(f"/financeiro/tipos-documento/{item_id}", json={"nome": "INVADIDO PELA FAZENDA 2"})
        assert r.status_code == 404

        _como_fazenda(1)
        ainda = c.get("/financeiro/tipos-documento").json()
        assert any(x["nome"] == "Nota fiscal fazenda 1" for x in ainda)
        assert all(x["nome"] != "INVADIDO PELA FAZENDA 2" for x in ainda)
