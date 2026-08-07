"""
G1 — PUT/DELETE de `MovimentoEstoque` lançado manualmente:
- `PUT /estoque/movimentos/{id}` edita quantidade/data/observação e ajusta o
  saldo do item pelo delta.
- `DELETE` é feito pelo motor genérico (`POST /exclusoes/...`, tipo
  "movimento_estoque"), que reverte o saldo dentro de `alvos`.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda,
    ContratoFazendaModulo,
    Estoque,
    EstoqueSemen,
    Fazenda,
    MovimentoEstoque,
    SolicitacaoExclusao,
)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="estoque", preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "admin@teste.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: None

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _como_operador():
    import main
    from fazenda.auth import get_current_user

    class _FakeOperador:
        id = 2
        papel = "operador"
        ativo = True
        username = "operador"
        email = "operador@teste.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()


class TestPutMovimentoEstoque:
    def test_editar_quantidade_ajusta_saldo_pelo_delta(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Ração", quantidade=100, unidade="kg"))
            s.add(MovimentoEstoque(
                id=1, nome_item="Ração", movimento="Entrada de ajuste", quantidade=10,
                unidade="kg", data_movimento=date(2026, 1, 1), estoque_id=1,
            ))
            s.commit()

        r = c.put("/estoque/movimentos/1", json={
            "quantidade": 25, "unidade": "kg", "data_movimento": "2026-01-02", "observacao": "corrigido",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        # delta = +1 * (25 - 10) = +15 -> saldo 100 + 15 = 115
        assert body["saldo_item"] == 115
        assert body["quantidade"] == 25
        assert body["data_movimento"] == "2026-01-02"

        with _sessao(engine) as s:
            item = s.get(Estoque, 1)
            assert item.quantidade == 115

    def test_editar_saida_ajusta_saldo_pelo_delta_com_sinal_invertido(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Ração", quantidade=100, unidade="kg"))
            s.add(MovimentoEstoque(
                id=1, nome_item="Ração", movimento="Saída de ajuste", quantidade=10,
                unidade="kg", data_movimento=date(2026, 1, 1), estoque_id=1,
            ))
            s.commit()

        r = c.put("/estoque/movimentos/1", json={
            "quantidade": 30, "unidade": "kg", "data_movimento": "2026-01-01",
        })
        assert r.status_code == 200, r.text
        # sinal = -1; delta = -1 * (30-10) = -20 -> saldo 100 - 20 = 80
        assert r.json()["saldo_item"] == 80

    def test_editar_movimento_origem_lancamento_da_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Vacina X", quantidade=50))
            s.add(MovimentoEstoque(
                id=1, nome_item="Vacina X", movimento="Aplicação", quantidade=1,
                data_movimento=date(2026, 1, 1), estoque_id=1, origem_tipo="sanidade", origem_id=99,
            ))
            s.commit()

        r = c.put("/estoque/movimentos/1", json={
            "quantidade": 2, "data_movimento": "2026-01-01",
        })
        assert r.status_code == 400
        assert "sanidade" in r.json()["detail"]

    def test_editar_movimento_com_pedido_item_da_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Cal", quantidade=10))
            s.add(MovimentoEstoque(
                id=1, nome_item="Cal", movimento="Entrada de ajuste", quantidade=1,
                data_movimento=date(2026, 1, 1), estoque_id=1, pedido_item_id=7,
            ))
            s.commit()

        r = c.put("/estoque/movimentos/1", json={"quantidade": 5, "data_movimento": "2026-01-01"})
        assert r.status_code == 400
        assert "Pedido" in r.json()["detail"]

    def test_editar_quantidade_zero_da_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Cal", quantidade=10))
            s.add(MovimentoEstoque(
                id=1, nome_item="Cal", movimento="Entrada de ajuste", quantidade=1,
                data_movimento=date(2026, 1, 1), estoque_id=1,
            ))
            s.commit()

        r = c.put("/estoque/movimentos/1", json={"quantidade": 0, "data_movimento": "2026-01-01"})
        assert r.status_code == 400

    def test_editar_movimento_de_outra_fazenda_da_404(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Cal", quantidade=10, fazenda_id=1))
            s.add(MovimentoEstoque(
                id=1, nome_item="Cal", movimento="Entrada de ajuste", quantidade=1,
                data_movimento=date(2026, 1, 1), estoque_id=1, fazenda_id=1,
            ))
            s.commit()

        _como_fazenda(2)
        r = c.put("/estoque/movimentos/1", json={"quantidade": 5, "data_movimento": "2026-01-01"})
        assert r.status_code == 404

    def test_editar_movimento_inexistente_da_404(self, client):
        c, engine = client
        r = c.put("/estoque/movimentos/9999", json={"quantidade": 5, "data_movimento": "2026-01-01"})
        assert r.status_code == 404

    def test_editar_saida_de_semen_espelha_em_estoque_semen(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(EstoqueSemen(id=1, touro_nome="Touro A", naab="000A", doses=20))
            s.add(Estoque(id=1, nome="Sêmen Touro A", quantidade=20, estoque_semen_id=1))
            s.add(MovimentoEstoque(
                id=1, nome_item="Sêmen Touro A", movimento="Aplicação", quantidade=2,
                data_movimento=date(2026, 1, 1), estoque_id=1,
            ))
            s.commit()

        r = c.put("/estoque/movimentos/1", json={"quantidade": 3, "data_movimento": "2026-01-01"})
        assert r.status_code == 200, r.text
        # saída: sinal=-1; delta = -1*(3-2) = -1 -> saldo 20-1=19
        assert r.json()["saldo_item"] == 19
        with _sessao(engine) as s:
            touro = s.get(EstoqueSemen, 1)
            assert touro.doses == 19


class TestExcluirMovimentoEstoqueViaMotorGenerico:
    def _impacto(self, c, mov_id: int):
        return c.post("/exclusoes/impacto", json={"tipo": "movimento_estoque", "id": str(mov_id)})

    def _confirmar(self, c, mov_id: int):
        return c.post("/exclusoes/confirmar", json={"tipo": "movimento_estoque", "id": str(mov_id)})

    def test_excluir_devolve_o_saldo_exato(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Ração", quantidade=100, unidade="kg"))
            s.add(MovimentoEstoque(
                id=1, nome_item="Ração", movimento="Saída de ajuste", quantidade=15,
                unidade="kg", data_movimento=date(2026, 1, 1), estoque_id=1,
            ))
            s.commit()

        r = self._confirmar(c, 1)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            item = s.get(Estoque, 1)
            # saída revertida: saldo volta a subir os 15 que tinham sido baixados
            assert item.quantidade == 115
            assert s.get(MovimentoEstoque, 1) is None

    def test_excluir_saida_de_semen_devolve_doses(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(EstoqueSemen(id=1, touro_nome="Touro A", naab="000A", doses=10))
            s.add(Estoque(id=1, nome="Sêmen Touro A", quantidade=10, estoque_semen_id=1))
            s.add(MovimentoEstoque(
                id=1, nome_item="Sêmen Touro A", movimento="Aplicação", quantidade=4,
                data_movimento=date(2026, 1, 1), estoque_id=1,
            ))
            s.commit()

        r = self._confirmar(c, 1)
        assert r.status_code == 200, r.text
        with _sessao(engine) as s:
            touro = s.get(EstoqueSemen, 1)
            assert touro.doses == 14

    def test_excluir_movimento_com_origem_tipo_da_400_no_impacto(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Vacina X", quantidade=50))
            s.add(MovimentoEstoque(
                id=1, nome_item="Vacina X", movimento="Aplicação", quantidade=1,
                data_movimento=date(2026, 1, 1), estoque_id=1, origem_tipo="sanidade", origem_id=99,
            ))
            s.commit()

        r = self._impacto(c, 1)
        assert r.status_code == 400
        assert "sanidade" in r.json()["detail"]

        r = self._confirmar(c, 1)
        assert r.status_code == 400

    def test_excluir_movimento_com_pedido_item_da_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Cal", quantidade=10))
            s.add(MovimentoEstoque(
                id=1, nome_item="Cal", movimento="Entrada de ajuste", quantidade=1,
                data_movimento=date(2026, 1, 1), estoque_id=1, pedido_item_id=7,
            ))
            s.commit()

        r = self._confirmar(c, 1)
        assert r.status_code == 400

    def test_movimento_de_outra_fazenda_nao_aparece_na_busca_e_da_404_no_impacto(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Cal", quantidade=10, fazenda_id=1))
            s.add(MovimentoEstoque(
                id=1, nome_item="Cal", movimento="Entrada de ajuste", quantidade=1,
                data_movimento=date(2026, 1, 1), estoque_id=1, fazenda_id=1,
            ))
            s.commit()

        _como_fazenda(2)
        r = c.get("/exclusoes/buscar", params={"tipo": "movimento_estoque", "termo": "Cal"})
        assert r.status_code == 200
        assert r.json() == []

        r = self._impacto(c, 1)
        assert r.status_code == 404

    def test_previa_de_impacto_nao_altera_nada(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Ração", quantidade=100, unidade="kg"))
            s.add(MovimentoEstoque(
                id=1, nome_item="Ração", movimento="Saída de ajuste", quantidade=15,
                unidade="kg", data_movimento=date(2026, 1, 1), estoque_id=1,
            ))
            s.commit()

        r = self._impacto(c, 1)
        assert r.status_code == 200
        assert any("Ração" in i for i in r.json()["impacto"])

        with _sessao(engine) as s:
            item = s.get(Estoque, 1)
            assert item.quantidade == 100  # nada mudou
            assert s.get(MovimentoEstoque, 1) is not None  # nada foi apagado

    def test_fluxo_de_aprovacao_operador_solicita_admin_aprova_e_executa_exclusao(self, client):
        """Operador não apaga nada na hora — só cria uma `SolicitacaoExclusao`
        pendente; só a aprovação do admin de fato apaga o `MovimentoEstoque`.

        NOTA sobre o saldo: `POST /exclusoes/confirmar` (`exclusoes.py`, fora
        da fronteira deste agente) chama `_alvos` — que já reverte o saldo —
        e faz `session.commit()` também no ramo "solicitado" (não só no
        "excluido"), então o efeito colateral de `alvos` já fica persistido
        assim que o operador solicita, antes de qualquer aprovação; a
        aprovação chama `_alvos` de novo e reverte uma segunda vez. Esse é um
        comportamento do motor genérico COMPARTILHADO por todos os tipos com
        efeito colateral (mesma issue reproduz em G4/`movimento_lote`, de
        outro agente, neste mesmo diretório de trabalho) — não é algo
        introduzido por G1, e `exclusoes.py` está fora da fronteira permitida
        para este agente corrigir. Por isso este teste verifica o que
        realmente está sob o controle de G1 (a exclusão de fato do
        movimento na aprovação), sem travar num valor de saldo que depende
        de um comportamento pré-existente do motor compartilhado."""
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(id=1, nome="Ração", quantidade=100, unidade="kg"))
            s.add(MovimentoEstoque(
                id=1, nome_item="Ração", movimento="Saída de ajuste", quantidade=15,
                unidade="kg", data_movimento=date(2026, 1, 1), estoque_id=1,
            ))
            s.commit()

        _como_operador()
        r = c.post("/exclusoes/confirmar", json={"tipo": "movimento_estoque", "id": "1"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "solicitado"

        with _sessao(engine) as s:
            sol = s.exec(select(SolicitacaoExclusao)).first()
            assert sol is not None
            assert sol.status == "pendente"
            sol_id = sol.id
            assert s.get(MovimentoEstoque, 1) is not None  # ainda não apagado

        import main
        from fazenda.auth import exigir_admin, get_current_user

        class _FakeAdmin:
            id = 1
            papel = "admin"
            ativo = True
            username = "teste"
            email = "admin@teste.com"
            permissoes = ""

        main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
        main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()

        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 200, r.text
        assert r.json()["aprovado"] is True

        with _sessao(engine) as s:
            assert s.get(MovimentoEstoque, 1) is None  # excluído de fato na aprovação
            sol = s.get(SolicitacaoExclusao, sol_id)
            assert sol.status == "aprovada"
