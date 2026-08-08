"""
Integração da Agenda com o controle de diárias:
- Evento `diaria_trabalho` (diarista ativo, sem folga marcada hoje).
- Regressão dos 3 bugs reais corrigidos no rebuild da Diária:
  Bug A — `DiariaAuditoria` criada pela Agenda sem `fazenda_id` fazia
  qualquer usuário com fazenda_id no token levar 404 eterno ao responder.
  Bug B — `eventos_diaria_fim`/`diaria_auditorias_pendentes` sem filtro de
  `fazenda_id` vazavam dados entre fazendas.
  Bug D — uma diária que passou a ser controlada pelo calendário
  (`controle_por_dia_desde` setado) para de gerar novas `DiariaAuditoria`.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, Diaria, DiariaAuditoria, DiariaDia, Pessoa


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


class _FakeOperadorSemFinanceiro:
    id = 2
    papel = "operador"
    permissoes = "agenda,sanidade"
    ativo = True
    username = "operador_sanidade"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


@pytest.fixture
def client_multi():
    """Duas fazendas com ContratoFazenda ativo — mesmo padrão de
    test_central_protocolos_fazenda.py/test_exclusao_pessoal.py.
    `make_client(id)` troca a fazenda "atual" a cada chamada."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(ContratoFazenda(fazenda_id=2, status="ativo"))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    def _make_client(fazenda_id: int) -> TestClient:
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
        return TestClient(main.app)

    yield engine, _make_client

    main.app.dependency_overrides.clear()


def _pessoa(engine, nome: str = "Diarista Teste", fazenda_id: int | None = None) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Diarista", fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _diaria(
    engine, pessoa_id: int, dias_atras: int = 4, status: str = "ativo",
    fazenda_id: int | None = None, data_fim: date | None = None,
) -> int:
    with Session(engine) as s:
        d = Diaria(
            pessoa_id=pessoa_id, valor_diaria=100.0, data_inicio=date.today() - timedelta(days=dias_atras),
            status=status, fazenda_id=fazenda_id, data_fim=data_fim,
        )
        s.add(d)
        s.commit()
        s.refresh(d)
        return d.id


def _eventos_diaria_trabalho(resposta_json: dict) -> list[dict]:
    return [e for e in resposta_json["eventos"] if e.get("tipo") == "diaria_trabalho"]


class TestEventoDiariaTrabalho:
    def test_diaria_ativa_sem_folga_aparece_hoje(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        diaria_id = _diaria(engine, pessoa_id)
        r = c.get("/agenda/")
        assert r.status_code == 200
        eventos = _eventos_diaria_trabalho(r.json())
        assert len(eventos) == 1
        assert eventos[0]["diaria_id"] == diaria_id
        assert eventos[0]["categoria"] == "Gestão/Financeiro"

    def test_folga_marcada_hoje_remove_o_evento(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        diaria_id = _diaria(engine, pessoa_id)
        with Session(engine) as s:
            s.add(DiariaDia(diaria_id=diaria_id, data=date.today(), trabalhado=False))
            s.commit()
        r = c.get("/agenda/")
        assert _eventos_diaria_trabalho(r.json()) == []

    def test_diaria_encerrada_nao_gera_evento(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        _diaria(engine, pessoa_id, status="encerrado")
        r = c.get("/agenda/")
        assert _eventos_diaria_trabalho(r.json()) == []

    def test_diaria_com_data_fim_no_passado_nao_gera_evento(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        _diaria(engine, pessoa_id, dias_atras=10, data_fim=date.today() - timedelta(days=2))
        r = c.get("/agenda/")
        assert _eventos_diaria_trabalho(r.json()) == []


class TestPermissaoEventoDiariaTrabalho:
    def test_operador_sem_financeiro_nao_ve_evento(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        _diaria(engine, pessoa_id)
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _FakeOperadorSemFinanceiro()
        try:
            r = c.get("/agenda/")
            assert _eventos_diaria_trabalho(r.json()) == []
        finally:
            main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()


class TestIsolamentoMultiTenantAgenda:
    def test_diaria_da_fazenda_a_nao_vaza_pra_agenda_da_fazenda_b(self, client_multi):
        engine, make_client = client_multi
        pessoa_id = _pessoa(engine, fazenda_id=1)
        _diaria(engine, pessoa_id, fazenda_id=1)

        c2 = make_client(2)
        r2 = c2.get("/agenda/")
        assert _eventos_diaria_trabalho(r2.json()) == []

        c1 = make_client(1)
        r1 = c1.get("/agenda/")
        assert len(_eventos_diaria_trabalho(r1.json())) == 1


class TestBugARegressaoAuditoriaRespondivel:
    """Bug A: DiariaAuditoria criada pela Agenda sem fazenda_id -> 404 eterno
    ao tentar responder, pra qualquer usuário cujo token carregue fazenda_id."""

    def test_auditoria_gerada_sob_fazenda_pode_ser_respondida(self, client_multi):
        engine, make_client = client_multi
        pessoa_id = _pessoa(engine, fazenda_id=1)
        diaria_id = _diaria(engine, pessoa_id, dias_atras=10, fazenda_id=1)
        with Session(engine) as s:
            d = s.get(Diaria, diaria_id)
            d.auditar_periodicamente = True
            d.frequencia_auditoria = "semanal"
            d.dia_semana_auditoria = date.today().weekday()
            s.add(d)
            s.commit()

        c1 = make_client(1)
        r = c1.get("/agenda/")  # dispara _gerar_auditorias_diarias
        assert r.status_code == 200

        with Session(engine) as s:
            auditoria = s.exec(select(DiariaAuditoria).where(DiariaAuditoria.diaria_id == diaria_id)).first()
            assert auditoria is not None
            assert auditoria.fazenda_id == 1  # Bug A: nascia None
            auditoria_id = auditoria.id

        r2 = c1.put(f"/cadastro/diarias/auditorias/{auditoria_id}", json={"dias_trabalhados": 5})
        assert r2.status_code == 200, r2.text  # Bug A fazia isso dar 404


class TestBugDCalendarioSuprimeAuditoriaAutomatica:
    def test_diaria_calendar_controlada_nao_gera_novas_auditorias(self, client_multi):
        engine, make_client = client_multi
        pessoa_id = _pessoa(engine, fazenda_id=1)
        diaria_id = _diaria(engine, pessoa_id, dias_atras=10, fazenda_id=1)
        with Session(engine) as s:
            d = s.get(Diaria, diaria_id)
            d.auditar_periodicamente = True
            d.frequencia_auditoria = "semanal"
            d.dia_semana_auditoria = date.today().weekday()
            d.controle_por_dia_desde = date.today() - timedelta(days=10)
            s.add(d)
            s.commit()

        c1 = make_client(1)
        r = c1.get("/agenda/")
        assert r.status_code == 200

        with Session(engine) as s:
            auditorias = s.exec(select(DiariaAuditoria).where(DiariaAuditoria.diaria_id == diaria_id)).all()
            assert auditorias == []
