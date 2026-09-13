"""
`animal.numero` deixou de ser único no banco INTEIRO e passou a ser único
POR FAZENDA (ver migração c24befa94c1b e fazenda/models/animais.py) — duas
fazendas diferentes podem ter, cada uma, uma vaca "100"; a mesma fazenda
continua barrada de duplicar.

Teste de modelo (SQLModel.metadata.create_all, sem passar pelo Alembic) —
cobre a garantia que o ORM/banco aplicam a partir de agora. A migração em si
(e as travas de segurança contra dado órfão/duplicado pré-existente) tem
cobertura própria em test_migracao_animal_numero_unico_por_fazenda.py.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Animal, Fazenda


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        s.commit()
    return eng


class TestMesmoNumeroEmFazendasDiferentes:
    def test_duas_fazendas_podem_ter_o_mesmo_numero(self, engine):
        with Session(engine) as s:
            s.add(Animal(numero="100", fazenda_id=1, ativo=True))
            s.add(Animal(numero="100", fazenda_id=2, ativo=True))
            s.commit()  # não deveria levantar IntegrityError

        with Session(engine) as s:
            from sqlmodel import select
            animais = s.exec(select(Animal).where(Animal.numero == "100")).all()
            assert {a.fazenda_id for a in animais} == {1, 2}


class TestDuplicataNaMesmaFazendaContinuaBarrada:
    def test_mesma_fazenda_nao_pode_duplicar_numero(self, engine):
        with Session(engine) as s:
            s.add(Animal(numero="100", fazenda_id=1, ativo=True))
            s.commit()

        with Session(engine) as s:
            s.add(Animal(numero="100", fazenda_id=1, ativo=True))
            with pytest.raises(IntegrityError):
                s.commit()
