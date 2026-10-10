"""Lote (B10): impacto e confirmar aceitam {itens:[...]} (até 50)."""
import tempfile

from sqlmodel import Session, SQLModel, create_engine
from fastapi.testclient import TestClient

from fazenda.models import ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


def _client():
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    database.engine = engine
    main.engine = engine

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for m in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=m, preco=0.0, ativo=True))
        s.commit()

    def _get_session():
        with Session(engine) as session:
            yield session

    class _User:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session
    main.app.dependency_overrides[get_current_user] = lambda: _User()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    return TestClient(main.app), engine


def test_lote_impacto_e_confirmar():
    c, engine = _client()
    with Session(engine) as s:
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-A", fazenda_id=1, descricao="A", valor_total=10.0))
        s.add(ContaGerencial(id=2, numero_lancamento="LC-2026-B", fazenda_id=1, descricao="B", valor_total=20.0))
        s.commit()

    r = c.post("/exclusoes/impacto", json={"itens": [
        {"tipo": "financeiro", "id": "1"},
        {"tipo": "financeiro", "id": "2"},
    ]})
    assert r.status_code == 200, r.text
    assert not r.json().get("bloqueia"), "dois lançamentos comuns não bloqueiam"

    r = c.post("/exclusoes/confirmar", json={
        "itens": [{"tipo": "financeiro", "id": "1"}, {"tipo": "financeiro", "id": "2"}],
        "motivo": "teste lote",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "excluido"

    with Session(engine) as s:
        assert s.get(ContaGerencial, 1) is None
        assert s.get(ContaGerencial, 2) is None


def test_lote_operador_forbidden():
    c, engine = _client()
    import main
    from fazenda.auth import get_current_user

    class _Operador:
        id = 2
        papel = "operador"
        ativo = True
        username = "op"

    main.app.dependency_overrides[get_current_user] = lambda: _Operador()

    r = c.post("/exclusoes/confirmar", json={"itens": [{"tipo": "financeiro", "id": "1"}]})
    assert r.status_code == 403