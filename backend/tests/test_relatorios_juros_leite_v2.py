"""
Fase A — PR 7 (juros e descontos da baixa) e PR 4 (receita do leite): unidades
e integração fora do cenário grande da auditoria (que está em
tests/test_relatorios_cenario_auditoria.py, seção 3).

  - rules/juros_descontos.py e rules/unidades.leite_em_litros;
  - motor da DRE: `linha_forcada` só com regras v2;
  - rateio do acréscimo da fatura de fornecedor em Outras;
  - receita com vários itens e filtro de centro de custo (dedução proporcional);
  - entrega em litros não converte; baixa em lote detalhada com abatimento;
  - estorno limpa o tipo da diferença; isolamento entre fazendas;
  - migração f3b8d1c6a9e2 (upgrade/downgrade em SQLite descartável).
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from fazenda.models import ContaGerencial
from fazenda.rules import juros_descontos as jd
from fazenda.rules.dre import montar_cascata_dre
from fazenda.rules.unidades import DENSIDADE_LEITE_KG_POR_L, leite_em_litros
from tests.test_relatorios_regras_v2 import (  # noqa: F401  (fixture `api`)
    _alembic, _colunas, _dre, _lanc, _ligar, _linha, _ok, _plano, api,
)

REVISAO_ANTERIOR = "e5a9c3f1b742"
REVISAO = "f3b8d1c6a9e2"


def _conta(**kw):
    base = {"data_pagamento": "2031-04-01", "valor_pago": 100.0, "desconto_acrescimo": 0.0, "diferenca_tipo": None}
    return SimpleNamespace(**{**base, **kw})


def _pagar(c, conta_id, valor, data="2031-04-20", **extra):
    return _ok(c.put(f"/financeiro/lancamentos/{conta_id}/pagar", json={
        "data_pagamento": data, "valor_pago": valor, "forma_pagamento": "pix", **extra}))


# =============================================================================
# Regras puras
# =============================================================================
def test_diferenca_da_baixa_e_seus_casos():
    assert jd.diferenca_da_baixa(_conta(desconto_acrescimo=12.5)) == 12.5
    assert jd.diferenca_da_baixa(_conta(desconto_acrescimo=-700, valor_pago=None)) == 0  # pago sem valor_pago
    assert jd.diferenca_da_baixa(_conta(desconto_acrescimo=-100, valor_pago=0)) == 0
    assert jd.diferenca_da_baixa(_conta(data_pagamento=None, desconto_acrescimo=5)) == 0
    assert jd.diferenca_da_baixa(_conta(desconto_acrescimo=None)) == 0
    abat = _conta(desconto_acrescimo=-40, diferenca_tipo="abatimento")
    assert (jd.diferenca_abatida(abat), jd.diferenca_financeira(abat)) == (-40, 0)
    fin = _conta(desconto_acrescimo=-40)
    assert (jd.diferenca_abatida(fin), jd.diferenca_financeira(fin)) == (0, -40)
    # Abatimento gravado num acréscimo (dado inconsistente) continua financeiro.
    assert jd.diferenca_financeira(_conta(desconto_acrescimo=30, diferenca_tipo="abatimento")) == 30


def test_pseudocontas_e_normalizacao():
    assert jd.pseudoconta_da_diferenca("despesa", 50)[0] == "(juros e multas pagos)"
    assert jd.pseudoconta_da_diferenca("despesa", -50)[0] == "(descontos obtidos)"
    assert jd.pseudoconta_da_diferenca("receita", 50)[0] == "(juros recebidos)"
    assert jd.pseudoconta_da_diferenca("receita", -50)[2] == "despesa"
    assert jd.normalizar_tipo_diferenca(None) is None and jd.normalizar_tipo_diferenca(" Financeiro ") is None
    assert jd.normalizar_tipo_diferenca("ABATIMENTO") == "abatimento"
    with pytest.raises(ValueError):
        jd.normalizar_tipo_diferenca("desconto")


def test_fator_bruto_da_receita():
    assert jd.fator_bruto_da_receita(10000, 150, None) == pytest.approx(10000 / 9850)
    assert jd.fator_bruto_da_receita(1000, 100, 50) == pytest.approx(1050 / 950)
    assert jd.fator_bruto_da_receita(1000, 0, 50) is None
    assert jd.fator_bruto_da_receita(100, 200, None) is None


def test_leite_em_litros():
    assert leite_em_litros(10320, "kg") == pytest.approx(10029.15, abs=0.01)
    assert leite_em_litros(10320, None) == leite_em_litros(10320, "kg")
    assert leite_em_litros(5000, "L") == pytest.approx(5000)
    assert leite_em_litros(5000, " l ") == pytest.approx(5000)
    assert leite_em_litros(1029, "kg") * DENSIDADE_LEITE_KG_POR_L == pytest.approx(1029)


def test_motor_so_honra_linha_forcada_com_regras_v2():
    reg = [{"codigo_conta": "(juros e multas pagos)", "tipo": "despesa", "valor": 50.0,
            "linha_forcada": "OUTRAS_REC_DESP", "natureza": "OPERACIONAL"}]
    antigo = montar_cascata_dre(reg, {})
    assert antigo["nao_classificado"]["total"] == 50
    novo = montar_cascata_dre(reg, {}, regras_v2=True)
    assert {x["chave"]: x["valor"] for x in novo["linhas"]}["OUTRAS_REC_DESP"] == -50
    assert novo["nao_classificado"]["total"] == 0


# =============================================================================
# API
# =============================================================================
def test_rateio_acrescimo_da_fatura_de_fornecedor_aparece_em_outras(api):
    c, engine, _ = api
    _plano(c, "3.02", "Combustíveis", "DESPESA_VARIAVEL")
    item = {"produto": "Diesel", "tipo_item": "produto", "quantidade": 1, "codigo_conta_gerencial": "3.02"}
    lote = _ok(c.post("/financeiro/faturas/lote", json={
        "fornecedor": "Posto", "centro_custo": "Pecuária Leiteira", "modo": "venc", "data_vencimento": "2031-04-10",
        "notas": [
            {"tipo_documento": "Nota fiscal", "numero_documento": "1", "data_emissao": "2031-03-05",
             "itens": [{**item, "valor_unitario": 100, "valor_total": 100}]},
            {"tipo_documento": "Nota fiscal", "numero_documento": "2", "data_emissao": "2031-03-06",
             "itens": [{**item, "valor_unitario": 300, "valor_total": 300}]},
        ],
    }))
    fatura_id = lote["fatura_id"]
    _ok(c.post(f"/financeiro/faturas/{fatura_id}/pagar",
               json={"parcela": 1, "data_pagamento": "2031-04-12", "forma_pagamento": "pix", "valor_pago": 450}))
    _ligar(engine)
    d = _dre(c, "2031-04-01", "2031-04-30", regime="caixa")
    assert _linha(d, "OUTRAS_REC_DESP") == -50
    assert _linha(d, "DESPESA_VARIAVEL") == 400
    assert sum(x["valor"] for x in d["diferencas_baixa"]) == 50
    # A nota da fatura continua só pagável pela fatura (regra de domínio intocada).
    conta_id = d["diferencas_baixa"][0]["conta_id"]
    assert c.put(f"/financeiro/lancamentos/{conta_id}/pagar", json={
        "data_pagamento": "2031-04-12", "valor_pago": 1, "forma_pagamento": "pix"}).status_code == 409


def test_receita_com_varios_itens_e_centro_de_custo_deduz_proporcional(api):
    c, engine, _ = api
    _plano(c, "2.01", "Leite", "RECEITA_VENDAS")
    _plano(c, "2.02", "Venda de bezerros", "RECEITA_VENDAS")
    _ok(c.post("/financeiro/lancamentos", json={
        "tipo": "receita", "centro_custo": "Pecuária Leiteira", "fornecedor_cliente": "Laticínio", "desconto": 100,
        "data_emissao": "2031-03-31", "data_competencia": "2031-03-31",
        "itens": [
            {"produto": "Leite", "codigo_conta_gerencial": "2.01", "valor_total": 600, "tipo_item": "servico"},
            {"produto": "Bezerros", "codigo_conta_gerencial": "2.02", "valor_total": 400, "tipo_item": "servico",
             "centro_custo": "Agricultura"},
        ],
    }))
    _ligar(engine)
    d = _dre(c)
    assert (_linha(d, "RECEITA_VENDAS"), _linha(d, "DEDUCAO_IMPOSTOS"), _linha(d, "RECEITA_LIQUIDA")) == (1000, 100, 900)
    so_leite = _dre(c, centro_custo="Pecuária Leiteira")
    assert (_linha(so_leite, "RECEITA_VENDAS"), _linha(so_leite, "DEDUCAO_IMPOSTOS")) == (600, 60)
    assert _linha(so_leite, "RECEITA_LIQUIDA") == 540  # = a fatia do centro no motor antigo


def test_desconto_na_nota_de_despesa_continua_rateado_nos_itens(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    _lanc(c, "3.01", 1000, desconto=100)
    _ligar(engine)
    d = _dre(c)
    assert _linha(d, "CUSTO_VARIAVEL") == 900 and _linha(d, "DEDUCAO_IMPOSTOS") == 0


def test_entrega_em_litros_nao_converte(api):
    c, engine, _ = api
    _ok(c.post("/financeiro/plano-contas", json={"codigo": "3.01", "nome": "Ração", "ativa": True, "rmca_custo_alimentacao": True}))
    _lanc(c, "3.01", 5000)
    _ok(c.post("/producao/entrega-leite", json={"competencia": "2031-03", "quantidade_litros": 10000, "unidade": "L"}))
    q = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}
    antes = _ok(c.get("/financeiro/custo-litro-leite", params=q))
    _ligar(engine)
    depois = _ok(c.get("/financeiro/custo-litro-leite", params=q))
    assert antes["litros"] == depois["litros"] == 10000
    assert depois["custo_por_litro"] == 0.5 and depois["litros_convertidos_de_kg"] is False
    assert depois["unidade_origem"] == "L" and depois["avisos"] == []
    assert "regras_v2" not in antes


def test_baixa_em_lote_detalhada_aceita_abatimento_e_valida_antes(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    a = _lanc(c, "3.01", 1000, data_vencimento="2031-04-10")["ids"][0]
    b = _lanc(c, "3.01", 500, data_vencimento="2031-04-10")["ids"][0]
    item = {"data_pagamento": "2031-04-10", "forma_pagamento": "pix"}
    r = c.put("/financeiro/lancamentos/baixa-lote-detalhada", json={"itens": [
        {**item, "lancamento_id": a, "valor_pago": 900, "natureza_diferenca": "abatimento"},
        {**item, "lancamento_id": b, "valor_pago": 520, "natureza_diferenca": "abatimento"},  # acréscimo: inválido
    ]})
    assert r.status_code == 400
    with Session(engine) as s:
        assert s.get(ContaGerencial, a).data_pagamento is None  # nada gravado
    _ok(c.put("/financeiro/lancamentos/baixa-lote-detalhada", json={"itens": [
        {**item, "lancamento_id": a, "valor_pago": 900, "natureza_diferenca": "abatimento"},
        {**item, "lancamento_id": b, "valor_pago": 520},
    ]}))
    with Session(engine) as s:
        assert s.get(ContaGerencial, a).diferenca_tipo == "abatimento"
        assert s.get(ContaGerencial, b).diferenca_tipo is None
    _ligar(engine)
    d = _dre(c, "2031-04-01", "2031-04-30", regime="caixa")
    # 900 (abatido) + 500 contratado; Outras = −20 de juros do b.
    assert _linha(d, "CUSTO_VARIAVEL") == 1400 and _linha(d, "OUTRAS_REC_DESP") == -20
    assert _linha(_dre(c), "CUSTO_VARIAVEL") == 1400


def test_estorno_limpa_o_tipo_da_diferenca(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    conta_id = _lanc(c, "3.01", 1000, data_vencimento="2031-04-10")["ids"][0]
    assert _pagar(c, conta_id, 800, natureza_diferenca="abatimento")["diferenca_tipo"] == "abatimento"
    _ok(c.post(f"/financeiro/lancamentos/{conta_id}/estornar", json={}))
    with Session(engine) as s:
        conta = s.get(ContaGerencial, conta_id)
        assert (conta.desconto_acrescimo, conta.diferenca_tipo) == (None, None)
    _pagar(c, conta_id, 800)
    with Session(engine) as s:
        assert s.get(ContaGerencial, conta_id).diferenca_tipo is None


def test_juros_de_nota_fora_da_dre_vao_para_outras_mas_aporte_nao(api):
    """Juros pagos junto com o principal do financiamento são despesa
    financeira (Outras); a diferença num aporte de sócio fica fora com ele."""
    c, engine, _ = api
    _plano(c, "9.1", "Principal do financiamento", "NAO_ENTRA_NA_DRE")
    _plano(c, "9.2", "Aporte de sócio", "NAO_ENTRA_NA_DRE")
    _ok(c.put("/financeiro/plano-contas/9.2/natureza-fin", json={"natureza_fin": "CAPITAL"}))
    principal = _lanc(c, "9.1", 5000, data_vencimento="2031-04-10")["ids"][0]
    aporte = _lanc(c, "9.2", 2000, tipo="receita", data_vencimento="2031-04-10")["ids"][0]
    _pagar(c, principal, 5080)
    _pagar(c, aporte, 2100)
    _ligar(engine)
    d = _dre(c, "2031-04-01", "2031-04-30", regime="caixa")
    assert _linha(d, "OUTRAS_REC_DESP") == -80
    assert d["fora_da_dre"]["por_natureza"] == {"CAPITAL": 2100.0, "NAO_INFORMADA": 5000.0}


def test_isolamento_entre_fazendas_juros_descontos(api):
    c, engine, estado = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    conta_f1 = _lanc(c, "3.01", 1000, data_vencimento="2031-04-10")["ids"][0]
    _pagar(c, conta_f1, 1100)
    _ligar(engine, 1)
    _ligar(engine, 2)
    estado["fazenda_id"] = 2
    # A fazenda 2 (também com a flag) não enxerga o juro da 1 nem paga a nota dela.
    d2 = _dre(c, "2031-04-01", "2031-04-30", regime="caixa")
    assert _linha(d2, "OUTRAS_REC_DESP") == 0 and d2["diferencas_baixa"] == []
    assert c.put(f"/financeiro/lancamentos/{conta_f1}/pagar", json={
        "data_pagamento": "2031-04-20", "valor_pago": 900, "forma_pagamento": "pix",
        "natureza_diferenca": "abatimento"}).status_code == 404
    rm = _ok(c.get("/financeiro/rmca", params={"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}))
    assert rm["gerencial"]["custo_alimentacao"] == 0
    estado["fazenda_id"] = 1
    d1 = _dre(c, "2031-04-01", "2031-04-30", regime="caixa")
    assert _linha(d1, "OUTRAS_REC_DESP") == -100
    with Session(engine) as s:
        assert s.get(ContaGerencial, conta_f1).diferenca_tipo is None


# =============================================================================
# Migração
# =============================================================================
def test_migracao_diferenca_tipo_sobe_desce_e_e_idempotente(tmp_path):
    db = tmp_path / "mig.db"
    _alembic(db, "upgrade", REVISAO_ANTERIOR)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO conta_gerencial (numero_lancamento, tipo, valor_total, desconto_acrescimo, origem, atualizado_em) "
                 "VALUES ('LC-1', 'despesa', 123.0, -3.0, 'manual', '2026-01-01')")
    conn.commit()
    conn.close()
    _alembic(db, "upgrade", REVISAO)
    info = _colunas(db, "conta_gerencial")["diferenca_tipo"]
    assert info["notnull"] == 0 and info["default"] is None
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT valor_total, desconto_acrescimo, diferenca_tipo FROM conta_gerencial").fetchone() == (123.0, -3.0, None)
    conn.close()
    _alembic(db, "downgrade", REVISAO_ANTERIOR)
    assert "diferenca_tipo" not in _colunas(db, "conta_gerencial")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT valor_total, desconto_acrescimo FROM conta_gerencial").fetchone() == (123.0, -3.0)
    conn.close()
    # Deploy: create_all do boot já criou a coluna antes do upgrade.
    db2 = tmp_path / "boot.db"
    _alembic(db2, "upgrade", REVISAO_ANTERIOR)
    conn = sqlite3.connect(db2)
    conn.execute("ALTER TABLE conta_gerencial ADD COLUMN diferenca_tipo VARCHAR")
    conn.commit()
    conn.close()
    _alembic(db2, "upgrade", "head")
    # A cabeça avança com os PRs seguintes (PR 2/3: a7c4e2d9f1b3); o que importa
    # aqui é o upgrade ter passado por esta revisão sem abortar.
    assert "(head)" in _alembic(db2, "current")
