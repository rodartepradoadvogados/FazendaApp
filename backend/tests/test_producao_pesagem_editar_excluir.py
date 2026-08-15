"""
Testes de G7 — GET /producao/pesagens (listagem individual, nova), PUT
/producao/pesagens/{id} (editar) e DELETE via motor genérico de exclusões
(tipo "pesagem_corporal").

Fixture própria (mesmo padrão de `test_exclusoes.py`, linhas 40-68) — arquivo
self-contained, não compartilha nada com os demais arquivos de teste.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, PesagemCorporal


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
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: None

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


def _seed_fazenda_produtivo(engine, fid: int) -> None:
    with _sessao(engine) as s:
        s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
        s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="produtivo", preco=0.0, ativo=True))
        s.commit()


def _como_fazenda(fid: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fid


class TestListarPesagens:
    def test_get_devolve_id(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(PesagemCorporal(numero_matriz="100", data_pesagem=date(2026, 1, 10), peso_kg=350.0))
            s.commit()

        r = c.get("/producao/pesagens")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["pesagens"][0]["id"] is not None
        assert body["pesagens"][0]["numero_matriz"] == "100"

    def test_ordenado_por_data_desc_id_desc(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(PesagemCorporal(numero_matriz="1", data_pesagem=date(2026, 1, 1), peso_kg=100.0))
            s.add(PesagemCorporal(numero_matriz="2", data_pesagem=date(2026, 3, 1), peso_kg=200.0))
            s.add(PesagemCorporal(numero_matriz="3", data_pesagem=date(2026, 2, 1), peso_kg=150.0))
            s.commit()

        r = c.get("/producao/pesagens")
        datas = [p["data_pesagem"] for p in r.json()["pesagens"]]
        assert datas == sorted(datas, reverse=True)

    def test_limite_corta_a_lista_mas_nao_o_total(self, client):
        c, engine = client
        with _sessao(engine) as s:
            for i in range(5):
                s.add(PesagemCorporal(numero_matriz=str(i), data_pesagem=date(2026, 1, 1 + i), peso_kg=100.0 + i))
            s.commit()

        r = c.get("/producao/pesagens", params={"limite": 2})
        body = r.json()
        assert len(body["pesagens"]) == 2
        assert body["total"] == 5


class TestPutPesagem:
    def test_put_altera_peso(self, client):
        c, engine = client
        with _sessao(engine) as s:
            p = PesagemCorporal(numero_matriz="200", data_pesagem=date(2026, 1, 1), peso_kg=300.0)
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

        r = c.put(f"/producao/pesagens/{pid}", json={"peso_kg": 320.0})
        assert r.status_code == 200
        assert r.json()["peso_kg"] == 320.0

        with _sessao(engine) as s:
            atualizado = s.get(PesagemCorporal, pid)
            assert atualizado.peso_kg == 320.0

    def test_gmd_do_relatorio_muda_apos_editar_peso(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(PesagemCorporal(numero_matriz="201", data_pesagem=date(2026, 1, 1), peso_kg=300.0))
            p2 = PesagemCorporal(numero_matriz="201", data_pesagem=date(2026, 1, 11), peso_kg=310.0)
            s.add(p2)
            s.commit()
            s.refresh(p2)
            pid = p2.id

        antes = c.get("/producao/pesagens/relatorio").json()["linhas"][0]
        assert antes["gmd_kg_dia"] == 1.0

        c.put(f"/producao/pesagens/{pid}", json={"peso_kg": 330.0})

        depois = c.get("/producao/pesagens/relatorio").json()["linhas"][0]
        assert depois["gmd_kg_dia"] == 3.0

    def test_put_que_muda_data_recalcula_fase(self, client):
        c, engine = client
        with _sessao(engine) as s:
            # Recém-parida na data original (del_dias baixo) -> fase pos_parto
            # gravada no lançamento original (foto do momento).
            p = PesagemCorporal(
                numero_matriz="202", data_pesagem=date(2026, 1, 1), peso_kg=500.0,
                del_dias=10, fase="pos_parto",
            )
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

        # Sem cadastro do animal (Animal não existe) -> _fase_transicao devolve
        # None: mudar a data recalcula e a fase antiga (pos_parto) é substituída.
        r = c.put(f"/producao/pesagens/{pid}", json={"data_pesagem": "2026-05-01"})
        assert r.status_code == 200
        assert r.json()["fase"] is None
        assert r.json()["data_pesagem"] == "2026-05-01"

    def test_put_preserva_del_dias_idade_grupo_foto_do_momento(self, client):
        c, engine = client
        with _sessao(engine) as s:
            p = PesagemCorporal(
                numero_matriz="203", data_pesagem=date(2026, 1, 1), peso_kg=200.0,
                del_dias=5, idade_meses=24.0, grupo_primario="01 - Lactação",
            )
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

        r = c.put(f"/producao/pesagens/{pid}", json={"peso_kg": 210.0})
        assert r.status_code == 200
        body = r.json()
        assert body["del_dias"] == 5
        assert body["idade_meses"] == 24.0
        assert body["grupo_primario"] == "01 - Lactação"

    def test_put_peso_invalido_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            p = PesagemCorporal(numero_matriz="204", data_pesagem=date(2026, 1, 1), peso_kg=100.0)
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

        r = c.put(f"/producao/pesagens/{pid}", json={"peso_kg": 0})
        assert r.status_code == 400

    def test_put_inexistente_404(self, client):
        c, engine = client
        r = c.put("/producao/pesagens/9999", json={"peso_kg": 100.0})
        assert r.status_code == 404


class TestExcluirPesagem:
    def test_excluir_remove_linha_e_relatorio_reflete(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(PesagemCorporal(numero_matriz="300", data_pesagem=date(2026, 1, 1), peso_kg=100.0))
            p2 = PesagemCorporal(numero_matriz="300", data_pesagem=date(2026, 1, 15), peso_kg=110.0)
            s.add(p2)
            s.commit()
            s.refresh(p2)
            pid = p2.id

        antes = c.get("/producao/pesagens/relatorio").json()["linhas"][0]
        assert antes["num_pesagens"] == 2

        r = c.post("/exclusoes/confirmar", json={"tipo": "pesagem_corporal", "id": str(pid)})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            assert s.get(PesagemCorporal, pid) is None

        depois = c.get("/producao/pesagens/relatorio").json()["linhas"][0]
        assert depois["num_pesagens"] == 1

    def test_previa_de_impacto_nao_altera_nada(self, client):
        c, engine = client
        with _sessao(engine) as s:
            p = PesagemCorporal(numero_matriz="301", data_pesagem=date(2026, 1, 1), peso_kg=100.0)
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

        r = c.post("/exclusoes/impacto", json={"tipo": "pesagem_corporal", "id": str(pid)})
        assert r.status_code == 200
        assert any("301" in i for i in r.json()["impacto"])

        with _sessao(engine) as s:
            assert s.get(PesagemCorporal, pid) is not None

    def test_operador_solicita_admin_aprova(self, client):
        c, engine = client
        with _sessao(engine) as s:
            p = PesagemCorporal(numero_matriz="302", data_pesagem=date(2026, 1, 1), peso_kg=100.0)
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

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
            r = c.post("/exclusoes/confirmar", json={"tipo": "pesagem_corporal", "id": str(pid)})
        finally:
            main.app.dependency_overrides[get_current_user] = anterior
        assert r.status_code == 200
        assert r.json()["status"] == "solicitado"

        with _sessao(engine) as s:
            assert s.get(PesagemCorporal, pid) is not None

        pendentes = c.get("/exclusoes/pendentes").json()
        sol_id = next(p["id"] for p in pendentes if p["tipo"] == "pesagem_corporal" and p["id_alvo"] == str(pid))
        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 200

        with _sessao(engine) as s:
            assert s.get(PesagemCorporal, pid) is None


class TestIsolamentoPesagem:
    def test_get_nao_devolve_pesagem_de_outra_fazenda(self, client):
        c, engine = client
        _seed_fazenda_produtivo(engine, 1)
        _seed_fazenda_produtivo(engine, 2)
        with _sessao(engine) as s:
            s.add(PesagemCorporal(numero_matriz="400", data_pesagem=date(2026, 1, 1), peso_kg=100.0, fazenda_id=1))
            s.commit()

        _como_fazenda(2)
        r = c.get("/producao/pesagens")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_put_de_outra_fazenda_404(self, client):
        c, engine = client
        _seed_fazenda_produtivo(engine, 1)
        _seed_fazenda_produtivo(engine, 2)
        with _sessao(engine) as s:
            p = PesagemCorporal(numero_matriz="401", data_pesagem=date(2026, 1, 1), peso_kg=100.0, fazenda_id=1)
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

        _como_fazenda(2)
        r = c.put(f"/producao/pesagens/{pid}", json={"peso_kg": 200.0})
        assert r.status_code == 404

    def test_buscar_e_impacto_nao_vazam_entre_fazendas(self, client):
        c, engine = client
        _seed_fazenda_produtivo(engine, 1)
        _seed_fazenda_produtivo(engine, 2)
        with _sessao(engine) as s:
            p = PesagemCorporal(numero_matriz="402", data_pesagem=date(2026, 1, 1), peso_kg=100.0, fazenda_id=1)
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

        _como_fazenda(2)
        busca = c.get("/exclusoes/buscar", params={"tipo": "pesagem_corporal", "termo": ""}).json()
        assert all(item["id"] != pid for item in busca)

        r = c.post("/exclusoes/impacto", json={"tipo": "pesagem_corporal", "id": str(pid)})
        assert r.status_code == 404
