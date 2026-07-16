"""
Aprovações — overhaul da despesa/receita: tipo de documento vindo do cadastro,
produto/conta gerencial por item, parcelamento e marcação de "já pago" (#389-392).
Cobre a materialização em `_criar_lancamento_financeiro`, chamada só quando o
admin aprova o LancamentoPendente.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, Fornecedor, LancamentoItem, LancamentoPendente, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1; papel = "admin"; ativo = True; username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        with Session(engine) as s:
            s.add(Fornecedor(nome="Casa do Produtor", tipo="fornecedor"))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


def _criar_pendente(engine, tipo="despesa", dados=None) -> int:
    dados = dados or {"fornecedor_cliente": "Casa do Produtor", "valor_total": 300.0, "itens": []}
    with Session(engine) as s:
        p = LancamentoPendente(tipo=tipo, payload=json.dumps(dados), resumo="teste", status="pendente")
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


class TestParcelamento:
    def test_editar_com_parcelas_e_aprovar_gera_uma_conta_por_parcela(self, client):
        c, engine = client
        pid = _criar_pendente(engine)
        novos = {
            "fornecedor_cliente": "Casa do Produtor",
            "tipo_documento": "Nota fiscal",
            "numero_documento": "NF-1",
            "data_emissao": "2026-07-10",
            "itens": [{"produto": "Ração", "quantidade": 10, "valor_unitario": 30.0, "valor_total": 300.0}],
            "parcelas": [
                {"data_vencimento": "2026-08-10", "valor": 150.0},
                {"data_vencimento": "2026-09-10", "valor": 150.0},
            ],
        }
        r = c.put(f"/aprovacoes/{pid}", json={"dados": novos})
        assert r.status_code == 200

        r = c.post(f"/aprovacoes/{pid}/aprovar")
        assert r.status_code == 200
        with Session(engine) as s:
            contas = s.exec(select(ContaGerencial)).all()
            assert len(contas) == 2
            assert {c2.parcela_total for c2 in contas} == {2}
            assert sorted(c2.valor_total for c2 in contas) == [150.0, 150.0]
            assert all(c2.data_pagamento is None for c2 in contas)  # parcelado nasce em aberto


class TestJaPago:
    def test_ja_pago_grava_forma_pagamento_e_conta_bancaria(self, client):
        c, engine = client
        pid = _criar_pendente(engine)
        novos = {
            "fornecedor_cliente": "Casa do Produtor",
            "tipo_documento": "Recibo",
            "data_emissao": "2026-07-10",
            "itens": [{"produto": "Frete", "valor_total": 200.0}],
            "parcelas": [],
            "data_pagamento": "2026-07-10",
            "forma_pagamento": "pix",
            "conta_bancaria": "Banco X",
            "numero_documento_pagamento": "PIX-99",
        }
        r = c.put(f"/aprovacoes/{pid}", json={"dados": novos})
        assert r.status_code == 200
        r = c.post(f"/aprovacoes/{pid}/aprovar")
        assert r.status_code == 200
        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial)).first()
            assert conta.forma_pagamento == "pix"
            assert conta.conta_bancaria == "Banco X"
            assert conta.numero_documento_pagamento == "PIX-99"
            assert conta.data_pagamento is not None
            assert conta.valor_pago == 200.0
            assert conta.tipo_documento == "Recibo"


class TestItensComContaGerencial:
    def test_itens_levam_conta_gerencial_escolhida_na_tela(self, client):
        c, engine = client
        pid = _criar_pendente(engine)
        novos = {
            "fornecedor_cliente": "Casa do Produtor",
            "tipo_documento": "Nota fiscal",
            "data_emissao": "2026-07-10",
            "itens": [
                {"produto": "Concentrado", "codigo_conta_gerencial": "3.01.01", "nome_conta_gerencial": "Concentrado", "quantidade": 2, "valor_unitario": 50.0, "valor_total": 100.0},
            ],
            "parcelas": [],
        }
        r = c.put(f"/aprovacoes/{pid}", json={"dados": novos})
        assert r.status_code == 200
        r = c.post(f"/aprovacoes/{pid}/aprovar")
        assert r.status_code == 200
        with Session(engine) as s:
            item = s.exec(select(LancamentoItem)).first()
            assert item.codigo_conta_gerencial == "3.01.01"
            assert item.nome_conta_gerencial == "Concentrado"


class TestTipoDocumentoNormalizacao:
    def test_valor_antigo_minusculo_ainda_funciona(self, client):
        """Payloads antigos do OCR (\"recibo\"/\"nota_fiscal\" minúsculo) continuam
        materializando certo mesmo sem terem passado pela tela de edição nova."""
        c, engine = client
        pid = _criar_pendente(engine, dados={
            "fornecedor_cliente": "Casa do Produtor", "tipo_documento": "recibo",
            "data_emissao": "2026-07-01", "data_pagamento": "2026-07-01",
            "valor_total": 80.0, "itens": [],
        })
        r = c.post(f"/aprovacoes/{pid}/aprovar")
        assert r.status_code == 200
        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial)).first()
            assert conta.tipo_documento == "Recibo"
