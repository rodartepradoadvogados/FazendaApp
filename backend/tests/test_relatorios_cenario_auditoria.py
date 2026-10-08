"""
Cenário da auditoria dos Relatórios do Financeiro (Fase A) como teste — PR 0.

O cenário (tests/cenario_auditoria_financeiro.py) é o da auditoria: março/2031,
plano 8.*, L1 a L10, cartão, entrega de 10.320 kg, orçamento e a folha da Ana.
Este arquivo trava três coisas:

1. REGRESSÃO (flag `financeiro_regras_v2` DESLIGADA): os relatórios saem
   idênticos aos do código original da main (460d9712), congelados em
   tests/dados/cenario_auditoria_golden_main.json — inclusive o formato da
   resposta (nenhuma chave nova com a flag desligada).
2. PR 1 (flag LIGADA): compra de bem, principal e aporte saem da DRE e dos
   custos, agrupados por natureza; a depreciação continua.
3. O QUE FALTA: cada erro ainda aberto é um `xfail(strict=True)` com o nome do
   PR que o resolve (numeração do SOLUCOES.md, §4). Strict de propósito: o PR
   que corrigir o número faz o teste PASSAR, o xfail estrito vira falha, e o
   PR é obrigado a tirar a marcação — o número certo vira asserção normal.
"""
from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401  (registra todas as tabelas no metadata)
from fazenda.models import ContaGerencial, ParametroFazenda
from tests.cenario_auditoria_financeiro import ler_relatorios_estaveis, montar_cenario, preparar_fazendas

GOLDEN = Path(__file__).parent / "dados" / "cenario_auditoria_golden_main.json"
_CACHE: dict = {}


class _Admin:
    id = 1
    papel = "admin"
    ativo = True
    username = "auditoria"


@contextmanager
def _cliente(engine, estado: dict):
    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    def _sessao():
        with Session(engine) as s:
            yield s

    main.app.dependency_overrides[database.get_session] = _sessao
    main.app.dependency_overrides[get_current_user] = lambda: _Admin()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: estado["fazenda_id"]
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        main.app.dependency_overrides.clear()


def _banco_do_cenario(tmp_path_factory) -> tuple[Path, dict]:
    """Monta o cenário UMA vez por processo (arquivo SQLite) e cada teste
    trabalha numa cópia — o cenário leva alguns segundos para montar."""
    if "db" not in _CACHE:
        destino = tmp_path_factory.mktemp("cenario_auditoria") / "cenario.db"
        engine = create_engine(f"sqlite:///{destino}", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(engine)
        preparar_fazendas(engine)
        with _cliente(engine, {"fazenda_id": 1}) as c:
            ids = montar_cenario(c, engine, 1)
        engine.dispose()
        _CACHE["db"] = (destino, ids)
    return _CACHE["db"]


class Cenario:
    def __init__(self, c, engine, ids, estado):
        self.c, self.engine, self.ids, self.estado = c, engine, ids, estado

    def get(self, caminho, **q):
        r = self.c.get(caminho, params=q)
        assert r.status_code == 200, (caminho, r.status_code, r.text[:300])
        return r.json()

    def put(self, caminho, corpo):
        r = self.c.put(caminho, json=corpo)
        assert r.status_code == 200, (caminho, r.status_code, r.text[:300])
        return r.json()

    def ligar_regras_v2(self, fazenda_id: int = 1) -> None:
        with Session(self.engine) as s:
            s.add(ParametroFazenda(
                chave="financeiro_regras_v2", fazenda_id=fazenda_id, grupo="financeiro",
                label="regras v2", valor="true", tipo="bool",
            ))
            s.commit()

    def dre(self, ini="2031-03-01", fim="2031-03-31", regime="competencia", **extra):
        return self.get("/financeiro/dre", data_inicio=ini, data_fim=fim, regime=regime, **extra)

    @staticmethod
    def linha(d, chave):
        return next(x["valor"] for x in d["cascata"] if x["chave"] == chave)

    def classificar_plano_por_natureza(self):
        """O que o backfill (regra C) aplica neste plano: 8.4 e 8.5 já estão
        fora da DRE, então ganham o motivo — sem mudar número."""
        self.put("/financeiro/plano-contas/8.4/natureza-fin", {"natureza_fin": "FINANCIAMENTO"})
        self.put("/financeiro/plano-contas/8.5/natureza-fin", {"natureza_fin": "CAPITAL"})


@pytest.fixture
def cenario(tmp_path_factory, tmp_path):
    origem, ids = _banco_do_cenario(tmp_path_factory)
    copia = tmp_path / "cenario.db"
    shutil.copyfile(origem, copia)
    engine = create_engine(f"sqlite:///{copia}", connect_args={"check_same_thread": False})
    estado = {"fazenda_id": 1}
    with _cliente(engine, estado) as c:
        yield Cenario(c, engine, ids, estado)
    engine.dispose()


def _normalizar(dados):
    return json.loads(json.dumps(dados, sort_keys=True))


# =============================================================================
# 1. Regressão: flag desligada = main original, byte a byte (no JSON).
# =============================================================================
def test_flag_desligada_relatorios_identicos_ao_golden_da_main(cenario):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    atual = _normalizar(ler_relatorios_estaveis(cenario.c))
    for chave in golden:
        assert atual[chave] == golden[chave], f"{chave} mudou com a flag desligada"
    assert set(atual) == set(golden)


def test_flag_desligada_numeros_de_hoje(cenario):
    """Os números da auditoria (saida_repro.txt), legíveis. Com a flag
    desligada eles NÃO mudam em PR nenhum desta fase."""
    dm = cenario.dre()
    assert cenario.linha(dm, "DESPESAS_OPERACIONAIS") == 120000
    assert cenario.linha(dm, "DEPRECIACAO_AMORT_EXAUSTAO") == 1000
    assert cenario.linha(dm, "GASTOS_PESSOAL") == 1600
    assert cenario.linha(dm, "CUSTO_VARIAVEL") == 7500
    assert cenario.linha(dm, "RESULTADO_LIQUIDO") == -120250
    assert dm["fora_da_dre"] == {"total": 25000.0, "contas": [
        {"codigo": "8.5", "nome": "Aporte", "valor": 20000.0},
        {"codigo": "8.4", "nome": "Parcela principal", "valor": 5000.0},
    ]}
    assert dm["nao_classificado"]["total"] == 2560
    assert (dm["receitas_total"], dm["despesas_total"], dm["resultado"]) == (29850, 136660, -106810)
    assert "regras_v2" not in dm and "por_natureza" not in dm["fora_da_dre"]
    ch = cenario.get("/financeiro/custo-hectare", data_inicio="2031-03-01", data_fim="2031-03-31")
    cv = cenario.get("/financeiro/custo-vaca-lote", data_inicio="2031-03-01", data_fim="2031-03-31")
    assert ch["despesas_total"] == 136660 and cv["despesas_total"] == 136660
    assert "cot" not in ch and "regras_v2" not in cv


def test_natureza_gravada_na_criacao_nao_muda_nada_com_flag_desligada(cenario):
    """O L8 (criar_patrimonio) já nasce INVESTIMENTO no banco — e mesmo assim,
    com a flag desligada, o trator continua nas despesas operacionais."""
    with Session(cenario.engine) as s:
        l8 = s.get(ContaGerencial, cenario.ids["L"]["L8"]["ids"][0])
        assert l8.natureza_fin == "INVESTIMENTO"
    assert cenario.linha(cenario.dre(), "DESPESAS_OPERACIONAIS") == 120000


# =============================================================================
# 2. PR 1 — natureza do lançamento (flag ligada).
# =============================================================================
def test_v2_compra_de_bem_sai_da_dre_e_so_deprecia(cenario):
    cenario.ligar_regras_v2()
    dm = cenario.dre()
    assert dm["regras_v2"] is True
    assert cenario.linha(dm, "DESPESAS_OPERACIONAIS") == 0
    assert cenario.linha(dm, "DEPRECIACAO_AMORT_EXAUSTAO") == 1000
    assert dm["fora_da_dre"]["por_natureza"]["INVESTIMENTO"] == 120000
    # O trator tem bem no Patrimônio: nenhuma pendência "não vai depreciar".
    assert dm["pendencias_natureza"] == []


def test_v2_fora_da_dre_agrupado_por_natureza(cenario):
    cenario.ligar_regras_v2()
    sem_motivo = cenario.dre()["fora_da_dre"]
    # 8.4/8.5 são NAO_ENTRA_NA_DRE sem natureza: continuam fora, "motivo não informado".
    assert sem_motivo["por_natureza"] == {"INVESTIMENTO": 120000.0, "NAO_INFORMADA": 25000.0}
    cenario.classificar_plano_por_natureza()
    fora = cenario.dre()["fora_da_dre"]
    assert fora["total"] == 145000
    assert fora["por_natureza"] == {"INVESTIMENTO": 120000.0, "FINANCIAMENTO": 5000.0, "CAPITAL": 20000.0}
    assert [g["natureza"] for g in fora["grupos"]] == ["INVESTIMENTO", "FINANCIAMENTO", "CAPITAL"]


def test_v2_cenario_antes_e_depois_marco_2031(cenario):
    """A tabela §P0-1 (3) do SOLUCOES.md, no estado do PR 1."""
    antes = cenario.dre()
    cenario.ligar_regras_v2()
    cenario.classificar_plano_por_natureza()
    depois = cenario.dre()
    tabela = {
        chave: (cenario.linha(antes, chave), cenario.linha(depois, chave))
        for chave in ("DESPESAS_OPERACIONAIS", "DEPRECIACAO_AMORT_EXAUSTAO", "EBITDA", "RESULTADO_LIQUIDO")
    }
    assert tabela == {
        "DESPESAS_OPERACIONAIS": (120000, 0),
        "DEPRECIACAO_AMORT_EXAUSTAO": (1000, 1000),
        # 9.850 − 7.500 − 1.600 (a folha ainda em não classificado: PR 2/3).
        "EBITDA": (-119250, 750),
        "RESULTADO_LIQUIDO": (-120250, -250),
    }
    assert (antes["fora_da_dre"]["total"], depois["fora_da_dre"]["total"]) == (25000, 145000)
    # Os campos legados (e-mail do Portal) só mudam no PR 8 (DRE única).
    assert depois["resultado"] == antes["resultado"] == -106810


def test_v2_regime_de_caixa_tambem_tira_o_investimento(cenario):
    cenario.ligar_regras_v2()
    dc = cenario.dre(regime="caixa")
    assert cenario.linha(dc, "DESPESAS_OPERACIONAIS") == 0
    assert dc["fora_da_dre"]["por_natureza"]["INVESTIMENTO"] == 120000


def test_v2_custos_por_hectare_e_vaca_ignoram_investimento_e_principal(cenario):
    q = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}
    cenario.ligar_regras_v2()
    cenario.classificar_plano_por_natureza()
    ch = cenario.get("/financeiro/custo-hectare", **q)
    cv = cenario.get("/financeiro/custo-vaca-lote", **q)
    # 136.660 − 120.000 (trator) − 5.000 (principal) = 11.660 no estado do PR 1
    # (13.140 com folha bruta e cartão: ver o xfail dos PRs 3 e 5 abaixo).
    assert ch["despesas_total"] == 11660 and cv["despesas_total"] == 11660
    assert ch["depreciacao_periodo"] == 1000 and ch["cot"] == 12660
    assert ch["fora_por_natureza"] == {"INVESTIMENTO": 120000.0, "FINANCIAMENTO": 5000.0}


def test_v2_listagem_mostra_a_natureza_resolvida(cenario):
    cenario.ligar_regras_v2()
    cenario.classificar_plano_por_natureza()
    por_numero = {
        l["numero_lancamento"]: l for l in cenario.get("/financeiro/lancamentos")["lancamentos"]
    }
    L = cenario.ids["L"]
    assert por_numero[L["L8"]["numero_lancamento"]]["natureza_fin"] == "INVESTIMENTO"
    assert por_numero[L["L4"]["numero_lancamento"]]["natureza_resolvida"] == "FINANCIAMENTO"
    assert por_numero[L["L5"]["numero_lancamento"]]["natureza_resolvida"] == "CAPITAL"
    assert por_numero[L["L2"]["numero_lancamento"]]["natureza_resolvida"] == "OPERACIONAL"


def test_v2_flag_de_uma_fazenda_nao_vaza_para_a_outra(cenario):
    """Multi-tenant: a fazenda 2 (sem flag) não vê nada do cenário da 1, e a
    flag da 1 não liga a 2. Uma compra de bem na 2 continua despesa lá."""
    cenario.ligar_regras_v2(fazenda_id=1)
    cenario.estado["fazenda_id"] = 2
    r = cenario.c.post("/financeiro/plano-contas", json={"codigo": "9.1", "nome": "Máquinas F2", "ativa": True})
    assert r.status_code == 200, r.text
    cenario.put("/financeiro/plano-contas/9.1/linha-dre", {"linha_dre": "DESPESAS_OPERACIONAIS"})
    r = cenario.c.post("/financeiro/lancamentos", json={
        "tipo": "despesa", "centro_custo": "Pecuária Leiteira", "fornecedor_cliente": "F2",
        "itens": [{"produto": "Ordenhadeira", "codigo_conta_gerencial": "9.1", "valor_total": 50000, "tipo_item": "servico"}],
        "data_emissao": "2031-03-05", "data_competencia": "2031-03-05",
        "criar_patrimonio": {"nome": "Ordenhadeira", "data_imobilizacao": "2031-03-05", "valor_total": 50000,
                             "depreciavel": True, "metodo_depreciacao": "linear", "vida_util_anos": 10},
    })
    assert r.status_code == 201, r.text
    d2 = cenario.dre()
    assert "regras_v2" not in d2
    assert cenario.linha(d2, "DESPESAS_OPERACIONAIS") == 50000
    assert d2["fora_da_dre"]["total"] == 0 and d2["nao_classificado"]["total"] == 0
    # A fazenda 1 não pode mexer na natureza de lançamento da 2, nem o contrário.
    numero_l8 = cenario.ids["L"]["L8"]["numero_lancamento"]
    r = cenario.c.put(f"/financeiro/lancamentos/{numero_l8}/natureza", json={"natureza_fin": "OPERACIONAL"})
    assert r.status_code == 404
    cenario.estado["fazenda_id"] = 1
    d1 = cenario.dre()
    assert d1["regras_v2"] is True and cenario.linha(d1, "DESPESAS_OPERACIONAIS") == 0


# =============================================================================
# 3. O que os PRs seguintes resolvem — xfail ESTRITO, com o PR no motivo.
#    Todos rodam com a flag LIGADA (as regras novas só valem com ela).
# =============================================================================
@pytest.mark.xfail(strict=True, reason="PR 2 (contas automáticas): a folha nasce com conta e item")
def test_pendente_pr2_folha_nao_cai_em_nao_classificado(cenario):
    cenario.ligar_regras_v2()
    assert cenario.dre()["nao_classificado"]["total"] == 0


@pytest.mark.xfail(strict=True, reason="PR 3 (folha pelo bruto e encargos): pessoal = 900 + 700 + 3.000 + 240")
def test_pendente_pr3_gastos_com_pessoal_pelo_bruto(cenario):
    cenario.ligar_regras_v2()
    assert cenario.linha(cenario.dre(), "GASTOS_PESSOAL") == 4840


@pytest.mark.xfail(strict=True, reason="PR 3 + PR 5 (folha bruta e cartão por item): o último dos dois a entrar tira este xfail")
def test_pendente_pr3_pr5_numerador_dos_custos_final(cenario):
    cenario.ligar_regras_v2()
    cenario.classificar_plano_por_natureza()
    ch = cenario.get("/financeiro/custo-hectare", data_inicio="2031-03-01", data_fim="2031-03-31")
    assert (ch["despesas_total"], ch["cot"]) == (13140, 14140)


@pytest.mark.xfail(strict=True, reason="PR 4 (leite kg→L): custo/litro usa os mesmos 10.029,2 L do RMCA")
def test_pendente_pr4_custo_litro_converte_kg(cenario):
    cenario.ligar_regras_v2()
    cl = cenario.get("/financeiro/custo-litro-leite", data_inicio="2031-03-01", data_fim="2031-03-31")
    assert cl["litros"] == pytest.approx(10029.15, abs=0.1)


@pytest.mark.xfail(strict=True, reason="PR 4 (Funrural): desconto da nota de receita vira dedução")
def test_pendente_pr4_receita_bruta_e_deducao(cenario):
    cenario.ligar_regras_v2()
    dm = cenario.dre()
    assert (cenario.linha(dm, "RECEITA_VENDAS"), cenario.linha(dm, "DEDUCAO_IMPOSTOS")) == (10000, 150)


@pytest.mark.xfail(strict=True, reason="PR 5 (cartão por item): a ração do cartão entra no CMV de março")
def test_pendente_pr5_cartao_no_cmv_da_competencia(cenario):
    cenario.ligar_regras_v2()
    assert cenario.linha(cenario.dre(), "CUSTO_VARIAVEL") == 8300


@pytest.mark.xfail(strict=True, reason="PR 5 (cartão por item): fatura aberta aparece em Contas a pagar (decisão a do dono)")
def test_pendente_pr5_fatura_aberta_em_contas_a_pagar(cenario):
    cenario.ligar_regras_v2()
    contas = cenario.get("/financeiro/contas-a-pagar", dias=90)
    assert any("Peça" in (x.get("descricao") or "") for x in contas)


@pytest.mark.xfail(strict=True, reason="PR 6 (saldo de abertura): saldo de hoje não soma pagamentos datados no futuro")
def test_pendente_pr6_saldo_hoje_sem_pagamento_futuro(cenario):
    cenario.ligar_regras_v2()
    contas = cenario.get("/financeiro/contas-correntes")
    saldo = next(x["saldo"] for x in contas if x["id"] == cenario.ids["conta_corrente_id"])
    assert saldo == 0


@pytest.mark.xfail(strict=True, reason="PR 6 (valor_pago obrigatório): pago sem valor_pago nasce com o valor da parcela")
def test_pendente_pr6_pago_sem_valor_pago(cenario):
    cenario.ligar_regras_v2()
    with Session(cenario.engine) as s:
        l6 = s.get(ContaGerencial, cenario.ids["L"]["L6"]["ids"][0])
        assert (l6.valor_pago, l6.desconto_acrescimo) == (700, 0)


@pytest.mark.xfail(strict=True, reason="PR 6 (Caixa Real sem ajuste de vale, P0-7): o boleto do L9 é 1.000")
def test_pendente_pr6_caixa_real_boleto_inteiro(cenario):
    cenario.ligar_regras_v2()
    cr = cenario.get("/financeiro/caixa-real", dias=90)
    itens = [i for p in cr["serie"] for i in p["itens"] if "Ração fazenda" in (i["descricao"] or "")]
    assert itens and itens[0]["valor"] == 1000


@pytest.mark.xfail(strict=True, reason="PR 7 (juros e descontos): −50 de juros do L3 e +400 de desconto do L7 em Outras")
def test_pendente_pr7_outras_receitas_e_despesas_da_baixa(cenario):
    cenario.ligar_regras_v2()
    assert cenario.linha(cenario.dre("2031-04-01", "2031-04-30", "caixa"), "OUTRAS_REC_DESP") == 350


@pytest.mark.xfail(strict=True, reason="PR 8 (DRE única): campos legados (CSV/e-mail do Portal) iguais à cascata")
def test_pendente_pr8_legado_igual_a_cascata(cenario):
    cenario.ligar_regras_v2()
    dm = cenario.dre()
    assert dm["resultado"] == cenario.linha(dm, "RESULTADO_LIQUIDO")


@pytest.mark.xfail(strict=True, reason="PR 8 (orçamento): totais separados por receita, despesa e fora do resultado")
def test_pendente_pr8_orcamento_totais_separados(cenario):
    cenario.ligar_regras_v2()
    o = cenario.get("/planejamento/orcamento/comparativo", ano=2031, mes_inicio=3, mes_fim=3)
    assert o["totais"]["receita"]["realizado"] == 10000


@pytest.mark.xfail(strict=True, reason="PR 9 (COE/COT): 'Todos' no custo por vaca não filtra centro de custo")
def test_pendente_pr9_custo_vaca_todos(cenario):
    cenario.ligar_regras_v2()
    cv = cenario.get("/financeiro/custo-vaca-lote", data_inicio="2031-03-01", data_fim="2031-03-31")
    assert cv["centro_custo"] is None


@pytest.mark.xfail(strict=True, reason="PR 9 (depreciação por centro): filtro 'Agricultura' sem bem desse centro não deprecia o trator")
def test_pendente_pr9_depreciacao_com_filtro_de_centro(cenario):
    cenario.ligar_regras_v2()
    d = cenario.dre("2031-04-01", "2031-04-30", centro_custo="Agricultura")
    assert cenario.linha(d, "DEPRECIACAO_AMORT_EXAUSTAO") == 0
