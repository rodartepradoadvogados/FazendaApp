"""
Alerta na Agenda quando o "Contrato de trabalho por prazo determinado"
anexado a uma Pessoa está com a validade vencendo — dispara 15 dias antes
(mais antecedência que Pedido: decidir renovar/encerrar um vínculo de
trabalho precisa de mais prazo do que aprovar um orçamento), enquanto a
pessoa segue ativa (ver PessoaAnexo, AgendaEngine bloco "5d").
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import Pessoa, PessoaAnexo


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


HOJE = date(2026, 8, 16)
CATEGORIA = "Contrato de trabalho por prazo determinado"


def _pessoa(**overrides) -> Pessoa:
    dados = dict(nome="João da Silva", tipo="Funcionário", ativo=True)
    dados.update(overrides)
    return Pessoa(**dados)


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    yield main.app, engine
    main.app.dependency_overrides.clear()


def _client(app):
    from fazenda.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    return TestClient(app)


def test_alerta_dispara_15_dias_antes_do_vencimento(setup):
    app, engine = setup
    with Session(engine) as s:
        pessoa = _pessoa()
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        s.add(PessoaAnexo(
            pessoa_id=pessoa.id, nome_arquivo="contrato.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria=CATEGORIA, data_validade=HOJE + timedelta(days=15),
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=20")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert any("João da Silva" in d and "vence em" in d for d in descricoes)


def test_sem_data_validade_nao_dispara_alerta(setup):
    app, engine = setup
    with Session(engine) as s:
        pessoa = _pessoa()
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        s.add(PessoaAnexo(
            pessoa_id=pessoa.id, nome_arquivo="contrato.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria=CATEGORIA, data_validade=None,
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=20")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("João da Silva" in d for d in descricoes)


def test_pessoa_inativa_nao_dispara_alerta(setup):
    app, engine = setup
    with Session(engine) as s:
        pessoa = _pessoa(ativo=False)
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        s.add(PessoaAnexo(
            pessoa_id=pessoa.id, nome_arquivo="contrato.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria=CATEGORIA, data_validade=HOJE + timedelta(days=15),
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=20")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("João da Silva" in d for d in descricoes)


def test_outra_categoria_nao_dispara_alerta(setup):
    """RG/CPF/holerite etc. não têm vencimento acompanhado pela Agenda —
    só "Contrato de trabalho por prazo determinado"."""
    app, engine = setup
    with Session(engine) as s:
        pessoa = _pessoa()
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        s.add(PessoaAnexo(
            pessoa_id=pessoa.id, nome_arquivo="rg.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria="RG", data_validade=HOJE + timedelta(days=15),
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=20")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("João da Silva" in d for d in descricoes)


def test_fora_da_janela_de_15_dias_nao_dispara_ainda(setup):
    """Vencimento daqui a 40 dias — o alerta (vencimento-15) só entra na janela quando `dias` for grande o suficiente."""
    app, engine = setup
    with Session(engine) as s:
        pessoa = _pessoa()
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        s.add(PessoaAnexo(
            pessoa_id=pessoa.id, nome_arquivo="contrato.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria=CATEGORIA, data_validade=HOJE + timedelta(days=40),
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=20")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("João da Silva" in d for d in descricoes)

    r2 = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=40")
    assert r2.status_code == 200
    descricoes2 = [e["descricao"] for e in r2.json()["eventos"]]
    assert any("João da Silva" in d for d in descricoes2)
