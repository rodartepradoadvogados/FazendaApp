"""
Fase A — PR 2 (contas automáticas) e PR 3 (folha pelo bruto e encargos):
cada ponto de criação de lançamento automático, pela API, com a flag
`financeiro_regras_v2` ligada na fazenda 1 e as contas automáticas
configuradas. Ver fazenda/rules/lancamento_automatico.py.

Para cada origem: a nota nasce com `codigo_conta`, com itens marcados com
`gerado_por` e a soma dos itens é o `valor_total` (a nota fecha). Mais: a
folha entra pelo bruto, vale/retidos/FGTS a recolher ficam fora da DRE, a guia
não conta o retido duas vezes, a retenção do caixa é obrigação (com as regras
de domínio: só administrador, só parcela de contrato/empreita), e nada disso
acontece na fazenda 2 (flag desligada) nem vaza entre fazendas.

Nenhum dado pessoal real: pessoas fictícias, sem CPF.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContaGerencial, ContaCorrente, ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaPagamento, LancamentoItem,
    ParametroFazenda, Pessoa, PlanoContaGerencial, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

HOJE = date.today()

PLANO_F1 = [
    ("3.1", "Salários", "GASTOS_PESSOAL"),
    ("3.2", "Prestadores de serviço", "GASTOS_PESSOAL"),
    ("3.3", "Prêmios e comissões", "GASTOS_PESSOAL"),
    ("3.4", "FGTS", "GASTOS_PESSOAL"),
    ("1.9", "Vales a receber", "NAO_ENTRA_NA_DRE"),
    ("2.9", "Retidos e encargos a recolher", "NAO_ENTRA_NA_DRE"),
]
CONTAS_AUTOMATICAS_F1 = {
    "folha_salario": "3.1", "contrato": "3.2", "caixa_entrada": "3.3", "encargo_fgts": "3.4",
    "vale": "1.9", "obrigacao_inss_irrf_retidos": "2.9", "caixa_retencao": "2.9",
}


@pytest.fixture
def amb(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auto.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)
    ids: dict[str, int] = {}
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.commit()
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
            s.add(ContaCorrente(banco="Banco T", agencia="0001", numero_conta=f"{fid}000-0", fazenda_id=fid))
        s.add(Usuario(id=3, username="gerente", senha_hash=hash_senha("x"), papel="operador", ativo=True))
        s.add(UsuarioFazenda(usuario_id=3, fazenda_id=1))
        s.add(ParametroFazenda(chave="financeiro_regras_v2", fazenda_id=1, grupo="financeiro", label="v2",
                               valor="true", tipo="bool"))
        for cod, nome, linha in PLANO_F1:
            s.add(PlanoContaGerencial(codigo=cod, nome=nome, linha_dre=linha, ativa=True, fazenda_id=1))
        s.commit()
        for chave, nome, tipo, fid in (
            ("ana", "Ana Teste", "Funcionário", 1), ("paulo", "Paulo Teste", "Prestador de serviços", 1),
            ("dora", "Dora Teste", "Diarista", 1), ("edu", "Edu Teste", "Empreiteiro", 1),
            ("bia", "Bia Teste", "Funcionário", 2),
        ):
            p = Pessoa(nome=nome, tipo=tipo, tipo_vinculo="clt", salario_base=3000.0, fazenda_id=fid,
                       data_admissao=date(2024, 1, 10))
            s.add(p)
            s.commit()
            s.refresh(p)
            ids[chave] = p.id
        ids["cc1"] = s.exec(select(ContaCorrente.id).where(ContaCorrente.fazenda_id == 1)).first()

    def _sess():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as c:
        for origem, codigo in CONTAS_AUTOMATICAS_F1.items():
            r = c.put(f"/financeiro/contas-automaticas/{origem}", json={"codigo_conta_gerencial": codigo}, headers=_cab())
            assert r.status_code == 200, r.text
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fid: int = 1, usuario: str | None = None):
    return {"Authorization": f"Bearer {criar_token(usuario or f'admin{fid}', fazenda_id=fid)}"}


def _ok(r):
    assert r.status_code in (200, 201), r.text
    return r.json()


def _nota(engine, numero, fid=1):
    """(parcelas, {papel: (valor, conta, natureza)}) e a nota tem de fechar."""
    with Session(engine) as s:
        contas = s.exec(select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == numero, ContaGerencial.fazenda_id == fid)).all()
        itens = s.exec(select(LancamentoItem).where(
            LancamentoItem.numero_lancamento == numero, LancamentoItem.fazenda_id == fid)).all()
    assert contas, numero
    if itens:
        assert all(it.gerado_por for it in itens)
        assert round(sum(it.valor_total for it in itens), 2) == round(sum(c.valor_total for c in contas), 2)
    return contas, {it.gerado_por: (it.valor_total, it.codigo_conta_gerencial, it.natureza_fin) for it in itens}


def _numero_da_folha(engine, pessoa_id, competencia):
    with Session(engine) as s:
        return s.exec(select(FolhaPagamento.numero_lancamento_gerado).where(
            FolhaPagamento.pessoa_id == pessoa_id, FolhaPagamento.competencia == competencia)).one()


def _folha(c, ids, competencia="2031-03", **extra):
    corpo = {"pessoa_id": ids["ana"], "competencia": competencia, "valor_bruto": 3000, "valor_inss": 240,
             "valor_fgts": 240, "status": "pendente", **extra}
    return _ok(c.post("/cadastro/folha-pagamento", json=corpo, headers=_cab()))


def _dre(c, ini, fim, fid=1, regime="competencia"):
    return _ok(c.get("/financeiro/dre", params={"data_inicio": ini, "data_fim": fim, "regime": regime}, headers=_cab(fid)))


def _linha(d, chave):
    return next(x["valor"] for x in d["cascata"] if x["chave"] == chave)


# =============================================================================
# Folha (PR 3: pelo bruto e encargos)
# =============================================================================
def test_folha_nasce_com_conta_e_itens_pelo_bruto(amb):
    c, engine, ids = amb
    _folha(c, ids)
    contas, itens = _nota(engine, _numero_da_folha(engine, ids["ana"], "2031-03"))
    assert contas[0].codigo_conta == "3.1" and contas[0].valor_total == 2760
    assert itens == {
        "folha_salario": (3000.0, "3.1", None),
        "folha_retidos": (-240.0, "2.9", "OBRIGACAO"),
        "folha_fgts_provisao": (240.0, "3.4", None),
        "folha_fgts_a_recolher": (-240.0, "2.9", "OBRIGACAO"),
    }
    d = _dre(c, "2031-03-01", "2031-03-31")
    assert _linha(d, "GASTOS_PESSOAL") == 3240
    assert d["nao_classificado"]["total"] == 0


def test_folha_editada_refaz_os_itens(amb):
    c, engine, ids = amb
    folha = _folha(c, ids)
    _ok(c.put(f"/cadastro/folha-pagamento/{folha['id']}", json={
        "pessoa_id": ids["ana"], "competencia": "2031-03", "valor_bruto": 3500, "valor_inss": 280, "valor_ir": 20,
        "valor_fgts": 280, "status": "pendente"}, headers=_cab()))
    contas, itens = _nota(engine, _numero_da_folha(engine, ids["ana"], "2031-03"))
    assert contas[0].valor_total == 3200
    assert itens["folha_salario"][0] == 3500 and itens["folha_retidos"][0] == -300
    assert itens["folha_fgts_provisao"][0] == 280
    assert _linha(_dre(c, "2031-03-01", "2031-03-31"), "GASTOS_PESSOAL") == 3780


def test_vale_em_dinheiro_mais_folha_igual_bruto_sem_dupla_contagem(amb):
    """O vale em dinheiro é adiantamento (fora da DRE) e volta pelo desconto
    na folha: o pessoal é o bruto, não bruto + vale."""
    c, engine, ids = amb
    vale = _ok(c.post("/cadastro/vales", json={
        "pessoa_id": ids["ana"], "valor_total": 200.0, "forma_pagamento": "pix", "data_pagamento": "2031-03-10",
        "parcelas": 1, "competencia_inicio": "2031-03", "conta_corrente_id": ids["cc1"]}, headers=_cab()))
    _contas_vale, itens_vale = _nota(engine, vale["numero_lancamento_gerado"])
    assert itens_vale == {"vale": (200.0, "1.9", "ADIANTAMENTO")}
    _folha(c, ids)
    _contas, itens = _nota(engine, _numero_da_folha(engine, ids["ana"], "2031-03"))
    assert itens["folha_vale"] == (-200.0, "1.9", "ADIANTAMENTO")
    d = _dre(c, "2031-03-01", "2031-03-31")
    assert _linha(d, "GASTOS_PESSOAL") == 3240
    adiantamento = next(g for g in d["fora_da_dre"]["grupos"] if g["natureza"] == "ADIANTAMENTO")
    assert adiantamento["liquido"] == 0  # deu 200, recebeu 200 de volta na folha


def test_folha_excluida_leva_os_itens_junto(amb):
    c, engine, ids = amb
    folha = _folha(c, ids)
    numero = _numero_da_folha(engine, ids["ana"], "2031-03")
    _ok(c.delete(f"/cadastro/folha-pagamento/{folha['id']}", headers=_cab()))
    with Session(engine) as s:
        assert s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == numero)).all() == []


def test_ferias_e_13_nascem_com_conta(amb):
    c, engine, ids = amb
    ferias = _ok(c.post("/cadastro/ferias", json={
        "pessoa_id": ids["ana"], "periodo_aquisitivo_inicio": "2030-01-10", "periodo_aquisitivo_fim": "2031-01-09",
        "dias_direito": 30, "dias_gozados": 30, "data_inicio_gozo": "2031-03-01", "data_fim_gozo": "2031-03-30",
        "status": "pendente"}, headers=_cab()))
    contas, itens = _nota(engine, ferias["numero_lancamento_gerado"])
    # Sem conta própria de férias: usa a de salários (reserva).
    assert list(itens) == ["ferias_bruto"] and itens["ferias_bruto"][1] == "3.1" and contas[0].codigo_conta == "3.1"
    decimo = _ok(c.post("/cadastro/decimo-terceiro", json={
        "pessoa_id": ids["ana"], "ano": 2031, "parcela": "unica", "meses_trabalhados": 12,
        "valor_inss": 240, "valor_ir": 10, "status": "pendente"}, headers=_cab()))
    _contas, itens = _nota(engine, decimo["numero_lancamento_gerado"])
    assert itens["decimo_bruto"] == (3000.0, "3.1", None)
    assert itens["decimo_retidos"] == (-250.0, "2.9", "OBRIGACAO")
    # 13º sem provisão mensal (decisão do dono): cai inteiro na competência dele.
    assert _linha(_dre(c, "2031-12-01", "2031-12-31"), "GASTOS_PESSOAL") == 3000


def test_rescisao_nasce_com_conta_e_itens(amb):
    c, engine, ids = amb
    sim = _ok(c.post("/cadastro/rescisoes", json={
        "pessoa_id": ids["ana"], "tipo_rescisao": "sem_justa_causa", "data_desligamento": "2031-05-20",
        "dias_ferias_vencidas": 0, "aviso_previo_trabalhado": False, "valor_inss": 100}, headers=_cab()))
    fechada = _ok(c.post(f"/cadastro/rescisoes/{sim['id']}/fechar", json={"forma_lancamento": "detalhado"}, headers=_cab()))
    contas, itens = _nota(engine, fechada["numero_lancamento_gerado"])
    assert len(contas) > 1  # detalhado: uma parcela por verba, os itens são da nota inteira
    assert itens["rescisao_verbas"][1] == "3.1"
    assert itens["rescisao_retidos"] == (-100.0, "2.9", "OBRIGACAO")


# =============================================================================
# Guias (PR 3: o retido e o provisionado não contam duas vezes)
# =============================================================================
def _guia(c, tipo, principal, multa=0.0, competencia="2031-03"):
    return _ok(c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": tipo, "competencia": competencia, "valor_principal": principal, "valor_multa": multa,
        "data_vencimento": "2031-04-20"}, headers=_cab()))


def test_guia_fgts_com_provisao_vira_obrigacao(amb):
    c, engine, ids = amb
    _folha(c, ids)
    guia = _guia(c, "fgts", 240.0, multa=12.0)
    _contas, itens = _nota(engine, guia["numero_lancamento"])
    assert itens["guia_provisionado"] == (240.0, "2.9", "OBRIGACAO")
    assert itens["guia_multa_juros"][0] == 12.0 and "guia_encargo_fgts" not in itens
    d = _dre(c, "2031-03-01", "2031-03-31")
    assert _linha(d, "GASTOS_PESSOAL") == 3240  # a provisão da folha, nada a mais pela guia
    assert _linha(d, "OUTRAS_REC_DESP") == -12


def test_guia_dctf_retidos_nao_contam_duas_vezes(amb):
    """Guia de 320 = 240 de INSS retido do funcionário + 80 patronal: a DRE soma
    só os 80 de encargo (o retido já está no bruto)."""
    c, engine, ids = amb
    _folha(c, ids)
    guia = _guia(c, "dctf", 320.0)
    _contas, itens = _nota(engine, guia["numero_lancamento"])
    assert itens["guia_retidos"] == (240.0, "2.9", "OBRIGACAO")
    assert itens["guia_encargo_patronal"][0] == 80.0
    assert _linha(_dre(c, "2031-03-01", "2031-03-31"), "GASTOS_PESSOAL") == 3240 + 80


# =============================================================================
# Contrato, empreita, diária (PR 2) e retenção do caixa (PR 3)
# =============================================================================
def _contrato(c, ids, valor=2000.0, venc=None):
    venc = venc or HOJE
    r = _ok(c.post("/cadastro/contratos", json={
        "pessoa_id": ids["paulo"], "descricao": "Serviço de curral", "valor_total": valor, "forma_pagamento": "mensal",
        "parcelas": [{"data_vencimento": venc.isoformat(), "valor": valor}]}, headers=_cab()))
    return r["parcelas"][0]["numero_lancamento_gerado"]


def _combinar(c, pessoa_id, valor=10.0):
    _ok(c.put(f"/cadastro/caixa-funcionarios/{pessoa_id}/retencao", json={
        "forma": "percentual", "valor": valor, "inicio": "2026-01-01", "autorizada": True}, headers=_cab()))


def test_contrato_empreita_e_etapa_nascem_com_conta(amb):
    c, engine, ids = amb
    contas, itens = _nota(engine, _contrato(c, ids))
    assert itens == {"contrato_bruto": (2000.0, "3.2", None)} and contas[0].codigo_conta == "3.2"
    emp = _ok(c.post("/cadastro/empreitadas", json={
        "pessoa_id": ids["edu"], "descricao": "Cerca", "valor_total": 900.0, "tipo_pagamento": "mensal",
        "parcelas": [{"data_vencimento": "2031-04-04", "valor": 900.0}]}, headers=_cab()))
    numero = emp["parcelas"][0]["numero_lancamento_gerado"]
    _contas, itens = _nota(engine, numero)
    assert itens == {"empreita_bruto": (900.0, "3.2", None)}  # empreita usa a conta de contratos (reserva)
    etapas = _ok(c.post("/cadastro/empreitadas", json={
        "pessoa_id": ids["edu"], "descricao": "Curral", "valor_total": 500.0, "tipo_pagamento": "por_etapa",
        "etapas": [{"nome": "Base", "valor": 500.0}]}, headers=_cab()))
    etapa = etapas["etapas"][0]
    feita = _ok(c.put(f"/cadastro/empreitadas/{etapas['id']}/etapas/{etapa['id']}/concluir", headers=_cab()))
    numero_etapa = feita["etapas"][0]["numero_lancamento_gerado"]
    assert _nota(engine, numero_etapa)[1] == {"empreita_bruto": (500.0, "3.2", None)}


def test_retencao_do_caixa_no_contrato_e_obrigacao_e_o_custo_fica_no_bruto(amb):
    c, engine, ids = amb
    _combinar(c, ids["paulo"])
    numero = _contrato(c, ids)
    conta = _nota(engine, numero)[0][0]
    corpo = {"data_pagamento": HOJE.isoformat(), "valor_pago": 2000.0, "forma_pagamento": "pix",
             "retencao_caixa": {"modo": "percentual", "valor": 10.0}}
    # Regra de domínio intacta: só o administrador retém.
    assert c.put(f"/financeiro/lancamentos/{conta.id}/pagar", json=corpo, headers=_cab(usuario="gerente")).status_code == 403
    _ok(c.put(f"/financeiro/lancamentos/{conta.id}/pagar", json=corpo, headers=_cab()))
    contas, itens = _nota(engine, numero)
    assert contas[0].valor_total == 1800
    assert itens == {"contrato_bruto": (2000.0, "3.2", None), "contrato_retencao": (-200.0, "2.9", "OBRIGACAO")}
    with Session(engine) as s:
        retencao = s.exec(select(ContaGerencial).where(
            ContaGerencial.tipo_documento == "Caixa do funcionário", ContaGerencial.fazenda_id == 1)).one()
    assert _nota(engine, retencao.numero_lancamento)[1] == {"caixa_retencao": (200.0, "2.9", "OBRIGACAO")}
    mes = HOJE.replace(day=1)
    fim = (mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    d = _dre(c, mes.isoformat(), fim.isoformat(), regime="caixa")
    assert _linha(d, "GASTOS_PESSOAL") == 2000  # o bruto, nem 1.800 nem 2.000 + 200
    # Estorno do pagamento devolve o valor à parcela e refaz os itens.
    _ok(c.post(f"/financeiro/lancamentos/{conta.id}/estornar", json={"motivo": "erro"}, headers=_cab()))
    assert _nota(engine, numero)[1] == {"contrato_bruto": (2000.0, "3.2", None)}


def test_diaria_pagamento_com_retencao_e_acerto(amb):
    c, engine, ids = amb
    _combinar(c, ids["dora"], valor=20.0)
    inicio = HOJE - timedelta(days=1)
    diaria = _ok(c.post("/cadastro/diarias", json={"pessoa_id": ids["dora"], "valor_diaria": 100.0,
                                                   "data_inicio": inicio.isoformat()}, headers=_cab()))
    pago = _ok(c.post(f"/cadastro/diarias/{diaria['id']}/pagamentos", json={
        "data_pagamento": HOJE.isoformat(), "valor": 100.0, "forma_pagamento": "pix",
        "retencao_caixa": {"modo": "percentual", "valor": 20.0}}, headers=_cab()))
    assert _nota(engine, pago["numero_lancamento_gerado"])[1] == {
        "diaria_bruto": (100.0, "3.2", None), "diaria_retencao": (-20.0, "2.9", "OBRIGACAO")}
    encerrada = _ok(c.put(f"/cadastro/diarias/{diaria['id']}/encerrar", json={
        "data_encerramento": HOJE.isoformat(), "data_vencimento": (HOJE + timedelta(days=10)).isoformat()}, headers=_cab()))
    with Session(engine) as s:
        from fazenda.models import Diaria
        numero = s.get(Diaria, encerrada["id"]).numero_lancamento_gerado
    _contas, itens = _nota(engine, numero)
    assert list(itens) == ["diaria_bruto"] and itens["diaria_bruto"][1] == "3.2"


def test_vale_avulso_e_adiantamento(amb):
    c, engine, ids = amb
    emp = _ok(c.post("/cadastro/empreitadas", json={
        "pessoa_id": ids["edu"], "descricao": "Cerca", "valor_total": 900.0, "tipo_pagamento": "mensal",
        "parcelas": [{"data_vencimento": "2031-04-04", "valor": 900.0}]}, headers=_cab()))
    r = _ok(c.post("/cadastro/vale-avulso", json={
        "origem_tipo": "empreitada", "origem_id": emp["id"], "valor": 300.0, "forma_pagamento": "pix",
        "data_pagamento": "2031-03-24", "conta_corrente_id": ids["cc1"]}, headers=_cab()))
    vale = r["vale"]
    assert _nota(engine, vale["numero_lancamento_gerado"])[1] == {"vale": (300.0, "1.9", "ADIANTAMENTO")}
    # A parcela da empreita foi abatida pelo vale: custo = contratado, vale volta.
    _contas, itens = _nota(engine, emp["parcelas"][0]["numero_lancamento_gerado"])
    assert itens == {"empreita_bruto": (900.0, "3.2", None), "empreita_vale": (-300.0, "1.9", "ADIANTAMENTO")}


def test_caixa_do_funcionario_entrada_e_estorno(amb):
    c, engine, ids = amb
    r = _ok(c.post("/cadastro/caixa-funcionarios/entradas", json={
        "pessoa_ids": [ids["ana"]], "tipo": "bonificacao", "data": "2031-03-15", "motivo": "Safra", "valor": 500.0},
        headers=_cab()))
    numero = r["criados"][0]["numero_lancamento"]
    assert _nota(engine, numero)[1] == {"caixa_entrada": (500.0, "3.3", None)}
    mov = r["criados"][0]["movimento_id"]
    _ok(c.post(f"/cadastro/caixa-funcionarios/{ids['ana']}/movimentos/{mov}/estornar", json={"motivo": "engano"},
               headers=_cab()))
    with Session(engine) as s:
        estorno = s.exec(select(ContaGerencial).where(
            ContaGerencial.tipo_documento == "Estorno caixa do funcionário", ContaGerencial.fazenda_id == 1)).one()
    _contas, itens = _nota(engine, estorno.numero_lancamento)
    assert itens == {"caixa_entrada": (500.0, "3.3", None)} and _contas[0].tipo == "receita"


# =============================================================================
# Flag desligada e multi-tenant
# =============================================================================
def test_flag_desligada_cria_como_antes(amb):
    """Fazenda 2 sem a flag: a folha nasce sem conta e sem item, como sempre."""
    c, engine, ids = amb
    _ok(c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": ids["bia"], "competencia": "2031-03", "valor_bruto": 3000, "valor_inss": 240, "valor_fgts": 240,
        "status": "pendente"}, headers=_cab(2)))
    numero = _numero_da_folha(engine, ids["bia"], "2031-03")
    contas, itens = _nota(engine, numero, fid=2)
    assert itens == {} and contas[0].codigo_conta is None and contas[0].valor_total == 2760
    d2 = _dre(c, "2031-03-01", "2031-03-31", fid=2)
    assert "regras_v2" not in d2 and d2["nao_classificado"]["total"] == 2760


def test_contas_automaticas_isoladas_por_fazenda(amb):
    c, engine, ids = amb
    # A 2 não usa conta do plano da 1, e não enxerga a configuração da 1.
    assert c.put("/financeiro/contas-automaticas/folha_salario", json={"codigo_conta_gerencial": "3.1"},
                 headers=_cab(2)).status_code == 404
    origens2 = {o["origem"]: o for o in _ok(c.get("/financeiro/contas-automaticas", headers=_cab(2)))["origens"]}
    assert all(o["codigo_conta_gerencial"] is None for o in origens2.values())
    origens1 = {o["origem"]: o for o in _ok(c.get("/financeiro/contas-automaticas", headers=_cab()))["origens"]}
    assert origens1["folha_salario"]["codigo_conta_gerencial"] == "3.1"
    assert origens1["folha_ferias"]["conta_efetiva"] == "3.1" and origens1["folha_ferias"]["conta_efetiva_de"] == "folha_salario"
    # Só administrador configura.
    assert c.put("/financeiro/contas-automaticas/folha_salario", json={"codigo_conta_gerencial": "3.1"},
                 headers=_cab(usuario="gerente")).status_code == 403
    assert c.put("/financeiro/contas-automaticas/inexistente", json={}, headers=_cab()).status_code == 404
    assert c.put("/financeiro/contas-automaticas/vale", json={"natureza_fin": "qualquer"}, headers=_cab()).status_code == 400


def test_sugestao_pelo_nome_do_plano_nao_e_aplicada_sozinha(amb):
    c, engine, ids = amb
    with Session(engine) as s:
        s.add(PlanoContaGerencial(codigo="4.1", nome="Salários e ordenados", ativa=True, fazenda_id=2))
        s.commit()
    origens2 = {o["origem"]: o for o in _ok(c.get("/financeiro/contas-automaticas", headers=_cab(2)))["origens"]}
    assert origens2["folha_salario"]["sugestao"] == {"codigo": "4.1", "nome": "Salários e ordenados"}
    assert origens2["folha_salario"]["codigo_conta_gerencial"] is None


def test_dre_nao_classificado_separa_receita_e_despesa():
    """P1 do PR 2 (motor puro): não classificado soma receita E despesa;
    com as regras v2 os dois lados vêm separados."""
    from fazenda.rules.dre import montar_cascata_dre

    registros = [
        {"codigo_conta": "9.1", "tipo": "receita", "valor": 50.0, "descricao": "Receita sem linha"},
        {"codigo_conta": "9.2", "tipo": "despesa", "valor": 30.0, "descricao": "Despesa sem linha"},
    ]
    antigo = montar_cascata_dre(registros, {})
    assert antigo["nao_classificado"]["total"] == 80 and "total_receita" not in antigo["nao_classificado"]
    novo = montar_cascata_dre(registros, {}, regras_v2=True)["nao_classificado"]
    assert (novo["total_receita"], novo["total_despesa"], novo["liquido"]) == (50, 30, 20)
    assert {c["codigo"]: (c["receita"], c["despesa"]) for c in novo["contas"]} == {"9.1": (50, 0), "9.2": (0, 30)}


# =============================================================================
# Migração a7c4e2d9f1b3 (aditiva e reversível)
# =============================================================================
def test_migracao_contas_automaticas_sobe_desce(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent

    def alembic(*args):
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'mig.db'}", "FAZENDA_TESTING": "1"}
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=backend, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout

    def colunas(tabela):
        conn = sqlite3.connect(tmp_path / "mig.db")
        nomes = {c[1] for c in conn.execute(f"PRAGMA table_info({tabela})")}
        conn.close()
        return nomes

    alembic("upgrade", "f3b8d1c6a9e2")
    conn = sqlite3.connect(tmp_path / "mig.db")
    conn.execute("INSERT INTO lancamento_item (numero_lancamento, produto, valor_total, atualizado_em) "
                 "VALUES ('LC-1', 'Ração', 50.0, '2026-01-01')")
    conn.commit()
    conn.close()
    alembic("upgrade", "a7c4e2d9f1b3")
    assert "gerado_por" in colunas("lancamento_item")
    assert {"fazenda_id", "origem", "codigo_conta_gerencial", "natureza_fin"} <= colunas("conta_padrao_origem")
    conn = sqlite3.connect(tmp_path / "mig.db")
    conn.execute("INSERT INTO lancamento_item (numero_lancamento, produto, valor_total, atualizado_em, gerado_por) "
                 "VALUES ('LC-2', 'Salário', 3000.0, '2026-01-01', 'folha_salario')")
    conn.commit()
    conn.close()
    alembic("downgrade", "f3b8d1c6a9e2")
    assert "gerado_por" not in colunas("lancamento_item") and colunas("conta_padrao_origem") == set()
    conn = sqlite3.connect(tmp_path / "mig.db")
    # O item de gente fica; o gerado pelo sistema sai junto com a coluna.
    assert conn.execute("SELECT numero_lancamento, valor_total FROM lancamento_item").fetchall() == [("LC-1", 50.0)]
    conn.close()
    alembic("upgrade", "head")
