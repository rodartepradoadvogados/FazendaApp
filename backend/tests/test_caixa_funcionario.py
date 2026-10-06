"""Caixa dos funcionários — Fase 1 (caixa individual): entrada, saldo, retirada,
estorno, exclusão e isolamento entre fazendas."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import CaixaMovimento, ContaGerencial, ContratoFazenda, ContratoFazendaModulo


class _FakeUser:
    id = 1
    papel = "admin"
    ativo = True
    username = "teste"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


@pytest.fixture
def client_multi():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="financeiro", ativo=True))
        s.commit()
    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    def _make(fid: int) -> TestClient:
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fid
        return TestClient(main.app)

    yield engine, _make
    main.app.dependency_overrides.clear()


def _pessoa(c, nome="Ana Souza", tipo="Funcionário") -> int:
    r = c.post("/cadastro/pessoas", json={"nome": nome, "tipos": [tipo]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _entrada(c, pessoa_ids, valor=500.0, tipo="deposito", motivo="Reconhecimento da safra", **extra):
    return c.post("/cadastro/caixa-funcionarios/entradas", json={
        "pessoa_ids": pessoa_ids, "tipo": tipo, "data": date.today().isoformat(), "motivo": motivo, "valor": valor, **extra,
    })


def _retirada(c, pessoa_id, valor, forma="pix", **extra):
    return c.post(f"/cadastro/caixa-funcionarios/{pessoa_id}/retiradas", json={
        "valor": valor, "data": date.today().isoformat(), "forma_pagamento": forma, **extra,
    })


def _caixa(c, pessoa_id):
    r = c.get(f"/cadastro/caixa-funcionarios/{pessoa_id}")
    assert r.status_code == 200, r.text
    return r.json()


class TestEntradas:
    def test_entrada_gera_movimento_e_despesa_baixada(self, client):
        c, engine = client
        pid = _pessoa(c)
        r = _entrada(c, [pid], 500.0)
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 500.0
        caixa = _caixa(c, pid)
        assert caixa["saldo"] == 500.0 and caixa["movimentos"][0]["tipo"] == "deposito"
        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Caixa do funcionário")).one()
            assert conta.tipo == "despesa" and conta.valor_pago == 500.0 and conta.data_pagamento == date.today()
            mov = s.exec(select(CaixaMovimento)).one()
            assert mov.lancamento_id == conta.id and mov.numero_lancamento == conta.numero_lancamento

    def test_entrada_em_lote_para_varias_pessoas(self, client):
        c, _ = client
        a, b = _pessoa(c, "Ana"), _pessoa(c, "Carlos", "Diarista")
        r = _entrada(c, [a, b], 200.0, tipo="outro", motivo="Ajuda de custo")
        assert r.status_code == 200 and r.json()["total"] == 400.0
        assert _caixa(c, a)["saldo"] == 200.0 and _caixa(c, b)["saldo"] == 200.0

    def test_comissao_calcula_valor_da_base_e_percentual(self, client):
        c, _ = client
        pid = _pessoa(c)
        r = c.post("/cadastro/caixa-funcionarios/entradas", json={
            "pessoa_ids": [pid], "tipo": "comissao", "data": date.today().isoformat(), "motivo": "Venda do lote 14",
            "base_valor": 40000.0, "percentual": 1.0,
        })
        assert r.status_code == 200, r.text
        mov = _caixa(c, pid)["movimentos"][0]
        assert mov["valor"] == 400.0 and mov["base_valor"] == 40000.0 and "1%" in mov["motivo"]

    @pytest.mark.parametrize("corpo,trecho", [
        ({"motivo": "  "}, "motivo"), ({"valor": 0}, "valor"), ({"tipo": "xyz"}, "Tipo"), ({"pessoa_ids": []}, "pessoa"),
    ])
    def test_validacoes(self, client, corpo, trecho):
        c, _ = client
        pid = _pessoa(c)
        base = {"pessoa_ids": [pid], "tipo": "deposito", "data": date.today().isoformat(), "motivo": "x", "valor": 10.0}
        r = c.post("/cadastro/caixa-funcionarios/entradas", json={**base, **corpo})
        assert r.status_code == 400 and trecho.lower() in r.text.lower()


class TestRetirada:
    def test_retirada_baixa_saldo_e_gera_recibo(self, client):
        c, _ = client
        pid = _pessoa(c)
        _entrada(c, [pid], 1000.0)
        r = _retirada(c, pid, 300.0, numero_documento_pagamento="88412")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["saldo_anterior"] == 1000.0 and corpo["saldo_depois"] == 700.0
        assert corpo["movimento"]["numero_recibo"].startswith(f"CX-{date.today().year}-")
        assert _caixa(c, pid)["saldo"] == 700.0
        rec = c.get(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{corpo['movimento']['id']}/recibo")
        assert rec.status_code == 200 and rec.json()["saldo_depois"] == 700.0

    def test_retirada_acima_do_saldo_e_bloqueada(self, client):
        c, _ = client
        pid = _pessoa(c)
        _entrada(c, [pid], 100.0)
        r = _retirada(c, pid, 100.01)
        assert r.status_code == 409 and "Vale" in r.text
        assert _caixa(c, pid)["saldo"] == 100.0

    def test_forma_invalida(self, client):
        c, _ = client
        pid = _pessoa(c)
        _entrada(c, [pid], 100.0)
        assert _retirada(c, pid, 10.0, forma="cheque").status_code == 400


class TestEstornoEExclusao:
    def test_estornar_entrada_cria_movimento_contrario_e_receita_no_financeiro(self, client):
        c, engine = client
        pid = _pessoa(c)
        _entrada(c, [pid], 400.0)
        mov_id = _caixa(c, pid)["movimentos"][0]["id"]
        r = c.post(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{mov_id}/estornar", json={"motivo": "Duplicado"})
        assert r.status_code == 200, r.text
        caixa = _caixa(c, pid)
        assert caixa["saldo"] == 0.0
        original = next(m for m in caixa["movimentos"] if m["id"] == mov_id)
        assert original["estornado"] is True and original["pode_estornar"] is False
        with Session(engine) as s:
            contra = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Estorno caixa do funcionário")).one()
            assert contra.tipo == "receita" and contra.valor_pago == 400.0
        # estorno duplo e estorno de estorno são recusados
        assert c.post(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{mov_id}/estornar", json={"motivo": "x"}).status_code == 409
        estorno_id = next(m["id"] for m in caixa["movimentos"] if m["eh_estorno"])
        assert c.post(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{estorno_id}/estornar", json={"motivo": "x"}).status_code == 409

    def test_estorno_exige_motivo(self, client):
        c, _ = client
        pid = _pessoa(c)
        _entrada(c, [pid], 50.0)
        mov_id = _caixa(c, pid)["movimentos"][0]["id"]
        assert c.post(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{mov_id}/estornar", json={"motivo": " "}).status_code == 400

    def test_nao_estorna_entrada_cujo_saldo_ja_foi_sacado(self, client):
        c, _ = client
        pid = _pessoa(c)
        _entrada(c, [pid], 400.0)
        entrada_id = _caixa(c, pid)["movimentos"][0]["id"]
        _retirada(c, pid, 300.0)
        r = c.post(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{entrada_id}/estornar", json={"motivo": "erro"})
        assert r.status_code == 409 and "retirada" in r.text.lower()

    def test_estornar_retirada_devolve_o_saldo(self, client):
        c, _ = client
        pid = _pessoa(c)
        _entrada(c, [pid], 400.0)
        retirada_id = _retirada(c, pid, 300.0).json()["movimento"]["id"]
        r = c.post(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{retirada_id}/estornar", json={"motivo": "Pix não saiu"})
        assert r.status_code == 200 and _caixa(c, pid)["saldo"] == 400.0

    def test_exclusao_so_do_ultimo_movimento(self, client):
        c, engine = client
        pid = _pessoa(c)
        _entrada(c, [pid], 100.0)
        _entrada(c, [pid], 200.0)
        movs = _caixa(c, pid)["movimentos"]
        primeiro = next(m for m in movs if m["valor"] == 100.0)
        ultimo = next(m for m in movs if m["valor"] == 200.0)
        assert primeiro["pode_excluir"] is False and ultimo["pode_excluir"] is True
        assert c.delete(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{primeiro['id']}").status_code == 409
        r = c.delete(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{ultimo['id']}")
        assert r.status_code == 200
        assert _caixa(c, pid)["saldo"] == 100.0
        with Session(engine) as s:  # a despesa da entrada excluída some junto
            assert len(s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Caixa do funcionário")).all()) == 1


class TestListagem:
    def test_lista_so_colaboradores_e_soma_o_devido(self, client):
        c, _ = client
        a = _pessoa(c, "Ana", "Funcionário")
        _pessoa(c, "Dr. Huerik", "Veterinário")
        e = _pessoa(c, "Luiz", "Empreiteiro")
        _entrada(c, [a], 300.0)
        _entrada(c, [e], 50.0)
        r = c.get("/cadastro/caixa-funcionarios").json()
        nomes = {p["nome"]: p for p in r["pessoas"]}
        assert set(nomes) == {"Ana", "Luiz"}
        assert nomes["Ana"]["grupos"] == ["clt"] and nomes["Luiz"]["grupos"] == ["empreita"]
        assert r["total_devido"] == 350.0


class TestIsolamentoEntreFazendas:
    def test_fazenda_b_nao_ve_nem_movimenta_o_caixa_da_a(self, client_multi):
        engine, make = client_multi
        # O override da fazenda "atual" é global: troca a cada chamada (make devolve o cliente já ajustado).
        pid = _pessoa(make(1))
        assert _entrada(make(1), [pid], 100.0).status_code == 200
        mov_id = _caixa(make(1), pid)["movimentos"][0]["id"]
        assert make(2).get(f"/cadastro/caixa-funcionarios/{pid}").status_code == 404
        assert _entrada(make(2), [pid], 10.0).status_code == 404
        assert _retirada(make(2), pid, 10.0).status_code == 404
        assert make(2).post(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{mov_id}/estornar", json={"motivo": "x"}).status_code == 404
        assert make(2).delete(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{mov_id}").status_code == 404
        assert make(2).get("/cadastro/caixa-funcionarios").json()["pessoas"] == []
        assert _caixa(make(1), pid)["saldo"] == 100.0
        with Session(engine) as s:
            assert all(m.fazenda_id == 1 for m in s.exec(select(CaixaMovimento)).all())
