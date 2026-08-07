"""
G2 — `POST /financeiro/lancamentos/{id}/estornar`: reverte a baixa de um
lançamento (volta para "em aberto"). Não é exclusão — o lançamento continua
existindo.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="financeiro", preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "admin@teste.com"
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: None

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestEstornarLancamento:
    def test_estornar_zera_os_campos_e_volta_para_em_aberto(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(
                id=1, numero_lancamento="LC-2026-00001", descricao="Ração", tipo="despesa",
                valor_total=100.0, valor_pago=100.0, data_pagamento=date(2026, 1, 5),
                conta_bancaria="Banco X", numero_documento_pagamento="DOC-1", forma_pagamento="pix",
                desconto_acrescimo=0.0, parcela_num=1, parcela_total=1, origem="manual",
            ))
            s.commit()

        r = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["estornado"] is True
        assert body["data_pagamento"] is None
        assert body["valor_pago"] is None
        assert body["conta_bancaria"] is None
        assert body["numero_documento_pagamento"] is None
        assert body["forma_pagamento"] is None
        assert body["data_vencimento_cartao"] is None
        assert body["desconto_acrescimo"] is None
        assert body["parcelas_diferenca_removidas"] == 0

        with _sessao(engine) as s:
            registro = s.get(ContaGerencial, 1)
            assert registro.data_pagamento is None
            assert registro.valor_pago is None
            assert registro.valor_total == 100.0  # o lançamento em si continua existindo

    def test_estornar_duas_vezes_da_400_na_segunda(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(
                id=1, numero_lancamento="LC-2026-00002", valor_total=50.0, valor_pago=50.0,
                data_pagamento=date(2026, 1, 5), parcela_num=1, parcela_total=1, origem="manual",
            ))
            s.commit()

        r1 = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r1.status_code == 200

        r2 = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r2.status_code == 400
        assert "não está baixado" in r2.json()["detail"]

    def test_estornar_lancamento_nunca_baixado_da_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00003", valor_total=50.0, parcela_num=1, parcela_total=1))
            s.commit()

        r = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r.status_code == 400

    def test_estornar_diaria_da_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(
                id=1, numero_lancamento="LC-2026-00004", tipo_documento="Diária",
                valor_total=100.0, valor_pago=100.0, data_pagamento=date(2026, 1, 5),
                parcela_num=1, parcela_total=1,
            ))
            s.commit()

        r = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r.status_code == 400
        assert "Diária" in r.json()["detail"]

    def test_estornar_vale_de_funcionario_da_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(
                id=1, numero_lancamento="LC-2026-00005", tipo_documento="Vale de funcionário",
                valor_total=100.0, valor_pago=100.0, data_pagamento=date(2026, 1, 5),
                parcela_num=1, parcela_total=1,
            ))
            s.commit()

        r = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r.status_code == 400
        assert "Vale de funcionário" in r.json()["detail"]

    def test_estornar_vale_avulso_da_400(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(
                id=1, numero_lancamento="LC-2026-00006", tipo_documento="Vale avulso",
                valor_total=100.0, valor_pago=100.0, data_pagamento=date(2026, 1, 5),
                parcela_num=1, parcela_total=1,
            ))
            s.commit()

        r = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r.status_code == 400

    def test_lancamento_de_outra_fazenda_da_404(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(
                id=1, numero_lancamento="LC-2026-00007", valor_total=100.0, valor_pago=100.0,
                data_pagamento=date(2026, 1, 5), parcela_num=1, parcela_total=1, fazenda_id=1,
            ))
            s.commit()

        _como_fazenda(2)
        r = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r.status_code == 404

    def test_lancamento_inexistente_da_404(self, client):
        c, engine = client
        r = c.post("/financeiro/lancamentos/9999/estornar", json={})
        assert r.status_code == 404


class TestEstornarComParcelasDeDiferenca:
    def _criar_e_baixar_com_diferenca(self, c, engine):
        with _sessao(engine) as s:
            s.add(ContaGerencial(
                id=1, numero_lancamento="LC-2026-00010", valor_total=100.0, parcela_num=1, parcela_total=1, origem="manual",
            ))
            s.commit()

        r = c.put("/financeiro/lancamentos/1/pagar", json={
            "data_pagamento": "2026-01-05", "valor_pago": 80.0,
            "parcelas_diferenca": [{"data_vencimento": "2026-02-05", "valor": 20.0}],
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_sem_confirmar_da_409_com_as_parcelas(self, client):
        c, engine = client
        self._criar_e_baixar_com_diferenca(c, engine)

        r = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert "1 parcela" in detail["mensagem"]
        assert len(detail["parcelas"]) == 1
        assert detail["parcelas"][0]["valor_total"] == 20.0

        # Nada foi alterado ainda — só a prévia do 409.
        with _sessao(engine) as s:
            registro = s.get(ContaGerencial, 1)
            assert registro.valor_pago == 80.0
            todas = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-2026-00010")).all()
            assert len(todas) == 2

    def test_confirmando_remove_a_parcela_e_restaura_parcela_total(self, client):
        c, engine = client
        self._criar_e_baixar_com_diferenca(c, engine)

        r = c.post("/financeiro/lancamentos/1/estornar", json={"confirmar_parcelas_diferenca": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["parcelas_diferenca_removidas"] == 1
        assert body["data_pagamento"] is None
        assert body["valor_pago"] is None

        with _sessao(engine) as s:
            restantes = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-2026-00010")).all()
            assert len(restantes) == 1
            assert restantes[0].id == 1
            assert restantes[0].parcela_total == 1


class TestEstornoNaoEExclusao:
    def test_lancamento_continua_existindo_apos_estorno(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(
                id=1, numero_lancamento="LC-2026-00020", valor_total=100.0, valor_pago=100.0,
                data_pagamento=date(2026, 1, 5), parcela_num=1, parcela_total=1,
            ))
            s.commit()

        r = c.post("/financeiro/lancamentos/1/estornar", json={})
        assert r.status_code == 200

        r2 = c.get("/financeiro/lancamentos")
        assert r2.status_code == 200
        assert any(l["id"] == 1 for l in r2.json()["lancamentos"])
