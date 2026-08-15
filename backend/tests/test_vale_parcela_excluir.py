"""
Testes do G15 — DELETE /cadastro/vales/{vale_id}/parcelas/{parcela_id}:
exclusão de UMA parcela de um vale de funcionário (endpoint próprio, com
reconciliação via `_reconciliar_vale_competencias` — não passa pelo motor
genérico de `exclusoes.py`).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, FolhaPagamento, Pessoa, ValeFuncionario, ValeParcela


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        # DELETE /cadastro/vales/.../parcelas/... exige o módulo comercial
        # "financeiro" contratado (RH passou a exigi-lo — ver
        # cadastro/__init__.py). test_isolamento_entre_fazendas troca a
        # fazenda atual para 1 via override — sem o módulo aqui, o teste
        # levaria 403 antes de chegar na checagem de isolamento que quer
        # exercitar.
        s.add(ContratoFazendaModulo(fazenda_id=1, modulo="financeiro", ativo=True))
        s.commit()

    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


def _criar_pessoa(engine, nome: str = "Fulano", salario_base: float = 10000.0, fazenda_id: int | None = None) -> int:
    with _sessao(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=salario_base, fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _criar_vale(c, pessoa_id: int, valor_total: float, parcelas: int, competencia_inicio: str) -> dict:
    r = c.post("/cadastro/vales", json={
        "pessoa_id": pessoa_id, "valor_total": valor_total, "forma_pagamento": "desconto_integral_folha",
        "data_pagamento": date.today().isoformat(), "parcelas": parcelas, "competencia_inicio": competencia_inicio,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _parcela_por_competencia(c, vale_id: int, competencia: str) -> dict:
    r = c.get("/cadastro/vales")
    assert r.status_code == 200
    vale = next(v for v in r.json() if v["id"] == vale_id)
    return next(p for p in vale["parcelas_detalhe"] if p["competencia"] == competencia)


class TestExcluirParcelaVale:
    def test_conceder_reduz_soma_mantem_valor_total(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        vale = _criar_vale(c, pessoa_id, valor_total=300.0, parcelas=3, competencia_inicio="2026-01")
        parcela = _parcela_por_competencia(c, vale["id"], "2026-02")

        r = c.delete(f"/cadastro/vales/{vale['id']}/parcelas/{parcela['id']}", params={"acao": "conceder", "confirmar": "true"})
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["valor_total"] == 300.0
        assert dados["soma_parcelas_atual"] == 200.0
        assert dados["diverge_valor_pago"] is True
        assert dados["diferenca_valor_pago"] == -100.0
        competencias = {p["competencia"] for p in dados["parcelas_detalhe"]}
        assert competencias == {"2026-01", "2026-03"}

        with _sessao(engine) as s:
            assert s.get(ValeParcela, parcela["id"]) is None

    def test_redistribuir_igual_mantem_soma_e_sobe_posteriores(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        vale = _criar_vale(c, pessoa_id, valor_total=300.0, parcelas=3, competencia_inicio="2026-01")
        primeira = _parcela_por_competencia(c, vale["id"], "2026-01")

        r = c.delete(
            f"/cadastro/vales/{vale['id']}/parcelas/{primeira['id']}",
            params={"acao": "redistribuir_igual", "confirmar": "true"},
        )
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["soma_parcelas_atual"] == 300.0
        assert dados["diverge_valor_pago"] is False
        valores = {p["competencia"]: p["valor"] for p in dados["parcelas_detalhe"]}
        assert valores == {"2026-02": 150.0, "2026-03": 150.0}

    def test_redistribuir_igual_sem_posteriores_pendentes_bloqueia(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        vale = _criar_vale(c, pessoa_id, valor_total=200.0, parcelas=2, competencia_inicio="2026-01")
        ultima = _parcela_por_competencia(c, vale["id"], "2026-02")

        r = c.delete(
            f"/cadastro/vales/{vale['id']}/parcelas/{ultima['id']}",
            params={"acao": "redistribuir_igual", "confirmar": "true"},
        )
        assert r.status_code == 400
        assert "redistribuir" in r.json()["detail"].lower()

    def test_parcela_de_folha_paga_bloqueia(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        vale = _criar_vale(c, pessoa_id, valor_total=300.0, parcelas=3, competencia_inicio="2026-01")
        parcela = _parcela_por_competencia(c, vale["id"], "2026-02")
        with _sessao(engine) as s:
            s.add(FolhaPagamento(
                pessoa_id=pessoa_id, competencia="2026-02", valor_bruto=3000.0, valor_liquido=2900.0, status="pago",
            ))
            s.commit()

        r = c.delete(f"/cadastro/vales/{vale['id']}/parcelas/{parcela['id']}", params={"confirmar": "true"})
        assert r.status_code == 400
        assert "paga" in r.json()["detail"].lower()

    def test_parcela_unica_bloqueia(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        vale = _criar_vale(c, pessoa_id, valor_total=100.0, parcelas=1, competencia_inicio="2026-01")
        parcela = _parcela_por_competencia(c, vale["id"], "2026-01")

        r = c.delete(f"/cadastro/vales/{vale['id']}/parcelas/{parcela['id']}", params={"confirmar": "true"})
        assert r.status_code == 400
        assert "vale inteiro" in r.json()["detail"]

    def test_sem_confirmar_retorna_409_com_payload_divergencia(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        vale = _criar_vale(c, pessoa_id, valor_total=300.0, parcelas=3, competencia_inicio="2026-01")
        parcela = _parcela_por_competencia(c, vale["id"], "2026-02")

        r = c.delete(f"/cadastro/vales/{vale['id']}/parcelas/{parcela['id']}")
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["valor_parcela"] == 100.0
        assert detail["valor_vale"] == 300.0
        assert detail["soma_apos"] == 200.0
        assert detail["parcelas_pendentes_posteriores"] == 1

    def test_reconciliacao_remove_desconto_fantasma_da_folha(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-02", "valor_bruto": 1000.0,
        })
        assert r.status_code == 200, r.text

        vale = _criar_vale(c, pessoa_id, valor_total=300.0, parcelas=3, competencia_inicio="2026-01")
        r = c.get("/cadastro/folha-pagamento")
        folha = next(f for f in r.json() if f["competencia"] == "2026-02")
        assert folha["valor_vale"] == 100.0
        assert folha["valor_liquido"] == 900.0

        parcela = _parcela_por_competencia(c, vale["id"], "2026-02")
        r = c.delete(f"/cadastro/vales/{vale['id']}/parcelas/{parcela['id']}", params={"acao": "conceder", "confirmar": "true"})
        assert r.status_code == 200, r.text

        r = c.get("/cadastro/folha-pagamento")
        folha = next(f for f in r.json() if f["competencia"] == "2026-02")
        assert folha["valor_vale"] == 0.0
        assert folha["valor_liquido"] == 1000.0

    def test_isolamento_entre_fazendas(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, fazenda_id=2)
        with _sessao(engine) as s:
            vale = ValeFuncionario(
                pessoa_id=pessoa_id, valor_total=200.0, forma_pagamento="desconto_integral_folha",
                data_pagamento=date.today(), parcelas=2, competencia_inicio="2026-01", fazenda_id=2,
            )
            s.add(vale)
            s.commit()
            s.refresh(vale)
            p1 = ValeParcela(vale_id=vale.id, pessoa_id=pessoa_id, competencia="2026-01", valor=100.0, fazenda_id=2)
            p2 = ValeParcela(vale_id=vale.id, pessoa_id=pessoa_id, competencia="2026-02", valor=100.0, fazenda_id=2)
            s.add(p1)
            s.add(p2)
            s.commit()
            s.refresh(p1)
            vale_id, parcela_id = vale.id, p1.id

        from fazenda.auth import get_fazenda_atual_id
        import main
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        try:
            r = c.delete(f"/cadastro/vales/{vale_id}/parcelas/{parcela_id}", params={"confirmar": "true"})
            assert r.status_code == 404
        finally:
            del main.app.dependency_overrides[get_fazenda_atual_id]
