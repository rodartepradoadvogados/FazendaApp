"""
Formulação de Dietas — endpoints HTTP: controle de acesso (admin/contratante/
consultor passam; operador comum e contador não passam), isolamento entre
fazendas, CRUD de simulações, `/calcular` stateless, e `aplicar` gerando um
DietaLancamento real (com `dieta_simulacao_id` de volta) a partir do
resultado do motor.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Alimento, Animal, ContratoFazenda, ContratoFazendaModulo, DietaLancamento, Fazenda, Lote, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

DIETA_MINIMA = {
    "animal": {
        "estado_fisiologico": "vaca_lactante", "raca": "Holandes", "peso_vivo_kg": 650.0, "peso_maturo_kg": 680.0,
        "ecc": 3.0, "paridade": 2.0, "del_dias": 150, "eq_cms": 8,
        "producao_leite_kg_dia": 35.0, "gordura_leite_pct": 3.8, "proteina_leite_pct": 3.2,
    },
    "itens": [
        {"nome": "Silagem de milho", "categoria_nasem": "Forragem", "conc_pct": 0.0, "proporcao_ms_pct": 60.0, "origem": "manual"},
        {"nome": "Farelo de soja", "categoria_nasem": "Concentrado proteico", "conc_pct": 100.0, "proporcao_ms_pct": 40.0, "origem": "manual"},
    ],
}


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.add(Lote(codigo="01", nome="Lactação Alta", fazenda_id=1))
        s.add(Animal(numero="A1", sexo="F", ativo=True, grupo_primario="01 - Lactação Alta", fazenda_id=1))
        s.add(Animal(numero="A2", sexo="F", ativo=True, grupo_primario="01 - Lactação Alta", fazenda_id=1))
        s.add(Alimento(nome="Silagem de milho", fazenda_id=1))
        s.add(Alimento(nome="Farelo de soja", fazenda_id=1))

        s.add(Usuario(id=10, username="dono", nome="Dono", senha_hash="x", papel="admin", email="jairodarte@gmail.com"))
        s.add(Usuario(id=11, username="admin1", nome="Admin", senha_hash="x", papel="admin", email="admin1@example.com"))
        s.add(Usuario(id=12, username="contratante1", nome="Contratante", senha_hash="x", papel="operador", email="contratante@example.com"))
        s.add(Usuario(id=13, username="consultor1", nome="Consultor", senha_hash="x", papel="operador", email="consultor@example.com"))
        s.add(Usuario(id=14, username="operador1", nome="Operador", senha_hash="x", papel="operador", email="operador@example.com", permissoes="alimentacao"))
        s.add(Usuario(id=15, username="contador1", nome="Contador", senha_hash="x", papel="operador", email="contador@example.com"))
        s.commit()
        s.add(UsuarioFazenda(usuario_id=12, fazenda_id=1, contratante=True))
        s.add(UsuarioFazenda(usuario_id=13, fazenda_id=1, consultor=True))
        s.add(UsuarioFazenda(usuario_id=15, fazenda_id=1, contador=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como(usuario_id: int | None):
    import main
    from fazenda.auth import get_current_user

    if usuario_id is None:
        main.app.dependency_overrides.pop(get_current_user, None)
        return

    with Session(main.engine) as s:
        user = s.get(Usuario, usuario_id)
    main.app.dependency_overrides[get_current_user] = lambda: user


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestControleDeAcesso:
    @pytest.mark.parametrize("usuario_id", [10, 11, 12, 13])
    def test_passam(self, client, usuario_id):
        c, _ = client
        _como(usuario_id)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 200

    def test_operador_comum_nao_passa(self, client):
        c, _ = client
        _como(14)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 403

    def test_contador_nao_passa(self, client):
        c, _ = client
        _como(15)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 403

    def test_sem_token_nao_passa(self, client):
        c, _ = client
        _como(None)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 401

    def test_sem_fazenda_selecionada_403(self, client):
        c, _ = client
        _como(11)
        _como_fazenda(None)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 403


class TestCalcularStateless:
    def test_calcular_nao_grava_nada(self, client):
        c, engine = client
        _como(11)
        r = c.post("/formulacao/calcular", json=DIETA_MINIMA)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["consumo"]["cms_kg_dia"] > 0
        assert any(linha["nutriente"].startswith("ELl") for linha in corpo["balanco"])
        with Session(engine) as s:
            from fazenda.models import DietaSimulacao
            assert s.exec(select(DietaSimulacao)).all() == []


class TestCrudSimulacao:
    def test_criar_listar_obter_salvar(self, client):
        c, _ = client
        _como(11)
        r = c.post("/formulacao/simulacoes", json={"nome": "Lote 01 - agosto", "lote": 1})
        assert r.status_code == 201, r.text
        sim_id = r.json()["id"]
        assert r.json()["status"] == "rascunho"

        r = c.get("/formulacao/simulacoes")
        assert any(s["id"] == sim_id for s in r.json())

        r = c.put(f"/formulacao/simulacoes/{sim_id}", json={**DIETA_MINIMA, "etapa_atual": 4})
        assert r.status_code == 200, r.text
        assert r.json()["cabecalho"]["status"] == "concluida"
        assert len(r.json()["itens"]) == 2
        assert r.json()["resultado"]["consumo"]["cms_kg_dia"] > 0

        r = c.get(f"/formulacao/simulacoes/{sim_id}")
        assert r.status_code == 200
        assert r.json()["resultado"] is not None

    def test_duplicar(self, client):
        c, _ = client
        _como(11)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Original", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA)
        r = c.post(f"/formulacao/simulacoes/{sim_id}/duplicar", json={"nome": "Cópia"})
        assert r.status_code == 201, r.text
        assert len(r.json()["itens"]) == 2
        assert r.json()["cabecalho"]["status"] == "rascunho"

    def test_excluir(self, client):
        c, _ = client
        _como(11)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Descartável"}).json()["id"]
        r = c.delete(f"/formulacao/simulacoes/{sim_id}")
        assert r.status_code == 200
        assert c.get(f"/formulacao/simulacoes/{sim_id}").status_code == 404


class TestIsolamentoEntreFazendas:
    def test_simulacao_da_fazenda_1_invisivel_na_2(self, client):
        c, _ = client
        _como(11)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Só da 1"}).json()["id"]

        _como_fazenda(2)
        assert all(s["id"] != sim_id for s in c.get("/formulacao/simulacoes").json())
        assert c.get(f"/formulacao/simulacoes/{sim_id}").status_code == 404
        assert c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA).status_code == 404
        assert c.delete(f"/formulacao/simulacoes/{sim_id}").status_code == 404


class TestAplicarNaDieta:
    def test_aplicar_cria_lancamento_com_vinculo(self, client):
        c, engine = client
        _como(11)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Para aplicar", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA)

        r = c.post(f"/formulacao/simulacoes/{sim_id}/aplicar", json={
            "lote": 1, "data_abertura": "2026-08-08", "base_quantidade": "total",
        })
        assert r.status_code == 201, r.text
        dieta_id = r.json()["dieta_lancamento_id"]
        assert r.json()["itens_criados"] == 2
        assert r.json()["qtd_animais"] == 2

        with Session(engine) as s:
            dieta = s.get(DietaLancamento, dieta_id)
            assert dieta.dieta_simulacao_id == sim_id
            assert dieta.lote == 1

        r = c.get(f"/formulacao/simulacoes/{sim_id}")
        assert r.json()["cabecalho"]["status"] == "aplicada"
        assert r.json()["cabecalho"]["dieta_lancamento_id"] == dieta_id

    def test_aplicar_com_dieta_ativa_sem_encerrar_409(self, client):
        c, _ = client
        _como(11)
        sim1 = c.post("/formulacao/simulacoes", json={"nome": "Primeira", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim1}", json=DIETA_MINIMA)
        c.post(f"/formulacao/simulacoes/{sim1}/aplicar", json={"lote": 1, "data_abertura": "2026-08-01"})

        sim2 = c.post("/formulacao/simulacoes", json={"nome": "Segunda", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim2}", json=DIETA_MINIMA)
        r = c.post(f"/formulacao/simulacoes/{sim2}/aplicar", json={"lote": 1, "data_abertura": "2026-08-08"})
        assert r.status_code == 409

        r = c.post(f"/formulacao/simulacoes/{sim2}/aplicar", json={
            "lote": 1, "data_abertura": "2026-08-08", "encerrar_anterior": True,
        })
        assert r.status_code == 201, r.text

    def test_excluir_simulacao_aplicada_409(self, client):
        c, _ = client
        _como(11)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Aplicada", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA)
        c.post(f"/formulacao/simulacoes/{sim_id}/aplicar", json={"lote": 1, "data_abertura": "2026-08-08"})
        assert c.delete(f"/formulacao/simulacoes/{sim_id}").status_code == 409
        assert c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA).status_code == 409


class TestBibliotecaDeAlimentos:
    def test_listar_alimentos_marca_sem_composicao(self, client):
        c, _ = client
        _como(11)
        r = c.get("/formulacao/alimentos")
        assert r.status_code == 200
        nomes = {a["nome"]: a["sem_composicao"] for a in r.json()["cadastrados"]}
        assert nomes.get("Silagem de milho") is True

    def test_resolver_sem_biblioteca_nem_laudo_cai_no_template(self, client):
        c, engine = client
        _como(11)
        with Session(engine) as s:
            alimento_id = s.exec(select(Alimento).where(Alimento.nome == "Silagem de milho")).first().id
        r = c.get(f"/formulacao/alimentos/{alimento_id}/resolver")
        assert r.status_code == 200
        assert r.json()["origem"] == "template"
        assert r.json()["valores"]["fdn_pct"] is not None

    def test_templates_e_biblioteca_semente(self, client):
        c, _ = client
        _como(11)
        r = c.get("/formulacao/templates")
        assert r.status_code == 200
        assert len(r.json()["categorias"]) == 11
        assert len(r.json()["biblioteca_semente"]) == 12
