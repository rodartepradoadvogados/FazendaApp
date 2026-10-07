"""Caixa dos funcionários — Fase 4: rodapé do holerite, extrato mensal, rescisão e Agenda."""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    CaixaTime, CaixaTimeMembro, ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaPagamento, Pessoa, Usuario,
    UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import caixa_time as regras


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
        for chave, fid, nome in (("a", 1, "Ana"), ("b", 1, "Bia"), ("x", 2, "Xande")):
            p = Pessoa(nome=nome, tipo="Funcionário", salario_base=3000.0, data_admissao=date(2020, 1, 1), fazenda_id=fid)
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


def _entrada_pessoa(c, pid, valor, fid=1):
    r = c.post("/cadastro/caixa-funcionarios/entradas", json={
        "pessoa_ids": [pid], "tipo": "deposito", "data": date.today().isoformat(), "motivo": "Bônus", "valor": valor}, headers=_h(fid))
    assert r.status_code == 200, r.text


def _time_com_saldo(c, valor=1000.0):
    tid = c.post("/cadastro/caixa-time", json={"nome": "Turma", "auto_tipos": ["clt"]}, headers=_h()).json()["id"]
    r = c.post(f"/cadastro/caixa-time/{tid}/entradas", json={
        "tipo": "deposito", "data": date.today().isoformat(), "motivo": "Resultado", "valor": valor}, headers=_h())
    assert r.status_code == 200, r.text
    return tid


class TestRodape:
    def test_saldo_individual_e_parte_do_time(self, ambiente):
        c, _, ids = ambiente
        _entrada_pessoa(c, ids["a"], 300)
        _time_com_saldo(c, 1000)
        r = c.get("/cadastro/caixa-funcionarios/rodape-recibos", headers=_h()).json()["por_pessoa"]
        a = r[str(ids["a"])]
        assert a["saldo_individual"] == 300.0
        assert a["times"][0]["parte_estimada"] == 500.0 and a["times"][0]["saldo"] == 1000.0
        assert r[str(ids["b"])]["saldo_individual"] == 0.0 and r[str(ids["b"])]["times"][0]["parte_estimada"] == 500.0

    def test_so_admin_e_so_a_propria_fazenda(self, ambiente):
        c, _, ids = ambiente
        _entrada_pessoa(c, ids["a"], 300)
        assert str(ids["a"]) not in c.get("/cadastro/caixa-funcionarios/rodape-recibos", headers=_h(2)).json()["por_pessoa"]

    def test_listagem_da_folha_nao_vaza_o_rodape(self, ambiente):
        c, _, ids = ambiente
        _entrada_pessoa(c, ids["a"], 300)
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": ids["a"], "competencia": "2026-02", "valor_bruto": 3000.0, "percentual_inss": 9.0, "valor_inss": 270.0},
            headers=_h())
        for f in c.get("/cadastro/folha-pagamento", headers=_h()).json():
            assert "caixa_congelado" not in f

    def test_pagamento_congela_o_rodape_e_estorno_descongela(self, ambiente):
        c, engine, ids = ambiente
        _entrada_pessoa(c, ids["a"], 300)
        fo = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": ids["a"], "competencia": "2026-02", "valor_bruto": 3000.0, "percentual_inss": 9.0, "valor_inss": 270.0},
            headers=_h()).json()["id"]
        assert c.post(f"/cadastro/folha-pagamento/{fo}/pagar", json={"data_pagamento": "2026-03-05"}, headers=_h()).status_code == 200
        _entrada_pessoa(c, ids["a"], 100)  # depois do pagamento: não pode mudar o recibo
        por_folha = c.get("/cadastro/caixa-funcionarios/rodape-recibos", headers=_h()).json()["por_folha"]
        assert por_folha[str(fo)]["saldo_individual"] == 300.0
        assert c.post(f"/cadastro/folha-pagamento/{fo}/estornar", json={}, headers=_h()).status_code == 200
        assert str(fo) not in c.get("/cadastro/caixa-funcionarios/rodape-recibos", headers=_h()).json()["por_folha"]


class TestExtrato:
    def test_extrato_do_mes(self, ambiente):
        c, _, ids = ambiente
        _entrada_pessoa(c, ids["a"], 300)
        hoje = date.today()
        r = c.get(f"/cadastro/caixa-funcionarios/{ids['a']}/extrato?mes={hoje:%Y-%m}", headers=_h()).json()
        assert r["saldo_anterior"] == 0.0 and r["saldo_final"] == 300.0 and len(r["movimentos"]) == 1
        proximo = (hoje.replace(day=1) + timedelta(days=32)).replace(day=1)
        r2 = c.get(f"/cadastro/caixa-funcionarios/{ids['a']}/extrato?mes={proximo:%Y-%m}", headers=_h()).json()
        assert r2["saldo_anterior"] == 300.0 and r2["movimentos"] == []

    def test_mes_invalido_e_outra_fazenda(self, ambiente):
        c, _, ids = ambiente
        assert c.get(f"/cadastro/caixa-funcionarios/{ids['a']}/extrato?mes=xx", headers=_h()).status_code == 400
        assert c.get(f"/cadastro/caixa-funcionarios/{ids['a']}/extrato?mes=2026-01", headers=_h(2)).status_code == 404


class TestRescisaoETime:
    def test_saida_mantem_os_dias_e_o_rateio(self, ambiente):
        c, engine, ids = ambiente
        tid = _time_com_saldo(c, 1000)
        with Session(engine) as s:
            ana = s.get(Pessoa, ids["a"])
            regras.registrar_saida_dos_times(s, ana, date.today() - timedelta(days=10), 1)
            ana.ativo = False
            s.add(ana)
            s.commit()
            t = s.get(CaixaTime, tid)
            ini, fim, _ = regras.periodo_em_apuracao(date.today(), [(6, 1), (12, 1)])
            membros = {m["pessoa_id"]: m for m in regras.membros_do_periodo(s, t, ini, fim)}
        assert ids["a"] in membros and membros[ids["a"]]["saida"] == date.today() - timedelta(days=10)
        assert 0 < membros[ids["a"]]["dias"] < membros[ids["b"]]["dias"]

    def test_saida_nao_cria_membro_em_time_de_outra_fazenda_nem_sem_vinculo(self, ambiente):
        c, engine, ids = ambiente
        with Session(engine) as s:
            s.add(CaixaTime(fazenda_id=2, nome="Outro", auto_tipos="clt"))
            s.commit()
            regras.registrar_saida_dos_times(s, s.get(Pessoa, ids["a"]), date.today(), 1)
            s.commit()
            assert s.exec(select(CaixaTimeMembro)).all() == []


class TestAgenda:
    def test_rateio_proximo_aparece_e_some_com_rascunho(self, ambiente):
        c, engine, ids = ambiente
        tid = _time_com_saldo(c, 500)
        with Session(engine) as s:
            ini, fim, entrega = regras.periodo_em_apuracao(date.today(), [(6, 1), (12, 1)])
            perto = regras.rateios_proximos(s, 1, hoje=entrega - timedelta(days=3))
            longe = regras.rateios_proximos(s, 1, hoje=entrega - timedelta(days=60))
        assert [p["nome"] for p in perto] == ["Turma"] and perto[0]["faltam"] == 3
        assert longe == []
