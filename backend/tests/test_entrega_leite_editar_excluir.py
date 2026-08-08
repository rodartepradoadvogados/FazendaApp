"""
Testes de G6 — PUT /producao/entrega-leite/{id} (editar competência/valor) e
DELETE via motor genérico de exclusões (tipo "entrega_leite").

Fixture própria (mesmo padrão de `test_exclusoes.py`, linhas 40-68) — arquivo
self-contained, não compartilha nada com os demais arquivos de teste.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, ContratoFazenda, ContratoFazendaModulo, EntregaLeiteMensal, Fazenda


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

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

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()
    # Sem fazenda selecionada por padrão — mesmo comportamento "sem
    # retroatividade" de token legado (fazenda_id=None não filtra nada e não
    # passa por exigir_modulo_contratado, ver fazenda/auth.py).
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: None

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


def _seed_fazenda_produtivo(engine, fid: int) -> None:
    """producao.router exige exigir_modulo_contratado('produtivo') quando
    fazenda_id não é None — sem isso o PUT/GET devolveria 403 nos testes de
    isolamento (que forçam get_fazenda_atual_id a devolver um id real)."""
    with _sessao(engine) as s:
        s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
        s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="produtivo", preco=0.0, ativo=True))
        s.commit()


def _como_fazenda(fid: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fid


class TestPutEntregaLeite:
    def test_put_altera_competencia_e_valor(self, client):
        c, engine = client
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-01", quantidade_litros=1000.0)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        r = c.put(f"/producao/entrega-leite/{rid}", json={"competencia": "2026-02", "quantidade_litros": 1234.5, "observacao": "corrigido"})
        assert r.status_code == 200
        body = r.json()
        assert body["competencia"] == "2026-02"
        assert body["quantidade_litros"] == 1234.5
        assert body["observacao"] == "corrigido"

        with _sessao(engine) as s:
            atualizado = s.get(EntregaLeiteMensal, rid)
            assert atualizado.competencia == "2026-02"
            assert atualizado.quantidade_litros == 1234.5

    def test_put_competencia_ocupada_retorna_409(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(EntregaLeiteMensal(competencia="2026-01", quantidade_litros=1000.0))
            alvo = EntregaLeiteMensal(competencia="2026-02", quantidade_litros=500.0)
            s.add(alvo)
            s.commit()
            s.refresh(alvo)
            rid = alvo.id

        r = c.put(f"/producao/entrega-leite/{rid}", json={"competencia": "2026-01", "quantidade_litros": 600.0})
        assert r.status_code == 409

        with _sessao(engine) as s:
            intacto = s.get(EntregaLeiteMensal, rid)
            assert intacto.competencia == "2026-02"
            assert intacto.quantidade_litros == 500.0

    def test_put_mesma_competencia_nao_conflita_consigo_mesmo(self, client):
        c, engine = client
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-03", quantidade_litros=800.0)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        r = c.put(f"/producao/entrega-leite/{rid}", json={"competencia": "2026-03", "quantidade_litros": 900.0})
        assert r.status_code == 200
        assert r.json()["quantidade_litros"] == 900.0

    def test_put_quantidade_invalida_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-04", quantidade_litros=100.0)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        r = c.put(f"/producao/entrega-leite/{rid}", json={"competencia": "2026-04", "quantidade_litros": 0})
        assert r.status_code == 400

    def test_put_competencia_formato_invalido_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-05", quantidade_litros=100.0)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        r = c.put(f"/producao/entrega-leite/{rid}", json={"competencia": "05/2026", "quantidade_litros": 100.0})
        assert r.status_code == 400

    def test_put_inexistente_404(self, client):
        c, engine = client
        r = c.put("/producao/entrega-leite/9999", json={"competencia": "2026-01", "quantidade_litros": 10.0})
        assert r.status_code == 404


class TestExcluirEntregaLeite:
    def test_excluir_remove_e_relatorio_deixa_de_contar_o_mes(self, client):
        c, engine = client
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-06", quantidade_litros=2000.0)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        antes = c.get("/producao/relatorio-controle-entrega", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"}).json()
        assert antes["entrega_projetada_kg"] is not None

        r = c.post("/exclusoes/confirmar", json={"tipo": "entrega_leite", "id": str(rid)})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            assert s.get(EntregaLeiteMensal, rid) is None

        depois = c.get("/producao/relatorio-controle-entrega", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"}).json()
        assert depois["entrega_projetada_kg"] is None

    def test_previa_de_impacto_nao_altera_nada(self, client):
        c, engine = client
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-07", quantidade_litros=333.0)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        r = c.post("/exclusoes/impacto", json={"tipo": "entrega_leite", "id": str(rid)})
        assert r.status_code == 200
        assert any("333" in i for i in r.json()["impacto"])

        with _sessao(engine) as s:
            assert s.get(EntregaLeiteMensal, rid) is not None

    def test_operador_solicita_admin_aprova(self, client):
        c, engine = client
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-08", quantidade_litros=444.0)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        import main
        from fazenda.auth import get_current_user

        class _FakeOperador:
            id = 2
            papel = "operador"
            ativo = True
            username = "operador1"

        anterior = main.app.dependency_overrides[get_current_user]
        main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()
        try:
            r = c.post("/exclusoes/confirmar", json={"tipo": "entrega_leite", "id": str(rid)})
        finally:
            main.app.dependency_overrides[get_current_user] = anterior
        assert r.status_code == 200
        assert r.json()["status"] == "solicitado"

        with _sessao(engine) as s:
            assert s.get(EntregaLeiteMensal, rid) is not None

        pendentes = c.get("/exclusoes/pendentes").json()
        sol_id = next(p["id"] for p in pendentes if p["tipo"] == "entrega_leite" and p["id_alvo"] == str(rid))
        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 200

        with _sessao(engine) as s:
            assert s.get(EntregaLeiteMensal, rid) is None


class TestIsolamentoEntregaLeite:
    def test_put_de_outra_fazenda_404(self, client):
        c, engine = client
        _seed_fazenda_produtivo(engine, 1)
        _seed_fazenda_produtivo(engine, 2)
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-09", quantidade_litros=50.0, fazenda_id=1)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        _como_fazenda(2)
        r = c.put(f"/producao/entrega-leite/{rid}", json={"competencia": "2026-10", "quantidade_litros": 60.0})
        assert r.status_code == 404

    def test_buscar_e_impacto_nao_vazam_entre_fazendas(self, client):
        c, engine = client
        _seed_fazenda_produtivo(engine, 1)
        _seed_fazenda_produtivo(engine, 2)
        with _sessao(engine) as s:
            reg = EntregaLeiteMensal(competencia="2026-11", quantidade_litros=77.0, fazenda_id=1)
            s.add(reg)
            s.commit()
            s.refresh(reg)
            rid = reg.id

        _como_fazenda(2)
        busca = c.get("/exclusoes/buscar", params={"tipo": "entrega_leite", "termo": ""}).json()
        assert all(item["id"] != rid for item in busca)

        r = c.post("/exclusoes/impacto", json={"tipo": "entrega_leite", "id": str(rid)})
        assert r.status_code == 404
