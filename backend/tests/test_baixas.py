"""Testes de baixa de animal (Rebanho > Baixar animal) — óbito/descarte."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ComissaoCorretagem, ContaGerencial


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

    from fazenda.api.routers.cadastro import seed_motivos_baixa

    with TestClient(main.app) as c:
        with Session(engine) as s:
            s.add(Animal(numero="900", grupo_primario="01 - Alta", ativo=True))
            s.add(Animal(numero="901", grupo_primario="01 - Alta", ativo=True))
            seed_motivos_baixa(s)
            s.commit()
        c.engine = engine
        yield c

    main.app.dependency_overrides.clear()


class TestOpcoes:
    def test_lista_tipos_e_motivos(self, client):
        r = client.get("/baixas/motivos")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["tipos_baixa"] == ["morte", "descarte_voluntario", "descarte_involuntario"]
        assert "venda" in corpo["motivos"] and "doenca" in corpo["motivos"]
        assert "Mastite" in corpo["motivos_doenca"]


class TestRegistrarBaixa:
    def test_baixa_por_morte_doenca_marca_animal_inativo(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "morte", "motivo": "doenca",
            "motivo_doenca": "Mastite", "data_baixa": "2026-07-08", "observacao": "teste",
        })
        assert r.status_code == 200
        assert r.json()["baixados"] == 1
        animal = client.get("/animais/900").json()
        assert animal["ativo"] is False
        assert animal["data_baixa"] == "2026-07-08"
        assert animal["motivo_baixa"] == "Mastite"

    def test_baixa_por_venda_exige_valor_e_cliente(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "data_baixa": "2026-07-08",
        })
        assert r.status_code == 400

    def test_baixa_por_venda_com_valor_e_cliente(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 3500.0, "tipo_valor": "por_animal", "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
        })
        assert r.status_code == 200
        historico = client.get("/baixas/").json()
        assert historico[0]["valor"] == 3500.0
        assert historico[0]["cliente"] == "Frigorífico X"

    def test_venda_exige_tipo_valor(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 3500.0, "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
        })
        assert r.status_code == 400

    def test_baixa_doenca_sem_motivo_doenca_da_erro(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "morte", "motivo": "doenca",
            "data_baixa": "2026-07-08",
        })
        assert r.status_code == 400

    def test_baixa_em_lote_varios_animais(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900", "901"], "tipo_baixa": "morte", "motivo": "acidente",
            "data_baixa": "2026-07-08",
        })
        assert r.status_code == 200
        assert r.json()["baixados"] == 2
        assert client.get("/animais/900").json()["ativo"] is False
        assert client.get("/animais/901").json()["ativo"] is False

    def test_animal_inexistente_reportado_sem_quebrar_os_demais(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900", "999"], "tipo_baixa": "morte", "motivo": "abate",
            "data_baixa": "2026-07-08",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["baixados"] == 1
        assert corpo["nao_encontrados"] == ["999"]

    def test_tipo_baixa_invalido_rejeitado(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "sumiu", "motivo": "abate", "data_baixa": "2026-07-08",
        })
        assert r.status_code == 400

    def test_lista_baixas_ordenada_por_data_desc(self, client):
        client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "morte", "motivo": "abate", "data_baixa": "2026-07-01",
        })
        client.post("/baixas/", json={
            "animais": ["901"], "tipo_baixa": "morte", "motivo": "acidente", "data_baixa": "2026-07-08",
        })
        historico = client.get("/baixas/").json()
        assert historico[0]["numero_animal"] == "901"
        assert historico[1]["numero_animal"] == "900"


class TestVendaGeraFinanceiro:
    def test_venda_por_animal_gera_conta_gerencial_receita(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900", "901"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 3000.0, "tipo_valor": "por_animal", "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
        })
        assert r.status_code == 200
        with Session(client.engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Venda de animal")).first()
            assert conta is not None
            assert conta.tipo == "receita"
            assert conta.quantidade == 2
            assert conta.valor_unitario == 3000.0
            assert conta.valor_total == 6000.0
            assert conta.fornecedor_cliente == "Frigorífico X"

        historico = client.get("/baixas/").json()
        assert all(b["valor"] == 3000.0 and b["tipo_valor"] == "por_animal" for b in historico[:2])

    def test_venda_valor_total_divide_igualmente_entre_animais(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900", "901"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 5000.0, "tipo_valor": "total", "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
        })
        assert r.status_code == 200
        with Session(client.engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Venda de animal")).first()
            assert conta.valor_total == 5000.0
            assert conta.valor_unitario == 2500.0

        historico = client.get("/baixas/").json()
        assert all(b["valor"] == 2500.0 and b["tipo_valor"] == "total" for b in historico[:2])

    def test_venda_sem_comissao_nao_gera_comissao(self, client):
        client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 3000.0, "tipo_valor": "por_animal", "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
        })
        with Session(client.engine) as s:
            assert s.exec(select(ComissaoCorretagem)).first() is None


class TestComissaoCorretagem:
    def test_venda_com_comissao_redirecionada_ja_marca_como_paga(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 3000.0, "tipo_valor": "por_animal", "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
            "pagar_comissao": True, "corretor_nome": "João Corretor", "valor_comissao": 150.0,
            "forma_comissao": "redirecionado",
        })
        assert r.status_code == 200
        with Session(client.engine) as s:
            comissao = s.exec(select(ComissaoCorretagem)).first()
            assert comissao is not None
            assert comissao.corretor_nome == "João Corretor"
            assert comissao.forma == "redirecionado"
            venda = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Venda de animal")).first()
            assert venda.valor_total == 3000.0  # valor bruto da venda nunca é líquido da comissão
            despesa_comissao = s.exec(
                select(ContaGerencial).where(ContaGerencial.tipo_documento == "Comissão de corretagem")
            ).first()
            assert despesa_comissao is not None
            assert despesa_comissao.tipo == "despesa"
            assert despesa_comissao.valor_total == 150.0
            assert despesa_comissao.data_pagamento is not None
            assert despesa_comissao.valor_pago == 150.0

    def test_venda_com_comissao_separada_fica_em_aberto(self, client):
        client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 3000.0, "tipo_valor": "por_animal", "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
            "pagar_comissao": True, "corretor_nome": "João Corretor", "valor_comissao": 150.0,
            "forma_comissao": "separado",
        })
        with Session(client.engine) as s:
            despesa_comissao = s.exec(
                select(ContaGerencial).where(ContaGerencial.tipo_documento == "Comissão de corretagem")
            ).first()
            assert despesa_comissao.data_pagamento is None
            assert despesa_comissao.valor_pago is None

    def test_comissao_exige_motivo_venda(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "morte", "motivo": "abate", "data_baixa": "2026-07-08",
            "pagar_comissao": True, "corretor_nome": "João Corretor", "valor_comissao": 150.0,
            "forma_comissao": "redirecionado",
        })
        assert r.status_code == 400

    def test_comissao_exige_forma_valida(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 3000.0, "tipo_valor": "por_animal", "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
            "pagar_comissao": True, "corretor_nome": "João Corretor", "valor_comissao": 150.0,
            "forma_comissao": "invalida",
        })
        assert r.status_code == 400
