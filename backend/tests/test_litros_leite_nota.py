"""
T4 — litros do leite pela NOTA do laticínio (Financeiro › receita); a "Venda
mensal do leite" (EntregaLeiteMensal) é só a RESERVA dos meses sem nota.

Duas camadas:

- a regra pura (`rules/litros_leite.py`): nota > venda mensal > sem dado, mês a
  mês, e o mês com item de leite sem unidade cai na reserva;
- o endpoint, sobre o cenário da auditoria (março/2031, plano 8.*, fazendas 1 e 2):
  Resultado por litro, custo por litro e preço médio do litro (RMCA), com a
  flag `financeiro_regras_v2` ligada e desligada, regime caixa × competência,
  o item "Leite" de dieta, o isolamento entre fazendas e o endpoint de uso do
  item de estoque.

Com a flag DESLIGADA a saída é a de antes (os goldens do cenário da auditoria
seguem valendo; aqui se trava que as chaves novas nem existem).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, select

from fazenda.models import Alimento, DietaItemProgramado, DietaLancamento, Estoque, MovimentoEstoque
from fazenda.rules.litros_leite import (
    FONTE_MISTA, FONTE_NOTA, FONTE_SEM_DADO, FONTE_VENDA_MENSAL, campos_fonte_para_api, litros_do_leite,
    litros_no_periodo,
)
from fazenda.rules.unidades import unidade_leite_canonica
from tests.cenario_auditoria_financeiro import BANCO
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário da auditoria)

LEITE = "Leite Cru Refrigerado"


# ---------------------------------------------------------------------------
# Regra pura
# ---------------------------------------------------------------------------
def test_unidade_da_nota_nunca_e_chutada():
    assert unidade_leite_canonica("L") == "L" and unidade_leite_canonica(" litros ") == "L"
    assert unidade_leite_canonica("Kg") == "kg" and unidade_leite_canonica("quilos") == "kg"
    # Diferente de `leite_em_litros` (unidade ausente = kg): aqui ausente é "não sei".
    for ruim in (None, "", "saca 60kg", "ml", "dose", "arroba"):
        assert unidade_leite_canonica(ruim) is None


def test_nota_vence_a_venda_mensal_e_a_reserva_so_entra_sem_nota():
    r = litros_do_leite(
        ["2031-05", "2031-06", "2031-07"],
        litros_notas={"2031-05": 8000.0}, litros_venda_mensal={"2031-05": 5000.0, "2031-06": 10000.0},
    )
    assert (r["2031-05"].fonte, r["2031-05"].litros) == (FONTE_NOTA, 8000.0)
    assert r["2031-05"].litros_venda_mensal == 5000.0  # a reserva fica visível para conferência
    assert (r["2031-06"].fonte, r["2031-06"].litros) == (FONTE_VENDA_MENSAL, 10000.0)
    assert (r["2031-07"].fonte, r["2031-07"].litros) == (FONTE_SEM_DADO, 0.0)


def test_mes_com_nota_incompleta_cai_na_reserva_ou_fica_sem_dado():
    kw = dict(litros_notas={"2031-05": 3000.0, "2031-06": 3000.0}, meses_nota_incompleta={"2031-05", "2031-06"})
    r = litros_do_leite(["2031-05", "2031-06"], litros_venda_mensal={"2031-05": 9000.0}, **kw)
    # Os 3.000 L parciais da nota NÃO valem (a receita do mês tem a nota inteira).
    assert (r["2031-05"].fonte, r["2031-05"].litros, r["2031-05"].nota_incompleta) == (FONTE_VENDA_MENSAL, 9000.0, True)
    assert (r["2031-06"].fonte, r["2031-06"].litros) == (FONTE_SEM_DADO, 0.0)


def test_periodo_mista_projeta_por_dia_e_diz_quanto_e_estimado():
    meses = litros_do_leite(
        ["2031-05", "2031-06"], litros_notas={"2031-05": 3100.0}, litros_venda_mensal={"2031-06": 3000.0},
    )
    # 1 a 15/05 (15 dias de 31) + 1 a 30/06 inteiro.
    r = litros_no_periodo(meses, date(2031, 5, 1), date(2031, 6, 30))
    assert r["fonte"] == FONTE_MISTA and r["litros"] == 3100.0 + 3000.0
    assert r["por_fonte"] == {FONTE_NOTA: 3100.0, FONTE_VENDA_MENSAL: 3000.0}
    assert r["pct_estimado"] == 49.2
    parcial = litros_no_periodo(meses, date(2031, 5, 1), date(2031, 5, 15))
    assert parcial["litros"] == pytest.approx(3100.0 / 31 * 15) and parcial["fonte"] == FONTE_NOTA
    assert parcial["pct_estimado"] == 0.0
    vazio = litros_no_periodo(meses, date(2031, 8, 1), date(2031, 8, 31))
    assert (vazio["fonte"], vazio["litros"], vazio["pct_estimado"]) == (FONTE_SEM_DADO, 0.0, None)
    api = campos_fonte_para_api(r)
    assert set(api) == {"fonte_litros", "litros_por_fonte", "pct_litros_estimados", "meses_litros"}
    assert [m["fonte"] for m in api["meses_litros"]] == [FONTE_NOTA, FONTE_VENDA_MENSAL]


# ---------------------------------------------------------------------------
# Endpoints, sobre o cenário da auditoria
# ---------------------------------------------------------------------------
def _estoque(cenario, nome, unidade, *, produto_leite=False, fazenda_id=1, **kw) -> int:  # noqa: F811
    with Session(cenario.engine) as s:
        e = Estoque(nome=nome, unidade=unidade, produto_leite=produto_leite, fazenda_id=fazenda_id, ativo=True, **kw)
        s.add(e)
        s.commit()
        s.refresh(e)
        return e.id


def _nota(cenario, data, produto, quantidade, valor, *, conta="8.1", tipo="receita", nome="LAT", **extra) -> dict:  # noqa: F811
    item = {"produto": produto, "codigo_conta_gerencial": conta, "valor_total": valor, "tipo_item": "produto"}
    if quantidade is not None:
        item["quantidade"] = quantidade
    corpo = {
        "tipo": tipo, "centro_custo": "Pecuária Leiteira", "fornecedor_cliente": f"LAT-{nome}", "itens": [item],
        "data_emissao": data, "data_competencia": data, "data_vencimento": data, **extra,
    }
    r = cenario.c.post("/financeiro/lancamentos", json=corpo)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _venda_mensal(cenario, competencia, quantidade, unidade="kg"):  # noqa: F811
    r = cenario.c.post("/producao/entrega-leite", json={"competencia": competencia, "quantidade_litros": quantidade, "unidade": unidade})
    assert r.status_code in (200, 201), r.text


def _res(cenario, ini, fim, **q) -> dict:  # noqa: F811
    return cenario.get("/financeiro/resultado-por-litro", data_inicio=ini, data_fim=fim, **q)


def test_nota_vale_mais_que_a_venda_mensal(cenario):  # noqa: F811
    _estoque(cenario, LEITE, "L", produto_leite=True)
    _venda_mensal(cenario, "2031-05", 5145, "kg")  # a reserva: 5.000 L
    _nota(cenario, "2031-05-31", LEITE, 8000, 16000)
    cenario.ligar_regras_v2()

    r = _res(cenario, "2031-05-01", "2031-05-31")
    a = r["atual"]
    assert a["litros"] == 8000.0 and a["fonte_litros"] == FONTE_NOTA
    assert a["litros_por_fonte"] == {FONTE_NOTA: 8000.0, FONTE_VENDA_MENSAL: 0.0}
    assert a["pct_litros_estimados"] == 0.0
    assert a["preco_bruto_l"] == 2.0  # R$ 16.000 da nota ÷ os litros DA MESMA nota
    assert r["configuracao"]["tem_nota_leite"] is True and r["configuracao"]["tem_entrega"] is True
    # Nada de "estimado" nem de conversão: a nota foi lançada em litro.
    assert r["avisos"] == [] and r["avisos_fonte_litros"] == []

    cl = cenario.get("/financeiro/custo-litro-leite", data_inicio="2031-05-01", data_fim="2031-05-31")
    assert cl["litros"] == 8000.0 and cl["fonte_litros"] == FONTE_NOTA and cl["pct_litros_estimados"] == 0.0


def test_mes_misto_marca_a_fonte_de_cada_mes_e_avisa_o_estimado(cenario):  # noqa: F811
    _estoque(cenario, LEITE, "L", produto_leite=True)
    _nota(cenario, "2031-05-31", LEITE, 8000, 16000)
    _venda_mensal(cenario, "2031-06", 10290, "kg")  # só a reserva: 10.000 L
    cenario.ligar_regras_v2()

    r = _res(cenario, "2031-05-01", "2031-06-30", serie_meses=3)
    a = r["atual"]
    assert a["litros"] == 18000.0 and a["fonte_litros"] == FONTE_MISTA
    assert a["litros_por_fonte"] == {FONTE_NOTA: 8000.0, FONTE_VENDA_MENSAL: 10000.0}
    assert a["pct_litros_estimados"] == 55.6
    assert [(m["competencia"], m["fonte"]) for m in a["meses_litros"]] == [("2031-05", FONTE_NOTA), ("2031-06", FONTE_VENDA_MENSAL)]
    # A série (3 meses fechados terminando em jun/2031): abr sem dado, mai nota, jun reserva.
    assert [(m["competencia"], m["fonte_litros"]) for m in r["serie"]] == [
        ("2031-04", FONTE_SEM_DADO), ("2031-05", FONTE_NOTA), ("2031-06", FONTE_VENDA_MENSAL)]
    assert r["serie"][0]["litros"] == 0.0 and r["serie"][0]["coe_l"] is None
    assert any("estimados pela Venda mensal" in x and "06/2031" in x and "05/2031" not in x for x in r["avisos_fonte_litros"])
    # A reserva em kg foi convertida (a nota em litro não precisa).
    assert any("convertida para litros" in x for x in r["avisos"])


def test_nota_em_kg_vira_litro_pela_unidade_do_item_de_estoque(cenario):  # noqa: F811
    _estoque(cenario, LEITE, "kg", produto_leite=True)
    _nota(cenario, "2031-05-31", LEITE, 10290, 20000)
    cenario.ligar_regras_v2()

    a = _res(cenario, "2031-05-01", "2031-05-31")["atual"]
    assert a["litros"] == 10000.0 and a["fonte_litros"] == FONTE_NOTA  # 10.290 kg ÷ 1,029
    cl = cenario.get("/financeiro/custo-litro-leite", data_inicio="2031-05-01", data_fim="2031-05-31")
    assert cl["litros"] == 10000.0 and cl["unidade_origem"] == "kg" and cl["litros_convertidos_de_kg"] is True
    assert any("convertida para litros" in x for x in cl["avisos"])


def test_nota_sem_unidade_avisa_e_nao_entra_com_chute(cenario):  # noqa: F811
    _estoque(cenario, LEITE, None, produto_leite=True)  # marcado, mas sem unidade cadastrada
    n = _nota(cenario, "2031-05-31", LEITE, 8000, 16000)["numero_lancamento"]
    cenario.ligar_regras_v2()

    # Sem Venda mensal: o mês fica sem dado (nunca 8.000 "chutados" como kg ou litro).
    r = _res(cenario, "2031-05-01", "2031-05-31")
    assert r["atual"]["litros"] == 0.0 and r["atual"]["fonte_litros"] == FONTE_SEM_DADO
    assert r["atual"]["preco_bruto_l"] is None
    assert any(f"Nota {n} sem unidade" in x and '"Produto de leite"' in x for x in r["avisos_fonte_litros"])
    assert r["atual"]["meses_litros"][0]["nota_incompleta"] is True

    # Com Venda mensal: o mês cai na reserva (estimado), com o mesmo aviso.
    _venda_mensal(cenario, "2031-05", 5145, "kg")
    r = _res(cenario, "2031-05-01", "2031-05-31")
    assert r["atual"]["litros"] == 5000.0 and r["atual"]["fonte_litros"] == FONTE_VENDA_MENSAL
    assert any(f"Nota {n} sem unidade" in x for x in r["avisos_fonte_litros"])
    assert any("estimados pela Venda mensal" in x for x in r["avisos_fonte_litros"])


def test_item_so_na_conta_do_leite_sem_item_de_estoque_marcado_tambem_nao_chuta(cenario):  # noqa: F811
    n = _nota(cenario, "2031-05-31", "Leite do laticínio", 8000, 16000)["numero_lancamento"]
    cenario.ligar_regras_v2()
    r = _res(cenario, "2031-05-01", "2031-05-31")
    assert r["atual"]["litros"] == 0.0 and any(f"Nota {n} sem unidade" in x for x in r["avisos_fonte_litros"])


def test_item_de_leite_sem_quantidade_deixa_o_mes_na_reserva(cenario):  # noqa: F811
    _estoque(cenario, LEITE, "L", produto_leite=True)
    _nota(cenario, "2031-05-10", LEITE, 4000, 8000, nome="A")
    n = _nota(cenario, "2031-05-31", LEITE, None, 8000, nome="B")["numero_lancamento"]
    _venda_mensal(cenario, "2031-05", 8232, "kg")  # 8.000 L
    cenario.ligar_regras_v2()
    r = _res(cenario, "2031-05-01", "2031-05-31")
    # 4.000 L de uma nota só contra R$ 16.000 de receita inflaria o preço: o mês vai para a reserva.
    assert r["atual"]["fonte_litros"] == FONTE_VENDA_MENSAL and r["atual"]["litros"] == 8000.0
    assert any(f"Nota {n} sem quantidade" in x for x in r["avisos_fonte_litros"])


def test_quantidade_zero_de_proposito_e_neutra(cenario):  # noqa: F811
    """Bonificação lançada com quantidade 0 só traz valor: soma na receita, não trava o mês."""
    _estoque(cenario, LEITE, "L", produto_leite=True)
    _nota(cenario, "2031-05-10", LEITE, 4000, 8000, nome="A")
    _nota(cenario, "2031-05-31", "Bonificação por qualidade", 0, 500, nome="B")
    cenario.ligar_regras_v2()
    a = _res(cenario, "2031-05-01", "2031-05-31")["atual"]
    assert a["litros"] == 4000.0 and a["fonte_litros"] == FONTE_NOTA


def test_leite_de_dieta_nao_contamina_a_venda(cenario):  # noqa: F811
    # "Leite" é INGREDIENTE de dieta dos bezerros (não marcado); o de venda é outro item.
    _estoque(cenario, "Leite", "L", finalidade="Ração/Alimento")
    _estoque(cenario, LEITE, "L", produto_leite=True)
    _nota(cenario, "2031-05-31", LEITE, 6000, 12000, nome="LAT")
    # Compra do ingrediente (despesa) e um "Leite" em receita de outra conta: nenhum é venda ao laticínio.
    _nota(cenario, "2031-05-12", "Leite", 300, 600, conta="8.2", tipo="despesa", nome="COMPRA")
    _nota(cenario, "2031-05-20", "Leite", 100, 200, conta="8.3", nome="OUTRA")
    cenario.ligar_regras_v2()
    r = _res(cenario, "2031-05-01", "2031-05-31")
    assert r["atual"]["litros"] == 6000.0 and r["atual"]["fonte_litros"] == FONTE_NOTA
    assert r["avisos_fonte_litros"] == []


def test_leite_de_dieta_nao_empresta_unidade_para_a_nota(cenario):  # noqa: F811
    _estoque(cenario, "Leite", "L", finalidade="Ração/Alimento")  # a dieta tem unidade L, mas não é o de venda
    n = _nota(cenario, "2031-05-31", "Leite", 777, 1554)["numero_lancamento"]  # conta 8.1 (receita do leite)
    cenario.ligar_regras_v2()
    r = _res(cenario, "2031-05-01", "2031-05-31")
    assert r["atual"]["litros"] == 0.0 and any(f"Nota {n} sem unidade" in x for x in r["avisos_fonte_litros"])


def test_item_reconhecido_so_pelo_estoque_em_conta_nao_marcada_avisa(cenario):  # noqa: F811
    _estoque(cenario, LEITE, "L", produto_leite=True)
    n = _nota(cenario, "2031-05-31", LEITE, 6000, 12000, conta="8.3")["numero_lancamento"]
    cenario.ligar_regras_v2()
    r = _res(cenario, "2031-05-01", "2031-05-31")
    assert r["atual"]["litros"] == 6000.0
    assert any(f"Nota {n}" in x and "Receita do leite" in x for x in r["avisos_fonte_litros"])


def test_regime_caixa_leva_o_litro_junto_com_o_dinheiro(cenario):  # noqa: F811
    """Nota de setembro (competência) paga em outubro: no regime de competência o litro e a
    receita ficam em setembro; no de caixa, os dois em outubro — o preço por litro não mistura."""
    _estoque(cenario, LEITE, "L", produto_leite=True)
    n = _nota(cenario, "2031-09-30", LEITE, 9000, 18000)
    cenario.ligar_regras_v2()
    cenario.put(f"/financeiro/lancamentos/{n['ids'][0]}/pagar",
                {"data_pagamento": "2031-10-15", "valor_pago": 18000, "conta_bancaria": BANCO, "forma_pagamento": "pix"})

    comp_set = _res(cenario, "2031-09-01", "2031-09-30", regime="competencia")["atual"]
    comp_out = _res(cenario, "2031-10-01", "2031-10-31", regime="competencia")["atual"]
    assert (comp_set["litros"], comp_set["preco_bruto_l"]) == (9000.0, 2.0)
    assert (comp_out["litros"], comp_out["receita_leite_bruta"]) == (0.0, 0.0)

    cx_set = _res(cenario, "2031-09-01", "2031-09-30", regime="caixa")["atual"]
    cx_out = _res(cenario, "2031-10-01", "2031-10-31", regime="caixa")["atual"]
    assert (cx_set["litros"], cx_set["receita_leite_bruta"]) == (0.0, 0.0)
    assert (cx_out["litros"], cx_out["preco_bruto_l"], cx_out["fonte_litros"]) == (9000.0, 2.0, FONTE_NOTA)


def test_regime_caixa_nota_parcelada_reparte_o_litro_pelas_parcelas_pagas(cenario):  # noqa: F811
    _estoque(cenario, LEITE, "L", produto_leite=True)
    n = _nota(cenario, "2031-09-30", LEITE, 9000, 18000, parcelas=[
        {"data_vencimento": "2031-10-15", "valor": 9000}, {"data_vencimento": "2031-11-15", "valor": 9000}])
    cenario.ligar_regras_v2()
    ids = n["ids"]
    assert len(ids) == 2
    cenario.put(f"/financeiro/lancamentos/{ids[0]}/pagar",
                {"data_pagamento": "2031-10-15", "valor_pago": 9000, "conta_bancaria": BANCO, "forma_pagamento": "pix"})
    # Só a 1ª parcela (metade do valor) foi paga: a metade do litro está em outubro, o resto ainda não.
    out = _res(cenario, "2031-10-01", "2031-10-31", regime="caixa")["atual"]
    assert out["litros"] == 4500.0 and out["preco_bruto_l"] == 2.0
    # Em competência, a nota inteira é de setembro.
    assert _res(cenario, "2031-09-01", "2031-09-30")["atual"]["litros"] == 9000.0


def test_flag_desligada_nada_muda_e_as_chaves_novas_nem_existem(cenario):  # noqa: F811
    _estoque(cenario, LEITE, "L", produto_leite=True)
    _venda_mensal(cenario, "2031-05", 10320, "kg")
    _nota(cenario, "2031-05-31", LEITE, 20000, 40000, nome="MAI")
    mai = {"data_inicio": "2031-05-01", "data_fim": "2031-05-31"}
    r = cenario.get("/financeiro/resultado-por-litro", **mai, serie_meses=2)
    # Os litros seguem sendo o campo cru da Venda mensal (10.320 kg contam como 10.320), a nota é ignorada.
    assert r["atual"]["litros"] == 10320.0
    novas = {"fonte_litros", "litros_por_fonte", "pct_litros_estimados", "meses_litros", "avisos_fonte_litros"}
    for ind in (r["atual"], *r["serie"], r):
        assert novas.isdisjoint(ind)
    assert "tem_nota_leite" not in r["configuracao"]
    assert r["avisos"] == ["Entregas lançadas em kg contam como litros enquanto as regras novas dos relatórios estiverem desligadas."]
    cl = cenario.get("/financeiro/custo-litro-leite", **mai)
    assert cl["litros"] == 10320.0 and novas.isdisjoint(cl) and "regras_v2" not in cl
    preco = cenario.get("/financeiro/rmca", **mai)["preco_medio_litro_leite"]
    assert preco["litros"] == 10029.2 and "fonte_litros" not in preco  # RMCA já convertia kg → L: não mudou
    # Ligada, a mesma nota passa a mandar.
    cenario.ligar_regras_v2()
    assert cenario.get("/financeiro/resultado-por-litro", **mai)["atual"]["litros"] == 20000.0


def test_preco_medio_do_litro_do_rmca_usa_a_nota_com_a_flag(cenario):  # noqa: F811
    _estoque(cenario, LEITE, "L", produto_leite=True)
    _nota(cenario, "2031-07-31", LEITE, 8000, 20000)
    _venda_mensal(cenario, "2031-08", 10290, "kg")  # reserva mais recente, mas sem receita no mês
    cenario.ligar_regras_v2()
    p = cenario.get("/financeiro/rmca", data_inicio="2031-07-01", data_fim="2031-08-31")["preco_medio_litro_leite"]
    # Agosto tem litros (reserva) mas não tem receita: a conta não fecha ali; o preço de julho vem da nota.
    assert p is None
    p = cenario.get("/financeiro/rmca", data_inicio="2031-07-01", data_fim="2031-07-31")["preco_medio_litro_leite"]
    assert p is None  # o mais recente continua sendo agosto (reserva) — comportamento de "competência mais recente"
    _nota(cenario, "2031-08-31", LEITE, 9000, 22500, nome="AGO")
    p = cenario.get("/financeiro/rmca", data_inicio="2031-08-01", data_fim="2031-08-31")["preco_medio_litro_leite"]
    assert p["competencia"] == "2031-08" and p["fonte_litros"] == FONTE_NOTA
    assert p["litros"] == 9000.0 and p["preco_por_litro"] == 2.5


def test_isolamento_entre_fazendas(cenario):  # noqa: F811
    # Fazenda 1: o item de estoque NÃO está marcado — a marcação da fazenda 2 não vaza para ela.
    _estoque(cenario, LEITE, "L", produto_leite=False, fazenda_id=1)
    _estoque(cenario, LEITE, "L", produto_leite=True, fazenda_id=2)
    n1 = _nota(cenario, "2031-05-31", LEITE, 4000, 8000, nome="F1")["numero_lancamento"]
    cenario.ligar_regras_v2(1)
    cenario.ligar_regras_v2(2)

    cenario.estado["fazenda_id"] = 2
    r = cenario.c.post("/financeiro/plano-contas", json={"codigo": "8.1", "nome": "F2 Venda de leite", "ativa": True, "rmca_receita_leite": True})
    assert r.status_code == 200, r.text
    cenario.put("/financeiro/plano-contas/8.1/linha-dre", {"linha_dre": "RECEITA_VENDAS"})
    _nota(cenario, "2031-05-31", LEITE, 1000, 3000, nome="F2")
    r2 = _res(cenario, "2031-05-01", "2031-05-31")
    assert r2["atual"]["litros"] == 1000.0 and r2["atual"]["preco_bruto_l"] == 3.0  # só a nota dela
    assert r2["avisos_fonte_litros"] == []

    cenario.estado["fazenda_id"] = 1
    r1 = _res(cenario, "2031-05-01", "2031-05-31")
    assert r1["atual"]["litros"] == 0.0 and r1["atual"]["fonte_litros"] == FONTE_SEM_DADO
    assert any(f"Nota {n1} sem unidade" in x for x in r1["avisos_fonte_litros"])


# ---------------------------------------------------------------------------
# Cadastro do item de estoque e endpoint de uso
# ---------------------------------------------------------------------------
def test_cadastro_do_item_guarda_a_marca_de_produto_de_leite(cenario):  # noqa: F811
    c = cenario.c
    r = c.post("/estoque/", json={"nome": LEITE, "unidade": "L", "produto_leite": True, "estocavel": False})
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["produto_leite"] is True
    r = c.post("/estoque/", json={"nome": "Leite", "unidade": "L"})
    assert r.json()["produto_leite"] is False
    # PUT de um cliente que não conhece o campo não apaga a marcação; explícito, muda.
    base = {"nome": LEITE, "unidade": "L", "estocavel": False}
    assert c.put(f"/estoque/{item['id']}", json=base).json()["produto_leite"] is True
    assert c.put(f"/estoque/{item['id']}", json={**base, "produto_leite": False}).json()["produto_leite"] is False
    listado = {i["nome"]: i["produto_leite"] for i in c.get("/estoque/").json()["itens"]}
    assert listado[LEITE] is False and listado["Leite"] is False


def _uso(cenario, **q):  # noqa: F811
    return cenario.get("/estoque/uso-por-produto", **q)


def test_uso_por_produto_mostra_quem_esta_sem_uso_e_a_regra_do_delete(cenario):  # noqa: F811
    leite_dieta = _estoque(cenario, "Leite", "L", finalidade="Ração/Alimento")
    venda = _estoque(cenario, LEITE, "L", produto_leite=True)
    with Session(cenario.engine) as s:
        alimento = Alimento(nome="Leite integral", fazenda_id=1, estoque_preferido_id=leite_dieta)
        s.add(alimento)
        s.commit()
        s.refresh(alimento)
        dieta = DietaLancamento(lote=6, data_abertura=date(2031, 1, 1), fazenda_id=1)
        s.add(dieta)
        s.commit()
        s.refresh(dieta)
        s.add(DietaItemProgramado(dieta_lancamento_id=dieta.id, alimento="Leite", alimento_id=alimento.id, quantidade=4, unidade="L", fazenda_id=1))
        s.add(MovimentoEstoque(nome_item="Leite", movimento="Saída de ajuste", quantidade=10, unidade="L",
                               data_movimento=date(2031, 1, 5), estoque_id=leite_dieta, fazenda_id=1))
        s.commit()
    _nota(cenario, "2031-05-12", "Leite", 300, 600, conta="8.2", tipo="despesa", nome="COMPRA")

    dieta_uso = _uso(cenario, nome="leite ")["itens"]  # sem diferenciar caixa/espaços
    assert [i["id"] for i in dieta_uso] == [leite_dieta]
    u = dieta_uso[0]
    assert u["lancamentos"]["itens"] == 1 and u["lancamentos"]["por_tipo"] == {"despesa": 1}
    assert u["movimentos"]["vinculados"] >= 1
    assert u["dieta"]["estoque_preferido_de"] == [{"id": u["dieta"]["estoque_preferido_de"][0]["id"], "nome": "Leite integral"}]
    assert u["dieta"]["itens_de_dieta"] == 1 and u["dieta"]["dietas"] == 1
    assert u["pode_excluir"] is False and u["sem_uso"] is False
    assert {b["codigo"] for b in u["bloqueios_exclusao"]} >= {"movimentos", "estoque_preferido"}
    # A regra é a MESMA do DELETE: a mensagem do 1º bloqueio é o 409 devolvido.
    r = cenario.c.delete(f"/estoque/{leite_dieta}")
    assert r.status_code == 409 and r.json()["detail"] == u["bloqueios_exclusao"][0]["mensagem"]

    # O de venda ao laticínio, nunca lançado: sem uso nenhum — e a consulta NÃO excluiu nada.
    v = _uso(cenario, nome=LEITE)["itens"][0]
    assert v["id"] == venda and v["produto_leite"] is True
    assert (v["lancamentos"]["itens"], v["movimentos"]["vinculados"], v["dieta"]["itens_de_dieta"]) == (0, 0, 0)
    assert v["pode_excluir"] is True and v["sem_uso"] is True and v["bloqueios_exclusao"] == []
    with Session(cenario.engine) as s:
        assert len(s.exec(select(Estoque).where(Estoque.fazenda_id == 1)).all()) == 2

    # Depois de uma nota de venda, deixa de estar "sem uso" (embora o DELETE só olhe movimentos/preferido/mesclagem).
    _nota(cenario, "2031-05-31", LEITE, 6000, 12000)
    v = _uso(cenario, estoque_id=venda)["itens"][0]
    assert v["lancamentos"]["itens"] == 1 and v["lancamentos"]["por_tipo"] == {"receita": 1}
    assert v["lancamentos"]["ultima_competencia"] == "2031-05-31"
    assert v["sem_uso"] is False and v["pode_excluir"] is True


def test_uso_por_produto_exige_filtro_e_respeita_a_fazenda(cenario):  # noqa: F811
    r = cenario.c.get("/estoque/uso-por-produto")
    assert r.status_code == 422
    _estoque(cenario, LEITE, "L", produto_leite=True, fazenda_id=2)
    achado = _uso(cenario, nome=LEITE)
    assert achado["encontrado"] is False and achado["itens"] == []
    outro_id = _estoque(cenario, "Leite", "L", fazenda_id=2)
    assert _uso(cenario, estoque_id=outro_id)["itens"] == []  # id de outra fazenda: nada
    cenario.estado["fazenda_id"] = 2
    assert _uso(cenario, nome=LEITE)["encontrado"] is True
    cenario.estado["fazenda_id"] = 1
