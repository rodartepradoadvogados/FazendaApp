"""
Testes do calendário de dias trabalhados/folga da diária — `DiariaDia`
(modelo esparso: só existe linha para o dia que FOGE do padrão trabalhado) e
o marco `Diaria.controle_por_dia_desde` que decide se `_resumo_diaria` usa a
regra legada (contagem cega + auditorias agregadas + ajuste manual) ou o
calendário por dia.

`GET/PUT /cadastro/diarias/{id}/dias` — ver rh_contratos.py.

Os 5 testes de `TestDiaria` em test_cadastro.py continuam passando sem
nenhuma alteração — são a garantia de que uma diária que nunca tocou o
calendário se comporta exatamente como antes.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Diaria, DiariaAuditoria, DiariaDia, DiariaPagamento


class _FakeUser:
    id = 1
    papel = "admin"
    ativo = True
    username = "teste"


@pytest.fixture
def client():
    """Mesmo padrão de TestDiaria em test_cadastro.py — sem fazenda_id
    resolvida (token legado), usado pelos testes que não são de isolamento
    multi-tenant."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


@pytest.fixture
def client_multi():
    """Duas fazendas com ContratoFazenda ativo (exigido pelo middleware de
    contrato comercial quando get_fazenda_atual_id devolve um int real) —
    mesmo padrão de test_central_protocolos_fazenda.py. `make_client(id)`
    troca a fazenda "atual" a cada chamada."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(ContratoFazenda(fazenda_id=2, status="ativo"))
        # /cadastro/diarias exige o módulo comercial "financeiro" contratado
        # (RH passou a exigi-lo — ver cadastro/__init__.py).
        s.add(ContratoFazendaModulo(fazenda_id=1, modulo="financeiro", ativo=True))
        s.add(ContratoFazendaModulo(fazenda_id=2, modulo="financeiro", ativo=True))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    def _make_client(fazenda_id: int) -> TestClient:
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
        return TestClient(main.app)

    yield engine, _make_client

    main.app.dependency_overrides.clear()


def _diarista(c) -> int:
    return c.post("/cadastro/pessoas", json={"nome": "Maria Diarista", "tipos": ["Diarista"]}).json()["id"]


def _criar_diaria(c, pessoa_id: int, dias_atras: int, valor: float = 100.0, data_fim: date | None = None) -> int:
    inicio = date.today() - timedelta(days=dias_atras)
    payload = {"pessoa_id": pessoa_id, "valor_diaria": valor, "data_inicio": inicio.isoformat()}
    if data_fim:
        payload["data_fim"] = data_fim.isoformat()
    r = c.post("/cadastro/diarias", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# 1-2: diária nunca tocada pelo calendário — regressão do caminho legado.
# ---------------------------------------------------------------------------
class TestDiariaNuncaTocada:
    def test_resumo_conta_todo_dia_como_antes(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        diaria_id = _criar_diaria(c, pessoa_id, 4)  # hoje + 4 dias atrás = 5 diárias
        dados = next(d for d in c.get("/cadastro/diarias").json() if d["id"] == diaria_id)
        assert dados["controle_por_dia_desde"] is None
        assert dados["numero_diarias"] == 5
        assert dados["total_ate_hoje"] == 500.0
        assert dados["dias_folga"] == 0
        assert dados["ultima_folga"] is None
        assert dados["pago_ate"] is None

    def test_get_dias_devolve_tudo_trabalhado_e_nunca_auditado(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        r = c.get(f"/cadastro/diarias/{diaria_id}/dias")
        assert r.status_code == 200
        dados = r.json()
        assert dados["nunca_auditado"] is True
        assert dados["controle_por_dia_desde"] is None
        assert len(dados["dias"]) == 5
        assert all(d["trabalhado"] for d in dados["dias"])
        assert all(not d["pago"] for d in dados["dias"])
        assert dados["resumo_periodo"]["dias_trabalhados"] == 5
        assert dados["resumo_periodo"]["dias_folga"] == 0


# ---------------------------------------------------------------------------
# 3-9: PUT/GET do calendário — marcar folga, reverter, validações, modos.
# ---------------------------------------------------------------------------
class TestCalendarioDiaria:
    def test_marcar_folga_reduz_contagem_e_seta_marco(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)  # 5 dias corridos
        folga = date.today() - timedelta(days=2)
        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [folga.isoformat()],
        })
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["numero_diarias"] == 4
        assert dados["total_ate_hoje"] == 400.0
        assert dados["dias_folga"] == 1
        assert dados["controle_por_dia_desde"] == inicio.isoformat()
        assert dados["ultima_folga"] == folga.isoformat()

    def test_resubmeter_vazio_reverte_folga_replace_nao_merge(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        folga = date.today() - timedelta(days=2)
        c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [folga.isoformat()],
        })
        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [],
        })
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["numero_diarias"] == 5
        assert dados["dias_folga"] == 0
        assert dados["ultima_folga"] is None
        with Session(engine) as s:
            assert s.exec(select(DiariaDia).where(DiariaDia.diaria_id == diaria_id)).all() == []

    def test_rejeita_data_fora_do_periodo(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        fora = date.today() - timedelta(days=10)
        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [fora.isoformat()],
        })
        assert r.status_code == 400

    def test_rejeita_periodo_fim_no_futuro(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        futuro = date.today() + timedelta(days=1)
        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": futuro.isoformat(),
            "dias_nao_trabalhados": [],
        })
        assert r.status_code == 400

    def test_modo_ultimo_periodo_comeca_dia_apos_ultima_folga(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=9)
        diaria_id = _criar_diaria(c, pessoa_id, 9)
        folga = date.today() - timedelta(days=5)
        c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [folga.isoformat()],
        })
        r = c.get(f"/cadastro/diarias/{diaria_id}/dias", params={"modo": "ultimo_periodo"})
        assert r.status_code == 200
        dados = r.json()
        assert dados["modo"] == "ultimo_periodo"
        assert dados["periodo_inicio"] == (folga + timedelta(days=1)).isoformat()
        assert dados["periodo_fim"] == date.today().isoformat()

    def test_modo_ultimo_periodo_ignora_folga_marcada_hoje(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        hoje = date.today()
        c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": hoje.isoformat(),
            "dias_nao_trabalhados": [hoje.isoformat()],
        })
        r = c.get(f"/cadastro/diarias/{diaria_id}/dias", params={"modo": "ultimo_periodo"})
        dados = r.json()
        # a janela nunca colapsa a vazio: nenhuma folga ANTES de hoje, então o
        # início continua sendo data_inicio, não hoje+1.
        assert dados["periodo_inicio"] == inicio.isoformat()
        assert dados["periodo_fim"] == hoje.isoformat()
        assert len(dados["dias"]) >= 1

    def test_modo_ultimo_periodo_sem_folga_cai_para_data_inicio(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        r = c.get(f"/cadastro/diarias/{diaria_id}/dias", params={"modo": "ultimo_periodo"})
        dados = r.json()
        assert dados["periodo_inicio"] == inicio.isoformat()
        assert dados["ultima_folga"] is None

    def test_modo_completo_com_desde_ate_alcanca_mais_longe(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=9)
        diaria_id = _criar_diaria(c, pessoa_id, 9)
        folga = date.today() - timedelta(days=1)
        c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [folga.isoformat()],
        })
        # modo=ultimo_periodo pararia em folga+1; modo=completo com desde/ate
        # explícitos alcança de volta até data_inicio.
        r = c.get(f"/cadastro/diarias/{diaria_id}/dias", params={
            "modo": "completo", "desde": inicio.isoformat(), "ate": date.today().isoformat(),
        })
        assert r.status_code == 200
        dados = r.json()
        assert dados["modo"] == "completo"
        assert dados["periodo_inicio"] == inicio.isoformat()
        assert len(dados["dias"]) == 10


# ---------------------------------------------------------------------------
# Meia diária — dias_meia_diaria conta metade do valor de uma diária cheia.
# ---------------------------------------------------------------------------
class TestMeiaDiaria:
    def test_marcar_meia_diaria_conta_metade_do_valor(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4, valor=100.0)  # 5 dias corridos
        meia = date.today() - timedelta(days=2)
        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_meia_diaria": [meia.isoformat()],
        })
        assert r.status_code == 200, r.text
        dados = r.json()
        # 4 dias cheios + 1 meia diária = 4.5 diárias -> 450,00
        assert dados["numero_diarias"] == 4.5
        assert dados["total_ate_hoje"] == 450.0
        assert dados["dias_folga"] == 0
        assert dados["dias_meia_diaria"] == 1

    def test_get_dias_marca_meia_diaria_e_soma_valor_periodo(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4, valor=100.0)
        meia = date.today() - timedelta(days=2)
        c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_meia_diaria": [meia.isoformat()],
        })
        r = c.get(f"/cadastro/diarias/{diaria_id}/dias")
        dados = r.json()
        dia_meia = next(d for d in dados["dias"] if d["data"] == meia.isoformat())
        assert dia_meia["meia_diaria"] is True
        assert dia_meia["trabalhado"] is False
        assert dados["resumo_periodo"]["dias_meia_diaria"] == 1
        assert dados["resumo_periodo"]["dias_trabalhados"] == 4
        assert dados["resumo_periodo"]["valor_periodo"] == 450.0

    def test_mesma_data_em_folga_e_meia_diaria_da_400(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        dia = date.today() - timedelta(days=2)
        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [dia.isoformat()], "dias_meia_diaria": [dia.isoformat()],
        })
        assert r.status_code == 400

    def test_combina_folga_e_meia_diaria_no_mesmo_periodo(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4, valor=100.0)  # 5 dias corridos
        folga = date.today() - timedelta(days=3)
        meia = date.today() - timedelta(days=1)
        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [folga.isoformat()], "dias_meia_diaria": [meia.isoformat()],
        })
        assert r.status_code == 200, r.text
        dados = r.json()
        # 3 dias cheios + 1 folga + 1 meia diária = 3.5 diárias -> 350,00
        assert dados["numero_diarias"] == 3.5
        assert dados["total_ate_hoje"] == 350.0
        assert dados["dias_folga"] == 1
        assert dados["dias_meia_diaria"] == 1


# ---------------------------------------------------------------------------
# 10-11: convivência com auditoria legada já respondida.
# ---------------------------------------------------------------------------
class TestConviveComAuditoriaLegada:
    def test_soma_legado_mais_calendario_sem_sobreposicao_nem_buraco(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=13)  # 14 dias corridos até hoje
        diaria_id = _criar_diaria(c, pessoa_id, 13)

        # Auditoria legada RESPONDIDA cobrindo os primeiros 7 dias, com 1 dia
        # de falta (6 de 7 confirmados).
        periodo_fim_legado = inicio + timedelta(days=6)
        with Session(engine) as s:
            s.add(DiariaAuditoria(
                diaria_id=diaria_id, periodo_inicio=inicio, periodo_fim=periodo_fim_legado,
                dias_trabalhados=6, confirmado_em=datetime.utcnow(),
            ))
            s.commit()

        # Calendário assume a partir do dia seguinte ao período legado, com
        # mais 1 folga dentro da janela.
        corte = periodo_fim_legado + timedelta(days=1)
        folga_calendario = date.today() - timedelta(days=3)
        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": corte.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [folga_calendario.isoformat()],
        })
        assert r.status_code == 200, r.text
        dados = r.json()

        dias_totais_corridos = (date.today() - inicio).days + 1  # 14
        dias_perdidos_na_auditoria = 7 - 6  # período de 7 dias, 6 confirmados
        dias_folga_calendario = 1
        esperado = dias_totais_corridos - dias_perdidos_na_auditoria - dias_folga_calendario
        assert dados["numero_diarias"] == esperado
        assert dados["total_ate_hoje"] == round(esperado * 100.0, 2)
        assert dados["controle_por_dia_desde"] == corte.isoformat()

    def test_put_apaga_pendentes_superadas_mas_mantem_respondidas(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=9)
        diaria_id = _criar_diaria(c, pessoa_id, 9)

        with Session(engine) as s:
            respondida = DiariaAuditoria(
                diaria_id=diaria_id, periodo_inicio=inicio, periodo_fim=inicio + timedelta(days=2),
                dias_trabalhados=3, confirmado_em=datetime.utcnow(),
            )
            pendente_superada = DiariaAuditoria(
                diaria_id=diaria_id, periodo_inicio=inicio + timedelta(days=3), periodo_fim=inicio + timedelta(days=5),
            )
            s.add(respondida)
            s.add(pendente_superada)
            s.commit()
            s.refresh(respondida)
            s.refresh(pendente_superada)
            respondida_id, pendente_id = respondida.id, pendente_superada.id

        r = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": (inicio + timedelta(days=3)).isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [],
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            assert s.get(DiariaAuditoria, respondida_id) is not None
            assert s.get(DiariaAuditoria, pendente_id) is None


# ---------------------------------------------------------------------------
# 12: conflito com pagamento já registrado.
# ---------------------------------------------------------------------------
class TestConflitoComPagamento:
    def test_periodo_ja_pago_exige_confirmacao_explicita(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        r = c.post(f"/cadastro/diarias/{diaria_id}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 500.0,
        })
        assert r.status_code == 200, r.text

        r_sem_confirmar = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [],
        })
        assert r_sem_confirmar.status_code == 409
        assert "pagamento" in r_sem_confirmar.json()["detail"].lower()

        r_confirmando = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [], "confirmar_periodo_pago": True,
        })
        assert r_confirmando.status_code == 200, r_confirmando.text


# ---------------------------------------------------------------------------
# 13: data_fim no passado limita o range válido do calendário.
# ---------------------------------------------------------------------------
class TestDataFimLimitaCalendario:
    def test_data_fim_no_passado_clampa_periodo_fim(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=9)
        fim = date.today() - timedelta(days=5)
        diaria_id = _criar_diaria(c, pessoa_id, 9, data_fim=fim)

        r = c.get(f"/cadastro/diarias/{diaria_id}/dias", params={"modo": "ultimo_periodo"})
        dados = r.json()
        assert dados["periodo_fim"] == fim.isoformat()
        assert dados["hoje"] == date.today().isoformat()

        r2 = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [],
        })
        assert r2.status_code == 400

        r3 = c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": fim.isoformat(),
            "dias_nao_trabalhados": [],
        })
        assert r3.status_code == 200, r3.text


# ---------------------------------------------------------------------------
# 14-15: isolamento multi-tenant.
# ---------------------------------------------------------------------------
class TestMultiTenant:
    def test_fazenda_b_leva_404_na_diaria_da_fazenda_a(self, client_multi):
        engine, make_client = client_multi
        c1 = make_client(1)
        pessoa_id = c1.post("/cadastro/pessoas", json={"nome": "Diarista A", "tipos": ["Diarista"]}).json()["id"]
        inicio = date.today() - timedelta(days=4)
        diaria_id = c1.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": inicio.isoformat(),
        }).json()["id"]

        c2 = make_client(2)
        assert c2.get(f"/cadastro/diarias/{diaria_id}/dias").status_code == 404
        r_put = c2.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [],
        })
        assert r_put.status_code == 404

    def test_dias_criados_carregam_fazenda_id_do_usuario(self, client_multi):
        engine, make_client = client_multi
        c1 = make_client(1)
        pessoa_id = c1.post("/cadastro/pessoas", json={"nome": "Diarista B", "tipos": ["Diarista"]}).json()["id"]
        inicio = date.today() - timedelta(days=4)
        diaria_id = c1.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": inicio.isoformat(),
        }).json()["id"]
        folga = date.today() - timedelta(days=1)
        r = c1.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [folga.isoformat()],
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            rows = s.exec(select(DiariaDia).where(DiariaDia.diaria_id == diaria_id)).all()
            assert len(rows) == 1
            assert rows[0].fazenda_id == 1


# ---------------------------------------------------------------------------
# 16: cascata de exclusão — deletar a Diaria também apaga seus DiariaDia.
# ---------------------------------------------------------------------------
class TestExclusaoCascata:
    def test_excluir_diaria_remove_dias_do_calendario_sem_orfaos(self, client):
        c, engine = client
        pessoa_id = _diarista(c)
        inicio = date.today() - timedelta(days=4)
        diaria_id = _criar_diaria(c, pessoa_id, 4)
        folga = date.today() - timedelta(days=1)
        c.put(f"/cadastro/diarias/{diaria_id}/dias", json={
            "periodo_inicio": inicio.isoformat(), "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [folga.isoformat()],
        })
        with Session(engine) as s:
            assert len(s.exec(select(DiariaDia).where(DiariaDia.diaria_id == diaria_id)).all()) == 1

        r = c.post("/exclusoes/confirmar", json={"tipo": "diaria", "id": str(diaria_id)})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            assert s.get(Diaria, diaria_id) is None
            assert s.exec(select(DiariaDia).where(DiariaDia.diaria_id == diaria_id)).all() == []
