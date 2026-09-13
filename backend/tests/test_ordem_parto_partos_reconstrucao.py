"""
GET /producao/ordem-parto/partos/divergencias e
POST /producao/ordem-parto/partos/reconstruir — reconstrução de
`Parto.ordem_parto` em si (a FONTE do dado), não o derivado em
`ControleLeiteiro` (esse já tem cobertura em
test_ordem_parto_reconstrucao_endpoint.py).

Cenário real relatado pelo usuário (matriz "432" do relatório): o primeiro
parto veio da importação de planilha do Ideagri com `ordem_parto=0` — a
planilha usa uma convenção base 0 (0 = 1ª cria), diferente da deste app
(1 = 1ª cria). Simulado aqui inserindo o `Parto` direto no banco, como um
import faria (sem passar pelo endpoint, que sempre calcula a ordem certa
hoje — ver `test_lactacao.py` e `rules/parto.py` para a correção da
PROPAGAÇÃO do bug; este arquivo cobre a correção do DADO JÁ GRAVADO).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Parto
from fazenda.rules.equivalente_maduro import classe_de_ordem


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    # `fazenda_id=None` — mesmo padrão de test_lactacao.py — dispensa o setup
    # de ContratoFazenda/ContratoFazendaModulo (ver exigir_modulo_contratado).
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: None
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: None

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _add(engine, *objs):
    with Session(engine) as s:
        for o in objs:
            s.add(o)
        s.commit()


# ---------------------------------------------------------------------------
# Cenário matriz 432: 1º parto importado com ordem_parto=0 (errado — a
# planilha do Ideagri é base 0), 2º parto lançado ao vivo pelo app.
# ---------------------------------------------------------------------------
class TestCenarioMatriz432:
    def test_relatorio_acusa_o_primeiro_parto_importado_como_divergente(self, client):
        c, engine = client
        _add(
            engine,
            Animal(numero="432", sexo="F", ativo=True),
            # Simula o import: ordem_parto=0 (convenção da planilha de origem).
            Parto(numero_matriz="432", data_parto=date(2024, 1, 10), ordem_parto=0, tipo_parto="Parto normal"),
            # 2º parto lançado ao vivo já usa a contagem corrigida (ver
            # test_lactacao.py) — nasce com ordem_parto=2, e portanto NÃO
            # diverge aqui.
            Parto(numero_matriz="432", data_parto=date(2025, 6, 20), ordem_parto=2, tipo_parto="Parto normal"),
        )
        r = c.get("/producao/ordem-parto/partos/divergencias")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["partos"] == 2
        assert corpo["matrizes_com_parto"] == 1
        assert corpo["muda"] == 1
        assert corpo["vira_desconhecido"] == 0
        amostra = corpo["amostra"][0]
        assert amostra["numero_matriz"] == "432"
        assert amostra["data_parto"] == "2024-01-10"
        assert amostra["ordem_hoje"] == 0
        assert amostra["ordem_correta"] == 1

    def test_reconstruir_corrige_o_primeiro_parto_de_0_para_1(self, client):
        c, engine = client
        _add(
            engine,
            Animal(numero="432", sexo="F", ativo=True),
            Parto(numero_matriz="432", data_parto=date(2024, 1, 10), ordem_parto=0, tipo_parto="Parto normal"),
            Parto(numero_matriz="432", data_parto=date(2025, 6, 20), ordem_parto=2, tipo_parto="Parto normal"),
        )
        r = c.post("/producao/ordem-parto/partos/reconstruir", json={"confirmar": True})
        assert r.status_code == 200
        assert r.json()["gravados"] == 1

        with Session(engine) as s:
            partos = {p.data_parto: p.ordem_parto for p in s.exec(select(Parto)).all()}
            assert partos[date(2024, 1, 10)] == 1     # era 0, virou 1
            assert partos[date(2025, 6, 20)] == 2      # já estava certo, intocado

    def test_equivalente_maduro_deixa_de_ser_desconhecido_apos_a_correcao(self):
        """`classe_de_ordem` já trata `ordem_parto < 1` como "desconhecida" —
        é exatamente o sintoma do dado sujo (0 é lido como "não sei
        classificar"). Depois da reconstrução (0 -> 1), a classificação
        volta a funcionar."""
        assert classe_de_ordem(0) is None      # dado sujo: "desconhecida"
        assert classe_de_ordem(1) == 1          # dado corrigido: 1ª cria


class TestSemConfirmarNaoGravaNada:
    def test_sem_confirmar_e_400(self, client):
        c, engine = client
        _add(engine, Animal(numero="432", sexo="F", ativo=True),
             Parto(numero_matriz="432", data_parto=date(2024, 1, 10), ordem_parto=0, tipo_parto="Parto normal"))
        r = c.post("/producao/ordem-parto/partos/reconstruir", json={})
        assert r.status_code == 400
        with Session(engine) as s:
            assert s.exec(select(Parto)).one().ordem_parto == 0

    def test_rodar_de_novo_nao_regrava_o_que_ja_esta_certo(self, client):
        c, engine = client
        _add(engine, Animal(numero="432", sexo="F", ativo=True),
             Parto(numero_matriz="432", data_parto=date(2024, 1, 10), ordem_parto=0, tipo_parto="Parto normal"))
        r1 = c.post("/producao/ordem-parto/partos/reconstruir", json={"confirmar": True})
        assert r1.json()["gravados"] == 1
        r2 = c.post("/producao/ordem-parto/partos/reconstruir", json={"confirmar": True})
        assert r2.json()["gravados"] == 0


class TestAbortoNaReconstrucao:
    """Aborto sem abertura de lactação fica fora da contagem (ordem_parto
    deve ser None); um aborto histórico com ordem_parto gravado por engano
    (ex.: parser legado que não distinguia tipo) é corrigido para None."""

    def test_aborto_sem_lactacao_com_ordem_espuria_vira_none(self, client):
        c, engine = client
        _add(
            engine,
            Animal(numero="900", sexo="F", ativo=True),
            Parto(numero_matriz="900", data_parto=date(2024, 1, 1), ordem_parto=1, tipo_parto="Parto normal"),
            # Aborto histórico com ordem_parto gravado por engano (dado sujo).
            Parto(numero_matriz="900", data_parto=date(2024, 6, 1), ordem_parto=2, tipo_parto="Aborto"),
            Parto(numero_matriz="900", data_parto=date(2025, 1, 1), ordem_parto=3, tipo_parto="Parto normal"),
        )
        r = c.get("/producao/ordem-parto/partos/divergencias")
        corpo = r.json()
        assert corpo["muda"] == 2          # o aborto (2->None) e o parto seguinte (3->2)
        assert corpo["vira_desconhecido"] == 1

        c.post("/producao/ordem-parto/partos/reconstruir", json={"confirmar": True})
        with Session(engine) as s:
            partos = {p.data_parto: (p.tipo_parto, p.ordem_parto) for p in s.exec(select(Parto)).all()}
            assert partos[date(2024, 1, 1)] == ("Parto normal", 1)
            assert partos[date(2024, 6, 1)] == ("Aborto", None)
            assert partos[date(2025, 1, 1)] == ("Parto normal", 2)

    def test_aborto_que_abriu_lactacao_conta_na_sequencia(self, client):
        c, engine = client
        _add(
            engine,
            Animal(numero="901", sexo="F", ativo=True),
            Parto(numero_matriz="901", data_parto=date(2024, 1, 1), ordem_parto=1, tipo_parto="Parto normal"),
            # Aborto que abriu lactação — produtivo, deve contar como 2.
            Parto(
                numero_matriz="901", data_parto=date(2024, 8, 1), ordem_parto=None,
                tipo_parto="Aborto", abriu_lactacao=True,
            ),
            Parto(numero_matriz="901", data_parto=date(2025, 3, 1), ordem_parto=None, tipo_parto="Parto normal"),
        )
        r = c.get("/producao/ordem-parto/partos/divergencias")
        corpo = r.json()
        # O aborto-com-lactação (None -> 2) e o parto seguinte (None -> 3) mudam.
        assert corpo["muda"] == 2
        assert corpo["vira_desconhecido"] == 0

        c.post("/producao/ordem-parto/partos/reconstruir", json={"confirmar": True})
        with Session(engine) as s:
            partos = {p.data_parto: p.ordem_parto for p in s.exec(select(Parto)).all()}
            assert partos[date(2024, 1, 1)] == 1
            assert partos[date(2024, 8, 1)] == 2   # aborto com lactação conta
            assert partos[date(2025, 3, 1)] == 3
