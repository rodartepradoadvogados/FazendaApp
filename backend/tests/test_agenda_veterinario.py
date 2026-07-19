"""
Testes da agenda/roteiro do veterinário do serviço — classificação do
rebanho em 11 listas.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, PesagemCorporal, Servico

HOJE = date(2026, 7, 8)

# Idade/peso "aptos" padrão para testes que não estão testando o gate em si.
IDADE_APTA = 24.0
PESO_APTO = 320.0


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


def _add_animal(engine, numero, categoria_abrev, sexo="F", eh_semen=False, ativo=True, idade_meses=None):
    with Session(engine) as s:
        s.add(Animal(numero=numero, categoria_abrev=categoria_abrev, sexo=sexo, eh_semen=eh_semen, ativo=ativo,
                      idade_meses=idade_meses))
        s.commit()


def _add_peso(engine, numero, peso):
    with Session(engine) as s:
        s.add(PesagemCorporal(numero_matriz=numero, data_pesagem=HOJE, peso_kg=peso))
        s.commit()


def _add_servico(engine, numero, dias_atras, **kwargs):
    with Session(engine) as s:
        s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), **kwargs))
        s.commit()


class TestExclusoes:
    def test_macho_nunca_entra(self, client):
        c, engine = client
        _add_animal(engine, "1", "Touro", sexo="M", idade_meses=IDADE_APTA)
        _add_peso(engine, "1", PESO_APTO)
        r = c.get("/reproducao/agenda-veterinario")
        assert all(a["numero_matriz"] != "1" for lst in r.json()["listas"].values() for a in lst)

    def test_bezerra_nunca_entra(self, client):
        c, engine = client
        _add_animal(engine, "2", "Bezerra", idade_meses=IDADE_APTA)
        _add_peso(engine, "2", PESO_APTO)
        r = c.get("/reproducao/agenda-veterinario")
        assert all(a["numero_matriz"] != "2" for lst in r.json()["listas"].values() for a in lst)

    def test_novilha_abaixo_300kg_nao_entra_em_novilhas_aptas_vazias(self, client):
        # Gate de aptidão (#364): restrito a "novilhas_aptas_vazias" — sem
        # servico e sem atingir peso_apta_min, a novilha cai em
        # pendentes_classificacao (não fica mais invisível em todo lugar).
        c, engine = client
        _add_animal(engine, "3", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "3", 200)
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        assert all(a["numero_matriz"] != "3" for a in listas["novilhas_aptas_vazias"])
        assert any(a["numero_matriz"] == "3" for a in listas["pendentes_classificacao"])

    def test_vaca_com_peso_mas_idade_insuficiente_fica_pendente(self, client):
        # Gate de aptidão só vale para novilha ("novilhas_aptas_vazias") — para
        # vaca sem serviço, idade não muda nada: ela cai em pendentes_classificacao.
        c, engine = client
        _add_animal(engine, "4", "Vaca", idade_meses=10)
        _add_peso(engine, "4", PESO_APTO)
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        assert any(a["numero_matriz"] == "4" for a in listas["pendentes_classificacao"])

    def test_vaca_com_idade_mas_peso_insuficiente_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "5", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "5", 250)
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        assert any(a["numero_matriz"] == "5" for a in listas["pendentes_classificacao"])

    def test_sem_idade_registrada_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "6", "Vaca")
        _add_peso(engine, "6", PESO_APTO)
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        assert any(a["numero_matriz"] == "6" for a in listas["pendentes_classificacao"])


class TestInseminadas:
    def test_1_a_29_dias(self, client):
        c, engine = client
        _add_animal(engine, "10", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "10", PESO_APTO)
        _add_servico(engine, "10", 10)
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "10" for a in r.json()["listas"]["inseminadas_1_29"])

    def test_30_a_59_sem_toque_fica_atrasada(self, client):
        c, engine = client
        _add_animal(engine, "11", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "11", PESO_APTO)
        _add_servico(engine, "11", 40)
        r = c.get("/reproducao/agenda-veterinario")
        item = next(a for a in r.json()["listas"]["inseminadas_30_59"] if a["numero_matriz"] == "11")
        assert item["atrasada"] is True

    def test_60_mais_sem_reconfirmacao_fica_atrasada(self, client):
        c, engine = client
        _add_animal(engine, "12", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "12", PESO_APTO)
        _add_servico(engine, "12", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        item = next(a for a in r.json()["listas"]["inseminadas_60_mais"] if a["numero_matriz"] == "12")
        assert item["atrasada"] is True
        assert item["tocada"] is True

    def test_gestante_confirmada_sai_das_listas_1_2_3(self, client):
        c, engine = client
        _add_animal(engine, "13", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "13", PESO_APTO)
        _add_servico(engine, "13", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=5), diagnostico_reconfirmacao="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        assert not any(a["numero_matriz"] == "13" for a in listas["inseminadas_60_mais"])
        assert any(a["numero_matriz"] == "13" for a in listas["vacas_gestantes"])


class TestNovilhas:
    def test_apta_vazia_300kg_sem_servico(self, client):
        c, engine = client
        _add_animal(engine, "20", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "20", 320)
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "20" for a in r.json()["listas"]["novilhas_aptas_vazias"])

    def test_novilha_gestante_confirmada(self, client):
        c, engine = client
        _add_animal(engine, "22", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "22", 350)
        _add_servico(engine, "22", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=5), diagnostico_reconfirmacao="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "22" for a in r.json()["listas"]["novilhas_gestantes"])

    def test_inseminada_nao_reconfirmada_nao_entra_em_gestantes(self, client):
        c, engine = client
        _add_animal(engine, "23", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "23", 350)
        _add_servico(engine, "23", 40, data_diagnostico=HOJE - timedelta(days=10), diagnostico="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        assert not any(a["numero_matriz"] == "23" for a in r.json()["listas"]["novilhas_gestantes"])


class TestVerificarAptidao:
    """Critério próprio: >=280kg, >=15 meses, nunca inseminada/coberta."""

    def test_280kg_15_meses_sem_servico_entra(self, client):
        c, engine = client
        _add_animal(engine, "21", "Novilha", idade_meses=15)
        _add_peso(engine, "21", 280)
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "21" for a in r.json()["listas"]["verificar_aptidao"])

    def test_abaixo_280kg_nao_entra(self, client):
        c, engine = client
        _add_animal(engine, "24", "Novilha", idade_meses=15)
        _add_peso(engine, "24", 270)
        r = c.get("/reproducao/agenda-veterinario")
        assert not any(a["numero_matriz"] == "24" for a in r.json()["listas"]["verificar_aptidao"])

    def test_abaixo_15_meses_nao_entra(self, client):
        c, engine = client
        _add_animal(engine, "25", "Novilha", idade_meses=10)
        _add_peso(engine, "25", 300)
        r = c.get("/reproducao/agenda-veterinario")
        assert not any(a["numero_matriz"] == "25" for a in r.json()["listas"]["verificar_aptidao"])

    def test_ja_teve_servico_nao_entra(self, client):
        c, engine = client
        _add_animal(engine, "26", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "26", 320)
        _add_servico(engine, "26", 5)
        r = c.get("/reproducao/agenda-veterinario")
        assert not any(a["numero_matriz"] == "26" for a in r.json()["listas"]["verificar_aptidao"])


class TestPreParto:
    def test_gestante_31_a_60_dias_para_parto(self, client):
        c, engine = client
        _add_animal(engine, "30", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "30", PESO_APTO)
        # gestação de 283 dias; faltando 45 dias -> serviço há 238 dias
        _add_servico(engine, "30", 238, data_diagnostico=HOJE - timedelta(days=200), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=170), diagnostico_reconfirmacao="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "30" for a in r.json()["listas"]["verificar_pre_parto"])


class TestPendentesClassificacao:
    def test_vaca_sem_servico_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "40", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "40", PESO_APTO)
        r = c.get("/reproducao/agenda-veterinario")
        item = next(a for a in r.json()["listas"]["pendentes_classificacao"] if a["numero_matriz"] == "40")
        assert "motivo" in item and item["motivo"]

    def test_novilha_sem_peso_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "41", "Novilha", idade_meses=IDADE_APTA)
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        assert all(a["numero_matriz"] != "41" for a in listas["novilhas_aptas_vazias"])
        assert any(a["numero_matriz"] == "41" for a in listas["pendentes_classificacao"])


class TestVaziasPorDiagnostico:
    def test_negativo_no_toque_vai_para_lista_propria(self, client):
        c, engine = client
        _add_animal(engine, "50", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "50", PESO_APTO)
        _add_servico(engine, "50", 40, data_diagnostico=HOJE - timedelta(days=10), diagnostico="NEGATIVO")
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        item = next(a for a in listas["vazias_por_diagnostico"] if a["numero_matriz"] == "50")
        assert "negativo" in item["motivo"].lower()
        assert not any(a["numero_matriz"] == "50" for a in listas["pendentes_classificacao"])

    def test_perda_de_prenhez_vai_para_lista_propria(self, client):
        c, engine = client
        _add_animal(engine, "51", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "51", PESO_APTO)
        _add_servico(engine, "51", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=5), diagnostico_reconfirmacao="NEGATIVO")
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        item = next(a for a in listas["vazias_por_diagnostico"] if a["numero_matriz"] == "51")
        assert "perda" in item["motivo"].lower()
        assert not any(a["numero_matriz"] == "51" for a in listas["pendentes_classificacao"])


class TestUltimoDiagnostico:
    """#488 — "último DG" da matriz + envio por e-mail (Resend, mockado)."""

    def test_ultimo_diagnostico_sem_servico_devolve_none(self, client):
        c, engine = client
        r = c.get("/reproducao/animais/999/ultimo-diagnostico")
        assert r.status_code == 200
        assert r.json() is None

    def test_ultimo_diagnostico_devolve_servico_mais_recente(self, client):
        c, engine = client
        _add_servico(engine, "60", 90, data_diagnostico=HOJE - timedelta(days=60), diagnostico="NEGATIVO")
        _add_servico(engine, "60", 20, data_diagnostico=HOJE - timedelta(days=5), diagnostico="POSITIVO")
        r = c.get("/reproducao/animais/60/ultimo-diagnostico")
        assert r.status_code == 200
        assert r.json()["diagnostico"] == "POSITIVO"

    def test_enviar_diagnostico_sem_destinatario_da_erro(self, client):
        c, engine = client
        _add_servico(engine, "61", 20, data_diagnostico=HOJE - timedelta(days=5), diagnostico="POSITIVO")
        r = c.post("/reproducao/animais/61/diagnostico/enviar", json={"destinatario": "  "})
        assert r.status_code == 400

    def test_enviar_diagnostico_sem_servico_da_404(self, client):
        c, engine = client
        r = c.post("/reproducao/animais/999/diagnostico/enviar", json={"destinatario": "a@b.com"})
        assert r.status_code == 404

    def test_enviar_diagnostico_sem_dg_lancado_da_erro(self, client):
        c, engine = client
        _add_servico(engine, "62", 5)
        r = c.post("/reproducao/animais/62/diagnostico/enviar", json={"destinatario": "a@b.com"})
        assert r.status_code == 400
        assert "diagnóstico" in r.json()["detail"].lower()

    def test_enviar_diagnostico_sem_resend_configurado_da_erro_claro(self, client):
        c, engine = client
        _add_servico(engine, "63", 20, data_diagnostico=HOJE - timedelta(days=5), diagnostico="POSITIVO")
        r = c.post("/reproducao/animais/63/diagnostico/enviar", json={"destinatario": "a@b.com"})
        assert r.status_code == 400
        assert "RESEND_API_KEY" in r.json()["detail"]

    def test_enviar_diagnostico_com_envio_mockado(self, client, monkeypatch):
        c, engine = client
        from fazenda.api.routers import reproducao as reproducao_router
        chamadas = []
        monkeypatch.setattr(
            reproducao_router, "enviar_email",
            lambda destinatario, assunto, corpo_html, anexo_nome=None, anexo_bytes=None: chamadas.append(destinatario),
        )
        _add_servico(engine, "64", 20, data_diagnostico=HOJE - timedelta(days=5), diagnostico="POSITIVO",
                     metodo_diagnostico="Ultrassom")
        r = c.post("/reproducao/animais/64/diagnostico/enviar", json={"destinatario": "vet@exemplo.com"})
        assert r.status_code == 200 and r.json() == {"enviado": True}
        assert chamadas == ["vet@exemplo.com"]


class TestDataReferenciaProjetada:
    """#490 — data de referência opcional (?data=) simula um cenário
    projetado (ex.: a data da próxima visita do veterinário), recalculando a
    classificação como se aquela fosse "hoje"."""

    def test_sem_parametro_usa_hoje_real_e_nao_marca_projetado(self, client):
        c, engine = client
        r = c.get("/reproducao/agenda-veterinario")
        corpo = r.json()
        assert corpo["data_referencia"] == date.today().isoformat()
        assert corpo["projetado"] is False

    def test_com_data_futura_marca_projetado_e_usa_a_data_informada(self, client):
        c, engine = client
        futura = date.today() + timedelta(days=15)
        r = c.get(f"/reproducao/agenda-veterinario?data={futura.isoformat()}")
        corpo = r.json()
        assert corpo["data_referencia"] == futura.isoformat()
        assert corpo["projetado"] is True

    def test_data_projetada_recalcula_a_classificacao(self, client):
        c, engine = client
        _add_animal(engine, "70", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "70", PESO_APTO)
        base = date(2026, 1, 1)
        with Session(engine) as s:
            s.add(Servico(numero_matriz="70", data_servico=base))
            s.commit()

        r10 = c.get(f"/reproducao/agenda-veterinario?data={(base + timedelta(days=10)).isoformat()}")
        listas10 = r10.json()["listas"]
        assert any(a["numero_matriz"] == "70" for a in listas10["inseminadas_1_29"])
        assert not any(a["numero_matriz"] == "70" for a in listas10["inseminadas_30_59"])

        r40 = c.get(f"/reproducao/agenda-veterinario?data={(base + timedelta(days=40)).isoformat()}")
        listas40 = r40.json()["listas"]
        assert any(a["numero_matriz"] == "70" for a in listas40["inseminadas_30_59"])
        assert not any(a["numero_matriz"] == "70" for a in listas40["inseminadas_1_29"])
