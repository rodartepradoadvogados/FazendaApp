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
from fazenda.models.planos import ContratoFazenda


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


def _como_fazenda(fazenda_id: int | None):
    """Simula uma sessão já com fazenda selecionada (token com "fid") —
    mesmo padrão de tests/test_seguranca_p1_multitenant.py."""
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def test_renumerar_nao_atravessa_fazenda_furo_confirmado(client):
    """FURO CONFIRMADO (achado da tarefa "sandbox/replicação Fazenda ->
    Fazenda"): `animal.numero` deixou de ser único no banco inteiro
    (migração c24befa94c1b — unicidade composta (fazenda_id, numero), feita
    para permitir a Fazenda Teste copiar uma fazenda real com os MESMOS
    números) — duas fazendas podem hoje ter, cada uma, um animal "100" com
    histórico PRÓPRIO. `_renumerar_em_cascata` (cadastro/animais.py)
    resolvia as linhas de histórico só por `numero_matriz/numero_animal ==
    numero_antigo`, SEM filtrar fazenda_id — renumerar o "100" da fazenda A
    reescrevia também o histórico do "100" da fazenda B.

    Este teste tem que FALHAR antes da correção (fazenda_id propagado para
    dentro de `_renumerar_em_cascata`) e PASSAR depois — ver relatório da
    tarefa."""
    c, engine, fa_id = client
    with Session(engine) as s:
        fb = Fazenda(nome="Fazenda B", ativa=True)
        s.add(fb)
        s.commit()
        s.refresh(fb)
        fb_id = fb.id
        # `cadastro.router` (dono da rota de renumerar) exige contrato ativo
        # quando há fazenda selecionada — ver main.py::_contrato_ativo.
        s.add(ContratoFazenda(fazenda_id=fa_id, status="ativo"))
        s.add(ContratoFazenda(fazenda_id=fb_id, status="ativo"))
        s.commit()

        # Cada fazenda tem seu PRÓPRIO animal "100", com histórico PRÓPRIO —
        # cenário real desde que a unicidade de numero passou a ser
        # (fazenda_id, numero), não mais global.
        s.add(Animal(numero="100", fazenda_id=fa_id, nome="Vaca da Fazenda A"))
        s.add(Animal(numero="100", fazenda_id=fb_id, nome="Vaca da Fazenda B"))
        s.commit()

        s.add(ControleLeiteiro(numero_matriz="100", data_controle=date(2026, 1, 1), fazenda_id=fa_id))
        s.add(Sanidade(numero_matriz="100", data_aplicacao=date(2026, 1, 2), produto="Vacina A", fazenda_id=fa_id))
        s.add(MovimentoLote(numero_matriz="100", data_movimento=date(2026, 1, 3), lote_origem="01", lote_destino="02", fazenda_id=fa_id))
        s.add(AgendaManual(descricao="Evento A", data_evento=date(2026, 1, 4), numero_animal="100", fazenda_id=fa_id))

        s.add(ControleLeiteiro(numero_matriz="100", data_controle=date(2026, 2, 1), fazenda_id=fb_id))
        s.add(Sanidade(numero_matriz="100", data_aplicacao=date(2026, 2, 2), produto="Vacina B", fazenda_id=fb_id))
        s.add(MovimentoLote(numero_matriz="100", data_movimento=date(2026, 2, 3), lote_origem="03", lote_destino="04", fazenda_id=fb_id))
        s.add(AgendaManual(descricao="Evento B", data_evento=date(2026, 2, 4), numero_animal="100", fazenda_id=fb_id))
        s.commit()

    _logar_como("admin")
    _como_fazenda(fa_id)

    r = c.post("/cadastro/animais/100/renumerar", json={"novo_numero": "9100"})
    assert r.status_code == 200, r.text

    with Session(engine) as s:
        # Fazenda A: renumerado de fato, histórico cascateado.
        assert s.exec(select(Animal).where(Animal.numero == "100", Animal.fazenda_id == fa_id)).first() is None
        renumerado_a = s.exec(select(Animal).where(Animal.numero == "9100", Animal.fazenda_id == fa_id)).first()
        assert renumerado_a is not None and renumerado_a.nome == "Vaca da Fazenda A"
        assert s.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "9100", ControleLeiteiro.fazenda_id == fa_id)).first() is not None
        assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "9100", Sanidade.fazenda_id == fa_id)).first() is not None
        assert s.exec(select(MovimentoLote).where(MovimentoLote.numero_matriz == "9100", MovimentoLote.fazenda_id == fa_id)).first() is not None
        evento_a = s.exec(select(AgendaManual).where(AgendaManual.fazenda_id == fa_id)).first()
        assert evento_a.numero_animal == "9100"

        # Fazenda B: NADA pode ter mudado — nem o animal, nem o histórico.
        animal_b = s.exec(select(Animal).where(Animal.numero == "100", Animal.fazenda_id == fb_id)).first()
        assert animal_b is not None and animal_b.nome == "Vaca da Fazenda B"
        assert s.exec(select(Animal).where(Animal.numero == "9100", Animal.fazenda_id == fb_id)).first() is None
        assert s.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "100", ControleLeiteiro.fazenda_id == fb_id)).first() is not None
        assert s.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "9100", ControleLeiteiro.fazenda_id == fb_id)).first() is None
        assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "100", Sanidade.fazenda_id == fb_id)).first() is not None
        assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "9100", Sanidade.fazenda_id == fb_id)).first() is None
        assert s.exec(select(MovimentoLote).where(MovimentoLote.numero_matriz == "100", MovimentoLote.fazenda_id == fb_id)).first() is not None
        assert s.exec(select(MovimentoLote).where(MovimentoLote.numero_matriz == "9100", MovimentoLote.fazenda_id == fb_id)).first() is None
        evento_b = s.exec(select(AgendaManual).where(AgendaManual.fazenda_id == fb_id)).first()
        assert evento_b.numero_animal == "100"
