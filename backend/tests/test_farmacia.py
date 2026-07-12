"""
Farmácia — hierarquia por princípio ativo, unificação de volumes, mínimo por
apresentações, compatibilização sem perda e o gatilho de comunicação (baixa só
após estoque inicial/compra) + o menu "qual frasco?".
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, MedicamentoComercial, MovimentoEstoque, PrincipioAtivo, Sanidade
from fazenda.rules.farmacia import compatibilizar_estoque, resumo_principios, seed_farmacia


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


class TestSeedCompatibilizacao:
    def test_seed_cria_principios_e_marcas(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            principios = s.exec(select(PrincipioAtivo)).all()
            marcas = s.exec(select(MedicamentoComercial)).all()
        nomes = {p.nome for p in principios}
        assert "Meloxicam" in nomes and "Ivermectina" in nomes
        assert any(p.eh_biologico and p.nome.startswith("Clostridioses") for p in principios)
        # Marcas viram tabela filha do princípio.
        assert any(m.nome_comercial == "Maxicam 2%" and m.laboratorio == "Ourofino" for m in marcas)

    def test_seed_idempotente_nao_duplica(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            n1 = len(s.exec(select(PrincipioAtivo)).all())
            m1 = len(s.exec(select(MedicamentoComercial)).all())
            seed_farmacia(s)
            assert len(s.exec(select(PrincipioAtivo)).all()) == n1
            assert len(s.exec(select(MedicamentoComercial)).all()) == m1

    def test_compatibiliza_por_marca_e_por_texto_sem_perda(self, client):
        c, engine = client
        with Session(engine) as s:
            # item vinculado pela MARCA no nome
            s.add(Estoque(nome="Maxicam 2% frasco", quantidade=50.0, unidade="ml"))
            # item vinculado pelo TEXTO do princípio
            s.add(Estoque(nome="Ivermectina genérica", principio_ativo="Ivermectina", quantidade=100.0, unidade="ml"))
            # item com princípio fora do catálogo → cria e vincula
            s.add(Estoque(nome="Remédio X", principio_ativo="Molécula Inédita", quantidade=10.0, unidade="ml"))
            s.commit()
            seed_farmacia(s)
            res = compatibilizar_estoque(s)
            assert res["vinculados"] == 3
            assert res["criados"] == 1
            maxicam = s.exec(select(Estoque).where(Estoque.nome == "Maxicam 2% frasco")).first()
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            assert maxicam.principio_ativo_id == melox.id
            assert maxicam.medicamento_comercial_id is not None  # casou a marca
            assert s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Molécula Inédita")).first() is not None


class TestUnificacaoMinimo:
    def test_soma_volumes_e_minimo_por_apresentacoes(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            # frasco de 50ml com 40ml (0,8) + frasco de 250ml com 125ml (0,5) = 1,3 apres
            s.add(Estoque(nome="Maxicam 50", principio_ativo_id=melox.id, quantidade=40.0, unidade="ml",
                          volume_por_apresentacao=50.0, volume_unidade="ml"))
            s.add(Estoque(nome="Aliv V 250", principio_ativo_id=melox.id, quantidade=125.0, unidade="ml",
                          volume_por_apresentacao=250.0, volume_unidade="ml"))
            s.commit()
        r = c.get("/farmacia/principios")
        assert r.status_code == 200
        melox_res = next(p for p in r.json() if p["nome"] == "Meloxicam")
        assert melox_res["total_base"] == 165.0  # 40 + 125 ml
        assert melox_res["total_apresentacoes"] == 1.3
        assert melox_res["abaixo_minimo"] is False  # 1,3 >= 1

    def test_abaixo_do_minimo_quando_menos_de_uma_apresentacao(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            s.add(Estoque(nome="Maxicam 50 quase vazio", principio_ativo_id=melox.id, quantidade=20.0, unidade="ml",
                          volume_por_apresentacao=50.0, volume_unidade="ml"))  # 0,4 apres
            s.commit()
        melox_res = next(p for p in c.get("/farmacia/principios").json() if p["nome"] == "Meloxicam")
        assert melox_res["abaixo_minimo"] is True

    def test_converte_litros_e_ml_no_mesmo_principio(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            amitraz = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Amitraz")).first()  # base L
            s.add(Estoque(nome="Triatox 1L", principio_ativo_id=amitraz.id, quantidade=1.0, unidade="L"))
            s.add(Estoque(nome="Amitraz 500ml", principio_ativo_id=amitraz.id, quantidade=500.0, unidade="ml"))
            s.commit()
        res = next(p for p in c.get("/farmacia/principios").json() if p["nome"] == "Amitraz")
        assert res["total_base"] == 1.5  # 1 L + 0,5 L


class TestGatilhoQualFrasco:
    def _principio_com_dois_frascos(self, engine):
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            a = Estoque(nome="Maxicam 50", principio_ativo_id=melox.id, quantidade=50.0, unidade="ml",
                        volume_por_apresentacao=50.0, volume_unidade="ml", estoque_inicializado=True)
            b = Estoque(nome="Aliv V 250", principio_ativo_id=melox.id, quantidade=250.0, unidade="ml",
                        volume_por_apresentacao=250.0, volume_unidade="ml", estoque_inicializado=True)
            s.add(a); s.add(b)
            s.commit()
            return melox.id, a.id, b.id

    def test_apresentacoes_lista_frascos_do_principio(self, client):
        c, engine = client
        pa_id, a_id, b_id = self._principio_com_dois_frascos(engine)
        r = c.get("/farmacia/apresentacoes", params={"principio_ativo_id": pa_id})
        assert r.status_code == 200
        nomes = {x["nome"] for x in r.json()}
        assert nomes == {"Maxicam 50", "Aliv V 250"}

    def test_qual_frasco_abate_do_recipiente_escolhido(self, client):
        c, engine = client
        pa_id, a_id, b_id = self._principio_com_dois_frascos(engine)
        # Aplica 10ml escolhendo o frasco B (Aliv V 250) em 1 animal.
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": date.today().isoformat(), "animais": ["1"],
            "itens": [{"produto": "Aliv V 250", "quantidade": 10.0, "unidade": "ml", "estoque_id": b_id}],
        })
        assert r.status_code == 200
        with Session(engine) as s:
            assert s.get(Estoque, a_id).quantidade == 50.0    # frasco A intacto
            assert s.get(Estoque, b_id).quantidade == 240.0   # abateu do B

    def test_gatilho_sem_estoque_inicial_nao_baixa(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            item = Estoque(nome="Maxicam novo", principio_ativo_id=melox.id, quantidade=0.0, unidade="ml",
                           estoque_inicializado=False)
            s.add(item); s.commit(); item_id = item.id
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": date.today().isoformat(), "animais": ["1"],
            "itens": [{"produto": "Maxicam novo", "quantidade": 5.0, "unidade": "ml", "estoque_id": item_id}],
        })
        assert r.status_code == 200
        assert any("sem baixa" in a for a in r.json()["avisos"])
        with Session(engine) as s:
            assert s.get(Estoque, item_id).quantidade == 0.0  # não baixou
            # a aplicação foi registrada mesmo assim
            assert s.exec(select(Sanidade).where(Sanidade.produto == "Maxicam novo")).first() is not None

    def test_inicializar_liga_gatilho_e_baixa_passa_a_valer(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            item = Estoque(nome="Maxicam novo", principio_ativo_id=melox.id, quantidade=0.0, unidade="ml",
                           estoque_inicializado=False)
            s.add(item); s.commit(); item_id = item.id
        # Registra estoque inicial → liga o gatilho.
        r = c.post(f"/farmacia/estoque/{item_id}/inicializar", json={"quantidade": 100.0})
        assert r.status_code == 200 and r.json()["estoque_inicializado"] is True
        # Agora a aplicação baixa.
        c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": date.today().isoformat(), "animais": ["1"],
            "itens": [{"produto": "Maxicam novo", "quantidade": 10.0, "unidade": "ml", "estoque_id": item_id}],
        })
        with Session(engine) as s:
            assert s.get(Estoque, item_id).quantidade == 90.0
            assert s.exec(select(MovimentoEstoque).where(MovimentoEstoque.movimento == "Estoque inicial")).first() is not None


def test_bootstrap_popula_catalogo_completo_idempotente():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine, select
    from fazenda.models import PrincipioAtivo, MedicamentoComercial
    from fazenda.rules.farmacia import bootstrap_farmacia
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        bootstrap_farmacia(s)
        bootstrap_farmacia(s)  # roda de novo: não pode duplicar
        pas = s.exec(select(PrincipioAtivo)).all()
        marcas = s.exec(select(MedicamentoComercial)).all()
        assert len(pas) == 38
        assert all(p.categoria_software for p in pas)   # todas com característica
        assert len(marcas) == 111
        mel = next(p for p in pas if p.nome == "Meloxicam")
        assert mel.categoria_software == "AINE" and mel.uso_principal
