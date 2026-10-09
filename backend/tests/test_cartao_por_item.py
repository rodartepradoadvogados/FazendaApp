"""
Fase A — PR 5 (cartão de crédito por item; erro 3 da auditoria), fora do cenário
grande (que está em tests/test_relatorios_cenario_auditoria.py, §3c).

  - rateio da diferença em centavos (o mesmo da fatura de fornecedor);
  - compra vira nota em aberto (conta, centro, competência = compra,
    vencimento = fatura); IOF/anuidade são compras próprias;
  - nota de fatura de cartão só se paga pela fatura: 409 no individual, no
    lote, no lote detalhado e no estorno;
  - pagar a fatura baixa todas as notas e rateia a diferença (juros em Outras);
    compra lançada antes da flag ganha a nota no pagamento; estorno da fatura;
  - fatura aberta em Contas a pagar e no Caixa Real; DRE competência × caixa;
  - flag desligada: compra sem nota, fatura pela nota genérica, mesmas chaves;
  - backfill (dry-run, revisão, saldo inalterado, reverter com conflito);
  - isolamento entre fazendas; migração b9d3f5a1c864.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest
from sqlmodel import Session, select

from fazenda.models import ContaGerencial, FaturaCartao, LancamentoCartao, LancamentoItem
from fazenda.rules.cartao_por_item import ratear_diferenca
from fazenda.rules.datas import hoje_local
from tests.test_relatorios_regras_v2 import (  # noqa: F401  (fixture `api`)
    _alembic, _colunas, _dre, _lanc, _ligar, _linha, _ok, _plano, api,
)

REVISAO_ANTERIOR = "a7c4e2d9b351"
REVISAO = "b9d3f5a1c864"
HOJE = hoje_local()
# Compras sempre num mês futuro, com fechamento no dia 20: a fatura nunca
# fecha sozinha durante o teste (ver o comentário em test_cartao_credito.py).
_MES = (HOJE.replace(day=1) + timedelta(days=40)).replace(day=1)
COMPRA = _MES.replace(day=5)
COMPETENCIA = f"{_MES:%Y-%m}"
VENCIMENTO = _MES.replace(day=28)


def _cartao(c, conta_bancaria_id=None):
    return _ok(c.post("/financeiro/cartoes", json={"apelido": "Visa", "dia_fechamento": 20, "dia_vencimento": 28,
                                                   "conta_bancaria_id": conta_bancaria_id}))


def _compra(c, cartao_id, valor, codigo="3.01", descricao="Ração", data=COMPRA):
    return _ok(c.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
        "data_compra": data.isoformat(), "descricao": descricao, "codigo_conta_gerencial": codigo, "valor": valor}))


def _preparar(c, engine, *, flag=True, com_conta=True):
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    _plano(c, "3.09", "Tarifas e IOF", "DESPESAS_OPERACIONAIS")
    if flag:
        _ligar(engine)
    conta = _ok(c.post("/financeiro/contas-correntes", json={"banco": "Banco X", "agencia": "1", "numero_conta": "2"})) if com_conta else None
    return conta, _cartao(c, conta["id"] if conta else None)


def _notas(engine, fatura_id):
    with Session(engine) as s:
        return s.exec(select(ContaGerencial).where(ContaGerencial.fatura_cartao_id == fatura_id).order_by(ContaGerencial.id)).all()


# =============================================================================
# Regra pura
# =============================================================================
@pytest.mark.parametrize("valores, pago, esperado", [
    ([800, 300], 1111, [8.0, 3.0]),
    ([800, 300], 1100, [0.0, 0.0]),
    ([100, 100, 100], 299.99, [0.0, 0.0, -0.01]),
    ([100, 100, 100], 300.01, [0.0, 0.0, 0.01]),
    ([333.33, 666.67], 990, [-3.33, -6.67]),
    ([50], 45, [-5.0]),
    ([], 10, []),
])
def test_ratear_diferenca_em_centavos(valores, pago, esperado):
    cotas = ratear_diferenca(valores, pago)
    assert cotas == esperado
    if valores:
        assert round(sum(valores) + sum(cotas), 2) == round(pago, 2)


# =============================================================================
# Compra = nota em aberto; só se paga pela fatura
# =============================================================================
def test_compra_no_cartao_vira_nota_em_aberto_com_conta_e_competencia_da_compra(api):
    c, engine, _ = api
    _conta, cartao = _preparar(c, engine)
    r = _compra(c, cartao["id"], 800)
    _compra(c, cartao["id"], 12.5, codigo="3.09", descricao="IOF")
    assert r["numero_lancamento"] and r["competencia"] == COMPETENCIA
    notas = _notas(engine, r["fatura_id"])
    assert [(n.descricao, n.valor_total, n.data_competencia, n.data_vencimento, n.codigo_conta, n.data_pagamento)
            for n in notas] == [("Ração", 800, COMPRA, VENCIMENTO, "3.01", None), ("IOF", 12.5, COMPRA, VENCIMENTO, "3.09", None)]
    with Session(engine) as s:
        item = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == r["numero_lancamento"])).one()
        assert (item.codigo_conta_gerencial, item.valor_total, item.data_competencia) == ("3.01", 800, COMPRA)
        assert s.get(LancamentoCartao, r["id"]).numero_lancamento == r["numero_lancamento"]
    # Competência: no mês da compra, cada uma na sua conta (IOF é compra própria).
    d = _dre(c, _MES.isoformat(), VENCIMENTO.isoformat())
    assert (_linha(d, "CUSTO_VARIAVEL"), _linha(d, "DESPESAS_OPERACIONAIS")) == (800, 12.5)
    extrato = _ok(c.get(f"/financeiro/cartoes/{cartao['id']}/extrato", params={"competencia": COMPETENCIA}))
    assert [x["numero_lancamento"] for x in extrato["lancamentos"]] == [n.numero_lancamento for n in notas]


def test_nota_de_fatura_de_cartao_nao_baixa_sozinha_409(api):
    c, engine, _ = api
    conta, cartao = _preparar(c, engine)
    nota = _notas(engine, _compra(c, cartao["id"], 800)["fatura_id"])[0]
    baixa = {"data_pagamento": HOJE.isoformat(), "valor_pago": 800, "conta_bancaria": conta["rotulo"]}
    assert c.put(f"/financeiro/lancamentos/{nota.id}/pagar", json=baixa).status_code == 409
    assert c.put("/financeiro/lancamentos/baixa-lote", json={"lancamento_ids": [nota.id], "data_pagamento": HOJE.isoformat()}).status_code == 409
    assert c.put("/financeiro/lancamentos/baixa-lote-detalhada", json={"itens": [{"lancamento_id": nota.id, **baixa}]}).status_code == 409
    assert c.post(f"/financeiro/lancamentos/{nota.id}/estornar", json={"motivo": "x"}).status_code == 409
    assert _notas(engine, nota.fatura_cartao_id)[0].data_pagamento is None


def test_pagar_fatura_baixa_todas_as_notas_e_rateia_diferenca(api):
    """Fatura de 800 + 300 paga por 1.111: acréscimo de 11 rateado 8/3; a soma
    dos valor_pago dá 1.111; os 11 viram juros em Outras (PR 7)."""
    c, engine, _ = api
    conta, cartao = _preparar(c, engine)
    fatura_id = _compra(c, cartao["id"], 800)["fatura_id"]
    _compra(c, cartao["id"], 300, descricao="Sal mineral")
    assert c.post(f"/financeiro/cartoes/faturas/{fatura_id}/pagar", json={}).status_code == 400  # aberta
    _ok(c.post(f"/financeiro/cartoes/faturas/{fatura_id}/fechar", json={}))
    data = VENCIMENTO.isoformat()
    r = _ok(c.post(f"/financeiro/cartoes/faturas/{fatura_id}/pagar", json={"data_pagamento": data, "valor_pago": 1111}))
    assert r["status"] == "paga" and r["lancamento"] is None and r["diferenca"] == 11
    assert (r["valor_pago"], r["desconto_acrescimo"]) == (1111, 11)
    notas = _notas(engine, fatura_id)
    assert [(n.valor_pago, n.desconto_acrescimo, n.data_pagamento, n.conta_corrente_id, n.forma_pagamento) for n in notas] == [
        (808, 8, VENCIMENTO, conta["id"], "transferencia"), (303, 3, VENCIMENTO, conta["id"], "transferencia")]
    assert round(sum(n.valor_pago for n in notas), 2) == 1111
    with Session(engine) as s:
        assert s.exec(select(ContaGerencial).where(ContaGerencial.descricao.like("Fatura %"))).all() == []
        assert s.get(FaturaCartao, fatura_id).numero_lancamento is None
    # Saldo da conta do cartão no dia do pagamento; DRE de caixa no mês do pagamento.
    saldo = next(x for x in _ok(c.get("/financeiro/contas-correntes", params={"hoje": data})) if x["id"] == conta["id"])
    assert saldo["saldo"] == -1111
    dc = _dre(c, VENCIMENTO.replace(day=1).isoformat(), data, regime="caixa")
    assert (_linha(dc, "CUSTO_VARIAVEL"), _linha(dc, "OUTRAS_REC_DESP")) == (1100, -11)
    assert c.post(f"/financeiro/cartoes/faturas/{fatura_id}/pagar", json={}).status_code == 400  # já paga
    # Estorno da fatura: as notas voltam juntas.
    assert c.post(f"/financeiro/cartoes/faturas/{fatura_id}/estornar-pagamento", json={"motivo": ""}).status_code == 400
    e = _ok(c.post(f"/financeiro/cartoes/faturas/{fatura_id}/estornar-pagamento", json={"motivo": "pago errado"}))
    assert e["status"] == "fechada" and e["valor_pago"] is None
    assert all(n.data_pagamento is None and n.valor_pago is None and n.conta_corrente_id is None for n in _notas(engine, fatura_id))


def test_compra_lancada_antes_da_flag_ganha_nota_ao_pagar_a_fatura(api):
    c, engine, _ = api
    _conta, cartao = _preparar(c, engine, flag=False)
    fatura_id = _compra(c, cartao["id"], 200)["fatura_id"]
    assert _notas(engine, fatura_id) == []
    _ligar(engine)
    _compra(c, cartao["id"], 100, descricao="Depois da flag")
    _ok(c.post(f"/financeiro/cartoes/faturas/{fatura_id}/fechar", json={}))
    r = _ok(c.post(f"/financeiro/cartoes/faturas/{fatura_id}/pagar", json={"data_pagamento": VENCIMENTO.isoformat()}))
    assert len(r["notas_pagas"]) == 2 and r["diferenca"] == 0
    assert sorted(n.valor_pago for n in _notas(engine, fatura_id)) == [100, 200]


def test_fatura_aberta_aparece_no_caixa_real_e_em_contas_a_pagar(api):
    c, engine, _ = api
    _conta, cartao = _preparar(c, engine)
    compra_proxima = HOJE  # fatura que vence dentro da janela de 90 dias
    r = _compra(c, cartao["id"], 450, descricao="Peça", data=compra_proxima)
    nota = _notas(engine, r["fatura_id"])[0]
    a_pagar = [x for x in _ok(c.get("/financeiro/contas-a-pagar", params={"dias": 90})) if x["id"] == nota.id]
    assert [(x["valor_total"], x["fatura_cartao_id"]) for x in a_pagar] == [(450, r["fatura_id"])]
    cr = _ok(c.get("/financeiro/caixa-real", params={"dias": 90}))
    itens = [(p["data"], i) for p in cr["serie"] for i in p["itens"] if i["descricao"] == "Peça"]
    assert len(itens) == 1 and itens[0][0] == nota.data_vencimento.isoformat() and itens[0][1]["fatura_cartao"] is True
    lista = {x["id"]: x for x in _ok(c.get("/financeiro/lancamentos"))["lancamentos"]}
    assert lista[nota.id]["fatura_cartao_id"] == r["fatura_id"]


def test_flag_desligada_cartao_como_antes(api):
    c, engine, _ = api
    _conta, cartao = _preparar(c, engine, flag=False)
    r = _compra(c, cartao["id"], 800)
    assert "numero_lancamento" not in r
    assert _notas(engine, r["fatura_id"]) == []
    fechada = _ok(c.post(f"/financeiro/cartoes/faturas/{r['fatura_id']}/fechar", json={}))
    assert "valor_pago" not in fechada and "desconto_acrescimo" not in fechada
    paga = _ok(c.post(f"/financeiro/cartoes/faturas/{r['fatura_id']}/pagar", json={"data_pagamento": VENCIMENTO.isoformat(), "valor_pago": 1}))
    assert paga["lancamento"]["valor_liquido"] == 800 and paga["numero_lancamento"]  # nota genérica, valor_pago ignorado
    assert c.post(f"/financeiro/cartoes/faturas/{r['fatura_id']}/estornar-pagamento", json={"motivo": "x"}).status_code == 409


# =============================================================================
# Backfill
# =============================================================================
def test_backfill_cartao_revisao_saldo_inalterado_e_conflito_na_reversao(api):
    from scripts.backfill_cartao_por_item import executar

    c, engine, _ = api
    conta, cartao = _preparar(c, engine, flag=False)
    paga_id = _compra(c, cartao["id"], 700)["fatura_id"]
    _ok(c.post(f"/financeiro/cartoes/faturas/{paga_id}/fechar", json={}))
    _ok(c.post(f"/financeiro/cartoes/faturas/{paga_id}/pagar", json={"data_pagamento": VENCIMENTO.isoformat()}))
    aberta = _compra(c, cartao["id"], 90, data=(_MES + timedelta(days=40)).replace(day=3))
    # Fatura "paga" sem nota genérica (dado inconsistente): vai para revisão.
    with Session(engine) as s:
        f = FaturaCartao(fazenda_id=1, cartao_id=cartao["id"], competencia="2030-01", data_fechamento=date(2030, 1, 20),
                         data_vencimento=date(2030, 1, 28), valor_total=10, status="paga")
        s.add(f)
        s.commit()
        s.add(LancamentoCartao(fazenda_id=1, cartao_id=cartao["id"], fatura_id=f.id, data_compra=date(2030, 1, 2),
                               descricao="Órfã", valor=10))
        s.commit()
    hoje_fim = (VENCIMENTO + timedelta(days=120)).isoformat()

    def saldo():
        return next(x for x in _ok(c.get("/financeiro/contas-correntes", params={"hoje": hoje_fim})) if x["id"] == conta["id"])["saldo"]
    _ligar(engine)
    antes = saldo()
    with Session(engine) as s:
        plano = executar(s, 1, aplicar=False, saida=lambda *_: None)["plano"]
        assert sorted(n["tipo"] for n in plano.notas) == ["nota_aberta", "nota_paga"]
        assert [r["competencia"] for r in plano.revisao] == ["2030-01"] and len(plano.genericas) == 1
    with Session(engine) as s:
        lote = executar(s, 1, aplicar=True, saida=lambda *_: None)["lote"]
    assert saldo() == antes == -700
    paga_nota = _notas(engine, paga_id)[0]
    assert (paga_nota.gerado_por, paga_nota.conta_bancaria, paga_nota.valor_pago) == ("backfill_cartao", None, 700)
    assert _linha(_dre(c, _MES.isoformat(), VENCIMENTO.isoformat()), "CUSTO_VARIAVEL") == 700
    # A nota da fatura aberta é paga depois pela fatura: na reversão ela vira conflito e fica.
    _ok(c.post(f"/financeiro/cartoes/faturas/{aberta['fatura_id']}/fechar", json={}))
    _ok(c.post(f"/financeiro/cartoes/faturas/{aberta['fatura_id']}/pagar", json={"data_pagamento": hoje_fim}))
    assert saldo() == -790
    with Session(engine) as s:
        resultado = executar(s, 1, aplicar=True, reverter=lote, saida=lambda *_: None)["reversao"]
        assert len(resultado.conflitos) == 1 and resultado.conflitos[0]["tabela"] == "conta_gerencial"
    assert _notas(engine, paga_id) == [] and len(_notas(engine, aberta["fatura_id"])) == 1
    assert saldo() == -790
    with Session(engine) as s:
        generica = s.exec(select(ContaGerencial).where(ContaGerencial.descricao.like("Fatura %"))).one()
        assert generica.natureza_fin is None


# =============================================================================
# Isolamento entre fazendas
# =============================================================================
def test_cartao_por_item_nao_vaza_entre_fazendas(api):
    from scripts.backfill_cartao_por_item import executar

    c, engine, estado = api
    _conta, cartao = _preparar(c, engine)
    r = _compra(c, cartao["id"], 800)
    _ok(c.post(f"/financeiro/cartoes/faturas/{r['fatura_id']}/fechar", json={}))
    nota = _notas(engine, r["fatura_id"])[0]
    estado["fazenda_id"] = 2
    assert c.post(f"/financeiro/cartoes/faturas/{r['fatura_id']}/pagar", json={}).status_code == 404
    assert c.post(f"/financeiro/cartoes/faturas/{r['fatura_id']}/estornar-pagamento", json={"motivo": "x"}).status_code == 409  # F2 sem flag
    assert c.put(f"/financeiro/lancamentos/{nota.id}/pagar", json={"data_pagamento": HOJE.isoformat(), "valor_pago": 800}).status_code == 404
    assert all(x["id"] != nota.id for x in _ok(c.get("/financeiro/contas-a-pagar", params={"dias": 400})))
    _ligar(engine, 2)
    assert c.post(f"/financeiro/cartoes/faturas/{r['fatura_id']}/estornar-pagamento", json={"motivo": "x"}).status_code == 404
    with Session(engine) as s:
        assert executar(s, 2, aplicar=True, saida=lambda *_: None)["lote"] is None  # nada da 1 entra no plano da 2
    estado["fazenda_id"] = 1
    assert _notas(engine, r["fatura_id"])[0].data_pagamento is None


# =============================================================================
# Migração
# =============================================================================
def test_migracao_cartao_por_item_sobe_desce_e_e_idempotente(tmp_path):
    db = tmp_path / "mig.db"
    _alembic(db, "upgrade", REVISAO_ANTERIOR)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO conta_gerencial (numero_lancamento, tipo, valor_total, valor_pago, origem, atualizado_em) "
                 "VALUES ('LC-1', 'despesa', 800.0, 800.0, 'manual', '2026-01-01')")
    conn.commit()
    conn.close()
    _alembic(db, "upgrade", REVISAO)
    assert _colunas(db, "conta_gerencial")["fatura_cartao_id"]["notnull"] == 0
    assert {"valor_pago", "desconto_acrescimo"} <= set(_colunas(db, "fatura_cartao"))
    assert "numero_lancamento" in _colunas(db, "lancamento_cartao")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT valor_total, valor_pago, fatura_cartao_id FROM conta_gerencial").fetchone() == (800.0, 800.0, None)
    assert "fatura_cartao" in [r[2] for r in conn.execute("PRAGMA foreign_key_list(conta_gerencial)")]
    conn.close()
    _alembic(db, "downgrade", REVISAO_ANTERIOR)
    assert "fatura_cartao_id" not in _colunas(db, "conta_gerencial")
    assert "valor_pago" not in _colunas(db, "fatura_cartao") and "numero_lancamento" not in _colunas(db, "lancamento_cartao")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT valor_total, valor_pago FROM conta_gerencial").fetchone() == (800.0, 800.0)
    conn.close()
    db2 = tmp_path / "boot.db"
    _alembic(db2, "upgrade", REVISAO_ANTERIOR)
    conn = sqlite3.connect(db2)
    conn.execute("ALTER TABLE conta_gerencial ADD COLUMN fatura_cartao_id INTEGER")
    conn.execute("ALTER TABLE lancamento_cartao ADD COLUMN numero_lancamento VARCHAR")
    conn.commit()
    conn.close()
    _alembic(db2, "upgrade", "head")
    assert "(head)" in _alembic(db2, "current")
    assert "valor_pago" in _colunas(db2, "fatura_cartao")
