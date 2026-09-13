"""
DRE Gerencial em cascata (Onda 3a — backend). Duas camadas de teste:

  A) unitários do motor puro (fazenda/rules/dre.py e
     fazenda/rules/depreciacao_periodo.py) — sem Session, sem HTTP;
  B) integração via API (GET /financeiro/dre, GET /financeiro/dre/conferencia,
     PUT /financeiro/plano-contas/{codigo}/linha-dre) — mesmo padrão de
     fixture `client` de tests/test_vale_item_lancamento.py.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
# Import de fazenda.models (mesmo sem usar as classes no módulo todo) força o
# pacote inteiro de models a registrar suas tabelas em SQLModel.metadata ANTES
# de qualquer fixture rodar `SQLModel.metadata.create_all(engine)` — sem isso,
# rodar ESTE arquivo sozinho (nenhum outro teste importou `main`/fazenda.models
# ainda no processo) cria um banco só com as tabelas que os imports deste
# arquivo tocaram por acaso, faltando tabela (ver mesmo padrão de import em
# tests/test_vale_item_lancamento.py).
import fazenda.models  # noqa: F401
from fazenda.rules.depreciacao_periodo import calcular_depreciacao_periodo
from fazenda.rules.dre import (
    CODIGOS_ATRIBUIVEIS,
    DEPRECIACAO_AMORT_EXAUSTAO,
    NAO_ENTRA_NA_DRE,
    RESULTADO_LIQUIDO,
    montar_cascata_dre,
    resolver_linha_dre,
)


# ===========================================================================
# A) Motor puro — fazenda/rules/dre.py
# ===========================================================================
def test_resolver_linha_dre_heranca_por_prefixo():
    """"3.04.04.02" sem linha própria, "3.04.04" também sem, "3.04" com
    DESPESAS_OPERACIONAIS -> herda de "3.04" (o ancestral mais próximo que
    tiver uma linha), sem precisar de nenhuma entrada explícita nos níveis
    intermediários."""
    mapa = {"3.04": "DESPESAS_OPERACIONAIS"}
    assert resolver_linha_dre("3.04.04.02", mapa) == "DESPESAS_OPERACIONAIS"
    assert resolver_linha_dre("3.04.04", mapa) == "DESPESAS_OPERACIONAIS"
    assert resolver_linha_dre("3.04", mapa) == "DESPESAS_OPERACIONAIS"


def test_resolver_linha_dre_prioriza_o_proprio_codigo_sobre_o_pai():
    mapa = {"3.04": "DESPESAS_OPERACIONAIS", "3.04.04.02": "GASTOS_PESSOAL"}
    assert resolver_linha_dre("3.04.04.02", mapa) == "GASTOS_PESSOAL"


def test_resolver_linha_dre_sem_nenhum_ancestral_classificado_e_none():
    assert resolver_linha_dre("3.09.09", {"3.04": "DESPESAS_OPERACIONAIS"}) is None
    assert resolver_linha_dre(None, {"3.04": "DESPESAS_OPERACIONAIS"}) is None


def test_cascata_fecha_com_numeros_redondos_conferindo_cada_subtotal():
    """Números fechados, um item por linha atribuível — confere CADA
    subtotal da cascata, não só o resultado final."""
    registros = [
        {"codigo_conta": "2.01", "tipo": "receita", "valor": 10000.0, "descricao": "Venda de leite"},
        {"codigo_conta": "3.09", "tipo": "despesa", "valor": 500.0, "descricao": "Impostos sobre venda"},
        {"codigo_conta": "3.01", "tipo": "despesa", "valor": 3000.0, "descricao": "Ração"},
        {"codigo_conta": "3.02", "tipo": "despesa", "valor": 500.0, "descricao": "Comissão de venda"},
        {"codigo_conta": "3.05", "tipo": "despesa", "valor": 2000.0, "descricao": "Salários"},
        {"codigo_conta": "3.04", "tipo": "despesa", "valor": 1000.0, "descricao": "Administrativas"},
        {"codigo_conta": "3.07", "tipo": "despesa", "valor": 300.0, "descricao": "Juros de empréstimo"},
        {"codigo_conta": "2.09", "tipo": "receita", "valor": 200.0, "descricao": "Desconto obtido"},
        {"codigo_conta": "3.08", "tipo": "despesa", "valor": 300.0, "descricao": "IRPJ/CSLL"},
    ]
    mapa = {
        "2.01": "RECEITA_VENDAS", "3.09": "DEDUCAO_IMPOSTOS", "3.01": "CUSTO_VARIAVEL",
        "3.02": "DESPESA_VARIAVEL", "3.05": "GASTOS_PESSOAL", "3.04": "DESPESAS_OPERACIONAIS",
        "3.07": "OUTRAS_REC_DESP", "2.09": "OUTRAS_REC_DESP", "3.08": "TRIBUTOS_IR_CSLL",
    }
    cascata = montar_cascata_dre(registros, mapa, depreciacao_periodo=400.0)
    por_chave = {linha["chave"]: linha for linha in cascata["linhas"]}

    assert por_chave["RECEITA_VENDAS"]["valor"] == 10000.0
    assert por_chave["DEDUCAO_IMPOSTOS"]["valor"] == 500.0
    assert por_chave["RECEITA_LIQUIDA"]["valor"] == 9500.0
    assert por_chave["CUSTO_VARIAVEL"]["valor"] == 3000.0
    assert por_chave["MARGEM_BRUTA"]["valor"] == 6500.0
    assert por_chave["DESPESA_VARIAVEL"]["valor"] == 500.0
    assert por_chave["MARGEM_CONTRIBUICAO"]["valor"] == 6000.0
    assert por_chave["GASTOS_PESSOAL"]["valor"] == 2000.0
    assert por_chave["DESPESAS_OPERACIONAIS"]["valor"] == 1000.0
    assert por_chave["EBITDA"]["valor"] == 3000.0
    assert por_chave["DEPRECIACAO_AMORT_EXAUSTAO"]["valor"] == 400.0
    assert por_chave["OUTRAS_REC_DESP"]["valor"] == -100.0  # 200 receita - 300 despesa (juros)
    assert por_chave["RESULTADO_OPERACIONAL"]["valor"] == 2500.0
    assert por_chave["TRIBUTOS_IR_CSLL"]["valor"] == 300.0
    assert por_chave[RESULTADO_LIQUIDO]["valor"] == 2200.0

    # Ordem de exibição = ordem das 15 linhas definidas (subtotal incluso).
    assert [l["chave"] for l in cascata["linhas"]] == [
        "RECEITA_VENDAS", "DEDUCAO_IMPOSTOS", "RECEITA_LIQUIDA", "CUSTO_VARIAVEL", "MARGEM_BRUTA",
        "DESPESA_VARIAVEL", "MARGEM_CONTRIBUICAO", "GASTOS_PESSOAL", "DESPESAS_OPERACIONAIS", "EBITDA",
        "DEPRECIACAO_AMORT_EXAUSTAO", "OUTRAS_REC_DESP", "RESULTADO_OPERACIONAL", "TRIBUTOS_IR_CSLL",
        "RESULTADO_LIQUIDO",
    ]
    assert cascata["nao_classificado"]["total"] == 0.0
    assert cascata["fora_da_dre"]["total"] == 0.0


def test_conta_nao_classificada_vai_pro_balde_e_nao_contamina_subtotal():
    """Uma conta sem entrada no mapa (nem herdada) some da cascata em si —
    fica só no balde `nao_classificado`, com total e lista de contas."""
    registros = [
        {"codigo_conta": "2.01", "tipo": "receita", "valor": 1000.0, "descricao": "Venda de leite"},
        {"codigo_conta": "3.99", "tipo": "despesa", "valor": 250.0, "descricao": "Conta esquisita nova"},
    ]
    mapa = {"2.01": "RECEITA_VENDAS"}
    cascata = montar_cascata_dre(registros, mapa)
    por_chave = {linha["chave"]: linha for linha in cascata["linhas"]}

    assert por_chave["RECEITA_VENDAS"]["valor"] == 1000.0
    # Nenhum subtotal foi contaminado pela conta não classificada.
    assert por_chave["RESULTADO_LIQUIDO"]["valor"] == 1000.0
    assert cascata["nao_classificado"]["total"] == 250.0
    assert cascata["nao_classificado"]["contas"] == [
        {"codigo": "3.99", "nome": "Conta esquisita nova", "valor": 250.0}
    ]


def test_conta_marcada_nao_entra_na_dre_nunca_aparece_em_subtotal_nenhum():
    """Simulação do caso que motivou o pedido explícito do dono do produto:
    uma conta de PRINCIPAL de financiamento (saída de caixa que NÃO é
    despesa) marcada NAO_ENTRA_NA_DRE some de toda a cascata — nenhum
    subtotal muda por causa dela, ela só aparece no balde `fora_da_dre`."""
    registros_sem_principal = [
        {"codigo_conta": "2.01", "tipo": "receita", "valor": 5000.0, "descricao": "Venda de leite"},
        {"codigo_conta": "3.01", "tipo": "despesa", "valor": 1000.0, "descricao": "Ração"},
    ]
    registros_com_principal = registros_sem_principal + [
        {"codigo_conta": "3.50", "tipo": "despesa", "valor": 9999.0, "descricao": "Amortização de financiamento (principal)"},
    ]
    mapa = {"2.01": "RECEITA_VENDAS", "3.01": "CUSTO_VARIAVEL", "3.50": NAO_ENTRA_NA_DRE}

    cascata_sem = montar_cascata_dre(registros_sem_principal, {"2.01": "RECEITA_VENDAS", "3.01": "CUSTO_VARIAVEL"})
    cascata_com = montar_cascata_dre(registros_com_principal, mapa)

    linhas_sem = {l["chave"]: l["valor"] for l in cascata_sem["linhas"]}
    linhas_com = {l["chave"]: l["valor"] for l in cascata_com["linhas"]}
    # Todo subtotal/linha é IDÊNTICO com ou sem o principal — ele não mexeu
    # em nada da DRE, nem na despesa "-", nem em depreciação, nem no líquido.
    assert linhas_sem == linhas_com
    assert linhas_com[DEPRECIACAO_AMORT_EXAUSTAO] == 0.0
    assert linhas_com[RESULTADO_LIQUIDO] == 4000.0

    assert cascata_com["fora_da_dre"]["total"] == 9999.0
    assert cascata_com["fora_da_dre"]["contas"][0]["codigo"] == "3.50"
    assert cascata_com["nao_classificado"]["total"] == 0.0


def test_depreciacao_do_periodo_entra_na_linha_certa():
    registros = [{"codigo_conta": "2.01", "tipo": "receita", "valor": 1000.0, "descricao": "Venda"}]
    mapa = {"2.01": "RECEITA_VENDAS"}
    cascata = montar_cascata_dre(registros, mapa, depreciacao_periodo=350.0)
    linha_dep = next(l for l in cascata["linhas"] if l["chave"] == DEPRECIACAO_AMORT_EXAUSTAO)
    assert linha_dep["valor"] == 350.0
    assert linha_dep["contas"][0]["nome"] == "Depreciação do período (patrimônio)"
    resultado = next(l for l in cascata["linhas"] if l["chave"] == RESULTADO_LIQUIDO)
    assert resultado["valor"] == 650.0


def test_todas_as_9_linhas_atribuiveis_estao_na_especificacao():
    assert len(CODIGOS_ATRIBUIVEIS) == 9


# ===========================================================================
# A2) Depreciação do período — fazenda/rules/depreciacao_periodo.py
# ===========================================================================
def _patrimonio_dict(**over) -> dict:
    base = {
        "id": 1, "nome": "Trator", "numero": "PAT-001", "depreciavel": True,
        "data_imobilizacao": date(2020, 1, 1), "vida_util": "10 anos",
        "valor_total": 120000.0, "valor_residual": 0.0, "data_baixa": None,
    }
    base.update(over)
    return base


def test_depreciacao_periodo_e_a_diferenca_entre_dois_instantes():
    """Contrato central do módulo: depreciação DO PERÍODO = acumulada até
    data_fim menos acumulada até o dia anterior a data_inicio — conferido
    contra a MESMA fórmula usada por calcular_depreciacao (linha reta,
    rules/patrimonio.py), não contra um número fixo (a idade em dias/365.25
    já embute uma pequena variação ano a ano que não é bug deste módulo)."""
    from datetime import timedelta

    from fazenda.rules.patrimonio import calcular_depreciacao

    item = _patrimonio_dict()
    data_inicio, data_fim = date(2026, 1, 1), date(2026, 12, 31)
    esperado = round(
        calcular_depreciacao(item, data_fim)["depreciacao_acumulada"]
        - calcular_depreciacao(item, data_inicio - timedelta(days=1))["depreciacao_acumulada"],
        2,
    )
    assert esperado == pytest.approx(12000.0, abs=50.0)  # ~1 ano inteiro, folga só da regra dias/365.25

    resultado = calcular_depreciacao_periodo([item], data_inicio, data_fim)
    assert resultado["total"] == esperado
    assert resultado["inconsistencias"] == []
    assert resultado["itens"][0]["patrimonio_id"] == 1


def test_bem_nao_depreciavel_nunca_entra():
    item = _patrimonio_dict(depreciavel=False)
    resultado = calcular_depreciacao_periodo([item], date(2026, 1, 1), date(2026, 12, 31))
    assert resultado["total"] == 0.0
    assert resultado["itens"] == []


def test_bem_baixado_antes_do_periodo_contribui_zero_sem_virar_inconsistencia():
    item = _patrimonio_dict(data_baixa=date(2025, 6, 1))
    resultado = calcular_depreciacao_periodo([item], date(2026, 1, 1), date(2026, 12, 31))
    assert resultado["total"] == 0.0
    assert resultado["inconsistencias"] == []


def test_bem_com_vida_util_nao_reconhecida_e_reportado_a_parte():
    item = _patrimonio_dict(vida_util="não sei")
    resultado = calcular_depreciacao_periodo([item], date(2026, 1, 1), date(2026, 12, 31))
    assert resultado["total"] == 0.0
    assert len(resultado["inconsistencias"]) == 1
    assert resultado["inconsistencias"][0]["item"] == "Trator"


# ===========================================================================
# B) Integração via API
# ===========================================================================
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _criar_conta_gerencial(c, codigo: str, nome: str) -> None:
    r = c.post("/financeiro/plano-contas", json={"codigo": codigo, "nome": nome})
    assert r.status_code == 200, r.text


def _classificar(c, codigo: str, linha_dre: str | None) -> None:
    r = c.put(f"/financeiro/plano-contas/{codigo}/linha-dre", json={"linha_dre": linha_dre})
    assert r.status_code == 200, r.text


def test_put_linha_dre_admin_ok_e_endpoint_reflete_no_dre(client):
    c, _engine = client
    _criar_conta_gerencial(c, "2.01", "Venda de leite")
    _classificar(c, "2.01", "RECEITA_VENDAS")

    r = c.post("/financeiro/lancamentos", json={
        "tipo": "receita", "data_emissao": "2026-07-05",
        "itens": [{"produto": "Leite", "valor_total": 1000.0, "codigo_conta_gerencial": "2.01"}],
    })
    assert r.status_code == 201, r.text

    dre = c.get("/financeiro/dre", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"}).json()
    assert dre["receitas_total"] == 1000.0  # campo legado intacto
    linha = next(l for l in dre["cascata"] if l["chave"] == "RECEITA_VENDAS")
    assert linha["valor"] == 1000.0
    assert linha["contas"][0]["codigo"] == "2.01"


def test_put_linha_dre_rejeita_valor_invalido(client):
    c, _engine = client
    _criar_conta_gerencial(c, "3.77", "Conta qualquer")
    r = c.put("/financeiro/plano-contas/3.77/linha-dre", json={"linha_dre": "NAO_EXISTE"})
    assert r.status_code == 400


def test_put_linha_dre_bloqueado_para_nao_admin(client):
    c, _engine = client
    _criar_conta_gerencial(c, "3.78", "Conta qualquer")

    import main
    from fazenda.auth import get_current_user

    class _FakeOperador:
        id = 2
        papel = "operador"
        ativo = True
        username = "operador"
        permissoes = ""
        email = None

    main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()
    r = c.put("/financeiro/plano-contas/3.78/linha-dre", json={"linha_dre": "RECEITA_VENDAS"})
    assert r.status_code == 403


def test_nota_multi_item_classificada_corretamente_nao_some_em_sem_classificacao(client):
    """O buraco relatado: nota com 2+ itens grava codigo_conta=None na
    ContaGerencial (ver criar_lancamento) e caía em "Sem classificação" no
    DRE antigo. Agora, cada item é resolvido pelo SEU PRÓPRIO
    codigo_conta_gerencial — a nota multi-item aparece corretamente em cada
    linha, e `por_conta` (legado) continua mostrando "Sem classificação"
    (comportamento antigo intocado, só a cascata nova resolve certo)."""
    c, _engine = client
    _criar_conta_gerencial(c, "3.01", "Ração")
    _criar_conta_gerencial(c, "3.05", "Salários")
    _classificar(c, "3.01", "CUSTO_VARIAVEL")
    _classificar(c, "3.05", "GASTOS_PESSOAL")

    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa", "data_emissao": "2026-07-10",
        "itens": [
            {"produto": "Ração concentrada", "valor_total": 700.0, "codigo_conta_gerencial": "3.01"},
            {"produto": "Diária extra", "valor_total": 300.0, "codigo_conta_gerencial": "3.05"},
        ],
    })
    assert r.status_code == 201, r.text

    dre = c.get("/financeiro/dre", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"}).json()
    # Legado: nota com 2+ itens grava codigo_conta=None -> "Sem classificação".
    assert "Sem classificação" in dre["por_conta"]

    por_chave = {l["chave"]: l for l in dre["cascata"]}
    assert por_chave["CUSTO_VARIAVEL"]["valor"] == 700.0
    assert por_chave["GASTOS_PESSOAL"]["valor"] == 300.0
    # E não sobrou nada em não-classificado por causa disso.
    assert dre["nao_classificado"]["total"] == 0.0


def test_heranca_de_linha_dre_do_pai_via_api(client):
    c, _engine = client
    _criar_conta_gerencial(c, "3.04", "Despesas administrativas")
    _criar_conta_gerencial(c, "3.04.02", "Telefone e internet")  # filha, sem linha_dre própria
    _classificar(c, "3.04", "DESPESAS_OPERACIONAIS")

    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa", "data_emissao": "2026-07-12",
        "itens": [{"produto": "Internet", "valor_total": 150.0, "codigo_conta_gerencial": "3.04.02"}],
    })
    assert r.status_code == 201, r.text

    dre = c.get("/financeiro/dre", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"}).json()
    linha = next(l for l in dre["cascata"] if l["chave"] == "DESPESAS_OPERACIONAIS")
    assert linha["valor"] == 150.0
    assert dre["nao_classificado"]["total"] == 0.0


def test_conferencia_lista_conta_sem_linha_dre_com_movimento(client):
    c, _engine = client
    _criar_conta_gerencial(c, "3.66", "Conta nunca classificada")

    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa", "data_emissao": "2026-07-15",
        "itens": [{"produto": "Item qualquer", "valor_total": 420.0, "codigo_conta_gerencial": "3.66"}],
    })
    assert r.status_code == 201, r.text

    conf = c.get("/financeiro/dre/conferencia", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"}).json()
    assert conf["total"] == 420.0
    assert conf["contas"][0]["codigo"] == "3.66"

    dre = c.get("/financeiro/dre", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"}).json()
    assert dre["nao_classificado"]["total"] == 420.0
    # Confere que ela realmente não contaminou nenhum subtotal.
    assert dre["resultado"] == -420.0  # campo legado (não filtra não-classificado)
    resultado_liquido = next(l for l in dre["cascata"] if l["chave"] == "RESULTADO_LIQUIDO")
    assert resultado_liquido["valor"] == 0.0


def test_ajuste_de_vale_aplicado_na_cascata(client):
    """Item marcado como vale de funcionário não é despesa gerencial —
    precisa sumir da cascata igual já sumia de despesas_total."""
    c, engine = client
    from fazenda.models import Pessoa

    with Session(engine) as s:
        p = Pessoa(nome="Fulano", tipo="Funcionário", salario_base=3000.0)
        s.add(p)
        s.commit()
        pessoa_id = p.id

    _criar_conta_gerencial(c, "3.01", "Ração")
    _classificar(c, "3.01", "CUSTO_VARIAVEL")

    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa", "data_emissao": "2026-06-10",
        "itens": [
            {"produto": "Insumo agrícola", "valor_total": 900.0, "codigo_conta_gerencial": "3.01"},
            {
                "produto": "Ração para cães 15kg", "valor_total": 100.0, "codigo_conta_gerencial": "3.01",
                "vale": {"pessoa_id": pessoa_id, "modo": "folha"},
            },
        ],
    })
    assert r.status_code == 201, r.text

    dre = c.get("/financeiro/dre", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"}).json()
    assert dre["despesas_total"] == 900.0  # legado, já cobria isso
    linha = next(l for l in dre["cascata"] if l["chave"] == "CUSTO_VARIAVEL")
    assert linha["valor"] == 900.0  # os 100 de vale não entraram na cascata


def test_depreciacao_periodo_entra_no_endpoint_dre(client):
    c, engine = client
    from fazenda.models import Patrimonio

    with Session(engine) as s:
        s.add(Patrimonio(
            nome="Ordenhadeira", depreciavel=True, data_imobilizacao=date(2020, 1, 1),
            vida_util="10 anos", valor_total=120000.0, valor_residual=0.0,
        ))
        s.commit()

    dre = c.get("/financeiro/dre", params={"data_inicio": "2026-01-01", "data_fim": "2026-12-31"}).json()
    # ~1 ano inteiro de depreciação (120.000 / 10 anos) — folga só da regra
    # dias/365.25 de calcular_depreciacao (rules/patrimonio.py), não deste código.
    assert dre["depreciacao_periodo"]["total"] == pytest.approx(12000.0, abs=50.0)
    linha = next(l for l in dre["cascata"] if l["chave"] == "DEPRECIACAO_AMORT_EXAUSTAO")
    assert linha["valor"] == dre["depreciacao_periodo"]["total"]
    resultado_liquido = next(l for l in dre["cascata"] if l["chave"] == "RESULTADO_LIQUIDO")
    assert resultado_liquido["valor"] == -dre["depreciacao_periodo"]["total"]


def test_conta_nao_entra_na_dre_via_api_fica_fora_de_todo_subtotal(client):
    """Simulação de PRINCIPAL de financiamento via API completa: marcado
    NAO_ENTRA_NA_DRE, aparece em `fora_da_dre` e nunca no resultado."""
    c, _engine = client
    _criar_conta_gerencial(c, "2.01", "Venda de leite")
    _criar_conta_gerencial(c, "3.90", "Amortização de financiamento (principal)")
    _classificar(c, "2.01", "RECEITA_VENDAS")
    _classificar(c, "3.90", NAO_ENTRA_NA_DRE)

    c.post("/financeiro/lancamentos", json={
        "tipo": "receita", "data_emissao": "2026-07-20",
        "itens": [{"produto": "Leite", "valor_total": 5000.0, "codigo_conta_gerencial": "2.01"}],
    })
    c.post("/financeiro/lancamentos", json={
        "tipo": "despesa", "data_emissao": "2026-07-20",
        "itens": [{"produto": "Parcela do financiamento", "valor_total": 2000.0, "codigo_conta_gerencial": "3.90"}],
    })

    dre = c.get("/financeiro/dre", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"}).json()
    resultado_liquido = next(l for l in dre["cascata"] if l["chave"] == "RESULTADO_LIQUIDO")
    assert resultado_liquido["valor"] == 5000.0  # o principal NÃO reduziu o resultado
    assert dre["fora_da_dre"]["total"] == 2000.0
    assert dre["nao_classificado"]["total"] == 0.0
