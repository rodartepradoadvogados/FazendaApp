"""
Vale de funcionário × folha de pagamento (correções pedidas pelo usuário):
- "descontos de folha" e "descontos de vale" são colunas SEPARADAS;
- um vale lançado DEPOIS de uma folha (não paga) da mesma competência ainda
  precisa reduzir aquela folha (self-heal na leitura);
- vale parcelado espalha as parcelas por competências consecutivas;
- edição de uma conta gerencial pelo novo PUT altera o valor_total.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaGerencial, FolhaPagamento, LancamentoItem, Pessoa, ValeFuncionario, ValeParcela,
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


def _criar_pessoa(engine, salario_base: float = 3000.0) -> int:
    with Session(engine) as s:
        p = Pessoa(nome="Fulano", tipo="Funcionário", salario_base=salario_base)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def test_vale_apos_folha_reduz_no_get_self_heal(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3000.0)

    # Folha lançada primeiro, sem vale — líquido = bruto.
    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-03", "valor_bruto": 3000.0,
    })
    assert r.status_code == 200, r.text
    assert r.json()["valor_liquido"] == 3000.0
    assert r.json()["valor_vale"] == 0.0

    # Um vale aparece DEPOIS, direto no banco (parcela da mesma competência),
    # simulando o lançamento que antes não reduzia a folha existente.
    with Session(engine) as s:
        vale = ValeFuncionario(
            pessoa_id=pessoa_id, valor_total=500.0, forma_pagamento="pix",
            data_pagamento=date(2026, 3, 1), parcelas=1, competencia_inicio="2026-03",
        )
        s.add(vale)
        s.commit()
        s.refresh(vale)
        s.add(ValeParcela(vale_id=vale.id, pessoa_id=pessoa_id, competencia="2026-03", valor=500.0))
        s.commit()

    # O GET faz o self-heal: valor_vale e valor_liquido passam a refletir o vale.
    r = c.get("/cadastro/folha-pagamento")
    assert r.status_code == 200, r.text
    folha = next(f for f in r.json() if f["competencia"] == "2026-03")
    assert folha["valor_vale"] == 500.0
    assert folha["valor_liquido"] == 2500.0
    # "descontos de folha" continua separado e zerado (não absorveu o vale).
    assert folha["descontos"] == 0.0

    # A conta a pagar vinculada também é sincronizada.
    with Session(engine) as s:
        registro = s.exec(select(FolhaPagamento).where(FolhaPagamento.competencia == "2026-03")).first()
        conta = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
        ).first()
        assert conta.valor_total == 2500.0


def test_vale_duas_parcelas_cai_em_competencias_consecutivas(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)

    r = c.post("/cadastro/vales", json={
        "pessoa_id": pessoa_id, "valor_total": 1000.0, "forma_pagamento": "pix",
        "data_pagamento": "2026-03-01", "parcelas": 2, "competencia_inicio": "2026-03",
    })
    assert r.status_code == 201 or r.status_code == 200, r.text
    detalhe = {d["competencia"]: d["valor"] for d in r.json()["parcelas_detalhe"]}
    assert detalhe == {"2026-03": 500.0, "2026-04": 500.0}

    with Session(engine) as s:
        parcelas = s.exec(select(ValeParcela).where(ValeParcela.pessoa_id == pessoa_id)).all()
        por_comp = {p.competencia: p.valor for p in parcelas}
        assert por_comp == {"2026-03": 500.0, "2026-04": 500.0}


def test_editar_conta_gerencial_altera_valor_total(client):
    c, engine = client
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Ração", "quantidade": 1, "valor_unitario": 500.0, "valor_total": 500.0}],
        "data_emissao": "2026-04-01",
    })
    assert r.status_code == 201, r.text
    conta_id = r.json()["ids"][0]

    r = c.put(f"/financeiro/lancamentos/{conta_id}", json={
        "valor_total": 750.0, "descricao": "Ração ajustada",
    })
    assert r.status_code == 200, r.text
    assert r.json()["valor_total"] == 750.0
    assert r.json()["descricao"] == "Ração ajustada"

    # Parcela única + 1 item → espelha no LancamentoItem (relatórios coerentes).
    with Session(engine) as s:
        item = s.exec(select(LancamentoItem)).first()
        assert item.valor_total == 750.0
        assert item.descricao == "Ração ajustada"


def test_editar_conta_inexistente_404(client):
    c, _ = client
    r = c.put("/financeiro/lancamentos/999999", json={"descricao": "x"})
    assert r.status_code == 404, r.text
