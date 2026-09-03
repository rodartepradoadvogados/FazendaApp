"""
Central de Protocolos — seletor de frasco/lote para o protocolo Sanitário
(01/09/2026). Pedido do usuário: mesmo campo "de qual frasco/lote?" que a
aplicação avulsa de Sanidade já tem (Fase G), agora também na baixa/estorno
via Central de Protocolos.

Cobre: `detalhe()` populando `hormonios[].opcoes[].lotes`, `dar_baixa` com
`estoque_id`/`lote_id` explícitos bypassando FIFO, e `desfazer_aplicacao`
devolvendo no MESMO lote que a baixa consumiu (não em outro escolhido de
novo por FIFO/nome).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import Animal, LoteEstoque


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


def _animais(engine, numeros):
    with Session(engine) as s:
        for n in numeros:
            s.add(Animal(numero=n, ativo=True))
        s.commit()


def _sanitario_com_dois_lotes(c, engine):
    """Um item de estoque com DOIS lotes abertos + um protocolo sanitário
    (D0) cujo produto é esse item — o cenário que exercita a escolha
    explícita de frasco/lote na Central."""
    item_id = c.post("/estoque/", json={
        "nome": "Borgal", "categoria": "Medicamento", "unidade": "ml",
    }).json()["id"]
    lote_a = c.post(f"/estoque/{item_id}/lotes", json={
        "quantidade": 50, "data_compra": "2026-06-01", "numero_lote": "A",
    }).json()
    lote_b = c.post(f"/estoque/{item_id}/lotes", json={
        "quantidade": 50, "data_compra": "2026-06-15", "numero_lote": "B",
    }).json()
    _animais(engine, ["700", "701"])
    pid = c.post("/cadastro/protocolos-sanitarios", json={
        "nome": "Mastite - Protocolo padrão",
        "etapas": [{"dia": 0, "produto": "Borgal", "dosagem": 40.0, "unidade": "ml", "via": "Intramuscular"}],
    }).json()
    c.post("/sanidade/protocolos/lancamentos", json={
        "protocolo_id": pid["id"], "numeros_matriz": ["700", "701"], "data_inicio": date.today().isoformat(),
    })
    lid = next(
        l["origem_id"] for l in c.get("/central-protocolos/acompanhamento").json()
        if l["origem"] == "sanitario"
    )
    return lid, item_id, lote_a["id"], lote_b["id"]


class TestDetalheTrazOpcoesDeFrascoELote:
    def test_dia_traz_hormonios_com_opcoes_e_lotes(self, client):
        c, engine = client
        lid, item_id, lote_a_id, lote_b_id = _sanitario_com_dois_lotes(c, engine)
        det = c.get(f"/central-protocolos/sanitario/{lid}").json()
        dia0 = next(d for d in det["dias"] if d["dia"] == 0)
        assert dia0["hormonios"], "dia sem hormônios/opções — seletor de frasco não apareceria na tela"
        hormonio = dia0["hormonios"][0]
        assert hormonio["produto"] == "Borgal"
        opcao = next(o for o in hormonio["opcoes"] if o["estoque_id"] == item_id)
        lotes_ids = {l["id"] for l in opcao.get("lotes", [])}
        assert lotes_ids == {lote_a_id, lote_b_id}


class TestBaixaComFrascoELoteExplicitos:
    def test_baixa_sem_escolha_cai_em_fifo(self, client):
        c, engine = client
        lid, item_id, lote_a_id, lote_b_id = _sanitario_com_dois_lotes(c, engine)
        r = c.post(f"/central-protocolos/sanitario/{lid}/baixa", json={"dia": 0, "animais": ["700"]})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(LoteEstoque, lote_a_id).quantidade_restante == 10  # 50 - 40, o mais antigo
            assert s.get(LoteEstoque, lote_b_id).quantidade_restante == 50  # intocado

    def test_baixa_com_lote_explicito_bypassa_fifo(self, client):
        c, engine = client
        lid, item_id, lote_a_id, lote_b_id = _sanitario_com_dois_lotes(c, engine)
        r = c.post(f"/central-protocolos/sanitario/{lid}/baixa", json={
            "dia": 0, "animais": ["700"],
            "medicamentos": [{"produto": "Borgal", "estoque_id": item_id, "lote_id": lote_b_id}],
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(LoteEstoque, lote_a_id).quantidade_restante == 50  # intocado — pedido explícito no B
            assert s.get(LoteEstoque, lote_b_id).quantidade_restante == 10  # 50 - 40


class TestDesfazerRestauraNoMesmoLote:
    def test_desfazer_aplicacao_devolve_no_lote_que_foi_consumido(self, client):
        c, engine = client
        lid, item_id, lote_a_id, lote_b_id = _sanitario_com_dois_lotes(c, engine)
        # Escolhe explicitamente o lote B — se o estorno resolvesse por FIFO/
        # nome de novo, devolveria no A (mais antigo), não no B (consumido).
        c.post(f"/central-protocolos/sanitario/{lid}/baixa", json={
            "dia": 0, "animais": ["700"],
            "medicamentos": [{"produto": "Borgal", "estoque_id": item_id, "lote_id": lote_b_id}],
        })
        with Session(engine) as s:
            assert s.get(LoteEstoque, lote_b_id).quantidade_restante == 10

        r = c.request("DELETE", f"/central-protocolos/sanitario/{lid}/baixa", json={"dia": 0, "numero_matriz": "700"})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            assert s.get(LoteEstoque, lote_b_id).quantidade_restante == 50, "estorno tem que voltar pro lote B, não pro A"
            assert s.get(LoteEstoque, lote_a_id).quantidade_restante == 50, "lote A nunca devia ter sido tocado"
