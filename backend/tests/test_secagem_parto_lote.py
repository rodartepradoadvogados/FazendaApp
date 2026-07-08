"""
Testes de: lançamento de Secagem, sugestão automática de lote em eventos de
vida (nascimento/parto/secagem) e o novo endpoint real de Parto/nascimento.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Estoque, Lote, Parto, Sanidade, Secagem, Servico


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


class TestSecagemInfo:
    def test_calcula_data_prevista_e_sugere_lote_das_secas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", del_dias=220, grupo_primario="02 - Alta", ativo=True))
            s.add(Servico(numero_matriz="500", data_servico=date(2026, 1, 1), diagnostico="POSITIVO", ordem_parto=2))
            s.add(Lote(codigo="05", nome="SECAS", status_lactacao="seca"))
            s.commit()

        r = c.get("/producao/secagem-info", params={"numero_matriz": "500"})
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["del_atual"] == 220
        assert corpo["deve_secar"] is True
        assert corpo["lote_sugerido"] == {"codigo": "05", "nome": "SECAS", "rotulo": "05 - SECAS"}
        # Girolando = 287 dias de gestação; secagem = parto provável - 60 dias
        assert corpo["data_prevista_secagem"] == "2026-08-16"

    def test_novilha_1a_cria_nao_deve_secar(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="501", raca="Girolando", del_dias=100, ativo=True))
            s.add(Servico(numero_matriz="501", data_servico=date(2026, 1, 1), diagnostico="POSITIVO", ordem_parto=0))
            s.commit()

        r = c.get("/producao/secagem-info", params={"numero_matriz": "501"})
        assert r.json()["deve_secar"] is False

    def test_animal_inexistente_da_404(self, client):
        c, _ = client
        r = c.get("/producao/secagem-info", params={"numero_matriz": "nao-existe"})
        assert r.status_code == 404


class TestRegistrarSecagem:
    def test_cria_registro_produtos_e_baixa_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", del_dias=220, ativo=True))
            s.add(Estoque(nome="Tetradelta", quantidade=20, unidade="dose"))
            s.add(Lote(codigo="05", nome="SECAS", status_lactacao="seca"))
            s.commit()

        r = c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "rotina",
            "escore_condicao_corporal": 3.25,
            "produtos": [{"produto": "Tetradelta", "quantidade": 4, "unidade": "dose"}],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["criado"] is True
        assert corpo["lote_sugerido"]["codigo"] == "05"

        with Session(engine) as s:
            from sqlmodel import select
            sec = s.exec(select(Secagem).where(Secagem.numero_matriz == "500")).first()
            assert sec.motivo == "rotina"
            assert sec.escore_condicao_corporal == 3.25
            aplicacao = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "500")).first()
            assert aplicacao.produto == "Tetradelta"
            assert aplicacao.atividade == "Secagem"
            item = s.exec(select(Estoque).where(Estoque.nome == "Tetradelta")).first()
            assert item.quantidade == 16

    def test_motivo_invalido_da_400(self, client):
        c, _ = client
        r = c.post("/producao/secagem", json={"numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "invalido"})
        assert r.status_code == 400

    def test_ecc_fora_da_faixa_da_400(self, client):
        c, _ = client
        r = c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "rotina", "escore_condicao_corporal": 6,
        })
        assert r.status_code == 400


class TestSugestaoLoteEvento:
    def test_sugere_lote_de_bezerras_ao_nascer(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="01", nome="BEZ 1 (0 A 30)", categorias="bezerra,bezerro", idade_dias_max=30))
            s.add(Lote(codigo="03", nome="Média", categorias="vaca", del_min=61, del_max=200))
            s.commit()

        r = c.post("/producao/sugestao-lote-evento", json={
            "numero_matriz": "600", "categoria_abrev": "Bezerra", "data_nasc": "2026-07-08",
        })
        assert r.status_code == 200
        assert r.json()["lote_sugerido"]["codigo"] == "01"

    def test_sugere_lote_de_vaca_parida(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="01", nome="BEZ 1 (0 A 30)", categorias="bezerra,bezerro", idade_dias_max=30))
            s.add(Lote(codigo="03", nome="Média", categorias="vaca", del_min=0, del_max=10))
            s.commit()

        r = c.post("/producao/sugestao-lote-evento", json={
            "numero_matriz": "500", "categoria_abrev": "Vaca", "del_dias": 0,
        })
        assert r.status_code == 200
        assert r.json()["lote_sugerido"]["codigo"] == "03"

    def test_sem_lote_configurado_retorna_nulo(self, client):
        c, _ = client
        r = c.post("/producao/sugestao-lote-evento", json={"numero_matriz": "700", "categoria_abrev": "Vaca"})
        assert r.json()["lote_sugerido"] is None


class TestRegistrarParto:
    def test_cria_parto_e_crias_novas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", del_dias=283, ativo=True))
            s.commit()

        r = c.post("/reproducao/parto", json={
            "numero_matriz": "500", "data_parto": "2026-07-08", "tipo_parto": "Normal",
            "crias": [{"numero": "601", "sexo": "F", "nasceu_viva": True}],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["ordem_parto"] == 1
        assert corpo["crias_criadas"] == ["601"]

        with Session(engine) as s:
            from sqlmodel import select
            parto = s.exec(select(Parto).where(Parto.numero_matriz == "500")).first()
            assert parto.sexo_cria_1 == "F"
            assert parto.ordem_parto == 1
            cria = s.exec(select(Animal).where(Animal.numero == "601")).first()
            assert cria.mae_numero == "500"
            assert cria.raca == "Girolando"
            mae = s.exec(select(Animal).where(Animal.numero == "500")).first()
            assert mae.del_dias == 0

    def test_incrementa_ordem_parto_em_partos_subsequentes(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", ativo=True))
            s.add(Parto(numero_matriz="500", data_parto=date(2024, 1, 1), ordem_parto=1))
            s.commit()

        r = c.post("/reproducao/parto", json={"numero_matriz": "500", "data_parto": "2026-07-08", "crias": []})
        assert r.json()["ordem_parto"] == 2

    def test_cria_ja_cadastrada_nao_e_duplicada(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", ativo=True))
            s.add(Animal(numero="601", raca="Girolando", ativo=True))
            s.commit()

        r = c.post("/reproducao/parto", json={
            "numero_matriz": "500", "data_parto": "2026-07-08",
            "crias": [{"numero": "601", "sexo": "F"}],
        })
        assert r.json()["crias_criadas"] == []

        with Session(engine) as s:
            from sqlmodel import select
            animais = s.exec(select(Animal).where(Animal.numero == "601")).all()
            assert len(animais) == 1

    def test_matriz_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/reproducao/parto", json={"numero_matriz": "nao-existe", "data_parto": "2026-07-08", "crias": []})
        assert r.status_code == 404


class TestMotivosDeMovimentacaoIncluemSecagemENascimento:
    def test_secagem_e_nascimento_sao_motivos_validos(self, client):
        c, _ = client
        motivos = c.get("/movimentacoes/motivos").json()
        assert "Secagem" in motivos
        assert "Nascimento" in motivos
