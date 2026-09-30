"""
Agenda x preventivo (regras R1/R2 do dono — docs/agents/auditoria-preventivo-
agenda/planejamento/06-planejamento-unificado.md, secao 7):

  R1  animal na janela de aplicacao/lista de espera NUNCA vira tarefa da Agenda
      (no maximo um resumo "N na lista de espera", atalho para Protocolos);
  R2  so o AGENDAMENTO (cronograma agendado, com modo/data definidos) entra na
      Agenda, no dia da aplicacao;
  --  GET /agenda nao escreve no banco (a materializacao de cronogramas/
      sugestoes/recorrencias e feita por POST /agenda/materializar);
  --  com a flag `usar_ocorrencia_universal`, a regra nao gera pendencia antiga
      (`calendario_sanitario_*`) E ocorrencia ao mesmo tempo, e animal ja
      vacinado na epoca nao vira "sugerido".
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    AgendaManual, Animal, CalendarioSanitario, CategoriaManejo, ChecklistItem, ContratoFazenda,
    ContratoFazendaModulo, CronogramaSanitario, CronogramaSanitarioAnimal, EventoSanitario, Fazenda,
    ParametroFazenda, Sanidade,
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
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
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


def _regra(s: Session, *, usa_cronograma: bool = True, produto: str = "Vacina X", tipo: str = "epoca",
           categoria: str = "Novilha", data_evento: date | None = None) -> int:
    n = len(s.exec(select(EventoSanitario)).all())
    ev = EventoSanitario(nome=f"Vacina X {n}", tipo_agendamento=tipo, fazenda_id=1)
    s.add(ev)
    s.commit()
    s.refresh(ev)
    cal = CalendarioSanitario(
        evento_sanitario_id=ev.id, categoria_alvo=categoria, produto=produto, frequencia_valor=6,
        frequencia_unidade="meses", data_evento=data_evento or (HOJE + timedelta(days=20)),
        usa_cronograma=usa_cronograma, fazenda_id=1,
    )
    s.add(cal)
    s.commit()
    s.refresh(cal)
    return cal.id


def _cron(s: Session, cal_id: int, *, status: str, data_evento: date, animais: dict[str, str]) -> int:
    cron = CronogramaSanitario(
        calendario_sanitario_id=cal_id, data_evento=data_evento, status=status, fazenda_id=1,
        modo_execucao="propria" if status == "agendado" else None,
    )
    s.add(cron)
    s.commit()
    s.refresh(cron)
    for numero, st in animais.items():
        s.add(CronogramaSanitarioAnimal(
            cronograma_id=cron.id, numero_matriz=numero, status=st, data_sugestao=HOJE, fazenda_id=1,
        ))
    s.commit()
    return cron.id


def _agenda(c, data: date = HOJE) -> dict:
    r = c.get("/agenda/", params={"data": data.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def _ids_cronograma(payload: dict) -> list[str]:
    return [e["id"] for e in payload["eventos"] if str(e["id"]).startswith("cronograma_sanitario_")]


def _flag_universal(engine) -> None:
    with Session(engine) as s:
        s.add(ParametroFazenda(chave="usar_ocorrencia_universal", fazenda_id=None, grupo="sanidade",
                               label="Universalizar Ocorrencia", valor="true", tipo="bool"))
        s.commit()


class TestListaDeEsperaNaoEhTarefa:
    def test_animal_sugerido_nao_aparece_na_agenda_nem_como_modo(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            cal = _regra(s)
            # cronograma aberto ha dias, data prevista dentro da janela de aviso (urgente)
            _cron(s, cal, status="aberto", data_evento=HOJE + timedelta(days=2), animais={"101": "sugerido", "102": "sugerido"})
        payload = _agenda(c)
        assert _ids_cronograma(payload) == []
        assert not [e for e in payload["eventos"] if str(e.get("tipo", "")).startswith("cronograma_sanitario")]
        # atalho de resumo, fora de `eventos` (nao e tarefa)
        resumo = payload["lista_espera_sanitaria"]
        assert sum(r["quantidade"] for r in resumo) == 2

    def test_cronograma_agendado_aparece_so_na_data(self, ctx):
        c, engine = ctx
        dia = HOJE + timedelta(days=5)
        with Session(engine) as s:
            cal = _regra(s, data_evento=dia)
            cron = _cron(s, cal, status="agendado", data_evento=dia, animais={"101": "incluido", "102": "sugerido"})
        assert _ids_cronograma(_agenda(c, HOJE)) == []
        assert _ids_cronograma(_agenda(c, dia - timedelta(days=1))) == []
        no_dia = _agenda(c, dia)
        assert _ids_cronograma(no_dia) == [f"cronograma_sanitario_aplicar_{cron}"]
        evento = next(e for e in no_dia["eventos"] if e["id"].startswith("cronograma_sanitario_aplicar_"))
        assert evento["animais"] == ["101"]  # o 'sugerido' (lista de espera) nao entra
        assert evento["data"] == dia.isoformat()


class TestGetAgendaSomenteLeitura:
    def test_duas_chamadas_nao_escrevem_no_banco(self, ctx):
        c, engine = ctx
        _flag_universal(engine)
        with Session(engine) as s:
            s.add(Animal(numero="55", data_nasc=HOJE - timedelta(days=100), ativo=True, sexo="F", fazenda_id=1))
            s.add(CategoriaManejo(nome="Novilha", dia_min=91, dia_max=730, ordem=1))
            _regra(s)                                  # regra SEM cronograma ainda (tentacao de criar no GET)
            _regra(s, usa_cronograma=False)
            s.add(AgendaManual(  # recorrente vencido (tentacao de gerar a proxima ocorrencia no GET)
                data_evento=HOJE - timedelta(days=40), descricao="Lembrete", categoria="Atividades",
                recorrente=True, intervalo_dias=7, fazenda_id=1,
            ))
            s.commit()

        escritas: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def _espia(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().split(None, 1)[0].upper() in ("INSERT", "UPDATE", "DELETE"):
                escritas.append(statement[:120])

        tabelas = (CronogramaSanitario, CronogramaSanitarioAnimal, ChecklistItem, AgendaManual)

        def _contagens() -> list[int]:
            with Session(engine) as s:
                return [s.exec(select(func.count()).select_from(t)).one() for t in tabelas]

        antes = _contagens()
        _agenda(c)
        _agenda(c)
        assert escritas == [], escritas
        assert _contagens() == antes

    def test_materializar_cria_e_e_idempotente(self, ctx):
        c, engine = ctx
        _flag_universal(engine)
        with Session(engine) as s:
            s.add(Animal(numero="55", data_nasc=HOJE - timedelta(days=100), ativo=True, sexo="F", fazenda_id=1))
            s.add(CategoriaManejo(nome="Novilha", dia_min=91, dia_max=730, ordem=1))
            _regra(s)
        assert c.post("/agenda/materializar").status_code == 200
        with Session(engine) as s:
            n_cron = len(s.exec(select(CronogramaSanitario)).all())
            linhas = s.exec(select(CronogramaSanitarioAnimal)).all()
        assert n_cron == 1
        assert [(l.numero_matriz, l.status) for l in linhas] == [("55", "sugerido")]
        assert c.post("/agenda/materializar").status_code == 200
        with Session(engine) as s:
            assert len(s.exec(select(CronogramaSanitario)).all()) == 1
            assert len(s.exec(select(CronogramaSanitarioAnimal)).all()) == 1


class TestDedupeEpocaUniversal:
    def test_animal_ja_vacinado_na_epoca_nao_vira_sugerido_nem_duplica_pendencia(self, ctx):
        c, engine = ctx
        _flag_universal(engine)
        with Session(engine) as s:
            for n in ("55", "56"):
                s.add(Animal(numero=n, data_nasc=HOJE - timedelta(days=100), ativo=True, sexo="F", fazenda_id=1))
            s.add(CategoriaManejo(nome="Novilha", dia_min=91, dia_max=730, ordem=1))
            cal = _regra(s, usa_cronograma=False, data_evento=HOJE)
            s.add(Sanidade(  # 55 ja tomou a vacina da regra dentro do ciclo de 6 meses
                numero_matriz="55", produto="Vacina X", data_aplicacao=HOJE - timedelta(days=20),
                natureza="preventivo", fazenda_id=1,
            ))
            s.commit()
        assert c.post("/agenda/materializar").status_code == 200
        with Session(engine) as s:
            sugeridos = {l.numero_matriz for l in s.exec(select(CronogramaSanitarioAnimal)).all()}
        assert sugeridos == {"56"}

        payload = _agenda(c)
        # ocorrencia governa a regra: nenhuma pendencia antiga E nenhum card de ocorrencia em `eventos`
        assert [e for e in payload["eventos"] if e.get("calendario_id") == cal] == []
        assert [e for e in payload["eventos"] if str(e["id"]).startswith(f"calendario_sanitario_{cal}__")] == []
        assert _ids_cronograma(payload) == []
        assert sum(r["quantidade"] for r in payload["lista_espera_sanitaria"]) == 1
