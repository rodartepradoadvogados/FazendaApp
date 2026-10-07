"""Faturas de fornecedor — Entrega 2 (modo Faturas): abrir, lançar notas, fechar, reabrir,
parcelar, pagar por parcela, estornar, inserir/tirar nota e excluir."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, ContratoFazenda, ContratoFazendaModulo, FaturaFornecedor


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


def _item(produto="Ração", valor=100.0):
    return {"produto": produto, "tipo_item": "servico", "quantidade": 1.0, "valor_unitario": valor, "valor_total": valor}


def _nota(numero, dia=5, valor=100.0, **extra):
    return {"tipo_documento": "Nota fiscal", "numero_documento": numero, "data_emissao": f"2026-10-{dia:02d}",
            "itens": [_item(valor=valor)], **extra}


def _abrir(c, **extra):
    corpo = {"fornecedor": "Cooperativa", "data_abertura": "2026-10-01", "data_fechamento_prevista": "2026-10-31",
             "data_vencimento": "2026-11-10", "conta_bancaria": "BB", "centro_custo": "Pecuária Leiteira"}
    corpo.update(extra)
    r = c.post("/financeiro/faturas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _notas(c, fid, *notas, **extra):
    return c.post(f"/financeiro/faturas/{fid}/notas", json={"notas": list(notas), **extra})


def _linhas(engine, **filtro):
    with Session(engine) as s:
        q = select(ContaGerencial)
        for k, v in filtro.items():
            q = q.where(getattr(ContaGerencial, k) == v)
        return s.exec(q.order_by(ContaGerencial.numero_lancamento, ContaGerencial.parcela_num)).all()


class TestAbrirEditar:
    def test_abre_aberta_com_rotulo_padrao_e_historico(self, ambiente):
        c, _ = ambiente
        f = _abrir(c)
        assert f["status"] == "aberta" and f["rotulo"] == "Cooperativa — 10/2026" and f["origem"] == "fatura"
        assert [e["acao"] for e in f["eventos"]] == ["aberta"]

    def test_validacoes(self, ambiente):
        c, _ = ambiente
        assert c.post("/financeiro/faturas", json={"fornecedor": "", "data_abertura": "2026-10-01", "data_vencimento": "2026-11-10"}).status_code == 400
        assert c.post("/financeiro/faturas", json={"fornecedor": "X", "data_abertura": "2026-10-01"}).status_code == 400  # sem vencimento
        assert c.post("/financeiro/faturas", json={"fornecedor": "X", "data_abertura": "2026-10-10", "data_fechamento_prevista": "2026-10-01", "data_vencimento": "2026-11-01"}).status_code == 400
        assert c.post("/financeiro/faturas", json={"fornecedor": "X", "data_abertura": "2026-10-01", "parcelamento": {"n": 1, "primeiro_vencimento": "2026-11-01"}}).status_code == 400

    def test_parcelamento_no_cadastro_define_o_vencimento(self, ambiente):
        c, _ = ambiente
        f = _abrir(c, data_vencimento=None, parcelamento={"n": 3, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"})
        assert f["data_vencimento"] == "2026-11-30" and f["parcelas_n"] == 3 and f["parcelamento_origem"] == "cadastro"

    def test_editar_so_aberta_e_reaplica_o_vencimento(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        assert _notas(c, f["id"], _nota("1")).status_code == 201
        r = c.put(f"/financeiro/faturas/{f['id']}", json={"fornecedor": "Cooperativa", "data_abertura": "2026-10-01", "data_vencimento": "2026-11-20"})
        assert r.status_code == 200, r.text
        assert {x.data_vencimento for x in _linhas(engine)} == {date(2026, 11, 20)}
        assert c.put(f"/financeiro/faturas/{f['id']}", json={"fornecedor": "Outro", "data_abertura": "2026-10-01", "data_vencimento": "2026-11-20"}).status_code == 409


class TestNotasNaFatura:
    def test_nota_nasce_com_o_vencimento_da_fatura_e_vinculada(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        r = _notas(c, f["id"], _nota("1", valor=100.0), _nota("2", valor=50.0))
        assert r.status_code == 201, r.text
        linhas = _linhas(engine)
        assert len(linhas) == 2 and {x.data_vencimento for x in linhas} == {date(2026, 11, 10)}
        assert all(x.fatura_id == f["id"] for x in linhas)
        d = c.get(f"/financeiro/faturas/{f['id']}").json()
        assert d["valor_total"] == 150.0 and d["notas"] == 2 and d["status"] == "aberta"

    def test_nota_com_parcelamento_do_cadastro_nasce_parcelada(self, ambiente):
        c, engine = ambiente
        f = _abrir(c, data_vencimento=None, parcelamento={"n": 3, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"})
        assert _notas(c, f["id"], _nota("1", valor=100.0)).status_code == 201
        assert [x.valor_total for x in _linhas(engine)] == [33.33, 33.33, 33.34]
        assert [x.parcela_total for x in _linhas(engine)] == [3, 3, 3]

    def test_fora_do_periodo_pergunta_e_depois_aceita(self, ambiente):
        c, _ = ambiente
        f = _abrir(c)
        r = _notas(c, f["id"], _nota("1", dia=5), {**_nota("2"), "data_emissao": "2026-09-28"})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "fora_do_periodo"
        assert r.json()["detail"]["fora"][0]["nota"] == 2
        assert _notas(c, f["id"], {**_nota("2"), "data_emissao": "2026-09-28"}, confirmar_fora_periodo=True).status_code == 201
        r = _notas(c, f["id"], {**_nota("3"), "data_emissao": "2026-11-05"})
        assert r.status_code == 409 and "posterior" in r.text

    def test_so_em_fatura_aberta_e_tudo_ou_nada(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        r = _notas(c, f["id"], _nota("1"), {**_nota("2"), "itens": [{"produto": "", "tipo_item": "servico", "valor_total": 10.0}]})
        assert r.status_code == 400 and _linhas(engine) == []
        assert _notas(c, f["id"], _nota("1")).status_code == 201
        assert c.post(f"/financeiro/faturas/{f['id']}/fechar", json={}).status_code == 200
        assert _notas(c, f["id"], _nota("9")).status_code == 409

    def test_duplicada_contra_existente_avisa(self, ambiente):
        c, _ = ambiente
        f = _abrir(c)
        assert _notas(c, f["id"], _nota("500")).status_code == 201
        r = _notas(c, f["id"], _nota("500"))
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "duplicadas"
        assert _notas(c, f["id"], _nota("500"), confirmar_duplicados=True).status_code == 201

    def test_notas_avulsas_sem_fatura(self, ambiente):
        c, engine = ambiente
        r = c.post("/financeiro/faturas/notas-avulsas", json={"fornecedor": "Cooperativa", "notas": [_nota("7")], "data_vencimento": "2026-11-15"})
        assert r.status_code == 201, r.text
        assert [x.fatura_id for x in _linhas(engine)] == [None]


class TestFecharReabrir:
    def test_fechar_vazia_recusa(self, ambiente):
        c, _ = ambiente
        assert c.post(f"/financeiro/faturas/{_abrir(c)['id']}/fechar", json={}).status_code == 409

    def test_fechar_a_vista_congela_o_total(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        _notas(c, f["id"], _nota("1", valor=100.0), _nota("2", valor=50.0))
        r = c.post(f"/financeiro/faturas/{f['id']}/fechar", json={"total_fornecedor": 150.0})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "fechada" and r.json()["valor_total"] == 150.0
        assert [e["acao"] for e in r.json()["eventos"]][:1] == ["fechada"]

    def test_divergencia_pede_confirmacao(self, ambiente):
        c, _ = ambiente
        f = _abrir(c)
        _notas(c, f["id"], _nota("1", valor=100.0))
        r = c.post(f"/financeiro/faturas/{f['id']}/fechar", json={"total_fornecedor": 90.0})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "divergencia_total"
        assert c.post(f"/financeiro/faturas/{f['id']}/fechar", json={"total_fornecedor": 90.0, "confirmar_divergencia": True}).status_code == 200

    def test_parcelar_no_fechamento_divide_cada_nota(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        _notas(c, f["id"], _nota("1", valor=100.0), _nota("2", valor=50.0))
        r = c.post(f"/financeiro/faturas/{f['id']}/fechar", json={
            "modo": "parcelar", "parcelamento": {"n": 3, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"}})
        assert r.status_code == 200, r.text
        linhas = _linhas(engine)
        assert len(linhas) == 6 and sorted({x.data_vencimento for x in linhas}) == [date(2026, 11, 30), date(2026, 12, 30), date(2027, 1, 30)]
        por_nota = {}
        for x in linhas:
            por_nota.setdefault(x.numero_nota, []).append(x.valor_total)
        assert {k: round(sum(v), 2) for k, v in por_nota.items()} == {"1": 100.0, "2": 50.0}
        assert [p["valor"] for p in r.json()["parcelas"]] == [49.99, 49.99, 50.02]  # 100/3 + 50/3, centavos na última de cada nota
        assert r.json()["parcelamento_origem"] == "fechamento"

    def test_parcelamento_do_cadastro_trava_a_escolha_do_fechamento(self, ambiente):
        c, engine = ambiente
        f = _abrir(c, data_vencimento=None, parcelamento={"n": 2, "primeiro_vencimento": "2026-11-30", "intervalo": "30dias"})
        _notas(c, f["id"], _nota("1", valor=100.0))
        r = c.post(f"/financeiro/faturas/{f['id']}/fechar", json={"modo": "vista"})  # "vista" é ignorado: o cadastro manda
        assert r.status_code == 200 and r.json()["parcelas_n"] == 2 and len(_linhas(engine)) == 2

    def test_reabrir_exige_motivo_e_desfaz_o_parcelamento_do_fechamento(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        _notas(c, f["id"], _nota("1", valor=100.0))
        c.post(f"/financeiro/faturas/{f['id']}/fechar", json={"modo": "parcelar", "parcelamento": {"n": 3, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"}})
        assert c.post(f"/financeiro/faturas/{f['id']}/reabrir", json={"motivo": " "}).status_code == 400
        r = c.post(f"/financeiro/faturas/{f['id']}/reabrir", json={"motivo": "nota esquecida"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "aberta" and r.json()["parcelas_n"] is None
        linhas = _linhas(engine)
        assert len(linhas) == 1 and linhas[0].valor_total == 100.0 and linhas[0].parcela_total == 1 and linhas[0].data_vencimento == date(2026, 11, 30)
        assert r.json()["eventos"][0]["acao"] == "reaberta" and r.json()["eventos"][0]["detalhe"] == "nota esquecida"

    def test_reabrir_mantem_o_parcelamento_do_cadastro(self, ambiente):
        c, engine = ambiente
        f = _abrir(c, data_vencimento=None, parcelamento={"n": 2, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"})
        _notas(c, f["id"], _nota("1", valor=100.0))
        c.post(f"/financeiro/faturas/{f['id']}/fechar", json={})
        r = c.post(f"/financeiro/faturas/{f['id']}/reabrir", json={"motivo": "ajuste"})
        assert r.json()["parcelas_n"] == 2 and len(_linhas(engine)) == 2


class TestPagar:
    def _fechada(self, c, n=None):
        f = _abrir(c)
        _notas(c, f["id"], _nota("1", valor=100.0), _nota("2", valor=50.0))
        corpo = {"modo": "parcelar", "parcelamento": {"n": n, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"}} if n else {}
        assert c.post(f"/financeiro/faturas/{f['id']}/fechar", json=corpo).status_code == 200
        return f["id"]

    def _pagar(self, c, fid, parcela=1, **extra):
        corpo = {"parcela": parcela, "data_pagamento": "2026-11-10", "forma_pagamento": "pix", "conta_bancaria": "BB", "numero_documento_pagamento": "E1"}
        corpo.update(extra)
        return c.post(f"/financeiro/faturas/{fid}/pagar", json=corpo)

    def test_nao_paga_fatura_aberta(self, ambiente):
        c, _ = ambiente
        f = _abrir(c)
        assert self._pagar(c, f["id"]).status_code == 409

    def test_paga_a_vista_baixa_todas_as_notas_e_fecha_a_fatura(self, ambiente):
        c, engine = ambiente
        fid = self._fechada(c)
        r = self._pagar(c, fid)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "paga" and r.json()["paga_em"] == "2026-11-10" and len(r.json()["ids_contas_pagas"]) == 2
        for x in _linhas(engine):
            assert x.data_pagamento == date(2026, 11, 10) and x.valor_pago == x.valor_total and x.forma_pagamento == "pix" and x.numero_documento_pagamento == "E1"
        assert self._pagar(c, fid).status_code == 409  # já paga

    def test_parcela_a_parcela(self, ambiente):
        c, engine = ambiente
        fid = self._fechada(c, n=3)
        r = self._pagar(c, fid, 1)
        assert r.json()["status"] == "fechada" and [p["pago"] for p in r.json()["parcelas"]] == [True, False, False]
        assert self._pagar(c, fid, 1).status_code == 409 and self._pagar(c, fid, 9).status_code == 404
        self._pagar(c, fid, 2)
        r = self._pagar(c, fid, 3)
        assert r.json()["status"] == "paga"

    def test_diferenca_e_rateada_proporcionalmente_e_fecha_a_conta(self, ambiente):
        c, engine = ambiente
        fid = self._fechada(c)  # notas de 100 e 50
        r = self._pagar(c, fid, valor_pago=140.0)  # 10 de desconto
        assert r.status_code == 200 and r.json()["diferenca"] == -10.0
        linhas = _linhas(engine)
        assert round(sum(x.valor_pago for x in linhas), 2) == 140.0 and round(sum(x.desconto_acrescimo for x in linhas), 2) == -10.0
        assert sorted(x.desconto_acrescimo for x in linhas) == [-6.66, -3.34]  # proporcional, centavo sobrante na última

    def test_credito_exige_vencimento_do_cartao_e_forma_valida(self, ambiente):
        c, _ = ambiente
        fid = self._fechada(c)
        assert self._pagar(c, fid, forma_pagamento="credito").status_code == 400
        assert self._pagar(c, fid, forma_pagamento="cheque").status_code == 400

    def test_estornar_devolve_a_fatura_a_fechada_e_paga_nao_reabre(self, ambiente):
        c, engine = ambiente
        fid = self._fechada(c)
        self._pagar(c, fid)
        assert c.post(f"/financeiro/faturas/{fid}/reabrir", json={"motivo": "x"}).status_code == 409
        assert c.post(f"/financeiro/faturas/{fid}/parcelas/1/estornar", json={"motivo": " "}).status_code == 400
        r = c.post(f"/financeiro/faturas/{fid}/parcelas/1/estornar", json={"motivo": "Pix devolvido"})
        assert r.status_code == 200 and r.json()["status"] == "fechada" and r.json()["paga_em"] is None
        assert all(x.data_pagamento is None and x.valor_pago is None for x in _linhas(engine))
        assert c.post(f"/financeiro/faturas/{fid}/parcelas/1/estornar", json={"motivo": "outra vez"}).status_code == 409
        assert c.post(f"/financeiro/faturas/{fid}/reabrir", json={"motivo": "agora sim"}).status_code == 200


class TestInserirTirarExcluir:
    def _avulsa(self, c, numero, fornecedor="Cooperativa", valor=80.0, venc="2026-12-25"):
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "fornecedor_cliente": fornecedor, "tipo_documento": "Nota fiscal", "numero_documento": numero,
            "data_emissao": "2026-10-22", "data_vencimento": venc, "itens": [_item(valor=valor)]})
        assert r.status_code == 201, r.text
        return r.json()["numero_lancamento"]

    def test_inserir_substitui_o_vencimento_da_nota(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        n1, n2 = self._avulsa(c, "A1"), self._avulsa(c, "A2", valor=20.0)
        prev = c.post(f"/financeiro/faturas/{f['id']}/notas/inserir/previa", json={"numeros_lancamento": [n1, n2]})
        assert prev.status_code == 200 and prev.json()["notas"][0]["parcelas_atuais"][0]["vencimento"] == "2026-12-25"
        r = c.post(f"/financeiro/faturas/{f['id']}/notas/inserir", json={"numeros_lancamento": [n1, n2]})
        assert r.status_code == 200, r.text
        assert r.json()["notas"] == 2 and r.json()["valor_total"] == 100.0
        assert {x.data_vencimento for x in _linhas(engine)} == {date(2026, 11, 10)} and all(x.fatura_id == f["id"] for x in _linhas(engine))

    def test_inserir_numa_fatura_parcelada_refaz_as_parcelas(self, ambiente):
        c, engine = ambiente
        f = _abrir(c, data_vencimento=None, parcelamento={"n": 2, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"})
        n1 = self._avulsa(c, "B1", valor=101.0)
        c.post(f"/financeiro/faturas/{f['id']}/notas/inserir", json={"numeros_lancamento": [n1]})
        assert [x.valor_total for x in _linhas(engine)] == [50.5, 50.5] and [x.parcela_total for x in _linhas(engine)] == [2, 2]

    def test_regras_de_quem_pode_entrar(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        outro = self._avulsa(c, "C1", fornecedor="Outro")
        assert c.post(f"/financeiro/faturas/{f['id']}/notas/inserir", json={"numeros_lancamento": [outro]}).status_code == 409
        paga = self._avulsa(c, "C2")
        lid = _linhas(engine, numero_lancamento=paga)[0].id
        assert c.put(f"/financeiro/lancamentos/{lid}/pagar", json={"data_pagamento": "2026-10-30", "valor_pago": 80.0}).status_code == 200
        assert c.post(f"/financeiro/faturas/{f['id']}/notas/inserir", json={"numeros_lancamento": [paga]}).status_code == 409
        ok = self._avulsa(c, "C3")
        assert c.post(f"/financeiro/faturas/{f['id']}/notas/inserir", json={"numeros_lancamento": [ok]}).status_code == 200
        assert c.post(f"/financeiro/faturas/{f['id']}/notas/inserir", json={"numeros_lancamento": [ok]}).status_code == 409  # já está numa fatura
        assert c.post(f"/financeiro/faturas/{f['id']}/notas/inserir", json={"numeros_lancamento": ["LC-0000-99999"]}).status_code == 404
        assert c.post(f"/financeiro/faturas/{f['id']}/notas/inserir", json={"numeros_lancamento": []}).status_code == 400

    def test_tirar_a_nota_volta_a_avulsa_com_vencimento_unico(self, ambiente):
        c, engine = ambiente
        f = _abrir(c, data_vencimento=None, parcelamento={"n": 2, "primeiro_vencimento": "2026-11-30", "intervalo": "mensal"})
        _notas(c, f["id"], _nota("1", valor=100.0))
        numero = _linhas(engine)[0].numero_lancamento
        r = c.post(f"/financeiro/faturas/{f['id']}/notas/{numero}/tirar")
        assert r.status_code == 200 and r.json()["notas"] == 0
        linhas = _linhas(engine)
        assert len(linhas) == 1 and linhas[0].fatura_id is None and linhas[0].valor_total == 100.0 and linhas[0].data_vencimento == date(2026, 11, 30)

    def test_excluir(self, ambiente):
        c, engine = ambiente
        vazia = _abrir(c)
        assert c.delete(f"/financeiro/faturas/{vazia['id']}").status_code == 200
        f = _abrir(c)
        _notas(c, f["id"], _nota("1"))
        assert c.delete(f"/financeiro/faturas/{f['id']}").status_code == 409
        r = c.delete(f"/financeiro/faturas/{f['id']}?soltar_notas=true")
        assert r.status_code == 200 and r.json()["notas_soltas"] == 1
        assert [x.fatura_id for x in _linhas(engine)] == [None]
        with Session(engine) as s:
            assert s.exec(select(FaturaFornecedor)).all() == []

    def test_fatura_com_pagamento_nao_se_exclui(self, ambiente):
        c, _ = ambiente
        f = _abrir(c)
        _notas(c, f["id"], _nota("1"))
        c.post(f"/financeiro/faturas/{f['id']}/fechar", json={})
        c.post(f"/financeiro/faturas/{f['id']}/pagar", json={"parcela": 1, "data_pagamento": "2026-11-10", "forma_pagamento": "pix"})
        assert c.delete(f"/financeiro/faturas/{f['id']}?soltar_notas=true").status_code == 409


class TestIsolamento:
    def test_outra_fazenda_nao_alcanca_a_fatura(self, multi):
        engine, make = multi
        c1 = make(1)
        f = c1.post("/financeiro/faturas", json={"fornecedor": "Coop", "data_abertura": "2026-10-01", "data_vencimento": "2026-11-10"}).json()
        fid = f["id"]
        assert c1.post(f"/financeiro/faturas/{fid}/notas", json={"notas": [_nota("1")]}).status_code == 201
        c2 = make(2)
        assert c2.get(f"/financeiro/faturas/{fid}").status_code == 404
        assert c2.post(f"/financeiro/faturas/{fid}/notas", json={"notas": [_nota("1")]}).status_code == 404
        assert c2.post(f"/financeiro/faturas/{fid}/fechar", json={}).status_code == 404
        assert c2.post(f"/financeiro/faturas/{fid}/pagar", json={"parcela": 1, "data_pagamento": "2026-11-10", "forma_pagamento": "pix"}).status_code == 404
        assert c2.delete(f"/financeiro/faturas/{fid}").status_code == 404
        assert c2.get("/financeiro/faturas").json() == []



class TestNotaDeFaturaNaoEBaixadaSozinha:
    def test_pagar_baixa_lote_e_estornar_isolados_sao_recusados(self, ambiente):
        c, engine = ambiente
        f = _abrir(c)
        r = _notas(c, f["id"], _nota("9001", 5, 100.0))
        assert r.status_code == 201, r.text
        cid = r.json()["ids_contas"][0]
        corpo = {"data_pagamento": "2026-10-20", "valor_pago": 100.0, "forma_pagamento": "pix", "conta_bancaria": "BB"}
        assert c.put(f"/financeiro/lancamentos/{cid}/pagar", json=corpo).status_code == 409
        assert c.put("/financeiro/lancamentos/baixa-lote", json={
            "lancamento_ids": [cid], "data_pagamento": "2026-10-20", "forma_pagamento": "pix", "conta_bancaria": "BB"}).status_code == 409
        assert c.post(f"/financeiro/lancamentos/{cid}/estornar", json={}).status_code == 409
        assert all(l.data_pagamento is None for l in _linhas(engine, fatura_id=f["id"]))
