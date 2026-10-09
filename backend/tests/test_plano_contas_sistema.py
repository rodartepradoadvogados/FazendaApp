"""
Contas do sistema 3.03.01.16 (Retenções) e 3.03.01.17 (Vales e adiantamentos)
— `rules/plano_padrao.py`, os `codigo_preferido` dos papéis de retenção e vale
em `rules/lancamento_automatico.py`, a reimportação do CSV do plano e o
backfill `scripts/backfill_contas_origem.py`.

Fazendas do cenário (todas com o grupo 3.03.01 no plano):
  1 = flag ligada, contas do sistema no plano;
  2 = flag ligada, SEM as contas do sistema;
  3 = flag desligada, contas do sistema no plano;
  4 = flag desligada, SEM as contas do sistema.

Nenhum dado pessoal real: pessoas fictícias, sem CPF.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContaCorrente, ContaGerencial, ContaPadraoOrigem, ContratoFazenda, ContratoFazendaModulo, Fazenda,
    LancamentoItem, MigracaoLogFinanceiro, ParametroFazenda, Pessoa, PlanoContaGerencial, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import lancamento_automatico as la
from fazenda.rules.plano_padrao import (
    CODIGO_RETENCOES, CODIGO_VALES, CONTAS_DO_SISTEMA, garantir_contas_do_sistema,
)

HOJE = date.today()

PLANO = [
    ("3.03", "Despesas gerais", None),
    ("3.03.01", "Pessoal", "GASTOS_PESSOAL"),
    ("3.03.01.01", "Salários", None),
    ("3.03.01.02", "Prestadores de serviço", None),
    ("1.9", "Adiantamentos a receber", "NAO_ENTRA_NA_DRE"),
    ("2.9", "Retidos e encargos a recolher", "NAO_ENTRA_NA_DRE"),
]
CONFIG_BASE = {"folha_salario": "3.03.01.01", "contrato": "3.03.01.02", "obrigacao_inss_irrf_retidos": "2.9"}
FAZENDAS_COM_FLAG = (1, 2)
FAZENDAS_COM_CONTAS = (1, 3)


@pytest.fixture
def amb(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pcs.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)
    ids: dict[str, int] = {}
    with Session(engine) as s:
        for fid in (1, 2, 3, 4):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.commit()
        for fid in (1, 2, 3, 4):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
            s.add(ContaCorrente(banco="Banco T", agencia="0001", numero_conta=f"{fid}000-0", fazenda_id=fid))
            if fid in FAZENDAS_COM_FLAG:
                s.add(ParametroFazenda(chave="financeiro_regras_v2", fazenda_id=fid, grupo="financeiro", label="v2",
                                       valor="true", tipo="bool"))
            for cod, nome, linha in PLANO:
                s.add(PlanoContaGerencial(codigo=cod, nome=nome, linha_dre=linha, ativa=True, fazenda_id=fid))
        s.commit()
        for fid in FAZENDAS_COM_CONTAS:
            garantir_contas_do_sistema(s, fid)
        s.commit()
        for fid in (1, 2, 3, 4):
            for chave, nome, tipo in (("ana", "Ana Teste", "Funcionário"), ("paulo", "Paulo Teste", "Prestador de serviços")):
                p = Pessoa(nome=nome, tipo=tipo, tipo_vinculo="clt", salario_base=3000.0, fazenda_id=fid,
                           data_admissao=date(2024, 1, 10))
                s.add(p)
                s.commit()
                s.refresh(p)
                ids[f"{chave}{fid}"] = p.id
            ids[f"cc{fid}"] = s.exec(select(ContaCorrente.id).where(ContaCorrente.fazenda_id == fid)).first()

    def _sess():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as c:
        for fid in (1, 2, 3, 4):
            if fid not in FAZENDAS_COM_FLAG:
                continue  # a configuração de contas automáticas só vale com a flag
            for origem, codigo in CONFIG_BASE.items():
                r = c.put(f"/financeiro/contas-automaticas/{origem}", json={"codigo_conta_gerencial": codigo},
                          headers=_cab(fid))
                assert r.status_code == 200, r.text
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fid: int = 1):
    return {"Authorization": f"Bearer {criar_token(f'admin{fid}', fazenda_id=fid)}"}


def _ok(r):
    assert r.status_code in (200, 201), r.text
    return r.json()


def _nota(engine, numero, fid=1):
    with Session(engine) as s:
        contas = s.exec(select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == numero, ContaGerencial.fazenda_id == fid)).all()
        itens = s.exec(select(LancamentoItem).where(
            LancamentoItem.numero_lancamento == numero, LancamentoItem.fazenda_id == fid)).all()
    assert contas, numero
    if itens:
        assert round(sum(it.valor_total for it in itens), 2) == round(sum(c.valor_total for c in contas), 2)
    return contas, {it.gerado_por: (it.valor_total, it.codigo_conta_gerencial, it.natureza_fin) for it in itens}


def _vale(c, ids, fid=1, valor=200.0):
    return _ok(c.post("/cadastro/vales", json={
        "pessoa_id": ids[f"ana{fid}"], "valor_total": valor, "forma_pagamento": "pix", "data_pagamento": "2031-03-10",
        "parcelas": 1, "competencia_inicio": "2031-03", "conta_corrente_id": ids[f"cc{fid}"]}, headers=_cab(fid)))


def _folha(c, ids, fid=1, competencia="2031-03"):
    return _ok(c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": ids[f"ana{fid}"], "competencia": competencia, "valor_bruto": 3000, "valor_inss": 240,
        "valor_fgts": 240, "status": "pendente"}, headers=_cab(fid)))


def _numero_da_folha(engine, pessoa_id, competencia):
    from fazenda.models import FolhaPagamento

    with Session(engine) as s:
        return s.exec(select(FolhaPagamento.numero_lancamento_gerado).where(
            FolhaPagamento.pessoa_id == pessoa_id, FolhaPagamento.competencia == competencia)).one()


def _combinar(c, pessoa_id, fid=1, valor=10.0):
    _ok(c.put(f"/cadastro/caixa-funcionarios/{pessoa_id}/retencao", json={
        "forma": "percentual", "valor": valor, "inicio": "2026-01-01", "autorizada": True}, headers=_cab(fid)))


def _contrato(c, ids, fid=1, valor=2000.0):
    r = _ok(c.post("/cadastro/contratos", json={
        "pessoa_id": ids[f"paulo{fid}"], "descricao": "Serviço de curral", "valor_total": valor,
        "forma_pagamento": "mensal", "parcelas": [{"data_vencimento": HOJE.isoformat(), "valor": valor}]},
        headers=_cab(fid)))
    return r["parcelas"][0]["numero_lancamento_gerado"]


def _pagar_com_retencao(c, engine, numero, fid=1, valor=2000.0, pct=10.0):
    conta = _nota(engine, numero, fid)[0][0]
    _ok(c.put(f"/financeiro/lancamentos/{conta.id}/pagar", json={
        "data_pagamento": HOJE.isoformat(), "valor_pago": valor, "forma_pagamento": "pix",
        "retencao_caixa": {"modo": "percentual", "valor": pct}}, headers=_cab(fid)))


def _nota_retencao(engine, fid=1):
    with Session(engine) as s:
        return s.exec(select(ContaGerencial).where(
            ContaGerencial.tipo_documento == "Caixa do funcionário", ContaGerencial.fazenda_id == fid)).one()


def _dre(c, ini, fim, fid=1, regime="competencia"):
    return _ok(c.get("/financeiro/dre", params={"data_inicio": ini, "data_fim": fim, "regime": regime}, headers=_cab(fid)))


def _linha(d, chave):
    return next(x["valor"] for x in d["cascata"] if x["chave"] == chave)


def _mes_atual():
    mes = HOJE.replace(day=1)
    return mes.isoformat(), ((mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)).isoformat()


def _plano_rows(engine, fid):
    with Session(engine) as s:
        return {p.codigo: p for p in s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.fazenda_id == fid)).all()}


# =============================================================================
# garantir_contas_do_sistema (rules/plano_padrao.py)
# =============================================================================
def test_lista_canonica_das_duas_contas():
    por_codigo = {c.codigo: c for c in CONTAS_DO_SISTEMA}
    assert set(por_codigo) == {"3.03.01.16", "3.03.01.17"}
    assert (por_codigo[CODIGO_RETENCOES].nome, por_codigo[CODIGO_RETENCOES].natureza_fin) == ("Retenções", "OBRIGACAO")
    assert (por_codigo[CODIGO_VALES].nome, por_codigo[CODIGO_VALES].natureza_fin) == ("Vales e adiantamentos", "ADIANTAMENTO")
    assert all(c.linha_dre == "NAO_ENTRA_NA_DRE" and c.tipo == "despesa" for c in CONTAS_DO_SISTEMA)


def test_garantir_cria_so_onde_existe_o_grupo_e_e_idempotente(amb):
    _c, engine, _ = amb
    rows1 = _plano_rows(engine, 1)
    assert rows1[CODIGO_RETENCOES].nome == "Retenções" and rows1[CODIGO_VALES].nome == "Vales e adiantamentos"
    for codigo, natureza in ((CODIGO_RETENCOES, "OBRIGACAO"), (CODIGO_VALES, "ADIANTAMENTO")):
        assert (rows1[codigo].linha_dre, rows1[codigo].natureza_fin, rows1[codigo].ativa) == ("NAO_ENTRA_NA_DRE", natureza, True)
    assert CODIGO_RETENCOES not in _plano_rows(engine, 2) and CODIGO_VALES not in _plano_rows(engine, 4)

    with Session(engine) as s:
        r = garantir_contas_do_sistema(s, 2)           # cria na 2 (tem o grupo)
        assert r.criadas == [CODIGO_RETENCOES, CODIGO_VALES]
        s.commit()
        r = garantir_contas_do_sistema(s, 2)           # idempotente
        assert r.criadas == [] and r.ja_existiam == [CODIGO_RETENCOES, CODIGO_VALES]
        s.commit()
        total = len(s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.fazenda_id == 2)).all())
        assert total == len(PLANO) + 2
        # Sem o grupo 3.03.01 (fazenda inexistente / sem plano): nada é criado, nem o grupo.
        r = garantir_contas_do_sistema(s, 99)
        assert r.sem_grupo and r.criadas == []
        assert s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.fazenda_id == 99)).all() == []


def test_garantir_nao_sobrescreve_conta_com_outro_nome(amb):
    _c, engine, _ = amb
    with Session(engine) as s:
        conta = s.exec(select(PlanoContaGerencial).where(
            PlanoContaGerencial.fazenda_id == 4, PlanoContaGerencial.codigo == "3.03.01")).one()
        s.add(PlanoContaGerencial(codigo=CODIGO_RETENCOES, nome="Retenção de ISS", fazenda_id=4, ativa=True,
                                  linha_dre="DESPESAS_OPERACIONAIS"))
        s.commit()
        r = garantir_contas_do_sistema(s, 4)
        s.commit()
        assert r.criadas == [CODIGO_VALES] and r.outro_nome == [(CODIGO_RETENCOES, "Retenção de ISS")]
        existente = s.exec(select(PlanoContaGerencial).where(
            PlanoContaGerencial.fazenda_id == 4, PlanoContaGerencial.codigo == CODIGO_RETENCOES)).one()
        assert (existente.nome, existente.linha_dre, existente.natureza_fin) == ("Retenção de ISS", "DESPESAS_OPERACIONAIS", None)
        assert conta.id  # o grupo continua o mesmo


# =============================================================================
# Folha, vale, contrato e caixa caem nas contas certas (flag ligada)
# =============================================================================
def test_vale_e_desconto_do_vale_na_folha_caem_em_vales_e_adiantamentos(amb):
    c, engine, ids = amb
    vale = _vale(c, ids)
    _contas, itens_vale = _nota(engine, vale["numero_lancamento_gerado"])
    assert itens_vale == {"vale": (200.0, CODIGO_VALES, "ADIANTAMENTO")}
    assert _contas[0].codigo_conta == CODIGO_VALES
    _folha(c, ids)
    _contas, itens = _nota(engine, _numero_da_folha(engine, ids["ana1"], "2031-03"))
    assert itens["folha_vale"] == (-200.0, CODIGO_VALES, "ADIANTAMENTO")
    assert itens["folha_salario"][1] == "3.03.01.01"
    d = _dre(c, "2031-03-01", "2031-03-31")
    assert _linha(d, "GASTOS_PESSOAL") == 3240          # o vale não entra: deu 200 e voltou 200
    assert d["nao_classificado"]["total"] == 0          # nada ficou "(sem conta)"
    adiantamento = next(g for g in d["fora_da_dre"]["grupos"] if g["natureza"] == "ADIANTAMENTO")
    assert adiantamento["liquido"] == 0
    # Nome gravado no item é o da conta do plano.
    with Session(engine) as s:
        item = s.exec(select(LancamentoItem).where(LancamentoItem.gerado_por == "folha_vale")).one()
        assert item.nome_conta_gerencial == "Vales e adiantamentos"


def test_retencao_do_caixa_cai_em_retencoes_e_o_custo_fica_no_bruto(amb):
    c, engine, ids = amb
    _combinar(c, ids["paulo1"])
    numero = _contrato(c, ids)
    _pagar_com_retencao(c, engine, numero)
    contas, itens = _nota(engine, numero)
    assert contas[0].valor_total == 1800
    assert itens == {"contrato_bruto": (2000.0, "3.03.01.02", None),
                     "contrato_retencao": (-200.0, CODIGO_RETENCOES, "OBRIGACAO")}
    retencao = _nota_retencao(engine)
    assert _nota(engine, retencao.numero_lancamento)[1] == {"caixa_retencao": (200.0, CODIGO_RETENCOES, "OBRIGACAO")}
    assert retencao.codigo_conta == CODIGO_RETENCOES
    ini, fim = _mes_atual()
    d = _dre(c, ini, fim, regime="caixa")
    assert _linha(d, "GASTOS_PESSOAL") == 2000
    assert d["nao_classificado"]["total"] == 0


def test_vale_avulso_no_contrato_e_devolucao_caem_em_vales(amb):
    c, engine, ids = amb
    emp = _ok(c.post("/cadastro/empreitadas", json={
        "pessoa_id": ids["paulo1"], "descricao": "Cerca", "valor_total": 900.0, "tipo_pagamento": "mensal",
        "parcelas": [{"data_vencimento": "2031-04-04", "valor": 900.0}]}, headers=_cab()))
    r = _ok(c.post("/cadastro/vale-avulso", json={
        "origem_tipo": "empreitada", "origem_id": emp["id"], "valor": 300.0, "forma_pagamento": "pix",
        "data_pagamento": "2031-03-24", "conta_corrente_id": ids["cc1"]}, headers=_cab()))
    assert _nota(engine, r["vale"]["numero_lancamento_gerado"])[1] == {"vale": (300.0, CODIGO_VALES, "ADIANTAMENTO")}
    _contas, itens = _nota(engine, emp["parcelas"][0]["numero_lancamento_gerado"])
    assert itens["empreita_vale"] == (-300.0, CODIGO_VALES, "ADIANTAMENTO")


def test_conta_configurada_a_mao_vence_a_do_sistema(amb):
    c, engine, ids = amb
    _ok(c.put("/financeiro/contas-automaticas/vale", json={"codigo_conta_gerencial": "1.9"}, headers=_cab()))
    vale = _vale(c, ids)
    assert _nota(engine, vale["numero_lancamento_gerado"])[1] == {"vale": (200.0, "1.9", "ADIANTAMENTO")}


def test_sem_a_conta_no_plano_o_item_continua_sem_conta(amb):
    """Fazenda 2: flag ligada, mas o plano não tem 3.03.01.17 -> comportamento de antes."""
    c, engine, ids = amb
    vale = _vale(c, ids, fid=2)
    _contas, itens = _nota(engine, vale["numero_lancamento_gerado"], fid=2)
    assert itens == {"vale": (200.0, None, "ADIANTAMENTO")}
    assert _contas[0].codigo_conta is None


def test_conta_inativa_do_sistema_nao_e_usada(amb):
    c, engine, ids = amb
    with Session(engine) as s:
        conta = s.exec(select(PlanoContaGerencial).where(
            PlanoContaGerencial.fazenda_id == 1, PlanoContaGerencial.codigo == CODIGO_VALES)).one()
        conta.ativa = False
        s.add(conta)
        s.commit()
    vale = _vale(c, ids)
    assert _nota(engine, vale["numero_lancamento_gerado"])[1] == {"vale": (200.0, None, "ADIANTAMENTO")}


def test_tela_de_contas_automaticas_mostra_sugestao_e_conta_do_sistema(amb):
    c, _engine, _ = amb
    origens = {o["origem"]: o for o in _ok(c.get("/financeiro/contas-automaticas", headers=_cab()))["origens"]}
    # "retenc" entrou nas palavras da origem: a sugestão aponta para "Retenções".
    assert origens["caixa_retencao"]["sugestao"] == {"codigo": CODIGO_RETENCOES, "nome": "Retenções"}
    assert origens["vale"]["sugestao"] == {"codigo": CODIGO_VALES, "nome": "Vales e adiantamentos"}
    # A sugestão não é aplicada sozinha; a conta do sistema é só a que vale enquanto não houver escolha.
    assert origens["vale"]["codigo_conta_gerencial"] is None and origens["vale"]["conta_efetiva"] is None
    assert origens["vale"]["conta_do_sistema"] == CODIGO_VALES
    assert origens["caixa_retencao"]["conta_do_sistema"] == CODIGO_RETENCOES
    assert origens["folha_salario"]["conta_do_sistema"] is None
    # Fazenda 2 não tem as contas no plano: nada a oferecer.
    origens2 = {o["origem"]: o for o in _ok(c.get("/financeiro/contas-automaticas", headers=_cab(2)))["origens"]}
    assert origens2["vale"]["conta_do_sistema"] is None
    assert origens2["vale"]["sugestao"]["codigo"] != CODIGO_VALES      # sugere outra conta do plano (1.9), nunca a inexistente


def test_palavras_de_sugestao_de_retencao_comecam_por_retenc():
    assert la.ORIGENS["caixa_retencao"].palavras[0] == "retenc"
    assert la.sugerir_conta("caixa_retencao", [type("C", (), {"codigo": "9.1", "nome": "Retenções do caixa", "ativa": True})()]) \
        == {"codigo": "9.1", "nome": "Retenções do caixa"}


def test_codigo_preferido_so_nos_papeis_de_retencao_e_vale():
    com_vale = {"folha_vale", "rescisao_vale", "contrato_vale", "empreita_vale", "diaria_vale", "vale", "vale_devolucao"}
    com_retencao = {"folha_retencao_caixa", "contrato_retencao", "empreita_retencao", "diaria_retencao", "caixa_retencao"}
    com_codigo = {p for p, info in la.PAPEIS.items() if info.codigo_preferido}
    assert com_codigo == com_vale | com_retencao
    assert all(la.PAPEIS[p].codigo_preferido == CODIGO_VALES for p in com_vale)
    assert all(la.PAPEIS[p].codigo_preferido == CODIGO_RETENCOES for p in com_retencao)


# =============================================================================
# DRE: as contas ficam fora e não alteram o resultado
# =============================================================================
def _lancar(c, codigo, valor, fid=1, data="2031-03-10", tipo="despesa"):
    return _ok(c.post("/financeiro/lancamentos", json={
        "tipo": tipo, "centro_custo": "Pecuária Leiteira", "fornecedor_cliente": "Teste",
        "itens": [{"produto": "Item", "codigo_conta_gerencial": codigo, "valor_total": valor, "tipo_item": "servico"}],
        "data_emissao": data, "data_competencia": data}, headers=_cab(fid)))


def test_dre_conta_de_retencao_e_vale_ficam_fora_e_nao_alteram_o_resultado(amb):
    c, _engine, _ = amb
    _lancar(c, "3.03.01.01", 1000.0)
    base = _dre(c, "2031-03-01", "2031-03-31")
    assert _linha(base, "GASTOS_PESSOAL") == 1000
    resultado = _linha(base, "RESULTADO_LIQUIDO")

    _lancar(c, CODIGO_VALES, 500.0)
    _lancar(c, CODIGO_RETENCOES, 300.0)
    d = _dre(c, "2031-03-01", "2031-03-31")
    # Mesmas linhas da cascata, mesmo resultado: as duas contas estão fora da DRE.
    assert [(x["chave"], x["valor"]) for x in d["cascata"]] == [(x["chave"], x["valor"]) for x in base["cascata"]]
    assert _linha(d, "RESULTADO_LIQUIDO") == resultado == -1000
    assert d["nao_classificado"]["total"] == 0
    fora = {g["natureza"]: g for g in d["fora_da_dre"]["grupos"]}
    assert fora["ADIANTAMENTO"]["total_despesa"] == 500 and fora["OBRIGACAO"]["total_despesa"] == 300
    assert d["fora_da_dre"]["por_natureza"]["ADIANTAMENTO"] == 500
    assert d["fora_da_dre"]["por_natureza"]["OBRIGACAO"] == 300


def test_dre_sem_regras_v2_as_contas_novas_tambem_nao_entram_no_resultado(amb):
    """Fazenda 3 (flag desligada): lançar nas contas novas cai na linha da própria conta (fora da DRE)."""
    c, _engine, _ = amb
    _lancar(c, "3.03.01.01", 1000.0, fid=3)
    base = _dre(c, "2031-03-01", "2031-03-31", fid=3)
    _lancar(c, CODIGO_VALES, 500.0, fid=3)
    _lancar(c, CODIGO_RETENCOES, 300.0, fid=3)
    d = _dre(c, "2031-03-01", "2031-03-31", fid=3)
    assert [(x["chave"], x["valor"]) for x in d["cascata"]] == [(x["chave"], x["valor"]) for x in base["cascata"]]
    assert d["fora_da_dre"]["total"] == 800 and d["nao_classificado"]["total"] == 0


# =============================================================================
# Flag desligada: nada muda
# =============================================================================
def _sem_numeros(dado):
    """Tira o número de lançamento (sequência única do banco: muda de uma fazenda para outra)."""
    if isinstance(dado, dict):
        return {k: _sem_numeros(v) for k, v in dado.items() if k != "numero_lancamento"}
    if isinstance(dado, list):
        return [_sem_numeros(v) for v in dado]
    return dado


def _roda_operacoes_de_folha_e_caixa(c, engine, ids, fid):
    _vale(c, ids, fid=fid)
    _folha(c, ids, fid=fid)
    _combinar(c, ids[f"paulo{fid}"], fid=fid)
    _pagar_com_retencao(c, engine, _contrato(c, ids, fid=fid), fid=fid)


def test_flag_desligada_com_as_contas_no_plano_nada_muda(amb):
    """Fazenda 3 (contas no plano) e 4 (sem as contas), as duas sem a flag, fazem
    as mesmas operações: nenhuma gera item ou conta, e os relatórios saem iguais."""
    c, engine, ids = amb
    for fid in (3, 4):
        _roda_operacoes_de_folha_e_caixa(c, engine, ids, fid)
    with Session(engine) as s:
        for fid in (3, 4):
            assert s.exec(select(LancamentoItem).where(LancamentoItem.fazenda_id == fid)).all() == []
            notas = s.exec(select(ContaGerencial).where(ContaGerencial.fazenda_id == fid)).all()
            assert notas and all(n.codigo_conta is None for n in notas)

    ini, fim = _mes_atual()
    for regime in ("competencia", "caixa"):
        for periodo in (("2031-03-01", "2031-03-31"), (ini, fim)):
            d3 = _sem_numeros(_dre(c, *periodo, fid=3, regime=regime))
            d4 = _sem_numeros(_dre(c, *periodo, fid=4, regime=regime))
            assert d3 == d4
            assert "regras_v2" not in d3
    for rota in ("/financeiro/dre/conferencia",):
        r3 = _sem_numeros(_ok(c.get(rota, params={"data_inicio": ini, "data_fim": fim}, headers=_cab(3))))
        r4 = _sem_numeros(_ok(c.get(rota, params={"data_inicio": ini, "data_fim": fim}, headers=_cab(4))))
        assert r3 == r4


def test_flag_desligada_resposta_de_contas_automaticas_nao_tem_conta_efetiva_nova(amb):
    c, _engine, _ = amb
    origens = {o["origem"]: o for o in _ok(c.get("/financeiro/contas-automaticas", headers=_cab(3)))["origens"]}
    assert origens["vale"]["conta_efetiva"] is None and origens["vale"]["codigo_conta_gerencial"] is None


# =============================================================================
# Reimportação do CSV do plano preserva as contas do sistema
# =============================================================================
CSV_COM_PESSOAL = (
    "N° ct. ger.;Nome ct. ger.;Ativa;Part. ativ.;Fluxo;Tipo F/V;\n"
    "3.03.01;Pessoal;Não;Não;Não;;\n"
    "3.03.01.01;Salários;Sim;Sim;Sim;Fixa;\n"
    "3.01.01.01;Concentrado protéico;Sim;Sim;Sim;Variável;\n"
).encode("windows-1252")
CSV_SEM_PESSOAL = (
    "N° ct. ger.;Nome ct. ger.;Ativa;Part. ativ.;Fluxo;Tipo F/V;\n"
    "3.01.01.01;Concentrado protéico;Sim;Sim;Sim;Variável;\n"
).encode("windows-1252")
CSV_COM_16_DIFERENTE = (
    "N° ct. ger.;Nome ct. ger.;Ativa;Part. ativ.;Fluxo;Tipo F/V;\n"
    "3.03.01;Pessoal;Não;Não;Não;;\n"
    "3.03.01.16;Retenção de ISS;Sim;Sim;Sim;;\n"
).encode("windows-1252")


def _subir_plano(c, csv: bytes, fid: int):
    return c.post("/upload/plano_conta_gerencial", files={"file": ("plano.csv", csv, "text/csv")}, headers=_cab(fid))


def test_reimportar_o_csv_do_plano_preserva_as_contas_do_sistema(amb):
    c, engine, _ = amb
    r = _ok(_subir_plano(c, CSV_COM_PESSOAL, 1))
    assert r["registros"] == 3
    rows = _plano_rows(engine, 1)
    assert set(rows) == {"3.03.01", "3.03.01.01", "3.01.01.01", CODIGO_RETENCOES, CODIGO_VALES}
    assert (rows[CODIGO_RETENCOES].linha_dre, rows[CODIGO_RETENCOES].natureza_fin) == ("NAO_ENTRA_NA_DRE", "OBRIGACAO")
    assert (rows[CODIGO_VALES].linha_dre, rows[CODIGO_VALES].natureza_fin) == ("NAO_ENTRA_NA_DRE", "ADIANTAMENTO")
    # Reimportar de novo: continua com uma só linha de cada, sem duplicar.
    _ok(_subir_plano(c, CSV_COM_PESSOAL, 1))
    with Session(engine) as s:
        assert len(s.exec(select(PlanoContaGerencial).where(
            PlanoContaGerencial.fazenda_id == 1, PlanoContaGerencial.codigo == CODIGO_VALES)).all()) == 1


def test_vale_continua_caindo_na_conta_depois_de_reimportar_o_plano(amb):
    c, engine, ids = amb
    _ok(_subir_plano(c, CSV_COM_PESSOAL, 1))
    for origem, codigo in {"folha_salario": "3.03.01.01"}.items():
        _ok(c.put(f"/financeiro/contas-automaticas/{origem}", json={"codigo_conta_gerencial": codigo}, headers=_cab()))
    vale = _vale(c, ids)
    assert _nota(engine, vale["numero_lancamento_gerado"])[1] == {"vale": (200.0, CODIGO_VALES, "ADIANTAMENTO")}


def test_reimportar_plano_sem_o_grupo_pessoal_nao_cria_as_contas(amb):
    c, engine, _ = amb
    r = _ok(_subir_plano(c, CSV_SEM_PESSOAL, 1))
    assert "contas_do_sistema_criadas" not in r
    assert set(_plano_rows(engine, 1)) == {"3.01.01.01"}


def test_reimportar_com_a_conta_16_de_outro_nome_nao_sobrescreve(amb):
    c, engine, _ = amb
    _ok(_subir_plano(c, CSV_COM_16_DIFERENTE, 1))
    rows = _plano_rows(engine, 1)
    assert rows[CODIGO_RETENCOES].nome == "Retenção de ISS" and rows[CODIGO_RETENCOES].natureza_fin is None
    assert rows[CODIGO_VALES].nome == "Vales e adiantamentos"


def test_reimportar_numa_fazenda_nao_mexe_nas_contas_de_outra(amb):
    c, engine, _ = amb
    _ok(_subir_plano(c, CSV_COM_PESSOAL, 2))   # a 2 não tinha as contas: passa a ter
    assert CODIGO_VALES in _plano_rows(engine, 2)
    assert CODIGO_VALES in _plano_rows(engine, 1) and CODIGO_VALES in _plano_rows(engine, 3)
    assert CODIGO_VALES not in _plano_rows(engine, 4)


def test_ligar_a_flag_pela_tela_garante_as_contas(amb):
    c, engine, _ = amb
    from fazenda.rules.parametros import seed_parametros

    with Session(engine) as s:
        seed_parametros(s)
        if not s.exec(select(ParametroFazenda).where(
                ParametroFazenda.chave == "financeiro_regras_v2", ParametroFazenda.fazenda_id.is_(None))).first():
            # O seed pula a chave porque as fazendas 1 e 2 já têm linha própria: em produção a global existe.
            s.add(ParametroFazenda(chave="financeiro_regras_v2", fazenda_id=None, grupo="financeiro", label="v2",
                                   valor="false", tipo="bool"))
            s.commit()
    assert CODIGO_VALES not in _plano_rows(engine, 4)
    # Desligado -> as contas não aparecem.
    _ok(c.put("/parametros/financeiro_regras_v2", json={"valor": False}, headers=_cab(4)))
    assert CODIGO_VALES not in _plano_rows(engine, 4)
    _ok(c.put("/parametros/financeiro_regras_v2", json={"valor": True}, headers=_cab(4)))
    assert {CODIGO_RETENCOES, CODIGO_VALES} <= set(_plano_rows(engine, 4))
    assert CODIGO_VALES not in _plano_rows(engine, 2)    # outra fazenda: intocada


# =============================================================================
# Backfill (scripts/backfill_contas_origem.py)
# =============================================================================
def _tabelas(engine):
    with Session(engine) as s:
        return (
            [(o.fazenda_id, o.origem, o.codigo_conta_gerencial) for o in s.exec(select(ContaPadraoOrigem).order_by(ContaPadraoOrigem.id)).all()],
            [(i.id, i.codigo_conta_gerencial, i.nome_conta_gerencial, i.valor_total) for i in s.exec(select(LancamentoItem).order_by(LancamentoItem.id)).all()],
            [(n.id, n.valor_total, n.valor_pago, n.codigo_conta) for n in s.exec(select(ContaGerencial).order_by(ContaGerencial.id)).all()],
            len(s.exec(select(MigracaoLogFinanceiro)).all()),
        )


def _historico_sem_contas(c, engine, ids):
    """Fazenda 2 (flag ligada, sem as contas): um vale, o desconto dele na folha e a retenção de um
    contrato -> itens GERADOS sem conta. Depois o plano ganha as contas (migração/reimportação)."""
    _vale(c, ids, fid=2)
    _folha(c, ids, fid=2)
    _combinar(c, ids["paulo2"], fid=2)
    _pagar_com_retencao(c, engine, _contrato(c, ids, fid=2), fid=2)
    with Session(engine) as s:
        sem_conta = [i.gerado_por for i in s.exec(select(LancamentoItem).where(
            LancamentoItem.fazenda_id == 2, LancamentoItem.codigo_conta_gerencial.is_(None))).all()]
        assert sorted(sem_conta) == ["caixa_retencao", "contrato_retencao", "folha_vale", "vale"]
        garantir_contas_do_sistema(s, 2)
        s.commit()


def test_backfill_dry_run_nao_grava_nada(amb):
    c, engine, ids = amb
    from scripts.backfill_contas_origem import executar

    _historico_sem_contas(c, engine, ids)
    antes = _tabelas(engine)
    saida: list[str] = []
    with Session(engine) as s:
        r = executar(s, 2, aplicar=False, repintar_itens=True, saida=saida.append)
    assert [p["origem"] for p in r["plano"].criar_origem] == ["vale", "caixa_retencao"]
    assert len(r["plano"].repintar) == 4 and r["lote"] is None
    assert any("Simulação" in linha for linha in saida)
    assert _tabelas(engine) == antes


def test_backfill_aplicar_grava_origens_e_itens_e_e_idempotente(amb):
    c, engine, ids = amb
    from scripts.backfill_contas_origem import executar

    _historico_sem_contas(c, engine, ids)
    with Session(engine) as s:  # sem --repintar-itens: só as origens
        r = executar(s, 2, aplicar=True, saida=lambda _t: None)
    assert r["linhas"] == 2
    origens, _itens, notas, _log = _tabelas(engine)
    assert {(f, o, cod) for f, o, cod in origens if f == 2} == {(2, "vale", CODIGO_VALES), (2, "caixa_retencao", CODIGO_RETENCOES),
                                                               (2, "folha_salario", "3.03.01.01"), (2, "contrato", "3.03.01.02"),
                                                               (2, "obrigacao_inss_irrf_retidos", "2.9")}
    with Session(engine) as s:
        assert [i for i in s.exec(select(LancamentoItem).where(
            LancamentoItem.fazenda_id == 2, LancamentoItem.gerado_por.in_(["vale", "folha_vale"]))).all()
            if i.codigo_conta_gerencial] == []   # os itens antigos ainda estão sem conta

    with Session(engine) as s:
        r2 = executar(s, 2, aplicar=True, repintar_itens=True, saida=lambda _t: None)
    assert r2["linhas"] == 8                       # 4 itens x (conta + nome)
    lote = r2["lote"]
    with Session(engine) as s:
        por_papel = {i.gerado_por: (i.codigo_conta_gerencial, i.nome_conta_gerencial) for i in s.exec(
            select(LancamentoItem).where(LancamentoItem.fazenda_id == 2, LancamentoItem.gerado_por.in_(
                ["vale", "folha_vale", "contrato_retencao", "caixa_retencao"]))).all()}
        assert por_papel == {
            "vale": (CODIGO_VALES, "Vales e adiantamentos"), "folha_vale": (CODIGO_VALES, "Vales e adiantamentos"),
            "contrato_retencao": (CODIGO_RETENCOES, "Retenções"), "caixa_retencao": (CODIGO_RETENCOES, "Retenções"),
        }
        # valor_total / valor_pago nunca mudam.
        assert [(n[1], n[2]) for n in _tabelas(engine)[2]] == [(n[1], n[2]) for n in notas]
        logs = s.exec(select(MigracaoLogFinanceiro).where(MigracaoLogFinanceiro.lote == lote)).all()
        assert len(logs) == 8 and all(lg.fazenda_id == 2 for lg in logs)
        assert all(lg.valor_antes == "null" for lg in logs if lg.campo == "codigo_conta_gerencial")

    # Idempotente: nada a fazer na terceira rodada.
    with Session(engine) as s:
        r3 = executar(s, 2, aplicar=True, repintar_itens=True, saida=lambda _t: None)
    assert r3["lote"] is None and r3["linhas"] == 0
    # Outras fazendas não foram tocadas.
    assert not [o for o in _tabelas(engine)[0] if o[0] == 4]


def test_backfill_reverter_devolve_o_estado_anterior(amb):
    c, engine, ids = amb
    from scripts.backfill_contas_origem import executar

    _historico_sem_contas(c, engine, ids)
    antes = _tabelas(engine)[:3]
    with Session(engine) as s:
        lote = executar(s, 2, aplicar=True, repintar_itens=True, saida=lambda _t: None)["lote"]
    depois = _tabelas(engine)[:3]
    assert depois != antes
    # Outra fazenda não reverte este lote; dry-run da reversão só conta.
    with Session(engine) as s:
        assert executar(s, 1, aplicar=True, reverter=lote, saida=lambda _t: None)["reversao"].revertidas == 0
    with Session(engine) as s:
        assert executar(s, 2, aplicar=False, reverter=lote, saida=lambda _t: None)["reversao"].revertidas == 10
    assert _tabelas(engine)[:3] == depois
    with Session(engine) as s:
        assert executar(s, 2, aplicar=True, reverter=lote, saida=lambda _t: None)["reversao"].revertidas == 10
    assert _tabelas(engine)[:3] == antes
    with Session(engine) as s:
        assert all(lg.revertido_em is not None for lg in s.exec(select(MigracaoLogFinanceiro)).all())


def test_backfill_reverter_nao_sobrescreve_mudanca_manual_posterior(amb):
    c, engine, ids = amb
    from scripts.backfill_contas_origem import executar

    _historico_sem_contas(c, engine, ids)
    with Session(engine) as s:
        lote = executar(s, 2, aplicar=True, repintar_itens=True, saida=lambda _t: None)["lote"]
    # O administrador troca a conta de vale pela 1.9 e o usuário reclassifica um item.
    _ok(c.put("/financeiro/contas-automaticas/vale", json={"codigo_conta_gerencial": "1.9"}, headers=_cab(2)))
    with Session(engine) as s:
        item = s.exec(select(LancamentoItem).where(LancamentoItem.gerado_por == "caixa_retencao",
                                                   LancamentoItem.fazenda_id == 2)).one()
        item.codigo_conta_gerencial = "2.9"
        s.add(item)
        s.commit()
    saida: list[str] = []
    with Session(engine) as s:
        r = executar(s, 2, aplicar=True, reverter=lote, saida=saida.append)["reversao"]
    assert len(r.conflitos) == 2 and r.revertidas == 8
    with Session(engine) as s:
        vale = s.exec(select(ContaPadraoOrigem).where(ContaPadraoOrigem.fazenda_id == 2, ContaPadraoOrigem.origem == "vale")).one()
        assert vale.codigo_conta_gerencial == "1.9"          # escolha do admin preservada
        item = s.exec(select(LancamentoItem).where(LancamentoItem.gerado_por == "caixa_retencao",
                                                   LancamentoItem.fazenda_id == 2)).one()
        assert item.codigo_conta_gerencial == "2.9"          # reclassificação preservada
    assert any("CONFLITO" in linha for linha in saida)


def test_backfill_nao_troca_conta_ja_configurada_nem_cria_sem_conta_no_plano(amb):
    c, engine, ids = amb
    from fazenda.rules import backfill_contas_origem as bf

    # Fazenda 2: vale já configurado à mão; a conta de retenção não existe no plano.
    _ok(c.put("/financeiro/contas-automaticas/vale", json={"codigo_conta_gerencial": "1.9"}, headers=_cab(2)))
    with Session(engine) as s:
        plano = bf.planejar(s, 2, repintar_itens=True)
    assert plano.criar_origem == [] and plano.preencher_origem == [] and plano.repintar == []
    motivos = {m["origem"]: m["motivo"] for m in plano.mantidas}
    assert "já configurada" in motivos["vale"] and "não existe" in motivos["caixa_retencao"]


def test_backfill_preenche_linha_da_origem_que_existe_sem_conta(amb):
    c, engine, ids = amb
    from scripts.backfill_contas_origem import executar

    # Só a natureza foi configurada (sem conta) na fazenda 1: a linha existe vazia.
    _ok(c.put("/financeiro/contas-automaticas/vale", json={"natureza_fin": "ADIANTAMENTO"}, headers=_cab(1)))
    with Session(engine) as s:
        r = executar(s, 1, aplicar=True, saida=lambda _t: None)
    assert [p["origem"] for p in r["plano"].preencher_origem] == ["vale"]
    assert [p["origem"] for p in r["plano"].criar_origem] == ["caixa_retencao"]
    with Session(engine) as s:
        vale = s.exec(select(ContaPadraoOrigem).where(ContaPadraoOrigem.fazenda_id == 1, ContaPadraoOrigem.origem == "vale")).one()
        assert (vale.codigo_conta_gerencial, vale.natureza_fin) == (CODIGO_VALES, "ADIANTAMENTO")
    with Session(engine) as s:
        executar(s, 1, aplicar=True, reverter=r["lote"], saida=lambda _t: None)
        vale = s.exec(select(ContaPadraoOrigem).where(ContaPadraoOrigem.fazenda_id == 1, ContaPadraoOrigem.origem == "vale")).one()
        assert (vale.codigo_conta_gerencial, vale.natureza_fin) == (None, "ADIANTAMENTO")   # a linha fica, vazia como estava
        assert s.exec(select(ContaPadraoOrigem).where(ContaPadraoOrigem.origem == "caixa_retencao",
                                                      ContaPadraoOrigem.fazenda_id == 1)).first() is None


def test_backfill_preserva_nota_com_item_lancado_por_gente(amb):
    c, engine, ids = amb
    from fazenda.rules import backfill_contas_origem as bf

    _historico_sem_contas(c, engine, ids)
    with Session(engine) as s:
        item_vale = s.exec(select(LancamentoItem).where(LancamentoItem.fazenda_id == 2,
                                                        LancamentoItem.gerado_por == "vale")).one()
        numero_vale = item_vale.numero_lancamento
        s.add(LancamentoItem(fazenda_id=2, numero_lancamento=numero_vale, tipo=item_vale.tipo,
                             produto="Item de gente", valor_total=0.0, tipo_item="servico"))
        s.commit()
    with Session(engine) as s:
        plano = bf.planejar(s, 2, repintar_itens=True)
    assert [p["numero_lancamento"] for p in plano.preservadas] == [numero_vale]
    assert "gente" in plano.preservadas[0]["motivo"]
    assert len(plano.repintar) == 3


def test_backfill_csv_e_json_do_log_sem_dado_pessoal(amb, tmp_path):
    c, engine, ids = amb
    from scripts.backfill_contas_origem import executar

    _historico_sem_contas(c, engine, ids)
    caminho = tmp_path / "plano.csv"
    with Session(engine) as s:
        executar(s, 2, aplicar=False, repintar_itens=True, csv_saida=str(caminho), saida=lambda _t: None)
    texto = caminho.read_text(encoding="utf-8-sig")
    assert "criar_origem;vale" in texto and "repintar_item;folha_vale" in texto
    assert "Ana Teste" not in texto and "Paulo Teste" not in texto
    with Session(engine) as s:
        executar(s, 2, aplicar=True, repintar_itens=True, saida=lambda _t: None)
        for lg in s.exec(select(MigracaoLogFinanceiro)).all():
            assert "Teste" not in (lg.valor_antes or "") + (lg.valor_depois or "") + (lg.motivo or "")
            json.loads(lg.valor_depois)
