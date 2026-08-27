"""
Cadastro de Tipo de documento e Forma de pagamento (Configurações > Parâmetros
financeiros) — substituem as listas fixas TIPOS_DOCUMENTO/FORMAS_PAGAMENTO —
e o campo forma_pagamento no lançamento com pagamento imediato (jaPago).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, FormaPagamentoCadastro, TipoDocumento
from fazenda.models.planos import MODULOS_COMERCIAIS


def _ativar_fazenda(session: Session, fazenda_id: int, nome: str) -> None:
    """Fazenda + contrato ativo com todos os módulos — sem isso, GET
    /financeiro/opcoes com uma fazenda real (fazenda_id != None) dá 403
    (sem assinatura), diferente do caso sem-fazenda usado nos outros testes
    deste arquivo."""
    session.add(Fazenda(id=fazenda_id, nome=nome))
    session.add(ContratoFazenda(fazenda_id=fazenda_id, status="ativo"))
    for modulo in MODULOS_COMERCIAIS:
        session.add(ContratoFazendaModulo(fazenda_id=fazenda_id, modulo=modulo, preco=0.0, ativo=True))


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        c.engine = engine
        yield c

    main.app.dependency_overrides.clear()


def test_crud_tipos_documento(client):
    resp = client.post("/financeiro/tipos-documento", json={"nome": "Ordem de serviço", "ativo": True})
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    resp = client.get("/financeiro/tipos-documento")
    assert resp.status_code == 200
    assert any(t["nome"] == "Ordem de serviço" for t in resp.json())

    resp = client.put(f"/financeiro/tipos-documento/{item_id}", json={"nome": "Ordem de serviço", "ativo": False})
    assert resp.status_code == 200
    assert resp.json()["ativo"] is False

    client.post("/financeiro/tipos-documento", json={"nome": "Fatura"})
    resp = client.post("/financeiro/tipos-documento", json={"nome": "Fatura"})
    assert resp.status_code == 409


def test_crud_formas_pagamento(client):
    resp = client.post("/financeiro/formas-pagamento-cadastro", json={"nome": "dinheiro", "ativo": True})
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    resp = client.get("/financeiro/formas-pagamento-cadastro")
    assert resp.status_code == 200
    assert any(f["nome"] == "dinheiro" for f in resp.json())

    resp = client.put(f"/financeiro/formas-pagamento-cadastro/{item_id}", json={"nome": "dinheiro", "ativo": False})
    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


def test_opcoes_le_cadastro_com_fallback_para_lista_fixa(client):
    resp = client.get("/financeiro/opcoes")
    assert resp.status_code == 200
    dados = resp.json()
    # Sem nada cadastrado, cai na lista fixa antiga.
    assert "Nota fiscal" in dados["tipos_documento"]
    assert "pix" in dados["formas_pagamento"]

    client.post("/financeiro/tipos-documento", json={"nome": "Ordem de serviço"})
    resp = client.get("/financeiro/opcoes")
    dados = resp.json()
    # Com cadastro, usa só os cadastrados (ativos).
    assert dados["tipos_documento"] == ["Ordem de serviço"]


def test_lancamento_ja_pago_grava_forma_pagamento(client):
    resp = client.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Ração", "quantidade": 1, "valor_unitario": 100.0, "valor_total": 100.0}],
        "data_emissao": "2026-07-01",
        "data_pagamento": "2026-07-01",
        "valor_pago": 100.0,
        "forma_pagamento": "pix",
    })
    assert resp.status_code in (200, 201), resp.text

    with Session(client.engine) as session:
        registro = session.exec(select(ContaGerencial)).first()
        assert registro is not None
        assert registro.forma_pagamento == "pix"


class TestSeedComprovanteBackfillFazenda1:
    """Bug real de produção: a fazenda #1 foi 'grandfathered' com fazenda_id=1
    nos cadastros de tipo de documento pela migração e3f4a5b6c7d8 ANTES de
    "Comprovante"/"Orçamento" entrarem em SEED_TIPOS_DOCUMENTO (Central de
    Documentos, #507) — o seed rodado depois só cria o que falta com
    fazenda_id=None, que o GET /financeiro/opcoes nunca enxerga pra quem já
    tem cadastro próprio. Sem o backfill em seed_tipos_documento_formas_pagamento,
    "Comprovante" nunca aparece no anexo inicial do lançamento pra essa fazenda."""

    def test_seed_acrescenta_comprovante_na_fazenda_1_que_ja_tinha_cadastro_proprio(self, client):
        # Estado real de uma fazenda #1 já em produção antes da Central de
        # Documentos: tem cadastro próprio (fazenda_id=1), sem "Comprovante".
        with Session(client.engine) as session:
            _ativar_fazenda(session, 1, "Fazenda 1")
            session.add(TipoDocumento(nome="Nota fiscal", fazenda_id=1))
            session.add(TipoDocumento(nome="Recibo", fazenda_id=1))
            session.commit()

        from fazenda.api.routers.financeiro import seed_tipos_documento_formas_pagamento
        with Session(client.engine) as session:
            seed_tipos_documento_formas_pagamento(session)

        import main
        from fazenda.auth import get_fazenda_atual_id
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        try:
            resp = client.get("/financeiro/opcoes")
            assert resp.status_code == 200
            tipos = resp.json()["tipos_documento"]
            assert "Comprovante" in tipos
            # Não perde o que a fazenda já tinha cadastrado antes.
            assert "Nota fiscal" in tipos
            assert "Recibo" in tipos
        finally:
            main.app.dependency_overrides.pop(get_fazenda_atual_id, None)

    def test_seed_e_idempotente_na_fazenda_1(self, client):
        with Session(client.engine) as session:
            _ativar_fazenda(session, 1, "Fazenda 1")
            session.commit()

        from fazenda.api.routers.financeiro import seed_tipos_documento_formas_pagamento
        with Session(client.engine) as session:
            seed_tipos_documento_formas_pagamento(session)
        with Session(client.engine) as session:
            seed_tipos_documento_formas_pagamento(session)  # roda de novo — não deve duplicar

        with Session(client.engine) as session:
            nomes = [t.nome for t in session.exec(select(TipoDocumento).where(TipoDocumento.fazenda_id == 1)).all()]
        assert nomes.count("Comprovante") == 1

    def test_seed_nao_mexe_em_outra_fazenda(self, client):
        with Session(client.engine) as session:
            _ativar_fazenda(session, 1, "Fazenda 1")
            _ativar_fazenda(session, 2, "Fazenda 2")
            session.add(TipoDocumento(nome="Recibo customizado", fazenda_id=2))
            session.commit()

        from fazenda.api.routers.financeiro import seed_tipos_documento_formas_pagamento
        with Session(client.engine) as session:
            seed_tipos_documento_formas_pagamento(session)

        import main
        from fazenda.auth import get_fazenda_atual_id
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 2
        try:
            resp = client.get("/financeiro/opcoes")
            # Fazenda 2 não recebeu o backfill (só a #1, grandfathered) — segue
            # vendo só o que ela mesma cadastrou.
            assert resp.json()["tipos_documento"] == ["Recibo customizado"]
        finally:
            main.app.dependency_overrides.pop(get_fazenda_atual_id, None)
