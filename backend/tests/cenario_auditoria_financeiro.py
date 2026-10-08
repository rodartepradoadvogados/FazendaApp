"""
Cenário da auditoria dos Relatórios do Financeiro (Fase A) — montado pela API.

É o mesmo cenário de `repro_fase_a.py` da auditoria (março/2031, plano 8.*,
lançamentos L1 a L10, cartão, entrega de 10.320 kg, orçamento e uma folha da
Ana com vale de item). NÃO é um arquivo de teste (não começa com `test_`): é
usado por

  - tests/test_relatorios_cenario_auditoria.py (os números de hoje, a
    regressão com a flag desligada e os xfail de cada PR seguinte);
  - tests/dados/gerar_golden_cenario_auditoria.py, que roda ESTE módulo contra
    o código ORIGINAL da main (git worktree) para congelar os números de antes
    da Fase A em tests/dados/cenario_auditoria_golden_main.json.

Só usa a API pública (mais um Pessoa direto no banco, como a auditoria), para
rodar igual nos dois códigos.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session

BANCO = "AUD Banco · Agência 0000 · Conta corrente 0000-0"

PLANO = [
    ("8", "AUD grupo", None, {}),
    ("8.1", "AUD Venda de leite", "RECEITA_VENDAS", {"rmca_receita_leite": True}),
    ("8.2", "AUD Ração concentrado", "CUSTO_VARIAVEL", {"rmca_custo_alimentacao": True}),
    ("8.3", "AUD Juros e multas", "OUTRAS_REC_DESP", {}),
    ("8.4", "AUD Principal financiamento", "NAO_ENTRA_NA_DRE", {}),
    ("8.5", "AUD Aporte sócio", "NAO_ENTRA_NA_DRE", {}),
    ("8.6", "AUD Máquinas (investimento)", "DESPESAS_OPERACIONAIS", {}),
    ("8.7", "AUD Mão de obra terceirizada", "GASTOS_PESSOAL", {}),
    ("8.8", "AUD Funrural/Senar", "DEDUCAO_IMPOSTOS", {}),
]


def preparar_fazendas(engine, ids=(1, 2)) -> None:
    """Fazendas com contrato ativo e todos os módulos (sem isso a trava
    comercial recusa as rotas com 403 quando a fazenda está selecionada)."""
    from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
    from fazenda.models.planos import MODULOS_COMERCIAIS

    with Session(engine) as s:
        for fid in ids:
            s.add(Fazenda(id=fid, nome=f"Fazenda AUD {fid}", ativa=True))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()


def _ok(r, caminho):
    assert r.status_code in (200, 201), (caminho, r.status_code, r.text[:400])
    return r.json()


def montar_cenario(c, engine, fazenda_id: int = 1, hoje: date | None = None) -> dict:
    """Monta o cenário com o TestClient `c` (já autenticado na fazenda
    `fazenda_id`). Devolve os ids/números de lançamento de cada Ln."""
    from fazenda.models import Pessoa

    hoje = hoje or date.today()

    def post(p, b):
        return _ok(c.post(p, json=b), p)

    def put(p, b):
        return _ok(c.put(p, json=b), p)

    for cod, nome, linha, flags in PLANO:
        post("/financeiro/plano-contas", {"codigo": cod, "nome": nome, "ativa": True, **flags})
        if linha:
            put(f"/financeiro/plano-contas/{cod}/linha-dre", {"linha_dre": linha})

    cc = post("/financeiro/contas-correntes", {"banco": "AUD Banco", "agencia": "0000", "numero_conta": "0000-0"})

    with Session(engine) as s:
        ana = Pessoa(nome="Ana Teste", tipo="funcionario", tipo_vinculo="clt", salario_base=3000.0, fazenda_id=fazenda_id)
        s.add(ana)
        s.commit()
        s.refresh(ana)
        ana_id = ana.id

    def it(prod, cod, v, **kw):
        return {"produto": prod, "codigo_conta_gerencial": cod, "valor_total": v, "tipo_item": "servico", **kw}

    def lanc(nome, body):
        body = {"centro_custo": "Pecuária Leiteira", "fornecedor_cliente": f"AUD-{nome}", **body}
        return post("/financeiro/lancamentos", body)

    L = {}
    L["L1"] = lanc("L1", {"tipo": "receita", "itens": [it("Leite mar/31", "8.1", 10000)], "desconto": 150,
                          "data_emissao": "2031-03-31", "data_competencia": "2031-03-31", "data_vencimento": "2031-04-15"})
    L["L2"] = lanc("L2", {"tipo": "despesa", "itens": [it("Ração", "8.2", 3000), it("Frete", "8.7", 1000)], "desconto": 400,
                          "data_emissao": "2031-03-10", "data_competencia": "2031-03-10", "data_vencimento": "2031-04-10"})
    L["L3"] = lanc("L3", {"tipo": "despesa", "itens": [it("Ração boleto", "8.2", 1000)],
                          "data_emissao": "2031-03-20", "data_competencia": "2031-03-20", "data_vencimento": "2031-04-05"})
    L["L4"] = lanc("L4", {"tipo": "despesa", "itens": [it("Parcela principal", "8.4", 5000)], "data_emissao": "2031-03-25",
                          "data_competencia": "2031-03-25", "data_pagamento": "2031-03-25", "valor_pago": 5000, "conta_bancaria": BANCO})
    L["L5"] = lanc("L5", {"tipo": "receita", "itens": [it("Aporte", "8.5", 20000)], "data_emissao": "2031-03-02",
                          "data_competencia": "2031-03-02", "data_pagamento": "2031-03-02", "valor_pago": 20000, "conta_bancaria": BANCO})
    L["L6"] = lanc("L6", {"tipo": "despesa", "itens": [it("Diarista", "8.7", 700)], "data_emissao": "2031-03-28",
                          "data_competencia": "2031-03-28", "data_pagamento": "2031-03-28", "conta_bancaria": BANCO})
    L["L7"] = lanc("L7", {"tipo": "despesa", "itens": [it("Ração desconto", "8.2", 1000)],
                          "data_emissao": "2031-03-15", "data_competencia": "2031-03-15", "data_vencimento": "2031-04-20"})
    L["L8"] = lanc("L8", {"tipo": "despesa", "itens": [it("Trator", "8.6", 120000)], "data_emissao": "2031-03-01",
                          "data_competencia": "2031-03-01", "data_pagamento": "2031-03-01", "valor_pago": 120000, "conta_bancaria": BANCO,
                          "criar_patrimonio": {"nome": "AUD Trator", "tipo": "Máquinas e equipamentos", "data_imobilizacao": "2031-03-01",
                                               "valor_total": 120000, "depreciavel": True, "metodo_depreciacao": "linear",
                                               "vida_util_anos": 10, "valor_residual": 0}})
    venc_l9 = (hoje + timedelta(days=22)).isoformat()
    L["L9"] = lanc("L9", {"tipo": "despesa", "itens": [it("Ração fazenda", "8.2", 800),
                   it("Ração cachorro funcionário", "8.2", 200, vale={"pessoa_id": ana_id, "modo": "folha", "parcelas": 1,
                                                                      "competencia_inicio": "2031-03", "confirmar": True})],
                          "data_emissao": "2031-03-18", "data_competencia": "2031-03-18", "data_vencimento": venc_l9})
    L["L10"] = lanc("L10", {"tipo": "despesa", "itens": [it("Ração parcial", "8.2", 2000)],
                            "data_emissao": "2031-03-12", "data_competencia": "2031-03-12", "data_vencimento": "2031-04-12"})

    def pagar(n, data, valor, **kw):
        return put(f"/financeiro/lancamentos/{L[n]['ids'][0]}/pagar",
                   {"data_pagamento": data, "valor_pago": valor, "conta_bancaria": BANCO, "forma_pagamento": "pix", **kw})

    pagar("L1", "2031-04-15", 9850)
    pagar("L2", "2031-04-10", 3600)
    pagar("L3", "2031-04-08", 1050)
    pagar("L7", "2031-04-20", 600)
    pagar("L10", "2031-04-12", 1200, parcelas_diferenca=[{"data_vencimento": "2031-05-12", "valor": 800}])

    post("/producao/entrega-leite", {"competencia": "2031-03", "quantidade_litros": 10320, "unidade": "kg"})

    cart = post("/financeiro/cartoes", {"apelido": "AUD Cartão", "dia_fechamento": 5, "dia_vencimento": 15})
    comp_cartao = post(f"/financeiro/cartoes/{cart['id']}/lancamentos", {"data_compra": "2031-03-03", "descricao": "Ração no cartão",
                                                                         "codigo_conta_gerencial": "8.2", "valor": 800})
    post(f"/financeiro/cartoes/faturas/{comp_cartao['fatura_id']}/fechar", {})
    post(f"/financeiro/cartoes/faturas/{comp_cartao['fatura_id']}/pagar", {"data_pagamento": "2031-04-15"})
    post(f"/financeiro/cartoes/{cart['id']}/lancamentos", {"data_compra": hoje.isoformat(), "descricao": "Peça (fatura aberta)",
                                                           "codigo_conta_gerencial": "8.6", "valor": 500})

    for o in [{"ano": 2031, "mes": 3, "codigo_conta_gerencial": "8.2", "tipo": "despesa", "valor_orcado": 5000},
              {"ano": 2031, "mes": 3, "codigo_conta_gerencial": "8", "tipo": "despesa", "valor_orcado": 2000},
              {"ano": 2031, "mes": 3, "codigo_conta_gerencial": "8.1", "tipo": "receita", "valor_orcado": 10000}]:
        post("/planejamento/orcamento", {**o, "centro_custo": "Pecuária Leiteira"})

    post("/cadastro/folha-pagamento", {"pessoa_id": ana_id, "competencia": "2031-03", "valor_bruto": 3000,
                                       "valor_inss": 240, "valor_fgts": 240, "status": "pendente"})
    return {"L": L, "conta_corrente_id": cc["id"], "ana_id": ana_id, "cartao_id": cart["id"]}


def ler_relatorios_estaveis(c) -> dict:
    """Respostas que NÃO dependem do dia em que o teste roda (o cenário é de
    2031; só o L9 e a compra aberta do cartão usam "hoje", e nenhuma destas
    leituras olha para eles por data). É o que o golden congela."""
    def get(p, **q):
        return _ok(c.get(p, params=q), p)

    mar = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}
    abr = {"data_inicio": "2031-04-01", "data_fim": "2031-04-30"}
    return {
        "dre_mar_competencia": get("/financeiro/dre", **mar, regime="competencia"),
        "dre_abr_competencia": get("/financeiro/dre", **abr, regime="competencia"),
        "dre_abr_caixa": get("/financeiro/dre", **abr, regime="caixa"),
        "dre_abr_agricultura": get("/financeiro/dre", **abr, regime="competencia", centro_custo="Agricultura"),
        "dre_conferencia_mar": get("/financeiro/dre/conferencia", **mar),
        "custo_hectare_mar": get("/financeiro/custo-hectare", **mar),
        "custo_vaca_lote_mar": get("/financeiro/custo-vaca-lote", **mar),
        "custo_litro_mar": get("/financeiro/custo-litro-leite", **mar),
        "rmca_mar": get("/financeiro/rmca", **mar),
        "orcamento_mar": get("/planejamento/orcamento/comparativo", ano=2031, mes_inicio=3, mes_fim=3),
    }
