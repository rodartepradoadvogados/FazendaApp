"""
As duas permissões de consumo de alimento do lote, editadas PELO ENDPOINT.

`permitir_fora_da_dieta` e `permitir_sem_estoque` controlam se o lançamento de
consumo aceita um alimento que não está na dieta ativa do lote, e um alimento
sem saldo em estoque. Nascem `False` — o padrão restritivo é o seguro, porque
cada uma desliga uma checagem que existe para pegar erro de digitação no curral.

O motivo deste arquivo existir separado é o buraco que ele fecha. As colunas
foram criadas no modelo e respeitadas pelo lançamento de consumo, mas `LoteIn`
não as declarava e `_aplicar_campos` não as atribuía — então a API aceitava o
JSON, ignorava os dois campos em silêncio e devolvia 200. Na prática as flags
ficavam `False` para sempre, e a única forma de ligá-las era editar o banco à
mão.

Isso passou despercebido porque os testes do lançamento de consumo setam as
flags DIRETO no banco via SQLModel, para montar o cenário — nenhum passava pelo
endpoint. Um campo que o payload ignora em silêncio é invisível para quem testa
só o comportamento a jusante: o cenário é montado à força e funciona, enquanto
o caminho real do usuário nunca é exercitado.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # A engine do módulo também aponta para cá: o conftest manda a aplicação
    # para um SQLite temporário SEM tabelas, e qualquer caminho que abra sessão
    # por fora do override de dependência estoura com "no such table".
    monkeypatch.setattr(database, "engine", engine)

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

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


def _criar(client, **extra) -> dict:
    corpo = {"codigo": "07", "nome": "Transição", **extra}
    r = client.post("/lotes/", json=corpo)
    assert r.status_code in (200, 201), r.text
    return r.json()


class TestPermissoesDeConsumoDoLote:
    def test_nascem_desmarcadas(self, client):
        """Padrão restritivo: quem não pediu nada não ganha a exceção."""
        lote = _criar(client)
        assert lote["permitir_fora_da_dieta"] is False
        assert lote["permitir_sem_estoque"] is False

    def test_criar_ja_ligando_as_duas(self, client):
        lote = _criar(client, permitir_fora_da_dieta=True, permitir_sem_estoque=True)
        assert lote["permitir_fora_da_dieta"] is True
        assert lote["permitir_sem_estoque"] is True

    def test_editar_liga_e_persiste(self, client):
        """O caso que estava quebrado: a API aceitava o JSON, respondia 200 e
        descartava os dois campos."""
        lote = _criar(client)
        r = client.put(f"/lotes/{lote['id']}", json={
            "codigo": "07", "nome": "Transição",
            "permitir_fora_da_dieta": True, "permitir_sem_estoque": True,
        })
        assert r.status_code == 200, r.text

        depois = next(l for l in client.get("/lotes/").json() if l["id"] == lote["id"])
        assert depois["permitir_fora_da_dieta"] is True, "a edição não persistiu — payload ignorado?"
        assert depois["permitir_sem_estoque"] is True

    def test_editar_desliga_de_volta(self, client):
        """Ligar sem conseguir desligar seria pior que não ter a flag."""
        lote = _criar(client, permitir_fora_da_dieta=True, permitir_sem_estoque=True)
        r = client.put(f"/lotes/{lote['id']}", json={
            "codigo": "07", "nome": "Transição",
            "permitir_fora_da_dieta": False, "permitir_sem_estoque": False,
        })
        assert r.status_code == 200, r.text

        depois = next(l for l in client.get("/lotes/").json() if l["id"] == lote["id"])
        assert depois["permitir_fora_da_dieta"] is False
        assert depois["permitir_sem_estoque"] is False

    def test_as_duas_sao_independentes(self, client):
        """São exceções diferentes: alimento fora da dieta e alimento sem
        saldo não têm relação entre si, e ligar uma não pode ligar a outra."""
        lote = _criar(client, permitir_fora_da_dieta=True)
        assert lote["permitir_fora_da_dieta"] is True
        assert lote["permitir_sem_estoque"] is False

    def test_omitir_os_campos_no_payload_nao_liga_nada(self, client):
        """Cliente antigo, que não conhece os campos novos, não pode ganhar a
        exceção sem querer."""
        lote = _criar(client, permitir_fora_da_dieta=True)
        client.put(f"/lotes/{lote['id']}", json={"codigo": "07", "nome": "Transição"})
        depois = next(l for l in client.get("/lotes/").json() if l["id"] == lote["id"])
        assert depois["permitir_fora_da_dieta"] is False, (
            "payload sem o campo deve cair no padrão restritivo, nunca manter ou ligar a exceção"
        )
