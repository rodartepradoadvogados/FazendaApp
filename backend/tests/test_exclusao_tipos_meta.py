"""B10: GET /exclusoes/tipos devolve dominio/plural/dica/cadastro (META_TIPOS)."""
import tempfile

from sqlmodel import Session, SQLModel, create_engine
from fastapi.testclient import TestClient

from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


def test_tipos_devolve_metadados():
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

    class _User:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    def _get_session():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session
    main.app.dependency_overrides[get_current_user] = lambda: _User()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        r = c.get("/exclusoes/tipos")
        assert r.status_code == 200
        por_id = {t["id"]: t for t in r.json()}
        assert por_id["financeiro"]["dominio"] == "fin"
        assert por_id["animal"]["dominio"] == "reb"
        assert por_id["pessoa"]["cadastro"] is True
        assert por_id["sanidade"]["dica"]