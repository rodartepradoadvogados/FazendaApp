"""
Tela "Classificar" (Relatórios › Resultado): a fila de pendências de classificação
(`GET /financeiro/classificacao/pendencias`), o lote de ações
(`POST .../aplicar`) e a reversão (`POST .../reverter/{lote}`).

Sobre o cenário da auditoria (tests/cenario_auditoria_financeiro.py), com pendências
de classificação acrescentadas por cima. O que trava aqui:
  - a fila FECHA com a DRE (sem classificação e fora da DRE sem motivo);
  - cada motivo, os ids, a sugestão (nunca aplicada sozinha);
  - o lote: tudo ou nada, log por campo, a DRE muda e o Desfazer devolve;
  - flag desligada: nada muda de número e a natureza vem travada com o porquê;
  - isolamento entre fazendas, permissão (só administrador) e mês fechado.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlmodel import Session, select

from fazenda.models import ContaGerencial, LancamentoItem, MigracaoLogFinanceiro, PlanoContaGerencial, UsuarioFazenda
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário)

P = "/financeiro/classificacao"
MAR = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}


def _item(produto, codigo, valor, **kw):
    return {"produto": produto, "codigo_conta_gerencial": codigo, "valor_total": valor, "tipo_item": "servico", **kw}


def _lancar(cenario, nome, tipo, itens, data="2031-03-12", **extra):
    body = {"centro_custo": "Pecuária Leiteira", "fornecedor_cliente": nome, "tipo": tipo, "itens": itens,
            "data_emissao": data, "data_competencia": data, "data_vencimento": "2031-04-20", **extra}
    r = cenario.c.post("/financeiro/lancamentos", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _plano(cenario, codigo, nome, linha=None):
    r = cenario.c.post("/financeiro/plano-contas", json={"codigo": codigo, "nome": nome, "ativa": True})
    assert r.status_code == 200, r.text
    if linha:
        cenario.put(f"/financeiro/plano-contas/{codigo}/linha-dre", {"linha_dre": linha})


def _sem_conta_no_banco(cenario, numero, valor=500.0, data="2031-03-14", fornecedor="AUD-Sem conta", tipo="despesa"):
    """Nota SEM conta e SEM itens (import antigo): cai no fallback da nota."""
    from datetime import date

    with Session(cenario.engine) as s:
        c = ContaGerencial(
            fazenda_id=1, numero_lancamento=numero, tipo=tipo, descricao="Nota sem conta", fornecedor_cliente=fornecedor,
            valor_total=valor, data_competencia=date.fromisoformat(data), data_emissao=date.fromisoformat(data),
            centro_custo="Pecuária Leiteira", parcela_num=1, parcela_total=1, origem="manual")
        s.add(c)
        s.commit()
        return c.id


def _fila(cenario, **extra):
    return cenario.get(f"{P}/pendencias", **{**MAR, **extra})


def _por_motivo(fila):
    return {m["motivo"]: m for m in fila["por_motivo"]}


def _linhas(fila, motivo):
    return [l for l in fila["pendencias"] if l["motivo"] == motivo]


def _com_pendencias(cenario):
    """Cenário + folha sem conta automática (itens gerados) + conta sem linha + nota sem conta, flag LIGADA.
    Devolve os ids úteis."""
    cenario.backfill_itens_automaticos()
    _plano(cenario, "8.20", "AUD Silagem comprada")           # conta sem linha
    n_silagem = _lancar(cenario, "AUD-Silo", "despesa", [_item("Silagem", "8.20", 700)])["numero_lancamento"]
    id_sem = _sem_conta_no_banco(cenario, "LC-2031-90001")
    cenario.ligar_regras_v2()
    return {"silagem": n_silagem, "sem_conta_id": id_sem, "sem_conta_numero": "LC-2031-90001"}


# ═══════════════════════════ a fila ═══════════════════════════════════════════
def test_fila_fecha_com_a_dre_nos_quatro_motivos(cenario):  # noqa: F811
    ids = _com_pendencias(cenario)
    dre = cenario.dre()
    fila = _fila(cenario)
    pm = _por_motivo(fila)

    assert fila["regras_v2"] is True and fila["regime"] == "competencia"
    assert [m["motivo"] for m in fila["por_motivo"]] == [
        "conta_sem_linha_dre", "sem_codigo_conta", "item_sem_conta_automatica", "natureza_nao_informada"]
    assert (pm["conta_sem_linha_dre"]["quantidade"], pm["sem_codigo_conta"]["quantidade"]) == (1, 1)
    assert pm["item_sem_conta_automatica"]["quantidade"] == 2          # salário e FGTS da folha da Ana
    assert pm["natureza_nao_informada"]["quantidade"] == 2             # principal (8.4) e aporte (8.5), fora sem motivo

    # Fecha com a DRE: sem classificação = os três primeiros motivos; fora sem motivo = o quarto.
    nao = dre["nao_classificado"]
    tres = [pm[m] for m in ("conta_sem_linha_dre", "sem_codigo_conta", "item_sem_conta_automatica")]
    assert round(sum(m["total_receita"] for m in tres), 2) == nao["total_receita"]
    assert round(sum(m["total_despesa"] for m in tres), 2) == nao["total_despesa"] == 700 + 500 + 3240
    grupo = next(g for g in dre["fora_da_dre"]["grupos"] if g["natureza"] == "NAO_INFORMADA")
    assert (pm["natureza_nao_informada"]["total_receita"], pm["natureza_nao_informada"]["total_despesa"]) == (grupo["total_receita"], grupo["total_despesa"])
    assert fila["resumo"]["total_pendencias"] == 6 and fila["resumo"]["truncado"] is False

    # ids, fornecedor, descrição, valor, data e conta atual de cada linha.
    silagem = _linhas(fila, "conta_sem_linha_dre")[0]
    assert (silagem["numero_lancamento"], silagem["codigo_conta"], silagem["nome_conta"], silagem["valor"]) == (
        ids["silagem"], "8.20", "AUD Silagem comprada", 700.0)
    assert silagem["conta_no_plano"] and silagem["item_id"] and silagem["conta_id"] and silagem["fornecedor"] == "AUD-Silo"
    assert silagem["tipo"] == "despesa" and silagem["data"] == "2031-03-12" and silagem["centro_custo"] == "Pecuária Leiteira"
    assert silagem["acoes"] == {"conta": True, "linha_dre": True, "natureza": True}

    sem = _linhas(fila, "sem_codigo_conta")[0]
    assert (sem["numero_lancamento"], sem["conta_id"], sem["item_id"], sem["codigo_conta"], sem["valor"]) == (
        ids["sem_conta_numero"], ids["sem_conta_id"], None, None, 500.0)
    assert sem["fornecedor"] == "AUD-Sem conta" and sem["descricao"] == "Nota sem conta"

    folha = _linhas(fila, "item_sem_conta_automatica")
    assert sorted(l["codigo_conta"] for l in folha) == ["(sem conta: FGTS (encargo do empregador))", "(sem conta: Salários e verbas da folha)"]
    assert {l["origem_automatica"] for l in folha} == {"folha_salario", "encargo_fgts"}
    assert all(l["item_id"] and l["conta_no_plano"] is False for l in folha)

    nat = {l["codigo_conta"]: l for l in _linhas(fila, "natureza_nao_informada")}
    assert set(nat) == {"8.4", "8.5"} and nat["8.4"]["valor"] == 5000.0 and nat["8.5"]["tipo"] == "receita"
    assert nat["8.4"]["natureza_atual"] == "NAO_INFORMADA" and nat["8.4"]["acoes"]["natureza"] is True


def test_fila_agrupa_por_motivo_e_por_conta(cenario):  # noqa: F811
    _com_pendencias(cenario)
    _lancar(cenario, "AUD-Silo2", "despesa", [_item("Silagem 2", "8.20", 300)], data="2031-03-20")
    fila = _fila(cenario)
    contas = {(g["motivo"], g["codigo"]): g for g in fila["por_conta"]}
    g = contas[("conta_sem_linha_dre", "8.20")]
    assert (g["quantidade"], g["total_despesa"], g["total_receita"], g["nome"]) == (2, 1000.0, 0.0, "AUD Silagem comprada")
    assert ("natureza_nao_informada", "8.4") in contas and ("sem_codigo_conta", None) in contas


def test_fila_de_uma_nota_com_parcelas_e_itens_soma_por_item(cenario):  # noqa: F811
    _plano(cenario, "8.21", "AUD Mineral sem linha")
    n = _lancar(cenario, "AUD-Parcelado", "despesa", [_item("A", "8.21", 600), _item("B", "8.2", 400)],
                 parcelas=[{"data_vencimento": "2031-04-10", "valor": 500}, {"data_vencimento": "2031-05-10", "valor": 500}])["numero_lancamento"]
    fila = _fila(cenario)
    linhas = [l for l in _linhas(fila, "conta_sem_linha_dre") if l["numero_lancamento"] == n]
    assert len(linhas) == 1 and linhas[0]["valor"] == 600.0 and linhas[0]["parcelas"] == 2


def test_fila_respeita_regime_e_centro(cenario):  # noqa: F811
    _plano(cenario, "8.22", "AUD Sem linha caixa")
    _lancar(cenario, "AUD-Caixa", "despesa", [_item("X", "8.22", 250)], data="2031-03-10",
            data_pagamento="2031-05-02", valor_pago=250)
    assert len(_linhas(_fila(cenario), "conta_sem_linha_dre")) == 1
    assert _linhas(_fila(cenario, regime="caixa"), "conta_sem_linha_dre") == []
    maio = _fila(cenario, regime="caixa", data_inicio="2031-05-01", data_fim="2031-05-31")
    assert [l["data"] for l in _linhas(maio, "conta_sem_linha_dre")] == ["2031-05-02"]
    assert _linhas(_fila(cenario, centro_custo="Agricultura"), "conta_sem_linha_dre") == []
    assert cenario.c.get(f"{P}/pendencias", params={**MAR, "regime": "semanal"}).status_code == 422
    assert cenario.c.get(f"{P}/pendencias", params={"data_inicio": "2031-03-01"}).status_code == 422
    # Apelidos curtos: inicio / fim / centro.
    assert _linhas(cenario.get(f"{P}/pendencias", inicio="2031-03-01", fim="2031-03-31", centro="Agricultura"), "conta_sem_linha_dre") == []


def test_fila_vazia_quando_tudo_esta_classificado(cenario):  # noqa: F811
    cenario.ligar_pr2_pr3()
    cenario.classificar_plano_por_natureza()
    fila = _fila(cenario)
    assert fila["resumo"]["total_pendencias"] == 0 and fila["pendencias"] == [] and fila["ultimo_lote"] is None
    assert all(m["quantidade"] == 0 for m in fila["por_motivo"])
    assert cenario.dre()["nao_classificado"]["total"] == 0


def test_fila_com_regras_antigas_so_lista_o_que_a_regra_antiga_enxerga(cenario):  # noqa: F811
    _plano(cenario, "8.20", "AUD Silagem comprada")
    _lancar(cenario, "AUD-Silo", "despesa", [_item("Silagem", "8.20", 700)])
    _sem_conta_no_banco(cenario, "LC-2031-90001")
    cenario.backfill_itens_automaticos()           # com a flag desligada, a folha gerada é ignorada pelos relatórios
    dre = cenario.dre()
    fila = _fila(cenario)
    pm = _por_motivo(fila)
    assert fila["regras_v2"] is False
    # Sem conta: a nota que entrou sem conta e a folha da Ana (a regra antiga lê a nota, não os itens gerados).
    assert (pm["conta_sem_linha_dre"]["quantidade"], pm["sem_codigo_conta"]["quantidade"]) == (1, 2)
    assert pm["item_sem_conta_automatica"]["quantidade"] == 0 and pm["natureza_nao_informada"]["quantidade"] == 0
    assert round(pm["conta_sem_linha_dre"]["total_despesa"] + pm["sem_codigo_conta"]["total_despesa"], 2) == dre["nao_classificado"]["total"] == 700 + 500 + 2560
    # O que a regra antiga não suporta vem travado, com o porquê.
    bloq = {b["motivo"]: b["porque"] for b in fila["bloqueios"]}
    assert set(bloq) == {"natureza_nao_informada", "item_sem_conta_automatica"} and "regras novas" in bloq["natureza_nao_informada"]
    l = _linhas(fila, "conta_sem_linha_dre")[0]
    assert l["acoes"] == {"conta": True, "linha_dre": True, "natureza": False} and "regras novas" in l["travas"]["natureza"]
    assert l["natureza_atual"] is None


# ═══════════════════════════ sugestões ════════════════════════════════════════
def test_sugestoes_sao_mostradas_mas_nunca_aplicadas(cenario):  # noqa: F811
    ids = _com_pendencias(cenario)
    # (a) item da folha: a conta do plano cujo nome combina com a origem.
    _plano(cenario, "8.9", "AUD Salários e encargos", "GASTOS_PESSOAL")
    # (b) fornecedor que sempre vai para a mesma conta: a nota sem conta dele sugere a conta.
    for i in range(3):
        _lancar(cenario, "AUD-Sem conta", "despesa", [_item(f"Ração {i}", "8.2", 100 + i)], data=f"2031-03-0{i + 1}")
    # (c) irmãs com a mesma linha: a conta nova sugere a linha delas.
    _plano(cenario, "7.1.1", "AUD Insumo A", "CUSTO_VARIAVEL")
    _plano(cenario, "7.1.2", "AUD Insumo B", "CUSTO_VARIAVEL")
    _plano(cenario, "7.1.3", "AUD Insumo C")
    _lancar(cenario, "AUD-C", "despesa", [_item("C", "7.1.3", 90)])
    # (d) pelo nome da conta.
    _plano(cenario, "9.1", "AUD Energia elétrica")
    _lancar(cenario, "AUD-Luz", "despesa", [_item("Luz", "9.1", 80)])
    fila = _fila(cenario)

    folha = {l["origem_automatica"]: l for l in _linhas(fila, "item_sem_conta_automatica")}
    assert folha["folha_salario"]["sugestao"]["tipo"] == "conta" and folha["folha_salario"]["sugestao"]["valor"] == "8.9"
    assert folha["folha_salario"]["sugestao"]["alvo"]["item_id"] == folha["folha_salario"]["item_id"]

    sem = _linhas(fila, "sem_codigo_conta")[0]
    assert sem["sugestao"]["valor"] == "8.2" and "3 de 3" in sem["sugestao"]["motivo"]

    linhas = {l["codigo_conta"]: l for l in _linhas(fila, "conta_sem_linha_dre")}
    assert linhas["7.1.3"]["sugestao"] == {
        "tipo": "linha_dre", "alvo": {"codigo": "7.1.3"}, "valor": "CUSTO_VARIAVEL",
        "rotulo": "Linha da DRE: Custo variável (CPV/CMV)", "motivo": linhas["7.1.3"]["sugestao"]["motivo"]}
    assert "7.1.1" not in linhas and "outras 2 contas de 7.1" in linhas["7.1.3"]["sugestao"]["motivo"]
    assert linhas["9.1"]["sugestao"]["valor"] == "DESPESAS_OPERACIONAIS" and "pelo nome" in linhas["9.1"]["sugestao"]["motivo"].lower()
    # "8.20 Silagem comprada": as irmãs (8.*) discordam, então vale o nome.
    assert linhas["8.20"]["sugestao"]["valor"] == "CUSTO_VARIAVEL"
    nat = {l["codigo_conta"]: l for l in _linhas(fila, "natureza_nao_informada")}
    assert nat["8.4"]["sugestao"]["valor"] == "FINANCIAMENTO" and nat["8.4"]["sugestao"]["alvo"] == {"codigo": "8.4"}
    assert nat["8.5"]["sugestao"]["valor"] == "CAPITAL"

    # Nada foi aplicado: a DRE e o plano continuam como estavam.
    with Session(cenario.engine) as s:
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "7.1.3")).one().linha_dre is None
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == "8.4")).one().natureza_fin is None
        assert s.exec(select(MigracaoLogFinanceiro).where(MigracaoLogFinanceiro.migracao == "classificacao_manual_v1")).all() == []
    assert ids  # (silencia o linter)
