"""
Eventos de vida adicionais do calendário sanitário — desmama, mudança para
recria, inseminação, gestação confirmada e mudança para pré-parto — usados
como gatilho no cadastro de evento sanitário (por evento) e no relatório
"quais animais entrarão em determinado calendário sanitário".
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, CategoriaManejo, Servico


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


HOJE = date.today()


def _agenda_sanidade(c) -> list[dict]:
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    return [e for e in r.json()["eventos"] if e.get("tipo") == "evento_sanitario"]


class TestGatilhosNovos:
    def test_desmama_usa_cadastro_de_categorias(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(CategoriaManejo(nome="Aleitamento", dia_min=0, dia_max=60, ordem=0))
            s.add(CategoriaManejo(nome="Recria 1", dia_min=61, dia_max=200, ordem=1))
            s.add(Animal(numero="801", data_nasc=HOJE - timedelta(days=60), sexo="F"))
            s.commit()
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vermífugo na desmama", "tipo_agendamento": "evento", "gatilho": "desmama",
            "produto_padrao": "Ivermectina", "dose_padrao": 5, "unidade_padrao": "ml",
        })
        assert r.status_code == 200, r.text
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "801"]
        assert len(meus) == 1

    def test_mudanca_recria_no_dia_seguinte_ao_fim_do_aleitamento(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(CategoriaManejo(nome="Aleitamento", dia_min=0, dia_max=60, ordem=0))
            s.add(CategoriaManejo(nome="Recria 1", dia_min=61, dia_max=200, ordem=1))
            s.add(Animal(numero="802", data_nasc=HOJE - timedelta(days=61), sexo="F"))
            s.commit()
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Exame na entrada da recria", "tipo_agendamento": "evento", "gatilho": "mudanca_recria",
        })
        assert r.status_code == 200, r.text
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "802"]
        assert len(meus) == 1

    def test_inseminacao_gera_evento_na_data_do_servico(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="803", data_nasc=HOJE - timedelta(days=800), sexo="F"))
            s.add(Servico(numero_matriz="803", data_servico=HOJE))
            s.commit()
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Exame pós-inseminação", "tipo_agendamento": "evento", "gatilho": "inseminacao",
        })
        assert r.status_code == 200, r.text
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "803"]
        assert len(meus) == 1

    def test_gestacao_confirmada_usa_data_diagnostico(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="804", data_nasc=HOJE - timedelta(days=800), sexo="F"))
            s.add(Servico(numero_matriz="804", data_servico=HOJE - timedelta(days=35), diagnostico="POSITIVO", data_diagnostico=HOJE))
            s.commit()
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina de gestante", "tipo_agendamento": "evento", "gatilho": "gestacao_confirmada",
        })
        assert r.status_code == 200, r.text
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "804"]
        assert len(meus) == 1

    def test_mudanca_pre_parto_antes_do_parto_previsto(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="805", data_nasc=HOJE - timedelta(days=900), sexo="F", raca="Holandês"))
            # Serviço positivo há 250 dias — parto previsto em ~30 dias (280 - 250),
            # dentro da janela de pré-parto (padrão pre_parto_max ~35-45 dias).
            s.add(Servico(numero_matriz="805", data_servico=HOJE - timedelta(days=250), raca_matriz="Holandês", diagnostico="POSITIVO"))
            s.commit()
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina pré-parto (evento)", "tipo_agendamento": "evento", "gatilho": "mudanca_pre_parto",
        })
        assert r.status_code == 200, r.text
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "805"]
        assert len(meus) == 1


class TestRelatorioEventosVida:
    def test_lista_vocabulario_de_gatilhos(self, client):
        c, _ = client
        r = c.get("/sanidade/calendario/eventos-vida")
        assert r.status_code == 200, r.text
        gatilhos = {item["gatilho"] for item in r.json()}
        assert {"desmama", "mudanca_recria", "inseminacao", "gestacao_confirmada", "mudanca_pre_parto"} <= gatilhos

    def test_relatorio_por_gatilho_avulso(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="806", data_nasc=HOJE - timedelta(days=800), sexo="F"))
            s.add(Servico(numero_matriz="806", data_servico=HOJE))
            s.commit()
        r = c.get("/sanidade/calendario/relatorio-eventos-vida", params={"gatilho": "inseminacao"})
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["gatilho"] == "inseminacao"
        numeros = {a["numero_matriz"] for a in dados["animais"]}
        assert "806" in numeros

    def test_relatorio_por_evento_sanitario_ja_cadastrado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="807", data_nasc=HOJE - timedelta(days=800), sexo="F"))
            s.add(Servico(numero_matriz="807", data_servico=HOJE - timedelta(days=250), raca_matriz="Holandês", diagnostico="POSITIVO"))
            s.commit()
        criado = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina pré-parto (evento)", "tipo_agendamento": "evento", "gatilho": "mudanca_pre_parto",
        })
        assert criado.status_code == 200, criado.text
        r = c.get("/sanidade/calendario/relatorio-eventos-vida", params={"evento_sanitario_id": criado.json()["id"]})
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["gatilho"] == "mudanca_pre_parto"
        numeros = {a["numero_matriz"] for a in dados["animais"]}
        assert "807" in numeros

    def test_gatilho_invalido_da_400(self, client):
        c, _ = client
        r = c.get("/sanidade/calendario/relatorio-eventos-vida", params={"gatilho": "inexistente"})
        assert r.status_code == 400

    def test_janela_de_aplicacao_classifica_situacao(self, client):
        """Com janela_de/janela_ate cadastrados, o relatório devolve
        situacao_janela por animal — sem janela cadastrada, nenhuma das novas
        chaves aparece (comportamento de hoje intacto)."""
        c, engine = client
        with Session(engine) as s:
            # Nasceu há 5 meses: está DENTRO de uma janela "3 a 8 meses".
            s.add(Animal(numero="910", data_nasc=HOJE - timedelta(days=150), sexo="F"))
            # Nasceu há 10 meses: já passou da janela "3 a 8 meses".
            s.add(Animal(numero="911", data_nasc=HOJE - timedelta(days=300), sexo="F"))
            s.commit()
        criado = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "B19 com janela", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "janela_de_valor": 3, "janela_de_unidade": "meses",
            "janela_ate_valor": 8, "janela_ate_unidade": "meses",
            "acao_fora_janela": "sair",
        })
        assert criado.status_code == 200, criado.text
        r = c.get("/sanidade/calendario/relatorio-eventos-vida", params={"evento_sanitario_id": criado.json()["id"]})
        assert r.status_code == 200, r.text
        por_numero = {a["numero_matriz"]: a for a in r.json()["animais"]}
        assert por_numero["910"]["situacao_janela"] == "na_janela"
        assert por_numero["911"]["situacao_janela"] == "fora_da_janela"
        assert por_numero["911"]["acao_fora_janela"] == "sair"

    def test_sem_janela_cadastrada_nao_inclui_situacao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="912", data_nasc=HOJE - timedelta(days=150), sexo="F"))
            s.commit()
        criado = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Sem janela", "tipo_agendamento": "evento", "gatilho": "nascimento",
        })
        assert criado.status_code == 200, criado.text
        r = c.get("/sanidade/calendario/relatorio-eventos-vida", params={"evento_sanitario_id": criado.json()["id"]})
        assert r.status_code == 200, r.text
        linha = next(a for a in r.json()["animais"] if a["numero_matriz"] == "912")
        assert "situacao_janela" not in linha
