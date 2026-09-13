"""
Evento sanitário agendado (por época e por evento de vida) → aparece na Agenda
com o medicamento padrão; a baixa some quando a aplicação é registrada.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, CalendarioSanitario, Estoque, MovimentoLote, Parto, PrincipioAtivo, Sanidade


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


class TestCadastroRico:
    def test_cria_evento_epoca_com_medicamento_padrao(self, client):
        c, _ = client
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vermífugo do rebanho", "tipo_agendamento": "epoca",
            "data_primeiro": HOJE.isoformat(), "frequencia_valor": 6, "frequencia_unidade": "meses",
            "categoria_alvo": "Bezerras", "produto_padrao": "Ivermectina", "dose_padrao": 5, "unidade_padrao": "ml", "via_padrao": "Subcutânea",
        })
        assert r.status_code == 200, r.text
        assert r.json()["proxima_ocorrencia"] is not None

    def test_epoca_sem_data_da_400(self, client):
        c, _ = client
        r = c.post("/cadastro/eventos-sanitarios", json={"nome": "X", "tipo_agendamento": "epoca", "frequencia_valor": 6, "frequencia_unidade": "meses"})
        assert r.status_code == 400

    def test_nome_simples_ainda_funciona(self, client):
        c, _ = client
        r = c.post("/cadastro/eventos-sanitarios", json={"nome": "Brucelose B19"})
        assert r.status_code == 200, r.text
        assert r.json()["tipo_agendamento"] == "nenhum"


class TestAgendaEpoca:
    def test_epoca_aparece_na_agenda_com_produto(self, client):
        c, _ = client
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vermífugo", "tipo_agendamento": "epoca",
            "data_primeiro": HOJE.isoformat(), "frequencia_valor": 6, "frequencia_unidade": "meses",
            "produto_padrao": "Ivermectina", "dose_padrao": 5, "unidade_padrao": "ml",
        })
        eventos = _agenda_sanidade(c)
        assert any(e["produto"] == "Ivermectina" and e["data"] == HOJE.isoformat() for e in eventos)


class TestAgendaPorEvento:
    def test_nascimento_gera_evento_por_animal(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="401", data_nasc=HOJE - timedelta(days=10), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina ao nascer", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "produto_padrao": "VacinaX", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        eventos = _agenda_sanidade(c)
        meus = [e for e in eventos if e["numero_animal"] == "401"]
        assert len(meus) == 1
        assert meus[0]["produto"] == "VacinaX"

    def test_some_depois_de_aplicado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="402", data_nasc=HOJE - timedelta(days=5), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina ao nascer", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "produto_padrao": "VacinaX", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        assert any(e["numero_animal"] == "402" for e in _agenda_sanidade(c))
        # Aplica → some da agenda (dedup por produto após o gatilho).
        with Session(engine) as s:
            s.add(Sanidade(numero_matriz="402", data_aplicacao=HOJE, produto="VacinaX", dose=2, unidade="ml"))
            s.commit()
        assert not any(e["numero_animal"] == "402" for e in _agenda_sanidade(c))

    def test_entrada_lote_gera_evento(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", data_nasc=HOJE - timedelta(days=800), sexo="F"))
            s.add(MovimentoLote(numero_matriz="500", lote_destino="PRE_PARTO", data_movimento=HOJE - timedelta(days=3)))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina pré-parto", "tipo_agendamento": "evento", "gatilho": "entrada_lote", "gatilho_lote": "PRE_PARTO",
            "produto_padrao": "VacinaPre", "dose_padrao": 5, "unidade_padrao": "ml",
        })
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "500"]
        assert len(meus) == 1 and meus[0]["produto"] == "VacinaPre"

    def test_animal_baixado_nao_aparece(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="403", data_nasc=HOJE - timedelta(days=10), sexo="F", ativo=False))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina ao nascer", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "produto_padrao": "VacinaX", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        assert not any(e["numero_animal"] == "403" for e in _agenda_sanidade(c))

    def test_sexo_alvo_restringe_ao_sexo_cadastrado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="03M", data_nasc=HOJE - timedelta(days=155), sexo="M"))
            s.add(Animal(numero="404", data_nasc=HOJE - timedelta(days=155), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Brucelose B19", "tipo_agendamento": "evento", "gatilho": "nascimento", "offset_dias": 150,
            "sexo_alvo": "F", "produto_padrao": "VacinaB19", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        eventos = _agenda_sanidade(c)
        assert not any(e["numero_animal"] == "03M" for e in eventos)
        assert any(e["numero_animal"] == "404" for e in eventos)


class TestGatilhoNovilhaApta:
    """O gatilho `novilha_apta` é "a novilha atingiu a idade-alvo configurada
    no cadastro do evento" — não a aptidão reprodutiva da regra 7 (que exige
    idade_apta_min_meses E peso_apta_min). O rótulo da tela é "Aptidão
    (novilha atingir certa idade)" e a semente do sistema traz Brucelose
    RB51 aos 13 meses, abaixo do idade_apta_min_meses padrão (15): amarrar
    este gatilho aos parâmetros de aptidão apagaria a vacina de brucelose da
    Agenda, e exigir peso apagaria o gatilho inteiro em fazenda que não pesa.

    O que É defeito, e o que estes testes fixam: o filtro antigo era só
    "fêmea ativa com data de nascimento", então agendava manejo de NOVILHA
    para vaca que já pariu e para animal marcado a descartar."""

    def _cadastrar(self, c, gatilho_idade_meses: int = 13):
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Exame de entrada em reprodução", "tipo_agendamento": "evento", "gatilho": "novilha_apta",
            "gatilho_idade_meses": gatilho_idade_meses, "produto_padrao": "ExameX", "dose_padrao": 1, "unidade_padrao": "un",
        })

    def test_novilha_na_idade_alvo_recebe(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="801", data_nasc=HOJE - timedelta(days=400), sexo="F", ativo=True))
            s.commit()
        self._cadastrar(c)
        assert any(e["numero_animal"] == "801" for e in _agenda_sanidade(c))

    def test_sem_pesagem_registrada_recebe_do_mesmo_jeito(self, client):
        """Sentinela: peso NÃO faz parte deste gatilho. A "801" acima também
        não tem pesagem — este teste existe para que uma tentativa futura de
        exigir peso aqui quebre com a razão escrita, em vez de silenciosamente
        esvaziar a Agenda de brucelose em fazenda que não pesa animal."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="806", data_nasc=HOJE - timedelta(days=400), sexo="F", ativo=True))
            s.commit()
        self._cadastrar(c)
        assert any(e["numero_animal"] == "806" for e in _agenda_sanidade(c))

    def test_idade_alvo_abaixo_do_parametro_de_aptidao_continua_valendo(self, client):
        """A idade-alvo é a do CADASTRO, não `idade_apta_min_meses()` (padrão
        15). Aos 4 meses — a idade legal da vacina de brucelose — o evento
        tem de aparecer."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="807", data_nasc=HOJE - timedelta(days=130), sexo="F", ativo=True))
            s.commit()
        self._cadastrar(c, gatilho_idade_meses=4)
        assert any(e["numero_animal"] == "807" for e in _agenda_sanidade(c))

    def test_vaca_multipara_nao_recebe(self, client):
        c, engine = client
        with Session(engine) as s:
            # Vaca com Parto registrado já não é novilha — não faz sentido
            # reagendar nela um manejo de novilha. Antes da correção, o
            # gatilho só olhava sexo+ativo+data_nasc.
            s.add(Animal(numero="804", data_nasc=HOJE - timedelta(days=1500), sexo="F", ativo=True))
            s.add(Parto(numero_matriz="804", data_parto=HOJE - timedelta(days=100)))
            s.commit()
        self._cadastrar(c)
        assert not any(e["numero_animal"] == "804" for e in _agenda_sanidade(c))

    def test_marcada_a_descartar_nao_recebe(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="805", data_nasc=HOJE - timedelta(days=400), sexo="F", ativo=True, a_descartar=True))
            s.commit()
        self._cadastrar(c)
        assert not any(e["numero_animal"] == "805" for e in _agenda_sanidade(c))


class TestAplicacaoAgendadaNaAgenda:
    """Bug real: 'Animal 03M ainda aparece pra tomar vacina de brucelose,
    mas é macho e já foi baixado' — a pendência vinha de AplicacaoAgendada
    (lançamento manual "aplicado? não"), que nunca filtrava por animal
    ativo. Uma vez criada, ficava pendurada na Agenda pra sempre, mesmo
    depois do animal ser baixado."""

    def _agenda_aplic_agendada(self, c) -> list[dict]:
        r = c.get("/agenda/", params={"data": HOJE.isoformat()})
        assert r.status_code == 200, r.text
        return [e for e in r.json()["eventos"] if e.get("tipo") == "aplicacao_agendada"]

    def test_animal_ativo_aparece(self, client):
        from fazenda.models import AplicacaoAgendada
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="03M", data_nasc=HOJE - timedelta(days=200), sexo="M"))
            s.add(AplicacaoAgendada(numero_matriz="03M", data=HOJE, produto="Brucelose B19"))
            s.commit()
        assert any(e["numero_animal"] == "03M" for e in self._agenda_aplic_agendada(c))

    def test_animal_baixado_nao_aparece_mais(self, client):
        from fazenda.models import AplicacaoAgendada
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="03M", data_nasc=HOJE - timedelta(days=200), sexo="M", ativo=False))
            s.add(AplicacaoAgendada(numero_matriz="03M", data=HOJE, produto="Brucelose B19"))
            s.commit()
        assert not any(e["numero_animal"] == "03M" for e in self._agenda_aplic_agendada(c))


def _agenda_calendario(c) -> list[dict]:
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    return [e for e in r.json()["eventos"] if e.get("tipo") == "calendario_sanitario"]


class TestCalendarioNaAgenda:
    """Regra do calendário sanitário (preventivo) precisa virar pendência na
    Agenda — antes só existia na tela de calendário e nunca dava baixa."""

    def _cria_exame(self, c, realizado=False):
        ev = c.post("/cadastro/eventos-sanitarios", json={"nome": "Exame de brucelose", "categoria_preventiva": "exame"})
        assert ev.status_code == 200, ev.text
        r = c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev.json()["id"], "categoria_alvo": "Novilhas",
            "frequencia_valor": 1, "frequencia_unidade": "anos", "data_evento": HOJE.isoformat(),
            "veterinario": "Dr. Carlos", "realizado": realizado,
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_exame_hoje_aparece_na_agenda(self, client):
        c, _ = client
        self._cria_exame(c)
        evs = _agenda_calendario(c)
        assert len(evs) == 1
        assert evs[0]["data"] == HOJE.isoformat()
        assert evs[0]["produto"] is None  # exame não tem baixa de estoque
        assert evs[0]["veterinario"] == "Dr. Carlos"
        assert evs[0]["categoria_preventiva"] == "exame"

    def test_baixa_some_da_agenda(self, client):
        c, _ = client
        self._cria_exame(c)
        eid = _agenda_calendario(c)[0]["id"]
        rb = c.post("/agenda/realizados", json={"evento_id": eid})
        assert rb.status_code == 200, rb.text
        assert not _agenda_calendario(c)

    def test_realizado_no_cadastro_ja_some(self, client):
        c, _ = client
        self._cria_exame(c, realizado=True)
        # marcado como realizado no cadastro → não aparece como pendência
        assert not _agenda_calendario(c)

    def test_excluir_regra_remove_da_agenda(self, client):
        c, _ = client
        regra = self._cria_exame(c)
        assert _agenda_calendario(c)
        rd = c.delete(f"/sanidade/calendario/{regra['id']}")
        assert rd.status_code == 200, rd.text
        assert not _agenda_calendario(c)


class TestBaixaDeRegraExistenteComDiagnostico:
    """Bug real: dar baixa (com diagnóstico) numa pendência que já vem de uma
    regra do calendário sanitário existente (ex.: exame de tuberculose) tinha
    que passar o id da regra (`calendario_id`) — sem isso, /cadastrar-preventivo
    sempre criava uma regra NOVA duplicada e marcava a ocorrência realizada
    dessa regra nova, deixando a pendência original (da regra antiga) presa na
    Agenda para sempre, mesmo com o diagnóstico já registrado."""

    def _cria_exame(self, c):
        ev = c.post("/cadastro/eventos-sanitarios", json={"nome": "Exame de tuberculose", "categoria_preventiva": "exame"})
        assert ev.status_code == 200, ev.text
        r = c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev.json()["id"], "categoria_alvo": "Rebanho",
            "frequencia_valor": 1, "frequencia_unidade": "anos", "data_evento": HOJE.isoformat(),
            "veterinario": "Dr. Carlos",
        })
        assert r.status_code == 200, r.text
        return ev.json()["id"], r.json()["id"]

    def test_calendario_id_da_baixa_sem_duplicar_regra(self, client):
        c, engine = client
        ev_id, regra_id = self._cria_exame(c)
        assert _agenda_calendario(c)  # pendência do exame de hoje

        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": HOJE.isoformat(), "animais": ["101"],
            "calendario_id": regra_id, "resultado_exame": "negativo",
        })
        assert r.status_code == 200, r.text
        assert r.json()["regra"]["id"] == regra_id  # reaproveita a regra existente

        with Session(engine) as s:
            assert len(s.exec(select(CalendarioSanitario)).all()) == 1  # sem duplicar

        rb = c.post("/agenda/realizados", json={"evento_id": f"calendario_sanitario_{regra_id}__{HOJE.isoformat()}"})
        assert rb.status_code == 200, rb.text
        assert not _agenda_calendario(c)

    def test_calendario_id_de_outro_evento_da_404(self, client):
        c, _ = client
        ev_id, regra_id = self._cria_exame(c)
        outro_ev = c.post("/cadastro/eventos-sanitarios", json={"nome": "Outra vacina"}).json()["id"]
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": outro_ev, "data_evento": HOJE.isoformat(), "animais": ["101"],
            "calendario_id": regra_id,
        })
        assert r.status_code == 404

    def test_calendario_id_inexistente_da_404(self, client):
        c, _ = client
        ev_id, _ = self._cria_exame(c)
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": HOJE.isoformat(), "animais": ["101"],
            "calendario_id": 999999,
        })
        assert r.status_code == 404


class TestPrincipioAtivoNaAgenda:
    """O evento sanitário por gatilho deve pré-preencher o princípio ativo do
    produto padrão (resolvido via Estoque) — sem isso, o seletor "Princípio
    ativo" da Agenda ficava sempre em branco para eventos por evento de vida."""

    def test_produto_padrao_resolve_principio_ativo_id(self, client):
        c, engine = client
        with Session(engine) as s:
            pa = PrincipioAtivo(nome="Brucelose Bovina")
            s.add(pa)
            s.commit()
            s.refresh(pa)
            pa_id = pa.id
            s.add(Estoque(nome="VACINA RB 51", quantidade=10, unidade="unidade", principio_ativo_id=pa_id))
            s.add(Animal(numero="601", data_nasc=HOJE - timedelta(days=400), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Brucelose RB51", "tipo_agendamento": "evento", "gatilho": "novilha_apta",
            "gatilho_idade_meses": 13, "produto_padrao": "VACINA RB 51", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "601"]
        assert len(meus) == 1
        assert meus[0]["principio_ativo_id"] == pa_id


class TestCondicaoExclusaoMutua:
    """Alternativas de vacina/estirpe para a mesma doença (ex.: Brucelose B19 ×
    RB51): o evento com condicao_evento_id não deve ser agendado se o animal já
    recebeu o evento apontado como condição — em qualquer data, não só desde o
    gatilho atual."""

    def _cadastrar_dois_eventos(self, c):
        b19 = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Brucelose B19", "tipo_agendamento": "evento", "gatilho": "novilha_apta",
            "gatilho_idade_meses": 13, "produto_padrao": "VACINA B19", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        assert b19.status_code == 200, b19.text
        rb51 = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Brucelose RB51", "tipo_agendamento": "evento", "gatilho": "novilha_apta",
            "gatilho_idade_meses": 13, "produto_padrao": "VACINA RB 51", "dose_padrao": 2, "unidade_padrao": "ml",
            "condicao_evento_id": b19.json()["id"],
        })
        assert rb51.status_code == 200, rb51.text
        return b19.json(), rb51.json()

    def test_sem_condicao_aplicada_agenda_normalmente(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="701", data_nasc=HOJE - timedelta(days=400), sexo="F"))
            s.commit()
        self._cadastrar_dois_eventos(c)
        nomes = {e["descricao"].split(" — ")[0] for e in _agenda_sanidade(c) if e["numero_animal"] == "701"}
        assert nomes == {"Brucelose B19", "Brucelose RB51"}

    def test_ja_vacinada_com_condicao_esconde_o_evento(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="702", data_nasc=HOJE - timedelta(days=400), sexo="F"))
            s.commit()
        self._cadastrar_dois_eventos(c)
        with Session(engine) as s:
            # Aplicação bem antiga (fora da janela do gatilho atual) — não deduplica
            # o próprio B19 (isso já é coberto por test_some_depois_de_aplicado),
            # mas a condição de RB51 olha "alguma vez", não só desde o gatilho.
            s.add(Sanidade(numero_matriz="702", data_aplicacao=HOJE - timedelta(days=1000), produto="VACINA B19", dose=2, unidade="ml"))
            s.commit()
        nomes = {e["descricao"].split(" — ")[0] for e in _agenda_sanidade(c) if e["numero_animal"] == "702"}
        assert "Brucelose RB51" not in nomes  # bloqueado pela condição, mesmo com aplicação antiga

    def test_condicao_invalida_da_400(self, client):
        c, _ = client
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Evento X", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "condicao_evento_id": 99999,
        })
        assert r.status_code == 400


class TestJanelaDeAplicacao:
    """Janela de aplicação (de/até/ação ao sair) — reportado pelo usuário
    2026-09-10 como redundante com "Dias após o gatilho" (offset_dias): os
    dois pareciam pedir a mesma coisa porque, de fato, calculavam a mesma
    coisa por dois caminhos diferentes — e "Dias após o gatilho" nunca soube
    contar em meses. Decisão do usuário: a janela ("de") vira a fonte real de
    quando o item entra na Agenda, substituindo offset_dias quando cadastrada
    (offset_dias continua valendo, sem mudança nenhuma, para quem nunca
    configurou janela). E "ação ao sair da janela" passa a valer de verdade:
    "sair" encerra a pendência, "manter" nunca some sozinha."""

    def test_janela_de_prevalece_sobre_offset_dias(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="901", data_nasc=HOJE - timedelta(days=120), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina com janela", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "offset_dias": 30,  # se ainda fosse usado, o gatilho cairia 90 dias atrás do previsto abaixo
            "janela_de_valor": 120, "janela_de_unidade": "dias",
            "produto_padrao": "VacinaJanela", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "901"]
        assert len(meus) == 1
        # nasceu há 120 dias + janela_de 120 dias = data prevista = hoje
        assert meus[0]["data"] == HOJE.isoformat()

    def test_janela_de_em_meses_usa_calendario_de_verdade(self, client):
        """`_somar_meses` (calendário real) em vez de uma aproximação de 30
        dias — nasceu há exatamente 4 meses corridos, janela de 4 meses deve
        cair em HOJE, não numa data alguns dias fora por causa de meses com
        tamanhos diferentes."""
        c, engine = client
        nascimento = HOJE.replace(year=HOJE.year if HOJE.month > 4 else HOJE.year - 1, month=(HOJE.month - 4) or 12) if HOJE.month > 4 else HOJE
        # Monta a data de nascimento como "4 meses corridos atrás de hoje" (o
        # próprio inverso de _somar_meses), sem reimplementar a lib de datas.
        from fazenda.rules.calendario_sanitario import _somar_meses
        m = HOJE.month - 4
        ano = HOJE.year
        while m <= 0:
            m += 12
            ano -= 1
        import calendar as _cal
        dia = min(HOJE.day, _cal.monthrange(ano, m)[1])
        nascimento = date(ano, m, dia)
        assert _somar_meses(nascimento, 4) == HOJE  # sanidade da massa de teste

        with Session(engine) as s:
            s.add(Animal(numero="902", data_nasc=nascimento, sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina 4 meses", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "janela_de_valor": 4, "janela_de_unidade": "meses",
            "produto_padrao": "Vacina4M", "dose_padrao": 1, "unidade_padrao": "ml",
        })
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "902"]
        assert len(meus) == 1
        assert meus[0]["data"] == HOJE.isoformat()

    def test_sem_janela_offset_dias_continua_funcionando(self, client):
        """Evento sem janela nenhuma (o caso de sempre) não muda em nada."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="903", data_nasc=HOJE - timedelta(days=150), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina sem janela", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "offset_dias": 150,
            "produto_padrao": "VacinaSemJanela", "dose_padrao": 1, "unidade_padrao": "ml",
        })
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "903"]
        assert len(meus) == 1
        assert meus[0]["data"] == HOJE.isoformat()

    def test_acao_sair_encerra_pendencia_fora_da_janela(self, client):
        c, engine = client
        with Session(engine) as s:
            # Nasceu há 100 dias: janela 60-90 dias (a partir do gatilho)
            # já fechou há 10 dias — mas a data em que o item ficou devido
            # (nascimento + 60 = há 40 dias) continua dentro da janela padrão
            # de visibilidade da Agenda (120 dias passado/180 futuro), pra
            # isolar o efeito de "sair" do filtro de visibilidade geral (que
            # é outra coisa, não relacionada à janela de aplicação).
            s.add(Animal(numero="904", data_nasc=HOJE - timedelta(days=100), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina com saida", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "janela_de_valor": 60, "janela_de_unidade": "dias",
            "janela_ate_valor": 90, "janela_ate_unidade": "dias", "acao_fora_janela": "sair",
            "produto_padrao": "VacinaSai", "dose_padrao": 1, "unidade_padrao": "ml",
        })
        assert not any(e["numero_animal"] == "904" for e in _agenda_sanidade(c))

    def test_acao_manter_nao_encerra_pendencia_fora_da_janela(self, client):
        c, engine = client
        with Session(engine) as s:
            # Mesmo cenário do teste de "sair" acima (janela já fechou há 10
            # dias, mas dentro da janela de visibilidade padrão da Agenda) —
            # só muda a ação: "manter" nunca expira sozinha.
            s.add(Animal(numero="905", data_nasc=HOJE - timedelta(days=100), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina com manter", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "janela_de_valor": 60, "janela_de_unidade": "dias",
            "janela_ate_valor": 90, "janela_ate_unidade": "dias", "acao_fora_janela": "manter",
            "produto_padrao": "VacinaManter", "dose_padrao": 1, "unidade_padrao": "ml",
        })
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "905"]
        assert len(meus) == 1
        assert meus[0]["acao_fora_janela"] == "manter"

    def test_dentro_da_janela_carrega_dias_para_fechar(self, client):
        c, engine = client
        with Session(engine) as s:
            # Nasceu há 150 dias: dentro da janela 120-240, faltam 90 dias pra fechar.
            s.add(Animal(numero="906", data_nasc=HOJE - timedelta(days=150), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina notificar", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "janela_de_valor": 120, "janela_de_unidade": "dias",
            "janela_ate_valor": 240, "janela_ate_unidade": "dias", "acao_fora_janela": "notificar",
            "produto_padrao": "VacinaNotif", "dose_padrao": 1, "unidade_padrao": "ml",
        })
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "906"]
        assert len(meus) == 1
        assert meus[0]["dias_para_fechar_janela"] == 90
        assert meus[0]["janela_fim"] == (HOJE + timedelta(days=90)).isoformat()
