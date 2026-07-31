"""
Bug relatado: vaca que pariu recentemente aparecia com DEL 0 e categoria
ainda "Novilha ges." na Ficha do animal e no seletor de Lançamentos >
Produção, porque `Animal.del_dias`/`categoria_completa`/`categoria_abrev` só
são atualizados no próximo upload do GERAL.csv (Ideagri) — `registrar_parto`
zera o DEL mas não corrige a categoria, e nada incrementa o DEL entre imports.

GET /animais e GET /animais/{numero}/ficha agora corrigem os dois campos AO
VIVO a partir do Parto (e Secagem) mais recente já lançado no app, igual ao
racional já usado em info_secagem/lote_criterios para o mesmo problema.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Parto, Secagem


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


class TestListarAnimaisAoVivo:
    def test_vaca_recem_parida_corrige_del_e_categoria(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="1274", sexo="F", ativo=True, del_dias=0,
                categoria_completa="Novilha ges.", categoria_abrev="Novilha ges.",
                grupo_primario="01 - Novilhas Alta",
            ))
            s.add(Parto(numero_matriz="1274", data_parto=hoje - timedelta(days=12), ordem_parto=1))
            s.commit()

        r = c.get("/animais/", params={"ativo": True})
        assert r.status_code == 200
        animal = next(a for a in r.json() if a["numero"] == "1274")
        assert animal["del_dias"] == 12
        assert animal["categoria_completa"] == "Vaca em lactação"
        assert animal["categoria_abrev"] == "Vaca em lactação"

    def test_vaca_ja_seca_nao_conta_del_e_mostra_seca(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="900", sexo="F", ativo=True, del_dias=250,
                categoria_completa="Vaca lactação", categoria_abrev="Vaca lactação",
            ))
            s.add(Parto(numero_matriz="900", data_parto=hoje - timedelta(days=305), ordem_parto=3))
            s.add(Secagem(numero_matriz="900", data_secagem=hoje - timedelta(days=10), motivo="rotina"))
            s.commit()

        r = c.get("/animais/", params={"ativo": True})
        animal = next(a for a in r.json() if a["numero"] == "900")
        assert animal["del_dias"] is None
        # Categoria já dizia "vaca" — texto original preservado (não mexe).
        assert animal["categoria_completa"] == "Vaca lactação"

    def test_novilha_ainda_nao_pariu_categoria_e_del_intocados(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(
                numero="2000", sexo="F", ativo=True, del_dias=None,
                categoria_completa="Novilha", categoria_abrev="Novilha",
            ))
            s.commit()

        r = c.get("/animais/", params={"ativo": True})
        animal = next(a for a in r.json() if a["numero"] == "2000")
        assert animal["del_dias"] is None
        assert animal["categoria_completa"] == "Novilha"


class TestFichaAnimalAoVivo:
    def test_ficha_corrige_del_e_categoria_apos_parto(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="2074", sexo="F", ativo=True, del_dias=0,
                categoria_completa="Novilha ges.", categoria_abrev="Novilha ges.",
            ))
            s.add(Parto(numero_matriz="2074", data_parto=hoje - timedelta(days=20), ordem_parto=1))
            s.commit()

        r = c.get("/animais/2074/ficha")
        assert r.status_code == 200
        animal = r.json()["animal"]
        assert animal["del_dias"] == 20
        assert animal["categoria_abrev"] == "Vaca em lactação"
