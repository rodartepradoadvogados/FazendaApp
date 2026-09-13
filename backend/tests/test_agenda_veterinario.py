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
from fazenda.models import Animal, Lote, Parto, PesagemCorporal, Servico

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


def _add_animal(engine, numero, categoria_abrev, sexo="F", eh_semen=False, ativo=True, idade_meses=None,
                 grupo_primario=None):
    with Session(engine) as s:
        s.add(Animal(numero=numero, categoria_abrev=categoria_abrev, sexo=sexo, eh_semen=eh_semen, ativo=ativo,
                      idade_meses=idade_meses, grupo_primario=grupo_primario))
        s.commit()


def _add_peso(engine, numero, peso):
    with Session(engine) as s:
        s.add(PesagemCorporal(numero_matriz=numero, data_pesagem=HOJE, peso_kg=peso))
        s.commit()


def _add_servico(engine, numero, dias_atras, **kwargs):
    with Session(engine) as s:
        s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), **kwargs))
        s.commit()


def _add_parto(engine, numero, dias_atras, ordem_parto=1):
    with Session(engine) as s:
        s.add(Parto(numero_matriz=numero, data_parto=HOJE - timedelta(days=dias_atras), ordem_parto=ordem_parto))
        s.commit()


def _add_lote_pre_parto(engine, codigo, nome):
    with Session(engine) as s:
        s.add(Lote(codigo=codigo, nome=nome, pre_parto=True))
        s.commit()


class TestExclusoes:
    def test_macho_nunca_entra(self, client):
        c, engine = client
        _add_animal(engine, "1", "Touro", sexo="M", idade_meses=IDADE_APTA)
        _add_peso(engine, "1", PESO_APTO)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        assert all(a["numero_matriz"] != "1" for lst in r.json()["listas"].values() for a in lst)

    def test_bezerra_nunca_entra(self, client):
        c, engine = client
        _add_animal(engine, "2", "Bezerra", idade_meses=IDADE_APTA)
        _add_peso(engine, "2", PESO_APTO)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        assert all(a["numero_matriz"] != "2" for lst in r.json()["listas"].values() for a in lst)

    def test_novilha_abaixo_300kg_nao_entra_em_novilhas_aptas_vazias(self, client):
        # Gate de aptidão (#364): restrito a "novilhas_aptas_vazias" — sem
        # servico e sem atingir peso_apta_min, a novilha cai em
        # pendentes_classificacao (não fica mais invisível em todo lugar).
        c, engine = client
        _add_animal(engine, "3", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "3", 200)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert all(a["numero_matriz"] != "3" for a in listas["novilhas_aptas_vazias"])
        assert any(a["numero_matriz"] == "3" for a in listas["pendentes_classificacao"])

    def test_vaca_com_peso_mas_idade_insuficiente_fica_pendente(self, client):
        # Gate de aptidão só vale para novilha ("novilhas_aptas_vazias") — para
        # vaca sem serviço, idade não muda nada: ela cai em pendentes_classificacao.
        c, engine = client
        _add_animal(engine, "4", "Vaca", idade_meses=10)
        _add_peso(engine, "4", PESO_APTO)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert any(a["numero_matriz"] == "4" for a in listas["pendentes_classificacao"])

    def test_vaca_com_idade_mas_peso_insuficiente_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "5", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "5", 250)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert any(a["numero_matriz"] == "5" for a in listas["pendentes_classificacao"])

    def test_sem_idade_registrada_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "6", "Vaca")
        _add_peso(engine, "6", PESO_APTO)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert any(a["numero_matriz"] == "6" for a in listas["pendentes_classificacao"])


class TestInseminadas:
    def test_1_a_29_dias(self, client):
        c, engine = client
        _add_animal(engine, "10", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "10", PESO_APTO)
        _add_servico(engine, "10", 10)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        assert any(a["numero_matriz"] == "10" for a in r.json()["listas"]["inseminadas_1_29"])

    def test_30_a_59_sem_toque_fica_atrasada(self, client):
        c, engine = client
        _add_animal(engine, "11", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "11", PESO_APTO)
        _add_servico(engine, "11", 40)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        item = next(a for a in r.json()["listas"]["inseminadas_30_59"] if a["numero_matriz"] == "11")
        assert item["atrasada"] is True

    def test_60_mais_sem_reconfirmacao_fica_atrasada(self, client):
        c, engine = client
        _add_animal(engine, "12", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "12", PESO_APTO)
        _add_servico(engine, "12", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO")
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        item = next(a for a in r.json()["listas"]["inseminadas_60_mais"] if a["numero_matriz"] == "12")
        assert item["atrasada"] is True
        assert item["tocada"] is True

    def test_gestante_confirmada_sai_das_listas_1_2_3(self, client):
        c, engine = client
        _add_animal(engine, "13", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "13", PESO_APTO)
        _add_servico(engine, "13", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=5), diagnostico_reconfirmacao="POSITIVO")
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert not any(a["numero_matriz"] == "13" for a in listas["inseminadas_60_mais"])
        assert any(a["numero_matriz"] == "13" for a in listas["vacas_gestantes"])

    def test_pariu_depois_do_servico_sai_da_reconfirmacao_mesmo_sem_reconfirmar(self, client):
        """Regressão (matriz 131, relato do produtor ago/2026): vaca tocada
        positiva, NUNCA reconfirmada formalmente, mas que já pariu — o parto
        prova a gestação sozinho; ela não deve continuar cobrada para
        reconfirmar um serviço já resolvido, e sim aparecer como "precisa de
        novo serviço" (voltou pro ciclo, aguardando IA)."""
        c, engine = client
        _add_animal(engine, "131", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "131", PESO_APTO)
        _add_servico(engine, "131", 300, data_diagnostico=HOJE - timedelta(days=270), diagnostico="POSITIVO")
        _add_parto(engine, "131", 56)  # pariu depois do serviço, antes de hoje
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert not any(a["numero_matriz"] == "131" for a in listas["inseminadas_60_mais"])
        assert not any(a["numero_matriz"] == "131" for a in listas["vacas_gestantes"])
        assert any(a["numero_matriz"] == "131" for a in listas["vazias_por_diagnostico"])

    def test_lote_pre_parto_sai_da_reconfirmacao_mesmo_sem_reconfirmar(self, client):
        """Regressão (matrizes 145/429/430/432/433/435, relato do produtor
        ago/2026): vaca tocada positiva, ainda sem reconfirmação formal, mas
        já movida para um lote cadastrado com `pre_parto=True` — a mudança de
        lote já reconhece a gestação como certa; ela não deve continuar
        cobrada para reconfirmar."""
        c, engine = client
        _add_lote_pre_parto(engine, "09", "Pré-parto")
        _add_animal(engine, "145", "Vaca", idade_meses=IDADE_APTA, grupo_primario="09 - Pré-parto")
        _add_peso(engine, "145", PESO_APTO)
        _add_servico(engine, "145", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert not any(a["numero_matriz"] == "145" for a in listas["inseminadas_60_mais"])
        assert any(a["numero_matriz"] == "145" for a in listas["vacas_gestantes"])


class TestNovilhas:
    def test_apta_vazia_300kg_sem_servico(self, client):
        c, engine = client
        _add_animal(engine, "20", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "20", 320)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        assert any(a["numero_matriz"] == "20" for a in r.json()["listas"]["novilhas_aptas_vazias"])

    def test_novilha_gestante_confirmada(self, client):
        c, engine = client
        _add_animal(engine, "22", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "22", 350)
        _add_servico(engine, "22", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=5), diagnostico_reconfirmacao="POSITIVO")
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        assert any(a["numero_matriz"] == "22" for a in r.json()["listas"]["novilhas_gestantes"])

    def test_novilha_toque_positivo_ja_confirma_sem_precisar_de_reconfirmacao(self, client):
        """Novilha (nunca pariu) dispensa o 2º exame de reconfirmação nesta
        fazenda — 1º toque positivo já é gestante confirmada (ver #657)."""
        c, engine = client
        _add_animal(engine, "23", "Novilha", idade_meses=IDADE_APTA)
        _add_peso(engine, "23", 350)
        _add_servico(engine, "23", 40, data_diagnostico=HOJE - timedelta(days=10), diagnostico="POSITIVO")
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        assert any(a["numero_matriz"] == "23" for a in r.json()["listas"]["novilhas_gestantes"])


class TestPreParto:
    def test_gestante_0_a_30_dias_para_parto(self, client):
        c, engine = client
        _add_animal(engine, "30", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "30", PESO_APTO)
        # gestação de referência 288 dias; faltando 20 dias -> serviço há 268 dias.
        # Janela real de pré-parto: últimos 30 dias antes do parto (vem DEPOIS
        # do período seco/Secagem, que é 31-60 dias antes — ver o teste abaixo
        # e fazenda.rules.parametros.pre_parto_max).
        _add_servico(engine, "30", 268, data_diagnostico=HOJE - timedelta(days=200), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=170), diagnostico_reconfirmacao="POSITIVO")
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        assert any(a["numero_matriz"] == "30" for a in r.json()["listas"]["verificar_pre_parto"])

    def test_gestante_31_a_60_dias_para_parto_nao_e_pre_parto(self, client):
        c, engine = client
        _add_animal(engine, "31", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "31", PESO_APTO)
        # gestação de referência 288 dias; faltando 45 dias -> serviço há 243 dias.
        # 45 dias para o parto é a janela do período seco/Secagem, não de
        # pré-parto — não deve entrar em "verificar_pre_parto".
        _add_servico(engine, "31", 243, data_diagnostico=HOJE - timedelta(days=200), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=170), diagnostico_reconfirmacao="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        assert not any(a["numero_matriz"] == "31" for a in r.json()["listas"]["verificar_pre_parto"])


class TestPendentesClassificacao:
    def test_vaca_sem_servico_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "40", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "40", PESO_APTO)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        item = next(a for a in r.json()["listas"]["pendentes_classificacao"] if a["numero_matriz"] == "40")
        assert "motivo" in item and item["motivo"]

    def test_novilha_sem_peso_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "41", "Novilha", idade_meses=IDADE_APTA)
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert all(a["numero_matriz"] != "41" for a in listas["novilhas_aptas_vazias"])
        assert any(a["numero_matriz"] == "41" for a in listas["pendentes_classificacao"])


class TestVaziasPorDiagnostico:
    def test_negativo_no_toque_vai_para_lista_propria(self, client):
        c, engine = client
        _add_animal(engine, "50", "Vaca", idade_meses=IDADE_APTA)
        _add_peso(engine, "50", PESO_APTO)
        _add_servico(engine, "50", 40, data_diagnostico=HOJE - timedelta(days=10), diagnostico="NEGATIVO")
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
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
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
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
        # Este teste testa exatamente o caso SEM "data" (o default do endpoint
        # é date.today() real, ver #490) — não pode receber o parâmetro, senão
        # deixa de testar o comportamento padrão que o nome do teste descreve.
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


class TestProximaVisitaReprodutivaSugerida:
    """#571 — a "Agenda Reprodutiva" expõe último serviço/próxima visita
    sugerida (último serviço do rebanho + intervalo do parâmetro), usada pelo
    seletor "Data atual"/"Projeção" no front. Intervalo 0 desliga a sugestão."""

    def test_sem_nenhum_servico_nao_ha_sugestao(self, client):
        c, engine = client
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        corpo = r.json()
        assert corpo["ultimo_servico"] is None
        assert corpo["proxima_visita_reprodutiva"] is None

    def test_com_servico_sugere_ultimo_servico_mais_intervalo_padrao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Servico(numero_matriz="80", data_servico=date(2026, 7, 1)))
            s.commit()
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        corpo = r.json()
        assert corpo["ultimo_servico"] == "2026-07-01"
        assert corpo["intervalo_visita_reprodutiva"] == 21
        assert corpo["proxima_visita_reprodutiva"] == "2026-07-22"

    def test_intervalo_zero_desliga_a_sugestao(self, client, monkeypatch):
        # get_param() lê do engine real compartilhado entre testes (não do
        # engine isolado do fixture), então mockar a função direto evita
        # sujar o parâmetro global para os outros testes da suíte.
        monkeypatch.setattr("fazenda.rules.parametros.intervalo_visita_reprodutiva", lambda: 0)
        c, engine = client
        with Session(engine) as s:
            s.add(Servico(numero_matriz="80", data_servico=date(2026, 7, 1)))
            s.commit()
        # data=HOJE fixa a data de referência do endpoint (default é date.today()
        # real, ver #490) — sem isso os testes de janela de dias (1-29/30-59/
        # pré-parto) driftam e quebram conforme o calendário real avança.
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        corpo = r.json()
        assert corpo["ultimo_servico"] == "2026-07-01"
        assert corpo["intervalo_visita_reprodutiva"] == 0
        assert corpo["proxima_visita_reprodutiva"] is None


class TestNovilhaAtrasadaNaListaDoVeterinario:
    """A lista "novilhas aptas vazias" juntava num balde só a novilha que
    acabou de ficar apta e a que está há um ano esperando serviço — o
    veterinário não via diferença entre as duas. O gate de idade/peso é
    reimplementado à mão neste módulo (idade_apta/peso_apta locais), então
    ele não herdava sozinho o ATRASADA que o motor passou a devolver para
    novilha nulípara (parâmetro idade_max_1a_cobertura_meses, 16 meses)."""

    def test_marca_atrasada_so_quem_passou_da_idade_maxima(self, client):
        c, engine = client
        # 15,5 meses: já passou do piso de aptidão (15) e ainda não do teto (16).
        _add_animal(engine, "70", "Novilha", idade_meses=15.5)
        _add_peso(engine, "70", PESO_APTO)
        # 24 meses: muito além do teto e continua vazia.
        _add_animal(engine, "71", "Novilha", idade_meses=24.0)
        _add_peso(engine, "71", PESO_APTO)
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        lista = {a["numero_matriz"]: a for a in r.json()["listas"]["novilhas_aptas_vazias"]}
        assert set(lista) == {"70", "71"}
        assert lista["70"]["atrasada"] is False
        assert lista["71"]["atrasada"] is True

    def test_atrasadas_vem_primeiro_na_lista(self, client):
        c, engine = client
        # Inseridas na ordem "recém-apta antes da atrasada" de propósito: sem a
        # ordenação, a atrasada sairia no fim da lista da visita.
        for numero, idade in (("72", 15.2), ("73", 15.4), ("74", 30.0), ("75", 40.0)):
            _add_animal(engine, numero, "Novilha", idade_meses=idade)
            _add_peso(engine, numero, PESO_APTO)
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        lista = r.json()["listas"]["novilhas_aptas_vazias"]
        assert [a["numero_matriz"] for a in lista] == ["74", "75", "72", "73"]
        assert [a["atrasada"] for a in lista] == [True, True, False, False]

    def test_novilha_inseminada_nao_entra_na_lista(self, client):
        # Sentinela: a marca não pode "puxar" ninguém para a lista — só
        # descreve quem já estava nela (vazia + apta).
        c, engine = client
        _add_animal(engine, "76", "Novilha", idade_meses=30.0)
        _add_peso(engine, "76", PESO_APTO)
        _add_servico(engine, "76", 10)
        r = c.get("/reproducao/agenda-veterinario", params={"data": HOJE.isoformat()})
        listas = r.json()["listas"]
        assert all(a["numero_matriz"] != "76" for a in listas["novilhas_aptas_vazias"])
        assert any(a["numero_matriz"] == "76" for a in listas["inseminadas_1_29"])
