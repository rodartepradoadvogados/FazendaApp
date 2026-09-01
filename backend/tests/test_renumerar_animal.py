"""
Renumerar animal (POST /cadastro/animais/{numero}/renumerar) — pedido do
usuário (01/09/2026): corrigir número/brinco digitado errado, só admin do
tenant, propagando em cascata pra toda referência por numero_matriz/
numero_animal (produção, reprodução, sanidade, genealogia...). Ver
fazenda/api/routers/cadastro/animais.py::renumerar_animal.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import get_current_user
from fazenda.models import (
    AgendaManual, Animal, ControleLeiteiro, Fazenda, MovimentoLote, Parto, Sanidade,
)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fa = Fazenda(nome="Fazenda A", ativa=True)
        s.add(fa)
        s.commit()
        s.refresh(fa)
        fa_id = fa.id

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine, fa_id
    main.app.dependency_overrides.clear()


def _logar_como(papel: str):
    class _FakeUser:
        id = 1
        username = "user"
        ativo = True
        permissoes = "cadastro,parametros,sanidade,producao,reproducao"

    _FakeUser.papel = papel
    import main
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()


def test_operador_nao_pode_renumerar(client):
    c, engine, fa_id = client
    with Session(engine) as s:
        s.add(Animal(numero="100", fazenda_id=fa_id))
        s.commit()
    _logar_como("operador")

    r = c.post("/cadastro/animais/100/renumerar", json={"novo_numero": "200"})
    assert r.status_code == 403


def test_admin_renumera_e_cascateia_historico(client):
    c, engine, fa_id = client
    with Session(engine) as s:
        mae = Animal(numero="10", fazenda_id=fa_id)
        cria = Animal(numero="500", fazenda_id=fa_id, mae_numero="500")  # placeholder, corrigido abaixo
        s.add_all([mae, cria])
        s.commit()
        s.refresh(mae)
        s.refresh(cria)

        # Vaca com número errado (100) que já tem histórico lançado.
        vaca = Animal(numero="100", fazenda_id=fa_id, nome="Errada")
        s.add(vaca)
        s.commit()

        s.add(ControleLeiteiro(numero_matriz="100", data_controle=date(2026, 1, 1), fazenda_id=fa_id))
        s.add(Sanidade(numero_matriz="100", data_aplicacao=date(2026, 1, 2), produto="Vacina X", fazenda_id=fa_id))
        s.add(MovimentoLote(numero_matriz="100", data_movimento=date(2026, 1, 3), lote_origem="01", lote_destino="02", fazenda_id=fa_id))
        s.add(Parto(numero_matriz="10", data_parto=date(2026, 1, 4), numero_cria_1="100", fazenda_id=fa_id))
        s.add(Animal(numero="501", fazenda_id=fa_id, mae_numero="100"))
        s.add(AgendaManual(descricao="Pesar novilhas", data_evento=date(2026, 1, 5), numero_animal="99,100,101", fazenda_id=fa_id))
        s.commit()

    _logar_como("admin")
    r = c.post("/cadastro/animais/100/renumerar", json={"novo_numero": "9100"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["numero_antigo"] == "100"
    assert corpo["numero_novo"] == "9100"
    assert "Sanidade.numero_matriz" in corpo["tabelas_afetadas"]
    assert "AgendaManual.numero_animal" in corpo["tabelas_afetadas"]

    with Session(engine) as s:
        assert s.exec(select(Animal).where(Animal.numero == "100")).first() is None
        renumerado = s.exec(select(Animal).where(Animal.numero == "9100")).first()
        assert renumerado is not None and renumerado.nome == "Errada"

        assert s.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "9100")).first() is not None
        assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "9100")).first() is not None
        assert s.exec(select(MovimentoLote).where(MovimentoLote.numero_matriz == "9100")).first() is not None

        parto = s.exec(select(Parto).where(Parto.numero_matriz == "10")).first()
        assert parto.numero_cria_1 == "9100"

        filha = s.exec(select(Animal).where(Animal.numero == "501")).first()
        assert filha.mae_numero == "9100"

        # Token trocado sem afetar os vizinhos "99"/"101" (não é um replace de substring ingênuo).
        evento = s.exec(select(AgendaManual)).first()
        assert evento.numero_animal == "99,9100,101"


def test_renumerar_bloqueia_colisao_com_animal_existente(client):
    c, engine, fa_id = client
    with Session(engine) as s:
        s.add(Animal(numero="100", fazenda_id=fa_id))
        s.add(Animal(numero="200", fazenda_id=fa_id))
        s.commit()
    _logar_como("admin")

    r = c.post("/cadastro/animais/100/renumerar", json={"novo_numero": "200"})
    assert r.status_code == 400


def test_renumerar_numero_igual_e_rejeitado(client):
    c, engine, fa_id = client
    with Session(engine) as s:
        s.add(Animal(numero="100", fazenda_id=fa_id))
        s.commit()
    _logar_como("admin")

    r = c.post("/cadastro/animais/100/renumerar", json={"novo_numero": "100"})
    assert r.status_code == 400


def test_renumerar_animal_inexistente_404(client):
    c, engine, fa_id = client
    _logar_como("admin")
    r = c.post("/cadastro/animais/999/renumerar", json={"novo_numero": "1000"})
    assert r.status_code == 404
