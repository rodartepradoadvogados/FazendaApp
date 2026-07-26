"""
Fase 2C — produto independente do consultor: assinatura própria (fora de
qualquer fazenda-tenant), fazendas gerenciadas por importação de planilha, e
o modo Simulação (cálculo puro, sem persistência).
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoConsultor, FazendaGerenciada, RegistroImportado, Usuario

EMAIL_DONO = "jairodarte@gmail.com"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Usuario(username="consultor1", senha_hash="x", papel="operador", permissoes=""))
        s.add(Usuario(username="consultor2", senha_hash="x", papel="operador", permissoes=""))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _usuario_atual["user"]

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


_usuario_atual: dict = {}


class _FakeUser:
    def __init__(self, id_, username, email=""):
        self.id = id_
        self.papel = "operador"
        self.ativo = True
        self.username = username
        self.email = email
        self.permissoes = ""


def _como(id_, username, email=""):
    _usuario_atual["user"] = _FakeUser(id_, username, email)


def _como_dono():
    _usuario_atual["user"] = _FakeUser(99, "dono", EMAIL_DONO)


class TestAssinaturaConsultor:
    def test_solicitar_e_aprovar_plano(self, client):
        c, engine = client
        _como(1, "consultor1")
        r = c.post("/consultor/solicitar", json={"plano": "consultor_standard"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "aguardando_aprovacao"

        _como_dono()
        r = c.post("/consultor/1/aprovar")
        assert r.status_code == 200
        assert r.json()["status"] == "ativo"
        assert r.json()["limite_fazendas"] == 3

    def test_plano_invalido_rejeitado(self, client):
        c, engine = client
        _como(1, "consultor1")
        r = c.post("/consultor/solicitar", json={"plano": "inexistente"})
        assert r.status_code == 400

    def test_sem_contrato_ativo_bloqueia_fazenda_gerenciada(self, client):
        c, engine = client
        _como(1, "consultor1")
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda do Zé"})
        assert r.status_code == 403

    def test_endpoints_dono_only_rejeitam_consultor_comum(self, client):
        c, engine = client
        _como(1, "consultor1")
        assert c.post("/consultor/1/aprovar").status_code == 403
        assert c.post("/consultor/1/suspender").status_code == 403
        assert c.get("/consultor/todos").status_code == 403

    def test_reduzir_plano_aumenta_pendencia(self, client):
        c, engine = client
        _como(1, "consultor1")
        c.post("/consultor/solicitar", json={"plano": "consultor_diamond"})
        _como_dono()
        c.post("/consultor/1/aprovar")
        _como(1, "consultor1")
        r = c.post("/consultor/solicitar", json={"plano": "consultor_standard"})
        assert r.json()["status"] == "aguardando_aprovacao"
        assert r.json()["limite_fazendas"] == 3


@pytest.fixture
def consultor_ativo(client):
    c, engine = client
    _como(1, "consultor1")
    c.post("/consultor/solicitar", json={"plano": "consultor_standard"})
    _como_dono()
    c.post("/consultor/1/aprovar")
    _como(1, "consultor1")
    return c, engine


class TestFazendasGerenciadas:
    def test_criar_e_listar(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda do Zé", "produtor": "José Silva"})
        assert r.status_code == 200, r.text
        r = c.get("/consultor/fazendas")
        assert len(r.json()) == 1
        assert r.json()[0]["nome"] == "Fazenda do Zé"

    def test_limite_do_plano_standard_3_fazendas(self, consultor_ativo):
        c, engine = consultor_ativo
        for i in range(3):
            assert c.post("/consultor/fazendas", json={"nome": f"Fazenda {i}"}).status_code == 200
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda 4"})
        assert r.status_code == 403
        assert "Limite" in r.json()["detail"]

    def test_isolamento_entre_consultores(self, consultor_ativo):
        c, engine = consultor_ativo
        c.post("/consultor/fazendas", json={"nome": "Fazenda do consultor1"})

        with Session(engine) as s:
            s.add(ContratoConsultor(usuario_id=2, plano="consultor_standard", limite_fazendas=3, status="ativo"))
            s.commit()
        _como(2, "consultor2")
        r = c.get("/consultor/fazendas")
        assert r.json() == []

    def test_nao_pode_acessar_fazenda_gerenciada_de_outro_consultor(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda do consultor1"})
        fid = r.json()["id"]

        with Session(engine) as s:
            s.add(ContratoConsultor(usuario_id=2, plano="consultor_standard", limite_fazendas=3, status="ativo"))
            s.commit()
        _como(2, "consultor2")
        assert c.delete(f"/consultor/fazendas/{fid}").status_code == 403

    def test_excluir_fazenda_gerenciada_remove_registros_em_cascata(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda do Zé"})
        fid = r.json()["id"]
        conteudo = "vacas;producao_media;data\n50;25;01/07/2026\n".encode("windows-1252")
        c.post(
            f"/consultor/fazendas/{fid}/importar",
            files={"file": ("rebanho.csv", conteudo, "text/csv")},
            data={"categoria": "rebanho"},
        )
        with Session(engine) as s:
            assert len(s.exec(select(RegistroImportado)).all()) == 1
        assert c.delete(f"/consultor/fazendas/{fid}").status_code == 200
        with Session(engine) as s:
            assert len(s.exec(select(RegistroImportado)).all()) == 0


class TestImportacaoPlanilha:
    def test_importar_csv_cria_registros(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda do Zé"})
        fid = r.json()["id"]
        conteudo = (
            "vacas;producao_media;data\n"
            "50;25;01/07/2026\n"
            "52;24;01/06/2026\n"
        ).encode("windows-1252")
        r = c.post(
            f"/consultor/fazendas/{fid}/importar",
            files={"file": ("rebanho.csv", conteudo, "text/csv")},
            data={"categoria": "rebanho"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["criados"] == 2

        r = c.get(f"/consultor/fazendas/{fid}/indicadores")
        assert len(r.json()) == 2
        item = next(i for i in r.json() if i["dados"]["vacas"] == "50")
        assert item["data_referencia"] == "2026-07-01"
        assert item["categoria"] == "rebanho"

    def test_categoria_invalida_rejeitada(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda do Zé"})
        fid = r.json()["id"]
        conteudo = "vacas;data\n50;01/07/2026\n".encode("windows-1252")
        r = c.post(
            f"/consultor/fazendas/{fid}/importar",
            files={"file": ("x.csv", conteudo, "text/csv")},
            data={"categoria": "invalida"},
        )
        assert r.status_code == 400

    def test_filtro_por_categoria_nos_indicadores(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda do Zé"})
        fid = r.json()["id"]
        c.post(
            f"/consultor/fazendas/{fid}/importar",
            files={"file": ("rebanho.csv", "vacas\n50\n".encode("windows-1252"), "text/csv")},
            data={"categoria": "rebanho"},
        )
        c.post(
            f"/consultor/fazendas/{fid}/importar",
            files={"file": ("fin.csv", "receita\n1000\n".encode("windows-1252"), "text/csv")},
            data={"categoria": "financeiro"},
        )
        r = c.get(f"/consultor/fazendas/{fid}/indicadores", params={"categoria": "financeiro"})
        assert len(r.json()) == 1
        assert r.json()[0]["categoria"] == "financeiro"

    def test_excluir_registro_importado(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/fazendas", json={"nome": "Fazenda do Zé"})
        fid = r.json()["id"]
        c.post(
            f"/consultor/fazendas/{fid}/importar",
            files={"file": ("rebanho.csv", "vacas\n50\n".encode("windows-1252"), "text/csv")},
            data={"categoria": "rebanho"},
        )
        registro_id = c.get(f"/consultor/fazendas/{fid}/indicadores").json()[0]["id"]
        r = c.delete(f"/consultor/fazendas/{fid}/importacoes/{registro_id}")
        assert r.status_code == 200
        assert c.get(f"/consultor/fazendas/{fid}/indicadores").json() == []


class TestSimulacao:
    def test_calcula_indicadores_sem_persistir(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/simulacao/calcular", json={
            "vacas_lactacao": 100, "producao_media_litro_vaca_dia": 25, "preco_litro": 2.20,
            "custo_alimentar_vaca_dia": 15.0, "outros_custos_mensais": 5000.0,
        })
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["producao_total_litro_dia"] == 2500.0
        assert dados["producao_total_litro_mes"] == 75000.0
        assert dados["receita_mes"] == pytest.approx(165000.0)
        assert dados["custo_alimentar_mes"] == pytest.approx(45000.0)
        assert dados["custo_total_mes"] == pytest.approx(50000.0)
        assert dados["margem_mes"] == pytest.approx(115000.0)

        # Cálculo puro — nenhuma FazendaGerenciada/RegistroImportado nasce disso.
        with Session(engine) as s:
            assert s.exec(select(FazendaGerenciada)).all() == []
            assert s.exec(select(RegistroImportado)).all() == []

    def test_valores_negativos_rejeitados(self, consultor_ativo):
        c, engine = consultor_ativo
        r = c.post("/consultor/simulacao/calcular", json={
            "vacas_lactacao": -1, "producao_media_litro_vaca_dia": 25, "preco_litro": 2.0,
            "custo_alimentar_vaca_dia": 10.0,
        })
        assert r.status_code == 400

    def test_simulacao_exige_consultor_ativo(self, client):
        c, engine = client
        _como(1, "consultor1")
        r = c.post("/consultor/simulacao/calcular", json={
            "vacas_lactacao": 10, "producao_media_litro_vaca_dia": 20, "preco_litro": 2.0,
            "custo_alimentar_vaca_dia": 10.0,
        })
        assert r.status_code == 403
