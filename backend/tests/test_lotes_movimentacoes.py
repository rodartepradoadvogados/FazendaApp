"""
Testes de cadastro de lotes (Configurações > Cadastro) e movimentação de
animais entre lotes (Rebanho > Movimentar animais).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Lote


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
        with Session(engine) as s:
            s.add(Lote(codigo="01", nome="Alta", del_min=0, del_max=100))
            s.add(Lote(codigo="02", nome="Baixa", del_min=101, del_max=305))
            s.add(Animal(numero="201", grupo_primario="01 - Alta", del_dias=50, ativo=True))
            s.add(Animal(numero="202", grupo_primario="01 - Alta", del_dias=80, ativo=True))
            s.add(Animal(numero="203", grupo_primario="02 - Baixa", del_dias=200, ativo=True))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestCadastroLotes:
    def test_lista_lotes_com_contagem(self, client):
        r = client.get("/lotes/")
        assert r.status_code == 200
        by_codigo = {l["codigo"]: l for l in r.json()}
        assert by_codigo["01"]["qtd_animais"] == 2
        assert by_codigo["02"]["qtd_animais"] == 1
        assert by_codigo["01"]["rotulo"] == "01 - Alta"

    def test_cria_lote_novo(self, client):
        r = client.post("/lotes/", json={"codigo": "03", "nome": "Média", "del_min": 0, "del_max": 60})
        assert r.status_code == 200
        assert r.json()["codigo"] == "03"

    def test_nao_permite_codigo_duplicado(self, client):
        r = client.post("/lotes/", json={"codigo": "01", "nome": "Outra"})
        assert r.status_code == 400

    def test_rejeita_faixa_del_invertida(self, client):
        r = client.post("/lotes/", json={"codigo": "04", "nome": "X", "del_min": 100, "del_max": 10})
        assert r.status_code == 400

    def test_editar_nome_cascateia_para_animais(self, client):
        lote_id = next(l["id"] for l in client.get("/lotes/").json() if l["codigo"] == "01")
        r = client.put(f"/lotes/{lote_id}", json={"codigo": "01", "nome": "Alta produção", "del_min": 0, "del_max": 100})
        assert r.status_code == 200
        animais = client.get("/animais/").json()
        assert all(a["grupo_primario"] == "01 - Alta produção" for a in animais if a["numero"] in ("201", "202"))


class TestMovimentacoes:
    def test_lista_motivos_fixos(self, client):
        r = client.get("/movimentacoes/motivos")
        assert r.status_code == 200
        assert "Tratamento/doença" in r.json()

    def test_move_um_animal(self, client):
        r = client.post("/movimentacoes/mover", json={
            "data_movimento": "2026-07-08", "hora_movimento": "10:30", "motivo": "Crescimento",
            "lote_destino_codigo": "02", "animais": ["201"],
        })
        assert r.status_code == 200
        assert r.json()["movidos"] == 1
        animal = client.get("/animais/201").json()
        assert animal["grupo_primario"] == "02 - Baixa"
        assert animal["grupo_manual"] is True

    def test_move_varios_animais_em_lote(self, client):
        r = client.post("/movimentacoes/mover", json={
            "data_movimento": "2026-07-08", "motivo": "Aptidão",
            "lote_destino_codigo": "02", "animais": ["201", "202"],
        })
        assert r.json()["movidos"] == 2

    def test_rejeita_motivo_fora_da_lista(self, client):
        r = client.post("/movimentacoes/mover", json={
            "data_movimento": "2026-07-08", "motivo": "Outro motivo qualquer",
            "lote_destino_codigo": "02", "animais": ["201"],
        })
        assert r.status_code == 400

    def test_rejeita_lote_destino_inexistente(self, client):
        r = client.post("/movimentacoes/mover", json={
            "data_movimento": "2026-07-08", "motivo": "Crescimento",
            "lote_destino_codigo": "99", "animais": ["201"],
        })
        assert r.status_code == 404

    def test_registra_historico_com_origem_e_destino(self, client):
        client.post("/movimentacoes/mover", json={
            "data_movimento": "2026-07-08", "motivo": "Parto",
            "lote_destino_codigo": "02", "animais": ["201"],
        })
        r = client.get("/movimentacoes/")
        registro = r.json()[0]
        assert registro["numero_matriz"] == "201"
        assert registro["lote_origem"] == "01 - Alta"
        assert registro["lote_destino"] == "02 - Baixa"
        assert registro["motivo"] == "Parto"

    def test_upload_geral_nao_sobrescreve_lote_movido_manualmente(self, client, monkeypatch):
        client.post("/movimentacoes/mover", json={
            "data_movimento": "2026-07-08", "motivo": "Crescimento",
            "lote_destino_codigo": "02", "animais": ["201"],
        })
        from fazenda.parsers import geral as geral_parser

        def _fake_parse_geral(content):
            return [Animal(numero="201", grupo_primario="01 - Alta", grupo_raw="01 - Alta", ativo=True)]

        monkeypatch.setattr(geral_parser, "parse_geral", _fake_parse_geral)
        import fazenda.api.routers.upload as upload_router
        monkeypatch.setattr(upload_router, "parse_geral", _fake_parse_geral)

        client.post("/upload/geral", files={"file": ("geral.csv", b"fake", "text/csv")})
        animal = client.get("/animais/201").json()
        assert animal["grupo_primario"] == "02 - Baixa"
