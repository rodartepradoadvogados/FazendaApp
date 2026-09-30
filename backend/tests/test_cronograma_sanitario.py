"""
Cronograma sanitário — workflow dinâmico de acompanhamento de uma regra do
calendário sanitário marcada usa_cronograma=True: animal que bate o critério
entra "sugerido" (trilha do animal), e a aplicação só acontece depois de
decidir veterinário/aplicação própria (trilha do agendamento), com aviso
obrigatório N dias antes se ninguém decidiu nada.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, CalendarioSanitario, CronogramaSanitario, CronogramaSanitarioAnimal, Estoque, Pessoa


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


def _criar_evento_e_calendario(c, dias_ate_evento: int = 30, frequencia_valor: int = 60) -> tuple[int, int]:
    """Cria o Evento Sanitário (gatilho: novilha_apta aos 3 meses) + a regra
    do calendário com usa_cronograma=True. Devolve (evento_sanitario_id, calendario_id)."""
    r = c.post("/cadastro/eventos-sanitarios", json={
        "nome": "Vacina Brucelose", "tipo_agendamento": "evento", "gatilho": "novilha_apta",
        "gatilho_idade_meses": 3, "produto_padrao": "VACINA BRUCELOSE B19", "dose_padrao": 2, "unidade_padrao": "ml",
        "via_padrao": "Subcutânea",
    })
    assert r.status_code == 200, r.text
    evento_id = r.json()["id"]

    r = c.post("/sanidade/calendario", json={
        "evento_sanitario_id": evento_id, "categoria_alvo": "Novilhas 3 meses",
        "produto": "VACINA BRUCELOSE B19", "unidade": "ml", "dosagem": "2 ml",
        "frequencia_valor": frequencia_valor, "frequencia_unidade": "dias",
        "data_evento": (HOJE + timedelta(days=dias_ate_evento)).isoformat(),
        "usa_cronograma": True,
    })
    assert r.status_code == 200, r.text
    return evento_id, r.json()["id"]


def _agenda(c, tipo: str | None = None) -> list[dict]:
    c.post("/agenda/materializar", params={"data": HOJE.isoformat()})
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    eventos = r.json()["eventos"]
    if tipo:
        eventos = [e for e in eventos if e.get("tipo") == tipo]
    return eventos


def _cron_id(c, engine) -> int:
    """Materializa (POST /agenda/materializar) e devolve o id do 1º cronograma —
    a Agenda não devolve mais card de "modo"/"sugeridos" (R1/R2), então o id sai
    direto do banco."""
    from sqlmodel import select as _select
    c.post("/agenda/materializar", params={"data": HOJE.isoformat()})
    with Session(engine) as s:
        return s.exec(_select(CronogramaSanitario)).first().id


def _lista_espera(c) -> int:
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    return sum(x["quantidade"] for x in r.json()["lista_espera_sanitaria"])


def _animal_cronograma(engine, numero_matriz: str) -> CronogramaSanitarioAnimal:
    """Acha a linha `CronogramaSanitarioAnimal` de uma matriz direto no banco —
    desde que o resumo por cronograma (`cronograma_sanitario_sugeridos_{id}`)
    substituiu o card por animal na Agenda (13/09/2026), decidir/remover um
    animal específico não passa mais por um `id` que a Agenda devolve; o `id`
    da linha (usado em `cronograma_sanitario_animal_{id}`/`remover_animal_
    {id}`) é lido direto daqui, como a tela de detalhe (GET /sanidade/
    ocorrencias/{cronograma_id}) também faz."""
    from sqlmodel import select as _select
    with Session(engine) as s:
        linha = s.exec(_select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.numero_matriz == numero_matriz)).first()
        assert linha is not None, f"nenhuma linha de cronograma para a matriz {numero_matriz}"
        return linha


class TestTrilhaDoAnimal:
    def test_animal_que_bate_criterio_vira_sugestao_nao_pendencia_antiga(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="900", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()

        # Lista de espera NÃO é tarefa (R1): só resumo, fora de `eventos`.
        _cron_id(c, engine)
        assert not _agenda(c, "cronograma_sanitario_sugeridos")
        assert _lista_espera(c) == 1
        linha = _animal_cronograma(engine, "900")
        assert linha.status == "sugerido"
        # Não deve mais gerar a pendência antiga de "aplicar agora".
        assert not any(e.get("numero_animal") == "900" for e in _agenda(c, "evento_sanitario"))

    def test_incluir_animal_marca_status_incluido(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="901", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()

        _agenda(c)  # materializa a linha de cronograma
        linha_id = _animal_cronograma(engine, "901").id
        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_animal_{linha_id}", "incluir": True})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            linha = s.get(CronogramaSanitarioAnimal, linha_id)
            assert linha.status == "incluido"

        # A sugestão sai da lista de espera depois de decidida.
        assert _lista_espera(c) == 0

    def test_excluir_animal_marca_status_excluido(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="902", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()

        _agenda(c)  # materializa a linha de cronograma
        linha_id = _animal_cronograma(engine, "902").id
        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_animal_{linha_id}", "incluir": False})
        with Session(engine) as s:
            linha = s.get(CronogramaSanitarioAnimal, linha_id)
            assert linha.status == "excluido"

    def test_decidir_sem_incluir_da_400(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="903", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()
        _agenda(c)  # materializa a linha de cronograma
        linha_id = _animal_cronograma(engine, "903").id
        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_animal_{linha_id}"})
        assert r.status_code == 400


class TestIncluirAnimalForaDaJanela:
    """Bug relatado pelo usuário em 12/09/2026: um animal que não bate o
    critério automático da regra (idade/gatilho/categoria projetada) nunca
    ganha linha "sugerido" — sem jeito nenhum de incluí-lo manualmente."""

    def test_inclui_animal_que_nunca_seria_sugerido(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        with Session(engine) as s:
            # Muito nova pro gatilho "novilha_apta aos 3 meses" — nunca entraria como sugestão.
            s.add(Animal(numero="950", data_nasc=HOJE - timedelta(days=10), sexo="F", ativo=True))
            s.commit()
        _agenda(c)  # materializa os cronogramas — 950 não deve entrar em nenhum
        with Session(engine) as s:
            from sqlmodel import select as _select
            assert s.exec(_select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.numero_matriz == "950")).first() is None

        cronograma_id = _cron_id(c, engine)
        r = c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_incluir_manual_{cronograma_id}", "numero_matriz": "950",
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            linha = s.exec(
                __import__("sqlmodel").select(CronogramaSanitarioAnimal)
                .where(CronogramaSanitarioAnimal.cronograma_id == cronograma_id)
                .where(CronogramaSanitarioAnimal.numero_matriz == "950")
            ).first()
            assert linha is not None
            assert linha.status == "incluido"

    def test_animal_inexistente_da_404(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        cronograma_id = _cron_id(c, engine)
        r = c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_incluir_manual_{cronograma_id}", "numero_matriz": "999999",
        })
        assert r.status_code == 404

    def test_animal_ja_no_cronograma_da_400(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="951", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()
        _agenda(c)  # materializa a linha de cronograma
        linha = _animal_cronograma(engine, "951")
        cronograma_id = linha.cronograma_id
        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_animal_{linha.id}", "incluir": True})

        r = c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_incluir_manual_{cronograma_id}", "numero_matriz": "951",
        })
        assert r.status_code == 400

    def test_sem_numero_matriz_da_400(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        cronograma_id = _cron_id(c, engine)
        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_incluir_manual_{cronograma_id}"})
        assert r.status_code == 400


class TestRemoverAnimal:
    """Pedido do usuário em 13/09/2026: "adicionar OU remover animais
    manualmente" — `decidir_animal` só decide uma sugestão pela primeira vez
    (nunca desfaz) e a inclusão manual não tinha contrapartida nenhuma para
    tirar o animal de volta."""

    def test_remove_animal_incluido_manualmente(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="960", data_nasc=HOJE - timedelta(days=10), sexo="F", ativo=True))
            s.commit()
        cronograma_id = _cron_id(c, engine)
        c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_incluir_manual_{cronograma_id}", "numero_matriz": "960",
        })
        with Session(engine) as s:
            from sqlmodel import select
            linha = s.exec(
                select(CronogramaSanitarioAnimal)
                .where(CronogramaSanitarioAnimal.cronograma_id == cronograma_id)
                .where(CronogramaSanitarioAnimal.numero_matriz == "960")
            ).first()
            linha_id = linha.id

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_remover_animal_{linha_id}"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(CronogramaSanitarioAnimal, linha_id).status == "excluido"

    def test_remove_animal_ainda_sugerido(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="961", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()
        _agenda(c)  # materializa a linha de cronograma
        linha_id = _animal_cronograma(engine, "961").id

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_remover_animal_{linha_id}"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(CronogramaSanitarioAnimal, linha_id).status == "excluido"

    def test_remove_animal_ja_aplicado_da_400(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="962", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()
            linha = CronogramaSanitarioAnimal(
                cronograma_id=1, numero_matriz="962", status="aplicado", data_sugestao=HOJE, data_decisao=HOJE,
            )
            s.add(linha); s.commit(); linha_id = linha.id

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_remover_animal_{linha_id}"})
        assert r.status_code == 400

    def test_remove_animal_ja_removido_da_400(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="963", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()
        _agenda(c)  # materializa a linha de cronograma
        linha_id = _animal_cronograma(engine, "963").id
        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_remover_animal_{linha_id}"})

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_remover_animal_{linha_id}"})
        assert r.status_code == 400

class TestTrilhaDoAgendamento:
    def test_cronograma_recem_criado_nao_vira_tarefa(self, client):
        c, engine = client
        _criar_evento_e_calendario(c, dias_ate_evento=30)
        _cron_id(c, engine)
        assert not _agenda(c, "cronograma_sanitario_modo")
        assert not _agenda(c, "cronograma_sanitario_urgente")

    def test_perto_da_data_sem_decisao_continua_fora_da_agenda(self, client):
        c, engine = client
        # R2: só o agendamento entra na Agenda — cronograma "aberto" (sem modo
        # decidido) fica na lista de espera mesmo dentro da janela de aviso.
        _criar_evento_e_calendario(c, dias_ate_evento=3)
        _cron_id(c, engine)
        assert not _agenda(c, "cronograma_sanitario_urgente")
        assert not _agenda(c, "cronograma_sanitario_modo")

    def test_decidir_modo_propria(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c, dias_ate_evento=30)
        cid = _cron_id(c, engine)
        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_modo_{cid}", "modo": "propria"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            cron = s.exec(
                __import__("sqlmodel").select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)
            ).first()
            assert cron.status == "agendado"
            assert cron.modo_execucao == "propria"
        assert not _agenda(c, "cronograma_sanitario_modo")

    def test_decidir_modo_veterinario_exige_pessoa(self, client):
        c, engine = client
        _criar_evento_e_calendario(c, dias_ate_evento=30)
        cid = _cron_id(c, engine)
        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_modo_{cid}", "modo": "veterinario"})
        assert r.status_code == 400

    def test_decidir_modo_veterinario_com_pessoa_valida(self, client):
        c, engine = client
        _criar_evento_e_calendario(c, dias_ate_evento=30)
        with Session(engine) as s:
            vet = Pessoa(nome="Dr. Marcelo", tipo="Veterinário", ativo=True)
            s.add(vet)
            s.commit()
            s.refresh(vet)
            vet_id = vet.id

        cid = _cron_id(c, engine)
        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_modo_{cid}", "modo": "veterinario", "veterinario_pessoa_id": vet_id})
        assert r.status_code == 200, r.text

    def test_adiar_reabre_com_nova_data(self, client):
        c, engine = client
        _criar_evento_e_calendario(c, dias_ate_evento=3)
        cid = _cron_id(c, engine)
        nova_data = (HOJE + timedelta(days=45)).isoformat()
        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_modo_{cid}", "nova_data": nova_data, "motivo": "veterinário sem agenda"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(CronogramaSanitario, cid).data_evento.isoformat() == nova_data
        assert not _agenda(c, "cronograma_sanitario_urgente")
        assert not _agenda(c, "cronograma_sanitario_modo")


class TestAplicacao:
    def test_aplicar_gera_sanidade_e_conclui_cronograma(self, client):
        c, engine = client
        _criar_evento_e_calendario(c, dias_ate_evento=0)
        with Session(engine) as s:
            s.add(Animal(numero="910", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.add(Estoque(nome="VACINA BRUCELOSE B19", quantidade=100, unidade="ml", estocavel=True))
            s.commit()

        _agenda(c)  # materializa a linha de cronograma
        linha_id = _animal_cronograma(engine, "910").id
        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_animal_{linha_id}", "incluir": True})

        # Decidir o modo (Protocolos) agenda o cronograma — só então entra na Agenda.
        cid = _cron_id(c, engine)
        assert not _agenda(c, "cronograma_sanitario_aplicar")
        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_modo_{cid}", "modo": "propria"})

        aplicar = _agenda(c, "cronograma_sanitario_aplicar")
        assert len(aplicar) == 1
        assert aplicar[0]["animais"] == ["910"]

        r = c.post("/agenda/realizados", json={"evento_id": aplicar[0]["id"]})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            from fazenda.models import Sanidade
            aplicacao = s.exec(__import__("sqlmodel").select(Sanidade).where(Sanidade.numero_matriz == "910")).first()
            assert aplicacao is not None
            assert aplicacao.produto == "VACINA BRUCELOSE B19"

            linha = s.exec(
                __import__("sqlmodel").select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.numero_matriz == "910")
            ).first()
            assert linha.status == "aplicado"

            cron = s.exec(__import__("sqlmodel").select(CronogramaSanitario)).first()
            assert cron.status == "concluido"

        assert not _agenda(c, "cronograma_sanitario_aplicar")

    def test_aplicar_antes_de_decidir_modo_da_400(self, client):
        c, engine = client
        _criar_evento_e_calendario(c, dias_ate_evento=0)
        with Session(engine) as s:
            s.add(Animal(numero="911", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()
        _agenda(c)  # materializa a linha de cronograma
        linha_id = _animal_cronograma(engine, "911").id
        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_animal_{linha_id}", "incluir": True})
        # Sem decidir modo, o cronograma segue "aberto" — nunca aparece o card de aplicar.
        assert not _agenda(c, "cronograma_sanitario_aplicar")


class TestRegraSemCronogramaContinuaIgual:
    def test_regra_usa_cronograma_false_mantem_comportamento_antigo(self, client):
        c, engine = client
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vermífugo do rebanho", "tipo_agendamento": "epoca",
            "data_primeiro": HOJE.isoformat(), "frequencia_valor": 6, "frequencia_unidade": "meses",
            "produto_padrao": "Ivermectina", "dose_padrao": 5, "unidade_padrao": "ml",
        })
        evento_id = r.json()["id"]
        r = c.post("/sanidade/calendario", json={
            "evento_sanitario_id": evento_id, "categoria_alvo": "Bezerras",
            "produto": "Ivermectina", "unidade": "ml", "dosagem": "5 ml",
            "frequencia_valor": 4, "frequencia_unidade": "meses", "data_evento": HOJE.isoformat(),
        })
        assert r.status_code == 200, r.text
        assert r.json()["usa_cronograma"] is False
        # Continua gerando a pendência antiga (calendario_sanitario), não cronograma.
        assert any(e["produto"] == "Ivermectina" for e in _agenda(c, "calendario_sanitario"))
        assert not _agenda(c, "cronograma_sanitario_modo")


class TestListagem:
    def test_get_cronogramas_lista_com_contagem_de_animais(self, client):
        c, engine = client
        _criar_evento_e_calendario(c)
        with Session(engine) as s:
            s.add(Animal(numero="920", data_nasc=HOJE - timedelta(days=95), sexo="F", ativo=True))
            s.commit()
        _agenda(c)  # dispara a geração do cronograma/sugestão

        r = c.get("/sanidade/cronogramas")
        assert r.status_code == 200, r.text
        cronogramas = r.json()
        assert len(cronogramas) == 1
        assert cronogramas[0]["animais_contagem"]["sugerido"] == 1
        assert cronogramas[0]["evento_sanitario_nome"] == "Vacina Brucelose"


class TestCriacaoManual:
    """POST /sanidade/cronogramas — card Cronogramas > "Novo cronograma":
    sempre exige vincular a uma regra existente com usa_cronograma=True."""

    def test_exige_regra_existente(self, client):
        c, _ = client
        r = c.post("/sanidade/cronogramas", json={"calendario_sanitario_id": 9999})
        assert r.status_code == 404

    def test_recusa_regra_sem_usa_cronograma(self, client):
        c, engine = client
        evento_id = c.post("/cadastro/eventos-sanitarios", json={"nome": "Vacina X", "categoria_preventiva": "vacina"}).json()["id"]
        calendario_id = c.post("/sanidade/calendario", json={
            "evento_sanitario_id": evento_id, "categoria_alvo": "Vacas",
            "frequencia_valor": 12, "frequencia_unidade": "meses", "data_evento": HOJE.isoformat(),
        }).json()["id"]
        r = c.post("/sanidade/cronogramas", json={"calendario_sanitario_id": calendario_id})
        assert r.status_code == 400
        assert "usa_cronograma" in r.json()["detail"] or "cronograma" in r.json()["detail"].lower()

    def test_cria_cronograma_vinculado_a_regra(self, client):
        c, _ = client
        _, calendario_id = _criar_evento_e_calendario(c, dias_ate_evento=20)
        r = c.post("/sanidade/cronogramas", json={"calendario_sanitario_id": calendario_id})
        assert r.status_code == 200, r.text
        cron = r.json()
        assert cron["calendario_sanitario_id"] == calendario_id
        assert cron["status"] == "aberto"
        # Chamar de novo devolve o MESMO cronograma em aberto (não duplica).
        r2 = c.post("/sanidade/cronogramas", json={"calendario_sanitario_id": calendario_id})
        assert r2.json()["id"] == cron["id"]
