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
