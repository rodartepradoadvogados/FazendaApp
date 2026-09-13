"""
Testes da migração idempotente que inativa linhas de Animal(eh_semen=True) —
sêmen/reprodutor importado do sistema anterior como pseudo-animal (categoria
"Indefinido"), sem grupo, que não deveria contar como animal ativo do rebanho.
"""
from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.database import _inativar_animais_semen
from fazenda.models import Animal


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


def test_inativa_apenas_animal_eh_semen_ativo():
    engine = _engine()
    with Session(engine) as s:
        s.add(Animal(numero="SEMEN-1", categoria_completa="Indefinido", sexo=None, eh_semen=True, ativo=True))
        s.add(Animal(numero="VACA-1", categoria_abrev="VL", sexo="F", eh_semen=False, ativo=True, grupo_primario="Lote 1"))
        s.add(Animal(numero="SEMEN-2-JA-INATIVO", categoria_completa="Indefinido", sexo=None, eh_semen=True, ativo=False))
        s.commit()

    import fazenda.database as database
    # `engine_manutencao` e não `engine`: desde 09/09/2026 esta rotina de boot
    # roda pela conexão de DONO (ver create_db_and_tables). Sob RLS ela
    # precisa disso — com a conexão contida da aplicação, a varredura por
    # `eh_semen` devolveria ZERO linhas e a migração não faria nada, em
    # silêncio. Fora do RLS as duas engines são a mesma.
    database.engine = engine
    database.engine_manutencao = engine
    _inativar_animais_semen()

    with Session(engine) as s:
        semen1 = s.exec(select(Animal).where(Animal.numero == "SEMEN-1")).one()
        vaca1 = s.exec(select(Animal).where(Animal.numero == "VACA-1")).one()
        assert semen1.ativo is False
        assert vaca1.ativo is True  # animal real do rebanho não é tocado


def test_idempotente_segunda_chamada_nao_falha():
    engine = _engine()
    with Session(engine) as s:
        s.add(Animal(numero="SEMEN-1", categoria_completa="Indefinido", sexo=None, eh_semen=True, ativo=True))
        s.commit()

    import fazenda.database as database
    # `engine_manutencao` e não `engine`: desde 09/09/2026 esta rotina de boot
    # roda pela conexão de DONO (ver create_db_and_tables). Sob RLS ela
    # precisa disso — com a conexão contida da aplicação, a varredura por
    # `eh_semen` devolveria ZERO linhas e a migração não faria nada, em
    # silêncio. Fora do RLS as duas engines são a mesma.
    database.engine = engine
    database.engine_manutencao = engine
    _inativar_animais_semen()
    _inativar_animais_semen()  # não deve levantar erro nem reverter nada

    with Session(engine) as s:
        semen1 = s.exec(select(Animal).where(Animal.numero == "SEMEN-1")).one()
        assert semen1.ativo is False
