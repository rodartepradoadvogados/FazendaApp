"""
Data da próxima visita reprodutiva DEFINIDA pelo usuário (rules/visita_reprodutiva.py).

Uma regra só, lida por todos: o motor da Agenda, o comunicado da Agenda ("Amanhã: visita reprodutiva" / "Visita
reprodutiva"), a projeção da Agenda Reprodutiva (Insights), as candidatas projetadas de IATF e a tela de Parâmetros.
Prioridade: data definida (enquanto não passou) > último serviço + intervalo > nenhuma.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ParametroFazenda, Servico
from fazenda.rules.agenda_engine import AgendaEngine
from fazenda.rules.parametros import DEFINICOES
from fazenda.rules.visita_reprodutiva import CHAVE_DATA, proxima_visita

HOJE = date.today()


class TestRegra:
    def test_definida_vence_o_calculo_enquanto_nao_passou(self):
        ultimo = HOJE - timedelta(days=5)
        assert proxima_visita(ultimo, 21, HOJE, HOJE + timedelta(days=3)) == (HOJE + timedelta(days=3), "definida")
        assert proxima_visita(ultimo, 21, HOJE, HOJE) == (HOJE, "definida")  # hoje ainda vale

    def test_definida_no_passado_ou_ausente_volta_ao_calculo(self):
        ultimo = HOJE - timedelta(days=5)
        assert proxima_visita(ultimo, 21, HOJE, HOJE - timedelta(days=1)) == (ultimo + timedelta(days=21), "calculada")
        assert proxima_visita(ultimo, 21, HOJE, None) == (ultimo + timedelta(days=21), "calculada")

    def test_intervalo_zero_desliga_o_calculo_mas_nao_a_data_definida(self):
        assert proxima_visita(HOJE, 0, HOJE, None) == (None, None)
        assert proxima_visita(None, 21, HOJE, None) == (None, None)
        assert proxima_visita(None, 0, HOJE, HOJE + timedelta(days=9)) == (HOJE + timedelta(days=9), "definida")


class TestMotorDaAgenda:
    def _calcular(self, **extra):
        return AgendaEngine().calcular(
            data_referencia=HOJE, animais=[], servicos=extra.pop("servicos", []), partos=[],
            estoque=[], contas=[], eventos_manuais=[], **extra)

    def test_data_definida_gera_o_item_mesmo_sem_nenhum_servico(self):
        r = self._calcular(proxima_visita_definida=HOJE + timedelta(days=4))
        assert r.proxima_visita_iatf == HOJE + timedelta(days=4)
        visitas = [e for e in r.eventos if "Visita reprodutiva" in e.descricao]
        assert len(visitas) == 1 and visitas[0].data == HOJE + timedelta(days=4)
        assert "definida" in visitas[0].descricao

    def test_data_definida_substitui_a_calculada(self):
        servico = {"numero_matriz": "9", "data_servico": HOJE - timedelta(days=2), "ult_ocorrencia": 1}
        r = self._calcular(servicos=[servico], proxima_visita_definida=HOJE + timedelta(days=30))
        assert r.proxima_visita_iatf == HOJE + timedelta(days=30)  # e não +19 (21 - 2)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # parametros.get_param* leem de `fazenda.database.engine`, não da sessão injetada (mesmo padrão de test_ajuste_proxima_bst.py)
    monkeypatch.setattr(database, "engine", engine)
    with Session(engine) as s:
        for item in DEFINICOES:
            s.add(ParametroFazenda(chave=item["chave"], grupo=item["grupo"], label=item["label"],
                                   valor=str(item["valor"]), tipo=item.get("tipo", "int"), unidade=item.get("unidade")))
        s.add(Animal(numero="300", grupo_primario="01 - Alta", del_dias=70, sexo="F", ativo=True))
        s.add(Servico(numero_matriz="300", data_servico=HOJE - timedelta(days=5), ult_ocorrencia=1))
        s.commit()

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = None

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _param(engine) -> str | None:
    with Session(engine) as s:
        row = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == CHAVE_DATA)).first()
        return row.valor if row else None


class TestEndpointEAgendaReprodutiva:
    def test_ida_e_volta_definir_ler_limpar(self, client):
        c, engine = client
        base = c.get("/reproducao/agenda-veterinario").json()
        assert base["origem_visita_reprodutiva"] == "calculada"
        assert base["proxima_visita_reprodutiva"] == (HOJE - timedelta(days=5) + timedelta(days=21)).isoformat()

        nova = HOJE + timedelta(days=6)
        r = c.put("/reproducao/visita-reprodutiva", json={"data": nova.isoformat()})
        assert r.status_code == 200, r.text
        assert r.json()["proxima_visita_reprodutiva"] == nova.isoformat() and r.json()["origem_visita_reprodutiva"] == "definida"
        assert _param(engine) == nova.isoformat()  # gravou no parâmetro (aparece em Configurações > Parâmetros)

        depois = c.get("/reproducao/agenda-veterinario").json()
        assert depois["proxima_visita_reprodutiva"] == nova.isoformat() and depois["origem_visita_reprodutiva"] == "definida"
        # a projeção das candidatas de IATF usa a MESMA data
        assert c.get("/reproducao/protocolo-iatf/candidatas").json()["proxima_visita_iatf"] == nova.isoformat()

        r2 = c.put("/reproducao/visita-reprodutiva", json={"data": None})
        assert r2.status_code == 200 and r2.json()["origem_visita_reprodutiva"] == "calculada"
        assert _param(engine) == ""

    def test_nao_aceita_data_no_passado(self, client):
        c, _ = client
        r = c.put("/reproducao/visita-reprodutiva", json={"data": (HOJE - timedelta(days=1)).isoformat()})
        assert r.status_code == 400

    def test_data_definida_que_ja_passou_volta_ao_calculo(self, client):
        c, engine = client
        with Session(engine) as s:
            row = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == CHAVE_DATA)).first()
            row.valor = (HOJE - timedelta(days=2)).isoformat()
            s.add(row)
            s.commit()
        d = c.get("/reproducao/agenda-veterinario").json()
        assert d["origem_visita_reprodutiva"] == "calculada"


class TestComunicadoNaAgenda:
    def _definir(self, c, dias: int):
        assert c.put("/reproducao/visita-reprodutiva", json={"data": (HOJE + timedelta(days=dias)).isoformat()}).status_code == 200

    def _agenda(self, c):
        r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=30")
        assert r.status_code == 200, r.text
        return r.json()

    def test_na_vespera_aparece_amanha_visita_reprodutiva(self, client):
        c, _ = client
        self._definir(c, 1)
        eventos = self._agenda(c)["eventos"]
        com = [e for e in eventos if e.get("tipo") == "visita_reprodutiva"]
        assert len(com) == 1
        assert com[0]["descricao"] == "Amanhã: visita reprodutiva" and com[0]["comunicado"] is True
        assert com[0]["data_visita"] == (HOJE + timedelta(days=1)).isoformat()
        assert com[0]["data"] == HOJE.isoformat()  # o aviso vale HOJE (o app do celular só lista data <= hoje)
        # sem duplicar com o item-tarefa do motor
        assert not [e for e in eventos if e["descricao"].startswith("Visita reprodutiva —")]

    def test_no_dia_aparece_visita_reprodutiva(self, client):
        c, _ = client
        self._definir(c, 0)
        com = [e for e in self._agenda(c)["eventos"] if e.get("tipo") == "visita_reprodutiva"]
        assert len(com) == 1 and com[0]["descricao"] == "Visita reprodutiva"

    def test_longe_ainda_nao_e_comunicado(self, client):
        c, _ = client
        self._definir(c, 5)
        eventos = self._agenda(c)["eventos"]
        assert not [e for e in eventos if e.get("tipo") == "visita_reprodutiva"]
        assert [e for e in eventos if e["descricao"].startswith("Visita reprodutiva —")]  # segue como item normal da agenda

    def test_mudou_a_data_o_comunicado_acompanha(self, client):
        c, _ = client
        self._definir(c, 1)
        assert [e for e in self._agenda(c)["eventos"] if e.get("tipo") == "visita_reprodutiva"]
        self._definir(c, 8)
        assert not [e for e in self._agenda(c)["eventos"] if e.get("tipo") == "visita_reprodutiva"]

    def test_comunicado_nao_pode_ser_marcado_como_realizado(self, client):
        c, _ = client
        self._definir(c, 1)
        com = [e for e in self._agenda(c)["eventos"] if e.get("tipo") == "visita_reprodutiva"][0]
        r = c.post("/agenda/realizados", json={"evento_id": com["id"], "categoria": "Reprodutivo", "descricao": com["descricao"]})
        assert r.status_code == 400


class TestAgendaDiaADia:
    """A Agenda abre no "Dia a dia" (GET /agenda/dia), que descarta comunicados: a visita vai à parte, em `comunicados_dia`."""

    def _dia(self, c):
        r = c.get(f"/agenda/dia?data={HOJE.isoformat()}")
        assert r.status_code == 200, r.text
        return r.json()

    def test_visita_na_vespera_vem_em_comunicados_dia_e_nao_conta_como_aviso(self, client):
        c, _ = client
        assert c.put("/reproducao/visita-reprodutiva", json={"data": (HOJE + timedelta(days=1)).isoformat()}).status_code == 200
        d = self._dia(c)
        assert [e["descricao"] for e in d["comunicados_dia"]] == ["Amanhã: visita reprodutiva"]
        assert d["resumo"]["avisos"] == 0
        # nem a tarefa do motor nem o comunicado entram na lista de tarefas duplicados
        assert not [e for e in d["eventos"] if e["descricao"].lower().startswith("visita reprodutiva") or e.get("tipo") == "visita_reprodutiva"]

    def test_visita_longe_nao_gera_comunicado_no_dia_a_dia(self, client):
        c, _ = client
        assert c.put("/reproducao/visita-reprodutiva", json={"data": (HOJE + timedelta(days=6)).isoformat()}).status_code == 200
        assert self._dia(c)["comunicados_dia"] == []


class TestUltimaVisitaInformada:
    """Data da última visita reprodutiva informada pelo usuário: âncora da contagem dos dias entre visitas."""

    def test_ultima_visita_ontem_ancora_a_proxima(self):
        ontem = HOJE - timedelta(days=1)
        servico_antigo = HOJE - timedelta(days=9)
        assert proxima_visita(servico_antigo, 21, HOJE, None, ontem) == (ontem + timedelta(days=21), "calculada")
        assert proxima_visita(None, 21, HOJE, None, ontem) == (ontem + timedelta(days=21), "calculada")

    def test_servico_mais_novo_que_a_ultima_visita_informada_volta_a_ser_a_ancora(self):
        informada, servico = HOJE - timedelta(days=10), HOJE - timedelta(days=2)
        assert proxima_visita(servico, 21, HOJE, None, informada) == (servico + timedelta(days=21), "calculada")

    def test_ciclo_fixo_pula_ciclos_vencidos_para_o_comunicado_nao_sumir(self):
        informada = HOJE - timedelta(days=50)  # 50 dias atrás, a cada 21: ciclos em -29, -8, +13
        assert proxima_visita(None, 21, HOJE, None, informada) == (HOJE + timedelta(days=13), "calculada")
        exata = HOJE - timedelta(days=42)  # a visita calculada cai exatamente hoje: permanece hoje
        assert proxima_visita(None, 21, HOJE, None, exata) == (HOJE, "calculada")

    def test_data_definida_continua_vencendo_a_ultima_visita(self):
        definida = HOJE + timedelta(days=3)
        assert proxima_visita(None, 21, HOJE, definida, HOJE - timedelta(days=1)) == (definida, "definida")

    def test_intervalo_zero_desliga_tambem_com_ultima_visita(self):
        assert proxima_visita(None, 0, HOJE, None, HOJE - timedelta(days=1)) == (None, None)

    def test_parametro_existe_no_seed_como_data_no_grupo_manejo(self):
        d = {i["chave"]: i for i in DEFINICOES}["ultima_visita_reprodutiva_data"]
        assert d["tipo"] == "date" and d["grupo"] == "manejo"

    def test_motor_usa_a_ultima_visita_informada(self):
        ontem = HOJE - timedelta(days=1)
        r = AgendaEngine().calcular(
            data_referencia=HOJE, animais=[], servicos=[], partos=[], estoque=[], contas=[], eventos_manuais=[],
            ultima_visita_informada=ontem)
        assert r.proxima_visita_iatf == ontem + timedelta(days=21)


class TestUltimaVisitaApi:
    def test_ida_e_volta_ultima_visita_ontem(self, client):
        c, engine = client
        ontem = HOJE - timedelta(days=1)
        r = c.put("/reproducao/visita-reprodutiva", json={"ultima": ontem.isoformat()})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ultima_visita_reprodutiva"] == ontem.isoformat()
        assert corpo["proxima_visita_reprodutiva"] == (ontem + timedelta(days=21)).isoformat()
        with Session(engine) as s:
            row = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "ultima_visita_reprodutiva_data")).first()
            assert row.valor == ontem.isoformat()
        d = c.get("/reproducao/agenda-veterinario").json()
        assert d["ultima_visita_reprodutiva"] == ontem.isoformat()
        assert d["ultima_visita_vigente"] == ontem.isoformat()
        assert d["proxima_visita_reprodutiva"] == (ontem + timedelta(days=21)).isoformat()
        assert d["origem_visita_reprodutiva"] == "calculada"

    def test_campo_ausente_nao_mexe_no_outro(self, client):
        c, engine = client
        prox = HOJE + timedelta(days=8)
        assert c.put("/reproducao/visita-reprodutiva", json={"data": prox.isoformat()}).status_code == 200
        r = c.put("/reproducao/visita-reprodutiva", json={"ultima": (HOJE - timedelta(days=1)).isoformat()})
        assert r.json()["definida"] == prox.isoformat() and r.json()["origem_visita_reprodutiva"] == "definida"
        r = c.put("/reproducao/visita-reprodutiva", json={"ultima": None})  # limpa só a última
        assert r.json()["ultima_visita_reprodutiva"] is None and r.json()["definida"] == prox.isoformat()

    def test_salva_as_duas_de_uma_vez(self, client):
        c, _ = client
        ontem, prox = HOJE - timedelta(days=1), HOJE + timedelta(days=4)
        r = c.put("/reproducao/visita-reprodutiva", json={"ultima": ontem.isoformat(), "data": prox.isoformat()})
        assert r.status_code == 200
        assert r.json()["ultima_visita_reprodutiva"] == ontem.isoformat() and r.json()["proxima_visita_reprodutiva"] == prox.isoformat()

    def test_ultima_visita_no_futuro_e_recusada(self, client):
        c, _ = client
        assert c.put("/reproducao/visita-reprodutiva", json={"ultima": (HOJE + timedelta(days=1)).isoformat()}).status_code == 400

    @staticmethod
    def _sem_servicos(engine):
        # a fixture tem um serviço de 5 dias atrás, que (sendo mais novo) ancoraria a contagem no lugar da última visita informada
        with Session(engine) as s:
            for sv in s.exec(select(Servico)).all():
                s.delete(sv)
            s.commit()

    def test_comunicado_na_vespera_pela_ultima_visita(self, client):
        c, engine = client
        self._sem_servicos(engine)
        # última visita há 20 dias, intervalo 21 → a próxima é amanhã: "Amanhã: visita reprodutiva"
        assert c.put("/reproducao/visita-reprodutiva", json={"ultima": (HOJE - timedelta(days=20)).isoformat()}).status_code == 200
        com = [e for e in c.get(f"/agenda/?data={HOJE.isoformat()}&dias=30").json()["eventos"] if e.get("tipo") == "visita_reprodutiva"]
        assert len(com) == 1 and com[0]["descricao"] == "Amanhã: visita reprodutiva"
        assert com[0]["data_visita"] == (HOJE + timedelta(days=1)).isoformat() and com[0]["origem_visita"] == "calculada"

    def test_comunicado_no_dia_pela_ultima_visita(self, client):
        c, engine = client
        self._sem_servicos(engine)
        assert c.put("/reproducao/visita-reprodutiva", json={"ultima": (HOJE - timedelta(days=21)).isoformat()}).status_code == 200
        com = [e for e in c.get(f"/agenda/?data={HOJE.isoformat()}&dias=30").json()["eventos"] if e.get("tipo") == "visita_reprodutiva"]
        assert len(com) == 1 and com[0]["descricao"] == "Visita reprodutiva"
