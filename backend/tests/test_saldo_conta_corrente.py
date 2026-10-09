"""
Fase A — PR 6 (saldo de abertura e Caixa Real; erros 6 e 7 da auditoria), fora
do cenário grande (que está em tests/test_relatorios_cenario_auditoria.py, §3b).

  - rules/saldo_conta.py (data de caixa, valor efetivo, abertura, agendado,
    casamento do rótulo livre com a conta);
  - saldo por FK e não por texto; pagamento futuro = agendado (resposta da
    baixa e Caixa Real); `valor_pago` obrigatório com a flag;
  - cartão avulso sai no vencimento do cartão (saldo e DRE de caixa);
  - retirada do caixa do funcionário pelo banco: baixa o saldo, fica fora da
    DRE, estorno devolve, exclusão apaga;
  - Caixa Real e fundo de reserva sem o desconto do vale de item;
  - flag desligada: respostas com as MESMAS chaves de antes;
  - backfill do vínculo (dry-run, aplicar, revisão, reverter, isolamento);
  - regressão das regras de domínio com a flag (retenção só admin, baixa
    parcial vale o pago);
  - migração a7c4e2d9b351 (upgrade/downgrade em SQLite descartável).
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from fazenda.models import CaixaMovimento, ContaCorrente, ContaGerencial, MigracaoLogFinanceiro, Pessoa
from fazenda.rules import saldo_conta as sc
from fazenda.rules.datas import hoje_local
from fazenda.rules.vale_item import valor_caixa_parcela
from tests.test_relatorios_regras_v2 import (  # noqa: F401  (fixture `api`)
    _alembic, _colunas, _dre, _lanc, _ligar, _linha, _ok, _plano, api,
)

REVISAO_ANTERIOR = "a7c4e2d9f1b3"
REVISAO = "a7c4e2d9b351"
HOJE = hoje_local()


def _conta(c, banco="Banco X", agencia="1", numero="2"):
    return _ok(c.post("/financeiro/contas-correntes", json={"banco": banco, "agencia": agencia, "numero_conta": numero}))


def _saldo(c, conta_id, **q):
    return next(x for x in _ok(c.get("/financeiro/contas-correntes", params=q)) if x["id"] == conta_id)


def _pago(c, valor, data, rotulo=None, tipo="despesa", codigo="3.01", **extra):
    corpo = {"data_pagamento": data.isoformat() if isinstance(data, date) else data, "valor_pago": valor, **extra}
    if rotulo:
        corpo["conta_bancaria"] = rotulo
    return _lanc(c, codigo, valor, data=corpo["data_pagamento"], tipo=tipo, **corpo)


# =============================================================================
# Regras puras
# =============================================================================
def _ns(**kw):
    base = {"data_pagamento": date(2026, 10, 1), "valor_pago": 100.0, "valor_total": 100.0, "tipo": "despesa",
            "forma_pagamento": "pix", "data_vencimento_cartao": None, "gerado_por": None, "id": 1,
            "descricao": "x", "numero_lancamento": "LC-1"}
    return SimpleNamespace(**{**base, **kw})


def test_data_de_caixa_e_valor_efetivo():
    assert sc.data_caixa(_ns()) == date(2026, 10, 1)
    assert sc.data_caixa(_ns(data_pagamento=None)) is None
    # Cartão avulso: o dinheiro sai no vencimento do cartão (R3).
    assert sc.data_caixa(_ns(forma_pagamento="credito", data_vencimento_cartao=date(2026, 11, 15))) == date(2026, 11, 15)
    assert sc.valor_pago_efetivo(_ns(valor_pago=None, valor_total=700.0)) == 700  # L6: pago sem valor_pago
    assert sc.valor_pago_efetivo(_ns(valor_pago=1200.0, valor_total=2000.0)) == 1200  # baixa parcial vale o pago
    assert sc.conta_entra_no_caixa(_ns(gerado_por=sc.GERADO_POR_BACKFILL_CARTAO)) is False
    assert sc.conta_entra_no_caixa(_ns(gerado_por=sc.GERADO_POR_RETIRADA_CAIXA)) is True
    assert sc.eh_agendado(_ns(data_pagamento=date(2026, 10, 9)), date(2026, 10, 8)) is True
    assert sc.eh_agendado(_ns(data_pagamento=date(2026, 10, 8)), date(2026, 10, 8)) is False


def test_saldo_puro_abertura_agendado_e_transferencia():
    s = sc.novo_saldo(1, 1000.0, date(2026, 9, 30), date(2026, 10, 8))
    sc.aplicar_lancamento(s, _ns(data_pagamento=date(2026, 9, 30), valor_pago=50.0))   # dentro da abertura
    sc.aplicar_lancamento(s, _ns(data_pagamento=date(2026, 10, 2), valor_pago=200.0))  # −200
    sc.aplicar_lancamento(s, _ns(data_pagamento=date(2026, 10, 5), tipo="receita", valor_pago=80.0))  # +80
    sc.aplicar_lancamento(s, _ns(data_pagamento=date(2026, 10, 20), valor_pago=300.0))  # agendado
    sc.aplicar_lancamento(s, _ns(data_pagamento=date(2026, 10, 3), gerado_por=sc.GERADO_POR_BACKFILL_CARTAO))
    sc.aplicar_transferencia(s, date(2026, 10, 4), 100.0, entrada=False)
    sc.aplicar_transferencia(s, date(2026, 10, 30), 999.0, entrada=True)  # futura
    assert s.saldo == 1000 - 200 + 80 - 100
    assert s.agendado_liquido == -300 and s.pendente_abertura is False
    sem = sc.novo_saldo(2, None, None, date(2026, 10, 8))
    assert sem.pendente_abertura and sem.saldo == 0


@pytest.mark.parametrize("texto, esperado", [
    ("Banco X · Agência 1 · Conta corrente 2", (10, "exato")),
    ("banco x ag. 0001 c/c 2", (None, "ambiguo")),       # bate com as duas do Banco X
    ("Banco X - Agência 1 / Conta 2", (10, "normalizado")),
    ("Banco X 2 / 1", (None, "ambiguo")),                  # dígitos fora de ordem: não é agência+conta
    ("Sicredi", (30, "banco_unico")),
    ("Sicredí 9.800", (None, "nao_encontrado")),          # tem dígito que não bate: revisão
    ("Banco X", (None, "ambiguo")),                       # duas contas no Banco X
    ("Caixa", (None, "nao_encontrado")),
    ("", (None, "nao_encontrado")),
])
def test_casar_conta_corrente(texto, esperado):
    contas = [
        sc.ContaRef(10, "Banco X", "1", "2", "Banco X · Agência 1 · Conta corrente 2"),
        sc.ContaRef(20, "Banco X", "0001", "2", "Banco X · Agência 0001 · Conta corrente 2"),
        sc.ContaRef(30, "Sicredi", "0101", "55.555-1", "Sicredi · Agência 0101 · Conta corrente 55.555-1"),
    ]
    assert sc.casar_conta_corrente(texto, contas) == esperado


def test_casar_normalizado_sem_acento_e_pontuacao():
    contas = [sc.ContaRef(1, "Banco do Brasil", "3775-3", "3.615-3", "Banco do Brasil · Agência 3775-3 · Conta corrente 3.615-3"),
              sc.ContaRef(2, "Banco do Brasil", "4057-6", "3.615-3", "Banco do Brasil · Agência 4057-6 · Conta corrente 3.615-3")]
    assert sc.casar_conta_corrente("BANCO DO BRASIL ag 3775 3 cc 3615-3", contas) == (1, "normalizado")
    assert sc.casar_conta_corrente("Banco do Brasil", contas) == (None, "ambiguo")


def test_valor_caixa_parcela_nunca_desconta_vale():
    assert valor_caixa_parcela(_ns(data_pagamento=None, valor_pago=None, valor_total=1000.0)) == 1000
    assert valor_caixa_parcela(_ns(valor_pago=950.0, valor_total=1000.0)) == 950
    assert valor_caixa_parcela(_ns(valor_pago=None, valor_total=700.0)) == 700


# =============================================================================
# API: saldo por FK, abertura, agendado
# =============================================================================
def test_saldo_hoje_ignora_pagamento_futuro(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    cc = _conta(c)
    _pago(c, 100, HOJE - timedelta(days=2), cc["rotulo"])
    _pago(c, 400, HOJE + timedelta(days=10), cc["rotulo"])
    assert _saldo(c, cc["id"])["saldo"] == -500  # flag desligada: soma tudo (como antes)
    _ligar(engine)
    s = _saldo(c, cc["id"])
    assert s["saldo"] == -100 and s["agendado_liquido"] == -400 and s["agendados_quantidade"] == 1
    assert _saldo(c, cc["id"], hoje=(HOJE + timedelta(days=10)).isoformat())["saldo"] == -500


def test_saldo_parte_do_saldo_de_abertura_e_valida(api):
    c, engine, estado = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    _ligar(engine)
    cc = _conta(c)
    _pago(c, 30, HOJE - timedelta(days=20), cc["rotulo"])   # antes da abertura: já está nela
    _pago(c, 100, HOJE - timedelta(days=2), cc["rotulo"])
    abertura = (HOJE - timedelta(days=10)).isoformat()
    url = f"/financeiro/contas-correntes/{cc['id']}/saldo-abertura"
    assert c.put(url, json={"saldo_abertura": 500}).status_code == 400
    assert c.put(url, json={"saldo_abertura": 500, "data_saldo_abertura": (HOJE + timedelta(days=1)).isoformat()}).status_code == 400
    estado["papel"] = "operador"
    assert c.put(url, json={"saldo_abertura": 500, "data_saldo_abertura": abertura}).status_code == 403
    estado["papel"] = "admin"
    r = _ok(c.put(url, json={"saldo_abertura": 500, "data_saldo_abertura": abertura}))
    assert r["saldo"] == 400 and r["pendente_saldo_abertura"] is False
    # Editar banco/agência não apaga a abertura.
    _ok(c.put(f"/financeiro/contas-correntes/{cc['id']}", json={"banco": "Banco X", "agencia": "1", "numero_conta": "2", "ativo": True}))
    assert _saldo(c, cc["id"])["saldo_abertura"] == 500
    # Transferência depois da abertura entra; remover a abertura volta à pendência.
    cc2 = _conta(c, "Banco Y", "3", "4")
    _ok(c.post("/financeiro/contas-correntes/transferencias", json={
        "conta_origem_id": cc["id"], "conta_destino_id": cc2["id"], "valor": 50, "data": HOJE.isoformat()}))
    assert _saldo(c, cc["id"])["saldo"] == 350 and _saldo(c, cc2["id"])["saldo"] == 50
    r = _ok(c.put(url, json={"saldo_abertura": None, "data_saldo_abertura": None}))
    assert r["pendente_saldo_abertura"] is True and r["saldo"] == -180


def test_casamento_por_conta_corrente_id_e_nao_por_texto(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    _ligar(engine)
    cc = _conta(c)
    outra = _conta(c, "Banco Y", "3", "4")
    # Rótulo de uma conta, FK de outra: vale a FK.
    r = _pago(c, 100, HOJE, cc["rotulo"], conta_corrente_id=outra["id"])
    with Session(engine) as s:
        assert s.get(ContaGerencial, r["ids"][0]).conta_corrente_id == outra["id"]
    assert _saldo(c, cc["id"])["saldo"] == 0 and _saldo(c, outra["id"])["saldo"] == -100
    # Renomear a conta não tira o pagamento dela (o texto antigo deixa de bater).
    _ok(c.put(f"/financeiro/contas-correntes/{outra['id']}", json={"banco": "Banco Z", "agencia": "3", "numero_conta": "4", "ativo": True}))
    assert _saldo(c, outra["id"])["saldo"] == -100
    # Linha sem FK (histórico) ainda casa pelo rótulo exato.
    with Session(engine) as s:
        legado = ContaGerencial(fazenda_id=1, tipo="despesa", valor_total=40, valor_pago=40, data_pagamento=HOJE,
                                conta_bancaria=cc["rotulo"], numero_lancamento="LC-LEG-1")
        s.add(legado)
        s.commit()
    assert _saldo(c, cc["id"])["saldo"] == -40
    # FK de outra fazenda é recusada.
    assert c.put(f"/financeiro/lancamentos/{r['ids'][0]}/pagar", json={
        "data_pagamento": HOJE.isoformat(), "valor_pago": 100, "conta_corrente_id": 999}).status_code == 404


def test_pago_sem_valor_pago_nasce_com_valor_total_e_zero_e_recusado(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    sem_flag = _lanc(c, "3.01", 700, data="2031-03-28", data_pagamento="2031-03-28")
    _ligar(engine)
    com_flag = _lanc(c, "3.01", 700, data="2031-03-28", data_pagamento="2031-03-28")
    parcelado = _lanc(c, "3.01", 300, data="2031-03-28", parcelas=[
        {"data_vencimento": "2031-03-28", "valor": 100, "data_pagamento": "2031-03-28"},
        {"data_vencimento": "2031-04-28", "valor": 200}])
    with Session(engine) as s:
        assert (s.get(ContaGerencial, sem_flag["ids"][0]).valor_pago, s.get(ContaGerencial, sem_flag["ids"][0]).desconto_acrescimo) == (None, -700)
        novo = s.get(ContaGerencial, com_flag["ids"][0])
        assert (novo.valor_pago, novo.desconto_acrescimo) == (700, 0)
        p1, p2 = (s.get(ContaGerencial, i) for i in parcelado["ids"])
        assert (p1.valor_pago, p1.desconto_acrescimo, p2.valor_pago) == (100, 0, None)
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa", "itens": [{"produto": "x", "codigo_conta_gerencial": "3.01", "valor_total": 10, "tipo_item": "servico"}],
        "data_emissao": "2031-03-28", "data_pagamento": "2031-03-28", "valor_pago": 0})
    assert r.status_code == 400
    aberto = _lanc(c, "3.01", 50, data="2031-03-28", data_vencimento="2031-04-01")
    assert c.put(f"/financeiro/lancamentos/{aberto['ids'][0]}/pagar", json={
        "data_pagamento": "2031-04-01", "valor_pago": 0}).status_code == 400
    assert c.put("/financeiro/lancamentos/baixa-lote-detalhada", json={"itens": [{
        "lancamento_id": aberto["ids"][0], "data_pagamento": "2031-04-01", "valor_pago": -1}]}).status_code == 400


def test_pagamento_com_data_futura_vira_agendado_e_aparece_no_caixa_real(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    cc = _conta(c)
    aberto = _lanc(c, "3.01", 250, data=HOJE.isoformat(), data_vencimento=(HOJE + timedelta(days=3)).isoformat(),
                   produto="Boleto agendado")
    futuro = (HOJE + timedelta(days=5)).isoformat()
    sem_flag = _ok(c.put(f"/financeiro/lancamentos/{aberto['ids'][0]}/pagar", json={
        "data_pagamento": futuro, "valor_pago": 250, "conta_bancaria": cc["rotulo"]}))
    assert "agendado" not in sem_flag
    _ok(c.post(f"/financeiro/lancamentos/{aberto['ids'][0]}/estornar", json={"motivo": "x"}))
    _ligar(engine)
    r = _ok(c.put(f"/financeiro/lancamentos/{aberto['ids'][0]}/pagar", json={
        "data_pagamento": futuro, "valor_pago": 250, "conta_bancaria": cc["rotulo"]}))
    assert r["agendado"] is True and r["conta_corrente_id"] == cc["id"]
    assert _saldo(c, cc["id"])["saldo"] == 0
    cr = _ok(c.get("/financeiro/caixa-real", params={"dias": 30}))
    itens = [(p["data"], i) for p in cr["serie"] for i in p["itens"] if i["descricao"] == "Boleto agendado"]
    assert len(itens) == 1 and itens[0][0] == futuro and itens[0][1]["agendado"] is True
    assert cr["saldo_final"] == -250
    hoje_pago = _lanc(c, "3.01", 10, data=HOJE.isoformat(), data_vencimento=HOJE.isoformat())
    assert _ok(c.put(f"/financeiro/lancamentos/{hoje_pago['ids'][0]}/pagar", json={
        "data_pagamento": HOJE.isoformat(), "valor_pago": 10}))["agendado"] is False


def test_cartao_avulso_sai_no_vencimento_do_cartao(api):
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    _ligar(engine)
    cc = _conta(c)
    aberto = _lanc(c, "3.01", 300, data="2031-03-05", data_vencimento="2031-03-05")
    _ok(c.put(f"/financeiro/lancamentos/{aberto['ids'][0]}/pagar", json={
        "data_pagamento": "2031-03-05", "valor_pago": 300, "forma_pagamento": "credito",
        "data_vencimento_cartao": "2031-04-15", "conta_bancaria": cc["rotulo"]}))
    assert _saldo(c, cc["id"], hoje="2031-04-14")["saldo"] == 0
    assert _saldo(c, cc["id"], hoje="2031-04-15")["saldo"] == -300
    # DRE de caixa: no mês do vencimento do cartão; competência: no da compra.
    assert _linha(_dre(c, "2031-03-01", "2031-03-31", regime="caixa"), "CUSTO_VARIAVEL") == 0
    assert _linha(_dre(c, "2031-04-01", "2031-04-30", regime="caixa"), "CUSTO_VARIAVEL") == 300
    assert _linha(_dre(c), "CUSTO_VARIAVEL") == 300


def test_caixa_real_igual_contas_a_pagar_e_fundo_reserva_sem_vale(api):
    """O Caixa Real projeta o mesmo valor que Contas a pagar mostra (o boleto
    inteiro, com o vale de item dentro) e o fundo de reserva soma o que foi
    PAGO — sem o desconto do vale."""
    c, engine, _ = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    with Session(engine) as s:
        ana = Pessoa(nome="Ana", tipo="funcionario", tipo_vinculo="clt", salario_base=3000.0, fazenda_id=1)
        s.add(ana)
        s.commit()
        ana_id = ana.id
    venc = (HOJE + timedelta(days=20)).isoformat()
    competencia = f"{HOJE.year:04d}-{HOJE.month:02d}"
    corpo = {"tipo": "despesa", "centro_custo": "Pecuária Leiteira", "fornecedor_cliente": "Agro",
             "data_emissao": HOJE.isoformat(), "data_competencia": HOJE.isoformat(), "data_vencimento": venc,
             "itens": [{"produto": "Ração fazenda", "codigo_conta_gerencial": "3.01", "valor_total": 800, "tipo_item": "servico"},
                       {"produto": "Ração cachorro", "codigo_conta_gerencial": "3.01", "valor_total": 200, "tipo_item": "servico",
                        "vale": {"pessoa_id": ana_id, "modo": "folha", "parcelas": 1, "competencia_inicio": competencia,
                                 "confirmar": True}}]}
    boleto = _ok(c.post("/financeiro/lancamentos", json=corpo))
    mes_passado = (HOJE.replace(day=1) - timedelta(days=10))
    corpo_pago = {**corpo, "data_emissao": mes_passado.isoformat(), "data_competencia": mes_passado.isoformat(),
                  "data_vencimento": mes_passado.isoformat(), "data_pagamento": mes_passado.isoformat(), "valor_pago": 1000}
    _ok(c.post("/financeiro/lancamentos", json=corpo_pago))

    def valor_no_caixa():
        cr = _ok(c.get("/financeiro/caixa-real", params={"dias": 90}))
        return [i["valor"] for p in cr["serie"] for i in p["itens"] if i["descricao"].startswith("Ração fazenda")]
    sugerido_antes = _ok(c.get("/financeiro/caixa-real/fundo-reserva-sugerido"))["meses_considerados"]
    assert valor_no_caixa() == [800] and sugerido_antes[-1]["saidas"] == 800
    _ligar(engine)
    a_pagar = [x for x in _ok(c.get("/financeiro/contas-a-pagar", params={"dias": 90})) if x["id"] == boleto["ids"][0]]
    assert valor_no_caixa() == [1000] == [x["valor_total"] for x in a_pagar]
    sugerido = _ok(c.get("/financeiro/caixa-real/fundo-reserva-sugerido"))
    assert sugerido["meses_considerados"][-1] == {"mes": mes_passado.strftime("%Y-%m"), "saidas": 1000}
    assert sugerido["regras_v2"] is True


# =============================================================================
# Retirada do caixa do funcionário
# =============================================================================
def _caixa_com_saldo(c, engine, valor=500):
    with Session(engine) as s:
        p = Pessoa(nome="Zé", tipo="funcionario", tipo_vinculo="empreita", fazenda_id=1)
        s.add(p)
        s.commit()
        pid = p.id
    _ok(c.post("/cadastro/caixa-funcionarios/entradas", json={
        "tipo": "deposito", "valor": valor, "data": HOJE.isoformat(), "motivo": "prêmio",
        "pessoa_ids": [pid]}))
    return pid


def test_retirada_do_caixa_reduz_saldo_e_nao_entra_na_dre(api):
    c, engine, _ = api
    cc = _conta(c)
    pid = _caixa_com_saldo(c, engine)
    _ok(c.post(f"/cadastro/caixa-funcionarios/{pid}/retiradas", json={
        "valor": 100, "data": HOJE.isoformat(), "forma_pagamento": "pix", "conta_bancaria": cc["rotulo"]}))
    assert _saldo(c, cc["id"])["saldo"] == 0  # flag desligada: como antes (não mexia no banco)
    _ligar(engine)
    r = _ok(c.post(f"/cadastro/caixa-funcionarios/{pid}/retiradas", json={
        "valor": 150, "data": HOJE.isoformat(), "forma_pagamento": "pix", "conta_bancaria": cc["rotulo"]}))
    assert r["movimento"]["numero_lancamento"]
    _ok(c.post(f"/cadastro/caixa-funcionarios/{pid}/retiradas", json={
        "valor": 20, "data": HOJE.isoformat(), "forma_pagamento": "dinheiro", "conta_bancaria": cc["rotulo"]}))
    assert _saldo(c, cc["id"])["saldo"] == -150
    with Session(engine) as s:
        nota = s.exec(select(ContaGerencial).where(ContaGerencial.gerado_por == sc.GERADO_POR_RETIRADA_CAIXA)).one()
        assert (nota.natureza_fin, nota.tipo, nota.valor_pago, nota.conta_corrente_id) == ("OBRIGACAO", "despesa", 150, cc["id"])
    d = _dre(c, HOJE.replace(day=1).isoformat(), HOJE.isoformat())
    assert d["fora_da_dre"]["por_natureza"].get("OBRIGACAO") == 150
    # Na DRE só o depósito (despesa de pessoal; sem conta até o PR 2, em não
    # classificado) — a retirada não é custo de novo.
    assert d["nao_classificado"]["total"] == 500 and _linha(d, "RESULTADO_LIQUIDO") == 0
    # Estorno devolve o dinheiro para a conta.
    mov_id = r["movimento"]["id"]
    _ok(c.post(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{mov_id}/estornar", json={"motivo": "pix errado"}))
    assert _saldo(c, cc["id"])["saldo"] == 0
    with Session(engine) as s:
        contra = s.exec(select(ContaGerencial).where(ContaGerencial.tipo == "receita",
                                                     ContaGerencial.gerado_por == sc.GERADO_POR_RETIRADA_CAIXA)).one()
        assert contra.natureza_fin == "OBRIGACAO" and contra.conta_corrente_id == cc["id"]


def test_excluir_retirada_apaga_a_saida_do_banco(api):
    c, engine, _ = api
    _ligar(engine)
    cc = _conta(c)
    pid = _caixa_com_saldo(c, engine)
    r = _ok(c.post(f"/cadastro/caixa-funcionarios/{pid}/retiradas", json={
        "valor": 70, "data": HOJE.isoformat(), "forma_pagamento": "transferencia", "conta_bancaria": cc["rotulo"]}))
    assert _saldo(c, cc["id"])["saldo"] == -70
    _ok(c.delete(f"/cadastro/caixa-funcionarios/{pid}/movimentos/{r['movimento']['id']}"))
    assert _saldo(c, cc["id"])["saldo"] == 0
    with Session(engine) as s:
        assert s.exec(select(CaixaMovimento).where(CaixaMovimento.tipo == "retirada")).all() == []


# =============================================================================
# Flag desligada: mesmas chaves de antes
# =============================================================================
def test_flag_desligada_mesmo_formato_de_resposta(api):
    c, _engine, _ = api
    cc = _conta(c)
    assert set(cc) == {"id", "fazenda_id", "banco", "agencia", "numero_conta", "ativo", "criado_em", "rotulo", "saldo"}
    assert set(_saldo(c, cc["id"])) == set(cc)
    cr = _ok(c.get("/financeiro/caixa-real", params={"dias": 10}))
    assert set(cr) == {"saldo_inicial", "saldo_final", "total_entradas", "total_saidas", "variacao", "fundo_reserva",
                       "primeiro_dia_negativo", "primeiro_dia_abaixo_da_reserva", "folga_minima", "serie", "dias",
                       "contas", "compromissos_sem_vencimento"}
    assert set(cr["contas"][0]) == {"id", "nome", "saldo"}
    assert "regras_v2" not in _ok(c.get("/financeiro/caixa-real/fundo-reserva-sugerido"))


# =============================================================================
# Backfill do vínculo conta_corrente_id
# =============================================================================
def test_backfill_conta_corrente_dry_run_aplicar_revisao_e_reverter(api):
    from scripts.backfill_conta_corrente import executar

    c, engine, _ = api
    _ok(c.post("/financeiro/contas-correntes", json={"banco": "Banco do Brasil", "agencia": "3775-3", "numero_conta": "3.615-3"}))
    _ok(c.post("/financeiro/contas-correntes", json={"banco": "Banco do Brasil", "agencia": "4057-6", "numero_conta": "3.615-3"}))
    sicredi = _ok(c.post("/financeiro/contas-correntes", json={"banco": "Sicredi", "agencia": "0101", "numero_conta": "55"}))
    textos = ["Banco do Brasil · Agência 3775-3 · Conta corrente 3.615-3", "banco do brasil ag 4057-6 cc 3615-3",
              "Banco do Brasil", "Sicredi", "Caixa Econômica"]
    with Session(engine) as s:
        for i, t in enumerate(textos):
            s.add(ContaGerencial(fazenda_id=1, tipo="despesa", valor_total=100 + i, valor_pago=100 + i,
                                 data_pagamento=date(2026, 9, 1), conta_bancaria=t, numero_lancamento=f"LC-B-{i}"))
        # Outra fazenda: nunca entra no plano da 1.
        s.add(ContaGerencial(fazenda_id=2, tipo="despesa", valor_total=9, valor_pago=9, data_pagamento=date(2026, 9, 1),
                             conta_bancaria="Sicredi", numero_lancamento="LC-F2"))
        s.commit()
    with Session(engine) as s:
        plano = executar(s, 1, aplicar=False, saida=lambda *_: None)["plano"]
        assert [(m["numero_lancamento"], m["regra"]) for m in plano.mudancas] == [
            ("LC-B-0", "exato"), ("LC-B-1", "normalizado"), ("LC-B-3", "banco_unico")]
        assert [r["numero_lancamento"] for r in plano.revisao] == ["LC-B-2", "LC-B-4"]
        assert s.exec(select(ContaGerencial).where(ContaGerencial.conta_corrente_id != None)).all() == []  # noqa: E711
    revisao = _ok(c.get("/financeiro/conta-corrente/revisao"))
    assert [r["numero_lancamento"] for r in revisao["revisao"]] == ["LC-B-2", "LC-B-4"]
    with Session(engine) as s:
        lote = executar(s, 1, aplicar=True, saida=lambda *_: None)["lote"]
    with Session(engine) as s:
        ligados = {x.numero_lancamento: x.conta_corrente_id for x in s.exec(select(ContaGerencial)).all()}
        assert ligados["LC-B-3"] == sicredi["id"] and ligados["LC-B-2"] is None and ligados["LC-F2"] is None
        assert len(s.exec(select(MigracaoLogFinanceiro).where(MigracaoLogFinanceiro.lote == lote)).all()) == 3
        # Nunca reescreve valor.
        assert sorted(x.valor_pago for x in s.exec(select(ContaGerencial).where(ContaGerencial.fazenda_id == 1)).all()) == [100, 101, 102, 103, 104]
    # Ligação em lote do que ficou na revisão.
    ids_revisao = [r["id"] for r in revisao["revisao"]]
    assert _ok(c.put("/financeiro/lancamentos/conta-corrente-lote", json={
        "lancamento_ids": ids_revisao, "conta_corrente_id": sicredi["id"]}))["ligados"] == 2
    with Session(engine) as s:
        resultado = executar(s, 1, aplicar=True, reverter=lote, saida=lambda *_: None)["reversao"]
        assert resultado.revertidas == 3
    with Session(engine) as s:
        ligados = {x.numero_lancamento: x.conta_corrente_id for x in s.exec(select(ContaGerencial)).all()}
        assert ligados["LC-B-0"] is None and ligados["LC-B-3"] is None
        assert ligados["LC-B-2"] == sicredi["id"]  # ligação manual não é do lote


# =============================================================================
# Regressão das regras de domínio com a flag ligada
# =============================================================================
def test_regressao_retencao_so_admin_e_baixa_parcial_vale_o_pago(api):
    c, engine, estado = api
    _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
    _ligar(engine)
    cc = _conta(c)
    aberto = _lanc(c, "3.01", 1000, data=HOJE.isoformat(), data_vencimento=HOJE.isoformat())
    estado["papel"] = "operador"
    r = c.put(f"/financeiro/lancamentos/{aberto['ids'][0]}/pagar", json={
        "data_pagamento": HOJE.isoformat(), "valor_pago": 1000, "retencao_caixa": {"modo": "valor", "valor": 50}})
    assert r.status_code in (403, 400), r.text
    estado["papel"] = "admin"
    _ok(c.put(f"/financeiro/lancamentos/{aberto['ids'][0]}/pagar", json={
        "data_pagamento": HOJE.isoformat(), "valor_pago": 600, "conta_bancaria": cc["rotulo"],
        "parcelas_diferenca": [{"data_vencimento": (HOJE + timedelta(days=30)).isoformat(), "valor": 400}]}))
    assert _saldo(c, cc["id"])["saldo"] == -600
    cr = _ok(c.get("/financeiro/caixa-real", params={"dias": 60}))
    assert cr["total_saidas"] == 400  # a parcela nova da diferença, no vencimento dela
    assert _linha(_dre(c, HOJE.replace(day=1).isoformat(), (HOJE + timedelta(days=40)).isoformat()), "CUSTO_VARIAVEL") == 1000


# =============================================================================
# Script de impacto (somente leitura): seção "saldo"
# =============================================================================
def test_script_de_impacto_mostra_o_saldo_antes_e_depois(tmp_path):
    import csv
    import hashlib

    from sqlmodel import SQLModel, create_engine

    from scripts.impacto_relatorios_v2 import executar
    from tests.cenario_auditoria_financeiro import preparar_fazendas
    from tests.test_relatorios_regras_v2 import _api

    db = tmp_path / "dump.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    preparar_fazendas(engine)
    with _api(engine, {"fazenda_id": 1}) as c:
        _plano(c, "3.01", "Ração", "CUSTO_VARIAVEL")
        cc = _conta(c)
        _pago(c, 100, HOJE - timedelta(days=1), cc["rotulo"])
        _pago(c, 900, HOJE + timedelta(days=30), cc["rotulo"])
        with Session(engine) as s:
            s.add(ContaGerencial(fazenda_id=1, tipo="despesa", valor_total=5, valor_pago=5, data_pagamento=HOJE,
                                 conta_bancaria="Banco X", numero_lancamento="LC-TXT"))
            s.commit()
    engine.dispose()
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    saida = tmp_path / "impacto.csv"
    executar(engine, 1, f"{HOJE:%Y-%m}", f"{HOJE:%Y-%m}", str(saida))
    engine.dispose()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes
    por = {r["metrica"]: r for r in csv.DictReader(saida.open(encoding="utf-8-sig"), delimiter=";") if r["secao"] == "saldo"}
    saldo = por[f"saldo_hoje[{cc['rotulo']}]"]
    assert (float(saldo["antes"]), float(saldo["depois"])) == (-1000, -100)
    assert float(por[f"agendado_liquido[{cc['rotulo']}]"]["depois"]) == -900
    assert float(por["vinculo.lista_de_revisao"]["depois"]) == 0
    assert float(por["vinculo.ligaveis_pelo_backfill"]["depois"]) == 1  # "Banco X": banco único


# =============================================================================
# Migração
# =============================================================================
def test_migracao_saldo_abertura_sobe_desce_e_e_idempotente(tmp_path):
    db = tmp_path / "mig.db"
    _alembic(db, "upgrade", REVISAO_ANTERIOR)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO conta_corrente (banco, agencia, numero_conta, ativo, criado_em) VALUES ('B', '1', '2', 1, '2026-01-01')")
    conn.execute("INSERT INTO conta_gerencial (numero_lancamento, tipo, valor_total, valor_pago, conta_bancaria, origem, atualizado_em) "
                 "VALUES ('LC-1', 'despesa', 123.0, 120.0, 'B · Agência 1 · Conta corrente 2', 'manual', '2026-01-01')")
    conn.commit()
    conn.close()
    _alembic(db, "upgrade", REVISAO)
    assert {"saldo_abertura", "data_saldo_abertura"} <= set(_colunas(db, "conta_corrente"))
    info = _colunas(db, "conta_gerencial")
    assert info["conta_corrente_id"]["notnull"] == 0 and info["gerado_por"]["default"] is None
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT valor_total, valor_pago, conta_corrente_id, gerado_por FROM conta_gerencial").fetchone() == (123.0, 120.0, None, None)
    fks = [r[2] for r in conn.execute("PRAGMA foreign_key_list(conta_gerencial)")]
    assert "conta_corrente" in fks
    conn.close()
    _alembic(db, "downgrade", REVISAO_ANTERIOR)
    assert "conta_corrente_id" not in _colunas(db, "conta_gerencial")
    assert "saldo_abertura" not in _colunas(db, "conta_corrente")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT valor_total, valor_pago FROM conta_gerencial").fetchone() == (123.0, 120.0)
    conn.close()
    # Deploy: create_all do boot já criou as colunas antes do upgrade.
    db2 = tmp_path / "boot.db"
    _alembic(db2, "upgrade", REVISAO_ANTERIOR)
    conn = sqlite3.connect(db2)
    conn.execute("ALTER TABLE conta_gerencial ADD COLUMN conta_corrente_id INTEGER")
    conn.execute("ALTER TABLE conta_gerencial ADD COLUMN gerado_por VARCHAR")
    conn.execute("ALTER TABLE conta_corrente ADD COLUMN saldo_abertura FLOAT")
    conn.commit()
    conn.close()
    _alembic(db2, "upgrade", "head")
    assert "(head)" in _alembic(db2, "current")
    assert "data_saldo_abertura" in _colunas(db2, "conta_corrente")
