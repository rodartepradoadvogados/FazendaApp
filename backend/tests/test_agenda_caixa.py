"""Agenda × Caixa dos funcionários: termo de retenção pendente e rateio do PL chegando."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401
from fazenda.models import CaixaRateio, CaixaRetencao, CaixaTime, CaixaTimeMovimento, Pessoa
from fazenda.rules import caixa_time as regras


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    yield TestClient(main.app), engine
    main.app.dependency_overrides.clear()


def _descricoes(c, dia: date) -> list[str]:
    r = c.get(f"/agenda/?data={dia.isoformat()}&dias=3")
    assert r.status_code == 200, r.text
    return [e["descricao"] for e in r.json()["eventos"]]


def test_termo_pendente_aparece_na_agenda(setup):
    c, engine = setup
    with Session(engine) as s:
        p = Pessoa(nome="Ana Souza", tipo="Funcionário", ativo=True)
        s.add(p)
        s.commit()
        s.refresh(p)
        s.add(CaixaRetencao(pessoa_id=p.id, forma="fixo", valor=100, inicio=date(2026, 1, 1), autorizada=True))
        s.commit()
    assert any("termo de autorização de retenção" in d and "Ana Souza" in d for d in _descricoes(c, date(2026, 8, 16)))


def test_rateio_proximo_aparece_e_some_com_rascunho(setup):
    c, engine = setup
    _, _, entrega = regras.periodo_em_apuracao(date(2026, 11, 20), [(6, 1), (12, 1)])  # 01/12/2026
    with Session(engine) as s:
        t = CaixaTime(nome="Turma da ordenha")
        s.add(t)
        s.commit()
        s.refresh(t)
        s.add(CaixaTimeMovimento(time_id=t.id, tipo="deposito", valor=800.0, data=date(2026, 9, 1), motivo="x"))
        s.commit()
        tid = t.id
    assert any("rateio do PL" in d and "Turma da ordenha" in d for d in _descricoes(c, entrega - timedelta(days=5)))
    assert not any("rateio do PL" in d for d in _descricoes(c, entrega - timedelta(days=60)))
    with Session(engine) as s:
        s.add(CaixaRateio(time_id=tid, periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 11, 30), data_entrega=entrega, total=800.0))
        s.commit()
    assert not any("rateio do PL" in d for d in _descricoes(c, entrega - timedelta(days=5)))
