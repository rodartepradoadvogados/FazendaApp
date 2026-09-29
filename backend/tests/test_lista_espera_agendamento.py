"""
Fatia 7 do planejamento unificado (docs/agents/auditoria-preventivo-agenda/
planejamento/06-planejamento-unificado.md, secao 7, R1-R9): lista de espera,
'Criar agendamento' (animais da janela + fora da janela com motivo), adiar e
cancelar; regra por EVENTO DE VIDA tambem entra na lista de espera.

  R6  animal fora da janela exige motivo;
  R8  um animal fica em UMA lista/agendamento ativo por protocolo;
  R9  adiar mantem os animais; cancelar devolve a lista de espera (com motivo).
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, CalendarioSanitario, CategoriaManejo, ContratoFazenda, ContratoFazendaModulo, CronogramaSanitario,
    CronogramaSanitarioAnimal, EventoSanitario, Fazenda, ParametroFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules.parametros import fazenda_atual

HOJE = date.today()


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "teste@example.com"
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()
    fazenda_atual.set(None)


def _animal(s: Session, numero: str, *, ativo: bool = True, fazenda_id: int = 1, grupo: str = "Novilhas") -> None:
    s.add(Animal(numero=numero, nome=f"Vaca {numero}", sexo="F", ativo=ativo, grupo_primario=grupo,
                 data_nasc=HOJE - timedelta(days=200), fazenda_id=fazenda_id))


def _regra(s: Session, nome: str = "Vacina X", *, fazenda_id: int = 1, data_evento: date | None = None) -> int:
    ev = EventoSanitario(nome=nome, tipo_agendamento="epoca", fazenda_id=fazenda_id)
    s.add(ev)
    s.commit()
    s.refresh(ev)
    cal = CalendarioSanitario(
        evento_sanitario_id=ev.id, categoria_alvo="Novilha", produto=nome, frequencia_valor=6,
        frequencia_unidade="meses", data_evento=data_evento or (HOJE + timedelta(days=20)),
        usa_cronograma=True, fazenda_id=fazenda_id,
    )
    s.add(cal)
    s.commit()
    s.refresh(cal)
    return cal.id


def _espera(s: Session, cal_id: int, numeros: list[str], *, data_evento: date, fazenda_id: int = 1, status: str = "aberto") -> int:
    cron = CronogramaSanitario(calendario_sanitario_id=cal_id, data_evento=data_evento, status=status, fazenda_id=fazenda_id)
    s.add(cron)
    s.commit()
    s.refresh(cron)
    for n in numeros:
        s.add(CronogramaSanitarioAnimal(cronograma_id=cron.id, numero_matriz=n, status="sugerido",
                                        data_sugestao=HOJE, fazenda_id=fazenda_id))
    s.commit()
    return cron.id


def _linhas(engine, cron_id: int) -> dict[str, CronogramaSanitarioAnimal]:
    with Session(engine) as s:
        return {l.numero_matriz: l for l in s.exec(
            select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron_id)).all()}


def _cron(engine, cron_id: int) -> CronogramaSanitario:
    with Session(engine) as s:
        return s.get(CronogramaSanitario, cron_id)


def _criar(c, cal_id: int, **kw):
    corpo = {"calendario_sanitario_id": cal_id, "data_evento": (HOJE + timedelta(days=3)).isoformat(), "hora": "08:30"}
    corpo.update(kw)
    return c.post("/sanidade/cronogramas/agendamentos", json=corpo)


class TestListaEspera:
    def test_agrupa_por_protocolo_com_atrasada_e_na_janela(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            for n in ("1", "2", "3"):
                _animal(s, n)
            a = _regra(s, "Vacina A")
            b = _regra(s, "Vacina B")
            _espera(s, a, ["1", "2"], data_evento=HOJE - timedelta(days=5))   # devida ha 5 dias
            _espera(s, b, ["3"], data_evento=HOJE + timedelta(days=4))         # ainda dentro da janela
        r = c.get("/sanidade/cronogramas/lista-espera")
        assert r.status_code == 200, r.text
        dados = r.json()
        por_nome = {g["protocolo_nome"]: g for g in dados["grupos"]}
        ga, gb = por_nome["Vacina A"], por_nome["Vacina B"]
        assert ga["quantidade"] == 2 and ga["situacao"] == "atrasada" and ga["dias_atraso"] == 5
        assert {x["numero_matriz"] for x in ga["animais"]} == {"1", "2"}
        assert all(x["situacao"] == "atrasada" and x["dias_atraso"] == 5 for x in ga["animais"])
        assert gb["quantidade"] == 1 and gb["situacao"] == "na_janela" and gb["dias_atraso"] == 0
        assert gb["animais"][0]["nome"] == "Vaca 3" and gb["animais"][0]["lote"] == "Novilhas"
        assert dados["total"] == 3 and dados["atrasadas"] == 2

    def test_exclui_vendidos_baixados_e_outra_fazenda(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            _animal(s, "2", ativo=False)           # baixado/vendido
            cal = _regra(s)
            _espera(s, cal, ["1", "2", "999"], data_evento=HOJE)   # 999 nem existe
            _animal(s, "50", fazenda_id=2)
            cal2 = _regra(s, "Vacina Y", fazenda_id=2)
            _espera(s, cal2, ["50"], data_evento=HOJE, fazenda_id=2)
        dados = c.get("/sanidade/cronogramas/lista-espera").json()
        assert [g["protocolo_nome"] for g in dados["grupos"]] == ["Vacina X"]
        assert [x["numero_matriz"] for x in dados["grupos"][0]["animais"]] == ["1"]
        assert dados["total"] == 1

    def test_filtra_por_calendario(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            _animal(s, "2")
            a, b = _regra(s, "A"), _regra(s, "B")
            _espera(s, a, ["1"], data_evento=HOJE)
            _espera(s, b, ["2"], data_evento=HOJE)
        dados = c.get("/sanidade/cronogramas/lista-espera", params={"calendario_id": b}).json()
        assert [g["calendario_id"] for g in dados["grupos"]] == [b]


class TestCriarAgendamento:
    def test_janela_e_fora_da_janela_com_motivo(self, ctx):
        c, engine = ctx
        dia = HOJE + timedelta(days=3)
        with Session(engine) as s:
            for n in ("1", "2", "3", "9"):
                _animal(s, n)
            cal = _regra(s)
            espera = _espera(s, cal, ["1", "2", "3"], data_evento=HOJE)
        r = _criar(c, cal, animais_janela=["1", "2"], animais_fora=[{"numero_matriz": "9", "motivo": "Exigência do frigorífico"}])
        assert r.status_code == 200, r.text
        ag = r.json()
        assert ag["status"] == "agendado" and ag["hora"] == "08:30" and ag["data_evento"] == dia.isoformat()
        assert ag["id"] != espera
        origens = {a["numero_matriz"]: (a["origem"], a["motivo"], a["status"]) for a in ag["animais"]}
        assert origens == {"1": ("janela", None, "incluido"), "2": ("janela", None, "incluido"),
                           "9": ("fora_janela", "Exigência do frigorífico", "incluido")}
        # quem nao foi escolhido segue na lista de espera
        restante = _linhas(engine, espera)
        assert {n: l.status for n, l in restante.items()} == {"3": "sugerido"}
        dados = c.get("/sanidade/cronogramas/lista-espera").json()
        assert [x["numero_matriz"] for g in dados["grupos"] for x in g["animais"]] == ["3"]

    def test_todos_os_animais_reaproveita_a_mesma_linha(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            _animal(s, "2")
            cal = _regra(s)
            espera = _espera(s, cal, ["1", "2"], data_evento=HOJE)
        r = _criar(c, cal, animais_janela=["1", "2"])
        assert r.status_code == 200, r.text
        assert r.json()["id"] == espera
        with Session(engine) as s:
            assert len(s.exec(select(CronogramaSanitario)).all()) == 1

    def test_fora_da_janela_exige_motivo_R6(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            _animal(s, "9")
            cal = _regra(s)
            _espera(s, cal, ["1"], data_evento=HOJE)
        for motivo in (None, "", "   "):
            item = {"numero_matriz": "9"} if motivo is None else {"numero_matriz": "9", "motivo": motivo}
            r = _criar(c, cal, animais_janela=["1"], animais_fora=[item])
            assert r.status_code == 400, r.text
            assert "motivo" in r.json()["detail"].lower()
        with Session(engine) as s:  # nada foi gravado
            assert len(s.exec(select(CronogramaSanitario)).all()) == 1

    def test_animal_da_janela_precisa_estar_na_lista_de_espera(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            _animal(s, "2")
            cal = _regra(s)
            _espera(s, cal, ["1"], data_evento=HOJE)
        r = _criar(c, cal, animais_janela=["2"])
        assert r.status_code == 400 and "lista de espera" in r.json()["detail"].lower()

    def test_sem_animal_ou_baixado_e_recusado(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            _animal(s, "8", ativo=False)
            cal = _regra(s)
            _espera(s, cal, ["1"], data_evento=HOJE)
        assert _criar(c, cal).status_code == 400
        r = _criar(c, cal, animais_janela=["1"], animais_fora=[{"numero_matriz": "8", "motivo": "x"}])
        assert r.status_code == 400

    def test_um_animal_por_agendamento_ativo_por_protocolo_R8(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            for n in ("1", "2", "9"):
                _animal(s, n)
            cal = _regra(s)
            outra = _regra(s, "Outro protocolo")
            _espera(s, cal, ["1", "2"], data_evento=HOJE)
            _espera(s, outra, ["1"], data_evento=HOJE)
        assert _criar(c, cal, animais_janela=["1"]).status_code == 200
        # 1 ja esta agendado neste protocolo: nao entra de novo, nem fora da janela
        r = _criar(c, cal, animais_janela=["2"], animais_fora=[{"numero_matriz": "1", "motivo": "teste"}])
        assert r.status_code == 400 and "1" in r.json()["detail"]
        # em outro protocolo pode
        assert _criar(c, outra, animais_janela=["1"]).status_code == 200

    def test_modo_veterinario_exige_pessoa_e_rascunho_fica_em_montagem(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"], data_evento=HOJE)
        assert _criar(c, cal, animais_janela=["1"], modo_execucao="veterinario").status_code == 400
        r = _criar(c, cal, animais_janela=["1"], rascunho=True)
        assert r.status_code == 200 and r.json()["status"] == "em_montagem"

    def test_agenda_mostra_so_no_dia_e_com_os_dois_tipos_de_animal(self, ctx):
        c, engine = ctx
        dia = HOJE + timedelta(days=3)
        with Session(engine) as s:
            for n in ("1", "9"):
                _animal(s, n)
            cal = _regra(s)
            _espera(s, cal, ["1"], data_evento=HOJE)
        ag = _criar(c, cal, animais_janela=["1"], animais_fora=[{"numero_matriz": "9", "motivo": "Outro"}]).json()
        antes = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        assert not [e for e in antes["eventos"] if str(e["id"]).startswith("cronograma_sanitario_")]
        no_dia = c.get("/agenda/", params={"data": dia.isoformat()}).json()
        ev = next(e for e in no_dia["eventos"] if e["id"] == f"cronograma_sanitario_aplicar_{ag['id']}")
        assert sorted(ev["animais"]) == ["1", "9"] and ev["hora"] == "08:30"

    def test_nao_ressugere_animal_que_ja_esta_em_agendamento(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            _animal(s, "2")
            cal = _regra(s)
            _espera(s, cal, ["1", "2"], data_evento=HOJE)
        _criar(c, cal, animais_janela=["1"])
        from fazenda.rules.cronograma_sanitario import sugerir_animais_em_lote
        with Session(engine) as s:
            sugerir_animais_em_lote(s, s.get(CalendarioSanitario, cal), ["1", "2"], HOJE)
            sugeridos = [(l.numero_matriz) for l in s.exec(
                select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.status == "sugerido")).all()]
        assert sugeridos == ["2"]


class TestAdiarECancelar:
    def _ag(self, c, engine):
        with Session(engine) as s:
            for n in ("1", "2", "9"):
                _animal(s, n)
            cal = _regra(s)
            _espera(s, cal, ["1", "2"], data_evento=HOJE)
        r = _criar(c, cal, animais_janela=["1", "2"], animais_fora=[{"numero_matriz": "9", "motivo": "Outro"}])
        assert r.status_code == 200, r.text
        return cal, r.json()["id"]

    def test_adiar_mantem_animais_status_e_guarda_data_original_R9(self, ctx):
        c, engine = ctx
        cal, ag = self._ag(c, engine)
        devida = _cron(engine, ag).data_original   # a data devida (da lista de espera) fica guardada
        assert devida == HOJE
        nova = HOJE + timedelta(days=10)
        r = c.post(f"/sanidade/cronogramas/{ag}/adiar", json={"nova_data": nova.isoformat(), "hora": "14:00", "motivo": "Chuva"})
        assert r.status_code == 200, r.text
        cron = _cron(engine, ag)
        assert cron.data_evento == nova and cron.data_original == devida and cron.hora == "14:00"
        assert cron.status == "agendado" and cron.modo_execucao == "propria"
        assert {n: l.status for n, l in _linhas(engine, ag).items()} == {"1": "incluido", "2": "incluido", "9": "incluido"}
        assert "Chuva" in (cron.observacao or "")

    def test_adiar_recusa_encerrado_e_lista_de_espera(self, ctx):
        c, engine = ctx
        cal, ag = self._ag(c, engine)
        with Session(engine) as s:
            aberta = _espera(s, cal, [], data_evento=HOJE)
            cron = s.get(CronogramaSanitario, ag)
            cron.status = "concluido"
            s.add(cron)
            s.commit()
        nova = (HOJE + timedelta(days=9)).isoformat()
        assert c.post(f"/sanidade/cronogramas/{ag}/adiar", json={"nova_data": nova}).status_code == 400
        assert c.post(f"/sanidade/cronogramas/{aberta}/adiar", json={"nova_data": nova}).status_code == 400

    def test_cancelar_exige_motivo_e_devolve_animais_da_janela_a_lista_de_espera_R9(self, ctx):
        c, engine = ctx
        cal, ag = self._ag(c, engine)
        assert c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={}).status_code == 422 or \
            c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": " "}).status_code == 400
        assert _cron(engine, ag).status == "agendado"
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Veterinário não pode"})
        assert r.status_code == 200, r.text
        assert r.json()["devolvidos"] == 2
        cron = _cron(engine, ag)
        assert cron.status == "cancelado" and cron.motivo_cancelamento == "Veterinário não pode"
        dados = c.get("/sanidade/cronogramas/lista-espera").json()
        assert sorted(x["numero_matriz"] for g in dados["grupos"] for x in g["animais"]) == ["1", "2"]  # 9 (fora) nao volta
        # some da Agenda no dia
        dia = cron.data_evento
        no_dia = c.get("/agenda/", params={"data": dia.isoformat()}).json()
        assert not [e for e in no_dia["eventos"] if str(e["id"]).startswith("cronograma_sanitario_aplicar_")]
        # e da pra montar outro agendamento com os devolvidos
        assert _criar(c, cal, animais_janela=["1", "2"]).status_code == 200

    def test_cancelar_recusa_lista_de_espera_e_concluido(self, ctx):
        c, engine = ctx
        cal, ag = self._ag(c, engine)
        with Session(engine) as s:
            aberta = _espera(s, cal, [], data_evento=HOJE)
        assert c.post(f"/sanidade/cronogramas/{aberta}/cancelar", json={"motivo": "x"}).status_code == 400

    def test_outra_fazenda_nao_mexe(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "50", fazenda_id=2)
            cal2 = _regra(s, "Y", fazenda_id=2)
            cron2 = _espera(s, cal2, ["50"], data_evento=HOJE, fazenda_id=2, status="agendado")
        assert c.post(f"/sanidade/cronogramas/{cron2}/cancelar", json={"motivo": "x"}).status_code == 404
        assert c.post(f"/sanidade/cronogramas/{cron2}/adiar", json={"nova_data": HOJE.isoformat()}).status_code == 404
        assert _criar(c, cal2, animais_janela=["50"]).status_code == 404


class TestDesconsiderar:
    def test_desconsiderar_exige_motivo_e_tira_da_lista(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            _animal(s, "2")
            cal = _regra(s)
            espera = _espera(s, cal, ["1", "2"], data_evento=HOJE)
        url = "/sanidade/cronogramas/lista-espera/desconsiderar"
        assert c.post(url, json={"calendario_sanitario_id": cal, "animais": ["1"], "motivo": " "}).status_code == 400
        r = c.post(url, json={"calendario_sanitario_id": cal, "animais": ["1"], "motivo": "Já vacinada em outra fazenda"})
        assert r.status_code == 200 and r.json()["desconsiderados"] == 1
        linhas = _linhas(engine, espera)
        assert linhas["1"].status == "excluido" and linhas["1"].motivo == "Já vacinada em outra fazenda"
        assert linhas["2"].status == "sugerido"


class TestEventoDeVidaVaiParaListaDeEspera:
    def _cenario(self, engine):
        with Session(engine) as s:
            s.add(ParametroFazenda(chave="usar_ocorrencia_universal", fazenda_id=None, grupo="sanidade",
                                   label="Universalizar Ocorrencia", valor="true", tipo="bool"))
            s.add(CategoriaManejo(nome="Novilha", dia_min=91, dia_max=730, ordem=1))
            s.add(Animal(numero="55", nome="Bezerra 55", sexo="F", ativo=True, grupo_primario="Bezerras",
                         data_nasc=HOJE - timedelta(days=100), fazenda_id=1))
            s.add(Animal(numero="56", nome="Baixada", sexo="F", ativo=False, grupo_primario="Bezerras",
                         data_nasc=HOJE - timedelta(days=100), fazenda_id=1))
            ev = EventoSanitario(nome="Brucelose", tipo_agendamento="evento", gatilho="nascimento",
                                 produto_padrao="B19", offset_dias=30, fazenda_id=1)
            s.add(ev)
            s.commit()
            s.refresh(ev)
            cal = CalendarioSanitario(evento_sanitario_id=ev.id, categoria_alvo="Bezerras", produto="B19",
                                      frequencia_valor=0, frequencia_unidade="meses", data_evento=HOJE,
                                      usa_cronograma=False, fazenda_id=1)
            s.add(cal)
            s.commit()
            s.refresh(cal)
            return cal.id

    def test_sugerido_na_lista_e_sem_pendencia_antiga_na_agenda(self, ctx):
        c, engine = ctx
        cal = self._cenario(engine)
        assert c.post("/agenda/materializar").status_code == 200
        with Session(engine) as s:
            linhas = s.exec(select(CronogramaSanitarioAnimal)).all()
        assert [(l.numero_matriz, l.status) for l in linhas] == [("55", "sugerido")]
        payload = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        assert not [e for e in payload["eventos"] if str(e["id"]).startswith("evento_sanitario_")]
        assert not [e for e in payload["eventos"] if str(e.get("tipo", "")).startswith("cronograma_sanitario")]
        assert sum(r["quantidade"] for r in payload["lista_espera_sanitaria"]) == 1
        dados = c.get("/sanidade/cronogramas/lista-espera").json()
        g = dados["grupos"][0]
        assert g["calendario_id"] == cal and [x["numero_matriz"] for x in g["animais"]] == ["55"]
        # nasceu ha 100 dias, janela abre aos 30: atrasada ha 70 dias
        assert g["animais"][0]["situacao"] == "atrasada" and g["animais"][0]["dias_atraso"] == 70

    def test_sem_a_flag_continua_como_antes(self, ctx):
        c, engine = ctx
        self._cenario(engine)
        with Session(engine) as s:
            for p in s.exec(select(ParametroFazenda)).all():
                s.delete(p)
            s.commit()
        payload = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        assert [e for e in payload["eventos"] if str(e["id"]).startswith("evento_sanitario_")]
