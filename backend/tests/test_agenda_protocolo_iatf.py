"""
Testes do protocolo IATF na Agenda: eventos agrupados por (lançamento, dia)
em vez de um por animal, a janela de atraso das etapas vencidas (ver
TestJanelaDeAtraso), e marcar "realizado" (total ou parcial) resolve só as
aplicações certas.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ProtocoloIatfAplicacao


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


def _lancar(c, animais, data_d0="2026-07-08", protocolo="IATF 08/07 a 19/07"):
    return c.post("/reproducao/protocolo-iatf", json={"animais": animais, "data_d0": data_d0, "protocolo": protocolo}).json()


class TestEventoAgrupado:
    def test_evento_iatf_agrupa_animais_do_mesmo_dia(self, client):
        c, engine = client
        _lancar(c, ["700", "701", "702"])

        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e["id"].endswith("_0") and e.get("tipo") == "protocolo_iatf")
        assert set(d0["animais"]) == {"700", "701", "702"}
        assert d0["numero_animal"] is None

    def test_descricao_tem_nome_do_protocolo_e_dia(self, client):
        """O nome do lançamento é sempre gerado automaticamente (Central de
        Protocolos: nome cadastrado + data D0 + data do último dia), mas o
        CARTÃO da Agenda mostra só a parte cadastrada — o intervalo de datas
        seria redundante num cartão que já está numa data e já termina em
        "— D7" (ver rules/nomenclatura_protocolo.nome_curto)."""
        c, engine = client
        _lancar(c, ["700"], data_d0="2026-07-03")

        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d7 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 7)
        assert d7["descricao"] == "PROTOCOLO IATF — D7"

    def test_observacao_mostra_proxima_etapa(self, client):
        c, engine = client
        _lancar(c, ["700"])

        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert "D7" in d0["observacao"]
        d11 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 11)
        assert d11["observacao"] is None  # última etapa, não há próxima

    def test_hormonio_do_dia_exposto(self, client):
        c, engine = client
        _lancar(c, ["700"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert "progesterona" in d0["hormonio"].lower()


class TestAdicionarAnimaisExistente:
    def test_lista_lancamentos_e_adiciona_animais(self, client):
        c, engine = client
        _lancar(c, ["700", "701"], data_d0="2026-07-08", protocolo="IATF 08/07/26 A 19/07/26")

        lancs = c.get("/reproducao/protocolo-iatf/lancamentos").json()
        assert len(lancs) == 1
        lanc = lancs[0]
        assert lanc["qtd_animais"] == 2
        lid = lanc["lancamento_id"]

        # Esqueci de incluir 4 novilhas — adiciona ao mesmo protocolo.
        r = c.post(f"/reproducao/protocolo-iatf/{lid}/animais", json={"animais": ["800", "801", "700"]})
        assert r.status_code == 200
        # 700 já estava → só 800 e 801 entram.
        assert r.json()["adicionados"] == 2

        with Session(engine) as s:
            todos = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lid)).all()
            assert {a.numero_matriz for a in todos} == {"700", "701", "800", "801"}
            # Cada animal novo herdou os 4 passos com a MESMA data de D0.
            d0_800 = [a for a in todos if a.numero_matriz == "800" and a.dia == 0]
            assert len(d0_800) == 1 and d0_800[0].data_prevista.isoformat() == "2026-07-08"

    def test_adicionar_em_lancamento_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/reproducao/protocolo-iatf/999/animais", json={"animais": ["800"]})
        assert r.status_code == 404


class TestJanelaDeAtraso:
    """CONTRATO ALTERADO EM 08/2026.

    Antes, etapa com data já vencida sumia da Agenda na hora. A intenção era
    não poluir a lista com passos perdidos — mas como a Agenda era o único
    lugar do sistema capaz de gravar `realizada = True`, o efeito real era
    que um protocolo que perdesse o dia ficava travado em "em andamento"
    PARA SEMPRE, sem nenhuma tela capaz de fechá-lo (relato do usuário: três
    protocolos IATF parados em 18/36, 15/20 e 8/16).

    Agora a etapa vencida continua cobrando por até JANELA_ATRASO_DIAS (30),
    a mesma janela que o protocolo customizado já usava. Passada a janela ela
    some daqui — o que estes testes seguem garantindo —, mas a baixa continua
    possível pela Central de Protocolos, que é quem fecha o ciclo.
    """

    def test_etapa_vencida_dentro_da_janela_continua_cobrando(self, client):
        c, engine = client
        # D0 em 01/07 → D0/D7 vencidos em 09/07, D9/D11 ainda por vir. Todos
        # dentro da janela (limite = 09/07 - 30 = 09/06).
        _lancar(c, ["700"], data_d0="2026-07-01")

        eventos = c.get("/agenda/", params={"data": "2026-07-09", "dias": 30}).json()["eventos"]
        dias_presentes = sorted(e["dia"] for e in eventos if e.get("tipo") == "protocolo_iatf")
        assert dias_presentes == [0, 7, 9, 11], "etapa vencida sumiu — protocolo fica sem como fechar"

    def test_etapa_alem_da_janela_para_de_cobrar(self, client):
        c, engine = client
        # D0 em 01/05 → o último passo (D11, 12/05) está a quase 2 meses da
        # data consultada: fora da janela, não polui mais a Agenda.
        _lancar(c, ["700"], data_d0="2026-05-01")

        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        assert [e for e in eventos if e.get("tipo") == "protocolo_iatf"] == []

    def test_a_janela_corta_etapa_por_etapa(self, client):
        c, engine = client
        # D0 em 01/06, consulta em 08/07 → limite = 08/06. D0 (01/06) fica de
        # fora; D7 (08/06) cai exatamente no limite e entra, junto com D9/D11.
        _lancar(c, ["700"], data_d0="2026-06-01")

        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        dias_presentes = sorted(e["dia"] for e in eventos if e.get("tipo") == "protocolo_iatf")
        assert dias_presentes == [7, 9, 11]


class TestMarcarRealizadoIatf:
    def test_marcar_grupo_inteiro_some_da_agenda(self, client):
        c, engine = client
        _lancar(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        r = c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        assert r.status_code == 200

        with Session(engine) as s:
            aps = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.dia == 0)).all()
            assert all(a.realizada for a in aps)

        eventos2 = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        assert not any(e.get("tipo") == "protocolo_iatf" and e["dia"] == 0 for e in eventos2)

    def test_marcar_apenas_um_animal_mantem_o_resto_pendente(self, client):
        c, engine = client
        _lancar(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        c.post("/agenda/realizados", json={"evento_id": d0["id"], "animais": ["700"]})

        with Session(engine) as s:
            ap700 = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "700", ProtocoloIatfAplicacao.dia == 0)).first()
            ap701 = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "701", ProtocoloIatfAplicacao.dia == 0)).first()
            assert ap700.realizada is True
            assert ap701.realizada is False

        eventos2 = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0_depois = next(e for e in eventos2 if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert d0_depois["animais"] == ["701"]


class TestVariosLancamentosMesmoD0:
    """Animais incluídos um a um (chamadas separadas a POST
    /reproducao/protocolo-iatf, sem usar "em lote") criam um
    ProtocoloIatfLancamento próprio cada — mas com o mesmo D0, todos devem
    continuar aparecendo juntos num único card por (data prevista, dia).
    Reproduz o relato: 9 animais em D11, só 1 aparecendo na Agenda."""

    def test_animais_incluidos_um_a_um_aparecem_no_mesmo_card(self, client):
        c, engine = client
        numeros = [str(700 + i) for i in range(9)]
        for numero in numeros:
            _lancar(c, [numero])  # 9 lançamentos separados, mesmo D0 padrão

        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d11_eventos = [e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 11]
        assert len(d11_eventos) == 1, "os 9 animais têm que cair num card só, não em 9"
        assert set(d11_eventos[0]["animais"]) == set(numeros)

    def test_marcar_grupo_mesclado_confirma_aplicacoes_dos_dois_lancamentos(self, client):
        c, engine = client
        _lancar(c, ["700"])
        _lancar(c, ["701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert set(d0["animais"]) == {"700", "701"}

        r = c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        assert r.status_code == 200
        with Session(engine) as s:
            aps = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.dia == 0)).all()
            assert {a.numero_matriz for a in aps} == {"700", "701"}
            assert all(a.realizada for a in aps)

        eventos2 = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        assert not any(e.get("tipo") == "protocolo_iatf" and e["dia"] == 0 for e in eventos2)

    def test_desfazer_grupo_mesclado_reverte_os_dois_lancamentos(self, client):
        c, engine = client
        _lancar(c, ["700"])
        _lancar(c, ["701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": d0["id"]})

        r = c.delete(f"/agenda/realizados/{d0['id']}")
        assert r.status_code == 200
        with Session(engine) as s:
            aps = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.dia == 0)).all()
            assert all(not a.realizada and a.data_realizacao is None for a in aps)

        eventos_final = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0_final = next(e for e in eventos_final if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert set(d0_final["animais"]) == {"700", "701"}

    def test_marcar_apenas_um_animal_de_lancamentos_diferentes(self, client):
        c, engine = client
        _lancar(c, ["700"])
        _lancar(c, ["701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        c.post("/agenda/realizados", json={"evento_id": d0["id"], "animais": ["700"]})
        with Session(engine) as s:
            ap700 = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "700", ProtocoloIatfAplicacao.dia == 0)).first()
            ap701 = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "701", ProtocoloIatfAplicacao.dia == 0)).first()
            assert ap700.realizada is True
            assert ap701.realizada is False

        eventos2 = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0_depois = next(e for e in eventos2 if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert d0_depois["animais"] == ["701"]

    def test_concluidos_mostra_grupo_mesclado_como_um_so(self, client):
        c, engine = client
        _lancar(c, ["700"])
        _lancar(c, ["701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": d0["id"]})

        concluidos = c.get("/agenda/protocolo-iatf/concluidos").json()
        assert len(concluidos) == 1
        assert set(concluidos[0]["animais"]) == {"700", "701"}


class TestDesfazerIatf:
    def test_desfazer_grupo_volta_a_aparecer_na_agenda(self, client):
        c, engine = client
        _lancar(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        eventos_depois = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        assert not any(e.get("tipo") == "protocolo_iatf" and e["dia"] == 0 for e in eventos_depois)

        r = c.delete(f"/agenda/realizados/{d0['id']}")
        assert r.status_code == 200

        with Session(engine) as s:
            aps = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.dia == 0)).all()
            assert all(not a.realizada and a.data_realizacao is None for a in aps)

        eventos_final = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0_final = next(e for e in eventos_final if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert set(d0_final["animais"]) == {"700", "701"}

    def test_listar_concluidos_e_desfazer_um_deles(self, client):
        c, engine = client
        _lancar(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": d0["id"]})

        concluidos = c.get("/agenda/protocolo-iatf/concluidos").json()
        assert len(concluidos) == 1
        assert concluidos[0]["id"] == d0["id"]
        assert set(concluidos[0]["animais"]) == {"700", "701"}
        assert concluidos[0]["dia"] == 0

        c.delete(f"/agenda/realizados/{d0['id']}")
        assert c.get("/agenda/protocolo-iatf/concluidos").json() == []

    def test_desfazer_parcial_mantem_apenas_animal_ainda_confirmado(self, client):
        c, engine = client
        _lancar(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        # Confirma só 700 primeiro, depois 701 — ambos ficam realizada=True.
        c.post("/agenda/realizados", json={"evento_id": d0["id"], "animais": ["700"]})
        c.post("/agenda/realizados", json={"evento_id": d0["id"], "animais": ["701"]})

        # Desfazer reverte o grupo inteiro (não há registro de "o que foi confirmado agora").
        c.delete(f"/agenda/realizados/{d0['id']}")
        with Session(engine) as s:
            aps = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.dia == 0)).all()
            assert all(not a.realizada for a in aps)
