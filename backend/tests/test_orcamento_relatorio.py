"""
Plano › Orçamento (Fase C dos Relatórios) — `GET /planejamento/orcamento/relatorio`
(orçado × realizado conta a conta, por linha da DRE e em R$/L) e
`PUT /planejamento/orcamento-grade` (a planilha conta × 12 meses salva de uma vez).

O relatório não inventa número: com a flag `financeiro_regras_v2` desligada
devolve o comparativo antigo tal qual; ligada, o comparativo do PR 8 (mesmo
motor), o realizado de cada linha é o da DRE do servidor e o orçado por linha é
a mesma cascata montada com os valores orçados.
"""
from __future__ import annotations

from sqlmodel import Session, select

from fazenda.models import OrcamentoItem, Pedido
from fazenda.rules.orcamento import cascata_orcada, conferir_com_a_dre, por_linha_dre
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário da auditoria)

MAR = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}
REL = "/planejamento/orcamento/relatorio"


def _por_chave(xs, k="chave"):
    return {x[k]: x for x in xs}


# ── motor puro ────────────────────────────────────────────────────────────
def test_cascata_orcada_usa_o_motor_da_dre_e_a_depreciacao_do_patrimonio():
    mapa = {"1": "RECEITA_VENDAS", "2": "CUSTO_VARIAVEL", "3": "GASTOS_PESSOAL"}
    orcadas = {
        "1": {"tipo": "receita", "orcado": 1000.0}, "2": {"tipo": "despesa", "orcado": 300.0},
        "9": {"tipo": "despesa", "orcado": 50.0},  # sem linha da DRE (conta-grupo)
    }
    c = cascata_orcada(orcadas, mapa, 20.0)
    linhas = _por_chave(c["linhas"])
    assert (linhas["RECEITA_VENDAS"]["valor"], linhas["RECEITA_VENDAS"]["orcado"]) == (1000.0, True)
    assert (linhas["CUSTO_VARIAVEL"]["valor"], linhas["CUSTO_VARIAVEL"]["orcado"]) == (300.0, True)
    # Sem conta orçada na linha: não há plano (a tela não pinta desvio).
    assert linhas["GASTOS_PESSOAL"]["orcado"] is False
    # Depreciação: a do período, do Patrimônio — não é orçada, mas entra para os subtotais compararem.
    assert (linhas["DEPRECIACAO_AMORT_EXAUSTAO"]["valor"], linhas["DEPRECIACAO_AMORT_EXAUSTAO"]["origem"]) == (20.0, "patrimonio")
    assert linhas["RESULTADO_LIQUIDO"]["valor"] == 680.0
    assert c["sem_linha"]["total"] == 50.0


def test_por_linha_dre_sem_orcado_fica_none_e_reparte_por_litro():
    real = [{"chave": "RECEITA_VENDAS", "rotulo": "R", "operador": "+", "eh_subtotal": False, "valor": 900.0},
            {"chave": "GASTOS_PESSOAL", "rotulo": "P", "operador": "-", "eh_subtotal": False, "valor": 100.0}]
    orc = [{"chave": "RECEITA_VENDAS", "valor": 1000.0, "orcado": True, "origem": "orcamento"},
           {"chave": "GASTOS_PESSOAL", "valor": 0.0, "orcado": False, "origem": "orcamento"}]
    linhas = _por_chave(por_linha_dre(real, orc, 500.0))
    assert (linhas["RECEITA_VENDAS"]["orcado"], linhas["RECEITA_VENDAS"]["orcado_l"], linhas["RECEITA_VENDAS"]["realizado_l"]) == (1000.0, 2.0, 1.8)
    assert linhas["GASTOS_PESSOAL"]["orcado"] is None and linhas["GASTOS_PESSOAL"]["orcado_l"] is None
    sem_litros = _por_chave(por_linha_dre(real, orc, 0.0))
    assert sem_litros["RECEITA_VENDAS"]["realizado_l"] is None


# ── endpoint ──────────────────────────────────────────────────────────────
def test_flag_desligada_devolve_o_comparativo_antigo_tal_qual(cenario):  # noqa: F811
    r = cenario.get(REL, **MAR)
    antigo = cenario.get("/planejamento/orcamento/comparativo", ano=2031, mes_inicio=3, mes_fim=3)
    assert r["regras_v2"] is False and r["comparativo_antigo"] == antigo
    assert r["tem_orcamento"] is True and r["meses_com_orcamento"] == ["2031-03"]
    # Sem as regras novas não há linha da DRE nem R$/L: nada de número novo.
    assert "linhas_dre" not in r and "litro_orcado" not in r
    # Período que cruza o ano: a regra antiga não suporta — trava com o porquê, sem número.
    safra = cenario.get(REL, data_inicio="2030-07-01", data_fim="2031-06-30")
    assert safra["comparativo_antigo"] is None and "mesmo ano" in safra["travado"]


def test_flag_ligada_conta_a_conta_e_o_comparativo_do_pr8(cenario):  # noqa: F811
    cenario.ligar_regras_v2()
    r = cenario.get(REL, **MAR)
    pr8 = cenario.get("/planejamento/orcamento/comparativo", ano=2031, mes_inicio=3, mes_fim=3)
    assert r["totais"] == pr8["totais"]
    assert [{k: v for k, v in l.items() if k != "linha_dre"} for l in r["linhas"]] == pr8["linhas"]
    linhas = _por_chave(r["linhas"], "codigo_conta_gerencial")
    assert linhas["8.1"]["linha_dre"] == "RECEITA_VENDAS" and linhas["8.2"]["linha_dre"] == "CUSTO_VARIAVEL"
    assert linhas["8.4"]["linha_dre"] is None  # fora do resultado


def test_flag_ligada_por_linha_da_dre_realizado_e_o_da_dre(cenario):  # noqa: F811
    cenario.ligar_regras_v2()
    r = cenario.get(REL, **MAR)
    dre = cenario.dre()
    por_linha = _por_chave(r["linhas_dre"])
    for l in dre["cascata"]:
        assert por_linha[l["chave"]]["realizado"] == l["valor"], l["chave"]
    # Orçado: 8.1 receita 10.000 e 8.2 ração 5.000; o grupo "8" (2.000) não tem linha da DRE.
    assert por_linha["RECEITA_VENDAS"]["orcado"] == 10000 and por_linha["CUSTO_VARIAVEL"]["orcado"] == 5000
    assert por_linha["GASTOS_PESSOAL"]["orcado"] is None and por_linha["DESPESAS_OPERACIONAIS"]["orcado"] is None
    assert r["orcado_sem_linha"]["total"] == 2000
    dep = cenario.linha(dre, "DEPRECIACAO_AMORT_EXAUSTAO")
    assert (por_linha["DEPRECIACAO_AMORT_EXAUSTAO"]["orcado"], por_linha["DEPRECIACAO_AMORT_EXAUSTAO"]["origem_orcado"]) == (dep, "patrimonio")
    assert por_linha["RESULTADO_LIQUIDO"]["orcado"] == round(10000 - 5000 - dep, 2)
    # R$/L com os litros entregues (10.320 kg ÷ 1,029, o mesmo do Resultado por litro).
    litro = cenario.get("/financeiro/resultado-por-litro", **MAR)["atual"]
    assert r["litros"] == litro["litros"] == 10029.2
    assert por_linha["RECEITA_VENDAS"]["orcado_l"] == round(10000 / 10029.2, 4)
    # O orçado por litro para o Resultado por litro comparar: 8.1 é a conta do leite, 8.2 a da comida.
    lo = r["litro_orcado"]
    assert lo["receita_leite_bruta"] == 10000 and lo["comida"] == 5000
    assert lo["preco_bruto_l"] == round(10000 / 10029.2, 4)
    # A cascata orçada tem a forma da DRE (a tela de DRE compara com ela).
    assert [l["chave"] for l in r["cascata_orcada"]] == [l["chave"] for l in dre["cascata"]]
    assert r["conferencia"]["fecha"] is True, r["conferencia"]


def test_periodo_de_meses_inteiros_centro_e_isolamento(cenario):  # noqa: F811
    cenario.ligar_regras_v2()
    meio = cenario.c.get(REL, params={"data_inicio": "2031-03-01", "data_fim": "2031-03-15"})
    assert meio.status_code == 422 and "meses inteiros" in meio.json()["detail"]
    assert cenario.c.get(REL, params={"data_inicio": "2031-04-01", "data_fim": "2031-03-31"}).status_code == 422
    agri = cenario.get(REL, **MAR, centro_custo="Agricultura")
    assert agri["tem_orcamento"] is False and agri["litro_orcado"] is None
    leite = cenario.get(REL, **MAR, centro_custo="Pecuária Leiteira")
    assert leite["tem_orcamento"] is True
    cenario.estado["fazenda_id"] = 2
    outra = cenario.get(REL, **MAR)
    assert outra["tem_orcamento"] is False and outra["meses_com_orcamento"] == []


# ── planilha ──────────────────────────────────────────────────────────────
def _itens(cenario, fazenda_id=1):  # noqa: F811
    with Session(cenario.engine) as s:
        return {(o.mes, o.codigo_conta_gerencial, o.centro_custo): o.valor_orcado
                for o in s.exec(select(OrcamentoItem).where(OrcamentoItem.fazenda_id == fazenda_id, OrcamentoItem.ano == 2031)).all()}


def test_grade_cria_atualiza_apaga_e_nao_mexe_em_celula_com_varios_itens(cenario):  # noqa: F811
    cc = "Pecuária Leiteira"
    # Uma célula com dois itens (lançados um a um na tela antiga).
    cenario.c.post("/planejamento/orcamento", json={"ano": 2031, "mes": 4, "codigo_conta_gerencial": "8.2", "centro_custo": cc, "tipo": "despesa", "valor_orcado": 100})
    cenario.c.post("/planejamento/orcamento", json={"ano": 2031, "mes": 4, "codigo_conta_gerencial": "8.2", "centro_custo": cc, "tipo": "despesa", "valor_orcado": 200})
    r = cenario.c.put("/planejamento/orcamento-grade", json={"ano": 2031, "celulas": [
        {"codigo_conta_gerencial": "8.2", "centro_custo": cc, "tipo": "despesa", "mes": 3, "valor": 5500},   # atualiza
        {"codigo_conta_gerencial": "8.1", "centro_custo": cc, "tipo": "receita", "mes": 3, "valor": 0},      # apaga
        {"codigo_conta_gerencial": "8.7", "centro_custo": cc, "tipo": "despesa", "mes": 5, "valor": 4200},   # cria
        {"codigo_conta_gerencial": "8.7", "centro_custo": cc, "tipo": "despesa", "mes": 6, "valor": 0},      # nada
        {"codigo_conta_gerencial": "8.2", "centro_custo": cc, "tipo": "despesa", "mes": 4, "valor": 999},    # ignorada
    ]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["criadas"], d["atualizadas"], d["excluidas"]) == (1, 1, 1)
    assert [(x["codigo_conta_gerencial"], x["mes"]) for x in d["ignoradas"]] == [("8.2", 4)]
    itens = _itens(cenario)
    assert itens[(3, "8.2", cc)] == 5500 and (3, "8.1", cc) not in itens and itens[(5, "8.7", cc)] == 4200
    assert (6, "8.7", cc) not in itens


def test_grade_zerar_item_que_virou_pedido_mantem_o_item(cenario):  # noqa: F811
    cc = "Pecuária Leiteira"
    with Session(cenario.engine) as s:
        item = s.exec(select(OrcamentoItem).where(OrcamentoItem.codigo_conta_gerencial == "8.1")).one()
        item_id = item.id
    assert cenario.c.post("/planejamento/importar-para-pedido", json={
        "origem_tipo": "orcamento", "origem_item_id": item_id, "tipo_pedido": "venda"}).status_code == 201
    r = cenario.c.put("/planejamento/orcamento-grade", json={"ano": 2031, "celulas": [
        {"codigo_conta_gerencial": "8.1", "centro_custo": cc, "tipo": "receita", "mes": 3, "valor": 0}]})
    assert r.json()["excluidas"] == 0 and _itens(cenario)[(3, "8.1", cc)] == 0
    with Session(cenario.engine) as s:
        assert s.exec(select(Pedido).where(Pedido.origem_item_id == item_id)).first() is not None


def test_grade_isolamento_entre_fazendas_e_validacao(cenario):  # noqa: F811
    cc = "Pecuária Leiteira"
    cenario.estado["fazenda_id"] = 2
    r = cenario.c.put("/planejamento/orcamento-grade", json={"ano": 2031, "celulas": [
        {"codigo_conta_gerencial": "8.2", "centro_custo": cc, "tipo": "despesa", "mes": 3, "valor": 1}]})
    assert r.status_code == 200 and r.json()["criadas"] == 1
    # A fazenda 1 continua com o orçamento dela intacto; a 2 ganhou só o item dela.
    assert _itens(cenario, 1)[(3, "8.2", cc)] == 5000
    assert _itens(cenario, 2) == {(3, "8.2", cc): 1}
    ruim = cenario.c.put("/planejamento/orcamento-grade", json={"ano": 2031, "celulas": [
        {"codigo_conta_gerencial": "8.2", "tipo": "despesa", "mes": 13, "valor": 1}]})
    assert ruim.status_code == 422
    ruim = cenario.c.put("/planejamento/orcamento-grade", json={"ano": 2031, "celulas": [
        {"codigo_conta_gerencial": "8.2", "tipo": "outro", "mes": 1, "valor": 1}]})
    assert ruim.status_code == 422


def test_conferencia_aponta_diferenca():
    linhas = [{"codigo_conta_gerencial": "1", "grupo": "receita", "tipo": "receita", "realizado": 100.0, "coberta_por": None, "cobre": []}]
    real = [{"chave": "RECEITA_VENDAS", "operador": "+", "eh_subtotal": False, "valor": 100.0},
            {"chave": "CUSTO_VARIAVEL", "operador": "-", "eh_subtotal": False, "valor": 30.0}]
    mapa = {"1": "RECEITA_VENDAS"}
    assert conferir_com_a_dre(linhas, real[:1], mapa)["fecha"] is True
    nao = conferir_com_a_dre(linhas, real, mapa)
    assert nao["fecha"] is False and nao["maior_diferenca"] == 30.0
