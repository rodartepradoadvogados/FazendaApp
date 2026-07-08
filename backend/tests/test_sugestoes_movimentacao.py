"""
Testes da sugestão automática de movimentação entre lotes — usa os critérios
já cadastrados por lote (Configurações > Cadastro > Lotes), sem pedir nenhum
parâmetro novo ao usuário.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Lote


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
        yield c, engine

    main.app.dependency_overrides.clear()


class TestSugestoes:
    def test_animal_fora_do_lote_certo_gera_sugestao(self, client):
        c, engine = client
        with Session(engine) as s:
            # Lote 02 exige peso >= 300kg. Vaca "100" está no lote 01 (sem
            # critério) mas pesa 350kg — deveria ser sugerida para o lote 02.
            s.add(Lote(codigo="01", nome="Recém-chegadas"))
            s.add(Lote(codigo="02", nome="Aptas", peso_min=300))
            s.add(Animal(numero="100", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Recém-chegadas", ativo=True))
            s.commit()

        with Session(engine) as s:
            from fazenda.models import PesagemCorporal
            from datetime import date
            s.add(PesagemCorporal(numero_matriz="100", data_pesagem=date.today(), peso_kg=350))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        d = r.json()
        assert d["lotes_com_criterio"] == 1  # só o lote 02 tem critério
        sug = next(s for s in d["sugestoes"] if s["numero_matriz"] == "100")
        assert any(l["codigo"] == "02" for l in sug["lotes_sugeridos"])

    def test_animal_ja_no_lote_certo_nao_gera_sugestao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="Aptas", peso_min=300))
            s.add(Animal(numero="101", categoria_abrev="Vaca", sexo="F", grupo_primario="02 - Aptas", ativo=True))
            s.commit()
            from fazenda.models import PesagemCorporal
            from datetime import date
            s.add(PesagemCorporal(numero_matriz="101", data_pesagem=date.today(), peso_kg=350))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        assert not any(s["numero_matriz"] == "101" for s in r.json()["sugestoes"])

    def test_lote_sem_criterio_nao_entra_na_comparacao(self, client):
        c, engine = client
        with Session(engine) as s:
            # Nenhum lote tem critério — nada pode ser sugerido.
            s.add(Lote(codigo="01", nome="Geral"))
            s.add(Lote(codigo="02", nome="Outro"))
            s.add(Animal(numero="102", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Geral", ativo=True))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        d = r.json()
        assert d["lotes_com_criterio"] == 0
        assert d["sugestoes"] == []

    def test_animal_sem_lote_correspondente_nao_gera_sugestao(self, client):
        c, engine = client
        with Session(engine) as s:
            # Lote exige peso >= 500kg; a vaca não pesa isso e não tem peso
            # registrado — não atende a nenhum lote, então nada a sugerir.
            s.add(Lote(codigo="02", nome="Pesadas", peso_min=500))
            s.add(Animal(numero="103", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Sem lote", ativo=True))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        assert not any(s["numero_matriz"] == "103" for s in r.json()["sugestoes"])
