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
from fazenda.models import Animal, Lote, Parto, Servico


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

    def test_reconfirmada_grava_nos_campos_de_reconfirmacao_sem_apagar_o_toque(self, client):
        """Regressão (relato do produtor, ago/2026): selecionar "reconfirmada"
        em Lançamentos > Diagnóstico de gestação (ex.: a partir da Agenda do
        veterinário > Inseminadas 60+ dias) só desligava `retoque`, sem
        gravar `data_reconfirmacao`/`diagnostico_reconfirmacao` — a matriz
        nunca aparecia como reconfirmada em lugar nenhum (Agenda, roteiro,
        histórico) e ainda perdia a data do 1º toque, sobrescrita pela data
        da reconfirmação."""
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-20", "resultado": "reconfirmada",
        })
        corpo = r.json()
        assert corpo["data_diagnostico"] == "2026-07-01"  # 1º toque preservado, não sobrescrito
        assert corpo["data_reconfirmacao"] == "2026-07-20"
        assert corpo["diagnostico_reconfirmacao"] == "POSITIVO"

    def test_negativo_apos_retoque_grava_perda_na_reconfirmacao_sem_apagar_o_toque(self, client):
        """2º exame (reconfirmação) vindo negativo — a matriz perdeu a
        prenhez depois de já ter sido tocada positiva. Não pode sobrescrever
        o 1º toque (que foi um resultado real, diferente) com NEGATIVO."""
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-20", "resultado": "negativo",
        })
        corpo = r.json()
        assert corpo["diagnostico"] == "POSITIVO"  # 1º toque preservado
        assert corpo["data_diagnostico"] == "2026-07-01"
        assert corpo["diagnostico_reconfirmacao"] == "NEGATIVO"
        assert corpo["data_reconfirmacao"] == "2026-07-20"
        assert corpo["retoque"] is False

    def test_reconfirmada_sai_da_lista_de_reconfirmacao_e_entra_em_gestantes(self, client_com_engine):
        """Ponta a ponta: lançar "reconfirmada" pela tela de Diagnóstico de
        gestação (POST /diagnostico, não /reconfirmacao) precisa tirar a
        matriz da lista "Inseminadas 60+ dias — reconfirmação" e colocá-la em
        "vacas_gestantes" no roteiro do veterinário — mesma verificação feita
        pela Agenda do veterinário."""
        c, engine = client_com_engine
        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "401")).first()
            animal.categoria_abrev = "Vaca"
            s.add(animal)
            s.add(Servico(
                numero_matriz="401", data_servico=date(2026, 5, 1),
                data_diagnostico=date(2026, 6, 1), diagnostico="POSITIVO", retoque=True,
                ult_ocorrencia=1,
            ))
            s.commit()
        r = c.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-08-14", "resultado": "reconfirmada",
        })
        assert r.status_code == 200

        r2 = c.get("/reproducao/agenda-veterinario", params={"data": "2026-08-14"})
        listas = r2.json()["listas"]
        assert not any(a["numero_matriz"] == "401" for a in listas["inseminadas_60_mais"])
        assert any(a["numero_matriz"] == "401" for a in listas["vacas_gestantes"])

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

    def test_pariu_depois_do_servico_nao_gera_retoque(self, client_com_engine):
        """Regressão (matriz 131, relato do produtor ago/2026): vaca com
        retoque pendente que já pariu depois do serviço não deve continuar
        recebendo o alerta de retoque na Agenda — o parto já resolveu a
        gestação sozinho, com ou sem reconfirmação formal."""
        c, engine = client_com_engine
        with Session(engine) as s:
            s.add(Servico(
                numero_matriz="401", data_servico=date(2026, 4, 1),
                data_diagnostico=date(2026, 5, 1), diagnostico="POSITIVO",
                retoque=True, ult_ocorrencia=1,
            ))
            s.add(Parto(numero_matriz="401", data_parto=date(2026, 6, 19), ordem_parto=1))
            s.commit()
        r = c.get("/agenda/", params={"data": "2026-08-14"})
        eventos = r.json()["eventos"]
        assert not any(e["numero_animal"] == "401" and "Retoque" in e["descricao"] for e in eventos)

    def test_lote_pre_parto_nao_gera_retoque(self, client_com_engine):
        """Regressão (matrizes 145/429/430/432/433/435, relato do produtor
        ago/2026): vaca com retoque pendente já movida para um lote
        cadastrado com `pre_parto=True` não deve continuar recebendo o
        alerta de retoque — a mudança de lote já reconhece a gestação."""
        c, engine = client_com_engine
        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "401")).first()
            animal.grupo_primario = "09 - Pré-parto"
            s.add(animal)
            s.add(Lote(codigo="09", nome="Pré-parto", pre_parto=True))
            s.add(Servico(
                numero_matriz="401", data_servico=date(2026, 6, 1),
                data_diagnostico=date(2026, 7, 1), diagnostico="POSITIVO",
                retoque=True, ult_ocorrencia=1,
            ))
            s.commit()
        r = c.get("/agenda/", params={"data": "2026-08-14"})
        eventos = r.json()["eventos"]
        assert not any(e["numero_animal"] == "401" and "Retoque" in e["descricao"] for e in eventos)


class TestHistoricoDiagnosticosExpoeDatas:
    """Histórico > Reprodução > Diagnósticos pedia data do 1º toque
    (`data_diagnostico`) e da reconfirmação — `GET /reproducao/servicos`
    (consumido por `analisar_servicos`) só devolvia a data do SERVIÇO,
    nunca a do diagnóstico em si (pedido do produtor, set/2026)."""

    def test_data_diagnostico_aparece_no_historico(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "negativo",
        })
        r = client.get("/reproducao/servicos")
        assert r.status_code == 200
        servico = next(s for s in r.json()["servicos"] if s["numero"] == "401")
        assert servico["data_diagnostico"] == "2026-07-01"
        assert servico["data"] == "2026-06-01"  # data do serviço, distinta

    def test_reconfirmacao_tambem_aparece_no_historico(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        client.post("/reproducao/reconfirmacao", json={
            "numero_matriz": "401", "data_reconfirmacao": "2026-08-25", "resultado": "positivo",
        })
        r = client.get("/reproducao/servicos")
        servico = next(s for s in r.json()["servicos"] if s["numero"] == "401")
        assert servico["data_diagnostico"] == "2026-07-01"
        assert servico["data_reconfirmacao"] == "2026-08-25"
        assert servico["diagnostico_reconfirmacao"] == "POSITIVO"


class TestEditarReconfirmacaoPorPut:
    """`PUT /reproducao/servicos/{id}` precisa poder corrigir qualquer dado
    da linha de Diagnósticos, inclusive os campos da reconfirmação — antes só
    dava para corrigir o 1º toque (data_diagnostico/diagnostico)."""

    def test_edita_data_e_resultado_da_reconfirmacao(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        servico_id = client.get("/reproducao/servicos").json()["servicos"][0]["id"]
        r = client.put(f"/reproducao/servicos/{servico_id}", json={
            "data_reconfirmacao": "2026-09-04", "diagnostico_reconfirmacao": "negativo",
        })
        assert r.status_code == 200
        assert r.json()["data_reconfirmacao"] == "2026-09-04"
        assert r.json()["diagnostico_reconfirmacao"] == "NEGATIVO"
        # 1º toque preservado — a edição da reconfirmação não apaga o toque.
        assert r.json()["diagnostico"] == "POSITIVO"

    def test_diagnostico_reconfirmacao_invalido_da_400(self, client):
        servico_id = client.get("/reproducao/servicos").json()["servicos"][0]["id"]
        r = client.put(f"/reproducao/servicos/{servico_id}", json={"diagnostico_reconfirmacao": "talvez"})
        assert r.status_code == 400
