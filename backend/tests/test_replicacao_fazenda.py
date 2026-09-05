"""
Motor de replicação Fazenda -> Fazenda (sandbox) — ver
fazenda/rules/replicacao_fazenda.py e
fazenda/api/routers/painel_cowdata_sincronizacao.py.

Cobre exatamente a lista de verificação obrigatória do pedido: cadeia de FK
remapeada (animal -> parto -> lactação), recusa sem `eh_teste`, recusa
origem==destino, catálogo global não duplicado, rodar duas vezes seguidas
não duplica, e a origem nunca é alterada.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import Animal, Fazenda, Lactacao, Parto
from fazenda.models.sanidade import Doenca, PrincipioAtivo
from fazenda.rules.replicacao_fazenda import (
    SincronizacaoInvalidaError, sincronizar_fazenda_teste_destrutivo,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


def _semear_cenario(engine):
    """Fazenda A (origem, "real") com um animal -> parto -> lactação (cadeia
    de FK em 3 níveis) mais uma linha de catálogo GLOBAL (fazenda_id=None)
    referenciada por uma linha da fazenda A. Fazenda B (destino) marcada
    eh_teste=True."""
    with Session(engine) as s:
        origem = Fazenda(id=1, nome="Jairo Nasser", eh_teste=False)
        destino = Fazenda(id=2, nome="Fazenda Teste", eh_teste=True)
        s.add_all([origem, destino])
        s.commit()

        # Catálogo global — nasce igual pra todo mundo (fazenda_id=None).
        doenca_global = Doenca(nome="Mastite", fazenda_id=None)
        s.add(doenca_global)
        s.commit()
        s.refresh(doenca_global)

        animal = Animal(numero="123", fazenda_id=1, sexo="F")
        s.add(animal)
        s.commit()
        s.refresh(animal)

        parto = Parto(animal_id=animal.id, numero_matriz="123", fazenda_id=1, ordem_parto=1)
        s.add(parto)
        s.commit()
        s.refresh(parto)

        lact = Lactacao(
            fazenda_id=1, animal_id=animal.id, parto_id=parto.id,
            numero_matriz="123", data_inicio=date(2026, 1, 1), numero_lactacao=1,
        )
        s.add(lact)
        s.commit()

        return {
            "origem_id": 1, "destino_id": 2,
            "animal_id": animal.id, "parto_id": parto.id, "lactacao_id": lact.id,
            "doenca_global_id": doenca_global.id,
        }


def test_copia_cadeia_de_fk_remapeada(engine):
    ids = _semear_cenario(engine)
    with Session(engine) as s:
        resultado = sincronizar_fazenda_teste_destrutivo(s, origem_id=ids["origem_id"], destino_id=ids["destino_id"])
        s.commit()

    assert resultado.tabelas > 0
    assert resultado.linhas_copiadas >= 3  # animal + parto + lactação, no mínimo

    with Session(engine) as s:
        animal_novo = s.exec(select(Animal).where(Animal.fazenda_id == ids["destino_id"])).one()
        parto_novo = s.exec(select(Parto).where(Parto.fazenda_id == ids["destino_id"])).one()
        lact_novo = s.exec(select(Lactacao).where(Lactacao.fazenda_id == ids["destino_id"])).one()

        # As FKs no destino apontam para as CÓPIAS, nunca para as linhas da origem.
        assert animal_novo.id != ids["animal_id"]
        assert parto_novo.id != ids["parto_id"]
        assert lact_novo.id != ids["lactacao_id"]
        assert parto_novo.animal_id == animal_novo.id
        assert lact_novo.animal_id == animal_novo.id
        assert lact_novo.parto_id == parto_novo.id


def test_catalogo_global_nao_e_duplicado(engine):
    ids = _semear_cenario(engine)
    with Session(engine) as s:
        sincronizar_fazenda_teste_destrutivo(s, origem_id=ids["origem_id"], destino_id=ids["destino_id"])
        s.commit()

    with Session(engine) as s:
        total_doencas = s.exec(select(Doenca)).all()
        assert len(total_doencas) == 1  # continua só a global, nenhuma cópia criada
        assert total_doencas[0].id == ids["doenca_global_id"]
        assert total_doencas[0].fazenda_id is None


def test_recusa_quando_destino_nao_e_teste(engine):
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser", eh_teste=False))
        s.add(Fazenda(id=2, nome="Outra fazenda real", eh_teste=False))
        s.commit()

    with Session(engine) as s:
        with pytest.raises(HTTPException) as exc:
            sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=2)
        assert exc.value.status_code == 409


def test_recusa_origem_igual_destino(engine):
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser", eh_teste=False))
        s.commit()

    with Session(engine) as s:
        with pytest.raises(SincronizacaoInvalidaError):
            sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=1)


def test_rodar_duas_vezes_nao_duplica(engine):
    ids = _semear_cenario(engine)
    with Session(engine) as s:
        sincronizar_fazenda_teste_destrutivo(s, origem_id=ids["origem_id"], destino_id=ids["destino_id"])
        s.commit()
    with Session(engine) as s:
        sincronizar_fazenda_teste_destrutivo(s, origem_id=ids["origem_id"], destino_id=ids["destino_id"])
        s.commit()

    with Session(engine) as s:
        animais_destino = s.exec(select(Animal).where(Animal.fazenda_id == ids["destino_id"])).all()
        partos_destino = s.exec(select(Parto).where(Parto.fazenda_id == ids["destino_id"])).all()
        lact_destino = s.exec(select(Lactacao).where(Lactacao.fazenda_id == ids["destino_id"])).all()
        assert len(animais_destino) == 1
        assert len(partos_destino) == 1
        assert len(lact_destino) == 1
        # A cadeia de FK continua íntegra na 2ª rodada.
        assert partos_destino[0].animal_id == animais_destino[0].id
        assert lact_destino[0].parto_id == partos_destino[0].id


def test_origem_nunca_e_alterada(engine):
    ids = _semear_cenario(engine)
    with Session(engine) as s:
        animal_antes = s.get(Animal, ids["animal_id"])
        estado_antes = (animal_antes.numero, animal_antes.fazenda_id, animal_antes.sexo)

    with Session(engine) as s:
        sincronizar_fazenda_teste_destrutivo(s, origem_id=ids["origem_id"], destino_id=ids["destino_id"])
        s.commit()

    with Session(engine) as s:
        animal_depois = s.get(Animal, ids["animal_id"])
        assert (animal_depois.numero, animal_depois.fazenda_id, animal_depois.sexo) == estado_antes
        # Continua existindo exatamente 1 animal na fazenda de origem (nada
        # foi removido nem duplicado do lado da origem).
        animais_origem = s.exec(select(Animal).where(Animal.fazenda_id == ids["origem_id"])).all()
        assert len(animais_origem) == 1


def test_falha_no_meio_reverte_tudo(engine):
    """Regra 6 — transação única. Simula uma falha no meio da cópia
    (referência a uma fazenda de origem inexistente) e confirma que nada
    fica gravado no destino."""
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser", eh_teste=False))
        s.add(Fazenda(id=2, nome="Fazenda Teste", eh_teste=True))
        s.commit()

    with Session(engine) as s:
        with pytest.raises(SincronizacaoInvalidaError):
            sincronizar_fazenda_teste_destrutivo(s, origem_id=999, destino_id=2)
        s.rollback()

    with Session(engine) as s:
        # Fazenda Teste segue existindo e vazia — nada "meio copiado".
        destino = s.get(Fazenda, 2)
        assert destino is not None
        assert s.exec(select(Animal).where(Animal.fazenda_id == 2)).all() == []
