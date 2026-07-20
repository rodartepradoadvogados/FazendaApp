"""
Correções do financeiro pedidas pelo usuário:
- data_vencimento explícita no lançamento não-parcelado (vai p/ contas a pagar);
- centros de custo canônicos (PL / C|26 / ARR → nomes legíveis);
- Estoque.data_inicio_controle recorta o custo físico do RMCA.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, Estoque
from fazenda.rules.rmca import calcular_custo_fisico


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


def test_data_vencimento_vai_para_conta_a_pagar(client):
    c, engine = client
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Arame", "quantidade": 1, "valor_unitario": 500.0, "valor_total": 500.0}],
        "data_emissao": "2026-04-01",
        "data_vencimento": "2026-05-10",
    })
    assert r.status_code == 201, r.text
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial)).first()
        assert conta.data_vencimento == date(2026, 5, 10)
        assert conta.data_pagamento is None  # nasce em aberto (contas a pagar)


def test_centro_custo_sigla_vira_nome_canonico(client):
    c, engine = client
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Boleto", "quantidade": 1, "valor_unitario": 100.0, "valor_total": 100.0}],
        "centro_custo": "PL",
        "data_emissao": "2026-04-01",
    })
    assert r.status_code == 201, r.text
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial)).first()
        assert conta.centro_custo == "Pecuária Leiteira"


def test_estoque_data_inicio_controle_recorta_custo_fisico():
    # Movimento antes do início do controle não conta no custo físico do RMCA.
    estoque = {"Milho": {"nome": "Milho", "valor_unitario": 2.0, "conta_gerencial_despesa_padrao": "3.01.01",
                          "data_inicio_controle": date(2026, 6, 1)}}
    movimentos = [
        {"nome_item": "Milho", "quantidade": 100, "data_movimento": date(2026, 5, 20)},  # antes → ignora
        {"nome_item": "Milho", "quantidade": 30, "data_movimento": date(2026, 6, 10)},   # depois → conta
    ]
    fisico = calcular_custo_fisico(movimentos, estoque)
    assert fisico["custo_total"] == 60.0  # só 30 × 2,00


def test_calcular_custo_fisico_so_inclui_conta_gerencial_3_01_01():
    # Unidade pura de calcular_custo_fisico (sem DB): só entram no custo
    # físico do RMCA os itens cuja conta_gerencial_despesa_padrao começa com
    # "3.01.01" — os demais, mesmo com movimento de "Saída de ajuste" no
    # período, ficam de fora.
    estoque = {
        "Ração concentrada": {"nome": "Ração concentrada", "valor_unitario": 2.0,
                               "conta_gerencial_despesa_padrao": "3.01.01"},
        "Milho moído": {"nome": "Milho moído", "valor_unitario": 1.5,
                        "conta_gerencial_despesa_padrao": "3.01.01.02"},  # dentro de 3.01.01 → conta
        "Medicamento X": {"nome": "Medicamento X", "valor_unitario": 10.0,
                          "conta_gerencial_despesa_padrao": "3.02.01"},  # fora → não conta
        "Item sem conta": {"nome": "Item sem conta", "valor_unitario": 5.0,
                           "conta_gerencial_despesa_padrao": None},  # sem conta → não conta
    }
    movimentos = [
        {"nome_item": "Ração concentrada", "quantidade": 100, "data_movimento": None},
        {"nome_item": "Milho moído", "quantidade": 40, "data_movimento": None},
        {"nome_item": "Medicamento X", "quantidade": 5, "data_movimento": None},
        {"nome_item": "Item sem conta", "quantidade": 3, "data_movimento": None},
    ]
    fisico = calcular_custo_fisico(movimentos, estoque)
    assert fisico["custo_total"] == 260.0  # 100×2,00 + 40×1,50 = 200 + 60
    assert sorted(i["ingrediente"] for i in fisico["itens"]) == ["Milho moído", "Ração concentrada"]


def test_opcoes_traz_centros_canonicos(client):
    c, _ = client
    r = c.get("/financeiro/opcoes")
    assert r.status_code == 200
    centros = r.json()["centros_custo"]
    for nome in ("Pecuária Leiteira", "Financiamento 2026", "Arrendamento"):
        assert nome in centros
