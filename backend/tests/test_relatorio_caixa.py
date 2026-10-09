"""
Relatórios do grupo CAIXA (Fase C1) — `GET /financeiro/caixa-real/folego`,
`/fluxo-caixa-mensal` e `/livro-caixa-rural`, e o motor puro
fazenda/rules/relatorio_caixa.py.

O que estes testes travam:
- flag `financeiro_regras_v2` DESLIGADA: o Fluxo e o Livro saem com os números
  das telas antigas (que somavam a lista de lançamentos no navegador: data de
  pagamento, `valor_pago` ou o valor da parcela);
- flag LIGADA: o Fluxo pela data de caixa (agendado vira previsto) e o Livro
  com a regra fiscal (receita bruta, investimento como despesa, financiamento
  e aporte fora), com a ponte para a DRE de caixa fechando no centavo;
- o saldo do fôlego é o MESMO do Caixa real; isolamento por fazenda.
"""
from __future__ import annotations

from datetime import date

import pytest

from fazenda.rules.relatorio_caixa import (
    classificar_registro_livro, fluxo_de_caixa, folego, meses_entre, montar_livro, repartir_por_itens,
)
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário da auditoria)


# ── Motor puro ───────────────────────────────────────────────────────────
def test_meses_entre_vira_o_ano():
    assert meses_entre(date(2030, 11, 15), date(2031, 2, 1)) == ["2030-11", "2030-12", "2031-01", "2031-02"]
    assert meses_entre(date(2031, 2, 1), date(2031, 1, 1)) == []


def test_folego_nao_inventa_media_nem_dia_negativo():
    f = folego(9000.0, 2700.0, 90)
    assert (f["saida_media_diaria"], f["folego_dias"]) == (30.0, 300)
    assert folego(9000.0, 0.0, 90)["folego_dias"] is None, "sem saída na janela não há média"
    assert folego(-500.0, 2700.0, 90)["folego_dias"] == 0


def test_fluxo_agrupa_por_mes_dia_e_conta_e_separa_previsto():
    mv = [
        {"data": date(2031, 3, 5), "tipo": "receita", "valor": 1000.0, "codigo": "8.1", "conta": "8.1 Leite"},
        {"data": date(2031, 3, 5), "tipo": "despesa", "valor": 300.0, "codigo": "8.2", "conta": "8.2 Ração"},
        {"data": date(2031, 4, 2), "tipo": "despesa", "valor": 200.0, "previsto": True, "vencido": True},
        {"data": date(2031, 5, 9), "tipo": "despesa", "valor": 999.0},  # fora do período
    ]
    r = fluxo_de_caixa(mv, date(2031, 3, 1), date(2031, 4, 30), date(2031, 4, 2), por_dia=True)
    mar, abr = r["meses"]
    assert (mar["entradas"], mar["saidas"], mar["sobra"], mar["situacao"]) == (1000.0, 300.0, 700.0, "realizado")
    assert (abr["previsto_saidas"], abr["vencidos"], abr["sobra"], abr["sobra_prevista"], abr["situacao"]) == (200.0, 200.0, 0.0, -200.0, "em_curso")
    assert r["totais"]["sobra_prevista"] == 500.0 and r["meses_com_movimento"] == 2
    assert [c["codigo"] for c in r["contas"]] == ["8.1", "8.2"], "previsto não entra no detalhe por conta"
    assert [(d["data"], d["acumulado"]) for d in r["dias"]] == [("2031-03-05", 700.0), ("2031-04-02", 500.0)]


def test_repartir_por_itens_fecha_no_centavo():
    partes = repartir_por_itens(100.0, [("8.2", "Ração", 1.0), ("8.7", "Frete", 2.0), ("x", "zero", 0.0)])
    assert [p[0] for p in partes] == ["8.2", "8.7"] and round(sum(p[2] for p in partes), 2) == 100.0
    assert repartir_por_itens(10.0, [("a", None, 0.0)]) == []


def test_livro_cronologico_receita_antes_de_despesa_com_saldo_e_meses():
    lv = montar_livro([
        {"id": 3, "data": date(2031, 3, 10), "custeio": 400.0},
        {"id": 2, "data": date(2031, 3, 10), "receita": 1000.0},
        {"id": 1, "data": date(2031, 4, 1), "investimento": 900.0, "custeio": 100.0},
        {"id": 9, "data": date(2031, 4, 2), "custeio": 0.0},  # tudo fora: não vira linha
    ], date(2031, 3, 1), date(2031, 5, 31))
    assert [(x["id"], x["saldo"]) for x in lv["linhas"]] == [(2, 1000.0), (3, 600.0), (1, -400.0)]
    assert [(m["competencia"], m["resultado"]) for m in lv["meses"]] == [("2031-03", 600.0), ("2031-04", -1000.0), ("2031-05", 0.0)]
    assert lv["totais"] == {"receitas": 1000.0, "custeio": 500.0, "investimentos": 900.0, "despesas": 1400.0, "resultado": -400.0, "quantidade": 3}


def test_classificacao_fiscal_dos_registros():
    reg = lambda **k: {"valor": 100.0, "tipo": "despesa", "tipo_nota": "despesa", "natureza": "OPERACIONAL", **k}  # noqa: E731
    assert classificar_registro_livro(reg(), True) == ("custeio", -100.0)
    assert classificar_registro_livro(reg(), False) == ("sem_conta", -100.0)
    assert classificar_registro_livro(reg(natureza="INVESTIMENTO"), True) == ("investimento", -100.0)
    assert classificar_registro_livro(reg(natureza="FINANCIAMENTO"), True) == ("FINANCIAMENTO", -100.0)
    assert classificar_registro_livro(reg(tipo="receita", tipo_nota="receita"), True) == ("receita", 100.0)
    assert classificar_registro_livro(reg(origem="deducao_nota", tipo_nota="receita"), True) == ("deducao", -100.0)
    # Desconto obtido na baixa (tipo receita numa nota de despesa) abate a despesa.
    assert classificar_registro_livro(reg(tipo="receita"), True) == ("custeio", 100.0)


# ── Endpoints sobre o cenário da auditoria ───────────────────────────────
MAR_ABR = {"data_inicio": "2031-03-01", "data_fim": "2031-04-30"}


def _lancamentos(cenario):  # noqa: F811
    return cenario.get("/financeiro/lancamentos")["lancamentos"]


def _realizado(l):
    return l["valor_pago"] if l["valor_pago"] is not None else l["valor"]


def test_fluxo_flag_desligada_tem_os_numeros_do_fluxo_antigo(cenario):  # noqa: F811
    """O Fluxo antigo (page.tsx: fluxoMensal) somava `valorRealizado` por
    `mes_caixa` das notas com data de pagamento no período."""
    r = cenario.get("/financeiro/fluxo-caixa-mensal", **MAR_ABR, hoje="2031-12-31")
    assert r["regras_v2"] is False
    antigo: dict[str, list[float]] = {}
    for l in _lancamentos(cenario):
        if l["data_pagamento"] and MAR_ABR["data_inicio"] <= l["data_pagamento"] <= MAR_ABR["data_fim"]:
            b = antigo.setdefault(l["mes_caixa"], [0.0, 0.0])
            b[0 if l["tipo"] == "receita" else 1] += _realizado(l)
    for m in r["meses"]:
        e, s = antigo.get(m["competencia"], [0.0, 0.0])
        assert (m["entradas"], m["saidas"]) == (round(e, 2), round(s, 2)), m["competencia"]
    assert r["totais"]["entradas"] > 0 and r["totais"]["saidas"] > 0
    # O detalhe por conta fecha com o total realizado.
    assert round(sum(c["entradas"] for c in r["contas"]), 2) == r["totais"]["entradas"]
    assert round(sum(c["saidas"] for c in r["contas"]), 2) == r["totais"]["saidas"]


def test_fluxo_flag_ligada_agendado_e_previsto(cenario):  # noqa: F811
    cenario.ligar_regras_v2()
    # Hoje = 13/04/2031: L1 (recebido em 15/04) e L7 (pago em 20/04) ainda são agendados.
    r = cenario.get("/financeiro/fluxo-caixa-mensal", **MAR_ABR, hoje="2031-04-13", por_dia="true")
    assert r["regras_v2"] is True
    mar, abr = r["meses"]
    assert mar["situacao"] == "realizado" and abr["situacao"] == "em_curso"
    assert abr["previsto_entradas"] >= 9850.0, "o recebimento do leite (agendado) é previsto, não realizado"
    assert r["agendado_no_periodo"] >= 9850.0 + 600.0
    # Dia a dia fecha com o mês.
    soma_dias = round(sum(d["sobra"] for d in r["dias"]), 2)
    assert soma_dias == r["totais"]["sobra_prevista"]
    # Centro que não existe: nada.
    vazio = cenario.get("/financeiro/fluxo-caixa-mensal", **MAR_ABR, centro_custo="Lavoura", hoje="2031-04-13")
    assert vazio["totais"]["entradas"] == vazio["totais"]["saidas"] == vazio["totais"]["previsto_saidas"] == 0.0


def test_fluxo_recusa_periodo_invertido(cenario):  # noqa: F811
    r = cenario.c.get("/financeiro/fluxo-caixa-mensal", params={"data_inicio": "2031-04-30", "data_fim": "2031-03-01"})
    assert r.status_code == 422


def test_livro_flag_desligada_e_o_livro_antigo(cenario):  # noqa: F811
    r = cenario.get("/financeiro/livro-caixa-rural", **MAR_ABR)
    assert r["separacao_fiscal"] is False and r["ponte_dre"] is None and r["presumido_20"] is None
    pagos = [l for l in _lancamentos(cenario) if l["data_pagamento"] and MAR_ABR["data_inicio"] <= l["data_pagamento"] <= MAR_ABR["data_fim"]]
    rec = round(sum(_realizado(l) for l in pagos if l["tipo"] == "receita"), 2)
    des = round(sum(_realizado(l) for l in pagos if l["tipo"] != "receita"), 2)
    assert (r["totais"]["receitas"], r["totais"]["despesas"]) == (rec, des)
    assert len(r["linhas"]) == len([l for l in pagos if _realizado(l)])
    datas = [x["data"] for x in r["linhas"]]
    assert datas == sorted(datas)
    assert r["linhas"][-1]["saldo"] == r["totais"]["resultado"]


def test_livro_flag_ligada_regra_fiscal_e_ponte_com_a_dre(cenario):  # noqa: F811
    cenario.ligar_regras_v2()
    r = cenario.get("/financeiro/livro-caixa-rural", **MAR_ABR)
    t = r["totais"]
    assert r["separacao_fiscal"] is True
    # Trator (L8, 120.000) é investimento pago — despesa no mês, sem depreciação.
    assert t["investimentos"] == 120000.0
    # Leite pela receita BRUTA (10.000; o Funrural/Senar de 150 não é despesa paga); aporte (L5) fora.
    assert t["receitas"] == 10000.0
    assert r["presumido_20"] == 2000.0
    naturezas = {g["natureza"] for g in r["fora_do_livro"]["grupos"]}
    assert "NAO_INFORMADA" in naturezas, "principal (8.4) e aporte (8.5) sem natureza informada ficam fora"
    assert all(l["categoria"] in ("receita", "custeio", "investimento", "misto") for l in r["linhas"])
    p = r["ponte_dre"]
    dre = cenario.dre(MAR_ABR["data_inicio"], MAR_ABR["data_fim"], regime="caixa")
    assert p["resultado_dre"] == dre["resumo"]["resultado_liquido"]
    assert p["fecha"] is True, p
    assert p["reconstruido"] == t["resultado"]


def test_folego_usa_o_saldo_do_caixa_real(cenario):  # noqa: F811
    for ligar in (False, True):
        if ligar:
            cenario.ligar_regras_v2()
        f = cenario.get("/financeiro/caixa-real/folego")
        cx = cenario.get("/financeiro/caixa-real")
        assert f["saldo_hoje"] == cx["saldo_inicial"], ligar
        assert f["dias_janela"] == 90 and f["regras_v2"] is ligar


@pytest.mark.parametrize("caminho,params", [
    ("/financeiro/fluxo-caixa-mensal", {**MAR_ABR, "hoje": "2031-12-31"}),
    ("/financeiro/livro-caixa-rural", MAR_ABR),
])
def test_isolamento_outra_fazenda_nao_ve_nada(cenario, caminho, params):  # noqa: F811
    cenario.estado["fazenda_id"] = 2
    r = cenario.get(caminho, **params)
    assert r["totais"]["entradas" if "fluxo" in caminho else "receitas"] == 0.0
    assert r.get("linhas", []) == [] and r.get("contas", []) == []
    f = cenario.get("/financeiro/caixa-real/folego")
    assert f["saldo_hoje"] == 0.0 and f["saidas_janela"] == 0.0
