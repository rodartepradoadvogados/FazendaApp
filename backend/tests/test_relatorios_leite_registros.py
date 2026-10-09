"""
Fase C dos Relatórios — grupos Leite e Registros:
- GET /financeiro/custos-leite (COE → COT → CT, CNA/Embrapa);
- GET /financeiro/rmca-vaca (sobra da comida por vaca/dia, 12 meses, por lote);
- GET /relatorio-compra-venda-animais/resumo (por cabeça, categoria e natureza);
- GET /relatorio-compra-semen/resumo (custo do sêmen por prenhez);
e as contas puras de fazenda/rules/relatorio_leite.py.

O princípio é o da Fase B: nada de número novo de custo. Cada endpoint parte do
que a tela anterior (ou o Resultado por litro) já mostrava e os testes conferem
que a base é a MESMA, com a flag `financeiro_regras_v2` ligada e desligada.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session

from fazenda.models import Animal, CompraAnimal, CompraSemen, ContaGerencial, ControleLeiteiro, Servico, VendaAnimal
from fazenda.rules.relatorio_leite import (
    eh_inseminacao, estimativas_custo_leite, media_ponderada_por_litro, preco_medio_dose, rmca_por_vaca_dia,
    semen_por_prenhez, vaca_dias,
)
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário da auditoria)

MAR = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}


# ── Contas puras ─────────────────────────────────────────────────────────────
def test_estimativas_sem_parametro_nao_inventam_numero():
    e = estimativas_custo_leite(coe=8500.0, depreciacao=500.0, litros=5000.0, meses=1.0, familia_mes=0,
                                taxa_capital_aa=6.0, capital_rebanho=0, capital_maquinas=0, capital_terra=0)
    # Sem família: o COT é o custo total do Resultado por litro (custeio + depreciação).
    assert (e["cot"], e["cot_l"], e["familia_l"]) == (9000.0, 1.8, 0.0)
    assert e["familia_informada"] is False and e["capital_informado"] is False
    # Sem capital informado não existe CT (a tela diz o que falta).
    assert e["ct"] is None and e["ct_l"] is None and e["retorno_capital_l"] is None


def test_estimativas_com_familia_e_capital():
    e = estimativas_custo_leite(coe=8500.0, depreciacao=500.0, litros=5000.0, meses=3.0, familia_mes=1000,
                                taxa_capital_aa=6.0, capital_rebanho=600000, capital_maquinas=400000, capital_terra=0)
    # Família 1.000 × 3 meses; capital 1.000.000 × 6% × 3/12 = 15.000.
    assert (e["familia_periodo"], e["retorno_capital_periodo"]) == (3000.0, 15000.0)
    assert (e["cot"], e["ct"]) == (12000.0, 27000.0)
    assert (e["cot_l"], e["ct_l"], e["retorno_capital_l"]) == (2.4, 5.4, 3.0)
    assert e["capital_total"] == 1000000.0
    sem_litros = estimativas_custo_leite(coe=1.0, depreciacao=0, litros=0, meses=1, familia_mes=10, taxa_capital_aa=6,
                                         capital_rebanho=1, capital_maquinas=0, capital_terra=0)
    assert sem_litros["cot_l"] is None and sem_litros["ct_l"] is None and sem_litros["cot"] == 11.0


def test_media_ponderada_por_litro_ignora_mes_sem_leite():
    meses = [{"coe": 1000.0, "litros": 500.0}, {"coe": 3000.0, "litros": 1500.0}, {"coe": 900.0, "litros": 0.0}]
    assert media_ponderada_por_litro(meses, "coe") == 2.0
    assert media_ponderada_por_litro([], "coe") is None


def test_vaca_dias_por_mes_e_mes_parcial():
    controles = [("10", date(2031, 3, 5)), ("10", date(2031, 3, 20)), ("11", date(2031, 3, 5)), ("12", date(2031, 4, 2))]
    marco = vaca_dias(controles, date(2031, 3, 1), date(2031, 3, 31))
    assert (marco["vaca_dias"], marco["dias"], marco["vacas"], marco["vacas_media"]) == (62.0, 31, 2, 2.0)
    # 16 a 30/04: só a vaca 12 (controlada em abril), 15 dias.
    parcial = vaca_dias(controles, date(2031, 4, 16), date(2031, 4, 30))
    assert (parcial["vaca_dias"], parcial["dias"], parcial["vacas"]) == (15.0, 15, 1)
    vazio = vaca_dias([], date(2031, 3, 1), date(2031, 3, 31))
    assert vazio["vaca_dias"] == 0 and vazio["vacas_media"] == 0.0


def test_rmca_por_vaca_dia_bruta_com_liquida_ao_lado():
    r = rmca_por_vaca_dia(receita_bruta=10000.0, receita_liquida=9850.0, comida=4000.0, vaca_dias_total=200.0, litros=4000.0)
    assert (r["rmca"], r["rmca_liquida"]) == (6000.0, 5850.0)
    assert (r["receita_vaca_dia"], r["comida_vaca_dia"], r["rmca_vaca_dia"]) == (50.0, 20.0, 30.0)
    assert r["comida_receita_pct"] == 40.0 and r["litros_vaca_dia"] == 20.0
    sem_vacas = rmca_por_vaca_dia(receita_bruta=10000.0, receita_liquida=None, comida=4000.0, vaca_dias_total=0, litros=0)
    assert sem_vacas["rmca"] == 6000.0 and sem_vacas["rmca_vaca_dia"] is None and sem_vacas["rmca_liquida"] is None


def test_eh_inseminacao():
    assert eh_inseminacao("IA", None) and eh_inseminacao("Inseminação", None) and eh_inseminacao("Monta natural", "sexado")
    assert not eh_inseminacao("Monta natural", None) and not eh_inseminacao("IA", "fazenda") and not eh_inseminacao(None, None)
    assert not eh_inseminacao("Diagnóstico", None)


def test_preco_medio_dose_janela_de_12_meses_e_historico():
    compras = [
        {"data": date(2029, 1, 10), "doses": 10, "valor_unitario": 100.0},
        {"data": date(2030, 6, 1), "doses": 20, "valor_unitario": 40.0},
        {"data": date(2030, 9, 1), "doses": 20, "valor_unitario": 60.0},
    ]
    p = preco_medio_dose(compras, date(2031, 3, 31))
    assert (p["preco"], p["doses"], p["base"]) == (50.0, 40, "12_meses")
    antigo = preco_medio_dose(compras, date(2029, 12, 31))
    assert (antigo["preco"], antigo["base"]) == (100.0, "12_meses")
    assert preco_medio_dose(compras, date(2032, 12, 31))["base"] == "historico"
    assert preco_medio_dose([], date(2031, 1, 1)) == {"preco": None, "doses": 0, "valor": 0.0, "base": None}


def test_semen_por_prenhez_so_conta_inseminacao_diagnosticada():
    s = [
        {"data_servico": date(2031, 3, 2), "tipo_servico": "IA", "tipo_semen": "convencional", "diagnostico": "POSITIVO"},
        {"data_servico": date(2031, 3, 5), "tipo_servico": "IA", "tipo_semen": "sexado", "diagnostico": "NEGATIVO"},
        {"data_servico": date(2031, 3, 8), "tipo_servico": "IA", "tipo_semen": "convencional", "diagnostico": "POSITIVO"},
        {"data_servico": date(2031, 3, 28), "tipo_servico": "IA", "tipo_semen": "convencional", "diagnostico": None},
        {"data_servico": date(2031, 3, 9), "tipo_servico": "Monta natural", "tipo_semen": "fazenda", "diagnostico": "POSITIVO"},
        {"data_servico": date(2031, 2, 9), "tipo_servico": "IA", "tipo_semen": "convencional", "diagnostico": "POSITIVO"},
    ]
    r = semen_por_prenhez(s, 50.0, date(2031, 3, 1), date(2031, 3, 31))
    assert (r["inseminacoes"], r["diagnosticadas"], r["aguardando_diagnostico"], r["prenhezes"]) == (4, 3, 1, 2)
    # 3 doses diagnosticadas × R$ 50 ÷ 2 prenhezes (a monta não gasta dose; a de fevereiro é de outro período).
    assert (r["custo_semen_diagnosticadas"], r["custo_por_prenhez"], r["taxa_concepcao_pct"]) == (150.0, 75.0, 66.7)
    assert r["custo_semen_usado"] == 200.0
    sem_preco = semen_por_prenhez(s, None, date(2031, 3, 1), date(2031, 3, 31))
    assert sem_preco["custo_por_prenhez"] is None and sem_preco["prenhezes"] == 2


# ── Endpoints (cenário da auditoria) ─────────────────────────────────────────
@pytest.mark.parametrize("ligar", [False, True])
def test_custos_leite_reaproveita_o_resultado_por_litro(cenario, ligar):  # noqa: F811
    if ligar:
        cenario.ligar_regras_v2()
    q = {**MAR, "regime": "competencia", "centro_custo": "Pecuária Leiteira", "serie_meses": 3}
    r = cenario.get("/financeiro/custos-leite", **q)
    litro = cenario.get("/financeiro/resultado-por-litro", **q)
    assert r["litro"] == litro and r["regras_v2"] is ligar
    a, e = litro["atual"], r["estimativas"]
    # Sem parâmetros: COT = custo total do Resultado por litro; CT não existe.
    assert e["cot"] == a["cot"] and e["cot_l"] == a["cot_l"]
    assert e["ct"] is None and e["familia_informada"] is False
    assert [m["competencia"] for m in litro["serie"]] == ["2031-01", "2031-02", "2031-03"]
    # Regras antigas: a comida por litro é a da tela anterior (custo-litro-leite), não outra.
    if ligar:
        assert r["alimentacao_tela_anterior"] is None
    else:
        assert r["alimentacao_tela_anterior"] == cenario.get("/financeiro/custo-litro-leite", data_inicio=MAR["data_inicio"], data_fim=MAR["data_fim"])
    assert r["media_serie"]["coe_l"] == round(sum(m["coe"] for m in litro["serie"] if m["litros"]) / sum(m["litros"] for m in litro["serie"]), 4)


def test_custos_leite_usa_os_parametros_da_fazenda(cenario, monkeypatch):  # noqa: F811
    import fazenda.api.routers.relatorio_leite as rl

    valores = {"custo_remuneracao_familia_mensal": 2000.0, "custo_taxa_retorno_capital": 6.0,
               "custo_capital_rebanho": 500000.0, "custo_capital_maquinas": 300000.0, "custo_capital_terra": 0.0}
    monkeypatch.setattr(rl, "get_param", lambda chave, padrao=None: valores.get(chave, padrao))
    r = cenario.get("/financeiro/custos-leite", **MAR, serie_meses=0)
    a, e = r["litro"]["atual"], r["estimativas"]
    assert e["cot"] == round(a["coe"] + a["depreciacao"] + 2000.0, 2)
    assert e["ct"] == round(e["cot"] + 800000 * 0.06 / 12, 2)
    assert e["ct_l"] == round(e["ct"] / a["litros"], 4)


def test_custos_leite_recusa_periodo_invertido(cenario):  # noqa: F811
    r = cenario.c.get("/financeiro/custos-leite", params={"data_inicio": "2031-03-31", "data_fim": "2031-03-01"})
    assert r.status_code == 422


def _controles(engine, fazenda_id: int, linhas):
    with Session(engine) as s:
        for numero, dia, kg, lote in linhas:
            s.add(ControleLeiteiro(fazenda_id=fazenda_id, numero_matriz=numero, data_controle=dia, producao_kg=kg))
        for numero, lote in {(n, lt) for n, _d, _kg, lt in linhas}:
            s.add(Animal(fazenda_id=fazenda_id, numero=numero, grupo_primario=lote))
        s.commit()


@pytest.mark.parametrize("ligar", [False, True])
def test_rmca_vaca_parte_do_rmca_da_tela_anterior(cenario, ligar):  # noqa: F811
    if ligar:
        cenario.ligar_regras_v2()
    _controles(cenario.engine, 1, [
        ("101", date(2031, 3, 10), 30.0, "01 - Alta"), ("102", date(2031, 3, 10), 20.0, "01 - Alta"),
        ("201", date(2031, 3, 11), 15.0, "02 - Baixa"),
    ])
    # Outra fazenda: não pode entrar na conta (isolamento multi-tenant).
    _controles(cenario.engine, 2, [("901", date(2031, 3, 10), 40.0, "01 - Alta")])
    r = cenario.get("/financeiro/rmca-vaca", **MAR, serie_meses=2)
    base = cenario.get("/financeiro/rmca", **MAR)
    g, a = base["gerencial"], r["atual"]
    assert r["gerencial"] == g and r["regras_v2"] is ligar
    assert r["contas_custo_codigos"] == [{"codigo": "8.2", "nome": "AUD Ração concentrado"}]
    assert (a["receita_bruta"], a["comida"], a["rmca"]) == (g["receita_leite"], g["custo_alimentacao"], g["rmca"])
    assert (a["vacas"], a["vaca_dias"]) == (3, 93.0)
    assert a["rmca_vaca_dia"] == round(g["rmca"] / 93.0, 4)
    assert r["fisico"]["comida"] == base["fisico"]["custo_alimentacao"]
    assert a["receita_liquida"] == (g["receita_leite_liquida"] if ligar else None)
    assert [m["competencia"] for m in r["serie"]] == ["2031-02", "2031-03"]
    assert r["serie"][-1]["rmca"] == g["rmca"] and r["serie"][0]["vaca_dias"] == 0
    lotes = {x["lote"]: x for x in r["por_lote"]}
    assert set(lotes) == {"01 - Alta", "02 - Baixa"}
    assert lotes["01 - Alta"]["vacas"] == 2
    # Leite do lote 01: média 25 kg/vaca/dia (kg vira litro só com as regras novas).
    assert lotes["01 - Alta"]["leite_l_vaca_dia"] == (round(25 / 1.029, 2) if ligar else 25.0)
    # Sem consumo registrado por lote: a comida do lote fica sem número (não vira zero).
    assert lotes["01 - Alta"]["comida_vaca_dia"] is None and lotes["01 - Alta"]["rmca_vaca_dia"] is None


def test_rmca_vaca_sem_controle_avisa_e_nao_divide(cenario):  # noqa: F811
    r = cenario.get("/financeiro/rmca-vaca", **MAR, serie_meses=0)
    assert r["atual"]["vaca_dias"] == 0 and r["atual"]["rmca_vaca_dia"] is None
    assert r["atual"]["rmca"] == cenario.get("/financeiro/rmca", **MAR)["gerencial"]["rmca"]
    assert any("Controle leiteiro" in x for x in r["avisos"]) and r["por_lote"] == []


def _compra_venda(engine, fazenda_id: int = 1):
    with Session(engine) as s:
        s.add(ContaGerencial(fazenda_id=fazenda_id, numero_lancamento="LC-A1", tipo="despesa", codigo_conta="8.6",
                             centro_custo="Pecuária Leiteira", numero_nota="NF-10", valor_total=24000,
                             natureza_fin="INVESTIMENTO", data_competencia=date(2031, 3, 5)))
        s.add(ContaGerencial(fazenda_id=fazenda_id, numero_lancamento="LC-A2", tipo="despesa", codigo_conta="8.2",
                             centro_custo="Pecuária Leiteira", numero_nota="NF-11", valor_total=1800,
                             data_competencia=date(2031, 3, 6)))
        s.add(ContaGerencial(fazenda_id=fazenda_id, numero_lancamento="LC-V1", tipo="receita", codigo_conta="8.1",
                             centro_custo="Pecuária Leiteira", numero_nota="NF-20", valor_total=9000,
                             data_competencia=date(2031, 3, 20)))
        for n in ("A1", "A2"):
            s.add(CompraAnimal(fazenda_id=fazenda_id, numero_animal=n, vendedor="Faz. Boa", valor=12000, tipo_valor="total",
                               data_compra=date(2031, 3, 5), numero_lancamento_gerado="LC-A1", gta="G-1"))
        s.add(CompraAnimal(fazenda_id=fazenda_id, numero_animal="B1", vendedor="Recria SJ", valor=1800, tipo_valor="por_animal",
                           data_compra=date(2031, 3, 6), numero_lancamento_gerado="LC-A2"))
        for n in ("D1", "D2"):
            s.add(VendaAnimal(fazenda_id=fazenda_id, numero_animal=n, comprador="Frigorífico", valor=4500, tipo_valor="total",
                              data_venda=date(2031, 3, 20), categorias="vaca", numero_lancamento_gerado="LC-V1"))
        s.add(VendaAnimal(fazenda_id=fazenda_id, numero_animal="X9", comprador="Vizinho", valor=900, tipo_valor="por_animal",
                          data_venda=date(2031, 4, 2)))
        s.add(Animal(fazenda_id=fazenda_id, numero="A1", categoria_completa="Novilha"))
        s.add(Animal(fazenda_id=fazenda_id, numero="A2", categoria_completa="Novilha"))
        s.commit()


def test_compra_venda_resumo_por_cabeca_categoria_e_natureza(cenario):  # noqa: F811
    _compra_venda(cenario.engine, 1)
    _compra_venda(cenario.engine, 2)  # a outra fazenda não pode aparecer
    r = cenario.get("/relatorio-compra-venda-animais/resumo", data_de="2031-03-01", data_ate="2031-03-31")
    t = r["totais"]
    assert (t["cab_compradas"], t["compras"], t["cab_vendidas"], t["vendas"], t["saldo"]) == (3, 25800.0, 2, 9000.0, -16800.0)
    assert (t["venda_por_cabeca"], t["compra_por_cabeca"]) == (4500.0, 8600.0)
    # Matriz comprada (natureza INVESTIMENTO) fica separada do custo operacional.
    assert (t["compras_investimento"], t["compras_operacionais"]) == (24000.0, 1800.0)
    cats = {x["categoria"]: x for x in r["por_categoria"]}
    assert cats["Vaca"]["cab_vendidas"] == 2 and cats["Vaca"]["venda_por_cabeca"] == 4500.0
    assert cats["Novilha"]["cab_compradas"] == 2 and cats["Novilha"]["compra_por_cabeca"] == 12000.0
    assert cats["Sem categoria"]["cab_compradas"] == 1
    nat = {x["natureza"]: x for x in r["por_natureza"]}
    assert nat["INVESTIMENTO"]["compras"] == 24000.0 and nat["OPERACIONAL"]["vendas"] == 9000.0
    assert {l["natureza_rotulo"] for l in r["linhas"] if l["numero_animal"] in ("A1", "A2")} == {"Investimentos (bens do imobilizado)"}
    # Venda sem lançamento (abril) fica fora do período; com centro, só o que tem lançamento daquele centro.
    assert all(l["numero_animal"] != "X9" for l in r["linhas"])
    outro_centro = cenario.get("/relatorio-compra-venda-animais/resumo", data_de="2031-03-01", data_ate="2031-04-30", centro_custo="Agricultura")
    assert outro_centro["linhas"] == []
    tudo = cenario.get("/relatorio-compra-venda-animais/resumo", data_de="2031-03-01", data_ate="2031-04-30")
    assert tudo["totais"]["sem_lancamento"] == 1
    # A lista de antes continua igual (com os campos novos a mais).
    antes = cenario.get("/relatorio-compra-venda-animais/", data_de="2031-03-01", data_ate="2031-03-31")
    assert len(antes) == 5 and all("natureza" in l and "categoria" in l for l in antes)


def test_compra_semen_resumo_custo_por_prenhez(cenario):  # noqa: F811
    with Session(cenario.engine) as s:
        s.add(ContaGerencial(fazenda_id=1, numero_lancamento="LC-S1", tipo="despesa", codigo_conta="8.2",
                             centro_custo="Pecuária Leiteira", numero_nota="NF-S1", valor_total=1000))
        s.add(CompraSemen(fazenda_id=1, estoque_semen_id=1, touro_nome="Coors", origem="estoque", doses=20,
                          valor_unitario=50.0, vendedor="Central", data_compra=date(2031, 3, 4), numero_lancamento_gerado="LC-S1"))
        s.add(CompraSemen(fazenda_id=2, estoque_semen_id=1, touro_nome="Outra", origem="estoque", doses=10,
                          valor_unitario=500.0, vendedor="Central", data_compra=date(2031, 3, 4)))
        for dia, diag in ((2, "POSITIVO"), (6, "NEGATIVO"), (9, "POSITIVO"), (29, None)):
            s.add(Servico(fazenda_id=1, numero_matriz=f"V{dia}", data_servico=date(2031, 3, dia), tipo_servico="IA",
                          tipo_semen="convencional", diagnostico=diag))
        s.add(Servico(fazenda_id=2, numero_matriz="Z", data_servico=date(2031, 3, 3), tipo_servico="IA",
                      tipo_semen="convencional", diagnostico="POSITIVO"))
        s.commit()
    r = cenario.get("/relatorio-compra-semen/resumo", data_de="2031-03-01", data_ate="2031-03-31", serie_meses=2)
    assert r["totais"] == {"gasto": 1000.0, "doses": 20, "compras": 1, "preco_medio_dose": 50.0, "sem_lancamento": 0}
    p = r["prenhez"]
    assert p["preco_dose"]["preco"] == 50.0
    assert (p["inseminacoes"], p["diagnosticadas"], p["prenhezes"], p["custo_por_prenhez"]) == (4, 3, 2, 75.0)
    assert r["linhas"][0]["natureza"] == "OPERACIONAL"
    assert [m["competencia"] for m in r["serie"]] == ["2031-02", "2031-03"]
    assert r["serie"][0]["inseminacoes"] == 0 and r["serie"][1]["custo_por_prenhez"] == 75.0
    assert len(cenario.get("/relatorio-compra-semen/")) == 1
