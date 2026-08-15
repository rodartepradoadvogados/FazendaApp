"""
G16 — PUT /central-protocolos/{origem}/{origem_id}: edição de data de
início/responsável/observação/nome, genérico para as 4 origens com ação
(iatf, inducao, customizado, lida). Mudar a data de início bloqueia se
alguma etapa já foi aplicada e, quando permitido, desloca TODAS as
`data_prevista` das aplicações pelo mesmo delta.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda,
    ProtocoloIatfAplicacao, ProtocoloIatfLancamento,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento,
)
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento

DATA_D0 = date(2026, 3, 1)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


@pytest.fixture
def client_fazenda():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _criar_iatf(engine, *, fazenda_id=None, nome=None, realizada=False):
    nome = nome or gerar_nome_lancamento("Protocolo IATF", DATA_D0, 0, 7)
    with Session(engine) as s:
        l = ProtocoloIatfLancamento(nome_protocolo=nome, data_d0=DATA_D0, ativo=True, fazenda_id=fazenda_id)
        s.add(l)
        s.commit()
        s.refresh(l)
        s.add(ProtocoloIatfAplicacao(
            lancamento_id=l.id, numero_matriz="700", dia=0, descricao="D0",
            data_prevista=DATA_D0, realizada=realizada, fazenda_id=fazenda_id,
        ))
        s.add(ProtocoloIatfAplicacao(
            lancamento_id=l.id, numero_matriz="700", dia=7, descricao="D7",
            data_prevista=DATA_D0 + timedelta(days=7), realizada=False, fazenda_id=fazenda_id,
        ))
        s.commit()
        return l.id


class TestEditarLancamentoProtocolo:
    def test_muda_data_e_desloca_todas_as_aplicacoes(self, client):
        c, engine = client
        lid = _criar_iatf(engine)
        nova_data = DATA_D0 + timedelta(days=3)

        r = c.put(f"/central-protocolos/iatf/{lid}", json={"data_inicio": nova_data.isoformat()})
        assert r.status_code == 200
        assert r.json()["data_inicio"] == nova_data.isoformat()

        with Session(engine) as s:
            l = s.get(ProtocoloIatfLancamento, lid)
            assert l.data_d0 == nova_data
            aps = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lid)).all()
            dias = {a.dia: a.data_prevista for a in aps}
            assert dias[0] == nova_data
            assert dias[7] == nova_data + timedelta(days=7)

    def test_bloqueia_quando_etapa_ja_aplicada(self, client):
        c, engine = client
        lid = _criar_iatf(engine, realizada=True)

        r = c.put(f"/central-protocolos/iatf/{lid}", json={"data_inicio": (DATA_D0 + timedelta(days=1)).isoformat()})
        assert r.status_code == 400
        assert "aplicad" in r.json()["detail"].lower()

        with Session(engine) as s:
            l = s.get(ProtocoloIatfLancamento, lid)
            assert l.data_d0 == DATA_D0  # nada mudou

    def test_protocolo_encerrado_da_400(self, client):
        c, engine = client
        lid = _criar_iatf(engine)
        with Session(engine) as s:
            l = s.get(ProtocoloIatfLancamento, lid)
            l.encerrado_em = date.today()
            s.add(l)
            s.commit()

        r = c.put(f"/central-protocolos/iatf/{lid}", json={"responsavel": "João"})
        assert r.status_code == 400
        assert "encerrado" in r.json()["detail"].lower()

    def test_nome_autogerado_e_regravado_ao_mudar_a_data(self, client):
        c, engine = client
        lid = _criar_iatf(engine)  # nome já é o auto-gerado para DATA_D0
        nova_data = DATA_D0 + timedelta(days=5)

        r = c.put(f"/central-protocolos/iatf/{lid}", json={"data_inicio": nova_data.isoformat()})
        assert r.status_code == 200

        esperado = gerar_nome_lancamento("Protocolo IATF", nova_data, 0, 7)
        assert r.json()["nome"] == esperado

    def test_nome_manual_e_preservado_ao_mudar_a_data(self, client):
        c, engine = client
        lid = _criar_iatf(engine, nome="Lote especial do zootecnista")
        nova_data = DATA_D0 + timedelta(days=5)

        r = c.put(f"/central-protocolos/iatf/{lid}", json={"data_inicio": nova_data.isoformat()})
        assert r.status_code == 200
        assert r.json()["nome"] == "Lote especial do zootecnista"

    def test_responsavel_observacao_e_nome_editaveis_direto(self, client):
        c, engine = client
        lid = _criar_iatf(engine)

        r = c.put(f"/central-protocolos/iatf/{lid}", json={
            "responsavel": "Maria", "observacao": "Repasse", "nome": "Nome escolhido à mão",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["responsavel"] == "Maria"
        assert body["nome"] == "Nome escolhido à mão"

    def test_funciona_para_inducao_tambem(self, client):
        c, engine = client
        with Session(engine) as s:
            l = ProtocoloInducaoLancamento(
                protocolo_id=1, nome_protocolo="Indução teste", data_d0=DATA_D0, ativo=True,
            )
            s.add(l)
            s.commit()
            s.refresh(l)
            s.add(ProtocoloInducaoAplicacao(
                lancamento_id=l.id, numero_matriz="800", dia=0, descricao="D0",
                data_prevista=DATA_D0, realizada=False,
            ))
            s.commit()
            lid = l.id

        nova_data = DATA_D0 + timedelta(days=2)
        r = c.put(f"/central-protocolos/inducao/{lid}", json={"data_inicio": nova_data.isoformat()})
        assert r.status_code == 200

        with Session(engine) as s:
            l = s.get(ProtocoloInducaoLancamento, lid)
            assert l.data_d0 == nova_data
            ap = s.exec(select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.lancamento_id == lid)).first()
            assert ap.data_prevista == nova_data

    def test_lancamento_de_outra_fazenda_da_404(self, client_fazenda):
        c, engine = client_fazenda
        lid_outra = _criar_iatf(engine, fazenda_id=2)

        r = c.put(f"/central-protocolos/iatf/{lid_outra}", json={"responsavel": "Alguém"})
        assert r.status_code == 404
