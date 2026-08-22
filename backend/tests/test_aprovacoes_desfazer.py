"""
G17 — Configurações > Aprovações > "Desfazer aprovação":
GET /aprovacoes/decididas e POST /aprovacoes/{id}/desfazer.

Rejeitado -> desfazer volta a pendente. Aprovado -> desfazer apaga o que foi
materializado (mesmo trio do motor de exclusões: desvincula vale, estorna
estoque, session.delete) e também volta a pendente. Pendente -> desfazer dá
409. Isolamento entre fazendas via _verificar_posse.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ControleLeiteiro, Estoque, Lactacao, LancamentoPendente, MovimentoEstoque, Sanidade,
)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import exigir_admin, get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""
        pode_publicar_materias_blog = True

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


@pytest.fixture
def client_sem_permissao_noticia():
    """Admin comum, mas SEM pode_publicar_materias_blog — para o caso
    noticia_manual, que exige a permissão específica mesmo de um admin."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import exigir_admin, get_current_user

    class _FakeAdminSemNoticia:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""
        pode_publicar_materias_blog = False

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdminSemNoticia()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdminSemNoticia()

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
    from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = ""
        pode_publicar_materias_blog = True

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _criar_pendente(engine, *, tipo: str, dados: dict, status="pendente", fazenda_id=None, registro_criado=None) -> int:
    with Session(engine) as s:
        p = LancamentoPendente(
            tipo=tipo, payload=json.dumps(dados), resumo=f"{tipo} de teste", status=status,
            fazenda_id=fazenda_id,
            decidido_em=datetime.utcnow() if status != "pendente" else None,
            decidido_por="alguem" if status != "pendente" else None,
            registro_criado=registro_criado,
        )
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


class TestDesfazerRejeitado:
    def test_desfazer_rejeitado_volta_a_pendente(self, client):
        c, engine = client
        pid = _criar_pendente(engine, tipo="controle_leiteiro", dados={
            "numero_matriz": "123", "data_controle": "2026-01-10", "ordenhas": [10, 8],
        })
        r = c.post(f"/aprovacoes/{pid}/rejeitar")
        assert r.status_code == 200

        r2 = c.post(f"/aprovacoes/{pid}/desfazer")
        assert r2.status_code == 200
        assert r2.json()["status"] == "pendente"

        with Session(engine) as s:
            p = s.get(LancamentoPendente, pid)
            assert p.status == "pendente"
            assert p.decidido_em is None
            assert p.decidido_por is None


class TestDesfazerAprovadoControleLeiteiro:
    def test_aprovado_controle_leiteiro_desfazer_apaga_e_volta_a_pendente(self, client):
        c, engine = client
        # Aprovar um controle leiteiro cai no mesmo caminho de gravação do
        # lançamento direto, que passou a exigir uma `Lactacao` ABERTA na data
        # do controle (ver rules/lactacao.py) — é dela que sai o DEL. Sem isso
        # a aprovação é recusada, que é justamente o comportamento desejado:
        # aprovar não deve ser uma porta dos fundos para gravar leite de uma
        # matriz que não está lactando.
        with Session(engine) as s:
            s.add(Animal(numero="321", ativo=True, sexo="F"))
            s.add(Lactacao(numero_matriz="321", data_inicio=date(2025, 12, 1), origem="parto"))
            s.commit()
        pid = _criar_pendente(engine, tipo="controle_leiteiro", dados={
            "numero_matriz": "321", "data_controle": "2026-02-01", "ordenhas": [12, 9],
        })

        r = c.post(f"/aprovacoes/{pid}/aprovar")
        assert r.status_code == 200

        with Session(engine) as s:
            p = s.get(LancamentoPendente, pid)
            assert p.status == "aprovado"
            assert p.registro_criado  # G17 gravou o que foi criado
            registros = json.loads(p.registro_criado)
            assert isinstance(registros, list) and registros[0]["tipo"] == "controle"
            criado = s.exec(
                select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "321")
            ).first()
            assert criado is not None

        # "Decididos" mostra que dá pra desfazer.
        r_dec = c.get("/aprovacoes/decididas")
        assert r_dec.status_code == 200
        item = next(x for x in r_dec.json() if x["id"] == pid)
        assert item["pode_desfazer"] is True

        r2 = c.post(f"/aprovacoes/{pid}/desfazer")
        assert r2.status_code == 200
        assert r2.json()["status"] == "pendente"

        with Session(engine) as s:
            p = s.get(LancamentoPendente, pid)
            assert p.status == "pendente"
            assert p.registro_criado is None
            ainda_existe = s.exec(
                select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "321")
            ).first()
            assert ainda_existe is None


class TestDesfazerAprovadoSanidadeEstornaEstoque:
    def test_desfazer_sanidade_devolve_o_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Vermífugo Teste", unidade="ml", quantidade=100, estocavel=True))
            s.commit()

        pid = _criar_pendente(engine, tipo="sanidade", dados={
            "animais": ["700"], "data_aplicacao": "2026-01-05",
            "produto": "Vermífugo Teste", "quantidade": 5, "unidade": "ml",
        })
        r = c.post(f"/aprovacoes/{pid}/aprovar")
        assert r.status_code == 200

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Vermífugo Teste")).first()
            assert item.quantidade == 95
            sanidade = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "700")).first()
            assert sanidade is not None
            sanidade_id = sanidade.id

        r2 = c.post(f"/aprovacoes/{pid}/desfazer")
        assert r2.status_code == 200

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Vermífugo Teste")).first()
            assert item.quantidade == 100  # devolvido
            assert s.get(Sanidade, sanidade_id) is None


class TestDesfazerAprovadoSemRegistroCriado:
    def test_aprovado_legado_sem_registro_criado_da_400(self, client):
        c, engine = client
        pid = _criar_pendente(
            engine, tipo="parto", dados={"numero_matriz": "1", "data_parto": "2026-01-01"},
            status="aprovado", registro_criado=None,
        )

        r = c.get("/aprovacoes/decididas")
        item = next(x for x in r.json() if x["id"] == pid)
        assert item["pode_desfazer"] is False
        assert item["motivo_nao_desfaz"]

        r2 = c.post(f"/aprovacoes/{pid}/desfazer")
        assert r2.status_code == 400


class TestDesfazerPendenteDa409:
    def test_desfazer_pendente_da_409(self, client):
        c, engine = client
        pid = _criar_pendente(engine, tipo="controle_leiteiro", dados={
            "numero_matriz": "1", "data_controle": "2026-01-01", "ordenhas": [1],
        })
        r = c.post(f"/aprovacoes/{pid}/desfazer")
        assert r.status_code == 409


class TestIsolamentoPorFazenda:
    def test_desfazer_pendente_de_outra_fazenda_da_404(self, client_fazenda):
        c, engine = client_fazenda
        pid = _criar_pendente(
            engine, tipo="controle_leiteiro",
            dados={"numero_matriz": "1", "data_controle": "2026-01-01", "ordenhas": [1]},
            status="rejeitado", fazenda_id=2,
        )
        r = c.post(f"/aprovacoes/{pid}/desfazer")
        assert r.status_code == 404


class TestNoticiaManualExigePermissao:
    def test_desfazer_noticia_manual_sem_permissao_da_403(self, client_sem_permissao_noticia):
        c, engine = client_sem_permissao_noticia
        pid = _criar_pendente(
            engine, tipo="noticia_manual", dados={"manchete": "Teste"}, status="rejeitado",
        )
        r = c.post(f"/aprovacoes/{pid}/desfazer")
        assert r.status_code == 403
