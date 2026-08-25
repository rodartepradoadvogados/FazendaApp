"""
GET /producao/ordem-parto/divergencias e POST /producao/ordem-parto/reconstruir
— versão HTTP, autenticada e escopada por fazenda_id, do script
scripts/reconstruir_ordem_parto.py (ver a docstring do próprio script, e a
seção "Reconstrução de ControleLeiteiro.ordem_parto" em
fazenda/api/routers/producao.py, para o porquê completo).

`levantar`/`gravar` foram portados para o router (não importados do script)
— a lógica é a mesma, então os números aqui espelham de propósito os já
travados em test_producao_controles.py::TestOrdemPartoNaListagem/
TestRelatorioOrdemParto (cenário idêntico: vaca "201", dois partos, três
controles — um ANTES de qualquer parto conhecido, um em cada lactação).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, ControleLeiteiro, Fazenda, Parto


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

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    # `get_fazenda_id_escrita` (usado pelo POST) é composto EM CIMA de
    # `get_fazenda_atual_id` — sobrescrever só este basta para os dois (ver
    # docstring de get_fazenda_id_escrita em fazenda/auth.py).
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        with Session(engine) as s:
            # `exigir_modulo_contratado("produtivo")` (main.py, na inclusão
            # do router /producao) exige contrato ATIVO + módulo "produtivo"
            # contratado para a fazenda do token — sem isso toda rota deste
            # router devolve 403 assim que `get_fazenda_atual_id` aponta para
            # uma fazenda de verdade (mesmo padrão de
            # test_isolamento_agenda_sanidade.py).
            for fid in (1, 2):
                s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="produtivo", preco=0.0, ativo=True))

            # Fazenda 1 — vaca "201" com dois partos e três controles: um
            # ANTES de qualquer parto conhecido, um DURANTE a 1ª lactação e
            # um DURANTE a 2ª (mesmo cenário de test_producao_controles.py).
            s.add(Animal(numero="201", grupo_primario="01 - Alta", raca="Holandês", ativo=True, fazenda_id=1))
            s.add(Parto(numero_matriz="201", data_parto=date(2026, 1, 1), ordem_parto=1, fazenda_id=1))
            s.add(Parto(numero_matriz="201", data_parto=date(2026, 7, 1), ordem_parto=2, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="201", data_controle=date(2025, 1, 1), producao_kg=20.0, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="201", data_controle=date(2026, 2, 1), producao_kg=25.0, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="201", data_controle=date(2026, 8, 1), producao_kg=30.0, fazenda_id=1))

            # Fazenda 2 — outro animal, cenário DIFERENTE (uma divergência
            # própria) — nunca deve aparecer nem ser gravada atuando como
            # fazenda 1, e vice-versa. `Animal.numero` é único globalmente
            # (não por fazenda), daí o número distinto de "201".
            s.add(Animal(numero="301", grupo_primario="01 - Alta", raca="Holandês", ativo=True, fazenda_id=2))
            s.add(Parto(numero_matriz="301", data_parto=date(2026, 3, 1), ordem_parto=1, fazenda_id=2))
            s.add(Parto(numero_matriz="301", data_parto=date(2026, 9, 1), ordem_parto=2, fazenda_id=2))
            s.add(ControleLeiteiro(numero_matriz="301", data_controle=date(2026, 4, 1), producao_kg=22.0, fazenda_id=2))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


def _atuar_como_fazenda(fazenda_id: int) -> None:
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestDivergenciasOrdemParto:
    def test_relatorio_reflete_divergencias_reais_da_fazenda(self, client):
        c, _ = client
        r = c.get("/producao/ordem-parto/divergencias")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["partos"] == 2
        assert corpo["controles"] == 3
        # Atalho antigo = contagem total de partos (2), aplicada aos 3
        # controles. Ordem correta por data é None / 1 / 2 — o controle mais
        # recente bate com o atalho por coincidência (é onde o atalho SEMPRE
        # acerta); os outros dois divergem.
        assert corpo["muda"] == 2
        assert corpo["vira_desconhecido"] == 1
        amostra = {a["data_controle"]: a for a in corpo["amostra"]}
        assert amostra["2026-02-01"]["ordem_hoje"] == 2
        assert amostra["2026-02-01"]["ordem_correta"] == 1
        assert amostra["2025-01-01"]["ordem_correta"] is None

    def test_relatorio_nao_grava_nada(self, client):
        c, engine = client
        c.get("/producao/ordem-parto/divergencias")
        r2 = c.get("/producao/ordem-parto/divergencias")
        assert r2.json()["muda"] == 2
        with Session(engine) as s:
            controles = s.exec(select(ControleLeiteiro).where(ControleLeiteiro.fazenda_id == 1)).all()
            assert all(ctrl.ordem_parto is None for ctrl in controles)

    def test_divergencia_da_outra_fazenda_nunca_aparece(self, client):
        c, _ = client
        r = c.get("/producao/ordem-parto/divergencias")
        assert r.json()["controles"] == 3  # só os da fazenda 1

        _atuar_como_fazenda(2)
        r2 = c.get("/producao/ordem-parto/divergencias")
        assert r2.json()["controles"] == 1  # só o da fazenda 2
        assert r2.json()["muda"] == 1


class TestReconstruirOrdemParto:
    def test_sem_confirmar_e_400_e_nao_grava_nada(self, client):
        c, engine = client
        r = c.post("/producao/ordem-parto/reconstruir", json={})
        assert r.status_code == 400
        with Session(engine) as s:
            controles = s.exec(select(ControleLeiteiro)).all()
            assert all(ctrl.ordem_parto is None for ctrl in controles)

    def test_confirmar_false_explicito_tambem_e_400(self, client):
        c, _ = client
        r = c.post("/producao/ordem-parto/reconstruir", json={"confirmar": False})
        assert r.status_code == 400

    def test_confirmar_true_grava_exatamente_os_valores_corretos(self, client):
        c, engine = client
        r = c.post("/producao/ordem-parto/reconstruir", json={"confirmar": True})
        assert r.status_code == 200
        assert r.json()["gravados"] == 2

        with Session(engine) as s:
            por_data = {
                ctrl.data_controle: ctrl.ordem_parto
                for ctrl in s.exec(select(ControleLeiteiro).where(ControleLeiteiro.fazenda_id == 1)).all()
            }
            assert por_data[date(2026, 2, 1)] == 1
            assert por_data[date(2026, 8, 1)] == 2

    def test_controle_anterior_a_qualquer_parto_conhecido_fica_intocado(self, client):
        """A resposta correta pra esse controle é genuinamente desconhecida —
        não pode virar um palpite, nem ser zerado se já tivesse algo (aqui já
        nasce None, e tem que CONTINUAR None, não ganhar um número)."""
        c, engine = client
        c.post("/producao/ordem-parto/reconstruir", json={"confirmar": True})
        with Session(engine) as s:
            controle = s.exec(
                select(ControleLeiteiro).where(
                    ControleLeiteiro.fazenda_id == 1, ControleLeiteiro.data_controle == date(2025, 1, 1),
                )
            ).first()
            assert controle.ordem_parto is None

    def test_rodar_de_novo_nao_recontagem_o_que_ja_esta_certo(self, client):
        c, _ = client
        r1 = c.post("/producao/ordem-parto/reconstruir", json={"confirmar": True})
        assert r1.json()["gravados"] == 2
        r2 = c.post("/producao/ordem-parto/reconstruir", json={"confirmar": True})
        assert r2.json()["gravados"] == 0

    def test_isolamento_por_fazenda_na_gravacao(self, client):
        """Gravar atuando como fazenda 1 nunca toca nos controles da
        fazenda 2, e vice-versa."""
        c, engine = client
        c.post("/producao/ordem-parto/reconstruir", json={"confirmar": True})
        with Session(engine) as s:
            controle_f2 = s.exec(select(ControleLeiteiro).where(ControleLeiteiro.fazenda_id == 2)).first()
            assert controle_f2.ordem_parto is None  # nunca tocado atuando como fazenda 1

        _atuar_como_fazenda(2)
        r = c.post("/producao/ordem-parto/reconstruir", json={"confirmar": True})
        assert r.json()["gravados"] == 1
        with Session(engine) as s:
            controle_f2 = s.exec(select(ControleLeiteiro).where(ControleLeiteiro.fazenda_id == 2)).first()
            assert controle_f2.ordem_parto == 1
            # Os da fazenda 1, já gravados antes, continuam intactos.
            controle_f1 = s.exec(
                select(ControleLeiteiro).where(
                    ControleLeiteiro.fazenda_id == 1, ControleLeiteiro.data_controle == date(2026, 2, 1),
                )
            ).first()
            assert controle_f1.ordem_parto == 1
