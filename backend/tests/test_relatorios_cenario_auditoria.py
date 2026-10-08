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
   custos, agrupados por natureza; a depreciação continua. PR 7 e PR 4 (flag
   LIGADA): juros e descontos da baixa em Outras (com a opção abatimento),
   receita do leite bruta com o Funrural/Senar em Deduções, kg→litro e mês
   fechado no custo por litro, RMCA/custo/orçamento pelos registros da DRE.
   PR 2 e PR 3 (contas → backfill → flag): a folha ganha conta e itens, entra
   pelo bruto (pessoal 4.840) e não classificado zera; retidos, vale e FGTS a
   recolher ficam fora da DRE; o backfill com a flag desligada não muda nada.
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
from tests.cenario_auditoria_financeiro import (
    HOJE_GOLDEN_CAIXA, ler_caixa_e_cartao, ler_relatorios_estaveis, montar_cenario, preparar_fazendas,
)

GOLDEN = Path(__file__).parent / "dados" / "cenario_auditoria_golden_main.json"
# Saldo, Caixa Real, Contas a pagar e fluxo do cartão pelo código de antes dos
# PRs 5 e 6 (62880163), com o relógio parado em HOJE_GOLDEN_CAIXA — gerado por
# tests/dados/gerar_golden_caixa_cartao.py.
GOLDEN_CAIXA = Path(__file__).parent / "dados" / "caixa_cartao_golden_pre_pr56.json"
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

    def configurar_contas_automaticas(self):
        """PR 2: a conta de salários do cenário (8.9, Gastos com pessoal) como
        conta automática da folha; os encargos usam a mesma (reserva)."""
        r = self.c.post("/financeiro/plano-contas", json={"codigo": "8.9", "nome": "AUD Salários e encargos", "ativa": True})
        assert r.status_code == 200, r.text
        self.put("/financeiro/plano-contas/8.9/linha-dre", {"linha_dre": "GASTOS_PESSOAL"})
        self.put("/financeiro/contas-automaticas/folha_salario", {"codigo_conta_gerencial": "8.9"})

    def backfill_itens_automaticos(self, aplicar: bool = True) -> dict:
        """O comando do PR 2/3 sobre o histórico (a folha da Ana nasceu antes
        das contas automáticas, com a flag desligada)."""
        from scripts.backfill_itens_automaticos import executar

        with Session(self.engine) as s:
            return executar(s, self.estado["fazenda_id"], aplicar=aplicar, saida=lambda *_: None)

    def ligar_pr2_pr3(self):
        """A ordem de rollout: contas configuradas → backfill → flag."""
        self.configurar_contas_automaticas()
        self.backfill_itens_automaticos()
        self.ligar_regras_v2()

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


@pytest.fixture
def relogio_parado(monkeypatch):
    """`hoje` do servidor parado em HOJE_GOLDEN_CAIXA (meio-dia em Brasília)."""
    import fazenda.rules.datas as datas
    from datetime import datetime

    meio_dia = datetime(HOJE_GOLDEN_CAIXA.year, HOJE_GOLDEN_CAIXA.month, HOJE_GOLDEN_CAIXA.day, 12, 0)
    monkeypatch.setattr(datas, "agora_local", lambda agora=None: meio_dia)
    return HOJE_GOLDEN_CAIXA


@pytest.fixture
def cenario_dia_fixo(tmp_path_factory, tmp_path, relogio_parado):
    """O mesmo cenário, montado e lido com o relógio parado (as leituras de
    saldo/Caixa Real/cartão dependem de hoje)."""
    if "db_dia_fixo" not in _CACHE:
        destino = tmp_path_factory.mktemp("cenario_dia_fixo") / "cenario.db"
        engine = create_engine(f"sqlite:///{destino}", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(engine)
        preparar_fazendas(engine)
        with _cliente(engine, {"fazenda_id": 1}) as c:
            ids = montar_cenario(c, engine, 1, hoje=relogio_parado)
        engine.dispose()
        _CACHE["db_dia_fixo"] = (destino, ids)
    origem, ids = _CACHE["db_dia_fixo"]
    copia = tmp_path / "cenario_dia_fixo.db"
    shutil.copyfile(origem, copia)
    engine = create_engine(f"sqlite:///{copia}", connect_args={"check_same_thread": False})
    estado = {"fazenda_id": 1}
    with _cliente(engine, estado) as c:
        yield Cenario(c, engine, ids, estado)
    engine.dispose()


# Colunas novas (nulas) dos PRs 5 e 6 que o dump cru do lançamento passa a ter —
# como natureza_fin/diferenca_tipo nos PRs 1 e 7. Com a flag desligada elas
# vêm sempre vazias; o resto do registro tem de ser idêntico.
_COLUNAS_NOVAS_PR56 = {"conta_corrente_id", "gerado_por", "fatura_cartao_id"}


def _sem_colunas_novas(lista):
    for x in lista:
        for k in _COLUNAS_NOVAS_PR56 & set(x):
            assert x[k] is None, (k, x)
    return [{k: v for k, v in x.items() if k not in _COLUNAS_NOVAS_PR56} for x in lista]


# =============================================================================
# 1. Regressão: flag desligada = main original, byte a byte (no JSON).
# =============================================================================
def test_flag_desligada_relatorios_identicos_ao_golden_da_main(cenario):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    atual = _normalizar(ler_relatorios_estaveis(cenario.c))
    for chave in golden:
        assert atual[chave] == golden[chave], f"{chave} mudou com a flag desligada"
    assert set(atual) == set(golden)


def test_flag_desligada_caixa_real_saldo_e_cartao_identicos_ao_golden(cenario_dia_fixo):
    """PR 5 e PR 6 com a flag DESLIGADA: saldo das contas, Caixa Real, fundo de
    reserva, Contas a pagar e o fluxo inteiro do cartão (compra, fechar,
    pagar — ainda pela nota genérica) saem como no código de antes."""
    golden = json.loads(GOLDEN_CAIXA.read_text(encoding="utf-8"))
    atual = _normalizar(ler_caixa_e_cartao(cenario_dia_fixo.c, cenario_dia_fixo.ids, HOJE_GOLDEN_CAIXA))
    atual["contas_a_pagar_90"] = _sem_colunas_novas(atual["contas_a_pagar_90"])
    assert set(atual) == set(golden)
    for chave in golden:
        assert atual[chave] == golden[chave], f"{chave} mudou com a flag desligada"


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
# 3. PR 7 (juros e descontos da baixa) e PR 4 (receita do leite) — flag ligada.
# =============================================================================
ABR = ("2031-04-01", "2031-04-30")
MAR_Q = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}


def _contas_da_linha(d, chave):
    return {c["codigo"]: c["valor"] for c in next(x for x in d["cascata"] if x["chave"] == chave)["contas"]}


def _repagar_l7_com_abatimento(cenario):
    l7 = cenario.ids["L"]["L7"]["ids"][0]
    r = cenario.c.post(f"/financeiro/lancamentos/{l7}/estornar", json={"motivo": "teste abatimento"})
    assert r.status_code == 200, r.text
    cenario.put(f"/financeiro/lancamentos/{l7}/pagar", {
        "data_pagamento": "2031-04-20", "valor_pago": 600, "forma_pagamento": "pix",
        "natureza_diferenca": "abatimento",
    })
    return l7


def test_pr7_juros_e_desconto_da_baixa_em_outras_no_caixa(cenario):
    """L3 pago com 50 de juros e L7 com 400 de desconto: Outras = −50 + 400."""
    cenario.ligar_regras_v2()
    dc = cenario.dre(*ABR, "caixa")
    assert cenario.linha(dc, "OUTRAS_REC_DESP") == 350
    assert _contas_da_linha(dc, "OUTRAS_REC_DESP") == {"(descontos obtidos)": 400.0, "(juros e multas pagos)": -50.0}
    # A linha da conta continua no valor CONTRATADO (L3 1.000, L7 1.000).
    assert cenario.linha(dc, "CUSTO_VARIAVEL") == 5900
    L = cenario.ids["L"]
    assert sorted((d["numero_lancamento"], d["valor"], d["tipo"]) for d in dc["diferencas_baixa"]) == sorted([
        (L["L3"]["numero_lancamento"], 50.0, "despesa"), (L["L7"]["numero_lancamento"], 400.0, "receita"),
    ])


def test_pr7_dre_de_caixa_fecha_com_o_pago(cenario):
    """Linha + Outras = valor_pago: as saídas operacionais de abril na DRE de
    caixa batem com o que saiu do banco (L2 3.600 + L3 1.050 + L7 600 + L10
    1.200 = 6.450), e a receita líquida com o recebido do L1 (9.850). A nota
    genérica da fatura do cartão (800, sem conta) é o PR 5."""
    cenario.ligar_regras_v2()
    dc = cenario.dre(*ABR, "caixa")
    saidas = cenario.linha(dc, "CUSTO_VARIAVEL") + cenario.linha(dc, "GASTOS_PESSOAL") - cenario.linha(dc, "OUTRAS_REC_DESP")
    L = cenario.ids["L"]
    with Session(cenario.engine) as s:
        pago = sum(s.get(ContaGerencial, L[n]["ids"][0]).valor_pago for n in ("L2", "L3", "L7", "L10"))
    assert round(saidas, 2) == pago == 6450
    assert cenario.linha(dc, "RECEITA_LIQUIDA") == 9850
    assert dc["nao_classificado"]["total"] == 800


def test_pr7_competencia_juros_na_data_do_pagamento(cenario):
    """O fato gerador do juro/desconto é a baixa: na competência, março fica
    com o contratado (sem Outras) e abril recebe os +350."""
    cenario.ligar_regras_v2()
    mar = cenario.dre()
    assert cenario.linha(mar, "OUTRAS_REC_DESP") == 0 and cenario.linha(mar, "CUSTO_VARIAVEL") == 7500
    assert cenario.linha(cenario.dre(*ABR), "OUTRAS_REC_DESP") == 350


def test_pr7_baixa_parcial_e_pago_sem_valor_pago_nao_geram_outras(cenario):
    """L10 (baixa parcial reparcelada: desconto_acrescimo 0) e L6 (pago sem
    valor_pago, desconto_acrescimo −700 por bug que o PR 6 corrige) não são
    desconto: nada em Outras."""
    cenario.ligar_regras_v2()
    L = cenario.ids["L"]
    with Session(cenario.engine) as s:
        l6 = s.get(ContaGerencial, L["L6"]["ids"][0])
        assert (l6.valor_pago, l6.desconto_acrescimo) == (None, -700)
    numeros = {d["numero_lancamento"] for d in cenario.dre(*ABR, "caixa")["diferencas_baixa"]}
    assert L["L10"]["numero_lancamento"] not in numeros
    marco_caixa = cenario.dre(regime="caixa")
    assert cenario.linha(marco_caixa, "OUTRAS_REC_DESP") == 0 and marco_caixa["diferencas_baixa"] == []


def test_pr7_abatimento_reduz_a_propria_conta(cenario):
    """Decisão do dono: o desconto na baixa pode ser marcado como abatimento —
    reduz o custo da própria conta e não vai para Outras (SOLUCOES §P0-4:
    CMV de março −400 e Outras de abril −50)."""
    cenario.ligar_regras_v2()
    antes_legado = cenario.dre()["despesas_total"]
    l7 = _repagar_l7_com_abatimento(cenario)
    with Session(cenario.engine) as s:
        conta = s.get(ContaGerencial, l7)
        assert (conta.valor_total, conta.valor_pago, conta.desconto_acrescimo, conta.diferenca_tipo) == (1000, 600, -400, "abatimento")
    mar = cenario.dre()
    assert cenario.linha(mar, "CUSTO_VARIAVEL") == 7100
    assert mar["despesas_total"] == antes_legado  # campos legados só mudam no PR 8
    dc = cenario.dre(*ABR, "caixa")
    assert cenario.linha(dc, "CUSTO_VARIAVEL") == 5500 and cenario.linha(dc, "OUTRAS_REC_DESP") == -50
    assert cenario.linha(cenario.dre(*ABR), "OUTRAS_REC_DESP") == -50
    # Custo por litro, RMCA e custos também enxergam o abatimento.
    assert cenario.get("/financeiro/custo-litro-leite", **MAR_Q)["custo_total"] == 7100
    assert cenario.get("/financeiro/rmca", **MAR_Q)["gerencial"]["custo_alimentacao"] == 7100


def test_pr7_abatimento_com_flag_desligada_nao_muda_numero(cenario):
    _repagar_l7_com_abatimento(cenario)
    dc = cenario.dre(*ABR, "caixa")
    assert "regras_v2" not in dc and "diferencas_baixa" not in dc
    assert cenario.linha(dc, "CUSTO_VARIAVEL") == 5900 and cenario.linha(dc, "OUTRAS_REC_DESP") == 0
    assert cenario.linha(cenario.dre(), "CUSTO_VARIAVEL") == 7500


def test_pr7_abatimento_so_para_desconto_e_valida_antes_de_gravar(cenario):
    l9 = cenario.ids["L"]["L9"]["ids"][0]  # em aberto, 1.000
    base = {"data_pagamento": "2031-04-30", "forma_pagamento": "pix"}
    casos = [
        {**base, "valor_pago": 1100, "natureza_diferenca": "abatimento"},  # acréscimo
        {**base, "valor_pago": 1000, "natureza_diferenca": "abatimento"},  # sem diferença
        {**base, "valor_pago": 900, "natureza_diferenca": "qualquer"},
        {**base, "valor_pago": 900, "natureza_diferenca": "abatimento",
         "parcelas_diferenca": [{"data_vencimento": "2031-05-30", "valor": 100}]},
    ]
    for corpo in casos:
        r = cenario.c.put(f"/financeiro/lancamentos/{l9}/pagar", json=corpo)
        assert r.status_code == 400, (corpo, r.text)
    with Session(cenario.engine) as s:
        conta = s.get(ContaGerencial, l9)
        assert (conta.data_pagamento, conta.valor_pago, conta.diferenca_tipo) == (None, None, None)
    # "financeiro" explícito = padrão (grava NULL).
    cenario.put(f"/financeiro/lancamentos/{l9}/pagar", {**base, "valor_pago": 950, "natureza_diferenca": "financeiro"})
    with Session(cenario.engine) as s:
        assert s.get(ContaGerencial, l9).diferenca_tipo is None


def test_pr7_orcamento_realizado_com_o_desconto_da_nota_rateado(cenario):
    """Orçado × realizado pela mesma função de registros da DRE: a ração (8.2)
    sai com o desconto do L2 rateado (7.500, antes 7.800 do item bruto)."""
    q = {"ano": 2031, "mes_inicio": 3, "mes_fim": 3}
    antes = {l["codigo_conta_gerencial"]: l["realizado"] for l in cenario.get("/planejamento/orcamento/comparativo", **q)["linhas"]}
    cenario.ligar_regras_v2()
    o = cenario.get("/planejamento/orcamento/comparativo", **q)
    depois = {l["codigo_conta_gerencial"]: l["realizado"] for l in o["linhas"]}
    assert (antes["8.2"], depois["8.2"]) == (7800, 7500)
    assert (antes["8.7"], depois["8.7"]) == (1700, 1600)
    assert (antes["8.1"], depois["8.1"]) == (10000, 10000)
    assert depois["(descontos na nota de venda)"] == 150
    assert o["regras_v2"] is True


def test_pr4_custo_litro_converte_kg(cenario):
    """Ex-xfail do PR 4: 10.320 kg ÷ 1,029 = 10.029,15 L, e o custo com o
    desconto da nota rateado (7.500; o cartão é o PR 5)."""
    cenario.ligar_regras_v2()
    cl = cenario.get("/financeiro/custo-litro-leite", **MAR_Q)
    assert cl["litros"] == pytest.approx(10029.15, abs=0.1)
    assert cl["custo_total"] == 7500 and cl["custo_por_litro"] == pytest.approx(0.7478, abs=1e-4)
    assert cl["litros_convertidos_de_kg"] is True and cl["unidade_origem"] == "kg"
    assert cl["periodo_ajustado_para_mes_fechado"] is False


def test_pr4_receita_bruta_e_deducao(cenario):
    """Ex-xfail do PR 4: o desconto da nota do leite (Funrural/Senar) vira
    dedução; a receita líquida e o resultado não mudam."""
    cenario.ligar_regras_v2()
    dm = cenario.dre()
    assert (cenario.linha(dm, "RECEITA_VENDAS"), cenario.linha(dm, "DEDUCAO_IMPOSTOS")) == (10000, 150)
    assert _contas_da_linha(dm, "DEDUCAO_IMPOSTOS") == {"(descontos na nota de venda)": 150.0}
    assert cenario.linha(dm, "RECEITA_LIQUIDA") == 9850
    assert (cenario.linha(dm, "EBITDA"), cenario.linha(dm, "RESULTADO_LIQUIDO")) == (750, -250)
    # No caixa (L1 recebido em abril) a mesma abertura.
    dc = cenario.dre(*ABR, "caixa")
    assert (cenario.linha(dc, "RECEITA_VENDAS"), cenario.linha(dc, "DEDUCAO_IMPOSTOS")) == (10000, 150)


def test_pr4_custo_litro_e_rmca_usam_o_mesmo_litro_e_rmca_bruta_com_liquida(cenario):
    cenario.ligar_regras_v2()
    cl = cenario.get("/financeiro/custo-litro-leite", **MAR_Q)
    rm = cenario.get("/financeiro/rmca", **MAR_Q)
    assert rm["preco_medio_litro_leite"]["litros"] == cl["litros"] == 10029.2
    assert rm["gerencial"] == {
        "receita_leite": 10000.0, "custo_alimentacao": 7500.0, "rmca": 2500.0,
        "deducoes_receita_leite": 150.0, "receita_leite_liquida": 9850.0, "rmca_sobre_liquida": 2350.0,
    }
    assert rm["regras_v2"] is True and rm["fisico"]["receita_leite_liquida"] == 9850


def test_pr4_custo_litro_periodo_parcial_vira_mes_fechado(cenario):
    cenario.ligar_regras_v2()
    cl = cenario.get("/financeiro/custo-litro-leite", data_inicio="2031-03-01", data_fim="2031-03-15")
    assert cl["periodo"] == {"inicio": "2031-03-01", "fim": "2031-03-31"}
    assert cl["periodo_solicitado"] == {"inicio": "2031-03-01", "fim": "2031-03-15"}
    assert cl["periodo_ajustado_para_mes_fechado"] is True and "mês fechado" in cl["avisos"][0]
    assert (cl["custo_total"], cl["litros"]) == (7500, 10029.2)


def test_pr4_pr7_cenario_antes_e_depois(cenario):
    """A tabela antes → depois deste PR (flag desligada → ligada), no estado
    sem os PRs 2, 3, 5 e 6."""
    def numeros():
        dm, dc = cenario.dre(), cenario.dre(*ABR, "caixa")
        cl = cenario.get("/financeiro/custo-litro-leite", **MAR_Q)
        rm = cenario.get("/financeiro/rmca", **MAR_Q)["gerencial"]
        return {
            "receita_vendas_mar": cenario.linha(dm, "RECEITA_VENDAS"),
            "deducoes_mar": cenario.linha(dm, "DEDUCAO_IMPOSTOS"),
            "receita_liquida_mar": cenario.linha(dm, "RECEITA_LIQUIDA"),
            "outras_abr_caixa": cenario.linha(dc, "OUTRAS_REC_DESP"),
            "cmv_abr_caixa": cenario.linha(dc, "CUSTO_VARIAVEL"),
            "resultado_abr_caixa": cenario.linha(dc, "RESULTADO_LIQUIDO"),
            "litros_mar": cl["litros"], "custo_alimentacao_mar": cl["custo_total"], "custo_litro_mar": cl["custo_por_litro"],
            "rmca_mar": rm["rmca"], "rmca_liquida_mar": rm.get("rmca_sobre_liquida"),
        }
    antes = numeros()
    cenario.ligar_regras_v2()
    depois = numeros()
    assert {k: (antes[k], depois[k]) for k in antes} == {
        "receita_vendas_mar": (9850, 10000),
        "deducoes_mar": (0, 150),
        "receita_liquida_mar": (9850, 9850),
        "outras_abr_caixa": (0, 350),
        "cmv_abr_caixa": (5900, 5900),
        # 9.850 − 5.900 − 900 − 1.000 de depreciação (+350 de Outras).
        "resultado_abr_caixa": (2050, 2400),
        "litros_mar": (10320.0, 10029.2),
        "custo_alimentacao_mar": (7800, 7500),
        "custo_litro_mar": (0.7558, 0.7478),
        "rmca_mar": (2200, 2500),
        "rmca_liquida_mar": (None, 2350),
    }


def test_v2_pr4_pr7_nao_vazam_para_outra_fazenda(cenario):
    """Multi-tenant: na fazenda 2 (sem flag) nota de receita com desconto e
    baixa com juros seguem as regras antigas, e nada da 2 aparece na 1."""
    cenario.ligar_regras_v2(fazenda_id=1)
    cenario.estado["fazenda_id"] = 2
    for cod, linha in (("9.1", "RECEITA_VENDAS"), ("9.2", "CUSTO_VARIAVEL")):
        assert cenario.c.post("/financeiro/plano-contas", json={"codigo": cod, "nome": f"F2 {cod}", "ativa": True}).status_code == 200
        cenario.put(f"/financeiro/plano-contas/{cod}/linha-dre", {"linha_dre": linha})
    base = {"centro_custo": "Pecuária Leiteira", "fornecedor_cliente": "F2", "data_emissao": "2031-04-02",
            "data_competencia": "2031-04-02", "data_vencimento": "2031-04-10"}
    rec = cenario.c.post("/financeiro/lancamentos", json={**base, "tipo": "receita", "desconto": 50, "itens": [
        {"produto": "Leite F2", "codigo_conta_gerencial": "9.1", "valor_total": 1000, "tipo_item": "servico"}]})
    desp = cenario.c.post("/financeiro/lancamentos", json={**base, "tipo": "despesa", "itens": [
        {"produto": "Ração F2", "codigo_conta_gerencial": "9.2", "valor_total": 500, "tipo_item": "servico"}]})
    assert rec.status_code == desp.status_code == 201
    cenario.put(f"/financeiro/lancamentos/{desp.json()['ids'][0]}/pagar",
                {"data_pagamento": "2031-04-20", "valor_pago": 530, "forma_pagamento": "pix"})
    d2 = cenario.dre(*ABR)
    assert "regras_v2" not in d2
    assert (cenario.linha(d2, "RECEITA_VENDAS"), cenario.linha(d2, "DEDUCAO_IMPOSTOS"), cenario.linha(d2, "OUTRAS_REC_DESP")) == (950, 0, 0)
    # A 2 não paga nem estorna a nota da 1.
    l3 = cenario.ids["L"]["L3"]["ids"][0]
    assert cenario.c.post(f"/financeiro/lancamentos/{l3}/estornar", json={}).status_code == 404
    cenario.estado["fazenda_id"] = 1
    d1 = cenario.dre(*ABR, "caixa")
    assert cenario.linha(d1, "OUTRAS_REC_DESP") == 350
    assert all(x["numero_lancamento"] != desp.json()["numero_lancamento"] for x in d1["diferencas_baixa"])
    assert cenario.linha(cenario.dre(*ABR), "RECEITA_VENDAS") == 0


# =============================================================================
# 3b. PR 6 (saldo de abertura e Caixa Real: erros 6 e 7) — flag ligada.
# =============================================================================
def _saldo_aud(cenario, **q):
    contas = cenario.get("/financeiro/contas-correntes", **q)
    return next(x for x in contas if x["id"] == cenario.ids["conta_corrente_id"])


def _itens_caixa(cr, texto):
    return [i for p in cr["serie"] for i in p["itens"] if texto in (i["descricao"] or "")]


def test_pr6_saldo_hoje_sem_pagamento_futuro_e_com_aviso(cenario):
    """Ex-xfail do PR 6. Hoje (2026) a conta AUD só tem pagamentos datados em
    2031: o saldo antigo somava todos (−101.600); com a flag eles são
    AGENDADOS, o saldo de hoje é 0 e a tela pede o saldo de abertura."""
    antes = _saldo_aud(cenario)
    assert antes["saldo"] == -101600 and "aviso" not in antes and "saldo_abertura" not in antes
    cenario.ligar_regras_v2()
    depois = _saldo_aud(cenario)
    assert depois["saldo"] == 0
    assert depois["pendente_saldo_abertura"] is True and "saldo de abertura" in depois["aviso"]
    # Os 2031 continuam lá, como agendados (o L6 sem valor_pago agora vale 700).
    assert depois["agendado_liquido"] == -102300 and depois["agendados_quantidade"] == 9


def test_pr6_back_e_livro_do_front_dao_o_mesmo_saldo_em_2031(cenario):
    """Em 31/12/2031 tudo já aconteceu: back = Livro do front (−102.300 — o
    Livro sempre contou o L6 pelo valor; o back antigo o ignorava)."""
    cenario.ligar_regras_v2()
    fim_2031 = _saldo_aud(cenario, hoje="2031-12-31")
    assert fim_2031["saldo"] == -102300 and fim_2031["agendado_liquido"] == 0
    # Antes de 25/03/2031: L8 (−120.000) e L5 (+20.000) já pagos.
    assert _saldo_aud(cenario, hoje="2031-03-02")["saldo"] == -100000


def test_pr6_saldo_parte_do_saldo_de_abertura(cenario):
    cenario.ligar_regras_v2()
    cc = cenario.ids["conta_corrente_id"]
    cenario.put(f"/financeiro/contas-correntes/{cc}/saldo-abertura",
                {"saldo_abertura": 150000, "data_saldo_abertura": "2026-09-30"})
    hoje = _saldo_aud(cenario)
    assert hoje["saldo"] == 150000 and hoje["pendente_saldo_abertura"] is False and hoje["aviso"] is None
    assert (hoje["saldo_abertura"], hoje["data_saldo_abertura"]) == (150000, "2026-09-30")
    assert _saldo_aud(cenario, hoje="2031-12-31")["saldo"] == 150000 - 102300
    cr = cenario.get("/financeiro/caixa-real", dias=90)
    assert cr["saldo_inicial"] == 150000 and cr["saldo_abertura_pendente"] == [] and cr["avisos"] == []
    conta = next(x for x in cr["contas"] if x["id"] == cc)
    assert (conta["saldo_abertura"], conta["data_saldo_abertura"]) == (150000, "2026-09-30")


def test_pr6_caixa_real_saldo_de_hoje_e_pendencia(cenario):
    antes = cenario.get("/financeiro/caixa-real", dias=90)
    assert antes["saldo_inicial"] == -101600 and "regras_v2" not in antes
    cenario.ligar_regras_v2()
    cr = cenario.get("/financeiro/caixa-real", dias=90)
    assert cr["saldo_inicial"] == 0 and cr["regras_v2"] is True
    assert [x["id"] for x in cr["saldo_abertura_pendente"]] == [cenario.ids["conta_corrente_id"]]
    assert "saldo de abertura" in cr["avisos"][0]
    # Os pagamentos de 2031 ficam fora da janela de 90 dias (agendados).
    assert cr["agendados_fora_da_janela"]["quantidade"] == 9
    assert not [i for p in cr["serie"] for i in p["itens"] if i.get("agendado")]


def test_pr6_caixa_real_boleto_inteiro_sem_desconto_do_vale(cenario):
    """Ex-xfail do PR 6 (P0-7): o L9 tem R$ 200 de vale de item (ração do
    cachorro da Ana), mas o boleto do fornecedor é de R$ 1.000."""
    antes = _itens_caixa(cenario.get("/financeiro/caixa-real", dias=90), "Ração fazenda")
    assert [i["valor"] for i in antes] == [800]
    cenario.ligar_regras_v2()
    depois = _itens_caixa(cenario.get("/financeiro/caixa-real", dias=90), "Ração fazenda")
    assert [i["valor"] for i in depois] == [1000]
    # O vale continua fora da DRE (a ração do cachorro não é CMV).
    assert cenario.linha(cenario.dre(), "CUSTO_VARIAVEL") == 7500


def test_pr6_pago_sem_valor_pago(cenario):
    """Ex-xfail do PR 6, com a decisão de nunca reescrever valor_pago
    histórico: o L6 (criado antes da flag) continua (None, −700) no banco e o
    saldo o lê pelo valor da parcela (700); lançamento NOVO que nasce pago sem
    valor_pago, com a flag, grava (700, 0)."""
    cenario.ligar_regras_v2()
    with Session(cenario.engine) as s:
        l6 = s.get(ContaGerencial, cenario.ids["L"]["L6"]["ids"][0])
        assert (l6.valor_pago, l6.desconto_acrescimo) == (None, -700)
    r = cenario.c.post("/financeiro/lancamentos", json={
        "tipo": "despesa", "centro_custo": "Pecuária Leiteira", "fornecedor_cliente": "AUD-L6b",
        "itens": [{"produto": "Diarista", "codigo_conta_gerencial": "8.7", "valor_total": 700, "tipo_item": "servico"}],
        "data_emissao": "2031-03-28", "data_competencia": "2031-03-28", "data_pagamento": "2031-03-28",
        "conta_bancaria": "AUD Banco · Agência 0000 · Conta corrente 0000-0",
    })
    assert r.status_code == 201, r.text
    with Session(cenario.engine) as s:
        novo = s.get(ContaGerencial, r.json()["ids"][0])
        assert (novo.valor_pago, novo.desconto_acrescimo) == (700, 0)
        assert novo.conta_corrente_id == cenario.ids["conta_corrente_id"]
    assert _saldo_aud(cenario, hoje="2031-12-31")["saldo"] == -103000


def test_pr6_cenario_antes_e_depois(cenario):
    """A tabela §P0-6/§P0-7 (3) do SOLUCOES.md, flag desligada → ligada."""
    def numeros():
        conta = _saldo_aud(cenario)
        cr = cenario.get("/financeiro/caixa-real", dias=90)
        return {
            "saldo_hoje": conta["saldo"],
            "saldo_fim_2031": _saldo_aud(cenario, hoje="2031-12-31")["saldo"],
            "caixa_real_saldo_inicial": cr["saldo_inicial"],
            "boleto_l9": _itens_caixa(cr, "Ração fazenda")[0]["valor"],
        }
    antes = numeros()
    cenario.ligar_regras_v2()
    depois = numeros()
    assert {k: (antes[k], depois[k]) for k in antes} == {
        "saldo_hoje": (-101600, 0),
        # Sem a flag, `hoje` é ignorado (o saldo antigo não tem data).
        "saldo_fim_2031": (-101600, -102300),
        "caixa_real_saldo_inicial": (-101600, 0),
        "boleto_l9": (800, 1000),
    }


def test_pr6_nao_vaza_para_outra_fazenda(cenario):
    """Multi-tenant: a fazenda 2 não define a abertura nem liga lançamentos
    na conta da 1; o saldo e o Caixa Real da 2 não enxergam a 1."""
    cenario.ligar_regras_v2(fazenda_id=1)
    cc1 = cenario.ids["conta_corrente_id"]
    cenario.estado["fazenda_id"] = 2
    r = cenario.c.put(f"/financeiro/contas-correntes/{cc1}/saldo-abertura",
                      json={"saldo_abertura": 1, "data_saldo_abertura": "2026-01-01"})
    assert r.status_code == 404
    l3 = cenario.ids["L"]["L3"]["ids"][0]
    cc2 = cenario.c.post("/financeiro/contas-correntes", json={"banco": "F2", "agencia": "1", "numero_conta": "2"}).json()["id"]
    r = cenario.c.put("/financeiro/lancamentos/conta-corrente-lote", json={"lancamento_ids": [l3], "conta_corrente_id": cc2})
    assert r.status_code == 200 and r.json()["nao_encontrados"] == [l3]
    r = cenario.c.put("/financeiro/lancamentos/conta-corrente-lote", json={"lancamento_ids": [l3], "conta_corrente_id": cc1})
    assert r.status_code == 404
    assert [x["id"] for x in cenario.get("/financeiro/contas-correntes")] == [cc2]
    assert "regras_v2" not in cenario.get("/financeiro/caixa-real", dias=90)
    cenario.estado["fazenda_id"] = 1
    with Session(cenario.engine) as s:
        assert s.get(ContaGerencial, l3).conta_corrente_id == cc1


# =============================================================================
# 4. PR 2 (contas automáticas) e PR 3 (folha pelo bruto e encargos) — a folha
#    da Ana (bruto 3.000, INSS 240, FGTS projetado 240, vale de item 200;
#    líquido 2.560) nasceu com a flag desligada: o histórico ganha os itens
#    pelo backfill, na ordem de rollout (contas → backfill → flag).
# =============================================================================
def _nota_da_folha(cenario):
    from fazenda.models import FolhaPagamento, LancamentoItem
    from sqlmodel import select

    with Session(cenario.engine) as s:
        folha = s.exec(select(FolhaPagamento).where(FolhaPagamento.fazenda_id == 1)).one()
        itens = s.exec(select(LancamentoItem).where(
            LancamentoItem.numero_lancamento == folha.numero_lancamento_gerado, LancamentoItem.fazenda_id == 1,
        )).all()
        conta = s.exec(select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == folha.numero_lancamento_gerado, ContaGerencial.fazenda_id == 1,
        )).one()
        return conta, {it.gerado_por: (it.valor_total, it.codigo_conta_gerencial, it.natureza_fin) for it in itens}


def test_pr2_folha_nao_cai_em_nao_classificado(cenario):
    """Ex-xfail do PR 2: a folha ganha conta e itens; não classificado = 0."""
    cenario.ligar_pr2_pr3()
    dm = cenario.dre()
    assert dm["nao_classificado"]["total"] == 0
    assert dm["pendencias_contas_automaticas"] == []


def test_pr3_gastos_com_pessoal_pelo_bruto(cenario):
    """Ex-xfail do PR 3: pessoal = 900 (frete do L2) + 700 (diarista) + 3.000
    (bruto) + 240 (FGTS provisionado)."""
    cenario.ligar_pr2_pr3()
    dm = cenario.dre()
    assert cenario.linha(dm, "GASTOS_PESSOAL") == 4840
    assert _contas_da_linha(dm, "GASTOS_PESSOAL") == {"8.7": 1600.0, "8.9": 3240.0}


def test_pr3_itens_da_folha_somam_o_liquido_e_o_valor_nao_muda(cenario):
    antes, _ = _nota_da_folha(cenario)
    cenario.ligar_pr2_pr3()
    conta, itens = _nota_da_folha(cenario)
    assert itens == {
        "folha_salario": (3000.0, "8.9", None),
        "folha_retidos": (-240.0, None, "OBRIGACAO"),
        "folha_vale": (-200.0, None, "ADIANTAMENTO"),
        "folha_fgts_provisao": (240.0, "8.9", None),
        "folha_fgts_a_recolher": (-240.0, None, "OBRIGACAO"),
    }
    assert round(sum(v for v, _c, _n in itens.values()), 2) == conta.valor_total == 2560
    # Backfill nunca mexe no valor nem na conta da nota.
    assert (conta.valor_total, conta.valor_pago, conta.codigo_conta) == (antes.valor_total, antes.valor_pago, antes.codigo_conta)


def test_pr3_retidos_vale_e_fgts_a_recolher_ficam_fora_da_dre(cenario):
    cenario.ligar_pr2_pr3()
    fora = cenario.dre()["fora_da_dre"]
    grupos = {g["natureza"]: g for g in fora["grupos"]}
    # Redutores entram no lado "receita" da obrigação/adiantamento: é o que a
    # fazenda ficou devendo (INSS 240 + FGTS 240) e o que recuperou do vale (200).
    assert (grupos["OBRIGACAO"]["total_receita"], grupos["OBRIGACAO"]["total_despesa"]) == (480.0, 0.0)
    assert (grupos["ADIANTAMENTO"]["total_receita"], grupos["ADIANTAMENTO"]["total_despesa"]) == (200.0, 0.0)
    assert fora["por_natureza"]["INVESTIMENTO"] == 120000


def test_pr2_pr3_cenario_antes_e_depois_marco_2031(cenario):
    """A tabela antes (flag desligada) → depois (contas + backfill + flag),
    no estado dos PRs 1, 7, 4, 2 e 3 (sem o cartão do PR 5)."""
    q = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}

    def numeros():
        dm = cenario.dre()
        ch = cenario.get("/financeiro/custo-hectare", **q)
        return {
            "pessoal": cenario.linha(dm, "GASTOS_PESSOAL"),
            "despesas_operacionais": cenario.linha(dm, "DESPESAS_OPERACIONAIS"),
            "nao_classificado": dm["nao_classificado"]["total"],
            "ebitda": cenario.linha(dm, "EBITDA"),
            "resultado": cenario.linha(dm, "RESULTADO_LIQUIDO"),
            "numerador_custos": ch["despesas_total"],
        }
    antes = numeros()
    cenario.ligar_pr2_pr3()
    cenario.classificar_plano_por_natureza()
    depois = numeros()
    assert {k: (antes[k], depois[k]) for k in antes} == {
        "pessoal": (1600, 4840),
        "despesas_operacionais": (120000, 0),
        "nao_classificado": (2560, 0),
        # 9.850 − 7.500 − 4.840 (−4.290 de resultado com o cartão do PR 5).
        "ebitda": (-119250, -2490),
        "resultado": (-120250, -3490),
        # 136.660 − 120.000 − 5.000 − 2.560 (líquido) + 3.240 (bruto + FGTS).
        "numerador_custos": (136660, 12340),
    }


def test_pr2_backfill_com_flag_desligada_nao_muda_nenhum_relatorio(cenario):
    """Ordem de rollout: o backfill roda ANTES da flag — e não pode mudar
    número nenhum enquanto ela estiver desligada (o motor antigo ignora os
    itens gerados)."""
    cenario.configurar_contas_automaticas()
    resultado = cenario.backfill_itens_automaticos()
    assert resultado["lote"] and resultado["linhas"] == 5
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    atual = _normalizar(ler_relatorios_estaveis(cenario.c))
    for chave in golden:
        assert atual[chave] == golden[chave], f"{chave} mudou com a flag desligada depois do backfill"


def test_pr2_backfill_simula_por_padrao_e_reverte_pelo_lote(cenario):
    cenario.configurar_contas_automaticas()
    simulado = cenario.backfill_itens_automaticos(aplicar=False)
    assert simulado["lote"] is None and len(simulado["plano"].criar) == 1
    assert _nota_da_folha(cenario)[1] == {}
    aplicado = cenario.backfill_itens_automaticos()
    assert len(_nota_da_folha(cenario)[1]) == 5
    # Idempotente: rodar de novo não acha mais nada para criar.
    assert cenario.backfill_itens_automaticos(aplicar=False)["plano"].criar == []
    from scripts.backfill_itens_automaticos import executar
    with Session(cenario.engine) as s:
        executar(s, 1, aplicar=True, reverter=aplicado["lote"], saida=lambda *_: None)
    assert _nota_da_folha(cenario)[1] == {}
    cenario.ligar_regras_v2()
    assert cenario.dre()["nao_classificado"]["total"] == 2560


def test_pr2_backfill_preserva_classificacao_manual(cenario):
    """Nota automática que o usuário já classificou à mão (conta preenchida)
    não ganha itens: o backfill a lista como preservada."""
    conta, _ = _nota_da_folha(cenario)
    with Session(cenario.engine) as s:
        manual = s.get(ContaGerencial, conta.id)
        manual.codigo_conta = "8.7"
        s.add(manual)
        s.commit()
    cenario.configurar_contas_automaticas()
    resultado = cenario.backfill_itens_automaticos()
    assert resultado["plano"].criar == []
    assert [p["numero_lancamento"] for p in resultado["plano"].preservadas] == [conta.numero_lancamento]
    assert _nota_da_folha(cenario)[1] == {}
    cenario.ligar_regras_v2()
    assert _contas_da_linha(cenario.dre(), "GASTOS_PESSOAL")["8.7"] == 1600 + 2560


def test_pr2_sem_conta_configurada_vira_pendencia_e_nao_quebra(cenario):
    """Sem conta automática: os itens nascem (obrigação/adiantamento já ficam
    fora da DRE pela natureza), o custo cai em não classificado com o nome da
    origem e a DRE/conferência apontam a pendência."""
    cenario.backfill_itens_automaticos()
    cenario.ligar_regras_v2()
    dm = cenario.dre()
    assert dm["nao_classificado"]["total"] == 3240
    assert (dm["nao_classificado"]["total_receita"], dm["nao_classificado"]["total_despesa"]) == (0.0, 3240.0)
    assert {c["codigo"]: c["valor"] for c in dm["nao_classificado"]["contas"]} == {
        "(sem conta: Salários e verbas da folha)": 3000.0, "(sem conta: FGTS (encargo do empregador))": 240.0}
    assert [(p["origem"], p["valor"]) for p in dm["pendencias_contas_automaticas"]] == [
        ("folha_salario", 3000.0), ("encargo_fgts", 240.0)]
    conf = cenario.get("/financeiro/dre/conferencia", data_inicio="2031-03-01", data_fim="2031-03-31")
    assert conf["total"] == 3240 and conf["contas_automaticas_pendentes"][0]["origem"] == "folha_salario"


def test_pr2_consultas_lista_a_folha_com_a_origem(cenario):
    """Decisão do dono: os lançamentos da folha aparecem em Consultas, com a
    origem identificada e os itens visíveis (somando o líquido)."""
    cenario.ligar_pr2_pr3()
    conta, _ = _nota_da_folha(cenario)
    lanc = next(l for l in cenario.get("/financeiro/lancamentos")["lancamentos"] if l["id"] == conta.id)
    assert (lanc["origem"], lanc["tipo_documento"], lanc["valor"]) == ("auto", "Folha de pagamento", 2560)
    assert sorted(i["gerado_por"] for i in lanc["itens"]) == sorted([
        "folha_salario", "folha_retidos", "folha_vale", "folha_fgts_provisao", "folha_fgts_a_recolher"])
    assert round(sum(i["valor_total"] for i in lanc["itens"]), 2) == 2560
    assert lanc["natureza_resolvida"] == "MISTA"


def test_pr2_pr3_nao_vazam_para_outra_fazenda(cenario):
    """Multi-tenant: a conta automática, os itens e o backfill de uma fazenda
    não alcançam a outra; a fazenda 2 não usa conta do plano da 1."""
    cenario.ligar_pr2_pr3()
    cenario.estado["fazenda_id"] = 2
    r = cenario.c.put("/financeiro/contas-automaticas/folha_salario", json={"codigo_conta_gerencial": "8.9"})
    assert r.status_code == 404
    origens = {o["origem"]: o for o in cenario.get("/financeiro/contas-automaticas")["origens"]}
    assert origens["folha_salario"]["codigo_conta_gerencial"] is None
    assert cenario.backfill_itens_automaticos(aplicar=False)["plano"].criar == []
    d2 = cenario.dre()
    assert "regras_v2" not in d2 and cenario.linha(d2, "GASTOS_PESSOAL") == 0
    cenario.estado["fazenda_id"] = 1
    assert cenario.linha(cenario.dre(), "GASTOS_PESSOAL") == 4840


# =============================================================================
# 5. O que os PRs seguintes resolvem — xfail ESTRITO, com o PR no motivo.
#    Todos rodam com a flag LIGADA (as regras novas só valem com ela).
# =============================================================================
@pytest.mark.xfail(strict=True, reason="PR 5 (cartão por item): falta só a ração do cartão (+800) — 12.340 → 13.140")
def test_pendente_pr3_pr5_numerador_dos_custos_final(cenario):
    cenario.ligar_pr2_pr3()
    cenario.classificar_plano_por_natureza()
    ch = cenario.get("/financeiro/custo-hectare", data_inicio="2031-03-01", data_fim="2031-03-31")
    assert (ch["despesas_total"], ch["cot"]) == (13140, 14140)


@pytest.mark.xfail(strict=True, reason="PR 5 (cartão por item): a ração do cartão entra no CMV de março")
def test_pendente_pr5_cartao_no_cmv_da_competencia(cenario):
    cenario.ligar_regras_v2()
    assert cenario.linha(cenario.dre(), "CUSTO_VARIAVEL") == 8300


@pytest.mark.xfail(strict=True, reason="PR 5 (cartão por item): fatura aberta aparece em Contas a pagar (decisão a do dono)")
def test_pendente_pr5_fatura_aberta_em_contas_a_pagar(cenario):
    cenario.ligar_regras_v2()
    contas = cenario.get("/financeiro/contas-a-pagar", dias=90)
    assert any("Peça" in (x.get("descricao") or "") for x in contas)


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
