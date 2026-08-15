"""
Visibilidade do CATÁLOGO da farmácia num banco multi-fazenda.

O catálogo (princípio ativo, doença, marca comercial, indicação terapêutica)
nasce GLOBAL — `fazenda_id` nulo, semeado igual para todo produtor. Todo o
código filtrava com `fazenda_id == fazenda_id`, e em SQL isso EXCLUI
`fazenda_id IS NULL`: a fazenda com `fid` no token via a Farmácia inteira
vazia, sem nenhum erro no log. Estes testes travam o comportamento correto —
global + da fazenda atual, nunca o de outra fazenda.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Doenca, Estoque, Fazenda, IndicacaoTerapeutica, PrincipioAtivo,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()
        # Catálogo global (como o seed cria: sem fazenda_id).
        pa_global = PrincipioAtivo(nome="Ceftiofur", unidade_base="ml")
        doenca_global = Doenca(nome="Metrite")
        s.add(pa_global)
        s.add(doenca_global)
        # Catálogo de OUTRA fazenda — nunca pode aparecer para a fazenda 1.
        s.add(PrincipioAtivo(nome="Princípio da fazenda 2", fazenda_id=2))
        s.add(Doenca(nome="Doença da fazenda 2", fazenda_id=2))
        s.commit()
        s.refresh(pa_global)
        s.refresh(doenca_global)
        s.add(IndicacaoTerapeutica(principio_ativo_id=pa_global.id, doenca_id=doenca_global.id, prioridade=1))
        s.add(Estoque(nome="Excenel", quantidade=10, unidade="ml",
                      principio_ativo_id=pa_global.id, fazenda_id=1))
        s.commit()

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
        permissoes = "sanidade,estoque"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestCatalogoGlobalVisivelParaFazenda:
    def test_principio_global_aparece_para_fazenda_com_fid(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.get("/farmacia/principios")
        assert r.status_code == 200, r.text
        nomes = {p["nome"] for p in r.json()}
        assert "Ceftiofur" in nomes, "catálogo global sumiu para a fazenda com fid no token"

    def test_principio_de_outra_fazenda_nunca_aparece(self, client):
        c, _ = client
        _como_fazenda(1)
        nomes = {p["nome"] for p in c.get("/farmacia/principios").json()}
        assert "Princípio da fazenda 2" not in nomes

    def test_medicamentos_por_principio_global_encontra_o_item(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.get("/estoque/medicamentos", params={"principio_ativo": "Ceftiofur"})
        assert r.status_code == 200
        assert [m["nome"] for m in r.json()] == ["Excenel"]

    def test_medicamentos_por_doenca_global_encontra_via_indicacao(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.get("/estoque/medicamentos", params={"doenca": "Metrite"})
        assert r.status_code == 200
        assert [m["nome"] for m in r.json()] == ["Excenel"]

    def test_indicacoes_por_doenca_global_nao_da_404(self, client):
        c, engine = client
        with Session(engine) as s:
            from sqlmodel import select
            doenca_id = s.exec(select(Doenca).where(Doenca.nome == "Metrite")).first().id
        _como_fazenda(1)
        r = c.get(f"/sanidade/indicacoes-doenca/{doenca_id}")
        assert r.status_code == 200, "doença do catálogo global dava 404 com fid no token"

    def test_token_legado_sem_fazenda_continua_vendo_tudo(self, client):
        c, _ = client
        _como_fazenda(None)
        nomes = {p["nome"] for p in c.get("/farmacia/principios").json()}
        assert "Ceftiofur" in nomes
        assert "Princípio da fazenda 2" in nomes
