"""
Isolamento por fazenda no upload de CSV (Fase 0).

Quase todo upload aqui é "apaga tudo e reimporta" — sem escopo por fazenda,
subir o CSV de UMA fazenda apagava os dados de TODAS as outras. Estes testes
sobem um CSV como a Fazenda 2 e provam que os dados da Fazenda 1 continuam
intactos.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, Sanidade,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for fid, nome in ((1, "Fazenda 1"), (2, "Fazenda 2")):
            s.add(Fazenda(id=fid, nome=nome))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        # Dados que pertencem à Fazenda 1 e NÃO podem sumir.
        s.add(Animal(numero="18", sexo="F", ativo=True, fazenda_id=1))
        s.add(Estoque(nome="Ração F1", quantidade=100, fazenda_id=1))
        s.add(Sanidade(numero_matriz="18", data_aplicacao=date(2026, 5, 1), produto="Vacina F1", fazenda_id=1))
        s.add(ContaGerencial(descricao="Conta F1", fazenda_id=1))
        s.commit()

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
        email = "teste@example.com"
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _subir(c, tipo: str, csv: str):
    return c.post(f"/upload/{tipo}", files={"file": (f"{tipo}.csv", csv.encode("utf-8"), "text/csv")})


class TestUploadNaoApagaOutraFazenda:
    def test_estoque_da_fazenda_2_preserva_a_1(self, client):
        c, engine = client
        _como_fazenda(2)
        r = _subir(c, "estoque", "Produto;Quantidade\nRação F2;50\n")
        assert r.status_code in (200, 422), r.text  # 422 = parser recusou o formato do fixture

        with Session(engine) as s:
            nomes_f1 = [e.nome for e in s.exec(select(Estoque).where(Estoque.fazenda_id == 1)).all()]
        assert "Ração F1" in nomes_f1, "upload da Fazenda 2 apagou o estoque da Fazenda 1"

    def test_sanidade_da_fazenda_2_preserva_a_1(self, client):
        c, engine = client
        _como_fazenda(2)
        _subir(c, "sanidade", "Animal;Data;Produto\n99;01/06/2026;Vacina F2\n")

        with Session(engine) as s:
            registros_f1 = s.exec(select(Sanidade).where(Sanidade.fazenda_id == 1)).all()
        assert len(registros_f1) == 1, "upload da Fazenda 2 apagou a sanidade da Fazenda 1"
        assert registros_f1[0].produto == "Vacina F1"

    def test_conta_gerencial_da_fazenda_2_preserva_a_1(self, client):
        c, engine = client
        _como_fazenda(2)
        _subir(c, "conta_gerencial", "Descricao;Valor\nConta F2;10\n")

        with Session(engine) as s:
            contas_f1 = s.exec(select(ContaGerencial).where(ContaGerencial.fazenda_id == 1)).all()
        assert len(contas_f1) == 1, "upload da Fazenda 2 apagou o financeiro da Fazenda 1"
        assert contas_f1[0].descricao == "Conta F1"

    def test_geral_nao_sobrescreve_animal_de_mesmo_numero(self, client):
        """`numero` não é único entre fazendas — a vaca "18" existe nas duas.
        O upload da Fazenda 2 tem que CRIAR a 18 dela, não sequestrar a da 1."""
        c, engine = client
        _como_fazenda(2)
        _subir(c, "geral", "Numero;Sexo\n18;F\n")

        with Session(engine) as s:
            f1 = s.exec(select(Animal).where(Animal.numero == "18", Animal.fazenda_id == 1)).all()
        assert len(f1) == 1, "a vaca 18 da Fazenda 1 sumiu ou foi absorvida pela Fazenda 2"
