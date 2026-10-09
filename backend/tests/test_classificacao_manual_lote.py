"""
Tela "Classificar" — o lote de ações (`POST /financeiro/classificacao/aplicar`) e o
Desfazer (`POST .../reverter/{lote}`): tudo ou nada, log por campo, a DRE muda e volta,
validações, regras antigas, isolamento entre fazendas, permissão e mês fechado.
A fila e as sugestões estão em tests/test_classificacao_manual.py (mesmos auxiliares).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlmodel import Session, select

from fazenda.models import ContaGerencial, LancamentoItem, MigracaoLogFinanceiro, PlanoContaGerencial, UsuarioFazenda
from tests.test_classificacao_manual import (  # noqa: F401
    MAR, P, _com_pendencias, _fila, _item, _lancar, _linhas, _plano, _sem_conta_no_banco,
)
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário)


def _normalizada(dre):
    """O que a classificação muda numa DRE: cascata, sem classificação e fora da DRE."""
    return {"cascata": [(l["chave"], l["valor"]) for l in dre["cascata"]],
            "nao": dre["nao_classificado"]["total"], "fora": dre["fora_da_dre"].get("por_natureza", {})}


def _acoes_da_fila(cenario):
    """Uma ação por pendência do cenário, no destino certo."""
    fila = _fila(cenario)
    sem = _linhas(fila, "sem_codigo_conta")[0]
    folha = {l["origem_automatica"]: l for l in _linhas(fila, "item_sem_conta_automatica")}
    return [
        {"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"},
        {"tipo": "conta", "alvo": {"numero_lancamento": sem["numero_lancamento"], "conta_id": sem["conta_id"]}, "valor": "8.7"},
        {"tipo": "conta", "alvo": {"numero_lancamento": folha["folha_salario"]["numero_lancamento"], "item_id": folha["folha_salario"]["item_id"]}, "valor": "8.9"},
        {"tipo": "conta", "alvo": {"numero_lancamento": folha["encargo_fgts"]["numero_lancamento"], "item_id": folha["encargo_fgts"]["item_id"]}, "valor": "8.9"},
        {"tipo": "natureza", "alvo": {"codigo": "8.4"}, "valor": "FINANCIAMENTO"},
        {"tipo": "natureza", "alvo": {"codigo": "8.5"}, "valor": "CAPITAL"},
    ]


def test_lote_classifica_a_dre_muda_e_desfazer_devolve(cenario):  # noqa: F811
    _com_pendencias(cenario)
    _plano(cenario, "8.9", "AUD Salários e encargos", "GASTOS_PESSOAL")
    antes = cenario.dre()
    fila0 = _fila(cenario)
    acoes = _acoes_da_fila(cenario)

    r = cenario.c.post(f"{P}/aplicar", json={"acoes": acoes, "motivo": "fechamento de março"})
    assert r.status_code == 200, r.text
    lote = r.json()
    assert lote["lote"].startswith("classificacao-") and lote["aplicadas"] == 6 and lote["sem_mudanca"] == 0
    assert lote["alteracoes"] == 8                      # 1 linha + 1 nota + 2 itens × (código, nome) + 2 naturezas
    assert [a["mudou"] for a in lote["acoes"]] == [True] * 6 and lote["avisos"] == []

    # A DRE mudou: nada sem classificação, o fora da DRE ganhou o motivo, pessoal e custo subiram.
    depois = cenario.dre()
    assert depois["nao_classificado"]["total"] == 0
    por_natureza = depois["fora_da_dre"]["por_natureza"]
    assert "NAO_INFORMADA" not in por_natureza and por_natureza["FINANCIAMENTO"] == 5000.0 and por_natureza["CAPITAL"] == 20000.0
    assert cenario.linha(depois, "CUSTO_VARIAVEL") == cenario.linha(antes, "CUSTO_VARIAVEL") + 700
    assert cenario.linha(depois, "GASTOS_PESSOAL") == cenario.linha(antes, "GASTOS_PESSOAL") + 500 + 3000 + 240
    assert depois["resumo"]["resultado_liquido"] == round(antes["resumo"]["resultado_liquido"] - 700 - 500 - 3240, 2)

    # A fila esvaziou e o último lote aparece para o Desfazer.
    fila = _fila(cenario)
    assert fila["resumo"]["total_pendencias"] == 0
    assert fila["ultimo_lote"]["lote"] == lote["lote"] and fila["ultimo_lote"]["alteracoes"] == 8

    # O log guarda antes/depois, lote, motivo e a fazenda de cada campo.
    with Session(cenario.engine) as s:
        log = s.exec(select(MigracaoLogFinanceiro).where(MigracaoLogFinanceiro.lote == lote["lote"])).all()
        assert len(log) == 8 and {l.fazenda_id for l in log} == {1} and {l.migracao for l in log} == {"classificacao_manual_v1"}
        assert all(l.motivo == "Classificação manual (tela Classificar): fechamento de março" for l in log)
        linha = next(l for l in log if l.tabela == "plano_conta_gerencial" and l.campo == "linha_dre")
        assert (linha.valor_antes, linha.valor_depois) == ("null", '"CUSTO_VARIAVEL"')
        item = next(l for l in log if l.tabela == "lancamento_item" and l.campo == "codigo_conta_gerencial")
        assert item.valor_antes == "null" and item.valor_depois == '"8.9"'

    # Aplicar de novo o mesmo lote não muda nada (e não cria lote para desfazer).
    de_novo = cenario.c.post(f"{P}/aplicar", json={"acoes": acoes})
    assert de_novo.status_code == 200 and de_novo.json()["lote"] is None
    assert (de_novo.json()["aplicadas"], de_novo.json()["sem_mudanca"]) == (0, 6)
    assert _fila(cenario)["ultimo_lote"]["lote"] == lote["lote"]

    # Desfazer: a DRE e a fila voltam ao que eram.
    d = cenario.c.post(f"{P}/reverter/{lote['lote']}")
    assert d.status_code == 200, d.text
    assert (d.json()["revertidas"], d.json()["ja_revertidas"], d.json()["conflitos"]) == (8, 0, [])
    assert _normalizada(cenario.dre()) == _normalizada(antes)
    fila2 = _fila(cenario)
    assert fila2["resumo"]["total_pendencias"] == fila0["resumo"]["total_pendencias"] == 6 and fila2["ultimo_lote"] is None
    # Desfazer duas vezes é inofensivo.
    d2 = cenario.c.post(f"{P}/reverter/{lote['lote']}").json()
    assert (d2["revertidas"], d2["ja_revertidas"]) == (0, 8)


def test_desfazer_nao_pisa_em_quem_mudou_depois(cenario):  # noqa: F811
    _com_pendencias(cenario)
    lote = cenario.c.post(f"{P}/aplicar", json={"acoes": [
        {"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"},
        {"tipo": "natureza", "alvo": {"codigo": "8.4"}, "valor": "FINANCIAMENTO"}]}).json()["lote"]
    cenario.put("/financeiro/plano-contas/8.20/linha-dre", {"linha_dre": "DESPESAS_OPERACIONAIS"})  # alguém mudou à mão
    d = cenario.c.post(f"{P}/reverter/{lote}").json()
    assert d["revertidas"] == 1 and len(d["conflitos"]) == 1
    assert d["conflitos"][0]["campo"] == "linha_dre" and d["conflitos"][0]["valor_atual"] == "DESPESAS_OPERACIONAIS"
    with Session(cenario.engine) as s:
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "8.20")).one().linha_dre == "DESPESAS_OPERACIONAIS"
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "8.4")).one().natureza_fin is None


def test_lote_e_tudo_ou_nada(cenario):  # noqa: F811
    _com_pendencias(cenario)
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [
        {"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"},
        {"tipo": "conta", "alvo": {"numero_lancamento": "LC-2031-90001", "conta_id": 1}, "valor": "9.99"}]})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["codigo"] == "acoes_invalidas" and [e["indice"] for e in d["erros"]] == [1] and d["erros"][0]["codigo"] == "nao_encontrado"
    with Session(cenario.engine) as s:
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "8.20")).one().linha_dre is None
        assert s.exec(select(MigracaoLogFinanceiro).where(MigracaoLogFinanceiro.migracao == "classificacao_manual_v1")).all() == []
    assert cenario.dre()["nao_classificado"]["total"] > 0


@pytest.mark.parametrize("acao,trecho", [
    ({"tipo": "deletar", "alvo": {"codigo": "8.20"}, "valor": "x"}, "Tipo de ação desconhecido"),
    ({"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "INVENTADA"}, "Linha da DRE inválida"),
    ({"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": None}, "Linha da DRE inválida"),
    ({"tipo": "linha_dre", "alvo": {"codigo": "0.0"}, "valor": "CUSTO_VARIAVEL"}, "não existe no plano"),
    ({"tipo": "linha_dre", "alvo": {}, "valor": "CUSTO_VARIAVEL"}, "não existe no plano"),
    ({"tipo": "natureza", "alvo": {"codigo": "8.4"}, "valor": "QUALQUER"}, "natureza_fin inválida"),
    ({"tipo": "natureza", "alvo": {"codigo": "8.4"}, "valor": None}, "Informe a natureza"),
    ({"tipo": "natureza", "alvo": {"codigo": "0.0"}, "valor": "CAPITAL"}, "não existe no plano"),
    ({"tipo": "natureza", "alvo": {"numero_lancamento": "LC-0000-00000"}, "valor": "CAPITAL"}, "Lançamento não encontrado"),
    ({"tipo": "conta", "alvo": {"numero_lancamento": "LC-2031-90001", "conta_id": 1}, "valor": ""}, "Informe a conta"),
    ({"tipo": "conta", "alvo": {"numero_lancamento": "LC-2031-90001", "conta_id": 1}, "valor": "8"}, "é um grupo"),
    ({"tipo": "conta", "alvo": {"numero_lancamento": "LC-0000-00000"}, "valor": "8.7"}, "Lançamento não encontrado"),
    ({"tipo": "conta", "alvo": {"item_id": 999999}, "valor": "8.7"}, "Item não encontrado"),
])
def test_acoes_invalidas_sao_recusadas_com_o_porque(cenario, acao, trecho):  # noqa: F811
    _com_pendencias(cenario)
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [acao]})
    assert r.status_code == 422, r.text
    assert trecho in r.json()["detail"]["mensagem"]


def test_lote_vazio_e_grande_demais(cenario):  # noqa: F811
    assert cenario.c.post(f"{P}/aplicar", json={"acoes": []}).status_code == 422
    muitas = [{"tipo": "linha_dre", "alvo": {"codigo": "8.1"}, "valor": "RECEITA_VENDAS"}] * 501
    assert cenario.c.post(f"{P}/aplicar", json={"acoes": muitas}).status_code == 422


def test_conta_inativa_nota_com_itens_e_item_de_outra_nota(cenario):  # noqa: F811
    ids = _com_pendencias(cenario)
    assert cenario.c.post("/financeiro/plano-contas", json={"codigo": "8.77", "nome": "AUD Antiga", "ativa": False}).status_code == 200
    sem = {"numero_lancamento": ids["sem_conta_numero"], "conta_id": ids["sem_conta_id"]}
    assert "inativa" in cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "conta", "alvo": sem, "valor": "8.77"}]}).json()["detail"]["mensagem"]
    # Nota com itens: a conta é a do item.
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "conta", "alvo": {"numero_lancamento": ids["silagem"]}, "valor": "8.7"}]})
    assert r.status_code == 422 and "tem itens" in r.json()["detail"]["mensagem"]
    # O item é de outra nota.
    item = _linhas(_fila(cenario), "conta_sem_linha_dre")[0]
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "conta", "alvo": {
        "numero_lancamento": ids["sem_conta_numero"], "item_id": item["item_id"]}, "valor": "8.7"}]})
    assert r.status_code == 422 and "Item não encontrado" in r.json()["detail"]["mensagem"]


def test_alvo_em_texto_e_atalho_do_codigo_ou_do_numero(cenario):  # noqa: F811
    ids = _com_pendencias(cenario)
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [
        {"tipo": "linha_dre", "alvo": "8.20", "valor": "CUSTO_VARIAVEL"},
        {"tipo": "conta", "alvo": ids["sem_conta_numero"], "valor": "8.7"}]})
    assert r.status_code == 200 and r.json()["aplicadas"] == 2


def test_nota_de_um_item_so_atualiza_o_item_e_o_resumo_da_nota(cenario):  # noqa: F811
    with Session(cenario.engine) as s:
        s.add(ContaGerencial(fazenda_id=1, numero_lancamento="LC-2031-90002", tipo="despesa", valor_total=320.0, descricao="Um item só",
                             data_competencia=date(2031, 3, 15), centro_custo="Pecuária Leiteira", parcela_num=1, parcela_total=1,
                             fornecedor_cliente="AUD-Um", origem="manual"))
        s.add(LancamentoItem(fazenda_id=1, numero_lancamento="LC-2031-90002", tipo="despesa", produto="Peça", valor_total=320.0,
                             data_competencia=date(2031, 3, 15)))
        s.commit()
        item_id = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == "LC-2031-90002")).one().id
    l = next(x for x in _linhas(_fila(cenario), "sem_codigo_conta") if x["numero_lancamento"] == "LC-2031-90002")
    assert l["item_id"] == item_id and l["valor"] == 320.0
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "conta", "alvo": {"numero_lancamento": "LC-2031-90002", "item_id": item_id}, "valor": "8.7"}]})
    assert r.status_code == 200 and r.json()["alteracoes"] == 3
    with Session(cenario.engine) as s:
        it = s.get(LancamentoItem, item_id)
        assert (it.codigo_conta_gerencial, it.nome_conta_gerencial) == ("8.7", "AUD Mão de obra terceirizada")
        assert s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-2031-90002")).one().codigo_conta == "8.7"
    assert all(x["numero_lancamento"] != "LC-2031-90002" for x in _linhas(_fila(cenario), "sem_codigo_conta"))
    cenario.c.post(f"{P}/reverter/{r.json()['lote']}")
    with Session(cenario.engine) as s:
        assert s.get(LancamentoItem, item_id).codigo_conta_gerencial is None
        assert s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-2031-90002")).one().codigo_conta is None


def test_natureza_so_neste_lancamento_sem_mexer_na_conta(cenario):  # noqa: F811
    _com_pendencias(cenario)
    l8_4 = next(l for l in _linhas(_fila(cenario), "natureza_nao_informada") if l["codigo_conta"] == "8.4")
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "natureza", "alvo": {
        "numero_lancamento": l8_4["numero_lancamento"], "item_id": l8_4["item_id"]}, "valor": "FINANCIAMENTO"}]})
    assert r.status_code == 200 and r.json()["alteracoes"] == 1
    with Session(cenario.engine) as s:
        assert s.get(LancamentoItem, l8_4["item_id"]).natureza_fin == "FINANCIAMENTO"
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "8.4")).one().natureza_fin is None
    assert [l["codigo_conta"] for l in _linhas(_fila(cenario), "natureza_nao_informada")] == ["8.5"]


def test_regras_antigas_linha_e_conta_funcionam_e_natureza_trava(cenario):  # noqa: F811
    _plano(cenario, "8.20", "AUD Silagem comprada")
    _lancar(cenario, "AUD-Silo", "despesa", [_item("Silagem", "8.20", 700)])
    id_sem = _sem_conta_no_banco(cenario, "LC-2031-90001")
    antes = cenario.dre()
    assert antes["nao_classificado"]["total"] == 700 + 500 + 2560
    # Natureza: recusada inteira, com o porquê (nenhuma outra ação do lote é gravada).
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [
        {"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"},
        {"tipo": "natureza", "alvo": {"codigo": "8.4"}, "valor": "FINANCIAMENTO"}]})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "regras_v2_desligadas" and "regras novas" in r.json()["detail"]["mensagem"]
    assert cenario.dre()["nao_classificado"]["total"] == antes["nao_classificado"]["total"]
    # Linha e conta valem como sempre valeram.
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [
        {"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"},
        {"tipo": "conta", "alvo": {"numero_lancamento": "LC-2031-90001", "conta_id": id_sem}, "valor": "8.7"}]})
    assert r.status_code == 200 and r.json()["aplicadas"] == 2
    depois = cenario.dre()
    assert depois["nao_classificado"]["total"] == 2560 and "regras_v2" not in depois
    assert cenario.linha(depois, "CUSTO_VARIAVEL") == cenario.linha(antes, "CUSTO_VARIAVEL") + 700
    assert cenario.linha(depois, "GASTOS_PESSOAL") == cenario.linha(antes, "GASTOS_PESSOAL") + 500
    assert cenario.c.post(f"{P}/reverter/{r.json()['lote']}").json()["revertidas"] == r.json()["alteracoes"]
    assert _normalizada(cenario.dre()) == _normalizada(antes)


def test_nota_so_com_itens_gerados_aceita_conta_na_nota_com_regras_antigas(cenario):  # noqa: F811
    cenario.backfill_itens_automaticos()           # itens gerados existem, mas a regra antiga os ignora
    folha = next(l for l in _linhas(_fila(cenario), "sem_codigo_conta") if l["valor"] == 2560.0)
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "conta", "alvo": {
        "numero_lancamento": folha["numero_lancamento"], "conta_id": folha["conta_id"]}, "valor": "8.7"}]})
    assert r.status_code == 200 and "itens gerados pelo sistema" in r.json()["avisos"][0]
    assert cenario.dre()["nao_classificado"]["total"] == 0


# ═══════════════════════════ isolamento, permissão, mês fechado ═══════════════
def test_isolamento_entre_fazendas(cenario):  # noqa: F811
    ids = _com_pendencias(cenario)
    lote = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"}]}).json()["lote"]
    cenario.estado["fazenda_id"] = 2
    try:
        f2 = _fila(cenario)
        assert f2["resumo"]["total_pendencias"] == 0 and f2["ultimo_lote"] is None
        # A fazenda 2 não classifica nem desfaz o que é da 1: tudo "não encontrado".
        for acao in (
            {"tipo": "linha_dre", "alvo": {"codigo": "8.1"}, "valor": "RECEITA_VENDAS"},
            {"tipo": "conta", "alvo": {"numero_lancamento": ids["sem_conta_numero"], "conta_id": ids["sem_conta_id"]}, "valor": "8.7"},
            {"tipo": "natureza", "alvo": {"numero_lancamento": ids["silagem"]}, "valor": "CAPITAL"},
        ):
            r = cenario.c.post(f"{P}/aplicar", json={"acoes": [acao]})
            assert r.status_code in (409, 422), (acao, r.text)
        assert cenario.c.post(f"{P}/reverter/{lote}").status_code == 404
    finally:
        cenario.estado["fazenda_id"] = 1
    with Session(cenario.engine) as s:
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "8.20")).one().linha_dre == "CUSTO_VARIAVEL"
        assert s.get(ContaGerencial, ids["sem_conta_id"]).codigo_conta is None
        assert s.exec(select(MigracaoLogFinanceiro).where(MigracaoLogFinanceiro.migracao == "classificacao_manual_v1")).all()[0].revertido_em is None
    assert _fila(cenario)["ultimo_lote"]["lote"] == lote


def test_so_administrador_aplica_e_desfaz_e_contador_so_le(cenario):  # noqa: F811
    import main
    from fazenda.auth import get_current_user

    ids = _com_pendencias(cenario)
    lote = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"}]}).json()["lote"]

    class _Operador:
        id, papel, ativo, username, nome, permissoes = 7, "operador", True, "operador", "Operador", "financeiro"

    main.app.dependency_overrides[get_current_user] = lambda: _Operador()
    corpo = {"acoes": [{"tipo": "conta", "alvo": {"numero_lancamento": ids["sem_conta_numero"], "conta_id": ids["sem_conta_id"]}, "valor": "8.7"}]}
    assert cenario.c.post(f"{P}/aplicar", json=corpo).status_code == 403
    assert cenario.c.post(f"{P}/reverter/{lote}").status_code == 403
    assert cenario.c.get(f"{P}/pendencias", params=MAR).status_code == 200            # ler, pode
    with Session(cenario.engine) as s:
        s.add(UsuarioFazenda(usuario_id=7, fazenda_id=1, contador=True))
        s.commit()
    assert cenario.c.post(f"{P}/aplicar", json=corpo).status_code == 403              # contador: nem escreve
    assert cenario.c.get(f"{P}/pendencias", params=MAR).status_code == 200
    with Session(cenario.engine) as s:
        assert s.get(ContaGerencial, ids["sem_conta_id"]).codigo_conta is None
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "8.20")).one().linha_dre == "CUSTO_VARIAVEL"


@pytest.fixture
def em_maio_de_2031(monkeypatch):
    import fazenda.rules.datas as datas

    monkeypatch.setattr(datas, "agora_local", lambda agora=None: datetime(2031, 5, 10, 12, 0))


def _fechar_marco(cenario):
    r = cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={"forcar": True, "motivo": "fechamento do teste"})
    assert r.status_code == 201, r.text


def test_mes_fechado_trava_o_lancamento_mas_a_conta_do_plano_avisa(cenario, em_maio_de_2031):  # noqa: F811
    ids = _com_pendencias(cenario)
    _fechar_marco(cenario)
    fila = _fila(cenario)
    sem = _linhas(fila, "sem_codigo_conta")[0]
    assert sem["mes_fechado"] and sem["meses_fechados"] == ["2031-03"]
    assert sem["acoes"]["conta"] is False and "reabra o mês" in sem["travas"]["conta"] and "março/2031" in sem["travas"]["conta"]
    silagem = _linhas(fila, "conta_sem_linha_dre")[0]
    assert silagem["acoes"]["linha_dre"] is True and silagem["acoes"]["conta"] is False

    # Lançamento em mês fechado → 409, e o lote inteiro fica sem gravar (a ação boa não passa).
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [
        {"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"},
        {"tipo": "conta", "alvo": {"numero_lancamento": ids["sem_conta_numero"], "conta_id": ids["sem_conta_id"]}, "valor": "8.7"}]})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["codigo"] == "mes_fechado" and d["meses"] == ["2031-03"] and "reabr" in d["mensagem"] and d["erros"][0]["indice"] == 1
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "natureza", "alvo": {"numero_lancamento": ids["silagem"]}, "valor": "CAPITAL"}]})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "mes_fechado"
    with Session(cenario.engine) as s:
        assert s.get(ContaGerencial, ids["sem_conta_id"]).codigo_conta is None
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "8.20")).one().linha_dre is None

    # A conta do plano segue a regra do Fechamento (vale para todos os meses): grava e AVISA.
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [
        {"tipo": "linha_dre", "alvo": {"codigo": "8.20"}, "valor": "CUSTO_VARIAVEL"},
        {"tipo": "natureza", "alvo": {"codigo": "8.4"}, "valor": "FINANCIAMENTO"}]})
    assert r.status_code == 200 and r.json()["aplicadas"] == 2
    assert len(r.json()["avisos"]) == 2 and all("março/2031" in a and "fechado" in a for a in r.json()["avisos"])
    assert cenario.get("/financeiro/fechamento/2031-03")["mudou_desde_o_fechamento"] is True


def test_desfazer_em_mes_fechado_exige_reabrir(cenario, em_maio_de_2031):  # noqa: F811
    ids = _com_pendencias(cenario)
    lote = cenario.c.post(f"{P}/aplicar", json={"acoes": [
        {"tipo": "conta", "alvo": {"numero_lancamento": ids["sem_conta_numero"], "conta_id": ids["sem_conta_id"]}, "valor": "8.7"}]}).json()["lote"]
    _fechar_marco(cenario)
    r = cenario.c.post(f"{P}/reverter/{lote}")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "mes_fechado"
    with Session(cenario.engine) as s:
        assert s.get(ContaGerencial, ids["sem_conta_id"]).codigo_conta == "8.7"
    assert cenario.c.post("/financeiro/fechamento/2031-03/reabrir", json={"motivo": "corrigir a classificação"}).status_code == 201
    r = cenario.c.post(f"{P}/reverter/{lote}")
    assert r.status_code == 200 and r.json()["revertidas"] == 1
    with Session(cenario.engine) as s:
        assert s.get(ContaGerencial, ids["sem_conta_id"]).codigo_conta is None


def test_mes_fechado_sem_a_flag_nao_trava_nada(cenario, em_maio_de_2031):  # noqa: F811
    """A trava do mês só existe com as regras novas: desligadas, o Fechamento nem fecha."""
    _plano(cenario, "8.20", "AUD Silagem comprada")
    _lancar(cenario, "AUD-Silo", "despesa", [_item("Silagem", "8.20", 700)])
    id_sem = _sem_conta_no_banco(cenario, "LC-2031-90001")
    assert cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={"forcar": True, "motivo": "x"}).status_code == 409
    l = next(x for x in _linhas(_fila(cenario), "sem_codigo_conta") if x["conta_id"] == id_sem)
    assert l["mes_fechado"] is False and l["acoes"]["conta"] is True
    r = cenario.c.post(f"{P}/aplicar", json={"acoes": [{"tipo": "conta", "alvo": {"numero_lancamento": "LC-2031-90001", "conta_id": id_sem}, "valor": "8.7"}]})
    assert r.status_code == 200


# ═══════════════════════════ contrato com o Fechamento do mês ═════════════════
def test_checklist_do_fechamento_leva_para_a_tela_classificar(cenario):  # noqa: F811
    cenario.ligar_regras_v2()
    item = next(c for c in cenario.get("/financeiro/fechamento/2031-03")["checklist"] if c["id"] == "sem_conta")
    assert item["destino"] == "classificar" and item["rotulo_acao"] == "Classificar"
