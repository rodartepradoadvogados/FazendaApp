"""
Lida — tarefas gerais da fazenda por período ou frequência (ver
fazenda/models/lida.py). Cobre: cadastro nos dois modos, lançamento
(frequência gera ocorrências a cada N dias; período expande dia_fim em uma
aplicação por dia), listagem em /lida/ativos, aparecer em Central de
Protocolos > Acompanhamento, baixa com estoque real (dose × nº de aplicações
confirmadas), e cancelamento com estorno (mecanismo genérico já existente
para IATF/indução/customizado, "lida" é só mais uma origem).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, LidaAplicacao, LidaLancamento


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

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(ContratoFazendaModulo(fazenda_id=1, modulo="produtivo", ativo=True))
        s.add(Estoque(fazenda_id=1, nome="Detergente para cochos", quantidade=20, unidade="L"))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _criar_molde_frequencia(c, dar_baixa=True):
    r = c.post("/cadastro/lidas", json={
        "nome": "Limpar cocho", "modo": "frequencia", "frequencia_dias": 15,
        "descricao_evento": "Limpar cocho de água", "insumo_padrao": "Detergente para cochos",
        "insumo_dose": 0.5, "insumo_unidade": "L", "dar_baixa_estoque": dar_baixa,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _criar_molde_periodo(c):
    r = c.post("/cadastro/lidas", json={
        "nome": "Obra da cerca", "modo": "periodo", "dia_inicial": 0,
        "etapas": [{"dia_inicio": 0, "dia_fim": 3, "descricao_evento": "Enviar foto da cerca", "foto_obrigatoria": True}],
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestCadastro:
    def test_cria_molde_frequencia(self, client):
        c, engine = client
        lid = _criar_molde_frequencia(c)
        assert lid > 0

    def test_cria_molde_periodo(self, client):
        c, engine = client
        lid = _criar_molde_periodo(c)
        assert lid > 0

    def test_rejeita_frequencia_sem_intervalo(self, client):
        c, engine = client
        r = c.post("/cadastro/lidas", json={"nome": "X", "modo": "frequencia", "descricao_evento": "Y"})
        assert r.status_code == 400

    def test_rejeita_baixa_sem_dose(self, client):
        c, engine = client
        r = c.post("/cadastro/lidas", json={
            "nome": "X", "modo": "frequencia", "frequencia_dias": 10, "descricao_evento": "Y",
            "insumo_padrao": "Detergente para cochos", "dar_baixa_estoque": True,
        })
        assert r.status_code == 400

    def test_nao_exige_tipo(self, client):
        # Diferença central em relação a Protocolo Customizado: Lida nunca
        # pede Tipo (produtivo/reprodutivo/sanitário) — o payload nem tem
        # esse campo, e ainda assim cadastra normalmente.
        c, engine = client
        lid = _criar_molde_frequencia(c)
        molde = next(m for m in c.get("/cadastro/lidas").json() if m["id"] == lid)
        assert "tipo" not in molde


class TestLancamentoFrequencia:
    def test_gera_ocorrencia_a_cada_n_dias(self, client):
        c, engine = client
        lid = _criar_molde_frequencia(c)
        r = c.post("/lida/lancar", json={
            "lida_id": lid, "data_inicio": "2026-08-01", "data_fim": "2026-10-01",
        })
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]
        with Session(engine) as s:
            aps = s.exec(select(LidaAplicacao).where(LidaAplicacao.lancamento_id == lancamento_id)).all()
            datas = sorted(a.data_prevista for a in aps)
        # 01/08, 16/08, 31/08, 15/09, 30/09 — a cada 15 dias até 01/10.
        assert datas == [date(2026, 8, 1), date(2026, 8, 16), date(2026, 8, 31), date(2026, 9, 15), date(2026, 9, 30)]

    def test_exige_data_fim(self, client):
        c, engine = client
        lid = _criar_molde_frequencia(c)
        r = c.post("/lida/lancar", json={"lida_id": lid, "data_inicio": "2026-08-01"})
        assert r.status_code == 400

    def test_tarefa_da_fazenda_sem_animal(self, client):
        c, engine = client
        lid = _criar_molde_frequencia(c)
        r = c.post("/lida/lancar", json={"lida_id": lid, "data_inicio": "2026-08-01", "data_fim": "2026-08-01"})
        assert r.status_code == 201, r.text
        assert r.json()["animais"] == 0
        with Session(engine) as s:
            aps = s.exec(select(LidaAplicacao).where(LidaAplicacao.lancamento_id == r.json()["lancamento_id"])).all()
            assert aps[0].numero_matriz is None


class TestLancamentoPeriodo:
    def test_expande_dia_fim_em_uma_aplicacao_por_dia(self, client):
        c, engine = client
        lid = _criar_molde_periodo(c)
        r = c.post("/lida/lancar", json={"lida_id": lid, "data_inicio": "2026-08-01", "animais": ["700"]})
        assert r.status_code == 201, r.text
        with Session(engine) as s:
            aps = s.exec(
                select(LidaAplicacao).where(LidaAplicacao.lancamento_id == r.json()["lancamento_id"])
            ).all()
        dias = sorted(a.dia for a in aps)
        assert dias == [0, 1, 2, 3]  # D0 a D3, um por dia (dia_fim=3)
        assert all(a.foto_obrigatoria for a in aps)


class TestCentralDeProtocolos:
    def test_aparece_no_acompanhamento_sem_tipo_reprodutivo_ou_sanitario(self, client):
        c, engine = client
        lid = _criar_molde_frequencia(c)
        c.post("/lida/lancar", json={"lida_id": lid, "data_inicio": "2026-08-01", "data_fim": "2026-08-01"})
        linhas = c.get("/central-protocolos/acompanhamento").json()
        linha_lida = next(l for l in linhas if l["origem"] == "lida")
        assert linha_lida["tipo"] == "lida"
        assert linha_lida["status"] == "ativo"

    def test_baixa_da_estoque_de_verdade(self, client):
        c, engine = client
        lid = _criar_molde_frequencia(c, dar_baixa=True)
        r = c.post("/lida/lancar", json={
            "lida_id": lid, "data_inicio": "2026-08-01", "data_fim": "2026-08-01", "animais": ["700", "701"],
        })
        lancamento_id = r.json()["lancamento_id"]
        rb = c.post(f"/central-protocolos/lida/{lancamento_id}/baixa", json={"dia": 0})
        assert rb.status_code == 200, rb.text

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Detergente para cochos")).one()
            # 20 L iniciais - (0.5 L x 2 aplicações confirmadas) = 19 L.
            assert item.quantidade == 19
            aps = s.exec(select(LidaAplicacao).where(LidaAplicacao.lancamento_id == lancamento_id)).all()
            assert all(a.realizada for a in aps)

    def test_cancelar_estorna_estoque(self, client):
        c, engine = client
        lid = _criar_molde_frequencia(c, dar_baixa=True)
        r = c.post("/lida/lancar", json={
            "lida_id": lid, "data_inicio": "2026-08-01", "data_fim": "2026-08-01",
        })
        lancamento_id = r.json()["lancamento_id"]
        c.post(f"/central-protocolos/lida/{lancamento_id}/baixa", json={"dia": 0})
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Detergente para cochos")).one()
            assert item.quantidade == 19.5  # 20 - 0.5 x 1 aplicação

        rc = c.post(f"/central-protocolos/lida/{lancamento_id}/cancelar", json={"motivo": "teste"})
        assert rc.status_code == 200, rc.text
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Detergente para cochos")).one()
            assert item.quantidade == 20  # estornado
            lanc = s.get(LidaLancamento, lancamento_id)
            assert lanc.ativo is False


class TestListagemAtivos:
    def test_lida_ativos_lista_pendentes(self, client):
        c, engine = client
        lid = _criar_molde_frequencia(c)
        c.post("/lida/lancar", json={"lida_id": lid, "data_inicio": "2026-08-01", "data_fim": "2026-08-16"})
        ativos = c.get("/lida/ativos").json()
        assert len(ativos) == 1
        assert ativos[0]["pendentes"] == 2
        assert ativos[0]["proxima_etapa"] == "D0"
