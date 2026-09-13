"""
Testes de `Lote.modo_baixa_estoque` — a proposta aceita pelo proprietário de
escolher, POR LOTE, como a dieta afeta o Estoque:

  "automatica"    baixa dia a dia pelo PLANO (`_dar_baixa_automatica`, o
                  mecanismo de dias decorridos que hoje roda incondicional
                  pra fazenda inteira).
  "consumo_real"  (padrão) só baixa quando alguém lança o consumo de verdade
                  em "Consumo diário e sobra" (`lancar_consumo`) — o único
                  mecanismo que já funcionava de ponta a ponta antes desta
                  coluna existir, por isso vira o padrão restritivo/compatível.
  "sem_baixa"     a dieta é só plano/receita — nenhum dos dois mecanismos
                  toca o Estoque deste lote.

`ConsumoAlimento.baixou_estoque` guarda, por registro, se aquele lançamento
específico debitou estoque — usado por `excluir_consumo` para saber se deve
devolver, sem depender do modo ATUAL do lote (que pode ter mudado depois).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import AlimentacaoEstado, Animal, ConsumoAlimento, DietaItemProgramado, DietaLancamento, Estoque, Lote

HOJE = date(2026, 8, 20)


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


def _seed_lote(
    engine, codigo: str, lote_int: int, modo: str | None, *,
    ingrediente: str = "Silagem", kg_total_dia: float = 40.0, estoque_inicial: float = 1000.0,
):
    """Lote com 2 animais e dieta ATIVA "total/dia" com um item — `kg_total_dia`
    é o total do LOTE (2 animais => `kg_total_dia`/2 por cabeça). `modo=None`
    omite o cadastro do campo (deixa o SQLModel aplicar o default
    "consumo_real" da própria coluna)."""
    with Session(engine) as s:
        dados_lote = {"codigo": codigo, "nome": f"Lote {codigo}"}
        if modo is not None:
            dados_lote["modo_baixa_estoque"] = modo
        s.add(Lote(**dados_lote))
        s.add(Animal(numero=f"{codigo}-A", categoria_abrev="Vaca", sexo="F", grupo_primario=f"{codigo} - Lote", ativo=True))
        s.add(Animal(numero=f"{codigo}-B", categoria_abrev="Vaca", sexo="F", grupo_primario=f"{codigo} - Lote", ativo=True))
        dieta = DietaLancamento(lote=lote_int, data_abertura=HOJE, base_quantidade="total")
        s.add(dieta)
        s.commit()
        s.refresh(dieta)
        s.add(DietaItemProgramado(dieta_lancamento_id=dieta.id, alimento=ingrediente, quantidade=kg_total_dia, unidade="kg"))
        s.add(Estoque(nome=ingrediente, quantidade=estoque_inicial, unidade="kg"))
        s.commit()


def _avancar_dias(engine, dias: int):
    """Simula que `dias` se passaram desde a última baixa automática, sem
    esperar de verdade — mesma técnica de test_alimentacao.py."""
    with Session(engine) as s:
        estado = s.exec(select(AlimentacaoEstado)).first()
        estado.ultima_data_deducao = date.today() - timedelta(days=dias)
        s.add(estado)
        s.commit()


def _lancar(c, lote: int, alimento: str, quantidade: float):
    return c.post("/alimentacao/consumo", json={
        "lote": lote, "data": HOJE.isoformat(), "origem": "kg",
        "itens": [{"alimento": alimento, "quantidade": quantidade, "unidade": "kg"}],
    })


def _quantidade(engine, nome: str) -> float:
    with Session(engine) as s:
        return s.exec(select(Estoque).where(Estoque.nome == nome)).first().quantidade


class TestModoConsumoRealEhOPadrao:
    """(a) Lote sem `modo_baixa_estoque` explícito — hoje o único mecanismo
    que funciona é o consumo real, e é isso que continua acontecendo."""

    def test_baixa_automatica_nao_toca_mas_lancar_consumo_deduz_normalmente(self, client):
        c, engine = client
        _seed_lote(engine, "01", 1, modo=None)

        c.get("/alimentacao/")  # baseline
        _avancar_dias(engine, 3)
        c.get("/alimentacao/")
        assert _quantidade(engine, "Silagem") == 1000.0, "consumo_real (padrão) não é debitado pela baixa automática"

        r = _lancar(c, 1, "Silagem", 40.0)
        assert r.status_code == 201, r.text
        assert _quantidade(engine, "Silagem") == 960.0

        with Session(engine) as s:
            registro = s.exec(select(ConsumoAlimento).where(ConsumoAlimento.lote == 1)).first()
            assert registro.baixou_estoque is True


class TestModoAutomatica:
    """(b) `_dar_baixa_automatica` deduz; `lancar_consumo` só registra."""

    def test_baixa_automatica_deduz_lancar_consumo_so_registra(self, client):
        c, engine = client
        _seed_lote(engine, "01", 1, modo="automatica")

        c.get("/alimentacao/")  # baseline
        _avancar_dias(engine, 2)
        c.get("/alimentacao/")
        assert _quantidade(engine, "Silagem") == 920.0  # 40kg/dia * 2 dias

        r = _lancar(c, 1, "Silagem", 40.0)
        assert r.status_code == 201, r.text
        assert _quantidade(engine, "Silagem") == 920.0, "modo automatica: lançar consumo não pode debitar de novo"

        with Session(engine) as s:
            registro = s.exec(select(ConsumoAlimento).where(ConsumoAlimento.lote == 1)).first()
            assert registro is not None, "o registro de consumo/sobra continua sendo criado"
            assert registro.baixou_estoque is False


class TestModoSemBaixa:
    """(c) Nenhum dos dois mecanismos toca o Estoque; o registro de consumo
    (sobra/histórico) continua existindo."""

    def test_nenhum_mecanismo_deduz(self, client):
        c, engine = client
        _seed_lote(engine, "01", 1, modo="sem_baixa")

        c.get("/alimentacao/")  # baseline
        _avancar_dias(engine, 5)
        c.get("/alimentacao/")
        assert _quantidade(engine, "Silagem") == 1000.0

        r = _lancar(c, 1, "Silagem", 40.0)
        assert r.status_code == 201, r.text
        assert _quantidade(engine, "Silagem") == 1000.0

        with Session(engine) as s:
            registro = s.exec(select(ConsumoAlimento).where(ConsumoAlimento.lote == 1)).first()
            assert registro is not None
            assert registro.baixou_estoque is False


class TestExclusaoRespeitaORegistro:
    """(d) A exclusão olha `baixou_estoque` do REGISTRO, não o modo atual do
    lote — nunca inventa devolução de estoque que nunca saiu."""

    def test_excluir_registro_que_nunca_debitou_nao_devolve_nada(self, client):
        c, engine = client
        _seed_lote(engine, "01", 1, modo="automatica")
        _lancar(c, 1, "Silagem", 40.0)

        with Session(engine) as s:
            registro = s.exec(select(ConsumoAlimento).where(ConsumoAlimento.lote == 1)).first()
            assert registro.baixou_estoque is False
            registro_id = registro.id
        antes = _quantidade(engine, "Silagem")

        r = c.delete(f"/alimentacao/consumo/{registro_id}")
        assert r.status_code == 200, r.text
        assert _quantidade(engine, "Silagem") == antes

        with Session(engine) as s:
            assert s.get(ConsumoAlimento, registro_id) is None

    def test_mudar_o_modo_depois_nao_muda_o_estorno_de_registros_antigos(self, client):
        """O registro nasceu em modo "automatica" (não debitou). Mesmo que o
        lote seja reconfigurado para "consumo_real" depois, excluir o
        registro antigo continua sem devolver nada — ele nunca tirou nada."""
        c, engine = client
        _seed_lote(engine, "01", 1, modo="automatica")
        _lancar(c, 1, "Silagem", 40.0)
        with Session(engine) as s:
            registro_id = s.exec(select(ConsumoAlimento).where(ConsumoAlimento.lote == 1)).first().id
            lote = s.exec(select(Lote).where(Lote.codigo == "01")).first()
            lote.modo_baixa_estoque = "consumo_real"
            s.add(lote)
            s.commit()
        antes = _quantidade(engine, "Silagem")

        r = c.delete(f"/alimentacao/consumo/{registro_id}")
        assert r.status_code == 200, r.text
        assert _quantidade(engine, "Silagem") == antes


class TestMultiLote:
    """(e) Lote A em "automatica" e lote B em "consumo_real", ambos com
    dieta — a baixa automática deduz SÓ o lote A."""

    def test_baixa_automatica_deduz_so_o_lote_automatica(self, client):
        c, engine = client
        _seed_lote(engine, "01", 1, modo="automatica", ingrediente="Silagem", kg_total_dia=40.0, estoque_inicial=1000.0)
        _seed_lote(engine, "02", 2, modo="consumo_real", ingrediente="Concentrado", kg_total_dia=20.0, estoque_inicial=500.0)

        c.get("/alimentacao/")  # baseline
        _avancar_dias(engine, 1)
        c.get("/alimentacao/")

        assert _quantidade(engine, "Silagem") == 960.0  # lote A: 1000 - 40kg/dia * 1 dia
        assert _quantidade(engine, "Concentrado") == 500.0, "lote B (consumo_real) não é tocado pela baixa automática"

        # O lote B só é debitado quando alguém lança o consumo de verdade.
        r = _lancar(c, 2, "Concentrado", 20.0)
        assert r.status_code == 201, r.text
        assert _quantidade(engine, "Concentrado") == 480.0
        # E o lote A, que já é debitado pelo mecanismo automático, não é
        # tocado de novo se alguém (por engano ou não) lançar consumo dele.
        r2 = _lancar(c, 1, "Silagem", 40.0)
        assert r2.status_code == 201, r2.text
        assert _quantidade(engine, "Silagem") == 960.0
