"""Caixa dos funcionários — retenção no PAGAMENTO de quem não é CLT (parcela de contrato, diária).

A retenção é decidida na janela do pagamento: o combinado (autorizado e em vigor) só sugere; vale
percentual livre ou valor nominal. A conta paga passa a valer o líquido e o retido vira despesa baixada
("Caixa do funcionário") — o gasto total não muda. Estorno do pagamento desfaz (recusa se já foi sacado)."""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    CaixaMovimento, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

HOJE = date.today()


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
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
        s.add(Usuario(id=3, username="gerente", senha_hash=hash_senha("x"), papel="operador", ativo=True))
        s.add(UsuarioFazenda(usuario_id=3, fazenda_id=1))
        s.commit()
        for nome, tipo, fid in (("Paulo Contratado", "Prestador de serviços", 1), ("Dora Diarista", "Diarista", 1),
                                ("Outro Contratado", "Prestador de serviços", 2)):
            p = Pessoa(nome=nome, tipo=tipo, fazenda_id=fid, data_admissao=date(2024, 1, 10))
            s.add(p)
            s.commit()
            s.refresh(p)
            ids[nome.split()[0].lower()] = p.id

    def _sess():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fid: int = 1, usuario: str | None = None):
    return {"Authorization": f"Bearer {criar_token(usuario or f'admin{fid}', fazenda_id=fid)}"}


def _combinar(c, pessoa_id, fid=1, **extra):
    corpo = {"forma": "percentual", "valor": 10.0, "inicio": "2026-01-01", "autorizada": True}
    corpo.update(extra)
    r = c.put(f"/cadastro/caixa-funcionarios/{pessoa_id}/retencao", json=corpo, headers=_cab(fid))
    assert r.status_code == 200, r.text


def _contrato(c, pessoa_id, valor=2000.0, fid=1) -> int:
    """Contrato de 1 parcela; devolve o id da conta (ContaGerencial) da parcela."""
    r = c.post("/cadastro/contratos", json={
        "pessoa_id": pessoa_id, "descricao": "Serviço de curral", "valor_total": valor, "forma_pagamento": "mensal",
        "parcelas": [{"data_vencimento": HOJE.isoformat(), "valor": valor}],
    }, headers=_cab(fid))
    assert r.status_code == 200, r.text
    numero = r.json()["parcelas"][0]["numero_lancamento_gerado"]
    assert numero
    return numero


def _conta(engine, numero) -> ContaGerencial:
    with Session(engine) as s:
        return s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()


def _pagar(c, conta_id, valor=2000.0, retencao=None, fid=1, usuario=None):
    corpo = {"data_pagamento": HOJE.isoformat(), "valor_pago": valor, "forma_pagamento": "pix"}
    if retencao is not None:
        corpo["retencao_caixa"] = retencao
    return c.put(f"/financeiro/lancamentos/{conta_id}/pagar", json=corpo, headers=_cab(fid, usuario))


def _saldo(c, pessoa_id, fid=1) -> float:
    return c.get(f"/cadastro/caixa-funcionarios/{pessoa_id}", headers=_cab(fid)).json()["saldo"]


def _gasto_total(engine) -> float:
    """Despesa total do Financeiro (contrato + retenção): o que a fazenda de fato gastou."""
    with Session(engine) as s:
        return round(sum(x.valor_total or 0 for x in s.exec(select(ContaGerencial).where(ContaGerencial.tipo == "despesa")).all()), 2)


class TestParcelaDeContrato:
    def test_percentual_livre_conta_vale_o_liquido_e_o_retido_vai_ao_caixa(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"], valor=10.0)
        numero = _contrato(c, ids["paulo"])
        conta = _conta(engine, numero)
        r = _pagar(c, conta.id, retencao={"modo": "percentual", "valor": 15.0})  # livre: não é os 10% do combinado
        assert r.status_code == 200, r.text
        pago = _conta(engine, numero)
        assert (pago.valor_total, pago.valor_pago) == (1700.0, 1700.0) and pago.data_pagamento is not None
        assert _saldo(c, ids["paulo"]) == 300.0
        assert _gasto_total(engine) == 2000.0  # 1700 + 300 retidos: o gasto não muda
        with Session(engine) as s:
            ret = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Caixa do funcionário")).all()
            assert [(x.valor_total, x.data_pagamento is not None) for x in ret] == [(300.0, True)]

    def test_valor_nominal(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"])
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        assert _pagar(c, conta.id, retencao={"modo": "valor", "valor": 123.45}).status_code == 200
        assert _saldo(c, ids["paulo"]) == 123.45
        assert _conta(engine, conta.numero_lancamento).valor_pago == 1876.55

    def test_sem_retencao_nada_muda(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"])
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        assert _pagar(c, conta.id).status_code == 200
        assert _saldo(c, ids["paulo"]) == 0.0 and _conta(engine, conta.numero_lancamento).valor_pago == 2000.0

    def test_sem_combinado_autorizado_recusa(self, ambiente):
        c, engine, ids = ambiente
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        r = _pagar(c, conta.id, retencao={"modo": "percentual", "valor": 10.0})
        assert r.status_code == 409 and "autorizada" in r.json()["detail"]
        assert _conta(engine, conta.numero_lancamento).data_pagamento is None  # nada foi baixado

    def test_validacoes_de_valor(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"])
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        assert _pagar(c, conta.id, retencao={"modo": "percentual", "valor": 100.0}).status_code == 400  # reteria tudo
        assert _pagar(c, conta.id, retencao={"modo": "percentual", "valor": 120.0}).status_code == 400
        assert _pagar(c, conta.id, retencao={"modo": "valor", "valor": 2000.0}).status_code == 400
        assert _pagar(c, conta.id, retencao={"modo": "xis", "valor": 5.0}).status_code == 400

    def test_acima_do_teto_pede_confirmacao(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"], teto=100.0)
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        r = _pagar(c, conta.id, retencao={"modo": "valor", "valor": 150.0})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "acima_do_teto"
        assert _saldo(c, ids["paulo"]) == 0.0
        ok = _pagar(c, conta.id, retencao={"modo": "valor", "valor": 150.0, "confirmar_acima_teto": True})
        assert ok.status_code == 200 and _saldo(c, ids["paulo"]) == 150.0

    def test_so_administrador_retem(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"])
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        r = _pagar(c, conta.id, retencao={"modo": "percentual", "valor": 10.0}, usuario="gerente")
        assert r.status_code == 403

    def test_conta_que_nao_e_de_contrato_recusa_retencao(self, ambiente):
        c, engine, ids = ambiente
        with Session(engine) as s:
            avulsa = ContaGerencial(numero_lancamento="LC-X-1", descricao="Energia", tipo="despesa", valor_total=500.0,
                                    data_vencimento=HOJE, fornecedor_cliente="Cemig", parcela_num=1, parcela_total=1, fazenda_id=1)
            s.add(avulsa)
            s.commit()
            s.refresh(avulsa)
        _combinar(c, ids["paulo"])
        r = _pagar(c, avulsa.id, valor=500.0, retencao={"modo": "percentual", "valor": 10.0})
        assert r.status_code == 400

    def test_estorno_devolve_valor_e_zera_o_caixa(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"])
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        assert _pagar(c, conta.id, retencao={"modo": "percentual", "valor": 10.0}).status_code == 200
        assert _saldo(c, ids["paulo"]) == 200.0
        r = c.post(f"/financeiro/lancamentos/{conta.id}/estornar", json={"motivo": "erro"}, headers=_cab())
        assert r.status_code == 200, r.text
        de_volta = _conta(engine, conta.numero_lancamento)
        assert de_volta.valor_total == 2000.0 and de_volta.data_pagamento is None and de_volta.valor_pago is None
        assert _saldo(c, ids["paulo"]) == 0.0

    def test_estorno_recusado_se_o_dinheiro_ja_foi_sacado(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"])
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        assert _pagar(c, conta.id, retencao={"modo": "percentual", "valor": 10.0}).status_code == 200
        r = c.post(f"/cadastro/caixa-funcionarios/{ids['paulo']}/retiradas", json={
            "valor": 150.0, "data": HOJE.isoformat(), "forma_pagamento": "pix", "motivo": "saque"}, headers=_cab())
        assert r.status_code == 200, r.text
        r = c.post(f"/financeiro/lancamentos/{conta.id}/estornar", json={}, headers=_cab())
        assert r.status_code == 409 and "retirad" in r.json()["detail"]
        assert _conta(engine, conta.numero_lancamento).data_pagamento is not None  # continua paga

    def test_destino_time_vai_para_o_caixa_do_time(self, ambiente):
        c, engine, ids = ambiente
        t = c.post("/cadastro/caixa-time", json={"nome": "Turma do curral", "auto_tipos": ["clt"]}, headers=_cab())
        assert t.status_code == 200, t.text
        _combinar(c, ids["paulo"], destino="time", time_id=t.json()["id"])
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        assert _pagar(c, conta.id, retencao={"modo": "valor", "valor": 200.0}).status_code == 200
        assert _saldo(c, ids["paulo"]) == 0.0
        d = c.get(f"/cadastro/caixa-time/{t.json()['id']}", headers=_cab()).json()
        assert d["saldo"] == 200.0
        assert c.post(f"/financeiro/lancamentos/{conta.id}/estornar", json={}, headers=_cab()).status_code == 200
        assert c.get(f"/cadastro/caixa-time/{t.json()['id']}", headers=_cab()).json()["saldo"] == 0.0


class TestDiaria:
    def _diaria(self, c, ids, dias=2):
        inicio = HOJE - timedelta(days=dias - 1)
        r = c.post("/cadastro/diarias", json={"pessoa_id": ids["dora"], "valor_diaria": 100.0, "data_inicio": inicio.isoformat()}, headers=_cab())
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_pagamento_com_retencao_abate_o_bruto_e_a_conta_vale_o_liquido(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["dora"], valor=10.0)
        did = self._diaria(c, ids)
        r = c.post(f"/cadastro/diarias/{did}/pagamentos", json={
            "data_pagamento": HOJE.isoformat(), "valor": 200.0, "forma_pagamento": "pix",
            "retencao_caixa": {"modo": "percentual", "valor": 20.0}}, headers=_cab())
        assert r.status_code == 200, r.text
        assert r.json()["valor_pago"] == 200.0 and r.json()["saldo_devedor"] == 0.0  # a diária foi quitada pelo bruto
        assert _saldo(c, ids["dora"]) == 40.0
        conta = _conta(engine, r.json()["numero_lancamento_gerado"])
        assert (conta.valor_total, conta.valor_pago) == (160.0, 160.0)
        assert _gasto_total(engine) == 200.0

    def test_diaria_sem_combinado_recusa_e_nao_grava_pagamento(self, ambiente):
        c, engine, ids = ambiente
        did = self._diaria(c, ids)
        r = c.post(f"/cadastro/diarias/{did}/pagamentos", json={
            "data_pagamento": HOJE.isoformat(), "valor": 100.0, "retencao_caixa": {"modo": "valor", "valor": 10.0}}, headers=_cab())
        assert r.status_code == 409
        from fazenda.models import DiariaPagamento
        with Session(engine) as s:
            assert s.exec(select(DiariaPagamento)).first() is None


class TestOpcoes:
    def test_sugestao_vem_do_combinado(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"], valor=12.5, teto=1000.0)
        r = c.get("/cadastro/caixa-funcionarios/retencao-opcoes", params={"pessoa_id": ids["paulo"], "valor": 2000.0}, headers=_cab())
        d = r.json()
        assert d["disponivel"] and d["percentual_sugerido"] == 12.5 and d["valor_sugerido"] == 250.0 and d["teto_restante"] == 1000.0

    def test_valor_fixo_vira_percentual_equivalente(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"], forma="fixo", valor=200.0)
        d = c.get("/cadastro/caixa-funcionarios/retencao-opcoes", params={"pessoa_id": ids["paulo"], "valor": 2000.0}, headers=_cab()).json()
        assert d["percentual_sugerido"] == 10.0 and d["valor_sugerido"] == 200.0

    def test_por_lancamento_acha_a_pessoa_do_contrato(self, ambiente):
        c, engine, ids = ambiente
        _combinar(c, ids["paulo"])
        conta = _conta(engine, _contrato(c, ids["paulo"]))
        d = c.get("/cadastro/caixa-funcionarios/retencao-opcoes", params={"lancamento_id": conta.id, "valor": 2000.0}, headers=_cab()).json()
        assert d["disponivel"] and d["pessoa"] == "Paulo Contratado"

    def test_indisponivel_sem_combinado_e_isolado_por_fazenda(self, ambiente):
        c, engine, ids = ambiente
        d = c.get("/cadastro/caixa-funcionarios/retencao-opcoes", params={"pessoa_id": ids["paulo"], "valor": 100.0}, headers=_cab()).json()
        assert d["disponivel"] is False and "autorizada" in d["motivo"]
        _combinar(c, ids["outro"], fid=2)
        # a fazenda 1 não enxerga a pessoa da fazenda 2
        d2 = c.get("/cadastro/caixa-funcionarios/retencao-opcoes", params={"pessoa_id": ids["outro"], "valor": 100.0}, headers=_cab(1)).json()
        assert d2["disponivel"] is False
