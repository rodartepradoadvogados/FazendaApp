"""
Recria: vínculo de OcorrenciaClinica/JanelaPontoCritico com o catálogo Doenca
(decisão (b) do dono do produto), o motor de alerta do Ponto Crítico na
Agenda (decisão (a)) e o indicador de mastite via `doenca_id` (decisão (c)).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Doenca, Fazenda, JanelaPontoCritico, OcorrenciaClinica, SeedFlag,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules.recria_doenca import backfill_doenca_catalogo, resolver_ou_criar_doenca


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()
        # Catálogo global, como o seed real cria (fazenda.rules.farmacia_indicacoes_seed).
        s.add(Doenca(nome="Mastite", fazenda_id=None, tipo="doenca"))
        s.commit()

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
        permissoes = "sanidade,rebanho,agenda,parametros"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


# ---------------------------------------------------------------------------
# Backfill (decisão b): casa por nome com o catálogo, cria o que faltar.
# ---------------------------------------------------------------------------
class TestBackfillDoencaCatalogo:
    def test_casa_mastite_com_a_doenca_do_catalogo(self, client):
        _, engine = client
        with Session(engine) as s:
            mastite_id = s.exec(select(Doenca).where(Doenca.nome == "Mastite")).first().id
            # texto livre casa (sem acento/caixa) com o "Mastite" global.
            s.add(OcorrenciaClinica(fazenda_id=1, numero_matriz="101", doenca="mastite", data_ocorrencia=date(2026, 1, 1)))
            s.commit()

        with Session(engine) as s:
            backfill_doenca_catalogo(s)

        with Session(engine) as s:
            o = s.exec(select(OcorrenciaClinica).where(OcorrenciaClinica.numero_matriz == "101")).first()
            assert o.doenca_id == mastite_id
            assert o.doenca == "mastite"  # texto original preservado — nunca renomeado
            # nenhuma doença nova criada por causa do casamento.
            assert len(s.exec(select(Doenca).where(Doenca.nome.ilike("mastite"))).all()) == 1

    def test_cria_doenca_nova_da_fazenda_para_tpb_preservando_o_nome(self, client):
        _, engine = client
        with Session(engine) as s:
            s.add(JanelaPontoCritico(fazenda_id=1, doenca="TPB", dia_min=90, dia_max=100, dias_antecedencia=7))
            s.commit()

        with Session(engine) as s:
            backfill_doenca_catalogo(s)

        with Session(engine) as s:
            j = s.exec(select(JanelaPontoCritico).where(JanelaPontoCritico.doenca == "TPB")).first()
            assert j.doenca_id is not None
            nova = s.get(Doenca, j.doenca_id)
            assert nova.nome == "TPB"           # nome exato do texto livre, preservado
            assert nova.fazenda_id == 1         # catálogo DA FAZENDA dona do registro, não global

    def test_backfill_idempotente_nao_duplica_mesmo_rodando_de_novo(self, client):
        _, engine = client
        with Session(engine) as s:
            s.add(OcorrenciaClinica(fazenda_id=1, numero_matriz="101", doenca="TPB", data_ocorrencia=date(2026, 1, 1)))
            s.add(OcorrenciaClinica(fazenda_id=1, numero_matriz="102", doenca="tpb", data_ocorrencia=date(2026, 1, 2)))
            s.commit()

        with Session(engine) as s:
            backfill_doenca_catalogo(s)
        with Session(engine) as s:
            # Roda de novo sem a guarda do SeedFlag (simula reexecução da
            # rotina) — a query por doenca_id IS NULL já não acha nada.
            s.delete(s.get(SeedFlag, "recria_doenca_catalogo_backfill_v1"))
            s.commit()
        with Session(engine) as s:
            backfill_doenca_catalogo(s)

        with Session(engine) as s:
            tpbs = s.exec(select(Doenca).where(Doenca.nome.ilike("tpb"))).all()
            assert len(tpbs) == 1  # "TPB" e "tpb" casam entre si — 1 doença só, nunca duplica
            ocorrencias = s.exec(select(OcorrenciaClinica).where(OcorrenciaClinica.fazenda_id == 1)).all()
            assert all(o.doenca_id == tpbs[0].id for o in ocorrencias)

    def test_resolver_ou_criar_doenca_e_idempotente(self, client):
        """Chamar duas vezes para o mesmo nome/fazenda devolve o mesmo id, sem
        criar uma segunda linha no catálogo."""
        _, engine = client
        with Session(engine) as s:
            id1 = resolver_ou_criar_doenca(s, "Onfaloflebite", 1)
            id2 = resolver_ou_criar_doenca(s, "onfaloflebite", 1)
            assert id1 == id2
            assert len(s.exec(select(Doenca).where(Doenca.nome.ilike("onfaloflebite"))).all()) == 1


# ---------------------------------------------------------------------------
# Tarefa 3: criar janela com doenca_id grava o texto denormalizado junto.
# ---------------------------------------------------------------------------
class TestCriarJanelaComDoencaId:
    def test_criar_janela_com_doenca_id_grava_texto_do_catalogo(self, client):
        c, engine = client
        _como_fazenda(1)
        with Session(engine) as s:
            mastite_id = s.exec(select(Doenca).where(Doenca.nome == "Mastite")).first().id

        r = c.post("/recria/janelas", json={
            "doenca": "texto digitado qualquer", "doenca_id": mastite_id,
            "dia_min": 0, "dia_max": 5, "dias_antecedencia": 2,
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["doenca_id"] == mastite_id
        assert body["doenca"] == "Mastite"  # denormalizado do catálogo, não o texto digitado

        # E a leitura devolve os dois campos.
        listagem = c.get("/recria/janelas").json()
        achado = next(j for j in listagem if j["id"] == body["id"])
        assert achado["doenca_id"] == mastite_id
        assert achado["doenca"] == "Mastite"


# ---------------------------------------------------------------------------
# Tarefa 2: motor de alerta do Ponto Crítico na Agenda.
# ---------------------------------------------------------------------------
class TestAlertaPontoCriticoAgenda:
    def test_alerta_aparece_quando_ha_animal_na_faixa(self, client):
        c, engine = client
        _como_fazenda(1)
        data_ref = date(2026, 3, 1)
        with Session(engine) as s:
            s.add(JanelaPontoCritico(
                fazenda_id=1, doenca="Diarreia", dia_min=5, dia_max=20, dias_antecedencia=3, ativo=True,
            ))
            # idade em data_ref = 9 dias — dentro de [5-3, 20] = [2, 20].
            s.add(Animal(numero="301", data_nasc=date(2026, 2, 20), ativo=True, sexo="F", fazenda_id=1))
            s.commit()

        r = c.get("/agenda/", params={"data": data_ref.isoformat()})
        assert r.status_code == 200, r.text
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "ponto_critico_recria"]
        assert len(eventos) == 1
        assert "Diarreia" in eventos[0]["descricao"]
        assert "301" in eventos[0]["animais"]

    def test_alerta_nao_aparece_sem_animal_na_faixa(self, client):
        c, engine = client
        _como_fazenda(1)
        data_ref = date(2026, 3, 1)
        with Session(engine) as s:
            s.add(JanelaPontoCritico(
                fazenda_id=1, doenca="Diarreia", dia_min=5, dia_max=20, dias_antecedencia=3, ativo=True,
            ))
            # idade em data_ref = 200 dias — bem fora da janela.
            s.add(Animal(numero="302", data_nasc=date(2025, 8, 13), ativo=True, sexo="F", fazenda_id=1))
            s.commit()

        r = c.get("/agenda/", params={"data": data_ref.isoformat()})
        assert r.status_code == 200, r.text
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "ponto_critico_recria"]
        assert eventos == []

    def test_sem_janela_ativa_nao_ha_evento(self, client):
        c, engine = client
        _como_fazenda(1)
        data_ref = date(2026, 3, 1)
        with Session(engine) as s:
            s.add(JanelaPontoCritico(
                fazenda_id=1, doenca="Diarreia", dia_min=5, dia_max=20, dias_antecedencia=3, ativo=False,
            ))
            s.add(Animal(numero="303", data_nasc=date(2026, 2, 20), ativo=True, sexo="F", fazenda_id=1))
            s.commit()

        r = c.get("/agenda/", params={"data": data_ref.isoformat()})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "ponto_critico_recria"]
        assert eventos == []

    def test_alerta_respeita_fazenda(self, client):
        c, engine = client
        data_ref = date(2026, 3, 1)
        with Session(engine) as s:
            # Janela só da fazenda 1; animal dentro da faixa em CADA fazenda.
            s.add(JanelaPontoCritico(
                fazenda_id=1, doenca="Diarreia", dia_min=5, dia_max=20, dias_antecedencia=3, ativo=True,
            ))
            s.add(Animal(numero="401", data_nasc=date(2026, 2, 20), ativo=True, sexo="F", fazenda_id=1))
            s.add(Animal(numero="402", data_nasc=date(2026, 2, 20), ativo=True, sexo="F", fazenda_id=2))
            s.commit()

        # Fazenda 1: vê o alerta, só com o animal dela (401), nunca o da fazenda 2 (402).
        _como_fazenda(1)
        r1 = c.get("/agenda/", params={"data": data_ref.isoformat()})
        eventos1 = [e for e in r1.json()["eventos"] if e.get("tipo") == "ponto_critico_recria"]
        assert len(eventos1) == 1
        assert eventos1[0]["animais"] == ["401"]

        # Fazenda 2: sem janela cadastrada lá — nenhum alerta, mesmo tendo animal na faixa.
        _como_fazenda(2)
        r2 = c.get("/agenda/", params={"data": data_ref.isoformat()})
        eventos2 = [e for e in r2.json()["eventos"] if e.get("tipo") == "ponto_critico_recria"]
        assert eventos2 == []


# ---------------------------------------------------------------------------
# Tarefa 4: indicador de mastite conta pelo vínculo do catálogo.
# ---------------------------------------------------------------------------
class TestIndicadorMastitePorVinculo:
    def test_conta_por_doenca_id_e_mantem_fallback_de_texto_para_historico(self, client):
        c, engine = client
        _como_fazenda(1)
        with Session(engine) as s:
            mastite_id = s.exec(select(Doenca).where(Doenca.nome == "Mastite")).first().id
            s.add(Animal(numero="501", data_nasc=date(2024, 1, 1), ativo=True, sexo="F", fazenda_id=1))
            # Caso novo, já vinculado ao catálogo.
            s.add(OcorrenciaClinica(
                fazenda_id=1, numero_matriz="501", doenca="Mastite", doenca_id=mastite_id,
                data_ocorrencia=date(2026, 1, 1),
            ))
            # Caso histórico, nunca vinculado (backfill não rodou) — ainda
            # conta, pelo texto (fallback documentado no comentário do router).
            s.add(OcorrenciaClinica(
                fazenda_id=1, numero_matriz="501", doenca="Mastite clínica", doenca_id=None,
                data_ocorrencia=date(2026, 1, 5),
            ))
            # Doença completamente diferente — não deve contar.
            s.add(OcorrenciaClinica(
                fazenda_id=1, numero_matriz="501", doenca="Diarreia", doenca_id=None,
                data_ocorrencia=date(2026, 1, 10),
            ))
            s.commit()

        r = c.post("/indicadores/relatorio-personalizado", json={"parametros": ["numero_mastites"]})
        assert r.status_code == 200, r.text
        linhas = {l["numero"]: l for l in r.json()["linhas"]}
        assert linhas["501"]["numero_mastites"] == 2

    def test_nao_conta_doenca_id_de_outra_doenca_mesmo_com_mastite_no_texto(self, client):
        c, engine = client
        _como_fazenda(1)
        with Session(engine) as s:
            outra_id = resolver_ou_criar_doenca(s, "Mastite subclínica (variante)", 1)
            s.add(Animal(numero="502", data_nasc=date(2024, 1, 1), ativo=True, sexo="F", fazenda_id=1))
            # doenca_id aponta para OUTRA doença do catálogo — vale o vínculo,
            # não o texto (que também contém "mastite").
            s.add(OcorrenciaClinica(
                fazenda_id=1, numero_matriz="502", doenca="Mastite subclínica (variante)", doenca_id=outra_id,
                data_ocorrencia=date(2026, 1, 1),
            ))
            s.commit()

        r = c.post("/indicadores/relatorio-personalizado", json={"parametros": ["numero_mastites"]})
        linhas = {l["numero"]: l for l in r.json()["linhas"]}
        assert linhas["502"]["numero_mastites"] == 0
