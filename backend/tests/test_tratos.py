"""
Tratos por dia cadastrados na dieta + ciclo de 24h da sobra de cocho
(decisões do dono de 2026-10-21 — ver fazenda/rules/tratos.py).

Cobre: % por trato na apresentação, validação (1 a 4 tratos, soma 100%),
dieta antiga = 2×50%, herança dos tratos na dieta nova sem cadastro, janela
da sobra pela posição da leitura (consumo por trato e por dia/rateio), o
resumo pré-montado do período (GET /sobra/janela), "selecionar outro
período", relançar substitui e o parâmetro "lançar consumo por trato".
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ConsumoAlimento, ConsumoSobra, ContratoFazenda, ContratoFazendaModulo, DietaItemProgramado,
    DietaLancamento, Estoque, Fazenda, Lote,
)
from fazenda.rules import tratos as regras

HOJE = date(2026, 10, 21)
ONTEM = HOJE - timedelta(days=1)


# ---------------------------------------------------------------------------
# Regras puras
# ---------------------------------------------------------------------------
class TestRegrasPuras:
    def test_dieta_sem_cadastro_vale_dois_tratos_50_50(self):
        assert regras.ler_tratos(None) == [50.0, 50.0]
        assert regras.ler_tratos("lixo") == [50.0, 50.0]

    @pytest.mark.parametrize("pcts", [[], [20, 20, 20, 20, 20], [60, 30], [100, 0], [-10, 110]])
    def test_validacao_recusa(self, pcts):
        with pytest.raises(regras.TratosInvalidos):
            regras.validar_tratos(pcts)

    def test_validacao_aceita_arredondamento_de_tres_tratos(self):
        assert regras.validar_tratos([33.33, 33.33, 33.34]) == [33.33, 33.33, 33.34]
        assert regras.validar_tratos([100]) == [100.0]

    def test_posicao_com_um_trato_e_sempre_1_e_fora_da_faixa_recusa(self):
        assert regras.validar_posicao(1, None) == 1
        assert regras.validar_posicao(3, None) is None
        with pytest.raises(regras.TratosInvalidos):
            regras.validar_posicao(2, 3)

    def test_janela_exemplo_do_dono_3_tratos_leitura_entre_t1_e_t2(self):
        fech = regras.data_fechamento(HOJE, 3, 1)
        assert fech == HOJE
        itens = regras.janela(fech, 3, 1)
        assert itens == [(ONTEM, 2), (ONTEM, 3), (HOJE, 1)]
        assert regras.descrever_janela(itens) == "A sobra se refere aos tratos 2 e 3 do dia 20/10 e ao trato 1 do dia 21/10?"

    def test_leitura_entre_ultimo_e_primeiro_fecha_o_dia_anterior(self):
        fech = regras.data_fechamento(HOJE, 2, 2)
        assert fech == ONTEM
        assert regras.janela(fech, 2, 2) == [(ONTEM, 1), (ONTEM, 2)]
        assert regras.data_leitura(fech, 2, 2) == HOJE

    def test_um_trato_janela_e_o_trato_do_dia_anterior(self):
        fech = regras.data_fechamento(HOJE, 1, 1)
        assert regras.janela(fech, 1, 1) == [(ONTEM, 1)]
        assert regras.descrever_janela(regras.janela(fech, 1, 1)) == "A sobra se refere ao trato 1 do dia 20/10?"

    def test_sem_posicao_e_o_dia_civil_de_sempre(self):
        assert regras.data_fechamento(HOJE, 2, None) == HOJE
        assert regras.janela(HOJE, 2, None) == [(HOJE, 1), (HOJE, 2)]

    def test_rateio_por_dia_exemplo_do_dono(self):
        # ontem 1000 kg (sem trato), hoje 900 kg (sem trato); tratos 40/30/30,
        # janela T2+T3 de ontem + T1 de hoje → 600 + 360.
        consumos = [(ONTEM, None, "Silagem", 1000.0), (HOJE, None, "Silagem", 900.0)]
        itens = regras.janela(HOJE, 3, 1)
        assert regras.fornecido_na_janela(consumos, itens, [40, 30, 30]) == {"Silagem": pytest.approx(960.0)}

    def test_consumo_por_trato_soma_so_os_tratos_da_janela(self):
        consumos = [(ONTEM, 1, "S", 400.0), (ONTEM, 2, "S", 300.0), (ONTEM, 3, "S", 300.0), (HOJE, 1, "S", 410.0), (HOJE, 2, "S", 290.0)]
        itens = regras.janela(HOJE, 3, 1)
        assert regras.fornecido_na_janela(consumos, itens, [40, 30, 30]) == {"S": pytest.approx(1010.0)}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(ContratoFazendaModulo(fazenda_id=1, modulo="alimentacao", ativo=True))
        s.add(Lote(codigo="01", fazenda_id=1, nome="Alta", permitir_sem_estoque=True))
        for n in ("A", "B"):
            s.add(Animal(numero=f"1-{n}", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True, fazenda_id=1))
        s.add(Estoque(nome="Silagem", fazenda_id=1, quantidade=100000.0, unidade="kg"))
        s.commit()

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
        email = "teste@example.com"
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _payload_dieta(**extra):
    return {
        "lote": 1, "data_abertura": "2026-10-01", "base_quantidade": "total",
        "itens": [{"alimento": "Silagem", "quantidade": 1000.0, "unidade": "kg"}], **extra,
    }


def _dieta_antiga(engine) -> int:
    """Dieta lançada antes do cadastro de tratos (tratos_pct NULL)."""
    with Session(engine) as s:
        d = DietaLancamento(lote=1, fazenda_id=1, data_abertura=date(2026, 10, 1), base_quantidade="total")
        s.add(d)
        s.commit()
        s.refresh(d)
        s.add(DietaItemProgramado(fazenda_id=1, dieta_lancamento_id=d.id, alimento="Silagem", quantidade=1000.0, unidade="kg"))
        s.commit()
        return d.id


def _consumo(engine, dia: date, kg: float, trato: int | None = None):
    with Session(engine) as s:
        s.add(ConsumoAlimento(fazenda_id=1, data=dia, lote=1, alimento="Silagem", quantidade=kg, unidade="kg", trato=trato))
        s.commit()


class TestCadastroDosTratos:
    def test_dieta_com_tratos_mostra_kg_por_trato_na_apresentacao(self, client):
        c, _ = client
        r = c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=1))
        assert r.status_code == 201, r.text
        assert r.json()["tratos_pct"] == [40.0, 30.0, 30.0] and r.json()["sobra_posicao_leitura"] == 1
        ap = c.get(f"/alimentacao/dietas/{r.json()['id']}/apresentacao").json()
        assert ap["num_tratos"] == 3 and ap["tratos_configurados"] is True
        assert ap["itens"][0]["por_trato"] == [400.0, 300.0, 300.0]
        assert ap["itens"][0]["total_trato"] is None  # tratos desiguais: não há um número único
        assert ap["vagao_kg_trato"] is None
        assert ap["tratos"] == [
            {"trato": 1, "pct": 40.0, "vagao_kg": 400.0}, {"trato": 2, "pct": 30.0, "vagao_kg": 300.0},
            {"trato": 3, "pct": 30.0, "vagao_kg": 300.0},
        ]

    @pytest.mark.parametrize("tratos", [[60, 30], [20, 20, 20, 20, 20], [], [100, 0]])
    def test_validacao_soma_100_e_1_a_4(self, client, tratos):
        c, engine = client
        r = c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=tratos))
        assert r.status_code == 400, r.text
        with Session(engine) as s:
            assert s.exec(select(DietaLancamento)).all() == []

    def test_posicao_invalida_recusa(self, client):
        c, _ = client
        r = c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[50, 50], sobra_posicao_leitura=3))
        assert r.status_code == 400

    def test_dieta_antiga_vale_dois_tratos_50_50(self, client):
        c, engine = client
        dieta_id = _dieta_antiga(engine)
        ap = c.get(f"/alimentacao/dietas/{dieta_id}/apresentacao").json()
        assert ap["num_tratos"] == 2 and ap["tratos_configurados"] is False and ap["sobra_posicao_leitura"] is None
        assert ap["itens"][0]["total_trato"] == 500.0 and ap["itens"][0]["por_trato"] == [500.0, 500.0]
        assert ap["vagao_kg_trato"] == 500.0
        lista = c.get("/alimentacao/dietas").json()
        assert lista[0]["tratos_pct"] == [50.0, 50.0] and lista[0]["num_tratos"] == 2

    def test_dieta_nova_sem_tratos_herda_da_anterior(self, client):
        c, _ = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=2))
        r = c.post("/alimentacao/dietas", json=_payload_dieta(data_abertura="2026-10-15", encerrar_anterior=True))
        assert r.status_code == 201, r.text
        assert r.json()["tratos_pct"] == [40.0, 30.0, 30.0] and r.json()["sobra_posicao_leitura"] == 2

    def test_um_trato_posicao_e_sempre_1(self, client):
        c, _ = client
        r = c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[100], sobra_posicao_leitura=None))
        assert r.json()["sobra_posicao_leitura"] == 1

    def test_dieta_do_lote_traz_tratos_e_parametro(self, client):
        c, _ = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=1))
        d = c.get("/alimentacao/consumo/dieta-do-lote?lote=1").json()
        assert d["tratos_pct"] == [40.0, 30.0, 30.0] and d["num_tratos"] == 3
        assert d["sobra_posicao_leitura"] == 1 and d["consumo_por_trato"] is False

    def test_plano_por_lote_traz_tratos(self, client):
        c, _ = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[60, 40], sobra_posicao_leitura=2))
        plano = c.get("/alimentacao/").json()
        assert [l["tratos_pct"] for l in plano["por_lote"] if l["lote"] == 1] == [[60.0, 40.0]]


class TestConsumoPorTrato:
    def test_parametro_ligado_exige_trato(self, client, monkeypatch):
        import fazenda.api.routers.alimentacao as alim
        monkeypatch.setattr(alim, "get_param_bool", lambda chave, padrao=False: chave == alim.CHAVE_CONSUMO_POR_TRATO or padrao)
        c, engine = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=1))
        corpo = {"lote": 1, "data": HOJE.isoformat(), "origem": "kg", "itens": [{"alimento": "Silagem", "quantidade": 400, "unidade": "kg"}]}
        assert c.post("/alimentacao/consumo", json=corpo).status_code == 400
        assert c.post("/alimentacao/consumo", json={**corpo, "trato": 4}).status_code == 400
        r = c.post("/alimentacao/consumo", json={**corpo, "trato": 2})
        assert r.status_code == 201, r.text
        with Session(engine) as s:
            assert [x.trato for x in s.exec(select(ConsumoAlimento)).all()] == [2]
        dia = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        assert dia["por_trato"] == [{"trato": 2, "kg": 400.0}] and dia["kg_sem_trato"] == 0.0

    def test_parametro_desligado_lanca_o_dia_como_sempre(self, client):
        c, engine = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=1))
        corpo = {"lote": 1, "data": HOJE.isoformat(), "origem": "kg", "itens": [{"alimento": "Silagem", "quantidade": 400, "unidade": "kg"}]}
        assert c.post("/alimentacao/consumo", json=corpo).status_code == 201
        with Session(engine) as s:
            assert [x.trato for x in s.exec(select(ConsumoAlimento)).all()] == [None]


class TestSobraPorCiclo:
    def test_janela_resumo_premontado_e_base_rateada_por_dia(self, client):
        c, engine = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=1))
        _consumo(engine, ONTEM, 1000.0)
        _consumo(engine, HOJE, 900.0)
        j = c.get(f"/alimentacao/sobra/janela?lote=1&data={HOJE.isoformat()}").json()
        assert j["descricao"] == "A sobra se refere aos tratos 2 e 3 do dia 20/10 e ao trato 1 do dia 21/10?"
        assert j["janela"] == [{"data": "2026-10-20", "trato": 2}, {"data": "2026-10-20", "trato": 3}, {"data": "2026-10-21", "trato": 1}]
        assert j["kg_fornecido_janela"] == 960.0 and j["kg_sobra_existente"] is None
        r = c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 48.0})
        assert r.status_code == 201, r.text
        assert r.json()["sobra_pct"] == 5.0 and r.json()["substituiu"] is False
        dia = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        assert dia["sobra_kg"] == 48.0 and dia["sobra_pct"] == 5.0 and dia["kg_fornecido_total"] == 900.0
        assert dia["sobra_janela"]["kg_fornecido"] == 960.0 and dia["sobra_janela"]["data_leitura"] == HOJE.isoformat()

    def test_base_por_trato_quando_lancado_por_trato(self, client):
        c, engine = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=1))
        for dia, trato, kg in [(ONTEM, 1, 400), (ONTEM, 2, 300), (ONTEM, 3, 320), (HOJE, 1, 380), (HOJE, 2, 999)]:
            _consumo(engine, dia, kg, trato)
        r = c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 50.0}).json()
        assert r["kg_fornecido_janela"] == 1000.0 and r["sobra_pct"] == 5.0

    def test_leitura_antes_do_primeiro_trato_fecha_o_ciclo_de_ontem(self, client):
        c, engine = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[50, 50], sobra_posicao_leitura=2))
        _consumo(engine, ONTEM, 1000.0)
        _consumo(engine, HOJE, 400.0)
        r = c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 50.0}).json()
        assert r["descricao"] == "A sobra se refere aos tratos 1 e 2 do dia 20/10?"
        assert r["data_fechamento"] == ONTEM.isoformat() and r["sobra_pct"] == 5.0
        with Session(engine) as s:
            reg = s.exec(select(ConsumoSobra)).one()
            assert (reg.data, reg.data_leitura, reg.posicao_leitura, reg.tratos_pct) == (ONTEM, HOJE, 2, "[50.0, 50.0]")

    def test_selecionar_outro_periodo(self, client):
        c, engine = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=1))
        j = c.get(f"/alimentacao/sobra/janela?lote=1&data={HOJE.isoformat()}&posicao_leitura=2").json()
        assert j["descricao"] == "A sobra se refere ao trato 3 do dia 20/10 e aos tratos 1 e 2 do dia 21/10?"
        assert j["posicao_leitura"] == 2 and j["posicao_da_dieta"] == 1
        assert c.get(f"/alimentacao/sobra/janela?lote=1&data={HOJE.isoformat()}&posicao_leitura=9").status_code == 400
        r = c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 10.0, "posicao_leitura": 2}).json()
        assert r["posicao_leitura"] == 2
        civil = c.get(f"/alimentacao/sobra/janela?lote=1&data={HOJE.isoformat()}&dia_civil=true").json()
        assert civil["descricao"] == "A sobra se refere aos tratos 1, 2 e 3 do dia 21/10?"

    def test_relancar_o_mesmo_ciclo_substitui(self, client):
        c, engine = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[50, 50], sobra_posicao_leitura=2))
        _consumo(engine, ONTEM, 1000.0)
        assert c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 30.0}).json()["substituiu"] is False
        j = c.get(f"/alimentacao/sobra/janela?lote=1&data={HOJE.isoformat()}").json()
        assert j["kg_sobra_existente"] == 30.0
        assert c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 70.0}).json()["substituiu"] is True
        # O mesmo ciclo lançado do jeito antigo (dia civil de ontem) também substitui — não duplica.
        assert c.post("/alimentacao/sobra", json={"lote": 1, "data": ONTEM.isoformat(), "kg_sobra": 60.0, "dia_civil": True}).json()["substituiu"] is True
        with Session(engine) as s:
            regs = s.exec(select(ConsumoSobra)).all()
            assert [(r.data, r.kg_sobra) for r in regs] == [(ONTEM, 60.0)]

    def test_dieta_antiga_mantem_o_comportamento_de_sempre(self, client):
        c, engine = client
        _dieta_antiga(engine)
        _consumo(engine, ONTEM, 999.0)
        _consumo(engine, HOJE, 40.0)
        r = c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 2.0}).json()
        assert r["descricao"] == "A sobra se refere aos tratos 1 e 2 do dia 21/10?"
        assert r["sobra_pct"] == 5.0  # 2 / 40 — fornecido do próprio dia, como antes
        with Session(engine) as s:
            reg = s.exec(select(ConsumoSobra)).one()
            assert (reg.data, reg.data_leitura, reg.posicao_leitura, reg.tratos_pct) == (HOJE, None, None, None)

    def test_registro_antigo_gravado_direto_continua_lido_pelo_dia(self, client):
        c, engine = client
        c.post("/alimentacao/dietas", json=_payload_dieta(tratos_pct=[40, 30, 30], sobra_posicao_leitura=1))
        _consumo(engine, ONTEM, 999.0)
        _consumo(engine, HOJE, 40.0)
        with Session(engine) as s:
            s.add(ConsumoSobra(fazenda_id=1, data=HOJE, lote=1, kg_sobra=2.0))
            s.commit()
        dia = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        assert dia["sobra_pct"] == 5.0
