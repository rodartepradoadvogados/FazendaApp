"""
Gauntlet A-13: editar/excluir uma aplicação de Sanidade estornava e
rebaixava o estoque resolvendo o item SÓ pelo nome do produto
(`_ajustar_estoque_por_aplicacao`, sanidade.py) — quando há mais de um frasco
cadastrado com o mesmo nome (lotes/validades diferentes, comum na Farmácia),
o estorno podia cair num frasco diferente do que a baixa original de fato
usou. A correção lê o `estoque_id` gravado no próprio MovimentoEstoque da
baixa original e força o mesmo frasco no estorno/rebaixa.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, MovimentoEstoque


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

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

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _saldo(engine, estoque_id: int) -> float:
    with Session(engine) as s:
        return s.get(Estoque, estoque_id).quantidade


class TestEditarAplicacaoRespeitaFrascoOriginal:
    def test_editar_dose_estorna_e_rebaixa_no_mesmo_frasco(self, client):
        c, engine = client
        with Session(engine) as s:
            frasco_a = Estoque(nome="Sincrocp", quantidade=50, unidade="ml")
            frasco_b = Estoque(nome="Sincrocp", quantidade=50, unidade="ml")
            s.add(frasco_a); s.add(frasco_b); s.commit()
            s.refresh(frasco_a); s.refresh(frasco_b)
            frasco_a_id, frasco_b_id = frasco_a.id, frasco_b.id

        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["700"],
            "itens": [{"produto": "Sincrocp", "quantidade": 5, "unidade": "ml", "estoque_id": frasco_b_id}],
        })
        assert r.status_code == 200, r.text
        assert _saldo(engine, frasco_a_id) == 50
        assert _saldo(engine, frasco_b_id) == 45

        aplicacao_id = c.get("/sanidade/aplicacoes").json()["aplicacoes"][0]["id"]
        r = c.put(f"/sanidade/aplicacoes/{aplicacao_id}", json={"dose": 8})
        assert r.status_code == 200, r.text

        # A correção tem que continuar SÓ no frasco B (o escolhido originalmente).
        assert _saldo(engine, frasco_a_id) == 50, "frasco não usado na baixa original não pode ser tocado"
        assert _saldo(engine, frasco_b_id) == 42, "frasco B: 50 - 8 (estorna os 5 antigos, rebaixa os 8 novos)"

    def test_excluir_aplicacao_devolve_no_mesmo_frasco(self, client):
        c, engine = client
        with Session(engine) as s:
            frasco_a = Estoque(nome="Sincrocp", quantidade=50, unidade="ml")
            frasco_b = Estoque(nome="Sincrocp", quantidade=50, unidade="ml")
            s.add(frasco_a); s.add(frasco_b); s.commit()
            s.refresh(frasco_a); s.refresh(frasco_b)
            frasco_a_id, frasco_b_id = frasco_a.id, frasco_b.id

        c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["701"],
            "itens": [{"produto": "Sincrocp", "quantidade": 5, "unidade": "ml", "estoque_id": frasco_b_id}],
        })
        aplicacao_id = c.get("/sanidade/aplicacoes").json()["aplicacoes"][0]["id"]

        r = c.delete(f"/sanidade/aplicacoes/{aplicacao_id}")
        assert r.status_code == 200, r.text

        assert _saldo(engine, frasco_a_id) == 50, "frasco não usado na baixa original não pode ser tocado"
        assert _saldo(engine, frasco_b_id) == 50, "devolve exatamente no frasco de onde saiu"

    def test_editar_produto_para_outro_nome_nao_usa_frasco_antigo(self, client):
        """Quando o PRODUTO muda de fato, não há frasco antigo válido pro
        produto novo — tem que resolver por nome mesmo (comportamento normal)."""
        c, engine = client
        with Session(engine) as s:
            frasco_x = Estoque(nome="Sincrocp", quantidade=50, unidade="ml")
            frasco_y = Estoque(nome="Croniben", quantidade=30, unidade="ml")
            s.add(frasco_x); s.add(frasco_y); s.commit()
            s.refresh(frasco_x); s.refresh(frasco_y)
            frasco_x_id, frasco_y_id = frasco_x.id, frasco_y.id

        c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["702"],
            "itens": [{"produto": "Sincrocp", "quantidade": 5, "unidade": "ml", "estoque_id": frasco_x_id}],
        })
        assert _saldo(engine, frasco_x_id) == 45
        aplicacao_id = c.get("/sanidade/aplicacoes").json()["aplicacoes"][0]["id"]

        r = c.put(f"/sanidade/aplicacoes/{aplicacao_id}", json={"produto": "Croniben", "dose": 3})
        assert r.status_code == 200, r.text

        assert _saldo(engine, frasco_x_id) == 50, "estorno vai pro frasco original (Sincrocp)"
        assert _saldo(engine, frasco_y_id) == 27, "rebaixa no produto novo (Croniben), resolvido por nome"

    def test_estoque_id_gravado_no_movimento_e_o_frasco_realmente_usado(self, client):
        c, engine = client
        with Session(engine) as s:
            frasco_a = Estoque(nome="Sincrocp", quantidade=50, unidade="ml")
            frasco_b = Estoque(nome="Sincrocp", quantidade=50, unidade="ml")
            s.add(frasco_a); s.add(frasco_b); s.commit()
            s.refresh(frasco_a); s.refresh(frasco_b)
            frasco_b_id = frasco_b.id

        c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["703"],
            "itens": [{"produto": "Sincrocp", "quantidade": 5, "unidade": "ml", "estoque_id": frasco_b_id}],
        })
        aplicacao_id = c.get("/sanidade/aplicacoes").json()["aplicacoes"][0]["id"]
        c.put(f"/sanidade/aplicacoes/{aplicacao_id}", json={"dose": 6})

        with Session(engine) as s:
            movimentos = s.exec(
                select(MovimentoEstoque).where(
                    MovimentoEstoque.origem_tipo == "sanidade", MovimentoEstoque.origem_id == aplicacao_id,
                )
            ).all()
        assert all(m.estoque_id == frasco_b_id for m in movimentos), \
            "todo movimento (baixa original, estorno, rebaixa) tem que apontar pro mesmo frasco"
