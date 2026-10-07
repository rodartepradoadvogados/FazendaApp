"""Caixa dos funcionários — Fase 3: caixa do time (PL) e rateio."""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    CaixaMovimento, CaixaTimeMovimento, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa,
    PessoaAnexo, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import caixa_time as regras
from fazenda.rules.caixa_funcionario import grupos_da_pessoa


class TestCalculo:
    def test_soma_exata_e_proporcional_aos_dias(self):
        r = regras.calcular_partes(21400, [{"pessoa_id": i, "dias": 183 if i < 6 else 92, "penalidade_pct": 0} for i in range(1, 7)])
        assert round(sum(x["parte_final"] for x in r), 2) == 21400.0
        assert r[5]["parte_final"] < r[0]["parte_final"]

    def test_penalidade_vai_para_os_demais(self):
        r = regras.calcular_partes(1000, [
            {"pessoa_id": 1, "dias": 100, "penalidade_pct": 50}, {"pessoa_id": 2, "dias": 100, "penalidade_pct": 0},
            {"pessoa_id": 3, "dias": 100, "penalidade_pct": 0}])
        assert [x["parte_final"] for x in r] == [166.67, 416.67, 416.66] or round(sum(x["parte_final"] for x in r), 2) == 1000.0
        assert r[0]["parte_final"] == pytest.approx(166.67, abs=0.01)

    def test_todos_penalizados_recusa(self):
        with pytest.raises(ValueError):
            regras.calcular_partes(100, [{"pessoa_id": 1, "dias": 10, "penalidade_pct": 10}])

    def test_resto_de_centavos_nao_some(self):
        r = regras.calcular_partes(100, [{"pessoa_id": i, "dias": 1, "penalidade_pct": 0} for i in range(3)])
        assert round(sum(x["parte_final"] for x in r), 2) == 100.0

    def test_periodo_e_proxima_entrega(self):
        d = [(6, 1), (12, 1)]
        assert regras.periodo_em_apuracao(date(2026, 10, 7), d) == (date(2026, 6, 1), date(2026, 11, 30), date(2026, 12, 1))
        assert regras.periodo_em_apuracao(date(2026, 12, 5), d)[2] == date(2027, 6, 1)

    def test_dias_no_periodo(self):
        assert regras.dias_no_periodo(date(2020, 1, 1), None, date(2026, 6, 1), date(2026, 11, 30)) == 183
        assert regras.dias_no_periodo(date(2026, 9, 10), None, date(2026, 6, 1), date(2026, 11, 30)) == 82
        assert regras.dias_no_periodo(date(2027, 1, 1), None, date(2026, 6, 1), date(2026, 11, 30)) == 0


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)
    ids: dict[str, int] = {}
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.commit()
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
        s.commit()
        for chave, fid, nome, tipo in (("a", 1, "Ana", "Funcionário"), ("b", 1, "Bia", "Funcionário"), ("c", 1, "Caio", "Diarista"),
                                       ("x", 2, "Xande", "Funcionário")):
            p = Pessoa(nome=nome, tipo=tipo, salario_base=2000.0, data_admissao=date(2020, 1, 1), fazenda_id=fid)
            s.add(p)
            s.commit()
            s.refresh(p)
            ids[chave] = p.id

    def _sess():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _h(fid=1):
    return {"Authorization": f"Bearer {criar_token(f'admin{fid}', fazenda_id=fid)}"}


def _time(c, fid=1, auto=("clt",)):
    r = c.post("/cadastro/caixa-time", json={"nome": "Turma", "auto_tipos": list(auto)}, headers=_h(fid))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _entrada(c, tid, valor=900.0, fid=1):
    r = c.post(f"/cadastro/caixa-time/{tid}/entradas", json={
        "tipo": "deposito", "data": date.today().isoformat(), "motivo": "Resultado", "valor": valor}, headers=_h(fid))
    assert r.status_code == 200, r.text


def _rateio(c, tid, fid=1):
    r = c.post(f"/cadastro/caixa-time/{tid}/rateios", json={
        "periodo_inicio": "2026-01-01", "periodo_fim": "2026-06-30", "data_entrega": "2026-07-01"}, headers=_h(fid))
    return r


def _saldo(c, pid):
    return c.get(f"/cadastro/caixa-funcionarios/{pid}", headers=_h()).json()["saldo"]


class TestTime:
    def test_entrada_gera_despesa_baixada_e_saldo(self, ambiente):
        c, engine, ids = ambiente
        tid = _time(c)
        _entrada(c, tid, 900)
        d = c.get(f"/cadastro/caixa-time/{tid}", headers=_h()).json()
        assert d["saldo"] == 900.0 and d["membros"] == 2  # só CLT (Ana e Bia); Caio é diarista
        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Caixa do time")).first()
            assert conta.valor_pago == 900.0 and conta.tipo == "despesa"

    def test_estorno_da_entrada_e_bloqueado_depois_do_rateio(self, ambiente):
        c, _, ids = ambiente
        tid = _time(c)
        _entrada(c, tid)
        mid = c.get(f"/cadastro/caixa-time/{tid}", headers=_h()).json()["movimentos"][0]["id"]
        rid = _rateio(c, tid).json()["id"]
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 200
        r = c.post(f"/cadastro/caixa-time/{tid}/movimentos/{mid}/estornar", json={"motivo": "x"}, headers=_h())
        assert r.status_code == 409

    def test_membro_por_nome_e_saida(self, ambiente):
        c, _, ids = ambiente
        tid = _time(c, auto=())
        assert c.post(f"/cadastro/caixa-time/{tid}/membros", json={"pessoa_ids": [ids["a"], ids["c"]], "entrada": "2020-01-01"}, headers=_h()).status_code == 200
        assert c.get(f"/cadastro/caixa-time/{tid}", headers=_h()).json()["membros"] == 2
        c.delete(f"/cadastro/caixa-time/{tid}/membros/{ids['c']}", headers=_h())
        assert c.get(f"/cadastro/caixa-time/{tid}", headers=_h()).json()["membros"] == 2  # ainda contou dias até hoje


class TestRateio:
    def test_rateio_confirma_credita_e_desfaz(self, ambiente):
        c, _, ids = ambiente
        tid = _time(c)
        _entrada(c, tid, 900)
        r = _rateio(c, tid)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        assert sorted(l["parte_final"] for l in r.json()["linhas"]) == [450.0, 450.0]
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 200
        assert _saldo(c, ids["a"]) == 450.0 and _saldo(c, ids["b"]) == 450.0
        assert c.get(f"/cadastro/caixa-time/{tid}", headers=_h()).json()["saldo"] == 0.0
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/desfazer", headers=_h()).status_code == 200
        assert _saldo(c, ids["a"]) == 0.0
        assert c.get(f"/cadastro/caixa-time/{tid}", headers=_h()).json()["saldo"] == 900.0

    def test_penalidade_exige_documento(self, ambiente):
        c, engine, ids = ambiente
        tid = _time(c)
        _entrada(c, tid, 900)
        rid = _rateio(c, tid).json()["id"]
        r = c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['a']}", json={
            "penalidade_pct": 50, "penalidade_motivo": "Art. 482 CLT"}, headers=_h())
        assert r.status_code == 200 and r.json()["documentos_pendentes"] == ["Ana"]
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 409
        with Session(engine) as s:
            a = PessoaAnexo(pessoa_id=ids["a"], fazenda_id=1, categoria="Documento de ciência de penalidade",
                            nome_arquivo="d.pdf", tamanho_bytes=5, mime_type="application/pdf")
            s.add(a)
            s.commit()
            aid = a.id
        r = c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['a']}", json={
            "penalidade_pct": 50, "penalidade_motivo": "Art. 482 CLT", "documento_anexo_id": aid}, headers=_h())
        assert r.json()["documentos_pendentes"] == []
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 200
        assert _saldo(c, ids["a"]) == 225.0 and _saldo(c, ids["b"]) == 675.0

    def test_documento_de_outra_pessoa_e_recusado(self, ambiente):
        c, engine, ids = ambiente
        tid = _time(c)
        _entrada(c, tid)
        rid = _rateio(c, tid).json()["id"]
        with Session(engine) as s:
            a = PessoaAnexo(pessoa_id=ids["b"], fazenda_id=1, categoria="x", nome_arquivo="d", tamanho_bytes=1, mime_type="a/b")
            s.add(a)
            s.commit()
            aid = a.id
        r = c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['a']}", json={
            "penalidade_pct": 10, "penalidade_motivo": "m", "documento_anexo_id": aid}, headers=_h())
        assert r.status_code == 404

    def test_desfazer_bloqueado_se_ja_sacou(self, ambiente):
        c, _, ids = ambiente
        tid = _time(c)
        _entrada(c, tid)
        rid = _rateio(c, tid).json()["id"]
        c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h())
        assert c.post(f"/cadastro/caixa-funcionarios/{ids['a']}/retiradas", json={
            "valor": 100, "data": date.today().isoformat(), "forma_pagamento": "pix"}, headers=_h()).status_code == 200
        r = c.post(f"/cadastro/caixa-time/rateios/{rid}/desfazer", headers=_h())
        assert r.status_code == 409
        assert _saldo(c, ids["b"]) == 450.0  # nada foi desfeito pela metade

    def test_pagamento_direto_credita_e_retira(self, ambiente):
        c, _, ids = ambiente
        tid = _time(c)
        _entrada(c, tid)
        rid = _rateio(c, tid).json()["id"]
        c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['a']}", json={"destino": "direto", "forma_pagamento": "pix"}, headers=_h())
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 200
        assert _saldo(c, ids["a"]) == 0.0 and _saldo(c, ids["b"]) == 450.0
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/desfazer", headers=_h()).status_code == 409

    def test_nao_estorna_nem_exclui_credito_de_rateio_pelo_caixa_individual(self, ambiente):
        c, engine, ids = ambiente
        tid = _time(c)
        _entrada(c, tid)
        rid = _rateio(c, tid).json()["id"]
        c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h())
        with Session(engine) as s:
            mid = s.exec(select(CaixaMovimento).where(CaixaMovimento.pessoa_id == ids["a"], CaixaMovimento.tipo == "rateio")).first().id
        assert c.post(f"/cadastro/caixa-funcionarios/{ids['a']}/movimentos/{mid}/estornar", json={"motivo": "x"}, headers=_h()).status_code == 409
        assert c.delete(f"/cadastro/caixa-funcionarios/{ids['a']}/movimentos/{mid}", headers=_h()).status_code == 409

    def test_so_um_rascunho_e_sem_saldo_recusa(self, ambiente):
        c, _, ids = ambiente
        tid = _time(c)
        assert _rateio(c, tid).status_code == 409  # sem saldo
        _entrada(c, tid)
        assert _rateio(c, tid).status_code == 200
        assert _rateio(c, tid).status_code == 409  # já há rascunho

    def test_saldo_mudou_depois_do_rascunho(self, ambiente):
        c, _, ids = ambiente
        tid = _time(c)
        _entrada(c, tid, 900)
        rid = _rateio(c, tid).json()["id"]
        _entrada(c, tid, 100)
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 409


class TestIsolamento:
    def test_fazenda_2_nao_alcanca_o_time_da_1(self, ambiente):
        c, _, ids = ambiente
        tid = _time(c)
        _entrada(c, tid)
        rid = _rateio(c, tid).json()["id"]
        assert c.get(f"/cadastro/caixa-time/{tid}", headers=_h(2)).status_code == 404
        assert c.get(f"/cadastro/caixa-time/rateios/{rid}", headers=_h(2)).status_code == 404
        assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h(2)).status_code == 404
        assert c.post(f"/cadastro/caixa-time/{tid}/membros", json={"pessoa_ids": [ids["x"]]}, headers=_h(2)).status_code == 404
        assert c.get("/cadastro/caixa-time", headers=_h(2)).json()["times"] == []
        # membro de outra fazenda não entra
        assert c.post(f"/cadastro/caixa-time/{tid}/membros", json={"pessoa_ids": [ids["x"]]}, headers=_h(1)).status_code == 404
