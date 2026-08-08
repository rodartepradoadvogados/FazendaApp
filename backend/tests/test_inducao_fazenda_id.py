"""
Lançamento de protocolo de indução de lactação (POST /producao/inducao-lactacao)
não carimbava fazenda_id em nenhum dos 3 registros que cria (Lancamento,
Medicamento, Aplicacao) nem filtrava por fazenda ao listar — por isso um
lançamento existia e aparecia em /producao/inducao-lactacao/ativos (que não
filtrava por fazenda), mas sumia da Central de Protocolos > Acompanhamento
(GET /central-protocolos/acompanhamento, que sempre filtrou por fazenda_id).
Cobre: fazenda_id carimbado ao lançar; aparece no Acompanhamento da MESMA
fazenda; NÃO aparece no Acompanhamento de outra fazenda; um lançamento antigo
com fazenda_id NULL (dado de antes desta correção) continua visível — não
fica órfão.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    # /producao e /cadastro exigem contrato ativo (+ módulo "produtivo" no
    # caso de /producao) — sem isso todo POST cai em 403 antes mesmo de
    # chegar na lógica de fazenda_id que este arquivo testa.
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="produtivo", ativo=True))
        s.commit()

    estado = {"fazenda_id": 1}
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: estado["fazenda_id"]

    with TestClient(main.app) as c:
        yield c, engine, estado

    main.app.dependency_overrides.clear()


def _criar_molde(c, nome="Indução padrão"):
    r = c.post("/cadastro/protocolos-inducao-lactacao", json={
        "nome": nome,
        "etapas": [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
            {"dia": 3, "tipo": "manejo", "produto": "Iniciar ordenha"},
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestFazendaIdCarimbado:
    def test_lancamento_carimba_fazenda_id(self, client):
        c, engine, estado = client
        pid = _criar_molde(c)
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": pid, "animais": ["422"], "data_d0": "2026-08-04",
        })
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]

        with Session(engine) as s:
            lanc = s.get(ProtocoloInducaoLancamento, lancamento_id)
            assert lanc.fazenda_id == 1
            aps = s.exec(
                select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.lancamento_id == lancamento_id)
            ).all()
            assert aps and all(a.fazenda_id == 1 for a in aps)

    def test_aparece_no_acompanhamento_da_mesma_fazenda(self, client):
        c, engine, estado = client
        pid = _criar_molde(c)
        c.post("/producao/inducao-lactacao", json={
            "protocolo_id": pid, "animais": ["422"], "data_d0": "2026-08-04",
        })
        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert any(l["origem"] == "inducao" for l in linhas)

    def test_nao_aparece_no_acompanhamento_de_outra_fazenda(self, client):
        c, engine, estado = client
        pid = _criar_molde(c)
        c.post("/producao/inducao-lactacao", json={
            "protocolo_id": pid, "animais": ["422"], "data_d0": "2026-08-04",
        })
        estado["fazenda_id"] = 2
        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert not any(l["origem"] == "inducao" for l in linhas)


class TestCompatibilidadeComLancamentoAntigo:
    def test_lancamento_com_fazenda_id_nulo_continua_visivel(self, client):
        # Simula um lançamento feito ANTES desta correção (fazenda_id nunca
        # foi carimbado) — não pode virar órfão depois que a listagem passa
        # a filtrar por fazenda.
        c, engine, estado = client
        with Session(engine) as s:
            lanc = ProtocoloInducaoLancamento(
                protocolo_id=1, nome_protocolo="INDUÇÃO ANTIGA — 01/01/26 A 10/01/26", data_d0=date(2026, 1, 1),
                fazenda_id=None,
            )
            s.add(lanc)
            s.commit()
            s.refresh(lanc)
            s.add(ProtocoloInducaoAplicacao(
                lancamento_id=lanc.id, numero_matriz="100", dia=0, descricao="D0",
                data_prevista=date(2026, 1, 1), fazenda_id=None,
            ))
            s.commit()

        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert any(l["nome"] == "INDUÇÃO ANTIGA — 01/01/26 A 10/01/26" for l in linhas)

        ativos = c.get("/producao/inducao-lactacao/ativos").json()
        assert any(a["nome_protocolo"] == "INDUÇÃO ANTIGA — 01/01/26 A 10/01/26" for a in ativos)
