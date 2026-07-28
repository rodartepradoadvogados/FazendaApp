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


# ---------------------------------------------------------------------------
# Edição de UMA parcela de vale de funcionário (PUT /vales/{id}/parcelas/{id})
# ---------------------------------------------------------------------------

def _criar_vale_3_parcelas(c, pessoa_id: int) -> dict:
    r = c.post("/cadastro/vales", json={
        "pessoa_id": pessoa_id, "valor_total": 900.0, "forma_pagamento": "pix",
        "data_pagamento": "2026-05-01", "parcelas": 3, "competencia_inicio": "2026-05",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _parcelas_do_vale(engine, vale_id: int) -> list[ValeParcela]:
    with Session(engine) as s:
        return sorted(
            s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all(),
            key=lambda p: p.competencia,
        )


def test_editar_parcela_sem_divergencia_nao_exige_acao(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    vale = _criar_vale_3_parcelas(c, pessoa_id)
    parcelas = _parcelas_do_vale(engine, vale["id"])

    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[0].id}", json={"valor": 300.0})
    assert r.status_code == 200, r.text
    assert r.json()["diverge_valor_pago"] is False


def test_editar_parcela_com_divergencia_sem_confirmar_da_409(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    vale = _criar_vale_3_parcelas(c, pessoa_id)
    parcelas = _parcelas_do_vale(engine, vale["id"])

    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[0].id}", json={"valor": 200.0})
    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe["valor_calculado"] == 300.0
    assert detalhe["diferenca"] == -100.0
    assert detalhe["parcelas_pendentes_restantes"] == 2


def test_editar_parcela_conceder_so_muda_essa_parcela(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    vale = _criar_vale_3_parcelas(c, pessoa_id)
    parcelas = _parcelas_do_vale(engine, vale["id"])

    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[0].id}", json={
        "valor": 200.0, "acao": "conceder", "confirmar": True,
    })
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["soma_parcelas_atual"] == 800.0  # 900 - 100 concedidos
    assert dados["diverge_valor_pago"] is True
    assert dados["diferenca_valor_pago"] == -100.0

    restantes = _parcelas_do_vale(engine, vale["id"])
    assert [p.valor for p in restantes] == [200.0, 300.0, 300.0]  # só a 1ª mudou


def test_editar_parcela_redistribuir_igual_mantem_soma_total(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    vale = _criar_vale_3_parcelas(c, pessoa_id)
    parcelas = _parcelas_do_vale(engine, vale["id"])

    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[0].id}", json={
        "valor": 0.0, "acao": "redistribuir_igual", "confirmar": True,
    })
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["diverge_valor_pago"] is False  # soma continua 900
    assert dados["soma_parcelas_atual"] == 900.0

    restantes = _parcelas_do_vale(engine, vale["id"])
    assert restantes[0].valor == 0.0
    assert restantes[1].valor == 450.0
    assert restantes[2].valor == 450.0


def test_editar_parcela_redistribuir_livre_aplica_valores_informados(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    vale = _criar_vale_3_parcelas(c, pessoa_id)
    parcelas = _parcelas_do_vale(engine, vale["id"])

    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[0].id}", json={
        "valor": 400.0, "acao": "redistribuir_livre", "confirmar": True,
        "valores_parcelas": {parcelas[1].id: 400.0, parcelas[2].id: 100.0},
    })
    assert r.status_code == 200, r.text
    restantes = _parcelas_do_vale(engine, vale["id"])
    assert [p.valor for p in restantes] == [400.0, 400.0, 100.0]


def test_editar_parcela_redistribuir_igual_nao_mexe_em_parcelas_anteriores(client):
    """Regressão: editar a parcela do meio (2/3) com redistribuir_igual só
    pode mexer nas posteriores (3/3) — a 1/3, já vencida/anterior, fica
    intocada."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    vale = _criar_vale_3_parcelas(c, pessoa_id)
    parcelas = _parcelas_do_vale(engine, vale["id"])

    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[1].id}", json={
        "valor": 100.0, "acao": "redistribuir_igual", "confirmar": True,
    })
    assert r.status_code == 200, r.text
    restantes = _parcelas_do_vale(engine, vale["id"])
    assert restantes[0].valor == 300.0  # 1ª parcela intocada
    assert restantes[1].valor == 100.0  # a editada
    assert restantes[2].valor == 500.0  # absorveu toda a diferença (200)


def test_editar_parcela_redistribuir_livre_divergencia_total_exige_confirmacao(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    vale = _criar_vale_3_parcelas(c, pessoa_id)
    parcelas = _parcelas_do_vale(engine, vale["id"])

    # 400 + 400 + 200 = 1000, diferente dos 900 pagos no vale.
    payload = {
        "valor": 400.0, "acao": "redistribuir_livre", "confirmar": True,
        "valores_parcelas": {parcelas[1].id: 400.0, parcelas[2].id: 200.0},
    }
    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[0].id}", json=payload)
    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe["valor_vale"] == 900.0
    assert detalhe["valor_lancado"] == 1000.0
    assert detalhe["diferenca"] == 100.0

    payload["confirmar_divergencia_total"] = True
    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[0].id}", json=payload)
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["soma_parcelas_atual"] == 1000.0
    assert dados["diverge_valor_pago"] is True
    assert dados["diferenca_valor_pago"] == 100.0


def test_editar_parcela_ja_paga_e_bloqueada(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    vale = _criar_vale_3_parcelas(c, pessoa_id)
    parcelas = _parcelas_do_vale(engine, vale["id"])

    with Session(engine) as s:
        folha = FolhaPagamento(
            pessoa_id=pessoa_id, competencia="2026-05", valor_bruto=5000.0, valor_liquido=4700.0, status="pago",
        )
        s.add(folha)
        s.commit()

    r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{parcelas[0].id}", json={"valor": 250.0})
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Vale avulso (empreitada) — mesmo fluxo de divergência (confirmar + 409) e
# redistribuição entre as parcelas pendentes do alvo.
# ---------------------------------------------------------------------------

def _criar_empreitada_3_parcelas(c, pessoa_id: int) -> dict:
    r = c.post("/cadastro/empreitadas", json={
        "pessoa_id": pessoa_id, "descricao": "Cerca nova", "valor_total": 3000.0,
        "tipo_pagamento": "mensal",
        "parcelas": [
            {"data_vencimento": "2026-06-05", "valor": 1000.0},
            {"data_vencimento": "2026-07-05", "valor": 1000.0},
            {"data_vencimento": "2026-08-05", "valor": 1000.0},
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_vale_avulso_editar_com_divergencia_sem_confirmar_da_409(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    empreitada = _criar_empreitada_3_parcelas(c, pessoa_id)

    r = c.post("/cadastro/vale-avulso", json={
        "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 300.0,
        "forma_pagamento": "pix", "data_pagamento": "2026-06-01",
    })
    assert r.status_code == 200, r.text
    vale_id = r.json()["vale"]["id"]

    r = c.put(f"/cadastro/vale-avulso/{vale_id}", json={
        "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 500.0,
        "forma_pagamento": "pix", "data_pagamento": "2026-06-01",
    })
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["diferenca"] == 200.0


def test_vale_avulso_redistribuir_igual_reequilibra_parcelas_pendentes(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    empreitada = _criar_empreitada_3_parcelas(c, pessoa_id)

    r = c.post("/cadastro/vale-avulso", json={
        "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 300.0,
        "forma_pagamento": "pix", "data_pagamento": "2026-06-01",
    })
    vale_id = r.json()["vale"]["id"]
    # abateu 300 da 1ª parcela: 700/1000/1000

    r = c.put(f"/cadastro/vale-avulso/{vale_id}", json={
        "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 900.0,
        "forma_pagamento": "pix", "data_pagamento": "2026-06-01",
        "acao": "redistribuir_igual", "confirmar": True,
    })
    assert r.status_code == 200, r.text
    parcelas = sorted(r.json()["origem"]["parcelas"], key=lambda p: p["data_vencimento"])
    # total pendente após reverter+reaplicar 900: (3000 - 900) = 2100, dividido em 3
    assert [p["valor"] for p in parcelas] == [700.0, 700.0, 700.0]


def test_vale_avulso_relatorio_mostra_parcela_referenciada(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    empreitada = _criar_empreitada_3_parcelas(c, pessoa_id)

    c.post("/cadastro/vale-avulso", json={
        "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 300.0,
        "forma_pagamento": "pix", "data_pagamento": "2026-06-01",
    })

    r = c.get("/cadastro/vale-avulso/todos")
    assert r.status_code == 200, r.text
    vale = r.json()[0]
    assert vale["total_parcelas_origem"] == 3
    assert vale["parcelas_referenciadas"] == [{"numero_parcela": 1, "valor_abatido": 300.0}]
