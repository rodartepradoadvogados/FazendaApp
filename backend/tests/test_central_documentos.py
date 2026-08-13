"""
Central de Documentos (Administração) — GET /documentos-central.

Junta, só leitura, DocumentoArquivado (fiscal, admin-only) e LancamentoAnexo
(financeiro, quem tem o módulo) num único endpoint filtrável. Cobertura
focada no que mais importa aqui: cada tier só aparece pra quem pode ver, e
— o mais crítico — NUNCA vaza documento de uma fazenda pra outra.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    ContaGerencial, ContratoFazenda, ContratoFazendaModulo, DocumentoArquivado, Fazenda, LancamentoAnexo, Usuario,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    main.app.dependency_overrides[database.get_session] = _get_session_override

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))

        # Fazenda 1: 1 documento fiscal, 1 lançamento com 1 anexo financeiro.
        s.add(DocumentoArquivado(
            fazenda_id=1, categoria="Nota fiscal", nome_original="NF-123-fazenda1.pdf",
            caminho_storage="fazenda-1/nota_fiscal/x.pdf", mime_type="application/pdf", tamanho_bytes=10,
            data_documento=date(2026, 7, 1), data_upload=datetime(2026, 7, 1),
        ))
        s.add(ContaGerencial(
            numero_lancamento="LC-F1", codigo_conta="3.01.01.01", descricao="Compra fazenda 1",
            fornecedor_cliente="Fornecedor 1", tipo="despesa", origem="manual", valor_total=100.0,
            data_competencia=date(2026, 7, 1), fazenda_id=1,
        ))
        s.add(LancamentoAnexo(
            fazenda_id=1, numero_lancamento="LC-F1", nome_arquivo="boleto-f1.pdf",
            mime_type="application/pdf", tamanho_bytes=10, categoria="Boleto",
            numero_documento="BOL-F1", data_documento=date(2026, 7, 2),
            caminho_storage="fazenda-1/LC-F1/0001_boleto-f1.pdf",
        ))

        # Fazenda 2: mesma coisa, dados totalmente diferentes — nunca deve
        # aparecer pra ninguém consultando como fazenda 1.
        s.add(DocumentoArquivado(
            fazenda_id=2, categoria="Nota fiscal", nome_original="NF-999-fazenda2.pdf",
            caminho_storage="fazenda-2/nota_fiscal/y.pdf", mime_type="application/pdf", tamanho_bytes=10,
            data_documento=date(2026, 7, 1), data_upload=datetime(2026, 7, 1),
        ))
        s.add(ContaGerencial(
            numero_lancamento="LC-F2", codigo_conta="3.01.01.01", descricao="Compra fazenda 2",
            fornecedor_cliente="Fornecedor 2", tipo="despesa", origem="manual", valor_total=200.0,
            data_competencia=date(2026, 7, 1), fazenda_id=2,
        ))
        s.add(LancamentoAnexo(
            fazenda_id=2, numero_lancamento="LC-F2", nome_arquivo="boleto-f2.pdf",
            mime_type="application/pdf", tamanho_bytes=10, categoria="Boleto",
            numero_documento="BOL-F2", data_documento=date(2026, 7, 2),
            caminho_storage="fazenda-2/LC-F2/0001_boleto-f2.pdf",
        ))
        s.commit()

    def _como(papel: str, permissoes: str, fazenda_id: int | None):
        class _FakeUser:
            id = 1
            username = "teste"

        _FakeUser.papel = papel
        _FakeUser.permissoes = permissoes
        _FakeUser.ativo = True
        main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id

    with TestClient(main.app) as c:
        c.como = _como
        yield c

    main.app.dependency_overrides.clear()


class TestPermissaoPorTier:
    def test_admin_ve_fiscal_e_financeiro_da_propria_fazenda(self, client):
        client.como("admin", "", 1)
        r = client.get("/documentos-central")
        assert r.status_code == 200
        origens = sorted(l["origem"] for l in r.json())
        assert origens == ["financeiro", "fiscal"]

    def test_funcionario_com_financeiro_ve_so_financeiro(self, client):
        client.como("funcionario", "financeiro", 1)
        r = client.get("/documentos-central")
        assert r.status_code == 200
        linhas = r.json()
        assert all(l["origem"] == "financeiro" for l in linhas)
        assert len(linhas) == 1

    def test_funcionario_sem_financeiro_nao_ve_nada_e_nao_da_403(self, client):
        client.como("funcionario", "", 1)
        r = client.get("/documentos-central")
        assert r.status_code == 200
        assert r.json() == []


class TestIsolamentoMultiTenant:
    def test_admin_da_fazenda_1_nunca_ve_documento_da_fazenda_2(self, client):
        client.como("admin", "", 1)
        r = client.get("/documentos-central")
        nomes = [l["nome_arquivo"] for l in r.json()]
        assert "NF-999-fazenda2.pdf" not in nomes
        assert "boleto-f2.pdf" not in nomes
        assert "NF-123-fazenda1.pdf" in nomes
        assert "boleto-f1.pdf" in nomes

    def test_admin_da_fazenda_2_nunca_ve_documento_da_fazenda_1(self, client):
        client.como("admin", "", 2)
        r = client.get("/documentos-central")
        nomes = [l["nome_arquivo"] for l in r.json()]
        assert "NF-123-fazenda1.pdf" not in nomes
        assert "boleto-f1.pdf" not in nomes
        assert "NF-999-fazenda2.pdf" in nomes
        assert "boleto-f2.pdf" in nomes

    def test_numero_documento_de_outra_fazenda_nao_vaza_na_busca(self, client):
        # Busca pelo número do boleto da fazenda 2 estando logado na fazenda 1
        # — tem que voltar vazio, não achar o documento de outro tenant.
        client.como("admin", "", 1)
        r = client.get("/documentos-central", params={"numero_documento": "BOL-F2"})
        assert r.json() == []


class TestFiltros:
    def test_filtro_por_categoria(self, client):
        client.como("admin", "", 1)
        r = client.get("/documentos-central", params={"categoria": "Boleto"})
        linhas = r.json()
        assert len(linhas) == 1
        assert linhas[0]["categoria"] == "Boleto"

    def test_filtro_por_numero_documento_do_financeiro(self, client):
        client.como("admin", "", 1)
        r = client.get("/documentos-central", params={"numero_documento": "BOL-F1"})
        linhas = r.json()
        assert len(linhas) == 1
        assert linhas[0]["numero_documento"] == "BOL-F1"

    def test_filtro_por_periodo(self, client):
        client.como("admin", "", 1)
        r = client.get("/documentos-central", params={"data_de": "2026-07-02", "data_ate": "2026-07-02"})
        linhas = r.json()
        assert len(linhas) == 1
        assert linhas[0]["origem"] == "financeiro"

    def test_linha_financeiro_traz_numero_de_lancamento_para_link(self, client):
        client.como("admin", "", 1)
        r = client.get("/documentos-central", params={"categoria": "Boleto"})
        assert r.json()[0]["numero_lancamento"] == "LC-F1"
