"""
Fase A — PR 0 (rede de segurança) e PR 1 (natureza do lançamento): unidades e
integração fora do cenário grande da auditoria.

  - hoje_local (America/Sao_Paulo);
  - rules/natureza.py (normalização, ordem de resolução, inferência por nome);
  - motor da DRE com e sem regras v2;
  - flag por fazenda (`regras_v2_ativas`, PUT /parametros, isolamento);
  - natureza no lançamento/item/plano (API), manutenção ligada ao bem,
    ganho/perda na baixa, compra de matriz, custo por safra;
  - backfill (dry-run, aplicar, idempotência, reverter, conflito, isolamento);
  - script de impacto (CSV, banco intocado);
  - migração Alembic (upgrade/downgrade em SQLite descartável).
"""
from __future__ import annotations

import csv
import hashlib
import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.models  # noqa: F401
from fazenda.models import (
    ContaGerencial, LancamentoItem, MigracaoLogFinanceiro, ParametroFazenda, Patrimonio, PlanoContaGerencial, Safra,
)
from fazenda.rules import natureza as nat
from fazenda.rules.datas import hoje_local
from fazenda.rules.dre import montar_cascata_dre
from fazenda.rules.parametros import regras_v2_ativas
from tests.cenario_auditoria_financeiro import preparar_fazendas

BACKEND = Path(__file__).resolve().parent.parent


# =============================================================================
# hoje_local
# =============================================================================
def test_hoje_local_sao_paulo():
    """23h30 em Brasília (02h30 UTC do dia seguinte) continua sendo hoje."""
    assert hoje_local(datetime(2026, 10, 9, 2, 30, tzinfo=timezone.utc)) == date(2026, 10, 8)
    assert hoje_local(datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)) == date(2026, 10, 9)
    # Sem fuso = relógio do servidor (UTC).
    assert hoje_local(datetime(2026, 10, 9, 1, 0)) == date(2026, 10, 8)


# =============================================================================
# rules/natureza.py
# =============================================================================
def test_normalizar_natureza():
    assert nat.normalizar_natureza(" investimento ") == "INVESTIMENTO"
    assert nat.normalizar_natureza("Transferência") == "TRANSFERENCIA"
    assert nat.normalizar_natureza("") is None and nat.normalizar_natureza(None) is None
    with pytest.raises(ValueError):
        nat.normalizar_natureza("despesa")


def test_resolver_natureza_ordem():
    mapa = {"3.10": "INVESTIMENTO"}
    # 1. item > 2. nota > 4. plano (herança) > 5. NAO_ENTRA > 6. operacional
    assert nat.resolver_natureza(natureza_item="OBRIGACAO", natureza_conta="CAPITAL",
                                 codigo_conta="3.10.02", mapa_natureza_plano=mapa) == "OBRIGACAO"
    assert nat.resolver_natureza(natureza_conta="CAPITAL", codigo_conta="3.10.02", mapa_natureza_plano=mapa) == "CAPITAL"
    assert nat.resolver_natureza(codigo_conta="3.10.02", mapa_natureza_plano=mapa) == "INVESTIMENTO"
    assert nat.resolver_natureza(codigo_conta="3.01", linha_dre="NAO_ENTRA_NA_DRE") == "NAO_INFORMADA"
    assert nat.resolver_natureza(codigo_conta="3.01", linha_dre="CUSTO_VARIAVEL") == "OPERACIONAL"
    # 3. receita de bem baixado com venda é desinvestimento; despesa ligada ao
    #    bem (manutenção) NÃO vira investimento em leitura.
    assert nat.resolver_natureza(tipo="receita", patrimonio_id=7, patrimonios_vendidos={7}) == "INVESTIMENTO"
    assert nat.resolver_natureza(tipo="despesa", patrimonio_id=7, patrimonios_vendidos={7}) == "OPERACIONAL"


@pytest.mark.parametrize("nome, esperado", [
    ("Principal do financiamento", "FINANCIAMENTO"),
    ("Amortização de empréstimo", "FINANCIAMENTO"),
    ("Juros de financiamento", None),
    ("IOF sobre empréstimo", None),
    ("Aporte de sócio", "CAPITAL"),
    ("Transferência entre contas", "TRANSFERENCIA"),
    ("Compra de matrizes", "INVESTIMENTO"),
    ("Máquinas e equipamentos", "INVESTIMENTO"),
    ("Aquisição de máquinas", "INVESTIMENTO"),
    ("Manutenção de máquinas e equipamentos", None),
    ("Ração concentrado", None),
])
def test_inferir_natureza_por_nome(nome, esperado):
    assert nat.inferir_natureza_por_nome(nome)[0] == esperado


# =============================================================================
# Motor da DRE
# =============================================================================
_MAPA = {"2.01": "RECEITA_VENDAS", "3.01": "CUSTO_VARIAVEL", "3.10": "DESPESAS_OPERACIONAIS", "9": "NAO_ENTRA_NA_DRE"}
_REGISTROS = [
    {"codigo_conta": "2.01", "tipo": "receita", "valor": 1000.0, "descricao": "Leite", "natureza": "OPERACIONAL"},
    {"codigo_conta": "3.01", "tipo": "despesa", "valor": 300.0, "descricao": "Ração", "natureza": "OPERACIONAL"},
    {"codigo_conta": "3.10", "tipo": "despesa", "valor": 5000.0, "descricao": "Trator", "natureza": "INVESTIMENTO"},
    {"codigo_conta": "9", "tipo": "despesa", "valor": 200.0, "descricao": "Principal", "natureza": "NAO_INFORMADA"},
]


def test_motor_sem_regras_v2_ignora_natureza_e_baixas():
    sem_nat = [{k: v for k, v in r.items() if k != "natureza"} for r in _REGISTROS]
    referencia = montar_cascata_dre(sem_nat, _MAPA, 50.0)
    assert montar_cascata_dre(_REGISTROS, _MAPA, 50.0) == referencia
    assert montar_cascata_dre(_REGISTROS, _MAPA, 50.0, regras_v2=False, resultado_baixas=-999.0) == referencia
    assert "por_natureza" not in referencia["fora_da_dre"]


def test_motor_com_regras_v2_agrupa_e_lanca_baixa_em_outras():
    r = montar_cascata_dre(_REGISTROS, _MAPA, 50.0, regras_v2=True, resultado_baixas=-10000.0)
    linhas = {x["chave"]: x for x in r["linhas"]}
    assert linhas["DESPESAS_OPERACIONAIS"]["valor"] == 0
    assert linhas["DEPRECIACAO_AMORT_EXAUSTAO"]["valor"] == 50
    assert linhas["OUTRAS_REC_DESP"]["valor"] == -10000
    assert linhas["OUTRAS_REC_DESP"]["contas"][0]["codigo"] == "(resultado de baixa de patrimônio)"
    assert linhas["RESULTADO_LIQUIDO"]["valor"] == 1000 - 300 - 50 - 10000
    assert r["fora_da_dre"]["por_natureza"] == {"INVESTIMENTO": 5000.0, "NAO_INFORMADA": 200.0}
    assert r["fora_da_dre"]["total"] == 5200
    ganho = montar_cascata_dre([], {}, 0.0, regras_v2=True, resultado_baixas=300.0)
    assert {x["chave"]: x["valor"] for x in ganho["linhas"]}["OUTRAS_REC_DESP"] == 300


# =============================================================================
# Cliente de API com duas fazendas
# =============================================================================
class _Usuario:
    def __init__(self, papel="admin"):
        self.id, self.papel, self.ativo, self.username = 1, papel, True, f"teste-{papel}"
        # Operador COM os módulos: a recusa tem de vir do exigir_admin da rota.
        self.permissoes = "financeiro,parametros,rebanho"
        self.pessoa_id = None


@contextmanager
def _api(engine, estado):
    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    def _sessao():
        with Session(engine) as s:
            yield s

    main.app.dependency_overrides[database.get_session] = _sessao
    main.app.dependency_overrides[get_current_user] = lambda: _Usuario(estado.get("papel", "admin"))
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: estado["fazenda_id"]
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        main.app.dependency_overrides.clear()


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    preparar_fazendas(engine)
    estado = {"fazenda_id": 1}
    with _api(engine, estado) as c:
        yield c, engine, estado


def _ok(r, status=(200, 201)):
    assert r.status_code in status, (r.status_code, r.text[:400])
    return r.json()


def _plano(c, codigo, nome, linha=None):
    _ok(c.post("/financeiro/plano-contas", json={"codigo": codigo, "nome": nome, "ativa": True}))
    if linha:
        _ok(c.put(f"/financeiro/plano-contas/{codigo}/linha-dre", json={"linha_dre": linha}))


def _lanc(c, codigo, valor, data="2031-03-10", tipo="despesa", **extra):
    corpo = {
        "tipo": tipo, "centro_custo": "Pecuária Leiteira", "fornecedor_cliente": "Teste",
        "itens": [{"produto": extra.pop("produto", "Item"), "codigo_conta_gerencial": codigo, "valor_total": valor,
                   "tipo_item": "servico", **extra.pop("item", {})}],
        "data_emissao": data, "data_competencia": data, **extra,
    }
    return _ok(c.post("/financeiro/lancamentos", json=corpo))


def _ligar(engine, fazenda_id=1, valor="true"):
    with Session(engine) as s:
        s.add(ParametroFazenda(chave="financeiro_regras_v2", fazenda_id=fazenda_id, grupo="financeiro",
                               label="v2", valor=valor, tipo="bool"))
        s.commit()


def _dre(c, ini="2031-03-01", fim="2031-03-31", **q):
    return _ok(c.get("/financeiro/dre", params={"data_inicio": ini, "data_fim": fim, **q}))


def _linha(d, chave):
    return next(x["valor"] for x in d["cascata"] if x["chave"] == chave)


# =============================================================================
# Flag por fazenda
# =============================================================================
def test_flag_padrao_desligada_global_ignorada_e_por_fazenda(api):
    _c, engine, _ = api
    with Session(engine) as s:
        assert regras_v2_ativas(s, 1) is False
        assert regras_v2_ativas(s, None) is False
        # Linha GLOBAL ligada por engano (Painel CowData) não liga ninguém.
        s.add(ParametroFazenda(chave="financeiro_regras_v2", fazenda_id=None, grupo="financeiro",
                               label="v2", valor="true", tipo="bool"))
        s.commit()
        assert regras_v2_ativas(s, 1) is False
    _ligar(engine, 2)
    with Session(engine) as s:
        assert regras_v2_ativas(s, 2) is True and regras_v2_ativas(s, 1) is False


def test_flag_liga_pela_tela_de_parametros_so_admin_e_so_na_fazenda(api):
    c, engine, estado = api
    from fazenda.rules.parametros import seed_parametros
    with Session(engine) as s:
        seed_parametros(s)
    grupos = _ok(c.get("/parametros/"))["grupos"]
    item = next(i for i in grupos["financeiro"]["itens"] if i["chave"] == "financeiro_regras_v2")
    assert item["valor"] is False and item["tipo"] == "bool"
    estado["papel"] = "operador"
    assert c.put("/parametros/financeiro_regras_v2", json={"valor": True}).status_code == 403
    estado["papel"] = "admin"
    _ok(c.put("/parametros/financeiro_regras_v2", json={"valor": True}))
    assert _ok(c.get("/financeiro/regras-v2"))["ativa"] is True
    estado["fazenda_id"] = 2
    assert _ok(c.get("/financeiro/regras-v2"))["ativa"] is False
    with Session(engine) as s:
        global_ = s.exec(select(ParametroFazenda).where(
            ParametroFazenda.chave == "financeiro_regras_v2", ParametroFazenda.fazenda_id.is_(None))).one()
        assert global_.valor == "false"


# =============================================================================
# Natureza no lançamento, no item e no plano
# =============================================================================
def test_compra_com_criar_patrimonio_nasce_investimento_e_natureza_invalida_400(api):
    c, engine, _ = api
    _plano(c, "3.10", "Máquinas", "DESPESAS_OPERACIONAIS")
    r = _lanc(c, "3.10", 50000, criar_patrimonio={"nome": "Trator", "data_imobilizacao": "2031-03-10",
                                                  "valor_total": 50000, "depreciavel": True,
                                                  "metodo_depreciacao": "linear", "vida_util_anos": 10})
    assert r["natureza_fin"] == "INVESTIMENTO"
    with Session(engine) as s:
        assert s.get(ContaGerencial, r["ids"][0]).natureza_fin == "INVESTIMENTO"
    corpo = {"tipo": "despesa", "itens": [{"produto": "x", "valor_total": 10}], "data_emissao": "2031-03-01",
             "natureza_fin": "DESPESA"}
    assert c.post("/financeiro/lancamentos", json=corpo).status_code == 400


def test_editar_natureza_da_nota_e_do_item(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    _plano(c, "3.04", "Benfeitorias", "DESPESAS_OPERACIONAIS")
    corpo = {"tipo": "despesa", "centro_custo": "Pecuária Leiteira", "data_emissao": "2031-03-05",
             "itens": [{"produto": "Ração", "codigo_conta_gerencial": "3.01", "valor_total": 1000},
                       {"produto": "Galpão", "codigo_conta_gerencial": "3.04", "valor_total": 9000}]}
    r = _ok(c.post("/financeiro/lancamentos", json=corpo))
    numero = r["numero_lancamento"]
    _ligar(engine)
    with Session(engine) as s:
        galpao = s.exec(select(LancamentoItem).where(LancamentoItem.produto == "Galpão")).one()
    resp = _ok(c.put(f"/financeiro/lancamentos/{numero}/natureza", json={"natureza_fin": "INVESTIMENTO", "item_id": galpao.id}))
    assert resp["aviso"] is None  # aviso só para a nota inteira
    d = _dre(c)
    assert _linha(d, "CUSTO_VARIAVEL") == 1000 and _linha(d, "DESPESAS_OPERACIONAIS") == 0
    assert d["fora_da_dre"]["por_natureza"] == {"INVESTIMENTO": 9000.0}
    # Investimento sem bem no Patrimônio: pendência "não vai depreciar".
    assert d["pendencias_natureza"][0]["numero_lancamento"] == numero
    lanc = next(x for x in _ok(c.get("/financeiro/lancamentos"))["lancamentos"] if x["numero_lancamento"] == numero)
    assert lanc["natureza_resolvida"] == "MISTA"
    # Nota inteira: aviso de bem ausente.
    resp = _ok(c.put(f"/financeiro/lancamentos/{numero}/natureza", json={"natureza_fin": "investimento"}))
    assert resp["natureza_fin"] == "INVESTIMENTO" and "não vai depreciar" in resp["aviso"]
    assert c.put(f"/financeiro/lancamentos/{numero}/natureza", json={"natureza_fin": "XYZ"}).status_code == 400
    # Volta a automática.
    _ok(c.put(f"/financeiro/lancamentos/{numero}/natureza", json={"natureza_fin": None, "item_id": galpao.id}))
    _ok(c.put(f"/financeiro/lancamentos/{numero}/natureza", json={"natureza_fin": None}))
    assert _linha(_dre(c), "DESPESAS_OPERACIONAIS") == 9000


def test_natureza_do_plano_admin_e_por_fazenda(api):
    c, engine, estado = api
    _plano(c, "9.1", "Principal do empréstimo", "NAO_ENTRA_NA_DRE")
    estado["papel"] = "operador"
    assert c.put("/financeiro/plano-contas/9.1/natureza-fin", json={"natureza_fin": "FINANCIAMENTO"}).status_code == 403
    estado["papel"] = "admin"
    assert c.put("/financeiro/plano-contas/9.1/natureza-fin", json={"natureza_fin": "nada"}).status_code == 400
    _ok(c.put("/financeiro/plano-contas/9.1/natureza-fin", json={"natureza_fin": "FINANCIAMENTO"}))
    assert next(p for p in _ok(c.get("/financeiro/plano-contas")) if p["codigo"] == "9.1")["natureza_fin"] == "FINANCIAMENTO"
    estado["fazenda_id"] = 2
    assert c.put("/financeiro/plano-contas/9.1/natureza-fin", json={"natureza_fin": "CAPITAL"}).status_code == 404
    # O PUT genérico do plano não apaga a natureza (campo não faz parte dele).
    estado["fazenda_id"] = 1
    with Session(engine) as s:
        conta = s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "9.1")).one()
    _ok(c.put(f"/financeiro/plano-contas/{conta.id}", json={"codigo": "9.1", "nome": "Principal", "ativa": True}))
    with Session(engine) as s:
        assert s.get(PlanoContaGerencial, conta.id).natureza_fin == "FINANCIAMENTO"


def test_manutencao_ligada_ao_bem_continua_operacional(api):
    c, engine, _ = api
    _plano(c, "3.10", "Máquinas", "DESPESAS_OPERACIONAIS")
    compra = _lanc(c, "3.10", 120000, data="2031-03-01",
                   criar_patrimonio={"nome": "Trator", "data_imobilizacao": "2031-03-01", "valor_total": 120000,
                                     "depreciavel": True, "metodo_depreciacao": "linear", "vida_util_anos": 10})
    with Session(engine) as s:
        bem_id = s.get(ContaGerencial, compra["ids"][0]).patrimonio_id
    manut = _lanc(c, "3.10", 3000, data="2031-03-20", produto="Revisão do trator")
    _ok(c.put(f"/financeiro/lancamentos/{manut['numero_lancamento']}/patrimonio", json={"patrimonio_id": bem_id}))
    _ligar(engine)
    d = _dre(c)
    assert _linha(d, "DESPESAS_OPERACIONAIS") == 3000
    assert d["fora_da_dre"]["por_natureza"] == {"INVESTIMENTO": 120000.0}
    from fazenda.rules.backfill_natureza import planejar
    with Session(engine) as s:
        plano = planejar(s, 1)
    assert plano.mudancas == []
    assert [r["numero_lancamento"] for r in plano.revisao] == [manut["numero_lancamento"]]


def test_baixa_com_venda_vai_para_outras_e_a_receita_sai_das_vendas(api):
    c, engine, _ = api
    _plano(c, "2.01", "Venda de leite", "RECEITA_VENDAS")
    _plano(c, "2.09", "Outras receitas", "RECEITA_VENDAS")
    with Session(engine) as s:
        bem = Patrimonio(nome="Trator", fazenda_id=1, data_imobilizacao=date(2031, 3, 1), valor_total=120000,
                         depreciavel=True, metodo_depreciacao="linear", vida_util_anos=10, valor_residual=0)
        s.add(bem)
        s.commit()
        bem_id = bem.id
    # 10 meses de 1.000: valor contábil 110.000 em 01/01/2032.
    _ok(c.post(f"/financeiro/patrimonio/{bem_id}/baixa", json={
        "data_baixa": "2032-01-01", "motivo": "VENDA", "valor_recebido": 100000}))
    venda = _lanc(c, "2.09", 100000, data="2032-01-01", tipo="receita", produto="Venda do trator")
    _ok(c.put(f"/financeiro/lancamentos/{venda['numero_lancamento']}/patrimonio", json={"patrimonio_id": bem_id}))
    _lanc(c, "2.01", 5000, data="2032-01-10", tipo="receita", produto="Leite")
    antes = _dre(c, "2032-01-01", "2032-01-31")
    assert _linha(antes, "RECEITA_VENDAS") == 105000 and _linha(antes, "OUTRAS_REC_DESP") == 0
    _ligar(engine)
    d = _dre(c, "2032-01-01", "2032-01-31")
    assert _linha(d, "OUTRAS_REC_DESP") == -10000
    assert _linha(d, "RECEITA_VENDAS") == 5000
    assert d["fora_da_dre"]["por_natureza"] == {"INVESTIMENTO": 100000.0}
    assert d["resultado_baixas_periodo"]["itens"][0]["resultado"] == -10000


def test_compra_de_matriz_nasce_investimento(api):
    c, engine, _ = api
    _plano(c, "3.10.06", "Compra de matrizes", "CUSTO_VARIAVEL")
    _plano(c, "3.10.07", "Compra de bezerros para recria", "CUSTO_VARIAVEL")
    base = {"animais": ["101"], "vendedor": "Haras", "valor": 8000, "tipo_valor": "por_animal",
            "data_compra": "2031-03-05", "centro_custo": "Pecuária Leiteira"}
    r1 = _ok(c.post("/compras-animais/", json={**base, "codigo_conta_gerencial": "3.10.06"}))
    r2 = _ok(c.post("/compras-animais/", json={**base, "animais": ["102"], "codigo_conta_gerencial": "3.10.07"}))
    r3 = _ok(c.post("/compras-animais/", json={**base, "animais": ["103"], "codigo_conta_gerencial": "3.10.07",
                                                "natureza_fin": "INVESTIMENTO"}))
    assert (r1["natureza_fin"], r2["natureza_fin"], r3["natureza_fin"]) == ("INVESTIMENTO", None, "INVESTIMENTO")
    _ligar(engine)
    assert _linha(_dre(c), "CUSTO_VARIAVEL") == 8000


def test_custo_safra_com_regras_v2(api):
    c, engine, _ = api
    _plano(c, "3.20", "Sementes", "CUSTO_VARIAVEL")
    _plano(c, "3.21", "Aquisição de máquinas", "DESPESAS_OPERACIONAIS")
    with Session(engine) as s:
        s.add(Safra(nome="Milho 31", fazenda_id=1, centro_custo="Agricultura", data_inicio=date(2031, 1, 1),
                    data_fim=date(2031, 6, 30), hectares=10, toneladas_produzidas=100))
        s.commit()
        safra_id = s.exec(select(Safra.id)).one()
    _lanc(c, "3.20", 2000, centro_custo="Agricultura")
    r = _lanc(c, "3.21", 30000, centro_custo="Agricultura")
    _ok(c.put(f"/financeiro/lancamentos/{r['numero_lancamento']}/natureza", json={"natureza_fin": "INVESTIMENTO"}))
    antes = _ok(c.get("/financeiro/custo-safra", params={"safra_id": safra_id}))
    assert antes["despesas_total"] == 32000 and "cot" not in antes
    _ligar(engine)
    depois = _ok(c.get("/financeiro/custo-safra", params={"safra_id": safra_id}))
    assert depois["despesas_total"] == 2000 and depois["custo_por_hectare"] == 200
    assert depois["fora_por_natureza"] == {"INVESTIMENTO": 30000.0}
    assert depois["por_categoria"] == [{"codigo": "3", "descricao": "Item", "valor": 2000.0}]


# =============================================================================
# Backfill: dry-run, aplicar, idempotência, reverter, conflito, isolamento
# =============================================================================
def _hash_tabela(engine, tabela):
    with engine.connect() as conn:
        linhas = conn.exec_driver_sql(f"SELECT * FROM {tabela} ORDER BY id").fetchall()
    return hashlib.sha256(repr(linhas).encode()).hexdigest()


def _historico_para_backfill(c, engine):
    """Notas 'antigas' (sem natureza): a compra ligada ao bem DEPOIS, a
    principal/aporte em conta NAO_ENTRA_NA_DRE e uma compra de matriz."""
    _plano(c, "3.10", "Máquinas", "DESPESAS_OPERACIONAIS")
    _plano(c, "3.10.06", "Compra de matrizes", "CUSTO_VARIAVEL")
    _plano(c, "8.4", "Principal do financiamento", "NAO_ENTRA_NA_DRE")
    _plano(c, "8.5", "Aporte de sócio", "NAO_ENTRA_NA_DRE")
    _plano(c, "8.6", "Benfeitorias e instalações", "DESPESAS_OPERACIONAIS")
    compra = _lanc(c, "3.10", 98000, data="2031-03-03", produto="Trator usado")
    bem = _ok(c.post("/financeiro/patrimonio", json={"nome": "Trator", "data_imobilizacao": "2031-03-01",
                                                     "valor_total": 100000, "depreciavel": True,
                                                     "metodo_depreciacao": "linear", "vida_util_anos": 10}))
    _ok(c.put(f"/financeiro/lancamentos/{compra['numero_lancamento']}/patrimonio", json={"patrimonio_id": bem["id"]}))
    _lanc(c, "8.4", 5000, data="2031-03-25")
    _lanc(c, "8.5", 20000, data="2031-03-02", tipo="receita")
    _ok(c.post("/compras-animais/", json={"animais": ["7"], "vendedor": "X", "valor": 9000, "tipo_valor": "total",
                                          "data_compra": "2031-03-07", "codigo_conta_gerencial": "3.10.06"}))
    with Session(engine) as s:  # simula o legado: compra de animal de antes da Fase A
        for conta in s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Compra de animal")).all():
            conta.natureza_fin = None
            s.add(conta)
        s.commit()
    return compra


def test_backfill_dry_run_aplicar_idempotente_e_reverter(api):
    c, engine, _ = api
    compra = _historico_para_backfill(c, engine)
    from scripts.backfill_natureza_fin import executar

    hash_inicial = _hash_tabela(engine, "conta_gerencial"), _hash_tabela(engine, "plano_conta_gerencial")
    saida: list[str] = []
    with Session(engine) as s:
        r = executar(s, 1, aplicar=False, saida=saida.append)
    assert len(r["plano"].mudancas) == 4  # trator, matriz, 8.4, 8.5
    # Só sugestão (contas que estão DENTRO da DRE): nada disso é aplicado.
    assert {s_["codigo"] for s_ in r["plano"].sugestoes} == {"3.10", "3.10.06", "8.6"}
    assert (_hash_tabela(engine, "conta_gerencial"), _hash_tabela(engine, "plano_conta_gerencial")) == hash_inicial
    with Session(engine) as s:
        assert s.exec(select(MigracaoLogFinanceiro)).all() == []

    with Session(engine) as s:
        r = executar(s, 1, aplicar=True, saida=saida.append)
    lote = r["lote"]
    assert r["aplicadas"] == 4
    with Session(engine) as s:
        trator = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == compra["numero_lancamento"])).one()
        assert trator.natureza_fin == "INVESTIMENTO" and trator.valor_total == 98000 and trator.valor_pago is None
        logs = s.exec(select(MigracaoLogFinanceiro).where(MigracaoLogFinanceiro.lote == lote)).all()
        assert len(logs) == 4 and all(lg.fazenda_id == 1 and lg.valor_antes == "null" for lg in logs)
        assert {p.codigo: p.natureza_fin for p in s.exec(select(PlanoContaGerencial)).all()
                if p.natureza_fin} == {"8.4": "FINANCIAMENTO", "8.5": "CAPITAL"}
    # Com a flag: cenário depois do backfill.
    _ligar(engine)
    d = _dre(c)
    assert _linha(d, "DESPESAS_OPERACIONAIS") == 0 and _linha(d, "CUSTO_VARIAVEL") == 0
    assert d["fora_da_dre"]["por_natureza"] == {"INVESTIMENTO": 107000.0, "FINANCIAMENTO": 5000.0, "CAPITAL": 20000.0}

    # Idempotente: rodar de novo não acha nada.
    with Session(engine) as s:
        assert executar(s, 1, aplicar=True, saida=saida.append)["aplicadas"] == 0

    # Reverter de OUTRA fazenda não toca em nada.
    with Session(engine) as s:
        r2 = executar(s, 2, aplicar=True, reverter=lote, saida=saida.append)
        assert r2["reversao"].revertidas == 0
    # Dry-run da reversão só conta.
    with Session(engine) as s:
        assert executar(s, 1, aplicar=False, reverter=lote, saida=saida.append)["reversao"].revertidas == 4
    with Session(engine) as s:
        assert s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == compra["numero_lancamento"])).one().natureza_fin == "INVESTIMENTO"
    with Session(engine) as s:
        assert executar(s, 1, aplicar=True, reverter=lote, saida=saida.append)["reversao"].revertidas == 4
    assert (_hash_tabela(engine, "conta_gerencial"), _hash_tabela(engine, "plano_conta_gerencial")) == hash_inicial
    with Session(engine) as s:
        assert all(lg.revertido_em is not None for lg in s.exec(select(MigracaoLogFinanceiro)).all())


def test_reverter_nao_sobrescreve_mudanca_manual_posterior(api):
    c, engine, _ = api
    compra = _historico_para_backfill(c, engine)
    from scripts.backfill_natureza_fin import executar

    with Session(engine) as s:
        lote = executar(s, 1, aplicar=True, saida=lambda *_: None)["lote"]
    # Depois do backfill, o usuário decide que aquilo era operacional.
    _ok(c.put(f"/financeiro/lancamentos/{compra['numero_lancamento']}/natureza", json={"natureza_fin": "OPERACIONAL"}))
    with Session(engine) as s:
        rev = executar(s, 1, aplicar=True, reverter=lote, saida=lambda *_: None)["reversao"]
    assert rev.revertidas == 3 and len(rev.conflitos) == 1
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == compra["numero_lancamento"])).one()
        assert conta.natureza_fin == "OPERACIONAL"


def test_backfill_so_enxerga_a_propria_fazenda(api):
    c, engine, estado = api
    _historico_para_backfill(c, engine)
    estado["fazenda_id"] = 2
    _plano(c, "8.4", "Principal do financiamento", "NAO_ENTRA_NA_DRE")
    from fazenda.rules.backfill_natureza import aplicar, planejar
    from fazenda.rules.migracao_log import registrar_mudanca
    with Session(engine) as s:
        plano2 = planejar(s, 2)
        assert [m["codigo"] for m in plano2.mudancas] == ["8.4"]
        ids_f1 = {cg.id for cg in s.exec(select(ContaGerencial).where(ContaGerencial.fazenda_id == 1)).all()}
        assert not ({m["id"] for m in plano2.mudancas if m["tabela"] == "conta_gerencial"} & ids_f1)
        # Mesmo forçando um id da fazenda 1 num plano da 2, nada é gravado.
        plano2.mudancas.append({"tabela": "conta_gerencial", "id": min(ids_f1), "campo": "natureza_fin",
                                "para": "CAPITAL", "motivo": "x"})
        assert aplicar(s, plano2, "lote-x") == 1
        s.commit()
        assert s.get(ContaGerencial, min(ids_f1)).natureza_fin != "CAPITAL"
        with pytest.raises(ValueError):
            registrar_mudanca(s, fazenda_id=2, lote="l", migracao="m", tabela="conta_gerencial",
                              registro=s.get(ContaGerencial, min(ids_f1)), campo="natureza_fin", valor_depois="CAPITAL")
        with pytest.raises(ValueError):
            registrar_mudanca(s, fazenda_id=1, lote="l", migracao="m", tabela="conta_gerencial",
                              registro=s.get(ContaGerencial, min(ids_f1)), campo="valor_total", valor_depois=1)


# =============================================================================
# Script de impacto (somente leitura)
# =============================================================================
def test_script_de_impacto_gera_csv_e_nao_grava_nada(tmp_path):
    db = tmp_path / "dump.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    preparar_fazendas(engine)
    with _api(engine, {"fazenda_id": 1}) as c:
        _historico_para_backfill(c, engine)
    engine.dispose()
    antes = hashlib.sha256(db.read_bytes()).hexdigest()

    from scripts.impacto_relatorios_v2 import executar
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    saida, saida_lanc = tmp_path / "impacto.csv", tmp_path / "lancamentos.csv"
    resultado = executar(engine, 1, "2031-03", "2031-04", str(saida), str(saida_lanc))
    engine.dispose()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes

    linhas = list(csv.DictReader(saida.open(encoding="utf-8-sig"), delimiter=";"))
    por = {(r["secao"], r["periodo"], r["metrica"]): r for r in linhas}
    desp = por[("dre_competencia", "2031-03", "dre.DESPESAS_OPERACIONAIS")]
    # Sem backfill (dados como estão): o trator não tem natureza → nada muda.
    assert float(desp["antes"]) == 98000 and float(desp["depois"]) == 98000
    # Com o backfill simulado, o trator sai.
    assert float(desp["depois_com_backfill"]) == 0 and float(desp["delta_com_backfill"]) == -98000
    custo = por[("custos", "2031-03", "custo_hectare.numerador")]
    assert float(custo["antes"]) == 98000 + 5000 + 9000
    assert float(custo["depois"]) == 98000 + 9000
    assert float(custo["depois_com_backfill"]) == 0
    lanc = list(csv.DictReader(saida_lanc.open(encoding="utf-8-sig"), delimiter=";"))
    motivos = {(r["regime"], r["destino_depois"]): r["motivo"] for r in lanc if r["periodo"] == "2031-03"}
    assert motivos[("competencia", "fora_da_dre.INVESTIMENTO")].startswith("backfill: ")
    assert resultado["plano_backfill"].mudancas


def test_script_de_impacto_recusa_escrita(tmp_path):
    from scripts.impacto_relatorios_v2 import _abrir_somente_leitura
    db = tmp_path / "x.db"
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        _abrir_somente_leitura(conn)
        with pytest.raises(Exception):
            conn.exec_driver_sql("INSERT INTO seed_flag (chave, aplicado_em) VALUES ('x', '2026-01-01')")
    engine.dispose()


# =============================================================================
# Migração Alembic (subprocesso, SQLite descartável)
# =============================================================================
REVISAO_ANTERIOR = "d2b6f0a4e813"
REVISAO = "e5a9c3f1b742"


def _alembic(db_path: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)}:\n{r.stdout}\n{r.stderr}"
    return r.stdout


def _colunas(db, tabela):
    conn = sqlite3.connect(db)
    info = {c[1]: {"notnull": c[3], "default": c[4]} for c in conn.execute(f"PRAGMA table_info({tabela})")}
    conn.close()
    return info


def test_migracao_natureza_fin_sobe_desce_e_e_idempotente(tmp_path):
    db = tmp_path / "mig.db"
    _alembic(db, "upgrade", REVISAO_ANTERIOR)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO conta_gerencial (numero_lancamento, tipo, valor_total, origem, atualizado_em) "
                 "VALUES ('LC-1', 'despesa', 123.0, 'manual', '2026-01-01')")
    conn.commit()
    conn.close()

    _alembic(db, "upgrade", "head")
    for tabela, coluna in [("conta_gerencial", "natureza_fin"), ("lancamento_item", "natureza_fin"),
                           ("plano_conta_gerencial", "natureza_fin"), ("patrimonio", "centro_custo")]:
        info = _colunas(db, tabela)[coluna]
        assert info["notnull"] == 0 and info["default"] is None, (tabela, coluna)
    assert "lote" in _colunas(db, "migracao_log_financeiro")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT valor_total, natureza_fin FROM conta_gerencial").fetchone() == (123.0, None)
    conn.close()

    _alembic(db, "downgrade", REVISAO_ANTERIOR)
    assert "natureza_fin" not in _colunas(db, "conta_gerencial")
    assert _colunas(db, "migracao_log_financeiro") == {}
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT valor_total FROM conta_gerencial").fetchone() == (123.0,)
    conn.close()

    # Deploy: create_all do boot já criou colunas/tabela antes do upgrade.
    db2 = tmp_path / "boot.db"
    _alembic(db2, "upgrade", REVISAO_ANTERIOR)
    conn = sqlite3.connect(db2)
    conn.execute("ALTER TABLE conta_gerencial ADD COLUMN natureza_fin VARCHAR")
    conn.commit()
    conn.close()
    _alembic(db2, "upgrade", "head")
    assert "natureza_fin" in _colunas(db2, "lancamento_item")
    # A cabeça avança com os PRs seguintes (PR 7: f3b8d1c6a9e2); o que importa
    # aqui é o upgrade ter passado por esta revisão sem abortar.
    assert "(head)" in _alembic(db2, "current")
