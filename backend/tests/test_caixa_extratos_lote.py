"""Extratos do mês em lote (vários colaboradores de uma vez)."""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from fazenda.models import CaixaMovimento
from tests.test_caixa_time import _h, ambiente  # noqa: F401


def _mov(engine, pessoa_id, tipo, valor, dia, fid=1):
    with Session(engine) as s:
        s.add(CaixaMovimento(fazenda_id=fid, pessoa_id=pessoa_id, tipo=tipo, valor=valor, data=dia, motivo="teste"))
        s.commit()


def _extratos(c, fid=1, **params):
    r = c.get("/cadastro/caixa-funcionarios/extratos", params=params, headers=_h(fid))
    assert r.status_code == 200, r.text
    return r.json()


def test_traz_so_quem_teve_movimento_ou_tem_saldo(ambiente):
    c, engine, ids = ambiente
    _mov(engine, ids["a"], "deposito", 300.0, date(2026, 8, 10))   # saldo anterior de agosto → entra em setembro
    _mov(engine, ids["b"], "deposito", 100.0, date(2026, 9, 5))    # movimento em setembro
    d = _extratos(c, mes="2026-09")
    nomes = [e["pessoa"]["nome"] for e in d["extratos"]]
    assert nomes == ["Ana", "Bia"] and d["total"] == 2          # Caio (sem nada) e Xande (outra fazenda) ficam de fora
    ana = d["extratos"][0]
    assert ana["saldo_anterior"] == 300.0 and ana["saldo_final"] == 300.0 and ana["movimentos"] == []
    bia = d["extratos"][1]
    assert bia["saldo_anterior"] == 0.0 and bia["saldo_final"] == 100.0 and len(bia["movimentos"]) == 1


def test_incluir_todos_e_filtros_por_pessoa_e_grupo(ambiente):
    c, engine, ids = ambiente
    _mov(engine, ids["a"], "deposito", 50.0, date(2026, 9, 1))
    todos = _extratos(c, mes="2026-09", so_com_movimento="false")
    assert [e["pessoa"]["nome"] for e in todos["extratos"]] == ["Ana", "Bia", "Caio"]
    so_diaria = _extratos(c, mes="2026-09", so_com_movimento="false", grupos="diaria")
    assert [e["pessoa"]["nome"] for e in so_diaria["extratos"]] == ["Caio"]
    escolhidos = _extratos(c, mes="2026-09", so_com_movimento="false", pessoa_ids=f"{ids['b']},{ids['c']}")
    assert [e["pessoa"]["nome"] for e in escolhidos["extratos"]] == ["Bia", "Caio"]


def test_estorno_aparece_marcado_e_o_saldo_fecha(ambiente):
    c, engine, ids = ambiente
    _mov(engine, ids["a"], "deposito", 200.0, date(2026, 9, 2))
    with Session(engine) as s:
        orig = s.exec(select(CaixaMovimento).where(CaixaMovimento.pessoa_id == ids["a"])).first()
        s.add(CaixaMovimento(fazenda_id=1, pessoa_id=ids["a"], tipo="estorno", valor=-200.0, data=date(2026, 9, 3), motivo="erro", estorna_id=orig.id))
        s.commit()
    e = _extratos(c, mes="2026-09")["extratos"][0]
    assert [m["estornado"] for m in e["movimentos"]] == [True, False] and e["saldo_final"] == 0.0


def test_igual_ao_extrato_individual_e_isolado_por_fazenda(ambiente):
    c, engine, ids = ambiente
    _mov(engine, ids["a"], "deposito", 80.0, date(2026, 9, 9))
    lote = _extratos(c, mes="2026-09")["extratos"][0]
    solo = c.get(f"/cadastro/caixa-funcionarios/{ids['a']}/extrato", params={"mes": "2026-09"}, headers=_h()).json()
    assert lote == solo
    _mov(engine, ids["x"], "deposito", 999.0, date(2026, 9, 9), fid=2)
    assert all(e["pessoa"]["nome"] != "Xande" for e in _extratos(c, mes="2026-09")["extratos"])
    assert [e["pessoa"]["nome"] for e in _extratos(c, fid=2, mes="2026-09")["extratos"]] == ["Xande"]


def test_validacoes(ambiente):
    c, _, _ = ambiente
    assert c.get("/cadastro/caixa-funcionarios/extratos", params={"mes": "2026-13"}, headers=_h()).status_code == 400
    assert c.get("/cadastro/caixa-funcionarios/extratos", params={"mes": "2026-09", "pessoa_ids": "a,b"}, headers=_h()).status_code == 400
