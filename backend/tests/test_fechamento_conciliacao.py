"""
Fase C5 dos Relatórios — fechamento do mês, conciliação bancária e pacote do
contador (docs/financeiro-fechamento-conciliacao.md).

- parser de extrato (OFX/CSV dos bancos brasileiros) e regra do casamento: puros;
- conciliação, fechamento e pacote pela API, sobre o cenário da auditoria
  (tests/cenario_auditoria_financeiro.py), com isolamento entre fazendas;
- a trava do mês fechado só existe com a flag `financeiro_regras_v2`: desligada,
  nada muda (os goldens de tests/dados continuam valendo — ver
  test_relatorios_cenario_auditoria.py).
"""
from __future__ import annotations

import io
import zipfile
from datetime import date, datetime

import pytest
from sqlmodel import Session, select

from fazenda.models import ExtratoLinha, FechamentoMesEvento, UsuarioFazenda
from fazenda.models.juridico import RegistroImutavelError
from fazenda.rules import conciliacao
from fazenda.rules.extrato_bancario import ExtratoInvalido, ler_extrato, ler_numero
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário)

# ── parser ─────────────────────────────────────────────────────────────────
OFX_SGML = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
CHARSET:1252

<OFX>
<BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL
<BANKACCTFROM><BANKID>001<ACCTID>00000-0</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20310401<DTEND>20310430
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20310415120000[-3:BRT]<TRNAMT>9850.00<FITID>A1<MEMO>PIX RECEBIDO LATICINIO AUD-L1</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20310411<TRNAMT>-3600,00<FITID>A2<CHECKNUM>123<NAME>AUD-L2<MEMO>PAGTO BOLETO</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20310401<TRNAMT>-68.00<FITID>A3<MEMO>TAR PACOTE SERVICOS</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>1234,56<DTASOF>20310430</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""

CSV_BB = (
    "Data;Lançamento;Detalhes;Nº documento;Valor;Tipo Lançamento\n"
    "31/03/2031;Saldo Anterior;;;1.000,00;\n"
    "01/04/2031;Tarifa Pacote de Serviços;Cobrança referente 01/04/2031;123;68,00;Saída\n"
    "15/04/2031;Pix - Recebido;15/04 10:01 LATICINIO;;9.850,00;Entrada\n"
    "15/04/2031;Pix - Recebido;15/04 10:01 LATICINIO;;9.850,00;Entrada\n"
    "30/04/2031;S A L D O;;;20.632,00;\n"
).encode("cp1252")

CSV_CRED_DEB = (
    "Extrato conta corrente\nAgência 0000 Conta 0000-0\n\n"
    "data,descrição,documento,crédito (R$),débito (R$),saldo (R$)\n"
    "2031-04-10,PAG BOLETO AUD-L2,,,\"3.600,00\",\"6.400,00\"\n"
    "2031-04-15,TED RECEBIDA,,\"9.850,00\",,\"16.250,00\"\n"
).encode("utf-8")


def test_ler_numero_formatos_brasileiros_e_americanos():
    assert ler_numero("1.234,56") == 1234.56
    assert ler_numero("-1.234,56") == -1234.56
    assert ler_numero("1,234.56") == 1234.56
    assert ler_numero("68,00 D") == -68.0
    assert ler_numero("(68,00)") == -68.0
    assert ler_numero("R$ 9.850,00") == 9850.0
    assert ler_numero("68.00") == 68.0
    assert ler_numero("1.234") == 1234.0
    assert ler_numero("20,00-") == -20.0
    assert ler_numero("abc") is None and ler_numero("") is None


def test_ofx_sgml_le_movimentos_saldo_e_chave_estavel():
    lido = ler_extrato(OFX_SGML, "extrato.ofx")
    assert lido.formato == "ofx"
    assert [(m.data, m.valor) for m in lido.movimentos] == [
        (date(2031, 4, 15), 9850.0), (date(2031, 4, 11), -3600.0), (date(2031, 4, 1), -68.0)]
    assert lido.movimentos[1].historico == "AUD-L2 · PAGTO BOLETO" and lido.movimentos[1].documento == "123"
    assert (lido.saldo_final, lido.data_saldo) == (1234.56, date(2031, 4, 30))
    assert [m.chave for m in ler_extrato(OFX_SGML).movimentos] == [m.chave for m in lido.movimentos]


def test_csv_banco_do_brasil_tipo_entrada_saida_e_linhas_de_saldo():
    lido = ler_extrato(CSV_BB, "extrato.csv")
    assert lido.formato == "csv"
    assert [(m.data, m.valor) for m in lido.movimentos] == [
        (date(2031, 4, 1), -68.0), (date(2031, 4, 15), 9850.0), (date(2031, 4, 15), 9850.0)]
    # Dois Pix iguais no mesmo dia são duas linhas (chaves diferentes) — e reimportar não muda as chaves.
    assert lido.movimentos[1].chave != lido.movimentos[2].chave
    assert [m.chave for m in ler_extrato(CSV_BB).movimentos] == [m.chave for m in lido.movimentos]
    assert (lido.saldo_final, lido.data_saldo) == (20632.0, date(2031, 4, 30))  # "S A L D O", não o "Saldo Anterior"


def test_csv_credito_debito_com_cabecalho_depois_do_preambulo():
    lido = ler_extrato(CSV_CRED_DEB, "itau.csv")
    assert [(m.data, m.valor) for m in lido.movimentos] == [(date(2031, 4, 10), -3600.0), (date(2031, 4, 15), 9850.0)]
    assert (lido.saldo_final, lido.data_saldo) == (16250.0, date(2031, 4, 15))


def test_arquivo_que_nao_e_extrato_e_recusado_com_mensagem():
    with pytest.raises(ExtratoInvalido):
        ler_extrato(b"", "x.ofx")
    with pytest.raises(ExtratoInvalido, match="cabeçalho"):
        ler_extrato(b"nome,idade\nana,3\n", "x.csv")
    with pytest.raises(ExtratoInvalido):
        ler_extrato(b"PK\x03\x04", "extrato.xlsx")


# ── regra do casamento ─────────────────────────────────────────────────────
def _l(i, d, v, h=""):
    return {"id": i, "data": d, "valor": v, "historico": h}


def _c(i, d, v, desc="", forn="", tipo="lancamento"):
    return {"tipo": tipo, "id": i, "data": d, "valor": v, "descricao": desc, "fornecedor": forn}


def test_sugestao_exige_sinal_valor_e_data_e_usa_o_texto_para_desempatar():
    linhas = [_l(1, date(2031, 4, 11), -3600.0, "PAGTO BOLETO AGROPECUARIA SOL")]
    cands = [
        _c(10, date(2031, 4, 10), -3600.0, "Ração", "Agropecuária Sol"),
        _c(11, date(2031, 4, 11), -3600.0, "Diesel", "Posto Mil"),
        _c(12, date(2031, 4, 11), 3600.0, "Venda"),           # sinal trocado: nunca
        _c(13, date(2031, 4, 20), -3600.0, "Ração", "Agropecuária Sol"),  # fora da tolerância
    ]
    s = conciliacao.sugerir(linhas, cands)[1]
    # 11 está no mesmo dia, mas 10 tem o fornecedor no histórico: 100 − 10 + 20×sim > 100.
    assert s["sugestao"]["id"] == 10 and s["sugestao"]["exata"]
    assert {a["id"] for a in s["alternativas"]} == {11}


def test_cada_movimento_do_sistema_casa_com_uma_linha_so_e_valor_diferente_so_e_alternativa():
    linhas = [_l(1, date(2031, 4, 15), 9850.0), _l(2, date(2031, 4, 15), 9850.0), _l(3, date(2031, 4, 18), -802.20)]
    cands = [_c(20, date(2031, 4, 15), 9850.0), _c(21, date(2031, 4, 18), -760.10)]
    s = conciliacao.sugerir(linhas, cands)
    assert s[1]["sugestao"]["id"] == 20 and s[2]["sugestao"] is None
    assert s[3]["sugestao"] is None and s[3]["alternativas"][0]["id"] == 21
    assert s[3]["alternativas"][0]["diferenca"] == -42.1 and not s[3]["alternativas"][0]["exata"]


# ── API: conciliação ───────────────────────────────────────────────────────
def _importar(cenario, conteudo: bytes, nome="extrato.ofx", conta_id=None):  # noqa: F811
    r = cenario.c.post("/financeiro/conciliacao/importar", data={"conta_corrente_id": str(conta_id or cenario.ids["conta_corrente_id"])},
                       files={"arquivo": (nome, conteudo, "application/octet-stream")})
    return r


def test_importar_sugerir_confirmar_desfazer_e_sem_lancamento(cenario):  # noqa: F811
    r = _importar(cenario, OFX_SGML)
    assert r.status_code == 201, r.text
    assert r.json()["linhas_novas"] == 3 and r.json()["saldo_final"] == 1234.56
    # Reimportar o mesmo arquivo não duplica nada.
    r2 = _importar(cenario, OFX_SGML).json()
    assert (r2["linhas_novas"], r2["linhas_repetidas"]) == (0, 3)

    cc = cenario.ids["conta_corrente_id"]
    s = cenario.get("/financeiro/conciliacao", mes="2031-04", conta_corrente_id=cc)["situacao"]
    por_valor = {l["valor"]: l for l in s["linhas"]}
    l1, l2 = cenario.ids["L"]["L1"]["ids"][0], cenario.ids["L"]["L2"]["ids"][0]
    assert por_valor[9850.0]["sugestao"]["id"] == l1
    assert por_valor[-3600.0]["sugestao"]["id"] == l2 and por_valor[-3600.0]["sugestao"]["dias"] == 1
    assert por_valor[-68.0]["sugestao"] is None
    assert s["contagem"]["sugestoes_exatas"] == 2
    # O que pagou pela conta em abril e não está no extrato (L3, L7, L10) fica "só no sistema".
    assert {m["valor"] for m in s["so_no_sistema"]} == {-1050.0, -600.0, -1200.0}
    assert s["saldos"]["saldo_extrato"] == 1234.56 and s["saldos"]["data"] == "2031-04-30"

    r = cenario.c.post("/financeiro/conciliacao/confirmar-sugestoes", json={"conta_corrente_id": cc, "mes": "2031-04"})
    assert r.status_code == 200 and r.json()["pareadas"] == 2
    tarifa = por_valor[-68.0]["id"]
    assert cenario.c.post(f"/financeiro/conciliacao/linhas/{tarifa}/sem-lancamento", json={"observacao": "estornada"}).status_code == 200
    s = cenario.get("/financeiro/conciliacao", mes="2031-04", conta_corrente_id=cc)["situacao"]
    assert s["contagem"] == {**s["contagem"], "pareadas": 2, "pendentes": 0, "sem_lancamento": 1}
    assert {l["par"]["id"] for l in s["linhas"] if l["status"] == "pareado"} == {l1, l2}

    # Lançamento já pareado não pareia de novo; desfazer devolve a linha para pendente.
    linha_l1 = next(l for l in s["linhas"] if l["valor"] == 9850.0)["id"]
    assert cenario.c.post(f"/financeiro/conciliacao/linhas/{tarifa}/desfazer").json()["status"] == "pendente"
    r = cenario.c.post(f"/financeiro/conciliacao/linhas/{tarifa}/parear", json={"lancamento_id": l1})
    assert r.status_code == 409
    assert cenario.c.post(f"/financeiro/conciliacao/linhas/{linha_l1}/desfazer").status_code == 200
    r = cenario.c.post(f"/financeiro/conciliacao/linhas/{linha_l1}/parear", json={"lancamento_id": l2})
    assert r.status_code == 409 and "Entrada" in r.json()["detail"]  # sinal trocado
    assert cenario.c.post(f"/financeiro/conciliacao/linhas/{linha_l1}/parear", json={"lancamento_id": l1}).status_code == 200


def test_conciliacao_isolada_por_fazenda(cenario):  # noqa: F811
    assert _importar(cenario, OFX_SGML).status_code == 201
    linha = cenario.get("/financeiro/conciliacao", mes="2031-04")["situacao"]["linhas"][0]["id"]
    cenario.estado["fazenda_id"] = 2
    try:
        assert cenario.get("/financeiro/conciliacao", mes="2031-04")["contas"] == []
        assert cenario.c.post(f"/financeiro/conciliacao/linhas/{linha}/desfazer").status_code == 404
        assert _importar(cenario, OFX_SGML).status_code == 404  # a conta é da fazenda 1
    finally:
        cenario.estado["fazenda_id"] = 1


# ── API: fechamento ────────────────────────────────────────────────────────
@pytest.fixture
def em_maio_de_2031(monkeypatch):
    import fazenda.rules.datas as datas

    monkeypatch.setattr(datas, "agora_local", lambda agora=None: datetime(2031, 5, 10, 12, 0))


def test_fechar_exige_a_flag_e_o_mes_terminado(cenario, em_maio_de_2031):  # noqa: F811
    r = cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={"forcar": True, "motivo": "teste de fechamento"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "regras_v2_desligadas"
    cenario.ligar_regras_v2()
    r = cenario.c.post("/financeiro/fechamento/2031-05/fechar", json={"forcar": True, "motivo": "teste de fechamento"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "mes_em_curso"
    assert cenario.c.post("/financeiro/fechamento/2031-13/fechar", json={}).status_code == 422


def test_checklist_fechar_com_pendencias_trava_e_reabrir_com_motivo(cenario, em_maio_de_2031):  # noqa: F811
    cenario.ligar_regras_v2()
    m = cenario.get("/financeiro/fechamento/2031-03")
    ids = {c["id"]: c for c in m["checklist"]}
    assert set(ids) == {"sem_conta", "natureza", "contas_automaticas", "saldo_abertura", "cartao", "folha", "conciliacao", "depreciacao"}
    assert not ids["saldo_abertura"]["ok"]  # a conta do cenário não tem saldo de abertura
    assert not ids["folha"]["ok"]  # a folha de março da Ana está pendente
    assert m["status"] == "aberto" and m["pendencias"] >= 2

    r = cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "pendencias"
    assert cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={"forcar": True}).status_code == 422
    r = cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={"forcar": True, "motivo": "Contador pediu o fechamento"})
    assert r.status_code == 201, r.text
    ev = r.json()["evento"]
    assert ev["acao"] == "fechar" and ev["usuario"] == "auditoria" and len(ev["retrato_sha256"]) == 64
    assert ev["pendencias_no_fechamento"] >= 2
    dre = cenario.dre()
    assert r.json()["retrato"]["dre_competencia"]["linhas"]["RESULTADO_LIQUIDO"] == cenario.linha(dre, "RESULTADO_LIQUIDO")

    m = cenario.get("/financeiro/fechamento/2031-03")
    assert m["status"] == "fechado" and m["mudou_desde_o_fechamento"] is False
    meses = {x["mes"]: x for x in cenario.get("/financeiro/fechamento/meses", ate="2031-05")["meses"]}
    assert meses["2031-03"]["status"] == "fechado" and meses["2031-04"]["status"] == "aberto" and meses["2031-05"]["status"] == "em_curso"

    # Com o mês fechado: editar, baixar, estornar, excluir, mudar natureza e lançar em março → 409.
    L = cenario.ids["L"]
    l2, l4 = L["L2"]["ids"][0], L["L4"]["ids"][0]
    r = cenario.c.put(f"/financeiro/lancamentos/{l2}", json={"descricao": "x"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "mes_fechado" and r.json()["detail"]["meses"] == ["2031-03"]
    assert "reabrir" in r.json()["detail"]["mensagem"]
    assert cenario.c.post(f"/financeiro/lancamentos/{l4}/estornar", json={}).status_code == 409
    assert cenario.c.put(f"/financeiro/lancamentos/{L['L9']['ids'][0]}/pagar",
                         json={"data_pagamento": "2031-03-30", "valor_pago": 800, "forma_pagamento": "pix"}).status_code == 409
    assert cenario.c.put(f"/financeiro/lancamentos/{L['L4']['numero_lancamento']}/natureza", json={"natureza_fin": "OPERACIONAL"}).status_code == 409
    assert cenario.c.post("/exclusoes/impacto", json={"tipo": "financeiro", "id": str(l2)}).status_code == 409
    novo = {"tipo": "despesa", "itens": [{"produto": "Sal", "valor_total": 10, "codigo_conta_gerencial": "8.2"}],
            "data_emissao": "2031-03-20", "data_competencia": "2031-03-20", "data_vencimento": "2031-05-20"}
    assert cenario.c.post("/financeiro/lancamentos", json=novo).status_code == 409
    # Abril continua aberto.
    assert cenario.c.post("/financeiro/lancamentos", json={**novo, "data_emissao": "2031-04-20", "data_competencia": "2031-04-20"}).status_code == 201

    # Reabrir: sem motivo não; com motivo sim — e a edição volta a valer.
    assert cenario.c.post("/financeiro/fechamento/2031-03/reabrir", json={"motivo": ""}).status_code == 422
    r = cenario.c.post("/financeiro/fechamento/2031-03/reabrir", json={"motivo": "Nota do tanque no centro errado"})
    assert r.status_code == 201
    assert cenario.c.put(f"/financeiro/lancamentos/{l2}", json={"descricao": "Ração (corrigida)"}).status_code == 200
    trilha = cenario.get("/financeiro/fechamento/2031-03")["trilha_do_mes"]
    assert [e["acao"] for e in trilha] == ["reabrir", "fechar"] and trilha[0]["motivo"] == "Nota do tanque no centro errado"


def test_com_a_flag_desligada_um_mes_fechado_nao_trava_nada(cenario, em_maio_de_2031):  # noqa: F811
    cenario.ligar_regras_v2()
    assert cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={"forcar": True, "motivo": "fechar e desligar"}).status_code == 201
    from fazenda.models import ParametroFazenda

    with Session(cenario.engine) as s:
        p = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "financeiro_regras_v2", ParametroFazenda.fazenda_id == 1)).one()
        p.valor = "false"
        s.add(p)
        s.commit()
    l2 = cenario.ids["L"]["L2"]["ids"][0]
    assert cenario.c.put(f"/financeiro/lancamentos/{l2}", json={"descricao": "edição com a flag desligada"}).status_code == 200


def test_trilha_e_append_only_e_fechamento_e_por_fazenda(cenario, em_maio_de_2031):  # noqa: F811
    cenario.ligar_regras_v2()
    cenario.ligar_regras_v2(fazenda_id=2)
    assert cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={"forcar": True, "motivo": "fechamento da 1"}).status_code == 201
    with Session(cenario.engine) as s:
        ev = s.exec(select(FechamentoMesEvento)).one()
        ev.motivo = "adulterado"
        s.add(ev)
        with pytest.raises(RegistroImutavelError):
            s.commit()
    cenario.estado["fazenda_id"] = 2
    try:
        assert cenario.get("/financeiro/fechamento/2031-03")["status"] == "aberto"
        assert cenario.get("/financeiro/fechamento/meses", ate="2031-04")["trilha"] == []
    finally:
        cenario.estado["fazenda_id"] = 1


def test_so_administrador_fecha_e_contador_so_le(cenario, em_maio_de_2031):  # noqa: F811
    import main
    from fazenda.auth import get_current_user

    cenario.ligar_regras_v2()

    class _Operador:
        id, papel, ativo, username, nome, permissoes = 7, "operador", True, "operador", "Operador", "financeiro"

    main.app.dependency_overrides[get_current_user] = lambda: _Operador()
    assert cenario.c.post("/financeiro/fechamento/2031-03/fechar", json={"forcar": True, "motivo": "operador tentando"}).status_code == 403
    with Session(cenario.engine) as s:
        s.add(UsuarioFazenda(usuario_id=7, fazenda_id=1, contador=True))
        s.commit()
    # O contador baixa o pacote (GET) mas não escreve.
    assert cenario.c.get("/financeiro/pacote-contador", params={"data_inicio": "2031-03-01", "data_fim": "2031-04-30"}).status_code == 200
    assert cenario.c.post("/financeiro/conciliacao/linhas/1/desfazer").status_code == 403


# ── API: pacote do contador ────────────────────────────────────────────────
@pytest.mark.parametrize("ligar", [False, True])
def test_pacote_resumo_zip_e_pdf_com_os_numeros_dos_relatorios(cenario, ligar):  # noqa: F811
    if ligar:
        cenario.ligar_regras_v2()
    q = {"data_inicio": "2031-03-01", "data_fim": "2031-04-30"}
    r = cenario.get("/financeiro/pacote-contador", **q)
    dre = cenario.get("/financeiro/dre", data_inicio=q["data_inicio"], data_fim=q["data_fim"], regime="competencia")
    assert r["dre"]["competencia"]["resultado"] == cenario.linha(dre, "RESULTADO_LIQUIDO")
    assert r["cabecalho"]["fazenda"] == "Fazenda AUD 1" and r["cabecalho"]["regras_v2"] is ligar
    assert r["cabecalho"]["gerado_por"] == "auditoria"
    livro = r["livro"]
    assert round(livro["saldo_inicial"] + livro["entradas"] - livro["saidas"], 2) == livro["saldo_final"]
    # Março: aporte 20.000 entra; trator 120.000, principal 5.000 e diarista 700 saem. Abril: L1 9.850 entra.
    assert livro["entradas"] >= 29850.0 and livro["saidas"] >= 125700.0
    assert {i["id"] for i in r["itens"]} >= {"dre_competencia", "dre_caixa", "livro", "nao_classificados", "pendencias", "patrimonio", "conciliacao", "fechamento", "lcdpr"}
    assert any("DESLIGADAS" in n for n in r["metodo"]) is (not ligar)

    z = cenario.c.get("/financeiro/pacote-contador/zip", params=q)
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert 'filename="pacote-contador_fazenda-aud-1_2031-03-01_2031-04-30.zip"' in z.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(z.content)) as arq:
        nomes = set(arq.namelist())
        assert {"dre_competencia.csv", "dre_caixa.csv", "livro_caixa.csv", "livro_caixa_mensal.csv", "nao_classificados.csv",
                "pendencias.csv", "patrimonio_depreciacao.csv", "conciliacao.csv", "fechamentos.csv", "lcdpr_apoio_Q100.csv",
                "lcdpr_apoio_Q200.csv", "LEIA-ME.txt"} <= nomes
        assert any(n.endswith(".pdf") for n in nomes) and any(n.endswith(".xlsx") for n in nomes)
        pdf = next(arq.read(n) for n in nomes if n.endswith(".pdf"))
        assert pdf.startswith(b"%PDF")
        dre_csv = arq.read("dre_competencia.csv").decode("utf-8-sig")
        assert "Fazenda AUD 1" in dre_csv and f"{cenario.linha(dre, 'RESULTADO_LIQUIDO'):.2f}" in dre_csv
        leia = arq.read("LEIA-ME.txt").decode("utf-8-sig")
        assert "NÃO É O ARQUIVO DE TRANSMISSÃO" in leia
        q100 = arq.read("lcdpr_apoio_Q100.csv").decode("utf-8-sig").splitlines()
        assert q100[0].startswith("DATA|COD_IMOVEL|COD_CONTA")
        # Sem a flag não há natureza: o apoio ao LCDPR sai só com o cabeçalho.
        assert (len(q100) > 1) is ligar
    pdf = cenario.c.get("/financeiro/pacote-contador/pdf", params=q)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_pacote_isolado_por_fazenda_e_periodo_validado(cenario):  # noqa: F811
    cenario.estado["fazenda_id"] = 2
    try:
        r = cenario.get("/financeiro/pacote-contador", data_inicio="2031-03-01", data_fim="2031-04-30")
        assert r["livro"]["lancamentos"] == 0 and r["dre"]["competencia"]["resultado"] == 0
        assert r["cabecalho"]["fazenda"] == "Fazenda AUD 2"
    finally:
        cenario.estado["fazenda_id"] = 1
    assert cenario.c.get("/financeiro/pacote-contador", params={"data_inicio": "2031-04-30", "data_fim": "2031-03-01"}).status_code == 422
    assert cenario.c.get("/financeiro/pacote-contador", params={"data_inicio": "2030-01-01", "data_fim": "2031-04-30"}).status_code == 422


def test_email_do_portal_envia_o_pacote_como_zip(cenario, monkeypatch):  # noqa: F811
    """Reaproveita o motor de e-mail do Portal: o pacote vai como anexo ZIP."""
    from fazenda.api.routers import portal
    from fazenda.models import Usuario

    with Session(cenario.engine) as s:
        u = Usuario(username="contador-aud", nome="Contador", senha_hash="x", papel="operador", ativo=True, email="contador@aud.test")
        s.add(u)
        s.commit()
        s.refresh(u)
        s.add(UsuarioFazenda(usuario_id=u.id, fazenda_id=1, contador=True))
        s.commit()
        uid = u.id
    enviados = []
    monkeypatch.setattr(portal, "enviar_email",
                        lambda dest, assunto, corpo, nome=None, conteudo=None, **kw: enviados.append((dest, nome, conteudo)))
    r = cenario.c.post("/portal/email", json={"destinatarios_usuario_id": [uid], "assunto": "Pacote", "relatorio": "pacote_contador",
                                              "data_inicio": "2031-03-01", "data_fim": "2031-04-30"})
    assert r.status_code == 200, r.text
    (dest, nome, conteudo), = enviados
    assert dest == "contador@aud.test" and nome.endswith(".zip")
    assert "LEIA-ME.txt" in zipfile.ZipFile(io.BytesIO(conteudo)).namelist()


def test_linha_do_extrato_guarda_so_o_necessario():
    colunas = set(ExtratoLinha.model_fields)
    assert colunas == {"id", "fazenda_id", "conta_corrente_id", "importacao_id", "data", "valor", "historico", "documento",
                       "chave_dedup", "status", "lancamento_id", "transferencia_id", "observacao", "conciliado_por",
                       "conciliado_em", "criado_em"}
