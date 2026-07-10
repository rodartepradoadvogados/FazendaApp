"""
Testes da ficha única do animal (GET /animais/{numero}/ficha) — reúne
absolutamente todos os lançamentos já registrados para um animal.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    Animal, BaixaAnimal, ColostragemBezerra, ControleLeiteiro, MovimentoLote, Parto, PesagemCorporal,
    ProtocoloSanitario, ProtocoloSanitarioLancamento, Sanidade, Secagem, Servico,
)


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


class TestFichaAnimal:
    def test_animal_inexistente_404(self, client):
        c, engine = client
        r = c.get("/animais/999/ficha")
        assert r.status_code == 404

    def test_reune_todos_os_lancamentos_do_animal(self, client):
        c, engine = client
        with Session(engine) as s:
            animal = Animal(numero="500", sexo="F", data_nasc=date(2023, 1, 1))
            s.add(animal)
            s.commit()
            s.refresh(animal)

            s.add(Parto(animal_id=animal.id, numero_matriz="500", data_parto=date(2025, 1, 10), ordem_parto=1))
            s.add(Servico(animal_id=animal.id, numero_matriz="500", data_servico=date(2024, 4, 1), tipo_servico="IA", diagnostico="POSITIVO"))
            s.add(MovimentoLote(numero_matriz="500", lote_destino="Lote 2", data_movimento=date(2025, 1, 11)))
            s.add(ColostragemBezerra(animal_id=animal.id, numero_animal="500", brix_colostro=22.0))
            s.add(ControleLeiteiro(animal_id=animal.id, numero_matriz="500", data_controle=date(2025, 2, 1), producao_kg=25.0))
            s.add(PesagemCorporal(numero_matriz="500", data_pesagem=date(2025, 2, 1), peso_kg=450.0))
            s.add(Sanidade(numero_matriz="500", produto="Vacina X", data_aplicacao=date(2025, 1, 15)))
            s.add(Secagem(numero_matriz="500", data_secagem=date(2025, 11, 1), motivo="rotina"))
            s.add(BaixaAnimal(numero_animal="500", tipo_baixa="descarte_voluntario", motivo="venda", valor=3000.0, data_baixa=date(2026, 1, 1)))

            protocolo = ProtocoloSanitario(nome="Vermifugação padrão")
            s.add(protocolo)
            s.commit()
            s.refresh(protocolo)
            s.add(ProtocoloSanitarioLancamento(protocolo_id=protocolo.id, numero_matriz="500", data_inicio=date(2025, 3, 1)))
            s.commit()

        r = c.get("/animais/500/ficha")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["animal"]["numero"] == "500"
        assert len(corpo["partos"]) == 1
        assert len(corpo["servicos"]) == 1
        assert len(corpo["movimentos_lote"]) == 1
        assert corpo["colostragem"]["brix_colostro"] == 22.0
        assert len(corpo["controles_leiteiros"]) == 1
        assert len(corpo["pesagens_corporais"]) == 1
        assert len(corpo["aplicacoes_sanitarias"]) == 1
        assert len(corpo["secagens"]) == 1
        assert corpo["baixa"]["valor"] == 3000.0
        assert len(corpo["protocolos_sanitarios"]) == 1
        assert corpo["protocolos_sanitarios"][0]["protocolo_nome"] == "Vermifugação padrão"

    def test_animal_sem_lancamentos_retorna_listas_vazias(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="501", sexo="F"))
            s.commit()
        r = c.get("/animais/501/ficha")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["partos"] == []
        assert corpo["colostragem"] is None
        assert corpo["baixa"] is None
