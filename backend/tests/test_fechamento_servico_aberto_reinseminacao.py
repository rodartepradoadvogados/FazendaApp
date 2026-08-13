"""
Nova inseminação fecha como NEGATIVO o serviço anterior em aberto.

Relatado pelo produtor a partir de um caso real (matriz 108):

    14/07/2026 — IA, método IATF,           diagnóstico ABERTO, tentativa 2
    05/08/2026 — IS, IA em cio natural,     diagnóstico ABERTO, tentativa 3

A segunda inseminação prova que a primeira não pegou. Deixando a de 14/07 em
aberto para sempre, ela some do denominador da taxa de concepção (que sai
inflada, ver rules/indicadores.py e rules/reproducao_analise.py) e polui o
histórico de reprodução da matriz.

Vale para IATF, IA em cio natural e monta natural — e também para o D0 de
protocolo IATF, que nem cria Servico.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, Parto, Servico
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.add(Animal(numero="108", fazenda_id=1, ativo=True, raca="Girolando"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "teste@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _servico(engine, **campos):
    with Session(engine) as s:
        s.add(Servico(numero_matriz="108", fazenda_id=1, **campos))
        s.commit()


def _diagnosticos(engine) -> list[tuple[date, str | None, str | None]]:
    with Session(engine) as s:
        linhas = s.exec(select(Servico).where(Servico.numero_matriz == "108")).all()
    return sorted(
        [(x.data_servico, x.diagnostico, x.origem_diagnostico) for x in linhas],
        key=lambda t: t[0],
    )


def _inseminar(c, data: str, tipo: str = "IA", protocolo: str | None = None):
    return c.post("/reproducao/servico", json={
        "numero_matriz": "108", "data_servico": data, "tipo_servico": tipo, "protocolo": protocolo,
    })


class TestCasoDaMatriz108:
    def test_nova_inseminacao_fecha_a_anterior_em_aberto(self, client):
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), tipo_servico="IA", protocolo="IATF")

        r = _inseminar(c, "2026-08-05", tipo="IS")
        assert r.status_code in (200, 201), r.text

        diags = _diagnosticos(engine)
        assert diags[0][0] == date(2026, 7, 14)
        assert diags[0][1] == "NEGATIVO", "o serviço de 14/07 devia ter fechado como negativo"
        assert diags[0][2] == "reinseminacao", "devia ficar marcado como fechamento automático"
        # A nova inseminação nasce em aberto — ela ainda não foi diagnosticada.
        assert diags[1][1] is None

    def test_o_novo_servico_nao_fecha_a_si_mesmo(self, client):
        c, engine = client
        _inseminar(c, "2026-08-05")
        assert _diagnosticos(engine)[0][1] is None


class TestFormasDeAberto:
    def test_fecha_diagnostico_nulo(self, client):
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)
        _inseminar(c, "2026-08-05")
        assert _diagnosticos(engine)[0][1] == "NEGATIVO"

    def test_fecha_a_string_ABERTO_vinda_do_csv(self, client):
        # 21 registros da base real do produtor vieram assim do Ideagri. Um
        # predicado que só olhasse `is None` deixaria justamente estes de fora.
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico="ABERTO")
        _inseminar(c, "2026-08-05")
        assert _diagnosticos(engine)[0][1] == "NEGATIVO"

    def test_fecha_string_vazia(self, client):
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico="")
        _inseminar(c, "2026-08-05")
        assert _diagnosticos(engine)[0][1] == "NEGATIVO"

    def test_fecha_aberto_com_caixa_diferente(self, client):
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=" aberto ")
        _inseminar(c, "2026-08-05")
        assert _diagnosticos(engine)[0][1] == "NEGATIVO"


class TestNaoTocaOQueJaFoiResolvido:
    def test_nao_sobrescreve_positivo(self, client):
        # POSITIVO é o fluxo de perda de prenhez, não de negativo.
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico="POSITIVO")
        _inseminar(c, "2026-08-05")
        assert _diagnosticos(engine)[0][1] == "POSITIVO"

    def test_nao_sobrescreve_negativo_lancado_por_gente(self, client):
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico="NEGATIVO", data_diagnostico=date(2026, 7, 30))
        _inseminar(c, "2026-08-05")
        assert _diagnosticos(engine)[0][2] is None, "não é fechamento automático — foi lançado por alguém"

    def test_nao_sobrescreve_indefinido(self, client):
        # INDEFINIDO é julgamento explícito do veterinário ("inconclusivo,
        # reavaliar"). Preencher um campo em branco é uma coisa; sobrescrever
        # o que uma pessoa registrou de propósito é outra.
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico="INDEFINIDO")
        _inseminar(c, "2026-08-05")
        assert _diagnosticos(engine)[0][1] == "INDEFINIDO"


class TestRecorteDeLactacao:
    def test_servico_anterior_ao_ultimo_parto_nao_e_tocado(self, client):
        # Lactação anterior — aquela gestação foi resolvida pelo parto.
        c, engine = client
        _servico(engine, data_servico=date(2025, 3, 10), diagnostico=None)
        with Session(engine) as s:
            s.add(Parto(numero_matriz="108", fazenda_id=1, data_parto=date(2025, 12, 20)))
            s.commit()
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)

        _inseminar(c, "2026-08-05")
        diags = _diagnosticos(engine)
        assert diags[0][1] is None, "serviço da lactação anterior não devia ser tocado"
        assert diags[1][1] == "NEGATIVO", "o da lactação corrente devia fechar"

    def test_fecha_todos_os_abertos_da_lactacao_corrente(self, client):
        c, engine = client
        _servico(engine, data_servico=date(2026, 5, 2), diagnostico=None)
        _servico(engine, data_servico=date(2026, 6, 10), diagnostico="ABERTO")
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)

        _inseminar(c, "2026-08-05")
        assert [d[1] for d in _diagnosticos(engine)] == ["NEGATIVO", "NEGATIVO", "NEGATIVO", None]


class TestBordas:
    def test_mesma_data_nao_fecha(self, client):
        # Duas doses no mesmo cio são uma tentativa só, biologicamente.
        c, engine = client
        _servico(engine, data_servico=date(2026, 8, 5), diagnostico=None)
        _inseminar(c, "2026-08-05")
        assert all(d[1] is None for d in _diagnosticos(engine))

    def test_lancamento_retroativo_nao_fecha_servico_posterior(self, client):
        # A fila offline do app pode entregar lançamentos fora de ordem.
        c, engine = client
        _servico(engine, data_servico=date(2026, 8, 20), diagnostico=None)
        _inseminar(c, "2026-08-05")
        diags = _diagnosticos(engine)
        assert diags[-1][0] == date(2026, 8, 20)
        assert diags[-1][1] is None, "serviço POSTERIOR não pode ser fechado por um lançamento retroativo"

    def test_monta_natural_tambem_fecha(self, client):
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)
        r = _inseminar(c, "2026-08-05", tipo="Monta natural")
        assert r.status_code in (200, 201), r.text
        assert _diagnosticos(engine)[0][1] == "NEGATIVO"

    def test_idempotente(self, client):
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)
        _inseminar(c, "2026-08-05")
        _inseminar(c, "2026-08-26")
        diags = _diagnosticos(engine)
        assert diags[0][1] == "NEGATIVO"
        assert diags[1][1] == "NEGATIVO", "a de 05/08 fecha quando chega a de 26/08"


class TestD0DoProtocoloIatf:
    def test_lancar_d0_fecha_o_servico_anterior_em_aberto(self, client):
        # O D0 não cria Servico, mas entrar no protocolo é decidir que a vaca
        # será inseminada de novo — o anterior não pegou.
        c, engine = client
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)

        r = c.post("/reproducao/protocolo-iatf", json={
            "animais": ["108"], "data_d0": "2026-08-05",
        })
        assert r.status_code in (200, 201), r.text
        assert _diagnosticos(engine)[0][1] == "NEGATIVO"


class TestNaoAfetaOutraMatriz:
    def test_servico_de_outra_matriz_nao_e_tocado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="200", fazenda_id=1, ativo=True))
            s.add(Servico(numero_matriz="200", fazenda_id=1, data_servico=date(2026, 7, 14), diagnostico=None))
            s.commit()
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)

        _inseminar(c, "2026-08-05")
        with Session(engine) as s:
            outra = s.exec(select(Servico).where(Servico.numero_matriz == "200")).first()
        assert outra.diagnostico is None


class TestBackfillDoHistorico:
    """O passivo: serviços que já estavam em aberto antes da correção existir."""

    def test_fecha_o_historico_e_preserva_o_ultimo_servico(self, client):
        from fazenda.api.routers.reproducao import backfill_fechar_servicos_abertos

        c, engine = client
        _servico(engine, data_servico=date(2026, 5, 2), diagnostico="ABERTO")
        _servico(engine, data_servico=date(2026, 6, 10), diagnostico=None)
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)

        with Session(engine) as s:
            backfill_fechar_servicos_abertos(s)

        diags = _diagnosticos(engine)
        assert [d[1] for d in diags[:2]] == ["NEGATIVO", "NEGATIVO"]
        assert diags[2][1] is None, "o serviço mais recente pode estar legitimamente aguardando o toque"

    def test_roda_uma_vez_so(self, client):
        from fazenda.api.routers.reproducao import backfill_fechar_servicos_abertos

        c, engine = client
        _servico(engine, data_servico=date(2026, 5, 2), diagnostico=None)
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)

        with Session(engine) as s:
            backfill_fechar_servicos_abertos(s)
        # Alguém lança um diagnóstico à mão depois do backfill...
        with Session(engine) as s:
            alvo = s.exec(select(Servico).where(Servico.data_servico == date(2026, 5, 2))).first()
            alvo.diagnostico = "POSITIVO"
            alvo.origem_diagnostico = None
            s.add(alvo)
            s.commit()
        # ...e o backfill não roda de novo para desfazer.
        with Session(engine) as s:
            backfill_fechar_servicos_abertos(s)
        assert _diagnosticos(engine)[0][1] == "POSITIVO"

    def test_nao_atravessa_o_parto(self, client):
        from fazenda.api.routers.reproducao import backfill_fechar_servicos_abertos

        c, engine = client
        _servico(engine, data_servico=date(2025, 3, 10), diagnostico="ABERTO")
        with Session(engine) as s:
            s.add(Parto(numero_matriz="108", fazenda_id=1, data_parto=date(2025, 12, 20)))
            s.commit()
        _servico(engine, data_servico=date(2026, 5, 2), diagnostico=None)
        _servico(engine, data_servico=date(2026, 7, 14), diagnostico=None)

        with Session(engine) as s:
            backfill_fechar_servicos_abertos(s)

        diags = _diagnosticos(engine)
        assert diags[0][1] == "ABERTO", "serviço da lactação anterior não deve ser reescrito"
        assert diags[1][1] == "NEGATIVO"
