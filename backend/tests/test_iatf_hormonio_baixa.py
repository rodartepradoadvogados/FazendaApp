"""
Protocolo IATF estruturado por medicamento: ao lançar com hormônios por dia
(ex.: D0 = 1ml SincroCP + 2ml Estron), a descrição de cada dia passa a listar
os produtos, e ao confirmar o dia na Agenda o estoque é baixado (dose × nº de
vacas confirmadas) e uma aplicação de Sanidade é registrada por vaca.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, MovimentoEstoque, ProtocoloIatfHormonio, Sanidade


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Estoque(nome="SincroCP", quantidade=100, unidade="ml"))
        s.add(Estoque(nome="Estron", quantidade=100, unidade="ml"))
        s.commit()

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


def _lancar_com_hormonios(c, animais, data_d0="2026-07-08"):
    return c.post("/reproducao/protocolo-iatf", json={
        "animais": animais, "data_d0": data_d0, "protocolo": "IATF teste",
        "hormonios": [
            {"dia": 0, "produto": "SincroCP", "dose": 1, "unidade": "ml", "via": "Intramuscular"},
            {"dia": 0, "produto": "Estron", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ],
    }).json()


class TestLancamentoComHormonios:
    def test_persiste_hormonios(self, client):
        c, engine = client
        _lancar_com_hormonios(c, ["700"])
        with Session(engine) as s:
            hs = s.exec(select(ProtocoloIatfHormonio).where(ProtocoloIatfHormonio.dia == 0)).all()
            assert {h.produto for h in hs} == {"SincroCP", "Estron"}

    def test_descricao_do_dia_lista_produtos(self, client):
        c, engine = client
        _lancar_com_hormonios(c, ["700"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert "SincroCP" in d0["hormonio"] and "Estron" in d0["hormonio"]


class TestConfirmarBaixaEstoque:
    def test_confirmar_grupo_baixa_estoque_e_cria_sanidade(self, client):
        c, engine = client
        _lancar_com_hormonios(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        r = c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        assert r.status_code == 200

        with Session(engine) as s:
            sincro = s.exec(select(Estoque).where(Estoque.nome == "SincroCP")).first()
            estron = s.exec(select(Estoque).where(Estoque.nome == "Estron")).first()
            # 2 vacas confirmadas: 1ml×2 e 2ml×2.
            assert sincro.quantidade == 100 - 2
            assert estron.quantidade == 100 - 4

            sanidades = s.exec(select(Sanidade)).all()
            # 2 produtos × 2 vacas = 4 registros de Sanidade.
            assert len(sanidades) == 4
            assert {sa.numero_matriz for sa in sanidades} == {"700", "701"}

            movs = s.exec(select(MovimentoEstoque)).all()
            assert len(movs) == 2  # um por hormônio

    def test_confirmar_parcial_baixa_so_pela_vaca_confirmada(self, client):
        c, engine = client
        _lancar_com_hormonios(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        c.post("/agenda/realizados", json={"evento_id": d0["id"], "animais": ["700"]})

        with Session(engine) as s:
            sincro = s.exec(select(Estoque).where(Estoque.nome == "SincroCP")).first()
            estron = s.exec(select(Estoque).where(Estoque.nome == "Estron")).first()
            assert sincro.quantidade == 100 - 1  # só 1 vaca
            assert estron.quantidade == 100 - 2
            sanidades = s.exec(select(Sanidade)).all()
            assert len(sanidades) == 2  # 2 produtos × 1 vaca
            assert {sa.numero_matriz for sa in sanidades} == {"700"}

    def test_sem_hormonios_nao_baixa_estoque(self, client):
        c, engine = client
        c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-07-08", "protocolo": "IATF simples"})
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        with Session(engine) as s:
            assert s.exec(select(Sanidade)).all() == []
            assert s.exec(select(MovimentoEstoque)).all() == []


class TestBaixaComLancamentosMesclados:
    """Quando o card do dia reúne animais de mais de um ProtocoloIatfLancamento
    (mesmo D0, incluídos separadamente — ver test_agenda_protocolo_iatf.py),
    a baixa sem medicamento explícito tem que respeitar o hormônio cadastrado
    em CADA lançamento, não misturar tudo como se fosse um só."""

    def test_lancamentos_com_hormonios_diferentes_baixam_cada_um_o_seu(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Benzoato", quantidade=100, unidade="ml"))
            s.commit()
        # Lançamento 1 (vaca 700): SincroCP + Estron. Lançamento 2 (vaca 701): Benzoato.
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": "2026-07-08", "protocolo": "IATF teste",
            "hormonios": [
                {"dia": 0, "produto": "SincroCP", "dose": 1, "unidade": "ml", "via": "Intramuscular"},
                {"dia": 0, "produto": "Estron", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
            ],
        })
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["701"], "data_d0": "2026-07-08", "protocolo": "IATF teste",
            "hormonios": [{"dia": 0, "produto": "Benzoato", "dose": 3, "unidade": "ml", "via": "Intramuscular"}],
        })

        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert set(d0["animais"]) == {"700", "701"}

        r = c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        assert r.status_code == 200

        with Session(engine) as s:
            sincro = s.exec(select(Estoque).where(Estoque.nome == "SincroCP")).first()
            estron = s.exec(select(Estoque).where(Estoque.nome == "Estron")).first()
            benzoato = s.exec(select(Estoque).where(Estoque.nome == "Benzoato")).first()
            assert sincro.quantidade == 100 - 1     # 1ml × 1 vaca (só 700 tem esse hormônio)
            assert estron.quantidade == 100 - 2     # 2ml × 1 vaca
            assert benzoato.quantidade == 100 - 3   # 3ml × 1 vaca (só 701)

            sanidades = s.exec(select(Sanidade)).all()
            assert {sa.numero_matriz for sa in sanidades if sa.produto == "Benzoato"} == {"701"}
            assert {sa.numero_matriz for sa in sanidades if sa.produto in ("SincroCP", "Estron")} == {"700"}


class TestQualMedicamentoNoConfirm:
    """Ao confirmar o dia (ex.: D9), o usuário escolhe QUAL medicamento/frasco
    foi usado; a baixa vai para o frasco escolhido (estoque_id) e não mais só
    pelo nome do produto/princípio."""

    def _princípio_com_dois_frascos(self, engine):
        from fazenda.models import PrincipioAtivo
        with Session(engine) as s:
            pa = PrincipioAtivo(nome="Cipionato de Estradiol", unidade_base="ml")
            s.add(pa); s.commit(); s.refresh(pa)
            a = Estoque(nome="E.C.P.", principio_ativo_id=pa.id, quantidade=50, unidade="ml", estoque_inicializado=True)
            b = Estoque(nome="SincroCP", principio_ativo_id=pa.id, quantidade=50, unidade="ml", estoque_inicializado=True)
            s.add(a); s.add(b); s.commit()
            return pa.id, a.id, b.id

    def test_evento_expoe_hormonios_com_opcoes(self, client):
        c, engine = client
        pa_id, a_id, b_id = self._princípio_com_dois_frascos(engine)
        # Lança o protocolo com o hormônio de D9 definido pelo princípio (via um
        # dos medicamentos do princípio, ex.: E.C.P.).
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["800"], "data_d0": "2026-07-01", "protocolo": "IATF teste",
            "hormonios": [{"dia": 9, "produto": "E.C.P.", "dose": 2, "unidade": "ml"}],
        })
        eventos = c.get("/agenda/", params={"data": "2026-07-10", "dias": 30}).json()["eventos"]
        d9 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 9)
        assert d9["hormonios"], "o dia deve expor os hormônios estruturados"
        opcoes = {o["nome"] for o in d9["hormonios"][0]["opcoes"]}
        assert {"E.C.P.", "SincroCP"} <= opcoes  # os dois frascos do princípio

    def test_confirmar_com_medicamento_abate_do_frasco_escolhido(self, client):
        c, engine = client
        pa_id, a_id, b_id = self._princípio_com_dois_frascos(engine)
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["800", "801"], "data_d0": "2026-07-01", "protocolo": "IATF teste",
            "hormonios": [{"dia": 9, "produto": "E.C.P.", "dose": 2, "unidade": "ml"}],
        })
        eventos = c.get("/agenda/", params={"data": "2026-07-10", "dias": 30}).json()["eventos"]
        d9 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 9)
        # Confirma escolhendo o frasco B (SincroCP) para as 2 vacas.
        r = c.post("/agenda/realizados", json={
            "evento_id": d9["id"],
            "medicamentos": [{"produto": "SincroCP", "estoque_id": b_id, "dose": 2, "unidade": "ml"}],
        })
        assert r.status_code == 200
        with Session(engine) as s:
            assert s.get(Estoque, a_id).quantidade == 50        # E.C.P. intacto
            assert s.get(Estoque, b_id).quantidade == 50 - 4    # SincroCP: 2ml × 2 vacas
            sanidades = s.exec(select(Sanidade)).all()
            assert {sa.produto for sa in sanidades} == {"SincroCP"}
