"""
Testes do lançamento de diagnóstico (retoque) e sua entrada na agenda.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Servico


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
            s.add(Animal(numero="401", sit_rep="Ins.", ativo=True))
            s.add(Servico(numero_matriz="401", data_servico=date(2026, 6, 1), ult_ocorrencia=1))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


@pytest.fixture
def client_com_engine():
    """Variante que expõe o engine para testes que precisam inserir Servico
    extra diretamente no banco (matriz com mais de um serviço)."""
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
            s.add(Animal(numero="401", sit_rep="Ins.", ativo=True))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


class TestRegistrarDiagnostico:
    def test_marca_retoque(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        assert r.status_code == 200
        assert r.json()["retoque"] is True
        assert r.json()["diagnostico"] == "POSITIVO"

    def test_reconfirmada_desliga_retoque(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-20", "resultado": "reconfirmada",
        })
        assert r.json()["retoque"] is False
        assert r.json()["diagnostico"] == "POSITIVO"

    def test_matriz_sem_servico_da_404(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "999", "data_diagnostico": "2026-07-01", "resultado": "negativo",
        })
        assert r.status_code == 404

    def test_resultado_invalido_da_400(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "outra_coisa",
        })
        assert r.status_code == 400

    def test_indefinido_e_distinto_de_negativo(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "indefinido",
        })
        assert r.status_code == 200
        assert r.json()["diagnostico"] == "INDEFINIDO"

    def test_indefinido_ja_entra_marcado_para_retoque(self, client):
        # Regra definida pelo produtor: inconclusivo não é positivo, negativo
        # nem "em aberto" — é um estado próprio, e a única saída dele é
        # examinar de novo. Antes o retoque ficava False e a vaca dependia de
        # alguém lembrar de voltar nela; agora o lembrete cai na agenda
        # sozinho (agenda_engine.py só olha o flag, não o diagnóstico).
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "indefinido",
        })
        assert r.status_code == 200
        assert r.json()["retoque"] is True

    def test_metodo_cio_de_repasse_persistido(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "negativo",
            "metodo": "Cio de repasse",
        })
        assert r.status_code == 200
        assert r.json()["metodo_diagnostico"] == "Cio de repasse"
        assert r.json()["diagnostico"] == "NEGATIVO"

    def test_prefere_servico_em_aberto_mesmo_nao_sendo_o_mais_recente(self, client_com_engine):
        """Regressão: matriz com dois serviços — um antigo ainda em aberto (sem
        diagnóstico) e um mais recente já diagnosticado — deve gravar no que
        está em aberto, não cegamente no "mais recente por data"."""
        c, engine = client_com_engine
        with Session(engine) as s:
            s.add(Servico(numero_matriz="401", data_servico=date(2026, 5, 1)))  # em aberto
            s.add(Servico(numero_matriz="401", data_servico=date(2026, 6, 1),
                          diagnostico="POSITIVO", data_diagnostico=date(2026, 6, 25)))  # mais recente, já fechado
            s.commit()

        r = c.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "negativo",
        })
        assert r.status_code == 200
        assert r.json()["data_servico"] == "2026-05-01"  # gravou no serviço em aberto, não no mais recente

        with Session(engine) as s:
            fechado = s.exec(
                select(Servico).where(Servico.numero_matriz == "401", Servico.data_servico == date(2026, 6, 1))
            ).first()
            assert fechado.diagnostico == "POSITIVO"  # preservado — não foi sobrescrito


class TestRegistrarReconfirmacao:
    def test_prefere_servico_positivo_aguardando_mesmo_nao_sendo_o_mais_recente(self, client_com_engine):
        """Regressão: matriz com um serviço antigo positivo aguardando
        reconfirmação e um serviço mais recente ainda sem diagnóstico (ex.:
        novo ciclo após perda) — a reconfirmação deve gravar no antigo
        positivo, não cegamente no "mais recente por data"."""
        c, engine = client_com_engine
        with Session(engine) as s:
            s.add(Servico(numero_matriz="401", data_servico=date(2026, 3, 1),
                          diagnostico="POSITIVO"))  # aguardando reconfirmação
            s.add(Servico(numero_matriz="401", data_servico=date(2026, 6, 10)))  # mais recente, sem diagnóstico
            s.commit()

        r = c.post("/reproducao/reconfirmacao", json={
            "numero_matriz": "401", "data_reconfirmacao": "2026-07-01", "resultado": "positivo",
        })
        assert r.status_code == 200
        assert r.json()["data_servico"] == "2026-03-01"

        with Session(engine) as s:
            aberto = s.exec(
                select(Servico).where(Servico.numero_matriz == "401", Servico.data_servico == date(2026, 6, 10))
            ).first()
            assert aberto.data_reconfirmacao is None  # preservado — não foi tocado


class TestTerceiroLancamentoViraAborto:
    """3º lançamento sobre a mesma prenhez (toque + retoque já confirmados
    POSITIVO) não sobrescreve o toque — é interpretado como aborto."""

    def test_terceiro_lancamento_registra_aborto(self, client_com_engine):
        c, engine = client_com_engine
        with Session(engine) as s:
            s.add(Servico(
                numero_matriz="401", data_servico=date(2026, 3, 1),
                data_diagnostico=date(2026, 4, 1), diagnostico="POSITIVO",
                data_reconfirmacao=date(2026, 5, 1), diagnostico_reconfirmacao="POSITIVO",
            ))
            s.commit()

        r = c.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "negativo",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["aborto_detectado"] is True
        assert corpo["data_perda_prenhez"] == "2026-07-01"
        assert corpo["motivo_perda_prenhez"] == "aborto"
        # o toque original não foi sobrescrito pelo 3º lançamento
        assert corpo["data_diagnostico"] == "2026-04-01"
        assert corpo["diagnostico"] == "POSITIVO"

    def test_ja_com_perda_registrada_nao_reaborta(self, client_com_engine):
        """Reeditar um serviço que já tem perda de prenhez lançada não deve
        entrar de novo no ramo de aborto (evita loop de reescrita)."""
        c, engine = client_com_engine
        with Session(engine) as s:
            s.add(Servico(
                numero_matriz="401", data_servico=date(2026, 3, 1),
                data_diagnostico=date(2026, 4, 1), diagnostico="POSITIVO",
                data_reconfirmacao=date(2026, 5, 1), diagnostico_reconfirmacao="POSITIVO",
                data_perda_prenhez=date(2026, 6, 1), motivo_perda_prenhez="aborto",
            ))
            s.commit()

        r = c.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "negativo",
        })
        assert r.status_code == 200
        assert "aborto_detectado" not in r.json() or r.json()["aborto_detectado"] is not True

    def test_apenas_toque_sem_retoque_nao_vira_aborto(self, client):
        """Só o toque feito (sem retoque) — o 2º lançamento é o retoque normal,
        não um 3º lançamento; não deve virar aborto."""
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-20", "resultado": "reconfirmada",
        })
        assert r.status_code == 200
        assert not r.json().get("aborto_detectado")


class TestAbrirLactacao:
    def test_abre_lactacao_zera_del_dias(self, client_com_engine):
        c, engine = client_com_engine
        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "401")).first()
            animal.del_dias = 200
            s.add(animal)
            s.commit()

        r = c.post("/reproducao/animais/401/abrir-lactacao")
        assert r.status_code == 200
        assert r.json()["aberto"] is True

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "401")).first()
            assert animal.del_dias == 0

    def test_animal_inexistente_da_404(self, client):
        r = client.post("/reproducao/animais/999/abrir-lactacao")
        assert r.status_code == 404


class TestRetoqueNaAgenda:
    def test_entra_na_agenda_no_dia_do_proximo_servico(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        r = client.get("/agenda/", params={"data": "2026-07-01"})
        eventos = r.json()["eventos"]
        retoques = [e for e in eventos if e["numero_animal"] == "401" and "Retoque" in e["descricao"]]
        assert len(retoques) == 1
        # data_diagnostico (01/07) + dias_reinseminacao_referencia (22, media de 18-25) = 23/07
        assert retoques[0]["data"] == "2026-07-23"

    def test_sem_retoque_nao_aparece(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "reconfirmada",
        })
        r = client.get("/agenda/", params={"data": "2026-07-01"})
        eventos = r.json()["eventos"]
        assert not any("Retoque" in e["descricao"] for e in eventos)
