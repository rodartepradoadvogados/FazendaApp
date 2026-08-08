"""
G11 — Safra ganha um tipo (`safra`) no motor genérico de exclusões
(rules/exclusao_tipos/agricultura.py). É o gap mais simples dos 17: Safra não
tem nenhuma FK apontando para ela, então a exclusão não tem efeito colateral
nenhum — só sai do banco.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, ContratoFazenda, Safra


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import exigir_admin, get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


@pytest.fixture
def client_fazenda():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _criar_safra(engine, *, fazenda_id=None, nome="Silagem Milho 2026") -> int:
    with Session(engine) as s:
        safra = Safra(
            nome=nome, centro_custo="Agricultura", data_inicio=date(2026, 1, 1), data_fim=date(2026, 3, 1),
            hectares=50, toneladas_produzidas=1200, fazenda_id=fazenda_id,
        )
        s.add(safra)
        s.commit()
        s.refresh(safra)
        return safra.id


class TestExcluirSafra:
    def test_tipo_safra_aparece_em_tipos(self, client):
        c, _ = client
        r = c.get("/exclusoes/tipos")
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()}
        assert "safra" in ids

    def test_impacto_lista_safra_sem_efeito_colateral(self, client):
        c, engine = client
        sid = _criar_safra(engine)
        r = c.post("/exclusoes/impacto", json={"tipo": "safra", "id": str(sid)})
        assert r.status_code == 200
        impacto = r.json()["impacto"]
        assert any("Silagem Milho 2026" in i for i in impacto)
        # A prévia não altera nada.
        with Session(engine) as s:
            assert s.get(Safra, sid) is not None

    def test_confirmar_remove_a_safra_e_some_do_get_safras(self, client):
        c, engine = client
        sid = _criar_safra(engine)

        r = c.post("/exclusoes/confirmar", json={"tipo": "safra", "id": str(sid)})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"

        with Session(engine) as s:
            assert s.get(Safra, sid) is None

        r2 = c.get("/safras/")
        assert r2.status_code == 200
        assert all(s["id"] != sid for s in r2.json())

    def test_exclusao_nao_apaga_lancamentos_do_centro_de_custo(self, client):
        c, engine = client
        sid = _criar_safra(engine)
        with Session(engine) as s:
            s.add(ContaGerencial(
                numero_lancamento="LC-2026-00099", parcela_num=1, parcela_total=1,
                valor_total=500, descricao="Adubo", centro_custo="Agricultura",
            ))
            s.commit()

        r = c.post("/exclusoes/confirmar", json={"tipo": "safra", "id": str(sid)})
        assert r.status_code == 200

        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-2026-00099")).first()
            assert conta is not None

    def test_safra_de_outra_fazenda_da_404_no_impacto_e_nao_aparece_na_busca(self, client_fazenda):
        c, engine = client_fazenda
        sid_outra = _criar_safra(engine, fazenda_id=2, nome="Safra da fazenda 2")

        r = c.post("/exclusoes/impacto", json={"tipo": "safra", "id": str(sid_outra)})
        assert r.status_code == 404

        r2 = c.get("/exclusoes/buscar", params={"tipo": "safra", "termo": "fazenda 2"})
        assert r2.status_code == 200
        assert all(item["id"] != str(sid_outra) for item in r2.json())

        with Session(engine) as s:
            assert s.get(Safra, sid_outra) is not None
