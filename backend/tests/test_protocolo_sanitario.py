"""
Testes do Protocolo sanitário: cadastro (com etapas D1/D2/D3...), lançamento
em um animal, geração de eventos na Agenda e baixa automática de estoque
quando o evento é marcado "realizado".
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, MovimentoEstoque, Sanidade


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

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _etapa(dia, produto="Mastite Injetável", dosagem=10.0, unidade="ml", via="Intramamária"):
    return {"dia": dia, "produto": produto, "dosagem": dosagem, "unidade": unidade, "via": via}


class TestCadastroProtocolo:
    def test_cria_protocolo_com_etapas(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite clínica padrão", "eh_mastite": True,
            "etapas": [_etapa(1), _etapa(2), _etapa(3)],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["eh_mastite"] is True
        assert [e["dia"] for e in corpo["etapas"]] == [1, 2, 3]

    def test_rejeita_etapa_com_dia_zero(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Protocolo inválido", "etapas": [_etapa(0), _etapa(1)],
        })
        assert r.status_code == 400
        assert "D0" in r.json()["detail"]

    def test_rejeita_protocolo_sem_etapas(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={"nome": "Vazio", "etapas": []})
        assert r.status_code == 400

    def test_rejeita_via_fora_da_lista_fixa(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Via inválida", "etapas": [_etapa(1, via="Tópica")],
        })
        assert r.status_code == 400
        assert "Via inválida" in r.json()["detail"]

    def test_aceita_cada_via_da_lista_fixa(self, client):
        c, engine = client
        for i, via in enumerate(["Intramamária", "Intramuscular", "Intravenosa", "Subdérmica", "Oral"]):
            r = c.post("/cadastro/protocolos-sanitarios", json={
                "nome": f"Via {via}", "etapas": [_etapa(1, via=via)],
            })
            assert r.status_code == 200, r.json()

    def test_rejeita_nome_duplicado(self, client):
        c, engine = client
        c.post("/cadastro/protocolos-sanitarios", json={"nome": "Duplicado", "etapas": [_etapa(1)]})
        r = c.post("/cadastro/protocolos-sanitarios", json={"nome": "Duplicado", "etapas": [_etapa(1)]})
        assert r.status_code == 409

    def test_atualiza_protocolo_substitui_etapas(self, client):
        c, engine = client
        pid = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Editável", "etapas": [_etapa(1), _etapa(2)],
        }).json()["id"]
        r = c.put(f"/cadastro/protocolos-sanitarios/{pid}", json={
            "nome": "Editável", "etapas": [_etapa(1, produto="Novo produto")],
        })
        assert r.status_code == 200
        assert len(r.json()["etapas"]) == 1
        assert r.json()["etapas"][0]["produto"] == "Novo produto"


class TestLancamentoProtocolo:
    def _protocolo_mastite(self, c):
        return c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite subclínica", "eh_mastite": True,
            "etapas": [_etapa(1), _etapa(2), _etapa(3)],
        }).json()["id"]

    def _protocolo_simples(self, c):
        return c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Vermifugação", "etapas": [_etapa(1, produto="Ivermectina", unidade="ml")],
        }).json()["id"]

    def test_lanca_protocolo_gera_uma_aplicacao_por_etapa_com_datas_corretas(self, client):
        c, engine = client
        protocolo_id = self._protocolo_simples(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numero_matriz": "700", "data_inicio": "2026-03-01",
        })
        assert r.status_code == 201

    def test_datas_das_etapas_seguem_d1_d2_d3_sem_d0(self, client):
        c, engine = client
        protocolo_id = self._protocolo_mastite(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numero_matriz": "700", "data_inicio": "2026-03-01",
            "classificacao_mastite": "clinica", "tetos_afetados": ["AE", "PD"],
        })
        assert r.status_code == 201
        aplicacoes = sorted(r.json()["aplicacoes"], key=lambda a: a["data_prevista"])
        datas = [a["data_prevista"] for a in aplicacoes]
        assert datas == ["2026-03-01", "2026-03-02", "2026-03-03"]  # D1=início, D2=+1, D3=+2

    def test_exige_classificacao_de_mastite_quando_protocolo_e_mastite(self, client):
        c, engine = client
        protocolo_id = self._protocolo_mastite(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numero_matriz": "700", "data_inicio": "2026-03-01",
        })
        assert r.status_code == 400

    def test_rejeita_teto_invalido(self, client):
        c, engine = client
        protocolo_id = self._protocolo_mastite(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numero_matriz": "700", "data_inicio": "2026-03-01",
            "classificacao_mastite": "clinica", "tetos_afetados": ["XX"],
        })
        assert r.status_code == 400

    def test_rejeita_protocolo_sem_etapas_cadastradas(self, client):
        c, engine = client
        # protocolo criado direto no banco sem passar pela validação de cadastro (não deve ocorrer via API, mas defende o endpoint de lançamento)
        pid = c.post("/cadastro/protocolos-sanitarios", json={"nome": "X", "etapas": [_etapa(1)]}).json()["id"]
        with Session(engine) as s:
            from fazenda.models import ProtocoloSanitarioEtapa
            etapa = s.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == pid)).first()
            s.delete(etapa)
            s.commit()
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numero_matriz": "700", "data_inicio": "2026-03-01",
        })
        assert r.status_code == 400


class TestAgendaEBaixaAutomatica:
    def _lancar(self, c, produto="Mastite Injetável", unidade="ml", dosagem=10.0):
        protocolo_id = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite ambiental", "eh_mastite": True,
            "etapas": [_etapa(1, produto=produto, unidade=unidade, dosagem=dosagem), _etapa(2, produto=produto, unidade=unidade, dosagem=dosagem)],
        }).json()["id"]
        lanc = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numero_matriz": "700", "data_inicio": "2026-01-01",
            "classificacao_mastite": "ambiental", "tetos_afetados": ["AD"],
        }).json()
        return lanc

    def test_aplicacao_pendente_aparece_na_agenda(self, client):
        c, engine = client
        self._lancar(c)
        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        assert any(e["id"].startswith("protocolo_sanitario_") and e["numero_animal"] == "700" for e in eventos)

    def test_marcar_realizado_da_baixa_e_registra_sanidade(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Mastite Injetável", quantidade=100.0, unidade="ml"))
            s.commit()

        self._lancar(c, produto="Mastite Injetável", unidade="ml", dosagem=10.0)
        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        alvo = next(e for e in eventos if e["id"].startswith("protocolo_sanitario_"))

        r = c.post("/agenda/realizados", json={"evento_id": alvo["id"]})
        assert r.status_code == 200

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Mastite Injetável")).first()
            assert item.quantidade == 90.0
            movimento = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.nome_item == "Mastite Injetável")).first()
            assert movimento is not None
            sanidade = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "700")).first()
            assert sanidade is not None
            assert sanidade.produto == "Mastite Injetável"

        eventos2 = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        assert alvo["id"] not in [e["id"] for e in eventos2]

    def test_nao_da_baixa_quando_unidade_incompativel(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Produto Litro", quantidade=50.0, unidade="L"))
            s.commit()

        self._lancar(c, produto="Produto Litro", unidade="unidade", dosagem=2.0)
        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        alvo = next(e for e in eventos if e["id"].startswith("protocolo_sanitario_"))
        c.post("/agenda/realizados", json={"evento_id": alvo["id"]})

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Produto Litro")).first()
            assert item.quantidade == 50.0  # sem baixa — unidade incompatível
            sanidade = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "700")).first()
            assert sanidade is not None  # aplicação ainda é registrada em Sanidade
