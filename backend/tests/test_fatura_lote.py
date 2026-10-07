"""Lançamento em lote (Entrega 1 das Faturas de fornecedor): várias notas de um fornecedor, uma
fatura já fechada/paga, tudo ou nada."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Estoque, FaturaFornecedor, LancamentoItem,
)


class _FakeUser:
    id = 1
    papel = "admin"
    ativo = True
    username = "teste"
    nome = "Jairo Teste"
    permissoes = None


@pytest.fixture
def ambiente():
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
def multi():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="financeiro", ativo=True))
        s.commit()

    def _sess():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    def _make(fid):
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fid
        return TestClient(main.app)

    yield engine, _make
    main.app.dependency_overrides.clear()


def _item(produto="Lavagem", valor=100.0, tipo="servico", qtd=1.0):
    return {"produto": produto, "tipo_item": tipo, "quantidade": qtd, "valor_unitario": valor / qtd, "valor_total": valor,
            "codigo_conta_gerencial": "3.02.01.03", "nome_conta_gerencial": "Combustíveis"}


def _nota(numero="1001", dia=3, itens=None, **extra):
    return {"tipo_documento": "Nota fiscal", "numero_documento": numero, "data_emissao": f"2026-10-{dia:02d}",
            "itens": itens or [_item()], **extra}


def _lote(**extra):
    corpo = {"fornecedor": "Posto Ipiranga", "conta_bancaria": "BB", "centro_custo": "Pecuária Leiteira",
             "notas": [_nota("1001", 3), _nota("1002", 5, [_item("Gasolina", 242.0, "produto", 40.0), _item("Lavagem", 60.0)])],
             "modo": "venc", "data_vencimento": "2026-11-01"}
    corpo.update(extra)
    return corpo


class TestLote:
    def test_vencimento_unico_cria_notas_e_fatura_fechada(self, ambiente):
        c, engine = ambiente
        r = c.post("/financeiro/faturas/lote", json=_lote())
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["status"] == "fechada" and d["valor_total"] == 402.0 and len(d["notas"]) == 2
        assert len({n["numero_lancamento"] for n in d["notas"]}) == 2
        with Session(engine) as s:
            contas = s.exec(select(ContaGerencial)).all()
            assert len(contas) == 2 and all(x.fatura_id == d["fatura_id"] for x in contas)
            assert {x.data_vencimento for x in contas} == {date(2026, 11, 1)} and all(x.data_pagamento is None for x in contas)
            assert {x.numero_nota for x in contas} == {"1001", "1002"} and contas[0].responsavel == "Jairo Teste"
            f = s.get(FaturaFornecedor, d["fatura_id"])
            assert f.origem == "lote" and f.data_abertura == date(2026, 10, 3) and f.rotulo == "Posto Ipiranga — 10/2026"
            assert len(s.exec(select(LancamentoItem)).all()) == 3

    def test_parcelar_divide_cada_nota_nas_mesmas_parcelas(self, ambiente):
        c, engine = ambiente
        r = c.post("/financeiro/faturas/lote", json=_lote(
            modo="parc", data_vencimento=None, parcelamento={"n": 3, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"}))
        assert r.status_code == 201, r.text
        with Session(engine) as s:
            contas = s.exec(select(ContaGerencial)).all()
            assert len(contas) == 6
            assert sorted({x.data_vencimento for x in contas}) == [date(2026, 11, 30), date(2026, 12, 30), date(2027, 1, 30)]
            por_nota = {}
            for x in contas:
                por_nota.setdefault(x.numero_lancamento, []).append(x.valor_total)
            assert sorted(round(sum(v), 2) for v in por_nota.values()) == [100.0, 302.0]
            assert s.get(FaturaFornecedor, r.json()["fatura_id"]).parcelas_n == 3

    def test_centavos_da_parcela_fecham_exatamente(self, ambiente):
        c, engine = ambiente
        r = c.post("/financeiro/faturas/lote", json=_lote(
            notas=[_nota("9", 3, [_item("X", 100.0)])], modo="parc", data_vencimento=None,
            parcelamento={"n": 3, "primeiro_vencimento": "2026-11-10", "intervalo": "30dias"}))
        assert r.status_code == 201, r.text
        with Session(engine) as s:
            assert sorted(x.valor_total for x in s.exec(select(ContaGerencial)).all()) == [33.33, 33.33, 33.34]

    def test_ja_pago_baixa_tudo_e_fatura_paga(self, ambiente):
        c, engine = ambiente
        r = c.post("/financeiro/faturas/lote", json=_lote(
            modo="pago", data_vencimento=None,
            pagamento={"data_pagamento": "2026-10-31", "forma_pagamento": "pix", "numero_documento_pagamento": "E123"}))
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "paga"
        with Session(engine) as s:
            for x in s.exec(select(ContaGerencial)).all():
                assert x.data_pagamento == date(2026, 10, 31) and x.valor_pago == x.valor_total
                assert x.forma_pagamento == "pix" and x.conta_bancaria == "BB" and x.numero_documento_pagamento == "E123"

    def test_desconto_nasce_na_nota(self, ambiente):
        c, engine = ambiente
        r = c.post("/financeiro/faturas/lote", json=_lote(notas=[_nota("1", 3, [_item("X", 100.0)], desconto=10.0)]))
        assert r.status_code == 201, r.text
        assert r.json()["valor_total"] == 90.0


class TestValidacoes:
    def test_campos_obrigatorios(self, ambiente):
        c, _ = ambiente
        assert c.post("/financeiro/faturas/lote", json=_lote(fornecedor=" ")).status_code == 400
        assert c.post("/financeiro/faturas/lote", json=_lote(notas=[])).status_code == 400
        assert c.post("/financeiro/faturas/lote", json=_lote(data_vencimento=None)).status_code == 400
        assert c.post("/financeiro/faturas/lote", json=_lote(modo="pago", pagamento=None)).status_code == 400
        assert c.post("/financeiro/faturas/lote", json=_lote(modo="parc", parcelamento={"n": 1, "primeiro_vencimento": "2026-11-01"})).status_code == 400
        assert c.post("/financeiro/faturas/lote", json=_lote(notas=[_nota(numero="")])).status_code == 400
        assert c.post("/financeiro/faturas/lote", json=_lote(notas=[_nota(numero="", sem_numero=True)])).status_code == 201

    def test_duplicada_dentro_do_lote_bloqueia(self, ambiente):
        c, engine = ambiente
        r = c.post("/financeiro/faturas/lote", json=_lote(notas=[_nota("77", 3), _nota("77", 4)]))
        assert r.status_code == 400 and "repete" in r.text
        with Session(engine) as s:
            assert s.exec(select(ContaGerencial)).all() == []

    def test_duplicada_contra_o_que_existe_avisa_e_confirma(self, ambiente):
        c, engine = ambiente
        assert c.post("/financeiro/faturas/lote", json=_lote(notas=[_nota("500", 3)])).status_code == 201
        r = c.post("/financeiro/faturas/lote", json=_lote(notas=[_nota("500", 9)]))
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "duplicadas"
        r = c.post("/financeiro/faturas/lote", json=_lote(notas=[_nota("500", 9)], confirmar_duplicados=True))
        assert r.status_code == 201
        # outro fornecedor com o mesmo número NÃO é duplicada
        assert c.post("/financeiro/faturas/lote", json=_lote(fornecedor="Outro", notas=[_nota("500", 9)])).status_code == 201

    def test_divergencia_com_o_total_do_fornecedor(self, ambiente):
        c, _ = ambiente
        r = c.post("/financeiro/faturas/lote", json=_lote(total_fornecedor=400.0))
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "divergencia_total"
        assert c.post("/financeiro/faturas/lote", json=_lote(total_fornecedor=400.0, confirmar_divergencia=True)).status_code == 201
        assert c.post("/financeiro/faturas/lote", json=_lote(fornecedor="B", total_fornecedor=402.0)).status_code == 201


class TestTudoOuNada:
    def test_falha_na_segunda_nota_desfaz_a_primeira(self, ambiente):
        c, engine = ambiente
        with Session(engine) as s:
            s.add(Estoque(nome="Filtro velho", unidade="un", ativo=False))
            s.commit()
        notas = [_nota("1", 3), _nota("2", 4, [_item("Filtro velho", 50.0, "produto", 1.0)])]
        r = c.post("/financeiro/faturas/lote", json=_lote(notas=notas))
        assert r.status_code == 409 and "Nota 2" in r.text and "inativo" in r.text
        with Session(engine) as s:
            assert s.exec(select(ContaGerencial)).all() == []
            assert s.exec(select(LancamentoItem)).all() == []
            assert s.exec(select(FaturaFornecedor)).all() == []

    def test_entrada_de_estoque_participa_da_mesma_transacao(self, ambiente):
        c, engine = ambiente
        with Session(engine) as s:
            s.add(Estoque(nome="Óleo diesel", unidade="L", quantidade=0.0, ativo=True))
            s.commit()
        r = c.post("/financeiro/faturas/lote", json=_lote(notas=[_nota("1", 3, [_item("Óleo diesel", 600.0, "produto", 100.0)])]))
        assert r.status_code == 201, r.text
        with Session(engine) as s:
            assert s.exec(select(Estoque)).first().quantidade == 100.0


class TestIsolamento:
    def test_lista_e_detalhe_so_da_propria_fazenda(self, multi):
        engine, make = multi
        c1 = make(1)
        r = c1.post("/financeiro/faturas/lote", json=_lote())
        assert r.status_code == 201, r.text
        fid = r.json()["fatura_id"]
        assert [f["id"] for f in c1.get("/financeiro/faturas").json()] == [fid]
        assert c1.get(f"/financeiro/faturas/{fid}").json()["notas"] == 2
        c2 = make(2)
        assert c2.get("/financeiro/faturas").json() == []
        assert c2.get(f"/financeiro/faturas/{fid}").status_code == 404
