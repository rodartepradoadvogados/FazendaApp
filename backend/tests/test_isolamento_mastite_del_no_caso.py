"""
FURO DE MULTI-TENANT CORRIGIDO em `lancar_protocolo` (POST /sanidade/
protocolos/lancamentos, fazenda/api/routers/sanidade.py) — quando o
protocolo é de mastite, o DEL "no caso" (snapshot gravado no lançamento)
buscava o Animal só por `numero == numero_matriz`, sem filtrar fazenda_id.
Como `animal.numero` deixou de ser único globalmente (migração
c24befa94c1b), duas fazendas podem ter cada uma um animal com o mesmo
número — o lançamento de mastite da fazenda 2 não pode gravar o DEL do
animal "500" da fazenda 1.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, ProtocoloSanitario, ProtocoloSanitarioEtapa,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.models.sanidade import ProtocoloSanitarioLancamento


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

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

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def test_lancamento_mastite_usa_del_dias_da_propria_fazenda(client):
    c, engine = client
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))

        protocolo = ProtocoloSanitario(nome="Mastite clínica", eh_mastite=True, dia_inicial=1)
        s.add(protocolo)
        s.commit()
        s.refresh(protocolo)
        s.add(ProtocoloSanitarioEtapa(protocolo_id=protocolo.id, dia=1, produto="Mastite Injetável", dosagem=10.0, unidade="ml", via="Intramamária"))
        s.commit()

        # Mesmo numero "500" nas duas fazendas, DEL bem diferente entre elas.
        s.add(Animal(numero="500", fazenda_id=1, del_dias=999))
        s.add(Animal(numero="500", fazenda_id=2, del_dias=5))
        s.commit()
        protocolo_id = protocolo.id

    _como_fazenda(2)
    r = c.post("/sanidade/protocolos/lancamentos", json={
        "protocolo_id": protocolo_id, "numeros_matriz": ["500"], "data_inicio": str(date(2026, 1, 1)),
        "classificacao_mastite": "clinica",
    })
    assert r.status_code == 201, r.text

    with Session(engine) as s:
        lancamento = s.exec(select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.fazenda_id == 2)).first()
        assert lancamento is not None
        assert lancamento.del_no_caso == 5, (
            "o DEL gravado no caso de mastite da fazenda 2 tem que ser o do SEU PRÓPRIO animal '500' "
            "(del_dias=5), nunca o do animal '500' de outra fazenda (del_dias=999)"
        )
