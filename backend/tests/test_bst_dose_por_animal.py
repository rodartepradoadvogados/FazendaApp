"""
POST /agenda/bst/aplicar — `dose_por_animal` (True, padrão) x dose informada
como TOTAL do lote selecionado (False). Bug relatado: a dose sempre era
tratada como "por animal", então quem media o total aplicado ao lote inteiro
via a mesma dose baixada de cada vaca individualmente — o estoque caía N
vezes o valor real.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Estoque, MovimentoEstoque, Sanidade


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        with Session(engine) as s:
            s.add(Animal(numero="301", grupo_primario="01 - Alta", del_dias=70, sexo="F", ativo=True))
            s.add(Animal(numero="302", grupo_primario="01 - Alta", del_dias=75, sexo="F", ativo=True))
            s.add(Animal(numero="303", grupo_primario="01 - Alta", del_dias=80, sexo="F", ativo=True))
            s.add(Estoque(nome="Lactotropin", categoria="medicamento", quantidade=1000.0, unidade="ml", estocavel=True))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


class TestDosePorAnimalOuTotal:
    def test_dose_por_animal_padrao_baixa_a_mesma_dose_de_cada_um(self, client):
        c, engine = client
        r = c.post("/agenda/bst/aplicar", json={
            "numeros_matriz": ["301", "302", "303"], "data_aplicacao": date.today().isoformat(),
            "produto": "Lactotropin", "dose": 2.0, "unidade": "ml", "aplicado": True,
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Lactotropin")).first()
            assert item.quantidade == 1000.0 - 3 * 2.0
            doses = {san.numero_matriz: san.dose for san in s.exec(select(Sanidade)).all()}
            assert doses == {"301": 2.0, "302": 2.0, "303": 2.0}

    def test_dose_total_divide_pelo_numero_de_animais(self, client):
        c, engine = client
        r = c.post("/agenda/bst/aplicar", json={
            "numeros_matriz": ["301", "302", "303"], "data_aplicacao": date.today().isoformat(),
            "produto": "Lactotropin", "dose": 6.0, "dose_por_animal": False, "unidade": "ml", "aplicado": True,
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Lactotropin")).first()
            # Baixa total = 6.0 (o total informado), não 6.0 * 3 = 18.0.
            assert item.quantidade == 1000.0 - 6.0
            doses = {san.numero_matriz: san.dose for san in s.exec(select(Sanidade)).all()}
            assert doses == {"301": 2.0, "302": 2.0, "303": 2.0}

    def test_dose_total_agendada_tambem_divide(self, client):
        c, engine = client
        from fazenda.models import AplicacaoAgendada
        futura = (date.today() + timedelta(days=30)).isoformat()
        r = c.post("/agenda/bst/aplicar", json={
            "numeros_matriz": ["301", "302"], "data_aplicacao": futura,
            "produto": "Lactotropin", "dose": 5.0, "dose_por_animal": False, "unidade": "ml", "aplicado": True,
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            doses = {a.numero_matriz: a.dose for a in s.exec(select(AplicacaoAgendada)).all()}
            assert doses == {"301": 2.5, "302": 2.5}
