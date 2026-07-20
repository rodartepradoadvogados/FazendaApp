"""
Testes do relatório de rastreabilidade sanitária (GET
/relatorio-rastreabilidade-sanitaria/) — reconstrói a cadeia sanitária de um
animal (ou de todos os animais ligados a uma GTA) a partir de compra/venda
(com GTA), aplicações sanitárias, protocolos, exames e doenças, filtrável por
número do animal, GTA ou período.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    Animal, BaixaAnimal, CompraAnimal, EventoSanitario, ExameResultado, OcorrenciaClinica,
    ProtocoloSanitario, ProtocoloSanitarioLancamento, Sanidade, VendaAnimal,
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


def _popular(engine):
    with Session(engine) as s:
        s.add(Animal(numero="700", sexo="F", nome="Estrela", data_nasc=date(2022, 1, 1)))
        s.add(Animal(numero="701", sexo="F", nome="Lua", data_nasc=date(2022, 1, 1)))
        s.commit()

        s.add(CompraAnimal(numero_animal="700", vendedor="Fazenda A", valor=3000.0,
                            tipo_valor="por_animal", data_compra=date(2024, 1, 10), gta="GTA-100"))
        s.add(VendaAnimal(numero_animal="700", comprador="Frigorífico B", valor=4000.0,
                           tipo_valor="por_animal", data_venda=date(2025, 1, 5), gta="GTA-200"))
        # Outro animal com GTA diferente — não deve aparecer no filtro por GTA-100.
        s.add(CompraAnimal(numero_animal="701", vendedor="Fazenda C", valor=2500.0,
                            tipo_valor="por_animal", data_compra=date(2024, 2, 1), gta="GTA-999"))

        s.add(Sanidade(numero_matriz="700", produto="Vacina Aftosa", data_aplicacao=date(2024, 3, 1), responsavel="João"))
        s.add(OcorrenciaClinica(numero_matriz="700", doenca="Mastite", data_ocorrencia=date(2024, 4, 1)))
        s.add(BaixaAnimal(numero_animal="700", tipo_baixa="descarte_voluntario", motivo="venda",
                           data_baixa=date(2025, 1, 5), responsavel="Maria"))

        protocolo = ProtocoloSanitario(nome="Vermifugação padrão")
        s.add(protocolo)
        s.commit()
        s.refresh(protocolo)
        s.add(ProtocoloSanitarioLancamento(protocolo_id=protocolo.id, numero_matriz="700",
                                            data_inicio=date(2024, 5, 1), responsavel="Ana"))

        evento = EventoSanitario(nome="Brucelose")
        s.add(evento)
        s.commit()
        s.refresh(evento)
        s.add(ExameResultado(numero_matriz="700", evento_sanitario_id=evento.id,
                              data_exame=date(2024, 6, 1), resultado="negativo", veterinario="Dr. Silva"))
        s.commit()


class TestRelatorioRastreabilidadeSanitaria:
    def test_filtro_por_numero_do_animal(self, client):
        c, engine = client
        _popular(engine)
        r = c.get("/relatorio-rastreabilidade-sanitaria/", params={"numero": "700"})
        assert r.status_code == 200
        linhas = r.json()
        tipos = {l["tipo_evento"] for l in linhas}
        assert tipos == {"Compra", "Venda", "Aplicação sanitária", "Protocolo sanitário", "Exame", "Doença (ocorrência clínica)", "Baixa"}
        assert all(l["numero_animal"] == "700" for l in linhas)
        # Ordenado cronologicamente.
        datas = [l["data"] for l in linhas]
        assert datas == sorted(datas)
        assert any(l["gta"] == "GTA-100" for l in linhas)
        assert any(l["gta"] == "GTA-200" for l in linhas)

    def test_filtro_por_gta_encontra_o_animal_certo(self, client):
        c, engine = client
        _popular(engine)
        r = c.get("/relatorio-rastreabilidade-sanitaria/", params={"gta": "GTA-100"})
        assert r.status_code == 200
        linhas = r.json()
        assert linhas
        assert all(l["numero_animal"] == "700" for l in linhas)

    def test_filtro_por_periodo(self, client):
        c, engine = client
        _popular(engine)
        r = c.get("/relatorio-rastreabilidade-sanitaria/", params={
            "numero": "700", "data_de": "2024-05-01", "data_ate": "2024-06-30",
        })
        assert r.status_code == 200
        linhas = r.json()
        tipos = {l["tipo_evento"] for l in linhas}
        assert tipos == {"Protocolo sanitário", "Exame"}

    def test_gta_inexistente_retorna_vazio(self, client):
        c, engine = client
        _popular(engine)
        r = c.get("/relatorio-rastreabilidade-sanitaria/", params={"gta": "GTA-NAO-EXISTE"})
        assert r.status_code == 200
        assert r.json() == []

    def test_nome_do_animal_vem_junto(self, client):
        c, engine = client
        _popular(engine)
        r = c.get("/relatorio-rastreabilidade-sanitaria/", params={"numero": "700"})
        linhas = r.json()
        assert all(l["nome_animal"] == "Estrela" for l in linhas)
