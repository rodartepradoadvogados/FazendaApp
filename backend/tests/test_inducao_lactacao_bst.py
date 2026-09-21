"""
Cobre o pedido: ao confirmar "Entrou em lactação?" de um protocolo de indução
de lactação, uma pergunta extra ("incluir_bst") pode marcar o animal direto
em "Incluir no próximo BST" — o protocolo já aplicou BST nele mesmo, então
não faz sentido esperar o DEL mínimo normal (ver
`fazenda.models.animais.Animal.bst_pendente_inducao_lactacao`).

Cobre:
  1. `incluir_bst=True` no confirmar marca `aguardando_nova_aplicacao_bst` E
     `bst_pendente_inducao_lactacao`.
  2. `incluir_bst=False` (padrão) não mexe em nenhum dos dois — regressão do
     fluxo normal (sem pedido de BST).
  3. GET /agenda/ mostra o animal em `bst_nunca_aplicados` com
     `origem_inducao_lactacao=True` e o motivo específico de indução, MESMO
     com `grupo_primario` fora dos códigos de lactação (a foto congelada do
     CSV ainda não teria sido atualizada pelo Ideagri).
  4. Uma aplicação de BST real (`POST /agenda/bst/aplicar`) fecha o ciclo:
     limpa `bst_pendente_inducao_lactacao` junto com
     `aguardando_nova_aplicacao_bst`.
  5. `POST /agenda/bst/marcar-inapta` (inapta=True) também limpa
     `bst_pendente_inducao_lactacao` — marcar como inapta manualmente cancela
     a origem de indução.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal


@pytest.fixture
def client():
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
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _protocolo_id(c) -> int:
    r = c.post("/cadastro/protocolos-inducao-lactacao", json={
        "nome": "Indução padrão — teste",
        "dia_inicial": 0,
        "etapas": [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 5, "unidade": "ml"},
            {"dia": 6, "tipo": "manejo", "produto": "Iniciar ordenha"},
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _lancar(c, protocolo_id: int, animais: list[str], data_d0: str) -> int:
    r = c.post("/producao/inducao-lactacao", json={
        "protocolo_id": protocolo_id, "animais": animais, "data_d0": data_d0,
    })
    assert r.status_code == 201, r.text
    return r.json()["lancamento_id"]


def _concluir_etapas(engine, lancamento_id: int, numeros_matriz: list[str]):
    from fazenda.models import ProtocoloInducaoAplicacao

    with Session(engine) as s:
        query = (
            select(ProtocoloInducaoAplicacao)
            .where(ProtocoloInducaoAplicacao.lancamento_id == lancamento_id)
            .where(ProtocoloInducaoAplicacao.numero_matriz.in_(numeros_matriz))
        )
        for a in s.exec(query).all():
            a.realizada = True
            a.data_realizacao = a.data_prevista
            s.add(a)
        s.commit()


def _bst_nunca_aplicados(c) -> list[dict]:
    r = c.get("/agenda/", params={"data": date.today().isoformat(), "dias": 5})
    assert r.status_code == 200, r.text
    return r.json()["bst_nunca_aplicados"]


class TestConfirmarComIncluirBst:
    def test_incluir_bst_true_marca_os_dois_flags(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["422"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["422"])

        with Session(engine) as s:
            s.add(Animal(numero="422", sexo="F", ativo=True))
            s.commit()

        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/422/confirmar",
            json={"entrou_em_lactacao": True, "incluir_bst": True},
        )
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "422")).first()
            assert animal.aguardando_nova_aplicacao_bst is True
            assert animal.bst_pendente_inducao_lactacao is True

    def test_incluir_bst_false_nao_mexe_nos_flags(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["423"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["423"])

        with Session(engine) as s:
            s.add(Animal(numero="423", sexo="F", ativo=True))
            s.commit()

        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/423/confirmar",
            json={"entrou_em_lactacao": True},
        )
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "423")).first()
            assert animal.aguardando_nova_aplicacao_bst is False
            assert animal.bst_pendente_inducao_lactacao is False


class TestApareceNaListaBstComOrigemInducao:
    def test_aparece_em_bst_nunca_aplicados_mesmo_com_grupo_fora_de_lactacao(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["422"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["422"])

        with Session(engine) as s:
            # grupo_primario ainda "congelado" do CSV antigo (pré-indução) —
            # nada a ver com lactação — de propósito: prova que o bypass do
            # filtro de grupo em agenda_engine.py funciona.
            s.add(Animal(numero="422", sexo="F", ativo=True, grupo_primario="05 - SECAS"))
            s.commit()

        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/422/confirmar",
            json={"entrou_em_lactacao": True, "incluir_bst": True},
        )
        assert r.status_code == 200, r.text

        entradas = _bst_nunca_aplicados(c)
        minha = [b for b in entradas if b["numero_matriz"] == "422"]
        assert len(minha) == 1, entradas
        assert minha[0]["origem_inducao_lactacao"] is True
        assert minha[0]["requer_reanalise"] is True
        assert minha[0]["motivo_exclusao"] == (
            "Indução de lactação — protocolo já aplicou BST, incluída para a próxima aplicação"
        )

    def test_sem_incluir_bst_nao_aparece_na_lista(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["424"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["424"])

        with Session(engine) as s:
            s.add(Animal(numero="424", sexo="F", ativo=True, grupo_primario="05 - SECAS"))
            s.commit()

        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/424/confirmar",
            json={"entrou_em_lactacao": True},
        )
        assert r.status_code == 200, r.text

        entradas = _bst_nunca_aplicados(c)
        assert not [b for b in entradas if b["numero_matriz"] == "424"]


class TestCicloFechaComAplicacaoReal:
    def test_aplicar_bst_lote_limpa_bst_pendente_inducao_lactacao(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["422"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["422"])

        with Session(engine) as s:
            s.add(Animal(numero="422", sexo="F", ativo=True))
            s.commit()

        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/422/confirmar",
            json={"entrou_em_lactacao": True, "incluir_bst": True},
        )
        assert r.status_code == 200, r.text

        r = c.post("/agenda/bst/aplicar", json={
            "numeros_matriz": ["422"], "data_aplicacao": date.today().isoformat(),
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "422")).first()
            assert animal.aguardando_nova_aplicacao_bst is False
            assert animal.bst_pendente_inducao_lactacao is False

        assert not [b for b in _bst_nunca_aplicados(c) if b["numero_matriz"] == "422"]


class TestMarcarInaptaCancelaOrigemDeInducao:
    def test_marcar_inapta_limpa_bst_pendente_inducao_lactacao(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["422"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["422"])

        with Session(engine) as s:
            s.add(Animal(numero="422", sexo="F", ativo=True))
            s.commit()

        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/422/confirmar",
            json={"entrou_em_lactacao": True, "incluir_bst": True},
        )
        assert r.status_code == 200, r.text

        r = c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["422"], "inapta": True})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "422")).first()
            assert animal.bst_pendente_inducao_lactacao is False
            assert animal.excluir_bst is True
